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
