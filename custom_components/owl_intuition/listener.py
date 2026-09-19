"""UDP server that receives Network OWL push (and optionally multicast) packets."""
from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable
from datetime import datetime, timezone

from .protocol import (
    DEFAULT_PUSH_PORT,
    MULTICAST_GROUP,
    ElectricityReading,
    OwlProtocolError,
    parse_electricity,
)

_LOGGER = logging.getLogger(__name__)


class _PushProtocol(asyncio.DatagramProtocol):
    def __init__(self, handler: Callable[[bytes, tuple[str, int]], None]) -> None:
        self._handler = handler

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._handler(data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.debug("push socket error: %s", exc)


class OwlPushListener:
    """Bind the push port and deliver parsed electricity readings."""

    def __init__(
        self,
        on_reading: Callable[[ElectricityReading], None],
        *,
        port: int = DEFAULT_PUSH_PORT,
        bind_host: str = "0.0.0.0",
        multicast: bool = False,
    ) -> None:
        self._on_reading = on_reading
        self._port = port
        self._bind_host = bind_host
        self._multicast = multicast
        self._transport: asyncio.DatagramTransport | None = None
        self._last_key: tuple[str, int] | None = None

    @property
    def port(self) -> int:
        if self._transport is None:
            return self._port
        return self._transport.get_extra_info("sockname")[1]

    async def async_start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _PushProtocol(self._handle),
            local_addr=(self._bind_host, self._port),
        )
        if self._multicast:
            sock: socket.socket = self._transport.get_extra_info("socket")
            membership = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        _LOGGER.debug(
            "listening for OWL push on %s:%s (multicast=%s)",
            self._bind_host,
            self.port,
            self._multicast,
        )

    async def async_stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def _handle(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            reading = parse_electricity(data, received_at=datetime.now(timezone.utc))
        except OwlProtocolError as err:
            _LOGGER.debug("ignoring packet from %s: %s", addr[0], err)
            return
        if reading is None:
            return
        key = (reading.owl_id, reading.timestamp)
        if key == self._last_key:
            return
        self._last_key = key
        self._on_reading(reading)
