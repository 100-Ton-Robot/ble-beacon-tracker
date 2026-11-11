# Scanner firmware (XIAO nRF54L15)

nRF Connect SDK (Zephyr) app behind MCUboot. It scans (passive, or active on command), controls
the RF switch and every 200 ms sends the gateway a protobuf bucket on the header UART: RSSI per
address, and optionally each address's raw advert and scan response bytes, plus status, events
(security ones included) and counters. A byte budget and a throttle keep it inside the line,
shedding payloads before RSSI. The gateway sends commands back on the same UART: listen, flash
mode, antenna, payloads, active scanning, intervals, budget and the ignore list (addresses
or address ranges whose adverts are dropped, saved in flash or until reboot). The stream is specified
in [PROTOCOL.md](PROTOCOL.md) and [proto/bletracker.proto](proto/bletracker.proto). Each scanner's TX (D6) has its own gateway RX pin, which is how the gateway
knows the sector (the scanner itself doesn't); the gateway's one TX drives all three scanners' RX (D7) through the bus board,
so commands are addressed by chip ID. In flash mode the scanner takes signed firmware updates
over BLE, so it can be updated with the box sealed. The antenna choice is kept in flash.

## Setup (once)

1. Install VS Code and the **nRF Connect for VS Code** extension pack.
2. In the extension, install a toolchain and an SDK (latest v3.x). The board target
   `xiao_nrf54l15/nrf54l15/cpuapp` must be in the board list; if it isn't, the SDK is too old.
3. "Open an existing application" -> the `scanner_fw` folder, through a path without spaces
   (e.g. `C:\fw\scanner_fw`, see below).

## Path without spaces

The SDK's build (sysbuild) fails when the app path contains spaces. If your clone of the repo
is in such a path, open the app through a space-free junction instead (one copy of the files,
two paths):

```bash
cmd /c mklink /J C:\fw\scanner_fw "<path to your clone>\scanner_fw"
```

(create `C:\fw` first). Keep build folders short too: Windows' 260-character path limit breaks
the build in deep folders. Built clean on 2026-10-29 with NCS v3.4.1: 103 KB flash, 26 KB RAM.

The commands below use `C:\ncs\v3.4.1` for the SDK and `C:\fw\scanner_fw` for the app. Change
them to your own SDK version and paths.

## Build and flash

In the extension: add a build configuration with board `xiao_nrf54l15/nrf54l15/cpuapp`,
build, then Flash. From an nRF Connect terminal the same thing is:

```bash
west build -b xiao_nrf54l15/nrf54l15/cpuapp
```

```bash
west flash
```

Flashing goes through the board's onboard SAMD11 (CMSIS-DAP) with **OpenOCD**, the board's
default runner. The SDK toolchain doesn't include OpenOCD. Stock OpenOCD works (Seeed's wiki
uses it): the board's `support/openocd.cfg` writes RRAM directly, so no special nRF54L driver
is needed, and Arduino's fork mentioned in the Zephyr docs has no downloadable releases. On
Windows, from an **admin** PowerShell with [Chocolatey](https://chocolatey.org/) installed:

```bash
choco install openocd
```

Restart VS Code afterwards so it sees `openocd` on PATH.

**Board flash bug (fixed in this app):** the board's own OpenOCD load (`nrf54l-load`) turns on the
RRAM write buffer and never commits it, so the last few bytes of the image are lost. The app then
crashes with a BUS FAULT in `bt_enable`. `CMakeLists.txt` swaps in `support/scanner-load.tcl`,
which writes unbuffered. Checked 2026-10-29 by writing junk over the image tail first: the board
load left it there, `west flash` with the fix rewrote it, and `verify_image` passed.
The board then boots, scans and runs the shell.
A J-Link on the SWD pads also works (`west flash --runner jlink`).

Open the board's USB serial port at 115200 baud (the extension's serial terminal or PuTTY).

### MCUboot and the signing key

`sysbuild.conf` puts MCUboot in front of the app. It uses swap-using-move with revert: a new
image first runs as a test and is rolled back unless it confirms itself. MCUboot only boots
images signed with the Ed25519 key named by `SB_CONFIG_BOOT_SIGNATURE_KEY_FILE` in
`sysbuild.conf` (`C:/fw/keys/bletracker-mcuboot-ed25519.pem`; change it if your key is
elsewhere).

The key is deliberately outside the repo. **Back it up** (password manager or a USB stick). If it
is lost, sealed scanners can no longer be updated over BLE; the box has to be opened and each
one reflashed by USB with a new key.

To make a new key:

```bash
python C:\ncs\v3.4.1\bootloader\mcuboot\scripts\imgtool.py keygen -k C:\fw\keys\bletracker-mcuboot-ed25519.pem -t ed25519
```

