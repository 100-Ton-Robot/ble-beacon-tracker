# Next steps

Shared to-do list for everyone working on this repo (Aaron and each Claude session). Pull before
you read it, edit only your own lines where you can, and commit it with the work that changes it.
Done items move to `CHANGELOG.md`, not here. To move to GitHub issues once a token can reach them.

Owners: **Aaron** (hands-on: wiring, flashing over USB, buying parts, decisions), **gateway**
(ESPHome session on the Home Assistant host), **scanner** (scanner_fw session), **any**.

## Scanner firmware 0.8.0 rollout

Aaron solders the harness on 2026-11-21. Order matters: the gateway goes last, or 0.7.0 radios raise `FIRMWARE_OUTDATED` every 10 min.

- [ ] **Aaron**: move each XIAO's harness wire from D6 to D8 (gateway end unchanged). A 0.8.0 board
  sends nothing on D6. Doc: `shield_deck/shield_deck_templates.pdf` page 6.
- [ ] **Aaron / scanner**: DFU `scanner_fw/release/scanner_fw-0.8.0-dfu.zip` to all three radios
  (built 2026-11-19, never run on hardware). Doc: `scanner_fw/README.md`.
- [ ] **gateway**: OTA the garage gateway with `scanner_firmware` 0.8.0 (commit 9fa1848, compiled
  2026-11-19); expect `PASS: commands 26/26, messages 23/23` and every sector's firmware at 0.8.0
  with no "outdated" problem. Doc: `gateway/README.md`.
- [ ] **any**: try `debug tx1m on` on `all/cmd` and check `<sector>/debug/tx_1m` against real
  beacons. Doc: `scanner_fw/PROTOCOL.md`.

## Gateway

- [ ] **gateway**: MQTT TLS to EMQX (8883) is in the build but has not been confirmed live.
  Doc: `gateway/README.md`.
- [ ] **Aaron**: MQTT ACLs on EMQX ("later"). Doc: `gateway/README.md`.

## LED direction ring (feasibility)

Hardware drawn (templates page 7); no firmware yet. Open decisions, all **Aaron**:

- [ ] What the calibration matrix holds and how it reaches the mast.
- [ ] Bearing only, or range / position too.
- [ ] Which signals (beacons) the ring points at.
- [ ] Power layout: separate bus board + LED power board (pages 6-7) or the unified power + LED
  board (page 8, 74HCT125 level shifter, one-time 2 A fuse).
- [ ] Confirm the pixel count (24 = 127 mm at 60/m) and data pin (GPIO1); both were the gateway
  session's picks, not decisions.

Doc: `shield_deck/README.md`, `shield_deck/shield_deck_templates.pdf` pages 7-8.

## Repo housekeeping

- [ ] **Aaron**: delete the merged cloud branch `claude/kind-faraday-9j0jyv`
  (`git push origin --delete claude/kind-faraday-9j0jyv`); it has no commits that `dev` lacks.
- [ ] **Aaron**: GitHub token for issues on this repo (100-Ton-Robot org needs lifetime <= 366
  days; Issues read/write + Contents read), then move this list into issues.
