"""Tests for entry setup and unload."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.owl_intuition.protocol import OwlTimeoutError

from .conftest import HA_IP, setup_integration


@pytest.fixture(autouse=True)
def _sockets(socket_enabled: None) -> None:
    """The real listener binds a loopback UDP port."""


async def test_setup_starts_listener_and_configures_push(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    runtime = mock_config_entry.runtime_data
    assert runtime.listener.port > 0
    mock_client.set_udp_target.assert_awaited_once_with(HA_IP, runtime.listener.port)
    mock_client.save.assert_awaited()
    assert runtime.coordinator.mac == "44:37:19:00:06:77"
    assert runtime.coordinator.data.device.rssi == -51
    assert runtime.coordinator.data.uptime == "3 Mins 2 Secs"


async def test_unload_stops_listener(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    listener = mock_config_entry.runtime_data.listener
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert listener._transport is None


async def test_setup_retries_when_push_config_fails(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.set_udp_target.side_effect = OwlTimeoutError("silent")
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.owl_intuition.OwlClient", return_value=mock_client):
        assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_retries_when_port_is_taken(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    with patch(
        "custom_components.owl_intuition.OwlPushListener.async_start",
        side_effect=OSError(98, "Address already in use"),
    ):
        mock_config_entry.add_to_hass(hass)
        with patch("custom_components.owl_intuition.OwlClient", return_value=mock_client):
            assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_first_poll_failure_does_not_block_setup(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    mock_client.get_device.side_effect = OwlTimeoutError("silent")
    await setup_integration(hass, mock_config_entry, mock_client)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.coordinator.data.device is None
