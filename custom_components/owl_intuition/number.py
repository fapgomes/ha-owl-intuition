"""Voltage and power factor configuration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OwlConfigEntry
from .const import DOMAIN
from .coordinator import OwlCoordinator
from .entity import OwlPollEntity
from .protocol import ElectricityConfig, OwlError


@dataclass(frozen=True, kw_only=True)
class OwlNumberDescription(NumberEntityDescription):
    value_fn: Callable[[ElectricityConfig], float]
    apply_fn: Callable[[ElectricityConfig, float], ElectricityConfig]


NUMBERS: tuple[OwlNumberDescription, ...] = (
    OwlNumberDescription(
        key="voltage",
        device_class=NumberDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=200,
        native_max_value=250,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda cfg: cfg.voltage,
        apply_fn=lambda cfg, value: replace(cfg, voltage=float(value)),
    ),
    OwlNumberDescription(
        key="power_factor",
        device_class=NumberDeviceClass.POWER_FACTOR,
        native_min_value=0.5,
        native_max_value=1.0,
        native_step=0.01,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda cfg: cfg.power_factor,
        apply_fn=lambda cfg, value: replace(cfg, power_factor=round(float(value), 2)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: OwlConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(OwlNumber(coordinator, description) for description in NUMBERS)


class OwlNumber(OwlPollEntity, NumberEntity):
    entity_description: OwlNumberDescription

    def __init__(self, coordinator: OwlCoordinator, description: OwlNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.electricity is not None

    @property
    def native_value(self) -> float | None:
        cfg = self.coordinator.data.electricity
        return None if cfg is None else self.entity_description.value_fn(cfg)

    async def async_set_native_value(self, value: float) -> None:
        current = self.coordinator.data.electricity
        if current is None:
            raise HomeAssistantError("Electricity configuration not loaded yet")
        try:
            await self.coordinator.client.set_electricity_config(
                self.entity_description.apply_fn(current, value)
            )
            await self.coordinator.client.save()
        except OwlError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
