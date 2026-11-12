# RF model of a sector

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
  receiver; trimming the whip a little would centre it.
- Beam: peak 4.9 dBi about 35 deg below the horizon, straight out from the face. The -3 dB width is 125-155 deg
  depending on elevation, wider than the 120 deg sector, so neighbouring sectors overlap and can be compared.
- Back: about 10-12 dB weaker behind than in front at most elevations (the single-angle front-to-back figures jump
  where a null lands on az 180, like the 48 dB at el -30).
- Isolation: -29 dB from sector 0's whip to each of the others.


## Limits

Not modelled: the enclosure, the electronics plate and its parts, the coax runs, the bolts and spacers, the
printed-dipole panels and the DIY dipoles. The core is a solid copper prism (only its outside affects the pattern),
and the whips are thin wires. Treat the results as how the deck and core shape the beam, not as exact gains, and
check them against an RSSI walk.
