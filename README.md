# OWL Intuition for Home Assistant (local only)

Home Assistant integration for the **OWL Intuition Network OWL** electricity
monitor that works **entirely on your LAN**. No OWL cloud account is needed
once you have the device's UDP key.

## Why

Current Network OWL firmware only enters pairing mode and only configures
itself through the OWL cloud. Once configured, though, the device can push
its readings by UDP to any host on the LAN and accepts commands on UDP port
5100 when they carry its UDP key. This integration uses exactly that, so
you can block the device's Internet access and keep everything at home.

## What you get

- Power per phase and total (W), energy today per phase and total (kWh,
  ready for the Energy dashboard)
- Transmitter battery, signal strength, link quality, last seen
- Network OWL uptime, clock offset, connectivity
- Voltage and power factor configuration
- Buttons: pair transmitter, sync clock, reboot
- Automatic clock, timezone and DST sync after the device reboots (without
  the cloud the device has no clock, and the daily counters would reset at
  the wrong time)
- Repairs issues when readings stop or the clock cannot be set

## Requirements

- Network OWL with an electricity transmitter (tested with CMR180i, three
  phase, Intuition-lc) already paired once.
- The device's **UDP key**: OWL Intuition dashboard → System → Advanced
  Settings → Data Push (7–8 hexadecimal characters). You need the device
  online once to read it. After that, block it at your firewall.
- Home Assistant 2026.9 or newer. UDP port 22600 free on the HA host.

## Installation

HACS → Integrations → ⋮ → Custom repositories → add this repository as
"Integration" → install → restart Home Assistant → Settings → Devices &
services → Add integration → **OWL Intuition**.

Enter the Network OWL IP, the UDP key, and confirm the push destination
(pre-filled with your Home Assistant IP). The integration sends `SET,UDP`
to the device and saves it.

## Options

Push host/port, multicast listening (off by default; only for Network OWLs
that broadcast on 224.192.32.19), and the diagnostics polling interval.

## Notes

- A wrong key produces **no response** from the device, so "cannot connect"
  usually means wrong key or wrong IP.
- The device can push to a single destination. Configuring this integration
  redirects any previous push target.
- If you change the transmitter batteries, pairing is lost: press
  **Pair transmitter**, then hold the transmitter's Check button until its
  red LED flashes.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

Design and device protocol notes: `docs/superpowers/specs/`.
