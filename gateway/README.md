# Mast gateway (ESPHome, ESP32-S3 + Ethernet)

Reads the three sector scanners' binary frames and publishes each second's device table to
MQTT, one JSON message per sector. It also sets each scanner's sector and passes commands to
the scanners. Frame and command formats (v2) are in `../scanner_fw/README.md`; the gateway
needs scanner firmware **0.3.0 or later** and drops older (v1) frames as bad.

Home Assistant sees only the gateway's own entities, over the ESPHome API: health sensors,
the chip ID on each sector and a few buttons. There are no Home Assistant entities per beacon,
and MQTT carries only the beacon data and the commands (MQTT discovery is off).

- `example-mast.yaml`: the per-mast device config. Copy it once per gateway (e.g.
  `bletracker-garage.yaml`) and set the mast ID, name and API key secret; it stays on DHCP
  unless you uncomment its static IP block.
- `packages/bletracker-gateway.yaml`: everything shared by every mast, for the Waveshare
  ESP32-S3-ETH (pins from its [pinout](https://docs.waveshare.com/ESP32-S3-ETH), all in
  `substitutions`). The mast files pull it in with `packages:`; it is not a device config on
  its own.
- `components/sector_scanner/`: external component, one entry per scanner UART.
- `secrets.example.yaml`: copy to `secrets.yaml` (or use the ESPHome dashboard's secrets).

Each mast needs its own `mast` ID: it goes into the MQTT topics (`bletracker/<mast>/...`) and
the device name (`bletracker-<mast>`), so two gateways never share topics or a Home Assistant
device.

```yaml
# bletracker-garage.yaml
substitutions:
  mast: garage
  name: bletracker-${mast}
  friendly_name: BLE Tracker Garage
  api_key: !secret api_key_garage

packages:
  gateway: !include packages/bletracker-gateway.yaml
```

## Build and flash

In the Home Assistant ESPHome add-on: copy `components/`, `packages/` and your mast file(s)
into the add-on's `config/esphome/` folder, then Install the mast. First flash over the S3's
USB-C; later ones over Ethernet (OTA). Then add the device in Home Assistant's ESPHome
integration (API key from your secrets).

From a PC, ESPHome must build in a path without spaces (like the scanner firmware), so copy
this folder somewhere like `C:\fw\gw-build` first:

```bash
esphome run example-mast.yaml
```

`example-mast.yaml` compiled clean with ESPHome 2026.9.0 on 2026-10-31, and the same gateway
code runs on a board (ESPHome 2026.10.1, flashed 2026-10-31; scanner frames not yet seen).

## Wiring

All gateway wiring is on header pins 31-40 (pin numbers as printed on Waveshare's pinout).
Each scanner's D6 has its own gateway RX pin, and that pin is its sector. The gateway has one
TX that goes to every scanner's D7 through the bus board's TX row; commands carry the target
scanner's chip ID, so only that scanner acts on them.

| XIAO | Sector 0 | Sector 1 | Sector 2 |
| --- | --- | --- | --- |
| D6 (TX) → gateway RX | GPIO17 (34) | GPIO16 (32) | GPIO18 (31) |
| D7 (RX) ← bus TX row ← gateway TX | GPIO21 (35) | GPIO21 (35) | GPIO21 (35) |
| 5V ← bus 5V row | VBUS (40) | VBUS (40) | VBUS (40) |
| GND ← bus GND row | GND (38) | GND (38) | GND (38) |

VBUS is the USB-C 5 V, which is where the PoE splitter feeds the board. Kept clear: GPIO 4-7
(TF card), 9-14 (W5500), 0/3/45/46 (strapping), 19/20 (USB), 33-37 (octal PSRAM), 43/44.
GPIO1 and GPIO2 are free. Logs come out on the S3's native USB-C (all three hardware UARTs are
used by the scanners).

## Sectors

The gateway learns each scanner's chip ID from its frames, per RX pin (on every frame, so a
swapped board is picked up). If a scanner reports a sector other than its pin's, the gateway
sends it that sector (command 4, addressed to its chip) at most every 5 s until the frame
header shows it. Scanners need no manual sector setup.

## MQTT output

Topic `bletracker/<mast>/<sector>`, once a second per sector, not retained:

```json
{"sector":0,"seq":175,"chip":"1a2b3c4d5e6f7081","scanner_sector":0,"ant":"int","adverts":46,
 "dropped":0,"full":false,"listening":true,"flash":false,"client":false,"test_image":false,
 "lost":0,"devs":[["0971EA5F01FD",1,"nonconn",-53,-53,3,null],
                  ["7A71EA904EBB",1,"scan",-67,-67,1,-59]]}
```

- `sector`: from the gateway config (which RX pin), not from the scanner.
- `chip`: the scanner's chip ID (lowercase hex, as its console's `status` prints it).
- `scanner_sector`: the sector saved in the scanner (the gateway corrects it, see above).
- `seq`: the scanner's frame counter (wraps at 256). `lost`: frames missed on this RX pin since
  boot. `dropped`: adverts the scanner itself couldn't queue.
- Header flags: `ant` (`int`/`ext` antenna), `full` (the 64-device table overflowed that
  second), `listening`, `flash` (flash mode open), `client` (an update client is connected),
  `test_image` (running an update that hasn't confirmed itself yet).
- `devs`, strongest first: `[address, random (1) / public (0), advert type, rssi_med, rssi_max,
  count, tx_1m or null]`. RSSI in dBm over that second; `tx_1m` is the beacon's advertised
  power at 1 m (iBeacon / Eddystone).

Watch the stream from a PC:

```bash
mosquitto_sub -h <broker> -u <user> -P <pass> -t 'bletracker/#' -v
```

## Commands

Publish to `bletracker/<mast>/<sector>/cmd` to reach that sector's scanner (the chip last
seen on its RX pin; ignored with a warning until one has been seen), or to
`bletracker/<mast>/all/cmd` for every scanner on the mast:

| Payload | Effect |
| --- | --- |
| `listen on` / `listen off` | start / stop scanning (frames keep coming, `listening` shows it) |
| `flash on` / `flash off` | open (10 min) / close flash mode for a BLE firmware update |
| `ant ext` / `ant int` | external / onboard antenna (saved in the scanner) |
| `reboot` | restart the scanner |

There is no reply; the result shows in the next frame (`flash`, `listening`, `ant`). The
sector can't be sent by hand: the gateway sets it. Each command sent is logged at DEBUG with
its bytes in hex, which match `../scanner_fw/tools/decode_frames.py --cmd ...`.

## Home Assistant entities

Over the ESPHome API, per sector: devices heard, lost frames, bad frames (CRC, length or
version errors; one at boot is normal, as the first frame is usually partial), the scanner's
chip ID, and buttons "flash mode" and "reboot scanner". Plus the gateway's IP and MAC address.
