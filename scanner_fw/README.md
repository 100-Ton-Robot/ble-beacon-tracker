# Sector scanner firmware (XIAO nRF54L15)

nRF Connect SDK (Zephyr) app behind MCUboot. It does a passive scan, controls the RF switch and
groups adverts per device each second. Once a second it sends a binary frame on the header UART
for the gateway. The gateway sends commands back on the same UART: listen on/off, flash mode,
antenna and sector. Each scanner's TX (D6) has its own gateway RX pin, which is how the gateway
knows the sector; the gateway's one TX drives all three scanners' RX (D7) through the bus board,
so commands are addressed by chip ID. In flash mode the scanner takes signed firmware updates
over BLE, so it can be updated with the box sealed. The sector ID and antenna choice are kept in flash.

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
the build in deep folders. Built clean on 2026-10-29 with NCS v3.4.0: 103 KB flash, 26 KB RAM.

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

No sector setup is needed: the gateway learns each scanner's chip ID from the RX pin its frames
arrive on and sends it its sector (cmd 4). It is saved in flash and shows in the frame header and
the flash-mode BLE name. On the bench without a gateway, `sector 0|1|2` on the console does the same.

The app's version comes from `VERSION`. Bump it for every release so `status` and the update app
show which image is running.

## Updating over BLE (box sealed)

1. **Turn on flash mode.** Only a serial command opens it: `flash on` from the gateway on D7
   (the "Sector <n> flash mode" button in Home Assistant, or MQTT, see `../gateway/README.md`),
   or `flash on` on the USB console. A normal boot does not (since v0.2.4), so a power cycle won't
   help if the gateway can't send the command. The scanner then advertises as
   `bletracker-s<sector>`.
   - Scanning carries on throughout.
   - Exception: a test image just after an update opens flash mode for 2 minutes. The
     self-check needs to see advertising work, and the uploading app can reconnect.
   - Each `flash on` gives 10 minutes. The timer only runs while no client is connected.
   - `flash off` ends it at once and drops any connection.
2. **Upload the new image.** Either way works:
   - Phone: **nRF Connect Device Manager** (Nordic, iOS/Android). Pick `bletracker-s<n>`, then
     Image -> Firmware Upgrade -> `dfu_application.zip`, mode "Test Only" (the scanner's own
     60 s check then decides; "Test and Confirm" would let the app confirm it instead).
   - PC with Bluetooth LE: `pip install smpmgr` (a venv is fine), then the command below.
     Not every adapter works: if bleak reports no BLE central role, use the phone app.

     ```bash
     smpmgr --ble bletracker-s0 upgrade build/scanner_fw/zephyr/zephyr.signed.bin
     ```

3. **The scanner reboots into the new image as a test.** MCUboot swaps it in. If the new image
   runs for 60 s with scanning and flash-mode advertising working, it confirms itself (`image
   confirmed` on the console; header flag bit5 clears). If it crashes or hangs before then, the
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
`--slot-size` and the `0xC2000` load address must match the board's devicetree partitions. On reset,
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

What you see and type:
- Every second: `[1s] ant=int adverts=37 devices=12 dropped=0` = adverts and distinct
  addresses heard in that second.
- `print on`: one line per advert, e.g. `C1:7D:2B:AC:03:BC (random) rssi=-48 type=0`.
  `type` is the advert type: 0 connectable, 1 directed, 2 scannable, 3 non-connectable
  (most beacons), 4 scan response, 5 extended. `print off` to stop; it scrolls fast.
- `list on`: a table each second, one row per device heard in that second, strongest first:
  `address type med max n tx1m adv` = median and max RSSI (dBm), adverts that second,
  advertised 1 m power (iBeacon, or Eddystone UID/URL 0 m power minus 41; blank if none),
  advert type. Up to 64 devices; the median uses that second's last 32 adverts.
  `minrssi -80` hides weaker devices (`minrssi -127` shows all). `list off` to stop.
- `list csv`: the same data in the gateway line format
  `sector_id,address,addr_type,rssi_med,rssi_max,count,tx_1m` (sector_id is 0 until it's stored
  in flash).
- `stream`: gateway frame stats (sent, skipped, seq). `stream dump`: prints the next frame's
  bytes in hex; `python tools/decode_frames.py --hex dump.txt` decodes a saved console log.
- `filter C1:7D:2B:AC:03:BC`: track one device; prints `n`, mean, min and max RSSI each second.
  `filter off` to go back.
- `ant` / `ant int` / `ant ext`: show or switch antenna. The choice is saved in flash; a new
  board boots on `int` (onboard).
