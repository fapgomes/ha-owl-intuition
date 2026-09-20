"""Tests for OwlClient against the fake device."""
import asyncio

import pytest

from custom_components.owl_intuition.protocol import (
    DeviceStatus,
    ElectricityConfig,
    OwlClient,
    OwlProtocolError,
    OwlTimeoutError,
)

from .conftest import KEY, FakeOwl


def make_client(fake_owl: FakeOwl, key: str = KEY, **kwargs) -> OwlClient:
    return OwlClient(fake_owl.host, key, port=fake_owl.port, timeout=0.2, retries=1, **kwargs)


async def test_get_mac_appends_upper_case_key(fake_owl: FakeOwl) -> None:
    client = make_client(fake_owl, key="70f87a4")
    assert await client.get_mac() == "44:37:19:00:06:77"
    assert fake_owl.received == ["GET,MAC,70F87A4"]


async def test_typed_getters(fake_owl: FakeOwl) -> None:
    client = make_client(fake_owl)
    assert await client.get_version() == "NOWL 2.3 1234"
    assert (await client.get_device_list())[0] == "CMR180"
    assert (await client.get_device(0)) == DeviceStatus(0, "2FC", "CMR180", 28, 0, -51, 1, "1", 3, 0)
    assert await client.get_udp_target() == ("192.168.1.100", 22600)
    assert await client.get_electricity_config() == ElectricityConfig(1, 7, 230.0, 1.0)
    assert await client.get_clock() == (1789825772, 1789829372)
    assert await client.get_uptime() == "3 Mins 2 Secs"


async def test_setters_send_expected_wire_format(fake_owl: FakeOwl) -> None:
    client = make_client(fake_owl)
    await client.set_udp_target("192.168.1.100", 22600)
    await client.save()
    assert await client.set_electricity_config(ElectricityConfig(1, 7, 240, 0.95)) == ElectricityConfig(1, 7, 240.0, 0.95)
    assert await client.set_clock(1789825772) == (1789825772, 1789829372)
    await client.set_timezone(0)
    await client.set_dst(True)
    await client.scan()
    assert fake_owl.received == [
        f"SET,UDP,,192.168.1.100,22600,{KEY}",
        f"SAVE,{KEY}",
        f"SET,ELECTRICITY,1,7,240,0.95,{KEY}",
        f"SET,CLOCK,1789825772,{KEY}",
        f"SET,TZ,0,{KEY}",
        f"SET,DST,1,{KEY}",
        f"SCAN,180,{KEY}",
    ]


async def test_wrong_key_times_out_after_retries(fake_owl: FakeOwl) -> None:
    client = make_client(fake_owl, key="0000000")
    with pytest.raises(OwlTimeoutError):
        await client.get_mac()
    assert fake_owl.received == ["GET,MAC,0000000", "GET,MAC,0000000"]  # 1 try + 1 retry


async def test_malformed_response_raises_protocol_error(fake_owl: FakeOwl) -> None:
    fake_owl.responses["GET,CLOCK"] = "OK,UPTIME,3 Mins"
    client = make_client(fake_owl)
    with pytest.raises(OwlProtocolError):
        await client.get_clock()


async def test_reboot_does_not_wait_for_a_reply(fake_owl: FakeOwl) -> None:
    client = make_client(fake_owl)
    await client.reboot()  # no response configured; must not raise
    await asyncio.sleep(0.05)  # let the fake server's loop iteration run
    assert fake_owl.received == [f"REBOOT,{KEY}"]


async def test_save_waits_for_slow_flash_write(fake_owl: FakeOwl) -> None:
    """The real device takes ~4 s to answer SAVE; other commands answer in ms."""
    fake_owl.delays["SAVE"] = 0.5  # longer than the 0.2 s general timeout
    client = make_client(fake_owl)
    await client.save()
    assert fake_owl.received == [f"SAVE,{KEY}"]  # one attempt, no retries needed
