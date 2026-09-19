"""Sensors for OWL Intuition."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import OwlConfigEntry
from .coordinator import OwlCoordinator, OwlData
from .entity import OwlPollEntity, OwlPushEntity


@dataclass(frozen=True, kw_only=True)
class OwlSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OwlData], StateType | datetime]
    push: bool


def _channel_power(index: int) -> Callable[[OwlData], StateType]:
    def value(data: OwlData) -> StateType:
        if data.reading is None or index >= len(data.reading.channels):
            return None
        return data.reading.channels[index].power_w

    return value


def _channel_energy_kwh(index: int) -> Callable[[OwlData], StateType]:
    def value(data: OwlData) -> StateType:
        if data.reading is None or index >= len(data.reading.channels):
            return None
        return data.reading.channels[index].energy_day_wh / 1000

    return value


PUSH_SENSORS: tuple[OwlSensorDescription, ...] = tuple(
    [
        *(
            OwlSensorDescription(
                key=f"power_{n}",
                push=True,
                device_class=SensorDeviceClass.POWER,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfPower.WATT,
                suggested_display_precision=0,
                value_fn=_channel_power(n - 1),
            )
            for n in (1, 2, 3)
        ),
        OwlSensorDescription(
            key="power_total",
            push=True,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.WATT,
            suggested_display_precision=0,
            value_fn=lambda d: d.reading.total_power_w if d.reading else None,
        ),
        *(
            OwlSensorDescription(
                key=f"energy_day_{n}",
                push=True,
                device_class=SensorDeviceClass.ENERGY,
                state_class=SensorStateClass.TOTAL_INCREASING,
                native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                suggested_display_precision=3,
                value_fn=_channel_energy_kwh(n - 1),
            )
            for n in (1, 2, 3)
        ),
        OwlSensorDescription(
            key="energy_day_total",
            push=True,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=3,
            value_fn=lambda d: d.reading.total_energy_day_wh / 1000 if d.reading else None,
        ),
        OwlSensorDescription(
            key="battery",
            push=True,
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: d.reading.battery_pct if d.reading else None,
        ),
        OwlSensorDescription(
            key="rssi",
            push=True,
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: d.reading.rssi if d.reading else None,
        ),
        OwlSensorDescription(
            key="lqi",
            push=True,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda d: d.reading.lqi if d.reading else None,
        ),
    ]
)

POLL_SENSORS: tuple[OwlSensorDescription, ...] = (
    OwlSensorDescription(
        key="last_seen",
        push=False,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.transmitter_last_seen,
    ),
    OwlSensorDescription(
        key="uptime",
        push=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.uptime,
    ),
    OwlSensorDescription(
        key="clock_offset",
        push=False,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.clock_offset_s,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: OwlConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [OwlPushSensor(coordinator, description) for description in PUSH_SENSORS]
        + [OwlPollSensor(coordinator, description) for description in POLL_SENSORS]
    )


class OwlPushSensor(OwlPushEntity, SensorEntity):
    entity_description: OwlSensorDescription

    def __init__(self, coordinator: OwlCoordinator, description: OwlSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)


class OwlPollSensor(OwlPollEntity, SensorEntity):
    entity_description: OwlSensorDescription

    def __init__(self, coordinator: OwlCoordinator, description: OwlSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
