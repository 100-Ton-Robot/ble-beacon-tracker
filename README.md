# BLE Beacon Tracker (DIY)

A passive BLE beacon locator. Three Seeed XIAO nRF54L15 scanners sit behind directional antennas
facing out 120 deg apart. Comparing RSSI between sectors gives a bearing, and RSSI gives a rough
range. An ESP32-S3 Ethernet gateway (ESPHome) collects the scanners' data and publishes it to MQTT
for a tracker in Home Assistant.

Passive RSSI only: it works with any beacon, with no pairing and no Channel Sounding.

## What's here

| Folder | What it is |
| --- | --- |
| [`scanner_fw/`](scanner_fw/README.md) | Scanner firmware: nRF Connect SDK / Zephyr behind MCUboot, with signed BLE updates. Build, flash, console commands, frame format. |
| [`gateway/`](gateway/README.md) | ESPHome config and the `sector_scanner` external component: binary UART frames in, JSON over MQTT out. |
| [`shield_deck/`](shield_deck/README.md) | Copper shield deck PCB (Gerbers for PCBWay) and printable 1:1 drilling templates, generated from Python scripts. |
| `experiments/` | Side experiments (the deck redone in KiCad). |

Prebuilt scanner update images are in `scanner_fw/release/`. They only install on scanners whose
MCUboot was built with the same signing key, so build your own from source with your own key
(see `scanner_fw/README.md`).

## Status

Work in progress. The scanner firmware runs on hardware; the gateway compiles but hasn't run on a
board yet; the Home Assistant tracker isn't written yet.

## Bugs and contributions

Bug reports and pull requests are welcome: use [Issues](../../issues). For firmware problems,
include the version, the console's `status` output and what you expected to happen.

## License

[MIT](LICENSE).
