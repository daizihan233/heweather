"""和风天气传感器平台。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
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
from .coordinator import (
    IndicesUpdateCoordinator,
    MinutelyUpdateCoordinator,
    WeatherUpdateCoordinator,
)
from .heweather.const import (
    ATTR_STATES,
    ATTR_UPDATE_TIME,
    ATTRIBUTION,
    DOMAIN,
    RUNTIME_INDICES_COORD,
    RUNTIME_MINUTELY_COORD,
    RUNTIME_WEATHER_COORD,
)


@dataclass(frozen=True, kw_only=True)
class HeWeatherSensorDescription(SensorEntityDescription):
    """传感器描述。"""

    value_fn: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], Any]
    attrs_fn: (
        Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]]
        | None
    ) = None
    source: str = "weather"


def _now(data: dict[str, Any]) -> dict[str, Any]:
    return (data.get("now") or {}) if data else {}


def _air(data: dict[str, Any]) -> dict[str, Any]:
    return (data.get("air") or {}) if data else {}


def _astro(data: dict[str, Any]) -> dict[str, Any]:
    return (data.get("astronomy") or {}) if data else {}


def _air_daily(data: dict[str, Any]) -> dict[str, Any]:
    return (data.get("air_daily") or {}) if data else {}


def _indices(idx: dict[str, Any], key: str) -> list[str]:
    return (idx.get("indices") or {}).get(key) or ["", ""]


def _pollutant(data: dict[str, Any], code: str) -> Any:
    return _air(data).get("pollutants", {}).get(code)


def _index_value(
    key: str,
) -> Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], Any]:
    def _fn(_w: dict, i: dict, _m: dict) -> Any:
        return _indices(i, key)[0] or None

    return _fn


def _index_attrs(
    key: str,
) -> Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], dict[str, Any]]:
    def _fn(_w: dict, i: dict, _m: dict) -> dict[str, Any]:
        pair = _indices(i, key)
        return {ATTR_STATES: pair[1] if len(pair) > 1 else ""}

    return _fn


def _safe_num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_time(value: str | None):
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return parsed


INDEX_ICONS = (
    ("air", "mdi:air-conditioner"),
    ("comf", "mdi:human-greeting"),
    ("cw", "mdi:car"),
    ("drsg", "mdi:hanger"),
    ("flu", "mdi:biohazard"),
    ("sport", "mdi:badminton"),
    ("trav", "mdi:wallet-travel"),
    ("uv", "mdi:sun-wireless"),
    ("guomin", "mdi:sunglasses"),
    ("kongtiao", "mdi:air-conditioner"),
    ("sunglass", "mdi:sunglasses"),
    ("fangshai", "mdi:shield-sun-outline"),
    ("liangshai", "mdi:tshirt-crew-outline"),
    ("jiaotong", "mdi:train-car"),
    ("fishing", "mdi:fish"),
    ("makeup", "mdi:lipstick"),
)

SENSOR_DESCRIPTIONS: tuple[HeWeatherSensorDescription, ...] = (
    HeWeatherSensorDescription(
        key="temperature",
        translation_key="heweather_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda w, i, m: _now(w).get("temp"),
    ),
    HeWeatherSensorDescription(
        key="humidity",
        translation_key="heweather_humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda w, i, m: _now(w).get("humidity"),
    ),
    HeWeatherSensorDescription(
        key="feelsLike",
        translation_key="heweather_feelslike",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda w, i, m: _now(w).get("feelsLike"),
    ),
    HeWeatherSensorDescription(
        key="text",
        translation_key="heweather_text",
        icon="mdi:weather-partly-cloudy",
        value_fn=lambda w, i, m: _now(w).get("text"),
    ),
    HeWeatherSensorDescription(
        key="precip",
        translation_key="heweather_precip",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        value_fn=lambda w, i, m: _now(w).get("precip"),
    ),
    HeWeatherSensorDescription(
        key="windDir",
        translation_key="heweather_winddir",
        icon="mdi:windsock",
        value_fn=lambda w, i, m: _now(w).get("windDir"),
    ),
    HeWeatherSensorDescription(
        key="windScale",
        translation_key="heweather_windscale",
        icon="mdi:weather-windy",
        value_fn=lambda w, i, m: _now(w).get("windScale"),
    ),
    HeWeatherSensorDescription(
        key="windSpeed",
        translation_key="heweather_windspeed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
        value_fn=lambda w, i, m: _now(w).get("windSpeed"),
    ),
    HeWeatherSensorDescription(
        key="dew",
        translation_key="heweather_dew",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-water",
        value_fn=lambda w, i, m: _now(w).get("dew"),
    ),
    HeWeatherSensorDescription(
        key="pressure",
        translation_key="heweather_pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=lambda w, i, m: _now(w).get("pressure"),
    ),
    HeWeatherSensorDescription(
        key="vis",
        translation_key="heweather_vis",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:eye",
        value_fn=lambda w, i, m: _now(w).get("vis"),
    ),
    HeWeatherSensorDescription(
        key="cloud",
        translation_key="heweather_cloud",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cloud-percent",
        value_fn=lambda w, i, m: _now(w).get("cloud"),
    ),
    HeWeatherSensorDescription(
        key="primary",
        translation_key="heweather_primary",
        icon="mdi:weather-dust",
        value_fn=lambda w, i, m: _air(w).get("primary"),
    ),
    HeWeatherSensorDescription(
        key="category",
        translation_key="heweather_category",
        icon="mdi:walk",
        value_fn=lambda w, i, m: _air(w).get("category"),
    ),
    HeWeatherSensorDescription(
        key="level",
        translation_key="heweather_level",
        icon="mdi:walk",
        value_fn=lambda w, i, m: _air(w).get("level"),
    ),
    HeWeatherSensorDescription(
        key="qlty",
        translation_key="heweather_qlty",
        icon="mdi:quality-high",
        value_fn=lambda w, i, m: _air(w).get("qlty"),
    ),
    HeWeatherSensorDescription(
        key="pm2p5",
        translation_key="heweather_pm25",
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:walk",
        value_fn=lambda w, i, m: _pollutant(w, "pm2p5"),
    ),
    HeWeatherSensorDescription(
        key="pm10",
        translation_key="heweather_pm10",
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:walk",
        value_fn=lambda w, i, m: _pollutant(w, "pm10"),
    ),
    HeWeatherSensorDescription(
        key="no2",
        translation_key="heweather_no2",
        device_class=SensorDeviceClass.NITROGEN_DIOXIDE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:emoticon-dead",
        value_fn=lambda w, i, m: _pollutant(w, "no2"),
    ),
    HeWeatherSensorDescription(
        key="so2",
        translation_key="heweather_so2",
        device_class=SensorDeviceClass.SULPHUR_DIOXIDE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:emoticon-dead",
        value_fn=lambda w, i, m: _pollutant(w, "so2"),
    ),
    HeWeatherSensorDescription(
        key="co",
        translation_key="heweather_co",
        device_class=SensorDeviceClass.CO,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule-co",
        value_fn=lambda w, i, m: _pollutant(w, "co"),
    ),
    HeWeatherSensorDescription(
        key="o3",
        translation_key="heweather_o3",
        device_class=SensorDeviceClass.OZONE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-cloudy",
        value_fn=lambda w, i, m: _pollutant(w, "o3"),
    ),
    HeWeatherSensorDescription(
        key="no",
        translation_key="heweather_no",
        device_class=SensorDeviceClass.NITROGEN_MONOXIDE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:emoticon-dead",
        value_fn=lambda w, i, m: _pollutant(w, "no"),
    ),
    HeWeatherSensorDescription(
        key="nmhc",
        translation_key="heweather_nmhc",
        icon="mdi:emoticon-dead",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda w, i, m: _pollutant(w, "nmhc"),
    ),
    HeWeatherSensorDescription(
        key="disaster_warn",
        translation_key="heweather_disaster_warn",
        icon="mdi:alert",
        value_fn=lambda w, i, m: "on"
        if (w.get("disaster") or {}).get("active")
        else "off",
        attrs_fn=lambda w, i, m: {
            ATTR_STATES: (w.get("disaster") or {}).get("text") or ""
        },
    ),
    *[
        HeWeatherSensorDescription(
            key=key,
            translation_key=f"suggestion_{key}",
            icon=icon,
            source="indices",
            value_fn=_index_value(key),
            attrs_fn=_index_attrs(key),
        )
        for key, icon in INDEX_ICONS
    ],
    HeWeatherSensorDescription(
        key="minutely_summary",
        translation_key="heweather_minutely_summary",
        icon="mdi:weather-pouring",
        source="minutely",
        value_fn=lambda w, i, m: (m or {}).get("summary"),
    ),
    HeWeatherSensorDescription(
        key="minutely_precip",
        translation_key="heweather_minutely_precip",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        icon="mdi:water",
        source="minutely",
        value_fn=lambda w, i, m: (m or {}).get("first_precip"),
    ),
    HeWeatherSensorDescription(
        key="sunrise",
        translation_key="heweather_sunrise",
        icon="mdi:weather-sunset-up",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda w, i, m: _parse_time(_astro(w).get("sunrise")),
    ),
    HeWeatherSensorDescription(
        key="sunset",
        translation_key="heweather_sunset",
        icon="mdi:weather-sunset-down",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda w, i, m: _parse_time(_astro(w).get("sunset")),
    ),
    HeWeatherSensorDescription(
        key="moonrise",
        translation_key="heweather_moonrise",
        icon="mdi:moon-waning-crescent",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda w, i, m: _parse_time(_astro(w).get("moonrise")),
    ),
    HeWeatherSensorDescription(
        key="moonset",
        translation_key="heweather_moonset",
        icon="mdi:moon-waning-crescent",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda w, i, m: _parse_time(_astro(w).get("moonset")),
    ),
    HeWeatherSensorDescription(
        key="moon_phase",
        translation_key="heweather_moon_phase",
        icon="mdi:moon-full",
        value_fn=lambda w, i, m: _astro(w).get("moon_phase"),
    ),
    HeWeatherSensorDescription(
        key="moon_illumination",
        translation_key="heweather_moon_illumination",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:moon-full",
        value_fn=lambda w, i, m: _safe_num(_astro(w).get("moon_illumination")),
    ),
    HeWeatherSensorDescription(
        key="aqi_daily_category",
        translation_key="heweather_aqi_daily_category",
        icon="mdi:air-filter",
        value_fn=lambda w, i, m: _air_daily(w).get("category"),
    ),
    HeWeatherSensorDescription(
        key="aqi_daily_level",
        translation_key="heweather_aqi_daily_level",
        icon="mdi:air-filter",
        value_fn=lambda w, i, m: _air_daily(w).get("level"),
    ),
    HeWeatherSensorDescription(
        key="aqi_daily_primary",
        translation_key="heweather_aqi_daily_primary",
        icon="mdi:air-filter",
        value_fn=lambda w, i, m: _air_daily(w).get("primary"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置传感器实体。"""
    runtime = hass.data[DOMAIN][config_entry.entry_id]
    weather_coord: WeatherUpdateCoordinator = runtime[RUNTIME_WEATHER_COORD]
    indices_coord: IndicesUpdateCoordinator = runtime[RUNTIME_INDICES_COORD]
    minutely_coord: MinutelyUpdateCoordinator = runtime[RUNTIME_MINUTELY_COORD]

    lon = weather_coord.longitude
    lat = weather_coord.latitude

    entities = [
        HeWeatherSensor(
            weather_coord,
            indices_coord,
            minutely_coord,
            description,
            lon,
            lat,
        )
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class HeWeatherSensor(CoordinatorEntity, SensorEntity):
    """和风传感器。"""

    entity_description: HeWeatherSensorDescription
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        weather_coord: WeatherUpdateCoordinator,
        indices_coord: IndicesUpdateCoordinator,
        minutely_coord: MinutelyUpdateCoordinator,
        description: HeWeatherSensorDescription,
        longitude: str,
        latitude: str,
    ) -> None:
        if description.source == "indices":
            super().__init__(indices_coord)
        elif description.source == "minutely":
            super().__init__(minutely_coord)
        else:
            super().__init__(weather_coord)

        self.entity_description = description
        self._weather = weather_coord
        self._indices = indices_coord
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
    def available(self) -> bool:
        source = self.entity_description.source
        if source == "indices":
            return self._indices.last_update_success
        if source == "minutely":
            data = self._minutely.data or {}
            return bool(
                self._minutely.last_update_success and data.get("available", True)
            )
        return self._weather.last_update_success

    @property
    def native_value(self) -> Any:
        w = self._weather.data or {}
        i = self._indices.data or {}
        m = self._minutely.data or {}
        return self.entity_description.value_fn(w, i, m)

    @property
    def native_unit_of_measurement(self) -> str | None:
        code_map = {
            "pm2p5": "pm2p5",
            "pm10": "pm10",
            "no2": "no2",
            "so2": "so2",
            "co": "co",
            "o3": "o3",
            "no": "no",
            "nmhc": "nmhc",
        }
        key = self.entity_description.key
        if key in code_map:
            units = (_air(self._weather.data or {})).get("pollutant_units") or {}
            unit = units.get(code_map[key])
            if unit:
                return unit
        return self.entity_description.native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        w = self._weather.data or {}
        i = self._indices.data or {}
        m = self._minutely.data or {}
        if self.entity_description.attrs_fn:
            attrs.update(self.entity_description.attrs_fn(w, i, m) or {})
        update_time = w.get("update_time") or i.get("update_time")
        if update_time:
            attrs[ATTR_UPDATE_TIME] = update_time
        return attrs
