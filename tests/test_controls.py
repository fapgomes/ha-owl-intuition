"""binary_sensor, number and button tests."""
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.owl_intuition.protocol import ElectricityConfig, OwlTimeoutError

from .conftest import setup_integration
from .test_coordinator import make_reading


@pytest.fixture(autouse=True)
def _sockets(socket_enabled: None) -> None:
    """The real listener binds a loopback UDP port."""


async def test_connectivity_follows_push(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    state = hass.states.get("binary_sensor.network_owl_connectivity")
    assert state.state == STATE_OFF
    assert state.attributes["device_class"] == "connectivity"
    mock_config_entry.runtime_data.coordinator.handle_reading(make_reading(1789825304))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.network_owl_connectivity").state == STATE_ON


async def test_number_values_and_set_voltage_preserves_mode_and_flags(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    voltage = hass.states.get("number.network_owl_voltage")
    assert voltage.state == "230.0"
    assert voltage.attributes["min"] == 200
    assert voltage.attributes["max"] == 250
    assert voltage.attributes["unit_of_measurement"] == "V"
    assert hass.states.get("number.network_owl_power_factor").state == "1.0"

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.network_owl_voltage", ATTR_VALUE: 240},
        blocking=True,
    )
    mock_client.set_electricity_config.assert_awaited_once_with(ElectricityConfig(1, 7, 240.0, 1.0))

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.network_owl_power_factor", ATTR_VALUE: 0.95},
        blocking=True,
    )
    assert mock_client.set_electricity_config.await_args.args[0] == ElectricityConfig(1, 7, 230.0, 0.95)


async def test_number_failure_raises_homeassistant_error(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    mock_client.set_electricity_config.side_effect = OwlTimeoutError("silent")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: "number.network_owl_voltage", ATTR_VALUE: 240},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("entity_id", "method", "args"),
    [
        ("button.network_owl_pair_transmitter", "scan", (180,)),
        ("button.network_owl_reboot", "reboot", ()),
    ],
)
async def test_buttons_send_commands(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    entity_id: str,
    method: str,
    args: tuple,
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    getattr(mock_client, method).assert_awaited_once_with(*args)


async def test_sync_clock_button(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    mock_client.set_clock.reset_mock()
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: "button.network_owl_sync_clock"}, blocking=True
    )
    mock_client.set_clock.assert_awaited_once()


async def test_button_failure_raises_homeassistant_error(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    mock_client.scan.side_effect = OwlTimeoutError("silent")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.network_owl_pair_transmitter"},
            blocking=True,
        )
