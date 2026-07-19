"""诊断信息（脱敏）。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .heweather.const import (
    CONF_KEY,
    DOMAIN,
    RUNTIME_INDICES_COORD,
    RUNTIME_MINUTELY_COORD,
    RUNTIME_WEATHER_COORD,
)

TO_REDACT = {CONF_KEY, "auth_jwt_sub", "auth_jwt_kid", "key", "token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    weather = runtime.get(RUNTIME_WEATHER_COORD)
    indices = runtime.get(RUNTIME_INDICES_COORD)
    minutely = runtime.get(RUNTIME_MINUTELY_COORD)

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "coordinators": {
            "weather": {
                "last_update_success": getattr(weather, "last_update_success", None),
                "update_interval": str(getattr(weather, "update_interval", None)),
                "has_data": bool(getattr(weather, "data", None)),
            },
            "indices": {
                "last_update_success": getattr(indices, "last_update_success", None),
                "update_interval": str(getattr(indices, "update_interval", None)),
                "has_data": bool(getattr(indices, "data", None)),
            },
            "minutely": {
                "last_update_success": getattr(minutely, "last_update_success", None),
                "update_interval": str(getattr(minutely, "update_interval", None)),
                "has_data": bool(getattr(minutely, "data", None)),
                "available": (getattr(minutely, "data", None) or {}).get("available"),
            },
        },
    }
