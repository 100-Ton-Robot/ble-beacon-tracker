# Mast gateway (ESPHome, ESP32-S3 + Ethernet)

Reads the three sector scanners' binary frames (format in `../scanner_fw/README.md`) and
publishes each second's device table to MQTT, one JSON message per sector. There are no Home
Assistant entities per device; only the gateway's own health sensors are discovered.

- `bletracker-gateway.yaml`: the device config for the Waveshare ESP32-S3-ETH (pins from its
  [pinout](https://docs.waveshare.com/ESP32-S3-ETH), all in `substitutions`).
- `components/sector_scanner/`: external component, one entry per UART.
- `secrets.example.yaml`: copy to `secrets.yaml` (or use the ESPHome dashboard's secrets).

## Build and flash

In the Home Assistant ESPHome add-on: copy `components/` into the add-on's `config/esphome/`
folder next to the YAML, then Install. First flash over the S3's USB-C; later ones over
Ethernet (OTA).

From a PC, ESPHome must build in a path without spaces (like the scanner firmware), so copy
this folder somewhere like `C:\fw\gw-build` first:

```bash
esphome run bletracker-gateway.yaml
```

Compiled clean with ESPHome 2026.10.1 on 2026-10-29 (not yet run on a board).

## Wiring per sector

All on the board's left header (pin numbers as printed on Waveshare's pinout):

| XIAO | Sector 0 | Sector 1 | Sector 2 |
| --- | --- | --- | --- |
| 5V | VBUS (40) | VBUS (40) | VBUS (40) |
| GND | GND (38) | GND (33) | GND (28) |
| D6 (TX) | GPIO21 (35) | GPIO16 (32) | GPIO2 (26) |
| D7 (RX), unused for now | GPIO17 (34) | GPIO18 (31) | GPIO1 (25) |

VBUS is the USB-C 5 V, which is where the PoE splitter feeds the board. Kept clear: GPIO 4-7
(TF card), 9-14 (W5500), 0/3/45/46 (strapping), 19/20 (USB), 33-37 (octal PSRAM), 43/44.
Logs come out on the S3's native USB-C (all three hardware UARTs are taken by the scanners).

## MQTT output

Topic `bletracker/<mast>/<sector>`, once a second per sector, not retained:

```json
{"sector":0,"seq":175,"ant":"int","adverts":46,"dropped":0,"full":false,"lost":0,
 "devs":[["0971EA5F01FD",1,"nonconn",-53,-53,3,null],
         ["7A71EA904EBB",1,"scan",-67,-67,1,-59]]}
```

- `sector`: from the gateway config (which UART), not from the scanner.
- `seq`: the scanner's frame counter (wraps at 256). `lost`: frames missed on this UART since
  boot. `dropped`: adverts the scanner itself couldn't queue. `full`: the scanner's 64-device
  table overflowed that second.
- `devs`, strongest first: `[address, random (1) / public (0), advert type, rssi_med, rssi_max,
  count, tx_1m or null]`. RSSI in dBm over that second; `tx_1m` is the beacon's advertised
  power at 1 m (iBeacon / Eddystone).

Health sensors per sector (MQTT discovery): devices heard, lost frames, bad frames (CRC or
length errors; one at boot is normal, as the first frame is usually partial).

Watch the stream from a PC:

```bash
mosquitto_sub -h <broker> -u <user> -P <pass> -t 'bletracker/#' -v
```
