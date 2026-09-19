"""Diagnostics must never leak the UDP key."""
import json
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.json import json_dumps
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.owl_intuition.diagnostics import async_get_config_entry_diagnostics

from .conftest import KEY, setup_integration
from .test_coordinator import make_reading


@pytest.fixture(autouse=True)
def _sockets(socket_enabled: None) -> None:
    """The real listener binds a loopback UDP port."""


async def test_diagnostics_redact_key_and_serialize(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    mock_config_entry.runtime_data.coordinator.handle_reading(make_reading(1789825304))
    await hass.async_block_till_done()
    result = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    dumped = json_dumps(result)
    assert KEY not in dumped
    assert result["entry"]["data"]["udp_key"] == "**REDACTED**"
    parsed = json.loads(dumped)
    assert parsed["data"]["reading"]["owl_id"] == "443719000677"
    assert parsed["data"]["device"]["rssi"] == -51
    assert parsed["listener_port"] > 0
    assert parsed["connected"] is True