The build makes two images, plus the files used for BLE updates:
- `build/mcuboot/zephyr/zephyr.hex`: the bootloader.
- `build/scanner_fw/zephyr/zephyr.signed.hex`: the signed app.
- `build/dfu_application.zip` and `build/scanner_fw/zephyr/zephyr.signed.bin`: for BLE updates.

There is no merged hex: this SDK uses devicetree partitions, not the Partition Manager.

**First flash over USB (box open).** `west flash` would load MCUboot with the board's buggy
loader, so write both hex files with OpenOCD and the fixed load instead:

```bash
openocd -s C:\ncs\v3.4.1\zephyr\boards\seeed\xiao_nrf54l15\support -f openocd.cfg -c "source {C:/fw/scanner_fw/support/scanner-load.tcl}" -c init -c "reset halt" -c "scanner-load C:/fw/scanner_fw/build/mcuboot/zephyr/zephyr.hex" -c "scanner-load C:/fw/scanner_fw/build/scanner_fw/zephyr/zephyr.signed.hex" -c "verify_image C:/fw/scanner_fw/build/mcuboot/zephyr/zephyr.hex" -c "verify_image C:/fw/scanner_fw/build/scanner_fw/zephyr/zephyr.signed.hex" -c reset -c shutdown
```

**Later updates over USB:** write and verify only `zephyr.signed.hex` with the same command.
MCUboot stays in place and the saved settings survive. With several boards attached, add
`-c "adapter serial <probe serial>"` after `-f openocd.cfg`. The probe serial is the last part of
the board's USB parent device ID, and `status` afterwards confirms the chip ID and version.

**No sector setup.** The scanner doesn't know or store its sector (since 0.5.0): the sector is
the gateway RX pin its D6 is wired to, so wiring alone decides it. Any board can go in any
position. 0.4.x boards had a `sector` command and saved claim; 0.5.0 deletes it at boot.

The app's version comes from `VERSION`. Bump it for every release so `status` and the update app
show which image is running.

## Updating over BLE (box sealed)

1. **Turn on flash mode.** Only a serial command opens it: `flash on` from the gateway on D7
   (the "Sector <n> flash mode" button in Home Assistant, or MQTT, see `../gateway/README.md`),
   or `flash on` on the USB console. A normal boot does not (since v0.2.4), so a power cycle won't
   help if the gateway can't send the command. The scanner then advertises as
   `bletracker-<last 6 hex digits of the chip ID>` (0.4.x used `bletracker-s<sector>`).
   - Scanning carries on throughout.
   - Exception: a test image just after an update opens flash mode for 2 minutes. The
     self-check needs to see advertising work, and the uploading app can reconnect.
   - Each `flash on` gives 10 minutes. The timer only runs while no client is connected.
   - `flash off` ends it at once and drops any connection.
2. **Upload the new image.** Either way works:
   - Phone: **nRF Connect Device Manager** (Nordic, iOS/Android). Pick `bletracker-<chip ID tail>`, then
     Image -> Firmware Upgrade -> `dfu_application.zip`, mode "Test Only" (the scanner's own
     60 s check then decides; "Test and Confirm" would let the app confirm it instead).
   - PC with Bluetooth LE: `pip install smpmgr` (a venv is fine), then the command below.
     Not every adapter works: if bleak reports no BLE central role, use the phone app.

     ```bash
     smpmgr --ble bletracker-08df82 upgrade build/scanner_fw/zephyr/zephyr.signed.bin
     ```

3. **The scanner reboots into the new image as a test.** MCUboot swaps it in. If the new image
   runs for 60 s with scanning and flash-mode advertising working, it confirms itself (`image
   confirmed` on the console; `Status.test_image` goes false and an `IMAGE_CONFIRMED` event is sent). If it crashes or hangs before then, the
   next reset puts the old image back.

Only images signed with your key are accepted. Anyone in range during flash mode could connect,
but all they can install is your own signed firmware.

### Testing swap and revert over USB

This puts an image in the second slot exactly as a BLE upload would, marked for a test boot:

```bash
python C:\ncs\v3.4.1\bootloader\mcuboot\scripts\imgtool.py sign --version 0.3.0+0 --slot-size 0xb2000 --header-size 0x800 --align 16 --rom-fixed 0x10000 -k C:/fw/keys/bletracker-mcuboot-ed25519.pem --sha 512 --pad C:/fw/scanner_fw/build/scanner_fw/zephyr/zephyr.bin slot1-test.bin
```

```bash
openocd -s C:\ncs\v3.4.1\zephyr\boards\seeed\xiao_nrf54l15\support -f openocd.cfg -c init -c "reset halt" -c "mww 0x5004b500 0x1" -c "load_image slot1-test.bin 0xC2000 bin" -c "mww 0x5004b500 0x0" -c reset -c shutdown
```

