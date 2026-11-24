# RF model of a sector and bearing simulation

Antenna and spacing choice, summarised from these runs: [`../docs/ANTENNA_SELECTION.md`](../docs/ANTENNA_SELECTION.md) (rerun `docs/make_antenna_doc.py` after new runs).

`sector_model.py` simulates one sector of the mast with [openEMS](https://openems.de) (free, open-source FDTD).
It builds the copper deck, the triangular core and the antennas at the three D holes from
the parameter files (`../common/parameters.csv` plus one build's own: `--build hand`, the default, is the
hand build's plain `DISC_DIAMETER` disc; `--build pcb` the rev 3 PCBs, see below), so the model follows the deck
when you change it there. It feeds sector 0's
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
  the deck (default `RF_FEED_DEPTH`, 45 mm; the H50327 runs use `DUCK_FEED_DEPTH`, 65 mm).
- `--spacing` moves the antennas in or out from the faces (default `DUCK_SPACING`, 31 mm: the D hole).
- `--length` sets the element length (default 0.95 x a quarter or half wavelength at `RF_FREQ`).
- `--single` leaves out the other sectors' antennas.
- `--sectors N` builds an N-sided core with N sectors 360/N apart (default `RF_SECTORS`, 3).
- `--build pcb|hand` picks the mast: `hand` (the default without `--deck`) is a plain copper disc of
  `DISC_DIAMETER` with the antennas `DUCK_SPACING` out; `pcb` (the default with `--deck`) is the rev 3 deck,
  `--deck d15` unless another is given. Each reads `../common/parameters.csv` plus `../builds/<build>/parameters.csv`.
- `--set NAME=VALUE` overrides any value in those files for this run only (repeatable), e.g.
  `--set FACE_WIDTH=80 --set DISC_DIAMETER=125`. Every dimension the model uses comes from them; the
  logged command carries the overrides, so it reproduces the run.
- `--end-plate` adds the end plate (`ENDPLATE_DIAMETER`) across the far end of the core.
- `--fine` uses a finer mesh (0.5 mm at the antenna, lambda/32 elsewhere) for convergence checks.
- Each run also writes `meta.json` (sectors, face size, deck and end plate, spacing, feed, overrides);
  `bearing_sim.py` takes the sector count from it.
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

## D-hole spacing (2026-11-12)

Is 31 mm (`DUCK_SPACING`, about a quarter wave) in front of the face the best spot? The H50327 (feed 65 mm down)
moved in and out with `--spacing`; 34 mm is as far out as a 6.5 mm hole fits on the 146 mm deck:

| Spacing | Peak | -3 dB width at el 0 | Back third vs front, el 0 / -30 | Median bearing error | Model feed Zin |
| --- | --- | --- | --- | --- | --- |
| 15 mm | 8.8 dBi | 85 deg | -17.0 / -14.0 dB | 19 deg | 42 + 105j ohm |
| 20 mm | 8.6 dBi | 85 deg | -16.4 / -13.4 dB | 19 deg | 69 + 115j ohm |
| 25 mm | 8.4 dBi | 85 deg | -15.8 / -12.7 dB | 19 deg | 94 + 112j ohm |
| 31 mm (D hole) | 8.0 dBi | 95 deg | -14.8 / -11.3 dB | 20 deg | 116 + 96j ohm |
| 34 mm | 7.7 dBi | 105 deg | -14.3 / -10.7 dB | 21 deg | 123 + 85j ohm |

- Closer to the copper gives a little more gain and back rejection (about 2-3 dB from 34 to 15 mm), but only about
  1-2 deg of bearing: the room's reflections still dominate. 31 mm is not the optimum, but it's within 1 deg of it.
- Closer also moves the antenna's impedance a long way (the model feed's resistance falls from 116 to 42 ohm).
  The H50327's own match is designed for open air, so very close in it would be detuned and lose signal; the
  model can't show how much, as it doesn't include the antenna's internal match.
- So keep the D hole at 31 mm for the first tests. If the deck is redone, 20-25 mm is a reasonable step in, after
  checking the real match there (NanoVNA or the RSSI walk). The reflector's shape (wider faces, wings) is still the
  bigger lever.

## Mast size, sector count and end plate (2026-11-23)

How small can the mast get, and do a fourth sector or an end plate help? `size_sweep.py` runs one
`sector_model.py` per geometry with `--set` overrides (face size, deck, end plate), then scores it with the bearing
simulation (default noise) and the back-level measure from `spec_sweep.py`. Each sweep writes `summary.txt` and
`summary.csv` in its `out/size*/` folder.

Every dimension comes from `../common/parameters.csv` and `../builds/hand/parameters.csv` (each run is `--build hand`, a plain disc):

- Deck: the rev 3 rule (`../common/layout.py`) scaled to the core: the larger of the D hole's exposed
  pad + `DECK_EDGE_MARGIN`, and the core's corners + the margin `DECK_MIN_DIAMETER` leaves past today's corners
  (2.7 mm).
- End plate: the core's corners + the margin `ENDPLATE_DIAMETER` leaves past today's corners (2.7 mm).
- Elements: `h50327`, the reference duck fed `DUCK_FEED_DEPTH` (65 mm) below the deck; `short`, a
  `CHIP_STANDIN_LENGTH` (20 mm) dipole at mid face height, a pattern stand-in for a chip antenna (its match and
  carrier ground are not modelled); `dipole`, a half-wave dipole at mid face height.

Checks: the ported model reproduces the PCB branch's patterns within 0.01 dB. The end-plate reference
(`out/ep_ref_0`, `out/ep_ref_140`: duck, 170 mm deck, no plate / 140 mm plate; `out/bearing_ep_ref`) gives
median bearing error 20 -> 16 deg and 90% 64 -> 46 deg. The fine mesh agrees with the default within 1 deg
(`out/size_ep_fine/`, `out/size_h50327_ep_fine/`). The coarse mesh is not good enough for size work.

**Ducks (H50327), faces 120 mm tall, with end plate** (`out/size_h50327_ep/`):

| Sectors | Face width | Spacing | Deck | End plate | Median | 90% | Right sector |
|---|---|---|---|---|---|---|---|
| 3 | 120 mm | 31 mm | 146 mm | 144 mm | 16 deg | 42 deg | 81% |
| 3 | 120 | 15 | 144 | 144 | 15 | 39 | 84% |
| 3 | 100 | 15 | 121 | 121 | 15 | 39 | 83% |
| 3 | 80 | 15 | 98 | 98 | 15 | 42 | 82% |
| 3 | 60 | 15 | 80 | 75 | 16 | 46 | 80% |
| 4 | 60 | 15 | 105 | 90 | 15 | 45 | 68% |
| 4 | 80 | 15 | 125 | 119 | 13 | 36 | 71% |
| 4 | 100 | 15 | 147 | 147 | 12 | 33 | 73% |
| 4 | 120 | 15 | 175 | 175 | 11 | 31 | 75% |

**Short element (chip stand-in), square faces, with end plate** (`out/size_ep/`):

| Sectors | Face | Spacing | Deck | Median | 90% |
|---|---|---|---|---|---|
| 3 | 120 mm | 15 mm | 144 mm | 14 deg | 37 deg |
| 3 | 100 | 15 | 121 | 16 | 45 |
| 3 | 80 | 15 | 98 | 19 | 59 |
| 3 | 60 | 15 | 80 | 23 | 75 |
| 4 | 60 | 8 | 91 | 16 | 54 |
| 4 | 80 | 8 | 119 | 13 | 42 |
| 4 | 100 | 15 | 147 | 11 | 33 |

Without the end plate (`out/size/`, `out/size_h50327/`): the duck masts are 4-7 deg worse at the median and their
90% tail passes 100 deg once the faces narrow (e.g. 60 x 120 mm at 15 mm: 20 deg, 90% 115 deg); ducks on faces
shorter than they hang (80 x 80 mm) fail (48-101 deg). The chip stand-in on square faces changes little either way:
3 sectors at 60 mm / 15 mm is 20 deg without the plate and 23 deg with it, 80 mm is 20 vs 19 deg.

What it shows:

- For the ducks, the end plate is the biggest gain after spacing; for the chip stand-in on short square faces it
  barely matters.
- 15 mm spacing beats 31 mm at every size. 8 mm adds little and drops the feed resistance to about 13-20 ohm (a
  hard match).
- With the end plate, the duck mast can narrow to 60-80 mm wide x 120 mm tall faces (80-98 mm across) at
  15-16 deg, as good as the 144 mm version.
- Face height matters as much as width: ducks on 60 x 120 mm faces (16 deg) beat the chip stand-in on 60 x 60 mm
  faces (23 deg) at the same diameter.
- A fourth sector gains 2-4 deg at the same face width, for one more radio and 25-30% more diameter.
- 45 mm faces are about 30 deg either way.
- No geometry reaches 20 dB back rejection at el -55 (best about 12 dB).

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
| `out/h50327_c65_s15`, `_s20`, `_s25`, `_s34` | H50327 (feed 65 mm down) 15 / 20 / 25 / 34 mm in front of the face | 8.8 / 8.6 / 8.4 / 7.7 dBi; 31 mm is `out/h50327_c65` |
| `out/bearing` | Bearing sim: monopole vs duck | Median 34 vs 21 deg |
| `out/bearing_spacing` | Bearing sim: the five spacings | Median 19-21 deg |
| `out/bearing_h50327` | Bearing sim: duck vs the three H50327 cases | Median 19-22 deg |
| `out/spec_sweep` | Idealised beams: beamwidth x back floor x noise | Back rejection matters most; specs above |

## Limits

## Rev 3 PCBs: outline vs real copper (2026-11-23, full mesh)

The rev 3 boards (`../builds/pcb`, `--build pcb`) at two levels of detail, H50327 with its feed 65 mm down, end plate fitted:
`--deck d15|d31 --end-plate` (outline: deck disc of the variant's diameter with the 22.2 mm pipe hole, solid core,
144 mm end plate disc) and the same with `--copper` (both deck layers 1.6 mm apart joined by every plated hole and
via, every hole, slot and track gap, the end plate's copper including the knockout ring, and a hollow core of three
1.6 mm face-board slabs with their tabs through the slots; from `../builds/pcb/out/*_copper.json`, written by
`make_pcbs.py`). Antennas at each deck's D holes (15 / 31 mm).

| Run | S11 at 2440 | Peak | -3 dB width el 0 / -30 | F/B el 0 / -30 | Isolation | Median bearing error | 90% | Right sector |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| d15 outline | -2.8 dB | 8.8 dBi | 85 / 105 deg | 29.4 / 19.9 dB | -49.3 dB | 15 deg | 39 deg | 84.4% |
| d15 copper | -2.7 dB | 8.7 dBi | 85 / 95 deg | 29.2 / 20.2 dB | -49.4 dB | 14 deg | 38 deg | 83.7% |
| d15 copper, deck board as end plate | -2.6 dB | 8.7 dBi | 85 / 95 deg | 29.5 / 19.9 dB | -49.7 dB | 14 deg | 38 deg | 83.7% |
| d31 outline | -5.1 dB | 8.0 dBi | 105 / 125 deg | 25.0 / 20.5 dB | -48.6 dB | 16 deg | 42 deg | 80.9% |
| d31 copper | -5.0 dB | 8.1 dBi | 100 / 130 deg | 30.2 / 21.0 dB | -52.1 / -49.4 dB | 14 deg | 39 deg | 81.0% |

(`out/rev3_*`, bearing at default noise in `out/bearing_rev3`.)

The copper runs above have the face's centre RP-SMA hole (the face PCB as built). The same runs with a solid face
(hole dropped for a few hours on 2026-11-23) are kept in `out/rev3_*_copper*_solidface` and
`out/bearing_rev3_solidface`: bearing within 0-1 deg of these, so the hole doesn't change the result.

The same copper runs on the service layout (M4 corner bolts, J1 / J2 on the bottom, ties at 248 deg, face gusset
slots open, gussets not modelled; ble-beacon-tracker 74aa1a4) are in `out/rev3_*_copper*_gusset` and
`out/bearing_rev3_gusset` (2026-11-24, openEMS v0.37.0 built natively from the Dockerfile's source; S11 within 0.2 dB
and peak gain within 0.1 dBi of the earlier runs). Bearing: 15 mm deck 15 / 38 deg median / 90% (14 / 38 before),
31 mm deck 15 / 40 (14 / 39), right sector within 0.2 points: the layout changes and slots cost nothing measurable.
Isolation below about -48 dB moves by several dB between runs and isn't a layout signal.

Stubby monopole on the 31 mm deck (2026-11-24, owner's candidate: a 28.4 mm end-to-end, 2 dBi, RP-SMA 2.4 GHz
stubby, sold as OL-3464-2X): modelled as a straight quarter-wave monopole of the stubby's full length
(`--antenna monopole --length 28.4 --deck d31 --end-plate --copper`, `out/rev3_d31_copper_stubby`; the real part is a
shortened, probably helical element inside a 20.3 mm radome, so the match below is the wire's, not the part's, but
the pattern is a monopole's either way). Peak 3.9 dBi at el -25 deg, isolation -29 dB (ducks -49 to -57). Bearing
(`out/bearing_rev3_d31_stubby`): 36 / 105 deg median / 90%, right sector 66%, against 15 / 40 deg and 81% for the
ducks on the same deck, and about the same as the 2026-11-12 monopole on the old mast (34 / 101). With the deck as
its ground plane a short monopole's beam stays broad; the face behind it does little. The same stubby on the 15 mm deck
(`out/rev3_d15_copper_stubby`, `out/bearing_rev3_stubby_d15_d31`): 29 / 89 deg, right sector 75%, peak 5.0 dBi at
az 0, el -25, isolation -34 dB. Closer to the face helps (the face starts to act as a reflector) but it stays about
twice the ducks' error (15 / 38 deg, 84%); the model's match drops to about 21 ohm there (S11 -5 dB).

- **Outline vs copper:** the two agree to within 0.3 dB on match, peak and the main-lobe numbers, and to 1-2 deg on
  median bearing error, which is at the simulation's noise level (about 1 deg). The real copper (holes, slots,
  the hollow core, the layer-to-layer vias) doesn't change the result: the outline model is enough for size and
  spacing questions. Single-angle front-to-back figures differ more where a null lands near az 180 (d31 at el -45:
  42.7 vs 16.9 dB); read those as "a null is near", not as a real difference.
- **d15 vs d31:** 15 mm gives the narrower beam (85 vs 100-105 deg at el 0), the higher peak (8.7-8.8 vs 8.0-8.1
  dBi) and a slightly better bearing (14-15 vs 14-16 deg median, 37-39 vs 39-42 deg at 90%, 84 vs 81% right
  sector). The duck's match is worse close to the face (-2.8 vs -5.1 dB S11), as in the spacing sweep; for a
  receiver that costs little.
- **Deck board as end plate** (`--end-plate deck`: a second d15 deck turned over, knockout in): the same as the
  end plate PCB within 0.1 dB and 0 deg, so one board design can serve both plates at 15 mm. (The d15 and d31
  copper runs were re-run after the deck gained its knockout, broken out in the model; within 0.3 dB / 1 deg of the
  first runs.)
- **Not comparable** with the older runs above (146 mm disc, no end plate, no pipe hole): both the deck size and
  the end plate changed at once.
- **Model limits (`--copper`):** tracks and gaps narrower than the 1 mm mesh are only roughly resolved, the faces
  at 120 / 240 deg are staircased, the face board is solid metal through its thickness, and the XIAOs, coax and
  pipe are not in the model.

Not modelled: the enclosure, the electronics plate and its parts, the coax runs, the bolts and spacers, the
printed-dipole panels and the DIY dipoles. The core is a solid copper prism (only its outside affects the pattern),
and the whips are thin wires. Treat the results as how the deck and core shape the beam, not as exact gains, and
check them against an RSSI walk.
