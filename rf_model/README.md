# RF model of a sector and bearing simulation

`sector_model.py` simulates one sector of the mast with [openEMS](https://openems.de) (free, open-source FDTD).
It builds the copper deck, the triangular core and the antennas at the three D holes from
`../shield_deck/parameters.csv`, so the model follows the deck when you change it there. It feeds sector 0's
antenna and ends the other two sectors' antennas in 50 ohm, the way their radios do.

What you get, in `out/<antenna>/`:

| File | What |
| --- | --- |
| `summary.txt` | Match (S11 and impedance at 2402 / 2440 / 2480 MHz), peak gain, -3 dB beamwidth and front-to-back at several elevations, isolation to the other two sectors |
| `pattern.csv` | Directivity in dBi on a 5 deg grid: `az_deg` clockwise from S0's face normal seen from above (the deck's convention), `el_deg` from the horizon, negative below the deck. Sectors 1 and 2 are the same pattern turned by +120 / +240 deg. |
| `pattern.png` | Azimuth cuts at el 0, -15, -30 and -45 deg |
| `s11.png` | Match across the BLE band |
| `model.xml` | The geometry; open it in AppCSXCAD to check it |

## Setup (Docker)

There's no ready-made openEMS package or image to rely on, so the `Dockerfile` here builds openEMS (tag
`v0.37.0`, no GUI) and its Python bindings from the official source. Start Docker Desktop, then from the project
folder (the first build takes 20-30 min):

```bash
docker build -t bletracker-openems rf_model
```

## Run

From the project folder (in PowerShell, `${PWD}` instead of `$(pwd)`):

```bash
docker run --rm -v "$(pwd):/work" -w /work/rf_model bletracker-openems python3 sector_model.py --antenna monopole --coarse
```

On Linux with openEMS installed, `python3 sector_model.py ...` runs it directly.

- `--antenna monopole`: a quarter-wave whip straight down from the D jack, the deck as its ground plane.
- `--antenna dipole`: a rubber duck as a vertical half-wave dipole; `--centre` sets its feed point's depth below
  the deck (default 45 mm).
- `--length` sets the element length (default 0.95 x a quarter or half wavelength at `RF_FREQ`).
- `--single` leaves out the other two sectors' antennas.
- `--coarse` uses a coarser mesh for a quick check. On a 12-core PC the coarse run takes about 10 s and the full
  one about 20 s of solver time; the two agreed within about 0.5 dB on the monopole.

## First result: quarter-wave monopoles (2026-11-12, full mesh)

From `out/monopole/summary.txt`:

- Match: S11 -14.6 / -12.6 / -11.0 dB at 2402 / 2440 / 2480 MHz (Zin about 65-71 + 16-28j ohm): fine for a
  receiver. S11 still falls below 2300 MHz (-22 dB there), so the whip resonates below the band next to the core;
  a shorter one (`--length`) would centre it.
- Beam: peak 4.9 dBi about 35 deg below the horizon, straight out from the face. The -3 dB width is 125-155 deg
  depending on elevation, wider than the 120 deg sector, so neighbouring sectors overlap and can be compared.
- Back: about 10-12 dB weaker behind than in front at most elevations (the single-angle front-to-back figures jump
  where a null lands on az 180, like the 48 dB at el -30).
- Isolation: -29 dB from sector 0's whip to each of the others.

## Rubber duck (sleeve dipole) (2026-11-12, full mesh)

Most 2 dBi ducks are half-wave sleeve dipoles; `--antenna dipole` models one as a centre-fed 58 mm wire with its
feed 45 mm below the deck, so it runs from 16 to 74 mm down, beside the face. From `out/dipole/summary.txt`:

- Beam: peak 7.5 dBi at the horizon, -3 dB width 105-125 deg down to el -30, then it fades below about el -45
  (the deck and core sit above and behind it). Narrower than the monopole and a better fit to 120 deg sectors.
- Back: 15-22 dB weaker behind down to el -30.
- Isolation: -51 dB to each of the other sectors.
- Match: S11 about -5 dB, but that's the model's bare centre feed, not a real duck (which has its own sleeve
  match). A 50 mm element gives about -9 dB with the same pattern within 0.2 dB and the same bearing result
  within 1 deg, so the pattern doesn't depend on it.

## Bearing simulation

`bearing_sim.py` takes one or more `pattern.csv` folders, places 4000 beacons at random bearings 1-15 m out with
the mast 1.4 m above them, adds BLE noise and works the bearing back out the way the tracker could: it fits the
three sectors' RSSI differences to the pattern (so transmit power and path loss cancel). Range comes from the
strongest sector, its fitted gain and a log-distance model. It needs only numpy and matplotlib:

