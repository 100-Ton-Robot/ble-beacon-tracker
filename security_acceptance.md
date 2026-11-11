# Security acceptance log

Known security gaps that have been reviewed and **accepted** as they are, with the reasons, what
limits them today and what would reopen them. Anything not listed here and found later is
open until it is fixed or added to this log.

Review: input validation across the scanner firmware and the gateway, 2026-11-11. The fixes
from that review are in `CHANGELOG.md` (scanner firmware 0.8.0 and the gateway's Unreleased
section).

| # | Gap | Status | Date |
| --- | --- | --- | --- |
| 1 | MCUboot accepts older signed images (no downgrade prevention) | Accepted | 2026-11-11 |
| 2 | Gateway -> scanner commands on D7 are not authenticated | Accepted | 2026-11-11 |
| 3 | MQTT commands are authorised by the broker login only | Accepted | 2026-11-11 |

## 1. MCUboot downgrade

**Gap.** `scanner_fw/sysbuild.conf` doesn't enable MCUboot's downgrade prevention. Any image
signed with the project's key installs, including an older version with bugs fixed since
(for example the 1 m power wrap fixed in 0.8.0).

**How it could be used.** Flash mode (BLE MCUmgr/SMP, no pairing) has to be open: it opens only
on a command (gateway D7 or USB console) for 10 minutes, or for 2 minutes after an update while
the new image is on trial. Within BLE range during that window, anyone can upload an older
**signed** image. Unsigned or foreign-key images are rejected by MCUboot.

**Why accepted.** An attacker can only install images the owner built and signed. Flash mode is
closed unless someone with gateway or USB access opens it. Every open, connect, version
change and test image is a SECURITY event on `bletracker/<mast>/security`
(`FLASH_MODE_ON`, `CLIENT_CONNECTED`, `VERSION_CHANGED`, `TEST_IMAGE`), so a downgrade can't
happen without leaving a record.

**Reopen if.** Flash mode can be opened without D7 or USB access; old signed images are
published where others can get them (`scanner_fw/release/` holds some: anyone who has the
public repo can obtain them, so this one matters if the repo is public and the boards use
the same key); or a released version has a security fix worth enforcing. The fix is MCUboot's
downgrade prevention (`MCUBOOT_DOWNGRADE_PREVENTION`, with version numbers in the image
header), tested on a board before release.

## 2. D7 commands not authenticated

**Gap.** Commands from the gateway to the scanners on the shared D7 serial line carry only a
CRC-16, which catches corruption, not forgery. Anything that can drive D7 can send any
command: `flash on`, `reboot`, `listen off`, `ignore <addr> save` (hides a device), `debug`, and
so on.

**How it could be used.** Physical access to the mast's wiring, or control of the gateway
(ESP32), which already has full control of the scanners by design.

**Why accepted.** D7 runs inside the sealed mast enclosure between the gateway and its own
scanners. Physical access already allows reflashing over USB or SWD, so a MAC on D7 would add
little. Mitigations in place: every command is acknowledged with an event (`CMD_OK` /
`CMD_REJECTED`); frames that don't decode are counted, and three or more within 10 s raise a
`BAD_COMMANDS` security event; changes that can hide devices or open flash mode
(`SETTING_CHANGED` for the ignore list, `FLASH_MODE_ON`) are SECURITY events; the gateway
compares the scanners' ignore lists and raises `IGNORE_MISMATCH` when they differ.

**Reopen if.** D7 leaves the enclosure (a cable run between boxes, a connector reachable from
outside), or something other than the gateway shares the line.

## 3. MQTT commands authorised by the broker login

**Gap.** The gateway acts on any command published to `bletracker/<mast>/cmd`,
`bletracker/<mast>/<sector>/cmd` or `bletracker/<mast>/all/cmd`. Who may publish there is up
to the MQTT broker. The gateway's MQTT connection doesn't use TLS.

**Why accepted.** Clients must log in to the broker (each gateway uses its own credentials from
`secrets.yaml`), and the broker is on a trusted LAN. Gateway-side checks limit what a command
can be (fixed words, ranges, ASCII only, 128 characters at most) and every command is
acknowledged on `events`.

**Reopen if.** The broker is shared with clients that shouldn't command the masts (then add
broker ACLs on the `cmd` topics), or the MQTT traffic leaves the trusted LAN (then add TLS).
