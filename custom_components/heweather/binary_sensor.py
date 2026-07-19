"""和风天气 binary_sensor 平台。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import unique_id_for
from .coordinator import (
    MinutelyUpdateCoordinator,
    WeatherUpdateCoordinator,
    condition_from_text,
)
from .heweather.const import (
    ATTR_STATES,
    ATTRIBUTION,
    DOMAIN,
    DRY_CONDITIONS,
    RUNTIME_MINUTELY_COORD,
    RUNTIME_WEATHER_COORD,
)


@dataclass(frozen=True, kw_only=True)
class HeWeatherBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor 描述。"""

    is_on_fn: Callable[[dict[str, Any], dict[str, Any]], bool]
    attrs_fn: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None
    source: str = "weather"


def rain_warn_active(weather_data: dict[str, Any]) -> bool:
    """下一小时是否可能有雨雪（对齐 README 模板逻辑）。"""
    hourly = weather_data.get("hourly") or []
    if not hourly:
        return False
    first = hourly[0]
    condition = first.get("condition") or condition_from_text(first.get("text"))
    return condition not in DRY_CONDITIONS


def rain_warn_attrs(weather_data: dict[str, Any]) -> dict[str, Any]:
    hourly = weather_data.get("hourly") or []
    if not hourly:
        return {ATTR_STATES: "暂无小时预报"}
    first = hourly[0]
    text = first.get("text") or ""
    pop = first.get("precipitation_probability")
    if rain_warn_active(weather_data):
        msg = f"接下来一小时会有{text}"
        if pop is not None:
            msg += f"，降水概率为 {pop}%"
    else:
        msg = f"未来一小时，天气{text}，没有降雨"
    return {
        ATTR_STATES: msg,
        "text": text,
        "precipitation_probability": pop,
        "condition": first.get("condition"),
    }


BINARY_DESCRIPTIONS: tuple[HeWeatherBinaryDescription, ...] = (
    HeWeatherBinaryDescription(
        key="disaster_warn_binary",
        translation_key="heweather_disaster_warn_binary",
        device_class=BinarySensorDeviceClass.SAFETY,
        icon="mdi:alert",
        is_on_fn=lambda w, m: bool((w.get("disaster") or {}).get("active")),
        attrs_fn=lambda w, m: {
            ATTR_STATES: (w.get("disaster") or {}).get("text") or "",
            "alerts": (w.get("disaster") or {}).get("alerts") or [],
        },
    ),
    HeWeatherBinaryDescription(
        key="rain_warn",
        translation_key="heweather_rain_warn",
        device_class=BinarySensorDeviceClass.MOISTURE,
        icon="mdi:weather-rainy",
        is_on_fn=lambda w, m: rain_warn_active(w),
        attrs_fn=lambda w, m: rain_warn_attrs(w),
    ),
    HeWeatherBinaryDescription(
        key="next_precip",
        translation_key="heweather_next_precip",
        device_class=BinarySensorDeviceClass.MOISTURE,
        icon="mdi:weather-pouring",
        source="minutely",
        is_on_fn=lambda w, m: bool((m or {}).get("has_precip")),
        attrs_fn=lambda w, m: {
            ATTR_STATES: (m or {}).get("summary") or "",
            "first_precip": (m or {}).get("first_precip"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][config_entry.entry_id]
    weather_coord: WeatherUpdateCoordinator = runtime[RUNTIME_WEATHER_COORD]
    minutely_coord: MinutelyUpdateCoordinator = runtime[RUNTIME_MINUTELY_COORD]
    lon = weather_coord.longitude
    lat = weather_coord.latitude

    async_add_entities(
        [
            HeWeatherBinarySensor(weather_coord, minutely_coord, desc, lon, lat)
            for desc in BINARY_DESCRIPTIONS
        ]
    )


class HeWeatherBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """和风 binary sensor。"""

    entity_description: HeWeatherBinaryDescription
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        weather_coord: WeatherUpdateCoordinator,
        minutely_coord: MinutelyUpdateCoordinator,
        description: HeWeatherBinaryDescription,
        longitude: str,
        latitude: str,
    ) -> None:
        if description.source == "minutely":
            super().__init__(minutely_coord)
        else:
            super().__init__(weather_coord)
        self.entity_description = description
        self._weather = weather_coord
        self._minutely = minutely_coord
        object_id = description.translation_key or description.key
        self._attr_unique_id = unique_id_for(object_id, longitude, latitude)
        self._attr_translation_key = description.translation_key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{longitude},{latitude}")},
            name="和风天气",
            manufacturer="QWeather",
            model="API v7",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool:
        w = self._weather.data or {}
        m = self._minutely.data or {}
        return self.entity_description.is_on_fn(w, m)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        w = self._weather.data or {}
        m = self._minutely.data or {}
        if self.entity_description.attrs_fn:
            return self.entity_description.attrs_fn(w, m) or {}
        return {}
