"""数据更新协调器。"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import QWeatherApiClient, QWeatherApiError
from .heweather.const import (
    DISASTER_LEVEL,
    DOMAIN,
    EVENT_DISASTER_CLEARED,
    EVENT_DISASTER_NEW,
    INDEX_TYPE_MAP,
    INDICES_UPDATE_INTERVAL,
    MINUTELY_UPDATE_INTERVAL,
    WEATHER_UPDATE_INTERVAL,
    CONF_DISASTERLEVEL,
    CONF_DISASTERMSG,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)

_LOGGER = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def condition_from_text(text: str | None) -> str:
    """将和风中文天气描述映射为 HA condition。"""
    from .heweather.const import CONDITION_CLASSES

    if not text:
        return "unknown"
    for condition, keywords in CONDITION_CLASSES.items():
        if text in keywords:
            return condition
    return "unknown"


def parse_cn_mee_air(air_data: dict[str, Any] | None) -> dict[str, Any]:
    """解析实时空气质量（优先 cn-mee）。"""
    result: dict[str, Any] = {
        "qlty": None,
        "level": None,
        "category": None,
        "primary": None,
        "pollutants": {},
        "pollutant_units": {},
        "hourly_attr": None,
    }
    if not air_data:
        return result

    indexes = air_data.get("indexes") or []
    air_index = next((i for i in indexes if i.get("code") == "cn-mee"), None)
    if air_index is None and indexes:
        air_index = indexes[0]
    if air_index:
        result["qlty"] = air_index.get("aqiDisplay")
        result["level"] = air_index.get("level")
        result["category"] = air_index.get("category")
        primary = air_index.get("primaryPollutant") or {}
        if isinstance(primary, dict):
            result["primary"] = primary.get("name")

    for pollutant in air_data.get("pollutants") or []:
        code = pollutant.get("code")
        if not code:
            continue
        conc = pollutant.get("concentration") or {}
        result["pollutants"][code] = conc.get("value")
        result["pollutant_units"][code] = conc.get("unit")
    return result


def parse_air_daily(air_daily: dict[str, Any] | None) -> dict[str, Any]:
    """取第一天（通常为明日）AQI 摘要。"""
    empty = {"category": None, "level": None, "primary": None, "qlty": None}
    if not air_daily:
        return empty
    days = air_daily.get("days") or []
    if not days:
        return empty
    day = days[0]
    indexes = day.get("indexes") or []
    air_index = next((i for i in indexes if i.get("code") == "cn-mee"), None)
    if air_index is None and indexes:
        air_index = indexes[0]
    if not air_index:
        return empty
    primary = air_index.get("primaryPollutant") or {}
    return {
        "category": air_index.get("category"),
        "level": air_index.get("level"),
        "qlty": air_index.get("aqiDisplay"),
        "primary": primary.get("name") if isinstance(primary, dict) else None,
    }


def parse_disaster(
    alert_data: dict[str, Any] | None,
    disaster_level: str,
    disaster_msg: str,
) -> dict[str, Any]:
    """按订阅等级过滤预警。"""
    threshold = int(disaster_level)
    alerts_raw = (alert_data or {}).get("alerts")
    if alerts_raw is None:
        alerts: list[dict[str, Any]] = []
    elif isinstance(alerts_raw, dict):
        alerts = [alerts_raw]
    elif isinstance(alerts_raw, list):
        alerts = alerts_raw
    else:
        alerts = []

    # allmsg: 仅 description；title: 仅 headline；多条用中文分号拼接
    all_parts: list[str] = []
    title_parts: list[str] = []
    matched: list[dict[str, Any]] = []
    for item in alerts:
        severity = str(item.get("severity", "")).lower()
        if severity in DISASTER_LEVEL and DISASTER_LEVEL[severity] >= threshold:
            matched.append(item)
            description = (item.get("description") or "").strip()
            headline = (item.get("headline") or "").strip()
            if description:
                all_parts.append(description)
            if headline:
                title_parts.append(headline)

    if not matched:
        # 无匹配预警：空文案，避免「近日无…」被语音/通知误播
        text = ""
        active = False
    elif disaster_msg == "title":
        text = "；".join(title_parts)
        active = True
    else:
        text = "；".join(all_parts)
        active = True

    return {
        "active": active,
        "text": text,
        "alerts": matched,
    }


def alert_key(alert: dict[str, Any]) -> str:
    """预警唯一标识（用于新旧对比）：severity:headline。"""
    headline = (alert.get("headline") or "").strip()
    severity = (alert.get("severity") or "").strip().lower()
    return f"{severity}:{headline}"


def _fire_disaster_events(
    hass: HomeAssistant,
    new_alerts: list[dict[str, Any]],
    cleared_alerts: list[dict[str, Any]],
    disaster_msg: str,
) -> None:
    """为新增/解除预警 fire 独立事件。

    新增事件 payload:
      - text:          跟随用户 disastermsg 配置（allmsg→description，title→headline）
      - text_long:     永远是 description（长文本，适合播报）
      - text_short:    永远是 headline（短文本，适合播报）
      - alerts:        新增的原始预警列表
      - source:        "heweather"

    解除事件 payload:
      - text_short:    永远是 headline（短文本，适合播报）
      - alerts:        解除的原始预警列表
      - source:        "heweather"
    """
    if new_alerts:
        descs = [a.get("description") or "" for a in new_alerts]
        headlines = [a.get("headline") or "" for a in new_alerts]
        text_long = "；".join(d for d in descs if d.strip())
        text_short = "；".join(h for h in headlines if h.strip())
        # text 跟随用户配置
        text = text_short if disaster_msg == "title" else text_long
        hass.bus.async_fire(
            EVENT_DISASTER_NEW,
            {
                "text": text,
                "text_long": text_long,
                "text_short": text_short,
                "alerts": new_alerts,
                "source": DOMAIN,
            },
        )

    if cleared_alerts:
        headlines = [a.get("headline") or "" for a in cleared_alerts]
        text_short = "；".join(h for h in headlines if h.strip())
        hass.bus.async_fire(
            EVENT_DISASTER_CLEARED,
            {
                "text_short": text_short,
                "alerts": cleared_alerts,
                "source": DOMAIN,
            },
        )


def parse_indices(indices_data: dict[str, Any] | None) -> dict[str, list[str]]:
    """type → [category, text]。"""
    parsed: dict[str, list[str]] = {}
    if not indices_data:
        return parsed
    for item in indices_data.get("daily") or []:
        type_id = str(item.get("type", ""))
        key = INDEX_TYPE_MAP.get(type_id)
        if not key:
            continue
        parsed[key] = [
            item.get("category") or "",
            item.get("text") or "",
        ]
    return parsed


def parse_minutely(minutely_data: dict[str, Any] | None) -> dict[str, Any]:
    summary = (minutely_data or {}).get("summary")
    items = (minutely_data or {}).get("minutely") or []
    first_precip = None
    has_precip = False
    for row in items:
        precip = _safe_float(row.get("precip"))
        if precip is not None and precip > 0:
            has_precip = True
            if first_precip is None:
                first_precip = precip
    return {
        "summary": summary,
        "has_precip": has_precip,
        "first_precip": first_precip,
        "minutely": items,
    }


def parse_now(weather_data: dict[str, Any] | None) -> dict[str, Any]:
    now = (weather_data or {}).get("now") or {}
    return {
        "temp": _safe_float(now.get("temp")),
        "humidity": _safe_float(now.get("humidity")),
        "feelsLike": _safe_float(now.get("feelsLike")),
        "text": now.get("text"),
        "windDir": now.get("windDir"),
        "windScale": now.get("windScale"),
        "windSpeed": _safe_float(now.get("windSpeed")),
        "precip": _safe_float(now.get("precip")),
        "pressure": _safe_float(now.get("pressure")),
        "vis": _safe_float(now.get("vis")),
        "cloud": _safe_float(now.get("cloud")),
        "dew": _safe_float(now.get("dew")),
        "obsTime": now.get("obsTime"),
        "icon": now.get("icon"),
        "condition": condition_from_text(now.get("text")),
    }


def parse_daily_forecast(forecast_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for day in (forecast_data or {}).get("daily") or []:
        text_day = day.get("textDay")
        result.append(
            {
                "datetime": day.get("fxDate"),
                "condition": condition_from_text(text_day),
                "native_temperature": _safe_float(day.get("tempMax")),
                "native_templow": _safe_float(day.get("tempMin")),
                "text": text_day,
                "sunrise": day.get("sunrise"),
                "sunset": day.get("sunset"),
                "moonPhase": day.get("moonPhase"),
                "precip": _safe_float(day.get("precip")),
                "humidity": _safe_float(day.get("humidity")),
                "uvIndex": day.get("uvIndex"),
            }
        )
    return result


def parse_hourly_forecast(forecast_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for hour in (forecast_data or {}).get("hourly") or []:
        text = hour.get("text")
        result.append(
            {
                "datetime": hour.get("fxTime"),
                "condition": condition_from_text(text),
                "native_temperature": _safe_float(hour.get("temp")),
                "humidity": _safe_float(hour.get("humidity")),
                "native_precipitation": _safe_float(hour.get("precip")),
                "precipitation_probability": _safe_float(hour.get("pop")),
                "wind_bearing": hour.get("windDir"),
                "native_wind_speed": _safe_float(hour.get("windSpeed")),
                "text": text,
            }
        )
    return result


class WeatherUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """实况 + 预报 + 空气 + 预警 + 天文。"""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: QWeatherApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_weather",
            update_interval=timedelta(seconds=WEATHER_UPDATE_INTERVAL),
        )
        self.entry = entry
        self.api = api
        self.longitude = entry.data[CONF_LONGITUDE]
        self.latitude = entry.data[CONF_LATITUDE]
        self.location = f"{self.longitude},{self.latitude}"
        self._last_disaster_alerts: list[dict[str, Any]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        lon, lat = self.longitude, self.latitude
        today = date.today().strftime("%Y%m%d")

        async def _soft(coro, label: str):
            try:
                return await coro
            except QWeatherApiError as err:
                _LOGGER.warning("%s failed: %s", label, err)
                return None

        try:
            now_raw, daily_raw, hourly_raw = await asyncio.gather(
                self.api.weather_now(lon, lat),
                self.api.weather_7d(lon, lat),
                self.api.weather_24h(lon, lat),
            )
        except QWeatherApiError as err:
            raise UpdateFailed(str(err)) from err

        air_raw, air_daily_raw, alert_raw, sun_raw, moon_raw = await asyncio.gather(
            _soft(self.api.air_current(lon, lat), "air_current"),
            _soft(self.api.air_daily(lon, lat), "air_daily"),
            _soft(self.api.weather_alert(lon, lat), "weather_alert"),
            _soft(self.api.astronomy_sun(lon, lat, today), "sun"),
            _soft(self.api.astronomy_moon(lon, lat, today), "moon"),
        )

        now = parse_now(now_raw)
        daily = parse_daily_forecast(daily_raw)
        hourly = parse_hourly_forecast(hourly_raw)
        air = parse_cn_mee_air(air_raw)
        air_daily = parse_air_daily(air_daily_raw)

        # --- 灾害预警：API 失败保留旧状态，成功时 diff + fire 事件 ---
        disaster_level = str(self.entry.data.get(CONF_DISASTERLEVEL, "3"))
        disaster_msg = str(self.entry.data.get(CONF_DISASTERMSG, "allmsg"))

        if alert_raw is not None:
            # API 成功：解析 + diff + fire 事件
            disaster = parse_disaster(alert_raw, disaster_level, disaster_msg)
            new_matched = disaster.get("alerts") or []

            # 对比新旧
            prev_keys = {alert_key(a) for a in self._last_disaster_alerts}
            curr_keys = {alert_key(a) for a in new_matched}

            if prev_keys or curr_keys:
                _fire_disaster_events(
                    self.hass,
                    new_alerts=[a for a in new_matched if alert_key(a) not in prev_keys],
                    cleared_alerts=[a for a in self._last_disaster_alerts if alert_key(a) not in curr_keys],
                    disaster_msg=disaster_msg,
                )

            self._last_disaster_alerts = new_matched
        else:
            # API 失败：保留上一轮的预警数据（避免误清）
            _LOGGER.warning(
                "weather_alert API failed, preserving previous disaster state"
            )
            disaster = {
                "active": bool(self._last_disaster_alerts),
                "text": "",
                "alerts": list(self._last_disaster_alerts),
            }

        # 日出日落：优先天文 API，否则回退日预报首日
        sunrise = (sun_raw or {}).get("sunrise")
        sunset = (sun_raw or {}).get("sunset")
        if not sunrise and daily:
            sunrise = daily[0].get("sunrise")
        if not sunset and daily:
            sunset = daily[0].get("sunset")

        moonrise = (moon_raw or {}).get("moonrise")
        moonset = (moon_raw or {}).get("moonset")
        moon_phase_name = None
        moon_illumination = None
        phases = (moon_raw or {}).get("moonPhase") or []
        if phases:
            moon_phase_name = phases[0].get("name")
            moon_illumination = phases[0].get("illumination")
        elif daily:
            moon_phase_name = daily[0].get("moonPhase")

        return {
            "now": now,
            "daily": daily,
            "hourly": hourly,
            "air": air,
            "air_daily": air_daily,
            "disaster": disaster,
            "astronomy": {
                "sunrise": sunrise,
                "sunset": sunset,
                "moonrise": moonrise,
                "moonset": moonset,
                "moon_phase": moon_phase_name,
                "moon_illumination": moon_illumination,
            },
            "update_time": now.get("obsTime"),
            "location": self.location,
        }


class IndicesUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """生活指数。"""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: QWeatherApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_indices",
            update_interval=timedelta(seconds=INDICES_UPDATE_INTERVAL),
        )
        self.entry = entry
        self.api = api
        self.longitude = entry.data[CONF_LONGITUDE]
        self.latitude = entry.data[CONF_LATITUDE]

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            raw = await self.api.indices_1d(self.longitude, self.latitude, "0")
        except QWeatherApiError as err:
            raise UpdateFailed(str(err)) from err

        indices = parse_indices(raw)
        # type=0 若缺钓鱼/化妆，补一次
        missing = [t for t, k in (("4", "fishing"), ("13", "makeup")) if k not in indices]
        if missing:
            try:
                extra = await self.api.indices_1d(
                    self.longitude, self.latitude, ",".join(missing)
                )
                indices.update(parse_indices(extra))
            except QWeatherApiError as err:
                _LOGGER.debug("optional indices failed: %s", err)

        return {
            "indices": indices,
            "update_time": (raw or {}).get("updateTime"),
        }


class MinutelyUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """分钟级降水（可选，失败不阻断）。"""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: QWeatherApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_minutely",
            update_interval=timedelta(seconds=MINUTELY_UPDATE_INTERVAL),
        )
        self.entry = entry
        self.api = api
        self.longitude = entry.data[CONF_LONGITUDE]
        self.latitude = entry.data[CONF_LATITUDE]

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            raw = await self.api.minutely_5m(self.longitude, self.latitude)
        except QWeatherApiError as err:
            _LOGGER.warning("minutely failed: %s", err)
            return parse_minutely(None) | {"available": False, "error": str(err)}
        return parse_minutely(raw) | {"available": True}