```bash
docker run --rm -v "$(pwd):/work" -w /work/rf_model bletracker-openems python3 bearing_sim.py out/monopole out/dipole
```

Noise (dB, all settable): `--fading` per advert (5), `--adverts` per second per sector on the compared channel
(3), `--room` per-sector reflections fixed for a place, which don't average out (3), `--shadow` common to all
sectors, moving range only (4), `--window` seconds the tracker averages (1). These are typical indoor BLE values,
not measured here; the RSSI walk should replace them.

Results in `out/bearing/` (`summary.txt`, `error_vs_bearing.png`, `estimate_vs_true.png`, `errors_<pattern>.csv`).
With the defaults:

| Antenna | Median bearing error | 90% within | Strongest sector right | Median range error |
| --- | --- | --- | --- | --- |
| monopole | 34 deg | 101 deg | 67% | 45% |
| rubber duck | 21 deg | 65 deg | 77% | 45% |

Median bearing error as the room's reflections and the tracker's averaging change:

| Room reflections | Window | Monopole | Duck |
| --- | --- | --- | --- |
| 0 dB | 1 s | 27 | 17 |
| 0 dB | 5 s | 13 | 7 |
| 3 dB | 1 s | 35 | 22 |
| 3 dB | 5 s | 29 | 17 |
| 5 dB | 5 s | 40 | 27 |

What it shows:

- The ducks' narrower beam cuts the monopoles' error by about a third to a half under the same noise.
- The error is smallest at the edges between sectors (about 12-17 deg) and largest in the middle of a sector,
  where the sector differences change slowly with bearing.
- Averaging over time beats fading down, but not the room's fixed reflections: with 3 dB of those, 5 s only takes
  the duck from 22 to 17 deg. Getting below that needs other information (the ESPHome proxies, a calibration walk
  that measures each place's offsets, or movement over time).
- Range is limited by shadowing, not the antenna: 4 dB of it is about 45% off on distance either way.

## Antenna specs (spec sweep)

`spec_sweep.py` runs idealised sector beams through the bearing simulation: each has a set -3 dB beamwidth and a
floor, how far the whole back of the beam sits below the front. It also measures the real patterns' back levels so
they can be read against the same tables. Results in `out/spec_sweep/summary.txt`:

```bash
docker run --rm -v "$(pwd):/work" -w /work/rf_model bletracker-openems python3 spec_sweep.py out/monopole out/dipole
```

Median bearing error (deg), default noise (room 3 dB, 1 s):

| Beamwidth | Floor 6 dB | 10 dB | 15 dB | 20 dB | 30 dB |
| --- | --- | --- | --- | --- | --- |
| 80 deg | 46 | 32 | 20 | 14 | 8 |
| 100 deg | 43 | 28 | 18 | 13 | 9 |
| 120 deg | 42 | 27 | 18 | 14 | 10 |
| 160 deg | 44 | 30 | 21 | 17 | 13 |

- The floor behind the beam matters most. The beamwidth matters less: 80-140 deg are all near the best (13-15 deg
  at a 20 dB floor), narrower beams pick the right sector more often but leave weak gaps between sectors, wider ones
  blur the sectors together.
- The real patterns fit the tables: the monopole's back third is only about 5 dB below its front (it simulates at
  34 deg, between the 6 and 10 dB columns); the duck's is 10-14 dB below near the horizon but only 1-5 dB below at
  el -45 to -55 (21 deg, the 10-15 dB columns). The single-angle front-to-back in `summary.txt` overstates both.

Recommended specs for the indoor, ceiling-hung mast:

| Spec | Target |
| --- | --- |
| Back rejection | Everything from az 120 to 240 at least 20 dB below the front (25-30 dB better) |
| Horizontal -3 dB beamwidth | 90-120 deg (80-140 deg acceptable) |
| Vertical coverage | Front gain within about 6 dB of the peak from the horizon down to el -55 (beacons 1-15 m out, 1.4 m below) |
| Gain | About 7-10 dBi, which follows from the beamwidth; not critical on its own |
| Match | S11 below -10 dB (VSWR < 2) across 2402-2480 MHz |
| Matching between sectors | Three of the same antenna, or calibrated per sector: a gain difference acts like a fixed room reflection |
| Polarisation | Vertical, the same on all three (convention, not from this data) |
| Fit | RP-SMA plug, at most about 170 mm below the deck and 12 mm across at the D holes |

