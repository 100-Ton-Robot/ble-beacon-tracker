# Changelog

Scanner firmware versions come from `scanner_fw/VERSION`; the gateway and the shield deck have no
version numbers yet. All versions below were made between 2026-10-29 and 2026-10-31; dates are
when the image was built, where known.

## Unreleased

### Gateway

Needs scanner firmware **0.3.0 or later**: v1 frames are dropped as bad.

- Changed: reads frame v2 only (16-byte header with `chip_id`).
- Added: learns each RX pin's chip ID (`chip` in the JSON, a chip text sensor per sector) and
  sets the scanner's sector to its pin's (command 4, addressed, at most every 5 s).
- Added: one shared command TX (GPIO21) to every scanner's D7. Addressed v2 commands come from
  MQTT `bletracker/<mast>/<sector>/cmd` and `bletracker/<mast>/all/cmd` (`listen`, `flash`,
  `ant`, `reboot`). Each sector gets Home Assistant buttons for flash mode and reboot.
- Added: JSON fields `scanner_sector`, `listening`, `flash`, `client`, `test_image`.
- Changed: pins are RX GPIO17/16/18 (header 34/32/31) and TX GPIO21 (35). GPIO1 and GPIO2 are
  free now.
- Changed: Home Assistant entities come over the ESPHome API and MQTT discovery is off. MQTT
  carries only beacon data and commands.
- Changed: the `api_key` secret (used for both API and OTA) replaces `ota_key`. The `mast`
  substitution names the device.
- Changed: the config is split into `packages/bletracker-gateway.yaml` (shared by every mast)
  and a per-mast file (`example-mast.yaml`). `bletracker-gateway.yaml` is no longer a device
  config on its own.

### Docs

- READMEs match gateway v2. Notes that only applied to one PC were made general. This changelog
  was added.

## Scanner firmware

### 0.3.0 (2026-10-31)

Breaking: a gateway from before this version can't read these frames, and its commands are
rejected.

- Frame v2: the header grows from 8 to 16 bytes and adds `chip_id` (the nRF FICR device ID).
- Commands v2: 13 bytes with an 8-byte `target` chip ID (all zeros = every scanner).
  v1 commands (5 bytes) are rejected as the wrong length. A sector command can't go to all
  scanners.
- Wiring: each scanner's D6 has its own gateway RX pin (that pin gives the sector), and one
  gateway TX drives every scanner's D7.
- The gateway assigns the sector (command 4); scanners need no manual sector setup.
- Image: `scanner_fw/release/scanner_fw-0.3.0-dfu.zip`.

### 0.2.4

- Flash mode opens only on a serial command (gateway `flash on` or the USB console). A normal
  boot no longer opens it. A test image after an update still opens it for 2 minutes.
- No image in `scanner_fw/release/`.

### 0.2.3 (2026-10-30)

- Image: `scanner_fw/release/scanner_fw-0.2.3-dfu.zip`.

### 0.2.2 (2026-10-30)

- Image: `scanner_fw/release/scanner_fw-0.2.2-dfu.zip`.
- Known issue: the image in this zip is signed with MCUboot version `0.2.1+0`, not `0.2.2`, so
  `status` and the update app show 0.2.1 after installing it.

### 0.2.1 (2026-10-30)

- Used to check MCUboot test boot, revert and confirm on hardware, updating from 0.2.0.

### 0.2.0

- Frame header flags bits 2-5: listening off, flash mode, update client connected, test image
  (not yet confirmed). A v0.1 reader ignores them.
