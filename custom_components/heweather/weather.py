"""和风天气 weather 平台。"""

from __future__ import annotations

from typing import Any, cast

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import unique_id_for
from .coordinator import WeatherUpdateCoordinator
from .heweather.const import (
    ATTRIBUTION,
    DOMAIN,
    RUNTIME_WEATHER_COORD,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: WeatherUpdateCoordinator = runtime[RUNTIME_WEATHER_COORD]
    async_add_entities([HeWeatherEntity(coordinator)])


class HeWeatherEntity(CoordinatorEntity[WeatherUpdateCoordinator], WeatherEntity):
    """和风 Weather 实体。"""

    _attr_has_entity_name = True
    _attr_name = "heweather"
    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(self, coordinator: WeatherUpdateCoordinator) -> None:
        super().__init__(coordinator)
        lon = coordinator.longitude
        lat = coordinator.latitude
        # 保持旧 unique_id 前缀 localweather_
        self._attr_unique_id = f"localweather_{lon}_{lat}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{lon},{lat}")},
            name="和风天气",
            manufacturer="QWeather",
            model="API v7",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _now(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("now") or {}

    @property
    def condition(self) -> str | None:
        return self._now.get("condition") or "unknown"

    @property
    def native_temperature(self) -> float | None:
        return self._now.get("temp")

    @property
    def humidity(self) -> float | None:
        return self._now.get("humidity")

    @property
    def native_pressure(self) -> float | None:
        return self._now.get("pressure")

    @property
    def native_wind_speed(self) -> float | None:
        return self._now.get("windSpeed")

    @property
    def wind_bearing(self) -> str | float | None:
        return self._now.get("windDir")

    @property
    def native_visibility(self) -> float | None:
        return self._now.get("vis")

    @property
    def native_precipitation(self) -> float | None:
        return self._now.get("precip")

    @property
    def native_dew_point(self) -> float | None:
        return self._now.get("dew")

    @property
    def native_apparent_temperature(self) -> float | None:
        return self._now.get("feelsLike")

    @property
    def cloud_coverage(self) -> float | None:
        return self._now.get("cloud")

    def _to_datetime(self, value: str | None):
        if not value:
            return None
        parsed = dt_util.parse_datetime(value)
        if parsed is None:
            # 日预报 fxDate 可能仅日期
            try:
                parsed = dt_util.as_local(dt_util.parse_datetime(f"{value}T00:00:00"))
            except (TypeError, ValueError):
                return value
        return parsed.isoformat() if parsed else value

    async def async_forecast_daily(self) -> list[Forecast] | None:
        daily = (self.coordinator.data or {}).get("daily") or []
        forecasts: list[Forecast] = []
        for day in daily:
            item: Forecast = {
                "datetime": cast(str, self._to_datetime(day.get("datetime"))),
                "condition": day.get("condition"),
                "native_temperature": day.get("native_temperature"),
                "native_templow": day.get("native_templow"),
            }
            if day.get("text"):
                item["text"] = day["text"]  # type: ignore[typeddict-unknown-key]
            forecasts.append(item)
        return forecasts

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        hourly = (self.coordinator.data or {}).get("hourly") or []
        forecasts: list[Forecast] = []
        for hour in hourly:
            item: Forecast = {
                "datetime": cast(str, self._to_datetime(hour.get("datetime"))),
                "condition": hour.get("condition"),
                "native_temperature": hour.get("native_temperature"),
                "humidity": hour.get("humidity"),
                "native_precipitation": hour.get("native_precipitation"),
                "precipitation_probability": hour.get("precipitation_probability"),
                "wind_bearing": hour.get("wind_bearing"),
                "native_wind_speed": hour.get("native_wind_speed"),
            }
            if hour.get("text"):
                item["text"] = hour["text"]  # type: ignore[typeddict-unknown-key]
            forecasts.append(item)
        return forecasts
