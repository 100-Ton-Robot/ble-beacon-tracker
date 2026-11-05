# Shield deck PCB (PCBWay)

Upload `shield_deck_gerbers.zip` to PCBWay's quick-order PCB page.

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
| Patch-end RP-SMA "P2" (x3) | 6.5 mm | 62.1 mm (7 mm in front of each face, 14 mm in from its counter-clockwise end) | 312.2 / 72.2 / 192.2 deg |
| Dipole coax pass-through (x3) | 10 mm | 20 mm (inside the core) | Sector 0 / 120 / 240 deg |
| M4 bolt to the electronics plate (x3) | 4.8 mm | 59.1 mm (inside the core, in each corner) | Corners 60 / 180 / 300 deg |
| Stitching vias (x36) | 0.6 mm | 71 mm | Every 10 deg |

RP-SMA connector thread OD is 6.3 mm, so 6.5 mm gives ~0.2 mm clearance. If the fab's plating tolerance worries you, request "+0.1 mm" or ream after delivery.

The M4 holes sit where a 7 mm (across flats) M4 nut, under the deck inside the core, has two flats flush against the faces' inner sides (`FACE_THICK = 1.6` mm boards) in each corner; solder the nut to the deck pad and both faces. 4.8 mm gives the bolt a little room to find the nut. If the faces are a different thickness, or a seam fillet fills the corner, change `FACE_THICK` / `NUT_GAP` and regenerate.

Exact coordinates: `hole_table.csv`.

## Changing it

Edit the PARAMETERS block in `make_shield_deck.py` (disc diameter, face width, spacings, hole sizes) and run `python make_shield_deck.py`. Sized for the enclosure (146 mm disc; tape any gap at the edge). If the enclosure is wider where the deck sits, raise `DISC_DIAMETER` (e.g. 160). `PATCH_OFFSET = 7` because the measured panel's connector axis is in line with its housing back, so the panel stands 7 mm off the face to clear the plug nut. The patch element outline on the back-panel template comes from `PATCH_W`/`PATCH_H`/`ELEMENT_END` in `make_templates.py`.

Check the upload in PCBWay's online Gerber viewer before paying.
