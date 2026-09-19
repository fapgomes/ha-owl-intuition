"""Shared fixtures."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

KEY = "70F87A4"

DEFAULT_RESPONSES = {
    "GET,MAC": "OK,MAC,443719000677",
    "GET,VERSION": "OK,VERSION,NOWL,2.3,1234",
    "GET,DEVICE,ALL": "OK,DEVICE,CMR180,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE",
    "GET,DEVICE,0": "OK,DEVICE,0,2FC,CMR180,28,0,-51,1,1,3,0,0.0:0,0.00,0,0,0,0.00",
    "GET,UDP": "OK,UDP,,192.168.1.100,22600",
    "SET,UDP,,192.168.1.100,22600": "OK,UDP,,192.168.1.100,22600",
    "SAVE": "OK,SAVE,",
    "GET,ELECTRICITY": "OK,ELECTRICITY,1,7,230,1.00",
    "SET,ELECTRICITY,1,7,240,0.95": "OK,ELECTRICITY,1,7,240,0.95",
    "GET,CLOCK": "OK,CLOCK,1789825772,1789829372",
    "SET,CLOCK,1789825772": "OK,CLOCK,1789825772,1789829372",
    "SET,TZ,0": "OK,TZ,0",
    "SET,DST,1": "OK,DST,1,1774746000,1792890000",
    "GET,UPTIME": "OK,UPTIME,3 Mins 2 Secs",
    "SCAN,180": "OK,SCAN",
}


class FakeOwl(asyncio.DatagramProtocol):
    """A UDP server that behaves like a Network OWL command port."""

    def __init__(self, key: str, responses: dict[str, str]) -> None:
        self.key = key
        self.responses = dict(responses)
        self.received: list[str] = []
        self.host = "127.0.0.1"
        self.port = 0
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        self.port = transport.get_extra_info("sockname")[1]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        text = data.decode()
        self.received.append(text)
        command, _, key = text.rpartition(",")
        if key != self.key:
            return  # the real device stays silent on a bad key
        response = self.responses.get(command)
        if response is not None and self.transport is not None:
            self.transport.sendto(response.encode(), addr)


@pytest.fixture
async def fake_owl(socket_enabled: None) -> AsyncIterator[FakeOwl]:
    """Real loopback UDP server; the HA plugin blocks sockets unless asked."""
    loop = asyncio.get_running_loop()
    server = FakeOwl(KEY, DEFAULT_RESPONSES)
    transport, _ = await loop.create_datagram_endpoint(
        lambda: server, local_addr=("127.0.0.1", 0)
    )
    try:
        yield server
    finally:
        transport.close()


import time  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from homeassistant.const import CONF_HOST  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.owl_intuition.const import (  # noqa: E402
    CONF_MULTICAST,
    CONF_POLL_INTERVAL,
    CONF_PUSH_HOST,
    CONF_PUSH_PORT,
    CONF_SW_VERSION,
    CONF_UDP_KEY,
    DOMAIN,
)
from custom_components.owl_intuition.protocol import (  # noqa: E402
    DeviceStatus,
    ElectricityConfig,
    OwlClient,
)

MAC = "44:37:19:00:06:77"
HOST = "192.168.1.38"
HA_IP = "192.168.1.100"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA load custom_components from this repo."""


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock(spec=OwlClient)
    client.host = HOST
    client.get_mac.return_value = MAC
    client.get_version.return_value = "NOWL 2.3 1234"
    client.get_device.return_value = DeviceStatus(0, "2FC", "CMR180", 28, 0, -51, 1, "1", 3, 0)
    client.get_electricity_config.return_value = ElectricityConfig(1, 7, 230.0, 1.0)
    client.set_electricity_config.side_effect = lambda cfg: cfg
    # clock in sync with "now" so setup never triggers a drift sync in tests
    client.get_clock.side_effect = lambda: (int(time.time()), int(time.time()) + 3600)
    client.set_clock.return_value = (1789825772, 1789829372)
    client.get_uptime.return_value = "3 Mins 2 Secs"
    return client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"Network OWL {MAC}",
        unique_id=MAC,
        data={CONF_HOST: HOST, CONF_UDP_KEY: KEY, CONF_SW_VERSION: "NOWL 2.3 1234"},
        options={
            CONF_PUSH_HOST: HA_IP,
            CONF_PUSH_PORT: 0,  # 0 = let the OS choose, so tests never collide
            CONF_MULTICAST: False,
            CONF_POLL_INTERVAL: 60,
        },
    )


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry, client: AsyncMock) -> None:
    entry.add_to_hass(hass)
    with patch("custom_components.owl_intuition.OwlClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
