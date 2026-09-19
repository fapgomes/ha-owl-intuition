"""OWL Intuition: local-only integration for the Network OWL energy monitor."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_MULTICAST,
    CONF_POLL_INTERVAL,
    CONF_PUSH_HOST,
    CONF_PUSH_PORT,
    CONF_UDP_KEY,
    DEFAULT_POLL_INTERVAL,
    PLATFORMS,
)
from .coordinator import OwlCoordinator
from .listener import OwlPushListener
from .protocol import DEFAULT_PUSH_PORT, OwlClient, OwlError


@dataclass
class OwlOptions:
    push_host: str
    push_port: int
    multicast: bool
    poll_interval: int


@dataclass
class OwlRuntimeData:
    client: OwlClient
    listener: OwlPushListener
    coordinator: OwlCoordinator


type OwlConfigEntry = ConfigEntry[OwlRuntimeData]


def get_options(entry: ConfigEntry) -> OwlOptions:
    return OwlOptions(
        push_host=entry.options[CONF_PUSH_HOST],
        push_port=int(entry.options.get(CONF_PUSH_PORT, DEFAULT_PUSH_PORT)),
        multicast=bool(entry.options.get(CONF_MULTICAST, False)),
        poll_interval=int(entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)),
    )


async def async_setup_entry(hass: HomeAssistant, entry: OwlConfigEntry) -> bool:
    options = get_options(entry)
    client = OwlClient(entry.data[CONF_HOST], entry.data[CONF_UDP_KEY])
    coordinator = OwlCoordinator(hass, entry, client)
    listener = OwlPushListener(
        coordinator.handle_reading, port=options.push_port, multicast=options.multicast
    )
    try:
        await listener.async_start()
    except OSError as err:
        raise ConfigEntryNotReady(f"Cannot bind UDP port {options.push_port}: {err}") from err
    try:
        await client.set_udp_target(options.push_host, listener.port)
        await client.save()
    except OwlError as err:
        await listener.async_stop()
        raise ConfigEntryNotReady(
            f"Network OWL did not accept push configuration: {err}"
        ) from err

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = OwlRuntimeData(client=client, listener=listener, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OwlConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.listener.async_stop()
        await entry.runtime_data.coordinator.async_shutdown()
    return unloaded
