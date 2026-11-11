# Ordering the shield deck PCB (PCBWay)

The deck is a round 146 mm two-layer PCB. These steps and settings are for PCBWay, the fab used so far; the Gerbers are standard RS-274X, so any PCB fab can make it with the same settings. Back to the [shield deck README](README.md).

## Order

1. Use `shield_deck_gerbers.zip` from this folder as it is. Rebuild it with `python make_shield_deck.py` only after changing a `deck` row in `parameters.csv` ([Using the scripts](README.md#using-the-scripts)).
2. Upload the zip to PCBWay's quick-order PCB page with the [order settings](#order-settings) below.
3. Check it in PCBWay's online Gerber viewer before paying.

## Order settings

| Setting | Value |
| --- | --- |
| Board type | Single pieces |
| Size | 146 x 146 mm (round board, outline in the GKO layer) |
| Layers | 2 |
| Material | FR-4, TG130 or better |
| Thickness | 1.6 mm |
| Copper | 1 oz outer |
| Min hole | 0.6 mm (stitching vias) |
| Surface finish | HASL lead-free (or ENIG) - copper must be solderable |
| Solder mask | Any colour |
| Silkscreen | White, top only |
| Quantity | 5 (minimum) |
| Note to fab | "Round board. All holes plated; sizes are finished hole sizes. Large solid copper pour on both layers is intentional (RF shield)." |

## What's on the board

- Solid copper on both sides, pulled back 0.5 mm from the edge, tied together by 36 plated vias on a 71 mm radius.
- Exposed copper (no mask): 4 mm ring at the rim on both sides (copper-tape edge seal), 12 mm pads around every RP-SMA hole (nut contact), on the bottom a 6 mm strip along the triangle where the 120 mm reflector faces solder on, and a 9 mm pad round each M4 hole for its nut.
- Top silkscreen: TOP, sector numbers S0-S2, an arrow for Sector 0, and hole letters (D = duck/monopole, P = patch, P2 = patch at the face end, C = dipole coax pass-through, M4 = bolt to the electronics plate).

Top = electronics side. Bottom = antenna side (the triangle seam strip is there).

## Holes (finished, plated)

| Hole | Dia. | Radius from centre | Direction |
| --- | --- | --- | --- |
| Duck / monopole RP-SMA (x3) | 6.5 mm | 65.6 mm (31 mm in front of each face) | Sector 0 / 120 / 240 deg |
| Patch RP-SMA (x3) | 6.5 mm | 41.6 mm (7 mm in front of each face) | Sector 0 / 120 / 240 deg |
| Patch-end RP-SMA "P2" (x3) | 6.5 mm | 48.6 mm (7 mm in front of each face, 25 mm off its centre toward its counter-clockwise end; moved in from 14 mm off the end on 2026-11-10 so the panel board's coax reaches it in back-panel positions A and C) | 329.0 / 89.0 / 209.0 deg |
| Dipole coax pass-through (x3) | 10 mm | 20 mm (inside the core) | Sector 0 / 120 / 240 deg |
| M4 bolt to the electronics plate (x3) | 4.8 mm | 59.1 mm (inside the core, in each corner) | Corners 60 / 180 / 300 deg |
| Stitching vias (x36) | 0.6 mm | 71 mm | Every 10 deg |

RP-SMA connector thread OD is 6.3 mm, so 6.5 mm gives ~0.2 mm clearance. If the fab's plating tolerance worries you, request "+0.1 mm" or ream after delivery.

The M4 holes sit where a 7 mm (across flats) M4 nut, under the deck inside the core, has two flats flush against the faces' inner sides (`FACE_THICK = 1.6` mm boards) in each corner; solder the nut to the deck pad and both faces. 4.8 mm gives the bolt a little room to find the nut. If the faces are a different thickness, or a seam fillet fills the corner, change `FACE_THICK` / `NUT_GAP` and regenerate.

Exact coordinates: `hole_table.csv`.
