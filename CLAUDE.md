# BLE Beacon Tracker (DIY)

Passive BLE beacon locator: 3 XIAO nRF54L15 scanners behind directional antennas facing out 120 deg
apart, RSSI sector comparison for bearing plus RSSI range, gateway on an ESP32-S3 (ESPHome), tracker
in Home Assistant. See `README.md` and each folder's README.

- `scanner_fw/`: nRF Connect SDK / Zephyr app, board `xiao_nrf54l15/nrf54l15/cpuapp`, behind MCUboot.
  Sysbuild breaks on paths with spaces: build through a space-free path. The board's stock OpenOCD
  load loses the image tail; `CMakeLists.txt` swaps in `support/scanner-load.tcl`. The signing key
  stays outside the repo (`*.pem` is ignored).
- `gateway/`: ESPHome package `packages/bletracker-gateway.yaml`, per-mast `example-mast.yaml`
  and external component `components/sector_scanner/`. Frame and command
  formats are defined in `scanner_fw/README.md`; keep both sides in step.
- `shield_deck/`: every number lives in `parameters.csv` (loaded by `params.py`); change values there,
  not in the scripts. Regenerate Gerbers and templates from `make_shield_deck.py` and
  `make_templates.py` (needs `reportlab`) rather than hand-editing outputs. Plate layouts round-trip
  through Inkscape: `make_plate_svg.py` -> edit -> `read_plate_svg.py` (writes the CSV, checks rules).
- Open work is in GitHub issues (conventions in `NEXT_STEPS.md`): check them before starting,
  comment or close them with the work.
- **This repo is public.** No private data, locations or home context anywhere: files, commit
  messages, issues, PRs. No place or room names (mast IDs are location names), IPs, hostnames,
  real chip IDs or BLE addresses, home security settings or anyone's schedule. Examples use
  made-up values (`mast1`, `AA:BB:CC:DD:EE:FF`, `a1b2c3d4e5f60718`). Work on a particular
  installation is tracked outside this repo.
- Never commit `secrets.yaml`, signing keys or personal notes (`*.local.md` is ignored).
