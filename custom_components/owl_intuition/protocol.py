"""Pure-Python protocol layer for the OWL Intuition Network OWL.

This module must not import anything from Home Assistant so it can be
unit-tested on its own and reused outside the integration.
"""
from __future__ import annotations

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
