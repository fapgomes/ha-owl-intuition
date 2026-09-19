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

from custom_components.owl_intuition.protocol import (  # noqa: E402
    DeviceStatus,
    ElectricityConfig,
    format_electricity_config,
    parse_clock,
    parse_device_list,
    parse_device_status,
    parse_electricity_config,
    parse_mac,
    parse_udp_target,
    parse_uptime,
    parse_version,
)


def test_parse_device_status_real_response() -> None:
    status = parse_device_status(
        "OK,DEVICE,0,2FC,CMR180,28,0,-51,1,1,3,0,0.0:0,0.00,0,0,0,0.00"
    )
    assert status == DeviceStatus(
        index=0,
        address="2FC",
        device_type="CMR180",
        seconds_since_rx=28,
        state=0,
        rssi=-51,
        lqi=1,
        battery="1",
        rx_packets=3,
        tx_packets=0,
    )


def test_parse_device_list() -> None:
    raw = "OK,DEVICE,CMR180,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE,NONE"
    assert parse_device_list(raw) == ("CMR180",) + ("NONE",) * 9


def test_parse_electricity_config_and_format_roundtrip() -> None:
    cfg = parse_electricity_config("OK,ELECTRICITY,1,7,230,1.00")
    assert cfg == ElectricityConfig(mode=1, flags=7, voltage=230.0, power_factor=1.0)
    assert format_electricity_config(cfg) == ("1", "7", "230", "1.00")
    assert format_electricity_config(
        ElectricityConfig(mode=1, flags=7, voltage=232.5, power_factor=0.95)
    ) == ("1", "7", "232.5", "0.95")


def test_parse_clock() -> None:
    assert parse_clock("OK,CLOCK,1789825772,1789829372") == (1789825772, 1789829372)


def test_parse_udp_target() -> None:
    assert parse_udp_target("OK,UDP,,192.168.1.1,22600") == ("192.168.1.1", 22600)
    assert parse_udp_target("OK,UDP,,0.0.0.0,0") == ("0.0.0.0", 0)


@pytest.mark.parametrize("raw", ["OK,MAC,443719000677", "OK,MAC,44:37:19:00:06:77"])
def test_parse_mac(raw: str) -> None:
    assert parse_mac(raw) == "44:37:19:00:06:77"


def test_parse_version_joins_fields() -> None:
    assert parse_version("OK,VERSION,NOWL,2.3,1234") == "NOWL 2.3 1234"


def test_parse_uptime_keeps_text() -> None:
    assert parse_uptime("OK,UPTIME,3 Mins 2 Secs") == "3 Mins 2 Secs"


@pytest.mark.parametrize(
    ("func", "raw"),
    [
        (parse_clock, "OK,UPTIME,3 Mins"),
        (parse_clock, "ERROR"),
        (parse_device_status, "OK,DEVICE,0,2FC"),
        (parse_udp_target, "OK,UDP,192.168.1.1"),
        (parse_electricity_config, "OK,ELECTRICITY,1,7"),
    ],
)
def test_parsers_reject_unexpected(func, raw: str) -> None:
    with pytest.raises(OwlProtocolError):
        func(raw)
