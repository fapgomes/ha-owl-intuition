"""Tests for the UDP push listener."""
import asyncio
import socket

import pytest

from custom_components.owl_intuition.listener import OwlPushListener
from custom_components.owl_intuition.protocol import ElectricityReading

from .test_protocol import REAL_PACKET


@pytest.fixture(autouse=True)
def _sockets(socket_enabled: None) -> None:
    """These tests use real loopback UDP sockets."""


def _send(port: int, payload: str) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(payload.encode(), ("127.0.0.1", port))


async def _wait_for(condition, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


async def test_listener_delivers_parsed_readings() -> None:
    readings: list[ElectricityReading] = []
    listener = OwlPushListener(readings.append, port=0, bind_host="127.0.0.1")
    await listener.async_start()
    try:
        _send(listener.port, REAL_PACKET)
        await _wait_for(lambda: len(readings) == 1)
        assert readings[0].owl_id == "443719000677"
        assert readings[0].timestamp == 1789825304
    finally:
        await listener.async_stop()


async def test_listener_deduplicates_same_timestamp_and_ignores_junk() -> None:
    readings: list[ElectricityReading] = []
    listener = OwlPushListener(readings.append, port=0, bind_host="127.0.0.1")
    await listener.async_start()
    try:
        _send(listener.port, REAL_PACKET)
        _send(listener.port, REAL_PACKET)  # multicast + push duplicate
        _send(listener.port, "<weather id='x'><temperature>1</temperature></weather>")
        _send(listener.port, "not xml at all")
        _send(listener.port, REAL_PACKET.replace("1789825304", "1789825364"))
        await _wait_for(lambda: len(readings) == 2)
        await asyncio.sleep(0.05)
        assert [r.timestamp for r in readings] == [1789825304, 1789825364]
    finally:
        await listener.async_stop()


async def test_listener_port_conflict_raises_oserror() -> None:
    first = OwlPushListener(lambda r: None, port=0, bind_host="127.0.0.1")
    await first.async_start()
    second = OwlPushListener(lambda r: None, port=first.port, bind_host="127.0.0.1")
    try:
        try:
            await second.async_start()
        except OSError:
            pass
        else:
            raise AssertionError("expected OSError on port conflict")
    finally:
        await first.async_stop()
        await second.async_stop()


async def test_stop_is_idempotent() -> None:
    listener = OwlPushListener(lambda r: None, port=0, bind_host="127.0.0.1")
    await listener.async_stop()  # never started
    await listener.async_start()
    await listener.async_stop()
    await listener.async_stop()
