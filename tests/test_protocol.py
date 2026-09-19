"""Tests for the pure-Python protocol layer."""
from datetime import datetime, timezone

import pytest

from custom_components.owl_intuition.protocol import (
    ElectricityReading,
    OwlProtocolError,
    normalize_key,
    normalize_mac,
    parse_electricity,
)

REAL_PACKET = (
    "<electricity id='443719000677'><timestamp>1789825304</timestamp>"
    "<signal rssi='-52' lqi='13'/><battery level='100%'/>"
    "<chan id='0'><curr units='w'>12.50</curr><day units='wh'>1234.00</day></chan>"
    "<chan id='1'><curr units='w'>0.00</curr><day units='wh'>0.00</day></chan>"
    "<chan id='2'><curr units='w'>300.25</curr><day units='wh'>5000.50</day></chan>"
    "</electricity>"
)


def test_parse_electricity_real_packet() -> None:
    received = datetime(2026, 9, 19, 13, 41, 44, tzinfo=timezone.utc)
    reading = parse_electricity(REAL_PACKET.encode(), received_at=received)
    assert isinstance(reading, ElectricityReading)
    assert reading.owl_id == "443719000677"
    assert reading.timestamp == 1789825304
    assert reading.rssi == -52
    assert reading.lqi == 13
    assert reading.battery_pct == 100
    assert reading.received_at == received
    assert [c.channel for c in reading.channels] == [0, 1, 2]
    assert reading.channels[0].power_w == 12.5
    assert reading.channels[0].energy_day_wh == 1234.0
    assert reading.channels[2].power_w == 300.25
    assert reading.total_power_w == pytest.approx(312.75)
    assert reading.total_energy_day_wh == pytest.approx(6234.5)


def test_parse_electricity_without_battery_defaults_to_none() -> None:
    packet = REAL_PACKET.replace("<battery level='100%'/>", "")
    reading = parse_electricity(packet)
    assert reading is not None
    assert reading.battery_pct is None
    assert reading.received_at.tzinfo is not None


def test_parse_electricity_ignores_other_roots() -> None:
    assert parse_electricity("<weather id='443719000677'><temperature>20</temperature></weather>") is None


def test_parse_electricity_rejects_malformed_xml() -> None:
    with pytest.raises(OwlProtocolError):
        parse_electricity("<electricity><timestamp>1<")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("70f87a4", "70F87A4"), (" 70F87A4\n", "70F87A4"), ("0011aabb", "0011AABB")],
)
def test_normalize_key_accepts_7_or_8_hex(raw: str, expected: str) -> None:
    assert normalize_key(raw) == expected


@pytest.mark.parametrize("raw", ["", "12345", "123456789", "70F87G4", "70 F87A4"])
def test_normalize_key_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_key(raw)


@pytest.mark.parametrize(
    "raw",
    ["443719000677", "44:37:19:00:06:77", "44-37-19-00-06-77", "443719-000677"],
)
def test_normalize_mac_formats(raw: str) -> None:
    assert normalize_mac(raw) == "44:37:19:00:06:77"


def test_normalize_mac_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        normalize_mac("4437190006")
