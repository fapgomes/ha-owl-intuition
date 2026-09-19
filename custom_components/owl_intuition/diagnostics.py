"""Diagnostics support."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import OwlConfigEntry
from .const import CONF_UDP_KEY

TO_REDACT = {CONF_UDP_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OwlConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "listener_port": runtime.listener.port,
        "connected": coordinator.connected,
        "last_update_success": coordinator.last_update_success,
        "data": asdict(coordinator.data),
    }