Use the toolchain's Python for imgtool, and give the `--version` from `VERSION` (0.3.0 here).
These values match the board's devicetree partitions (checked in `build/scanner_fw/zephyr/zephyr.dts`, NCS v3.4.1):
MCUboot at `0x0` (`0xf800`), slot 0 at `0x10000` and slot 1 at `0xC2000` (`0xb2000` each), storage at
`0x174000` (`0x9000`). `0x5004b500` is the RRAM controller's CONFIG register: `0x1` enables writes
without the write buffer, as in `support/scanner-load.tcl`. On reset,
MCUboot logs `Swap type: test` and boots the new image. Then either:
- `reboot` within 60 s: `Swap type: revert`, the old image comes back;
- wait 60 s: `image confirmed`, and it stays after a reboot.

Both paths were checked on hardware on 2026-10-30, going from 0.2.0 to 0.2.1.

## Watching what it hears

Open the XIAO's serial port (e.g. COM4; "USB Serial Device" in Device Manager) at 115200
baud with any of these:
- VS Code: nRF Connect sidebar -> **Connected Devices** -> the board -> serial port icon.
- nRF Connect for Desktop -> **Serial Terminal** app.
- PuTTY: Serial, COM4, 115200.

Only one program can hold the port. A script opening it must turn DTR on (pyserial does by
default; .NET `SerialPort` needs `DtrEnable = true`), or nothing comes out. Close the terminal before flashing from a script that
also reads it.

**Keep boards off USB hubs for radio tests.** A XIAO plugged straight into a USB hub lost
everything weaker than about -70 dBm (2026-10-31: 5 addresses and 16 adverts/s in the hub,
22 and 39/s on a cable, same board, same channel): the hub's noise raises the receiver's floor.
Put each board on a cable at least 30 cm from hubs, the PC and other boards. With several boards
attached, `openocd ... -c "adapter serial <probe serial>"` picks which one to flash.

What you see and type:
- Every second: `[1s] ant=int ch=all adverts=37 devices=12 dropped=0` = adverts and distinct
  addresses heard in that second. `ch` is the primary channel scanned (`all` = the controller
  rotates 37-39); `switch=850us` follows it in a second that started with a channel change.
- `print on`: one line per advert with its bytes, e.g.
  `C1:7D:2B:AC:03:BC (random) rssi=-48 type=0 ad=0201060fff...`.
  `type` is the advert type: 0 connectable, 1 directed, 2 scannable, 3 non-connectable
  (most beacons), 4 scan response, 5 extended. `print off` to stop; it scrolls fast.
- `list on`: a table each second, one row per device heard in that second, strongest first:
  `address type med max n tx1m adv` = median and max RSSI (dBm), adverts that second,
  advertised 1 m power (iBeacon, or Eddystone UID/URL 0 m power minus 41; blank if none or
  outside -100..+20 dBm),
  advert type. Up to 64 devices; the median uses that second's last 32 adverts.
  `minrssi -80` hides weaker devices (`minrssi -127` shows all). `list off` to stop.
- `list csv`: the same data as CSV
  `address,addr_type,rssi_med,rssi_max,count,tx_1m`.
- `stream`: bucket stats (sent, skipped, seq). `stream dump`: prints the next bucket's bytes in
  hex; `python tools/decode_frames.py --hex dump.txt` decodes a saved console log.
- `data on|off`: payload records (raw advert and scan response bytes) in the buckets. Off after
  boot; the gateway turns them on.
- `active on|off`: active scanning, which asks scannable devices for their scan response (names
  are usually there). The scanner then transmits scan requests. Passive after boot.
- `budget 10-90`: share of the line the buckets may use per tick (default 70). `budget 10` on
  the bench forces the throttle (load levels in the `[1s]` line and as events).
- `filter C1:7D:2B:AC:03:BC`: track one device; prints `n`, mean, min and max RSSI each second.
  `filter off` to go back.
- `ignore C1:7D:2B:AC:03:BC`: drop that address's adverts as they are heard (no RSSI, payloads
  or console lines) until reboot; add `save` to keep the rule in flash. A range takes a prefix
  or a mask, or `*` bytes: `ignore C1:7D:2B:*:*:*`, `ignore C1:7D:2B:00:00:00/24` and
  `ignore C1:7D:2B:00:00:00/FF:FF:FF:00:00:00` are the same rule. Re-adding a rule with or
  without `save` moves it into or out of flash. `ignore` lists the rules with their hits;
  `unignore <rule as listed>` removes one, `ignore clear boot|saved|all` several, and
  `ignore off` / `ignore on` pause and resume them (until reboot). Up to 32 rules; each change is
  a security event, and the `[1s]` line shows `ignored=N` while there are rules. The gateway
  sends the same words, only on `all/cmd`: the list is mast-wide, every scanner ignores the
  same addresses (see [PROTOCOL.md](PROTOCOL.md)). The console works on its own board, for the bench.
  The scanner sends its whole list to the gateway at boot, after each change and on
  `ignore list` (0.7.0+); the gateway publishes it on `<sector>/ignore` and warns when the
  scanners' lists differ.
