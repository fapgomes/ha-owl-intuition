"""Config and options flows for OWL Intuition."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.network import async_get_source_ip
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback

from .const import (
    CONF_MULTICAST,
    CONF_POLL_INTERVAL,
    CONF_PUSH_HOST,
    CONF_PUSH_PORT,
    CONF_SW_VERSION,
    CONF_UDP_KEY,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)
from .protocol import DEFAULT_PUSH_PORT, OwlClient, OwlError, normalize_key

_LOGGER = logging.getLogger(__name__)

PORT = vol.All(vol.Coerce(int), vol.Range(min=0, max=65535))

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_UDP_KEY): str,
        vol.Required(CONF_PUSH_HOST): str,
        vol.Required(CONF_PUSH_PORT, default=DEFAULT_PUSH_PORT): PORT,
        vol.Required(CONF_MULTICAST, default=False): bool,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PUSH_HOST): str,
        vol.Required(CONF_PUSH_PORT, default=DEFAULT_PUSH_PORT): PORT,
        vol.Required(CONF_MULTICAST, default=False): bool,
        vol.Required(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)
        ),
    }
)


class OwlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for host + key, validate with GET,MAC, configure push."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OwlOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                key = normalize_key(user_input[CONF_UDP_KEY])
            except ValueError:
                errors[CONF_UDP_KEY] = "invalid_key"
            else:
                client = OwlClient(user_input[CONF_HOST], key)
                try:
                    mac = await client.get_mac()
                except OwlError as err:
                    _LOGGER.debug("validation failed: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(mac)
                    self._abort_if_unique_id_configured()
                    try:
                        sw_version: str | None = await client.get_version()
                    except OwlError:
                        sw_version = None
                    try:
                        await client.set_udp_target(
                            user_input[CONF_PUSH_HOST], user_input[CONF_PUSH_PORT]
                        )
                        await client.save()
                    except OwlError as err:
                        _LOGGER.debug("push configuration failed: %s", err)
                        errors["base"] = "push_config_failed"
                    else:
                        return self.async_create_entry(
                            title=f"Network OWL {mac}",
                            data={
                                CONF_HOST: user_input[CONF_HOST],
                                CONF_UDP_KEY: key,
                                CONF_SW_VERSION: sw_version,
                            },
                            options={
                                CONF_PUSH_HOST: user_input[CONF_PUSH_HOST],
                                CONF_PUSH_PORT: user_input[CONF_PUSH_PORT],
                                CONF_MULTICAST: user_input[CONF_MULTICAST],
                                CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                            },
                        )

        suggested: dict[str, Any] = {
            CONF_PUSH_PORT: DEFAULT_PUSH_PORT,
            CONF_MULTICAST: False,
            CONF_PUSH_HOST: await self._async_default_push_host(user_input),
        }
        if user_input is not None:
            suggested.update(user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, suggested),
            errors=errors,
        )

    async def _async_default_push_host(self, user_input: dict[str, Any] | None) -> str:
        target = user_input.get(CONF_HOST) if user_input else None
        try:
            if target:
                source = await async_get_source_ip(self.hass, target_ip=target)
            else:
                source = await async_get_source_ip(self.hass)
        except Exception:  # noqa: BLE001 - best effort default only
            source = None
        return source or ""


class OwlOptionsFlow(OptionsFlowWithReload):
    """Push destination, multicast and polling interval; reloads the entry on save."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, dict(self.config_entry.options)
            ),
        )
