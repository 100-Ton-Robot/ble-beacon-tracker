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
- Mast builds: `builds/pcb/` (KiCad boards from `make_pcbs.py`) and `builds/hand/` (templates and
  copper deck from `make_templates.py`, `make_shield_deck.py`; needs `reportlab`). Every number lives
  in exactly one CSV: `common/parameters.csv` (shared geometry, read by `common/layout.py`) or the
  build's own `parameters.csv`; `common/params.py` loads common + one build (`load(build=...)`) and
  refuses a name in two files. Change values there, not in the scripts; regenerate rather than
  hand-edit outputs. Plate layouts round-trip through Inkscape: `make_plate_svg.py` -> edit ->
  `read_plate_svg.py` (writes `builds/hand/parameters.csv`, checks rules). `shield_deck/README.md`
  only points to the new folders.
- Docs take their numbers from the parameter CSVs, unless there is a reason not to (a measured result, a part's
  datasheet value used once): generate them where practical (e.g. `docs/make_antenna_doc.py` writes
  `docs/ANTENNA_SELECTION.md` from `parameters.csv`, `common/layout.py` and the RF runs), and name the parameter
  beside any number written by hand. A part spec several docs use goes in `parameters.csv`.
- `boards/`: module boards either build can use (`carrier/`, `radio3/`, `led/`, each with its own
  `parameters.csv`, loaded with `params.load(boards=[...])`) and `lib/kicad_lib.py`, the KiCad
  helpers every board generator shares, `builds/pcb/make_pcbs.py` included.
- Open work is in GitHub issues (conventions in `NEXT_STEPS.md`): check them before starting,
  comment or close them with the work.
- **This repo is public.** No private data, locations or home context anywhere: files, commit
  messages, issues, PRs. No place or room names (mast IDs are location names), IPs, hostnames,
  real chip IDs or BLE addresses, home security settings or anyone's schedule. Examples use
  made-up values (`mast1`, `AA:BB:CC:DD:EE:FF`, `a1b2c3d4e5f60718`). Work on a particular
  installation is tracked outside this repo.
- Never commit `secrets.yaml`, signing keys or personal notes (`*.local.md` is ignored).