Reference antenna for the first tests: the HiRO H50327, a 2 dBi dual-band (2.4 / 5 GHz) dipole, RP-SMA, 108 mm
long, 10 mm across, VSWR <= 1.92, swivelling 90 deg (set straight in the D hole). It's the `--antenna dipole` case
and stays within the 120 mm faces. Its own pattern isn't published, so compare it with `out/dipole` in the RSSI walk.

Against these, the monopoles miss on back rejection, and the ducks are close on beamwidth but 6-10 dB short on
back rejection and weak looking steeply down. The printed-dipole panels (dipole over a reflector) are the likeliest
to meet the specs; modelling them, or deepening the core behind the ducks, are the next things to try. Even a
30 dB floor leaves a median of about 7-10 deg under room reflections; beyond that it's calibration and the proxies.


## Reference antenna: HiRO H50327 (2026-11-12)

The H50327 is 108 mm long, of which the swivel and connector take about 20-25 mm, so its 2.4 GHz element sits
somewhere 25-105 mm below the deck; the maker doesn't say where. `run_all.sh` brackets it with the dipole's feed
55, 65 and 75 mm below the deck (`out/h50327_c55`, `_c65`, `_c75`), all inside the 120 mm faces:

| Feed depth | Peak | -3 dB width at el 0 / -30 | Gain at el -45 | Isolation | Median bearing error | 90% within |
| --- | --- | --- | --- | --- | --- | --- |
| 55 mm | 7.9 dBi | 95 / 125 deg | -2.5 dBi | -47 dB | 22 deg | 109 deg |
| 65 mm | 8.0 dBi | 95 / 125 deg | -1.2 dBi | -45 dB | 20 deg | 63 deg |
| 75 mm | 7.8 dBi | 95 / 115 deg | +1.1 dBi | -43 dB | 19 deg | 56 deg |

- Where the element sits barely moves the median (19-22 deg, the same as the generic duck's 21 deg): expect about
  20 deg in the first tests with the default noise.
- Lower is slightly better: more gain looking steeply down, so close beacons fare better. At 55 mm the beam picks
  up more from behind than in front at el -60, which gives the 109 deg tail (close beacons put on the wrong side).
- The model's match (S11 about -4 dB) is its bare centre feed, not the antenna's: the maker gives VSWR <= 1.92.
- What the specs can't give (the element's real position and pattern) the RSSI walk should: compare the measured
  sector differences with these three cases.

## Every simulation run

All runs are kept. `run_all.sh` holds every run behind this README, in order, and re-runs the lot in about 4 min:

```bash
docker run --rm -v "$(pwd):/work" -w /work/rf_model bletracker-openems sh run_all.sh
```

Each run writes its own folder under `out/`; its `summary.txt` starts with the command and date, and
`out/runs.csv` gets a row (date, script, folder, command, one-line result). Add new runs to `run_all.sh`, not
only on the command line. Re-running all of them on 2026-11-12 reproduced the earlier results within 0.1 dB and
1 deg (multi-threaded rounding).

| Folder | What | Key result |
| --- | --- | --- |
| `out/monopole_coarse` | Quarter-wave whip, coarse mesh | Mesh check: within 0.5 dB of the full mesh |
| `out/monopole` | Quarter-wave whip (29.2 mm) at the D hole | 4.9 dBi at el -35, 125-155 deg, -29 dB isolation |
| `out/dipole` | Sleeve-dipole duck (58.4 mm, feed 45 mm down) | 7.5 dBi at the horizon, 105-125 deg, -51 dB isolation |
| `out/dipole_len50` | Same duck, 50 mm element | Match changes, pattern doesn't (within 0.2 dB) |
| `out/h50327_c55`, `_c65`, `_c75` | HiRO H50327, feed 55 / 65 / 75 mm down | 7.8-8.0 dBi, 95 deg wide at the horizon |
| `out/bearing` | Bearing sim: monopole vs duck | Median 34 vs 21 deg |
| `out/bearing_h50327` | Bearing sim: duck vs the three H50327 cases | Median 19-22 deg |
| `out/spec_sweep` | Idealised beams: beamwidth x back floor x noise | Back rejection matters most; specs above |

## Limits

Not modelled: the enclosure, the electronics plate and its parts, the coax runs, the bolts and spacers, the
printed-dipole panels and the DIY dipoles. The core is a solid copper prism (only its outside affects the pattern),
and the whips are thin wires. Treat the results as how the deck and core shape the beam, not as exact gains, and
check them against an RSSI walk.
