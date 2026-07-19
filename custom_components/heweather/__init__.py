"""和风天气 Home Assistant 集成入口。"""

from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import QWeatherApiClient
from .coordinator import (
    IndicesUpdateCoordinator,
    MinutelyUpdateCoordinator,
    WeatherUpdateCoordinator,
)
from .heweather.const import (
    CONF_AUTH_METHOD,
    CONF_HOST,
    CONF_JWT_KID,
    CONF_JWT_SUB,
    CONF_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STORAGE_PATH,
    DOMAIN,
    PLATFORMS,
    RUNTIME_API,
    RUNTIME_INDICES_COORD,
    RUNTIME_MINUTELY_COORD,
    RUNTIME_WEATHER_COORD,
)
from .heweather.heweather_cert import HeWeatherCert

_LOGGER = logging.getLogger(__name__)


async def cleanup_duplicate_entities_on_startup(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """按 object_id 后缀分组清理重复实体。"""
    entity_registry = er.async_get(hass)
    lon = config_entry.data.get(CONF_LONGITUDE)
    lat = config_entry.data.get(CONF_LATITUDE)
    if not lon or not lat:
        return

    suffix = f"_{lon}_{lat}"
    entities_by_prefix: dict[str, list[tuple[str, Any]]] = {}

    for entity_id, entity in entity_registry.entities.items():
        if entity.config_entry_id != config_entry.entry_id:
            continue
        if not entity.unique_id or not entity.unique_id.endswith(suffix):
            continue
        prefix = entity.unique_id[: -len(suffix)]
        entities_by_prefix.setdefault(prefix, []).append((entity_id, entity))

    entities_to_remove: list[str] = []
    for prefix, entities in entities_by_prefix.items():
        if len(entities) > 1:
            entities.sort(key=lambda x: x[0])
            for entity_id, _entity in entities[:-1]:
                entities_to_remove.append(entity_id)
                _LOGGER.info("Found duplicate entity for %s: %s", prefix, entity_id)

    for entity_id in entities_to_remove:
        _LOGGER.info("Removing duplicate entity on startup: %s", entity_id)
        entity_registry.async_remove(entity_id)

    if entities_to_remove:
        _LOGGER.info(
            "Cleaned up %s duplicate entities on startup", len(entities_to_remove)
        )


async def migrate_legacy_unique_ids(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """迁移历史拼写 temprature 等 unique_id。"""
    entity_registry = er.async_get(hass)
    lon = config_entry.data.get(CONF_LONGITUDE)
    lat = config_entry.data.get(CONF_LATITUDE)
    if not lon or not lat:
        return

    # 旧 unique_id 已使用 heweather_temperature，一般无需迁移；
    # 若存在 heweather_temprature_* 则改写
    legacy_prefix = f"heweather_temprature_{lon}_{lat}"
    new_uid = f"heweather_temperature_{lon}_{lat}"
    for entity_id, entity in list(entity_registry.entities.items()):
        if entity.config_entry_id != config_entry.entry_id:
            continue
        if entity.unique_id == legacy_prefix:
            try:
                entity_registry.async_update_entity(
                    entity_id, new_unique_id=new_uid
                )
                _LOGGER.info("Migrated unique_id %s -> %s", legacy_prefix, new_uid)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("unique_id migration failed: %s", err)


async def async_setup(hass: HomeAssistant, hass_config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    import asyncio

    loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
    hass.data.setdefault(DOMAIN, {})

    cert: Optional[HeWeatherCert] = hass.data[DOMAIN].get("heweather_cert")
    if not cert:
        cert = HeWeatherCert(
            root_path=config_entry.data.get(CONF_STORAGE_PATH), loop=loop
        )
        hass.data[DOMAIN]["heweather_cert"] = cert
        _LOGGER.info("create heweather cert instance")

    session = async_get_clientsession(hass)
    auth_method = config_entry.data.get(CONF_AUTH_METHOD)
    host = config_entry.data.get(CONF_HOST)

    if auth_method == "key":
        api = QWeatherApiClient(
            session, host, key=config_entry.data.get(CONF_KEY)
        )
    else:
        api = QWeatherApiClient(
            session,
            host,
            heweather_cert=cert,
            jwt_sub=config_entry.data.get(CONF_JWT_SUB),
            jwt_kid=config_entry.data.get(CONF_JWT_KID),
        )

    weather_coord = WeatherUpdateCoordinator(hass, config_entry, api)
    indices_coord = IndicesUpdateCoordinator(hass, config_entry, api)
    minutely_coord = MinutelyUpdateCoordinator(hass, config_entry, api)

    await weather_coord.async_config_entry_first_refresh()
    await indices_coord.async_config_entry_first_refresh()
    # 分钟降水失败不阻断集成加载
    try:
        await minutely_coord.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("minutely first refresh failed: %s", err)

    hass.data[DOMAIN][config_entry.entry_id] = {
        RUNTIME_API: api,
        RUNTIME_WEATHER_COORD: weather_coord,
        RUNTIME_INDICES_COORD: indices_coord,
        RUNTIME_MINUTELY_COORD: minutely_coord,
    }

    await migrate_legacy_unique_ids(hass, config_entry)
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    await cleanup_duplicate_entities_on_startup(hass, config_entry)

    config_entry.async_on_unload(
        config_entry.add_update_listener(async_reload_entry)
    )
    return True


async def async_reload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id, None)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    # 仅当无其它条目时删除全局 JWT 密钥
    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != config_entry.entry_id
    ]
    if not remaining:
        heweather_cert: HeWeatherCert | None = hass.data.get(DOMAIN, {}).get(
            "heweather_cert"
        )
        if heweather_cert:
            await heweather_cert.del_key_async()
        hass.data.pop(DOMAIN, None)
    else:
        hass.data.get(DOMAIN, {}).pop(config_entry.entry_id, None)
    return True
