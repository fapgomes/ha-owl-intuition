"""Tests for the config and options flows."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.owl_intuition.const import (
    CONF_MULTICAST,
    CONF_POLL_INTERVAL,
    CONF_PUSH_HOST,
    CONF_PUSH_PORT,
    CONF_SW_VERSION,
    CONF_UDP_KEY,
    DOMAIN,
)
from custom_components.owl_intuition.protocol import OwlTimeoutError

from .conftest import HA_IP, HOST, KEY, MAC, setup_integration

USER_INPUT = {
    CONF_HOST: HOST,
    CONF_UDP_KEY: "70f87a4",
    CONF_PUSH_HOST: HA_IP,
    CONF_PUSH_PORT: 22600,
    CONF_MULTICAST: False,
}


@pytest.fixture
def flow_client(mock_client: AsyncMock):
    with (
        patch("custom_components.owl_intuition.config_flow.OwlClient", return_value=mock_client) as factory,
        patch("custom_components.owl_intuition.config_flow.async_get_source_ip", return_value=HA_IP),
        patch("custom_components.owl_intuition.async_setup_entry", return_value=True),
    ):
        yield factory


async def test_form_prefills_push_host_with_ha_ip(hass: HomeAssistant, flow_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    suggested = {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }
    assert suggested[CONF_PUSH_HOST] == HA_IP
    assert suggested[CONF_PUSH_PORT] == 22600
    assert suggested[CONF_MULTICAST] is False


async def test_happy_path_creates_entry_and_configures_push(
    hass: HomeAssistant, flow_client, mock_client: AsyncMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Network OWL {MAC}"
    assert result["data"] == {CONF_HOST: HOST, CONF_UDP_KEY: KEY, CONF_SW_VERSION: "NOWL 2.3 1234"}
    assert result["options"] == {
        CONF_PUSH_HOST: HA_IP,
        CONF_PUSH_PORT: 22600,
        CONF_MULTICAST: False,
        CONF_POLL_INTERVAL: 60,
    }
    assert result["result"].unique_id == MAC
    flow_client.assert_called_once_with(HOST, KEY)
    mock_client.set_udp_target.assert_awaited_once_with(HA_IP, 22600)
    mock_client.save.assert_awaited_once()


async def test_invalid_key_format(hass: HomeAssistant, flow_client) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_UDP_KEY: "12345"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_UDP_KEY: "invalid_key"}


async def test_no_response_shows_cannot_connect(
    hass: HomeAssistant, flow_client, mock_client: AsyncMock
) -> None:
    mock_client.get_mac.side_effect = OwlTimeoutError("silent")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_version_failure_is_tolerated(
    hass: HomeAssistant, flow_client, mock_client: AsyncMock
) -> None:
    mock_client.get_version.side_effect = OwlTimeoutError("silent")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SW_VERSION] is None


async def test_push_config_failure(hass: HomeAssistant, flow_client, mock_client: AsyncMock) -> None:
    mock_client.set_udp_target.side_effect = OwlTimeoutError("silent")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "push_config_failed"}


async def test_already_configured(
    hass: HomeAssistant, flow_client, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_reloads_and_reapplies_push(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock, socket_enabled: None
) -> None:
    await setup_integration(hass, mock_config_entry, mock_client)
    mock_client.set_udp_target.reset_mock()
    with patch("custom_components.owl_intuition.OwlClient", return_value=mock_client):
        result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_PUSH_HOST: "192.168.1.2", CONF_PUSH_PORT: 0, CONF_MULTICAST: True, CONF_POLL_INTERVAL: 120},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_PUSH_HOST] == "192.168.1.2"
    assert mock_config_entry.options[CONF_POLL_INTERVAL] == 120
    # OptionsFlowWithReload reloaded the entry, and setup re-sent SET,UDP with the new host
    assert mock_client.set_udp_target.await_args.args[0] == "192.168.1.2"
