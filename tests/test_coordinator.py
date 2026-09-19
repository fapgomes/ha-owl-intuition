"""Behavioural tests for OwlCoordinator."""
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.owl_intuition.const import DOMAIN
from custom_components.owl_intuition.coordinator import ISSUE_CLOCK_NOT_SYNCED, ISSUE_NO_DATA
from custom_components.owl_intuition.protocol import (
    ChannelReading,
    ElectricityReading,
    OwlTimeoutError,
)

from .conftest import MAC, setup_integration


@pytest.fixture(autouse=True)
def _sockets(socket_enabled: None) -> None:
    """The real listener binds a loopback UDP port."""


def make_reading(timestamp: int, power: float = 100.0) -> ElectricityReading:
    return ElectricityReading(
        owl_id="443719000677",
        timestamp=timestamp,
        rssi=-50,
        lqi=10,
        battery_pct=100,
        channels=(
            ChannelReading(0, power, 1000.0),
            ChannelReading(1, 0.0, 0.0),
            ChannelReading(2, 0.0, 0.0),
        ),
        received_at=dt_util.utcnow(),
    )


async def test_push_updates_data_and_connectivity(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    coordinator = mock_config_entry.runtime_data.coordinator
    assert coordinator.connected is False
    coordinator.handle_reading(make_reading(1789825304))
    await hass.async_block_till_done()
    assert coordinator.data.reading.total_power_w == 100.0
    assert coordinator.connected is True


async def test_packet_from_other_owl_is_ignored(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    coordinator = mock_config_entry.runtime_data.coordinator
    other = make_reading(1789825304)
    coordinator.handle_reading(
        ElectricityReading(**{**other.__dict__, "owl_id": "443719999999"})
    )
    await hass.async_block_till_done()
    assert coordinator.data.reading is None


async def test_reboot_triggers_clock_sync_once_per_10_minutes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    coordinator = mock_config_entry.runtime_data.coordinator
    mock_client.set_clock.reset_mock()
    coordinator.handle_reading(make_reading(195))  # seconds since boot => rebooted
    await hass.async_block_till_done()
    mock_client.set_timezone.assert_awaited()
    mock_client.set_dst.assert_awaited()
    assert mock_client.set_clock.await_count == 1
    mock_client.save.assert_awaited()

    coordinator.handle_reading(make_reading(255))
    await hass.async_block_till_done()
    assert mock_client.set_clock.await_count == 1  # rate limited

    freezer.tick(timedelta(minutes=11))
    coordinator.handle_reading(make_reading(100))  # timestamp went backwards => reboot
    await hass.async_block_till_done()
    assert mock_client.set_clock.await_count == 2


async def test_clock_sync_failure_creates_repair_issue(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    coordinator = mock_config_entry.runtime_data.coordinator
    mock_client.set_timezone.side_effect = OwlTimeoutError("silent")
    coordinator.handle_reading(make_reading(195))
    await hass.async_block_till_done()
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"{ISSUE_CLOCK_NOT_SYNCED}_{MAC}") is not None

    mock_client.set_timezone.side_effect = None
    await coordinator.async_sync_clock()
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, f"{ISSUE_CLOCK_NOT_SYNCED}_{MAC}") is None


async def test_no_data_for_5_minutes_marks_offline_and_raises_issue(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.handle_reading(make_reading(1789825304))
    await hass.async_block_till_done()
    assert coordinator.connected is True

    freezer.tick(timedelta(minutes=5, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.connected is False
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"{ISSUE_NO_DATA}_{MAC}") is not None

    coordinator.handle_reading(make_reading(1789825604))
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, f"{ISSUE_NO_DATA}_{MAC}") is None


async def test_poll_marks_unavailable_only_after_three_failures(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.async_add_listener(lambda: None)  # polling only runs with a listener (an entity)
    mock_client.get_device.side_effect = OwlTimeoutError("silent")
    for expected in (True, True, False):
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert coordinator.last_update_success is expected


async def test_clock_drift_triggers_sync_on_poll(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    mock_config_entry.runtime_data.coordinator.async_add_listener(lambda: None)
    mock_client.set_clock.reset_mock()
    mock_client.get_clock.side_effect = None
    mock_client.get_clock.return_value = (int(dt_util.utcnow().timestamp()) - 3600, 0)
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.set_clock.await_count == 1