- `ant` / `ant int` / `ant ext`: show or switch antenna. The choice is saved in flash; a new
  board boots on `int` (onboard).
- `status`: version, whether the image is confirmed, chip ID, boot and flash-mode counts,
  antenna, listening (passive/active), payloads, flash mode (time left, client connected), the
  stream (tick, baud, budget, load level, intervals, payload and trim counts) and gateway command
  counts (ok, bad, for other scanners).
- `scan on|off`: start or stop listening. Buckets keep coming with no RSSI records. Every boot
  starts listening.
- `flash on|off`: enter or leave flash mode (see above).
- `reboot`: restart.
- `chan auto|37|38|39|rot [s]`: primary channels scanned (bench test, not saved,
  every boot is `auto`). `37`-`39` = that channel only; `rot 1` = 37, 38, 39 in turn, changing at
  the 1 s boundary. The controller only takes a new channel map when scanning starts, so each
  change stops and restarts the scan (`switch=` shows how long). `tools/chan_test.py` compares
  the modes.
- `inject <hex>`: feed bytes to the D7 command decoder as if the gateway sent them. Get the hex
  from `python tools/decode_frames.py --cmd "flash on" --id <chip ID>` (no `--id` = all scanners).
- `cmdlog`: the last rejected D7 command frames and why.
- Events print as they happen, e.g. `[SECURITY WARN] flash mode on for 600 s (gateway)` or
  `[WARN] load level 1: payload refresh slowed`.
- `help`: lists all commands, including Zephyr's built-ins (`kernel uptime`, `device list`).

Phones and most tags use random addresses that change every few minutes, so filter on a
fixed-address beacon for antenna tests.

## Gateway stream (header UART)

Protocol 3 since 0.4.0 (it replaces the v2 one-frame-per-second format; a v2 gateway can't read
it). Full spec: [PROTOCOL.md](PROTOCOL.md), schema: [proto/bletracker.proto](proto/bletracker.proto).

- `uart21`: **D6 = TX, D7 = RX**, 115200 8N1, 3.3 V. Each scanner's D6 goes to its own gateway
  RX pin; the gateway's single TX drives every scanner's D7, so commands are addressed by chip ID.
- Every 200 ms one `Bucket` (protobuf + CRC-16 + COBS + 0x00): chip ID, tick seq,
  uptime, channel, load level, then records: events, status (1 s), counters (10 s), RSSI per
  address (every tick: sum, count and max, so the mean is exact), and, once the gateway turns
  them on, changed advert / scan response bytes plus a refresh every 10 s.
- Commands are protobuf too: listen, flash, antenna, reboot, payloads, active scanning,
  intervals, budget, ignore / unignore / ignore clear. Each is acknowledged with an event in the
  next bucket.

The firmware builds its C code from the schema with nanopb (in NCS, `CONFIG_NANOPB`). For the
Python tools, `tools/bletracker_pb2.py` is generated with the toolchain's protoc:

```bash
C:\ncs\toolchains\4f5b6ad6dd\opt\nanopb\generator-bin\protoc.exe -Iproto --python_out=tools proto/bletracker.proto
```

To watch it from a PC, wire D6 to the RX of a 3.3 V USB-serial adapter (and GND), then
(`pip install protobuf pyserial`):

```bash
python tools/decode_frames.py --port COM5
```

Without an adapter, `stream dump` on the console prints one bucket and
`python tools/decode_frames.py --hex log.txt` decodes it.

## Bench tests

1. **Boot:** banner, `rf switch: on, antenna int` (onboard until the pigtails go in), `scanning: ...`; the LED toggles each second.
   One `[1s] ... adverts=N dropped=0` line a second.
2. **Scan:** `print on` shows a line per advert (address, RSSI, PDU type); `print off` to stop.
3. **Antenna switch:** use a beacon with a fixed address (any nRF52 board running a
   beacon sample works) 2-3 m away. `filter AA:BB:CC:DD:EE:FF`, then alternate
   `ant int` / `ant ext` every ~10 s:
   - nothing on the IPEX connector: `ext` should be clearly weaker (10 dB or more) than `int`;
   - antenna on the pigtail: `ext` should match or beat `int`.
   Polarity, measured 2026-10-29 with nothing on IPEX (~37 vs ~13 adverts/s): the board
   devicetree's `rfsw-ctl` regulator enabled = P2.05 low = onboard; disabled = high = external.

`dropped` above 0 means the console can't keep up; leave `print` off.
