# Printed dipole fin — SHELVED, NOT TESTED

> **Status: shelved 2026-11-24. Not tested.** Simulation only: no fin has been built, fitted to a face or measured on
> air. Every number on this page is an openEMS model result.

A printed half-wave dipole on a small double-sided FR-4 board (the "fin") standing straight out from each face, at
the face centre over the 6.5 mm `DIPOLE_HOLE`, in place of a duck. Meant to be hand-made by score and peel from
1 mm double-sided copper-clad FR-4, from a 1:1 print template, with no tuning (there is no VNA): one fixed design
that has to work as built.

## Why it was shelved

The fin's two tabs (2.6 x 2.5 mm, through slots in the face) can't be cut cleanly by hand in fibreglass.

Untried fix, for whoever picks it up: drop the tabs and make the fin a plain rectangle (score and snap only). Stand
it on the face over the hole and solder a fillet where each side B strip meets the face copper, one each side of the
slot, held square by a block or a printed jig. The model already shorts the strips to the face along that edge, so
the tuned dimensions should carry over, but that variant has not been re-modelled, built or measured. No face slots
are needed then; on the PCB face the solder mask would have to open past the 12 mm pad round the hole (the strips
reach about 9 mm from the hole centre).

## Design (as modelled)

Fin-local coordinates, mm: `u` out from the face's outer copper, `v` along the face height, `v = 0` on the slot
centre line over the hole. All numbers are in [`parameters.csv`](parameters.csv); the face thickness and hole come
from [`common/parameters.csv`](../../common/parameters.csv) (`FACE_THICK`, `DIPOLE_HOLE`).

- Board 18.5 x 55.6 mm plus two tabs (21.1 x 55.6 mm overall), 1.0 mm double-sided FR-4.
- Side B (ground): two 8 mm strips from the face out to the dipole with a 2 mm slot between them: a slotline balun,
  shorted by the face, about a quarter wave long. Each strip turns into one arm: arms 4 mm wide, 52.6 mm tip to
  tip, on an axis 15 mm off the face (the 15 mm spacing the size sweep found best).
- Side A (feed): a 1.9 mm (50 ohm) microstrip over the lower strip from 0.8 mm off the face, crossing the slot at
  u = 11 mm and ending in an open stub over the upper strip, its return leg 7.8 mm back toward the face.
- Feed: half an IPEX4-IPEX4 jumper soldered straight on, shield to side B, centre round the face edge to side A.
- All copper is rectangles, every gap at least 1 mm, copper at least 1 mm from the board edge, so it can be
  scored and peeled. Fit all three fins the same way up (feed toward the end plate, as modelled).
- Fits the current mast: 120 x 120 mm faces, 6.5 mm centre hole, 144 mm deck (D15) and end plate. Not for D31,
  or for the narrower masts in the size sweep, without re-modelling.

## Model results (not tested in hardware)

openEMS on the rev 3 core: solid core, D15 deck outline with the pipe hole, 144 mm end plate, one fin per face (the
other two terminated in 50 ohm). FR-4 er 4.3, tan d 0.02.

| Check | Target | Result |
| --- | --- | --- |
| Match, nominal | S11 < -10 dB, 2400-2483.5 MHz | -11.1 dB worst in band, -22.8 dB best at 2463 MHz (`out/fin_runs/g3`) |
| Match, stacked tolerance corners | S11 < -6 dB | -6.8 dB (er 4.7, copper +0.3 mm on every edge, 0.9 mm board, lengths long: `g3_lo`); -9.0 dB (er 4.0, copper -0.3 mm, 1.1 mm board, lengths short: `g3_hi`) |
| Bearing, `bearing_sim.py` defaults | within 2 deg of the duck | median 15 deg / 90 % 40 deg, right sector 84.6 % vs duck stand-in at 15 mm 15 deg / 39 deg / 84.4 % (`out/bearing_fin`) |
| Peak gain | | 8.6 dBi (`out/fin_runs/arr_g3`) |

The slot was widened from 1 to 2 mm late in tuning: at 1 mm, copper left 0.3 mm wide on every edge pulled the
worst corner to -5.4 dB.

Not modelled: the coax run inside the core, the hollow core behind the hole (modelled as 1.6 mm of air into a solid
core), solder, the enclosure.

