"""Constants for the OWL Intuition integration."""
from homeassistant.const import Platform

DOMAIN = "owl_intuition"

CONF_UDP_KEY = "udp_key"
CONF_SW_VERSION = "sw_version"
CONF_PUSH_HOST = "push_host"
CONF_PUSH_PORT = "push_port"
CONF_MULTICAST = "multicast"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_POLL_INTERVAL = 60
MIN_POLL_INTERVAL = 30
MAX_POLL_INTERVAL = 600

MANUFACTURER = "OWL / 2 Save Energy"
MODEL = "Network OWL"

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.NUMBER, Platform.SENSOR]
