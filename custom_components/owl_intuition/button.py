"""Pair, sync clock and reboot buttons."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OwlConfigEntry
from .const import DOMAIN
from .coordinator import OwlCoordinator
from .entity import OwlEntity
from .protocol import OwlError


@dataclass(frozen=True, kw_only=True)
class OwlButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[OwlCoordinator], Awaitable[None]]


BUTTONS: tuple[OwlButtonDescription, ...] = (
    OwlButtonDescription(
        key="pair",
        press_fn=lambda c: c.client.scan(180),
    ),
    OwlButtonDescription(
        key="sync_clock",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.async_sync_clock(),
    ),
    OwlButtonDescription(
        key="reboot",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.client.reboot(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: OwlConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(OwlButton(coordinator, description) for description in BUTTONS)


class OwlButton(OwlEntity, ButtonEntity):
    entity_description: OwlButtonDescription

    def __init__(self, coordinator: OwlCoordinator, description: OwlButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return True  # commands are useful precisely when things look broken

    async def async_press(self) -> None:
        try:
            await self.entity_description.press_fn(self.coordinator)
        except OwlError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
