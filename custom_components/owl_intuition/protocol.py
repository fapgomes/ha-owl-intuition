"""Pure-Python protocol layer for the OWL Intuition Network OWL.

This module must not import anything from Home Assistant so it can be
unit-tested on its own and reused outside the integration.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from xml.etree import ElementTree

COMMAND_PORT = 5100
DEFAULT_PUSH_PORT = 22600
MULTICAST_GROUP = "224.192.32.19"

_KEY_RE = re.compile(r"^[0-9A-F]{7,8}$")


class OwlError(Exception):
    """Base error for the OWL protocol layer."""


class OwlTimeoutError(OwlError):
    """The device did not answer (wrong key, wrong host, or offline)."""


class OwlProtocolError(OwlError):
    """The device answered something we could not parse."""


def normalize_key(key: str) -> str:
    """Return the UDP key as the device expects it: 7-8 upper-case hex chars."""
    candidate = key.strip().upper()
    if not _KEY_RE.match(candidate):
        raise ValueError("UDP key must be 7 or 8 hexadecimal characters")
    return candidate


def normalize_mac(raw: str) -> str:
    """Return a MAC as lower-case colon-separated hex (44:37:19:00:06:77)."""
    digits = re.sub(r"[^0-9a-fA-F]", "", raw).lower()
    if len(digits) != 12:
        raise ValueError(f"invalid MAC address: {raw!r}")
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


@dataclass(frozen=True)
class ChannelReading:
    """One clamp channel of the transmitter."""

    channel: int
    power_w: float
    energy_day_wh: float


@dataclass(frozen=True)
class ElectricityReading:
    """One <electricity> push packet."""

    owl_id: str
    timestamp: int
    rssi: int
    lqi: int
    battery_pct: int | None
    channels: tuple[ChannelReading, ...]
    received_at: datetime

    @property
    def total_power_w(self) -> float:
        return sum(channel.power_w for channel in self.channels)

    @property
    def total_energy_day_wh(self) -> float:
        return sum(channel.energy_day_wh for channel in self.channels)


def _text(element: ElementTree.Element | None, default: str = "0") -> str:
    if element is None or element.text is None:
        return default
    return element.text.strip()


def parse_electricity(
    payload: bytes | str, received_at: datetime | None = None
) -> ElectricityReading | None:
    """Parse a push packet. Returns None for non-electricity packets."""
    text = payload.decode(errors="replace") if isinstance(payload, bytes) else payload
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as err:
        raise OwlProtocolError(f"malformed XML: {err}") from err
    if root.tag != "electricity":
        return None
    try:
        signal = root.find("signal")
        battery = root.find("battery")
        battery_pct: int | None = None
        if battery is not None and battery.get("level"):
            battery_pct = int(battery.get("level", "").rstrip("%"))
        channels = tuple(
            ChannelReading(
                channel=int(chan.get("id", "0")),
                power_w=float(_text(chan.find("curr"))),
                energy_day_wh=float(_text(chan.find("day"))),
            )
            for chan in root.iter("chan")
        )
        return ElectricityReading(
            owl_id=root.get("id", ""),
            timestamp=int(_text(root.find("timestamp"))),
            rssi=int(signal.get("rssi", "0")) if signal is not None else 0,
            lqi=int(signal.get("lqi", "0")) if signal is not None else 0,
            battery_pct=battery_pct,
            channels=channels,
            received_at=received_at or datetime.now(timezone.utc),
        )
    except (TypeError, ValueError) as err:
        raise OwlProtocolError(f"unexpected value in packet: {err}") from err


@dataclass(frozen=True)
class DeviceStatus:
    """Answer to GET,DEVICE,(index)."""

    index: int
    address: str
    device_type: str
    seconds_since_rx: int
    state: int
    rssi: int
    lqi: int
    battery: str
    rx_packets: int
    tx_packets: int


@dataclass(frozen=True)
class ElectricityConfig:
    """Answer to GET,ELECTRICITY: mode 0=single phase, 1=three phase, 2=PV."""

    mode: int
    flags: int
    voltage: float
    power_factor: float


def _fields(raw: str, command: str, minimum: int) -> list[str]:
    parts = raw.strip().split(",")
    if len(parts) < 2 or parts[0] != "OK" or parts[1] != command:
        raise OwlProtocolError(f"unexpected response to {command}: {raw!r}")
    fields = parts[2:]
    if len(fields) < minimum:
        raise OwlProtocolError(f"too few fields in response to {command}: {raw!r}")
    return fields


def _int(value: str, raw: str) -> int:
    try:
        return int(value)
    except ValueError as err:
        raise OwlProtocolError(f"expected integer in {raw!r}") from err


def _float(value: str, raw: str) -> float:
    try:
        return float(value)
    except ValueError as err:
        raise OwlProtocolError(f"expected number in {raw!r}") from err


def parse_device_status(raw: str) -> DeviceStatus:
    f = _fields(raw, "DEVICE", 10)
    return DeviceStatus(
        index=_int(f[0], raw),
        address=f[1],
        device_type=f[2],
        seconds_since_rx=_int(f[3], raw),
        state=_int(f[4], raw),
        rssi=_int(f[5], raw),
        lqi=_int(f[6], raw),
        battery=f[7],
        rx_packets=_int(f[8], raw),
        tx_packets=_int(f[9], raw),
    )


def parse_device_list(raw: str) -> tuple[str, ...]:
    return tuple(_fields(raw, "DEVICE", 1))


def parse_electricity_config(raw: str) -> ElectricityConfig:
    f = _fields(raw, "ELECTRICITY", 4)
    return ElectricityConfig(
        mode=_int(f[0], raw),
        flags=_int(f[1], raw),
        voltage=_float(f[2], raw),
        power_factor=_float(f[3], raw),
    )


def format_electricity_config(cfg: ElectricityConfig) -> tuple[str, ...]:
    """Arguments for SET,ELECTRICITY in the form the device echoes back."""
    voltage = str(int(cfg.voltage)) if cfg.voltage.is_integer() else f"{cfg.voltage:g}"
    return (str(cfg.mode), str(cfg.flags), voltage, f"{cfg.power_factor:.2f}")


def parse_clock(raw: str) -> tuple[int, int]:
    f = _fields(raw, "CLOCK", 2)
    return _int(f[0], raw), _int(f[1], raw)


def parse_udp_target(raw: str) -> tuple[str, int]:
    f = _fields(raw, "UDP", 3)  # hostname (unused), ip, port
    return f[1], _int(f[2], raw)


def parse_mac(raw: str) -> str:
    f = _fields(raw, "MAC", 1)
    try:
        return normalize_mac(f[0])
    except ValueError as err:
        raise OwlProtocolError(str(err)) from err


def parse_version(raw: str) -> str:
    return " ".join(part for part in _fields(raw, "VERSION", 1) if part)


def parse_uptime(raw: str) -> str:
    return ",".join(_fields(raw, "UPTIME", 1)).strip()


class _ResponseProtocol(asyncio.DatagramProtocol):
    """Collect the single datagram the device sends back."""

    def __init__(self, future: asyncio.Future[str]) -> None:
        self._future = future

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not self._future.done():
            self._future.set_result(data.decode(errors="replace"))

    def error_received(self, exc: Exception) -> None:
        if not self._future.done():
            self._future.set_exception(OwlProtocolError(f"socket error: {exc}"))


class OwlClient:
    """Send authenticated commands to the Network OWL command port."""

    def __init__(
        self,
        host: str,
        key: str,
        *,
        port: int = COMMAND_PORT,
        timeout: float = 3.0,
        retries: int = 2,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self._key = normalize_key(key)

    async def command(self, *parts: str, expect_response: bool = True) -> str:
        """Send `PART,PART,...,KEY` and return the raw reply text."""
        payload = ",".join((*parts, self._key)).encode()
        loop = asyncio.get_running_loop()
        for attempt in range(self.retries + 1):
            future: asyncio.Future[str] = loop.create_future()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _ResponseProtocol(future), remote_addr=(self.host, self.port)
            )
            try:
                transport.sendto(payload)
                if not expect_response:
                    return ""
                return await asyncio.wait_for(future, self.timeout)
            except TimeoutError:
                if attempt == self.retries:
                    break
            finally:
                transport.close()
        raise OwlTimeoutError(
            f"no response from {self.host}:{self.port} to {parts[0]} "
            "(wrong key, wrong host or device offline)"
        )

    async def get_mac(self) -> str:
        return parse_mac(await self.command("GET", "MAC"))

    async def get_version(self) -> str:
        return parse_version(await self.command("GET", "VERSION"))

    async def get_device_list(self) -> tuple[str, ...]:
        return parse_device_list(await self.command("GET", "DEVICE", "ALL"))

    async def get_device(self, index: int = 0) -> DeviceStatus:
        return parse_device_status(await self.command("GET", "DEVICE", str(index)))

    async def get_udp_target(self) -> tuple[str, int]:
        return parse_udp_target(await self.command("GET", "UDP"))

    async def set_udp_target(self, ip: str, port: int) -> None:
        parse_udp_target(await self.command("SET", "UDP", "", ip, str(port)))

    async def save(self) -> None:
        _fields(await self.command("SAVE"), "SAVE", 0)

    async def get_electricity_config(self) -> ElectricityConfig:
        return parse_electricity_config(await self.command("GET", "ELECTRICITY"))

    async def set_electricity_config(self, cfg: ElectricityConfig) -> ElectricityConfig:
        return parse_electricity_config(
            await self.command("SET", "ELECTRICITY", *format_electricity_config(cfg))
        )

    async def get_clock(self) -> tuple[int, int]:
        return parse_clock(await self.command("GET", "CLOCK"))

    async def set_clock(self, epoch_utc: int) -> tuple[int, int]:
        return parse_clock(await self.command("SET", "CLOCK", str(epoch_utc)))

    async def set_timezone(self, offset_seconds: int) -> None:
        _fields(await self.command("SET", "TZ", str(offset_seconds)), "TZ", 1)

    async def set_dst(self, enabled: bool) -> None:
        _fields(await self.command("SET", "DST", "1" if enabled else "0"), "DST", 1)

    async def get_uptime(self) -> str:
        return parse_uptime(await self.command("GET", "UPTIME"))

    async def scan(self, device_type: int = 180) -> None:
        _fields(await self.command("SCAN", str(device_type)), "SCAN", 0)

    async def reboot(self) -> None:
        await self.command("REBOOT", expect_response=False)
