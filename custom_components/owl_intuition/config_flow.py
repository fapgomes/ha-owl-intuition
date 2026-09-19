"""Config flow placeholder; implemented in a later task."""
from __future__ import annotations

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class OwlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Filled in later."""

    VERSION = 1
