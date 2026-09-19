"""Coordinator: holds the latest push reading and polls diagnostics."""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_POLL_INTERVAL,
    CONF_PUSH_PORT,
    CONF_SW_VERSION,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .protocol import (
    DeviceStatus,
    ElectricityConfig,
    ElectricityReading,
    OwlClient,
    OwlError,
    OwlTimeoutError,
)

_LOGGER = logging.getLogger(__name__)

CONNECTIVITY_TIMEOUT = timedelta(minutes=5)
AUTO_SYNC_MIN_INTERVAL = timedelta(minutes=10)
REBOOT_TIMESTAMP_THRESHOLD = 86_400  # a "timestamp" below one day is seconds since boot
CLOCK_DRIFT_THRESHOLD_S = 120
MAX_POLL_FAILURES = 3
ISSUE_NO_DATA = "no_data"
ISSUE_CLOCK_NOT_SYNCED = "clock_not_synced"


@dataclass
class OwlData:
    """Everything the entities read."""

    reading: ElectricityReading | None = None
    device: DeviceStatus | None = None
    electricity: ElectricityConfig | None = None
    clock_utc: int | None = None
    clock_offset_s: int | None = None
    uptime: str | None = None
    transmitter_last_seen: datetime | None = None


def _zone_uses_dst(now: datetime) -> bool:
    tz = now.tzinfo
    january = datetime(now.year, 1, 1, 12, tzinfo=tz)
    july = datetime(now.year, 7, 1, 12, tzinfo=tz)
    return (january.dst() or timedelta()) != (july.dst() or timedelta())


class OwlCoordinator(DataUpdateCoordinator[OwlData]):
    """Merge push readings with polled diagnostics."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: OwlClient) -> None:
        interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.unique_id}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.mac: str = entry.unique_id or ""
        self.sw_version: str | None = entry.data.get(CONF_SW_VERSION)
        self.data = OwlData()
        self._poll_failures = 0
        self._last_auto_sync: datetime | None = None
        self._connectivity_unsub: CALLBACK_TYPE | None = None

    # ---------- push path ----------

    @property
    def connected(self) -> bool:
        reading = self.data.reading if self.data else None
        if reading is None:
            return False
        return dt_util.utcnow() - reading.received_at < CONNECTIVITY_TIMEOUT

    @callback
    def handle_reading(self, reading: ElectricityReading) -> None:
        """Called by the listener for every new push packet."""
        if reading.owl_id.lower() != self.mac.replace(":", ""):
            _LOGGER.debug("ignoring packet from other OWL %s", reading.owl_id)
            return
        previous = self.data.reading
        rebooted = reading.timestamp < REBOOT_TIMESTAMP_THRESHOLD or (
            previous is not None and reading.timestamp < previous.timestamp
        )
        self.async_set_updated_data(replace(self.data, reading=reading))
        ir.async_delete_issue(self.hass, DOMAIN, f"{ISSUE_NO_DATA}_{self.mac}")
        self._schedule_connectivity_check()
        if rebooted:
            self.hass.async_create_task(self._async_auto_sync_clock())

    def _schedule_connectivity_check(self) -> None:
        if self._connectivity_unsub is not None:
            self._connectivity_unsub()
        self._connectivity_unsub = async_call_later(
            self.hass, CONNECTIVITY_TIMEOUT, self._connectivity_expired
        )

    @callback
    def _connectivity_expired(self, _now: datetime) -> None:
        self._connectivity_unsub = None
        self.async_update_listeners()
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{ISSUE_NO_DATA}_{self.mac}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_NO_DATA,
            translation_placeholders={
                "name": self.config_entry.title,
                "port": str(self.config_entry.options.get(CONF_PUSH_PORT, "")),
            },
        )

    async def async_shutdown(self) -> None:
        if self._connectivity_unsub is not None:
            self._connectivity_unsub()
            self._connectivity_unsub = None
        await super().async_shutdown()

    # ---------- poll path ----------

    async def _async_update_data(self) -> OwlData:
        data = self.data or OwlData()
        try:
            device = await self.client.get_device(0)
            uptime = await self.client.get_uptime()
            electricity = await self.client.get_electricity_config()
            try:
                clock_utc: int | None = (await self.client.get_clock())[0]
            except OwlTimeoutError:
                clock_utc = None  # no clock after a reboot without the cloud
        except OwlError as err:
            self._poll_failures += 1
            if self._poll_failures >= MAX_POLL_FAILURES:
                raise UpdateFailed(f"Network OWL not answering: {err}") from err
            _LOGGER.debug(
                "poll failed (%s/%s): %s", self._poll_failures, MAX_POLL_FAILURES, err
            )
            return data
        self._poll_failures = 0
        now = dt_util.utcnow()
        offset = clock_utc - int(now.timestamp()) if clock_utc is not None else None
        new = replace(
            data,
            device=device,
            uptime=uptime,
            electricity=electricity,
            clock_utc=clock_utc,
            clock_offset_s=offset,
            transmitter_last_seen=now - timedelta(seconds=device.seconds_since_rx),
        )
        if offset is None or abs(offset) > CLOCK_DRIFT_THRESHOLD_S:
            self.hass.async_create_task(self._async_auto_sync_clock())
        return new

    # ---------- clock ----------

    async def async_sync_clock(self) -> None:
        """Set timezone, DST and clock from Home Assistant's time. Raises OwlError."""
        now = dt_util.now()
        standard_offset = int(
            ((now.utcoffset() or timedelta()) - (now.dst() or timedelta())).total_seconds()
        )
        await self.client.set_timezone(standard_offset)
        await self.client.set_dst(_zone_uses_dst(now))
        await self.client.set_clock(int(dt_util.utcnow().timestamp()))
        await self.client.save()
        ir.async_delete_issue(self.hass, DOMAIN, f"{ISSUE_CLOCK_NOT_SYNCED}_{self.mac}")
        await self.async_request_refresh()

    async def _async_auto_sync_clock(self) -> None:
        now = dt_util.utcnow()
        if (
            self._last_auto_sync is not None
            and now - self._last_auto_sync < AUTO_SYNC_MIN_INTERVAL
        ):
            return
        self._last_auto_sync = now
        try:
            await self.async_sync_clock()
        except OwlError as err:
            _LOGGER.warning("automatic clock sync failed: %s", err)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{ISSUE_CLOCK_NOT_SYNCED}_{self.mac}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_CLOCK_NOT_SYNCED,
                translation_placeholders={"name": self.config_entry.title},
            )
