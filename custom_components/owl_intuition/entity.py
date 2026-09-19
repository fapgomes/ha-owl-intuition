"""Base entities."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import OwlCoordinator


class OwlEntity(CoordinatorEntity[OwlCoordinator]):
    """Common device info and naming."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OwlCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.mac}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.mac)},
            connections={(CONNECTION_NETWORK_MAC, coordinator.mac)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=MODEL,
            sw_version=coordinator.sw_version,
        )


class OwlPushEntity(OwlEntity):
    """Entities fed by push packets: available while packets keep coming."""

    @property
    def available(self) -> bool:
        return self.coordinator.connected


class OwlPollEntity(OwlEntity):
    """Entities fed by polling: available while polling succeeds."""

    @property
    def available(self) -> bool:
        return super().available