- `status`: version, whether the image is confirmed, chip ID, sector, antenna, listening, flash
  mode (time left, client connected) and gateway command counts (ok, bad, for other scanners).
- `sector` / `sector 2`: show or set the sector ID (0-254, saved in flash). It goes in every
  frame header and in the flash-mode BLE name.
- `scan on|off`: start or stop listening. Frames keep coming with no devices and header flag bit2
  set. Every boot starts listening.
- `flash on|off`: enter or leave flash mode (see above).
- `reboot`: restart.
- `inject <hex>`: feed bytes to the D7 command decoder as if the gateway sent them. Get the hex
  from `python tools/decode_frames.py --cmd "flash on" --id <chip ID>` (no `--id` = all scanners).
- `help`: lists all commands, including Zephyr's built-ins (`kernel uptime`, `device list`).

Phones and most tags use random addresses that change every few minutes, so filter on a
fixed-address beacon for antenna tests.

## Gateway stream (header UART)

Each second the scanner sends one binary frame of that second's per-device table on `uart21`:
**D6 = TX, D7 = RX** (commands from the gateway, below), 115200 8N1, 3.3 V.

Wiring (since v0.3.0): each scanner's D6 goes to its own gateway RX pin, and the gateway takes
the sector from that pin. The gateway's single TX drives every scanner's D7 (bus-board row 1), so
all scanners hear every command and each one acts only on commands for its chip ID.

The USB console is separate and unchanged. Every device heard is sent, strongest median first (`minrssi` only trims
the console list).

- Frames are COBS-encoded, so a frame never contains 0x00, and each is followed by a 0x00
  delimiter. Little-endian.
- Header, 16 bytes: `ver` (2), `sector`, `seq` (+1 per second, wraps; a gap = lost frame),
  `flags`, `adverts` (u16), `n_devs`, `dropped`, `chip_id` (8 bytes: the nRF FICR device ID from
  Zephyr's `hwinfo_get_device_id()`, sent and printed in the same byte order).
  - v1 (before 0.3.0) had the same first 8 bytes and no `chip_id`.
  - `flags`: bit0 external antenna, bit1 table full, bit2 listening off, bit3 flash mode,
    bit4 update client connected, bit5 test image (not confirmed yet).
  - Bits 2-5 were added in v0.2.0. A v0.1 reader just ignores them.
- Record, 11 bytes each: address (6 bytes, most significant first, as printed), `flags`
  (bit0 random address, bits1-3 advert type, bit4 tx_1m valid), `rssi_med`, `rssi_max`
  (int8 dBm), `count` (adverts that second, max 255), `tx_1m` (int8, 0 when not valid).
- CRC, 2 bytes: CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, check "123456789" = 0x29B1) of
  header + records. The receiver drops any frame whose CRC or length doesn't match.

Size: 16 + 11 x devices + 2, plus about 1 byte in 254 for COBS. 64 devices = about 720 bytes,
roughly 60 ms of each second at 115200.

To watch it from a PC, wire D6 to the RX of a 3.3 V USB-serial adapter (and GND), then:

```bash
python tools/decode_frames.py --port COM5
```

### Commands (gateway -> scanner, D7)

Commands use the same framing as frames: COBS, a 0x00 after each, and CRC-16/CCITT-FALSE. Each
decodes to 13 bytes: `ver` (2), `target` (8 bytes), `cmd`, `arg`, then the CRC (LE) of the first 11.
`target` is a chip ID from a frame header, or all zeros for every scanner. Sector can't go to all
(it would give every scanner the same sector). A valid command for another chip ID is ignored and
counted as "for others" in `status`. v1 commands (5 bytes, no target) are rejected as wrong length.

| cmd | meaning | arg |
| --- | --- | --- |
| 1 | listen | 0 stop, 1 start |
| 2 | flash mode | 0 leave, 1 enter (10 min, extended by each enter) |
| 3 | antenna (saved) | 0 onboard, 1 external |
| 4 | sector (saved) | 0-254 |
| 5 | reboot | 0xA5 (anything else is rejected) |

There is no reply: the result shows in the next frame's header (sector byte, flags bits 0, 2, 3).
Frames with a bad CRC, an unknown command or a bad argument are counted as bad (`status`) and
ignored.

`python tools/decode_frames.py --cmd "flash on" --id 1a2b3c4d5e6f7081` prints a command's bytes
for `inject`. With `--port COM5` (adapter TX wired to D7) it sends them.

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