## Files

| File | What |
| --- | --- |
| [`fin_model.py`](fin_model.py) | Geometry (shared with the template), score-and-peel rule check, openEMS model. `python3 fin_model.py [--coarse] [--set k=v ...] [--all --nf2ff] [--out DIR]` |
| [`make_fin_template.py`](make_fin_template.py) | 1:1 PDF template from the same geometry. `python3 make_fin_template.py --result out/fin_final.json` |
| [`parameters.csv`](parameters.csv) | The fin's numbers (tuned values) |
| [`out/fin_template.pdf`](out/fin_template.pdf) | Template, US Letter, true 1:1 (print at 100 %): three fins side A / B, face slot page, results and build steps. Still shows the tabs. |
| `out/fin_template_draft.pdf` | First draft of the template (untuned dimensions), kept for the record |
| `out/fin_final.json`, `out/fin_s11.png` | Results summary and S11 plot used on the template's last page |
| `out/fin_runs/`, `out/fin_sw1/`, `out/fin_c0/`, `out/fin_f0/` | Every model run: `result.json` (parameters and S11 figures), `s11.csv`, `model.xml`; `arr_*` also `pattern.csv` |
| `out/bearing_fin/` | `bearing_sim.py` comparison against `rf_model/out/rev3_d15_outline` |

Runs were made on 2026-11-23 with the code before it moved here (it then read the old `shield_deck/` parameters,
same values); the code was ported to `common/` on 2026-11-24 and a coarse check run reproduced the nominal design.
`t_etchm` and `t_etchp` returned NaN (a port/mesh bug in the copper-offset option, fixed); `t_etchm2` / `t_etchp2`
are the good reruns.

| Run | Changed from the defaults of the time | Worst in band, dB | Best at MHz |
| --- | --- | --- | --- |
| fin_c0 / fin_f0 | first design, L 52, Lsh 7, slot 1 (coarse / fine mesh) | -7.8 / -8.1 | 2485 / 2494 |
| fin_sw1/L53_s4, _s7, _s10 | L 53, Lsh 4 / 7 / 10 | -8.3 / -12.9 / -7.6 | 2495 / 2450 / 2378 |
| r1, r2 | L 53 Lsh 7.4; L 53.6 Lsh 7 | -13.7, -13.0 | 2445, 2427 |
| t_er40, t_er47 | r1, er 4.0 / 4.7 | -11.2, -10.4 | 2468, 2416 |
| t_etchm2, t_etchp2 | r1, copper -0.3 / +0.3 mm | -12.5, -9.2 | 2453, 2442 |
| t_t09, t_t11 | r1, board 0.9 / 1.1 mm | -10.4, -14.9 | 2457, 2435 |
| t_Lm, t_Lp | r1, L 52.5 / 53.5 | -11.0, -12.8 | 2468, 2425 |
| t_cornerlo, t_cornerhi | r1, all errors one way | -5.4, -9.6 | 2403, 2485 |
| n2, n2_lo, n2_hi | L 52.8 Lsh 7.2 and its corners | -11.8, -5.8, -8.6 | 2458, 2413, 2506 |
| g2a, g2b, g2c | slot 2, L 53, Lsh 7.4 / 8.2 / 6.6 | -12.9, -13.9, -11.6 | 2448, 2440, 2459 |
| g2b_ep, g2b_em, g2b_lo, g2b_hi | g2b, copper +0.3 / -0.3, corners | -10.1, -14.1, -5.7, -10.9 | 2437, 2440, 2402, 2465 |
| **g3**, g3_lo, g3_hi | **slot 2, L 52.6, Lsh 7.8 (final)** and its corners | **-11.1**, -6.8, -9.0 | 2463, 2422, 2496 |
| arr_fin, arr_g3 | three fins, far field: r1 and g3 | -13.5, -11.1 | 2447, 2465 |

## Picking it up again

1. Re-model the tabless fin (edge soldered to the face) and check the three targets above.
2. Regenerate the template without tabs; replace the face-slot page with a face marking guide (centre line through
   the hole, where the fin sits).
3. Build one, then three; compare RSSI by sector against the ducks on the same mast. Only then call it tested.
