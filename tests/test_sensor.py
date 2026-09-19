"""Sensor platform tests."""
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.owl_intuition.const import DOMAIN

from .conftest import MAC, setup_integration
from .test_coordinator import make_reading


@pytest.fixture(autouse=True)
def _sockets(socket_enabled: None) -> None:
    """The real listener binds a loopback UDP port."""


async def test_push_sensors_unavailable_until_first_reading(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    assert hass.states.get("sensor.network_owl_power_phase_1").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.network_owl_energy_today_total").state == STATE_UNAVAILABLE
    # poll-based diagnostics are available right after setup
    assert hass.states.get("sensor.network_owl_uptime").state == "3 Mins 2 Secs"


async def test_push_sensor_values_units_and_classes(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    mock_config_entry.runtime_data.coordinator.handle_reading(make_reading(1789825304, power=250.5))
    await hass.async_block_till_done()

    power = hass.states.get("sensor.network_owl_power_phase_1")
    assert power.state == "250.5"
    assert power.attributes["unit_of_measurement"] == "W"
    assert power.attributes["device_class"] == "power"
    assert power.attributes["state_class"] == "measurement"

    total = hass.states.get("sensor.network_owl_power_total")
    assert total.state == "250.5"

    energy = hass.states.get("sensor.network_owl_energy_today_phase_1")
    assert energy.state == "1.0"  # 1000 Wh -> kWh
    assert energy.attributes["unit_of_measurement"] == "kWh"
    assert energy.attributes["device_class"] == "energy"
    assert energy.attributes["state_class"] == "total_increasing"

    assert hass.states.get("sensor.network_owl_energy_today_total").state == "1.0"
    assert hass.states.get("sensor.network_owl_transmitter_battery").state == "100"
    assert hass.states.get("sensor.network_owl_signal_strength").state == "-50"
    assert hass.states.get("sensor.network_owl_link_quality").state == "10"


async def test_poll_sensors(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    last_seen = hass.states.get("sensor.network_owl_transmitter_last_seen")
    assert last_seen.attributes["device_class"] == "timestamp"
    assert last_seen.state != STATE_UNAVAILABLE
    offset = hass.states.get("sensor.network_owl_clock_offset")
    assert offset.attributes["unit_of_measurement"] == "s"
    assert offset.attributes["device_class"] == "duration"


async def test_diagnostic_sensors_have_diagnostic_category_and_device(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("sensor.network_owl_signal_strength")
    assert entry.entity_category == "diagnostic"
    assert entry.unique_id == f"{MAC}_rssi"
    device = dr.async_get(hass).async_get(entry.device_id)
    assert (DOMAIN, MAC) in device.identifiers
    assert (dr.CONNECTION_NETWORK_MAC, MAC) in device.connections
    assert device.manufacturer == "OWL / 2 Save Energy"
    assert device.sw_version == "NOWL 2.3 1234"


async def test_push_sensors_go_unavailable_after_5_minutes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    mock_config_entry.runtime_data.coordinator.handle_reading(make_reading(1789825304))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.network_owl_power_total").state == "100.0"
    freezer.tick(timedelta(minutes=5, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.network_owl_power_total").state == STATE_UNAVAILABLE
