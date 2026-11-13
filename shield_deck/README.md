# Shield deck and plate templates

Printable 1:1 drill templates for the electronics plates and back panel, stack views, the wiring diagram, and the Gerbers for the copper shield deck PCB. Everything is already built and in this folder: you only need the scripts to change something.

## Quick start (files in the repo, no software)

**Pick one build type first: pipe or no pipe.** Print and use only the pages for the one you pick; the plate pages are alternatives, not both.

| Page | What | Pipe | No pipe |
| --- | --- | :---: | :---: |
| 1 | Deck drill template (the 2-1/4" hole-saw circle is for the pipe only) | yes | yes |
| 2 | Pipe plate | yes | - |
| 3 | No-pipe split plate | - | yes |
| 4 | Back panel | yes | yes |
| 5 | Pipe stack views (not to scale) | yes | - |
| 6 | Wiring diagram | yes | yes |
| 7 | Design formulas: monopole spacing, triangle, baseplate (reference, no need to print) | - | - |

- **Pipe:** pages 1, 2, 4, 5, 6. PoE splitter and ESP32 hang on a 1/2" PVC pipe inside the core; the deck centre is opened with a 2-1/4" hole saw.
- **No pipe:** pages 1, 3, 4, 6. ESP32 and bus board hang under the plate; the PoE splitter sits in its own box.

**Pipe option, 1/2" EMT instead of PVC** (page 5 notes):
- **Size:** 17.9 mm OD and a 15.8 mm bore (`EMT_OD` / `EMT_ID`). The PVC pipe is 21.3 / 15.8 mm.
- **Mounting:** a set-screw or compression connector and locknut go in the same 7/8" (22.2 mm) hole. The deck's 2-1/4" hole stays.
- **RJ45:** a crimped head only just fits inside 1/2" EMT, so make sure there is no boot or crimp sleeve on the plug when it goes through. Check the connector's throat too.
- **Bushings:** fit one on every cut or drilled hole a cable passes near or through (the side slot, the tube ends), even when it's deburred properly.
- **Bonding:** bond the tube to the deck all round where it passes through: a copper collar, a ground clamp and braid, or conductive copper tape. Solder won't take on galvanized steel. Outdoors, seal the joint against zinc-copper corrosion.
- **ESP32 antenna:** mount it in a plastic cap or insulating bushing, not on the bare steel end.

1. Print your pages of `shield_deck_templates.pdf` at 100% ("Actual size", not "Fit to page"). Measure both 100 mm scale bars (across the top and down the left side) on each drill template with a ruler before you drill: the printer can scale one direction and not the other.
2. Order the deck PCB: upload `shield_deck_gerbers.zip` to a PCB fab. Steps and settings: [PCBWAY.md](PCBWAY.md).
3. Lay out your plate (page 2 or 3). Its layout is only a suggestion: lay your own parts on the printout and check every hole against them before drilling.
4. Drill the plate and back panel (page 4); sizes, counts and zip ties: [Drill sizes and zip ties](#drill-sizes-and-zip-ties). Page 1 is the deck's own hole pattern, for checking the board (and marking the pipe's hole-saw cut).
5. Put it together with the wiring diagram (page 6), and for the pipe the stack views (page 5).

Page 7 shows how the parts are sized: the monopole (D hole) spacing from the wavelength, the triangle core and back panels, and every hole radius on the baseplate (shield deck), worked out from the current `parameters.csv` values.

### Drill sizes and zip ties

Holes you drill yourself (the deck PCB comes drilled from the fab). Counts are for one mast. Inch sizes are the nearest drill that works.

| Drill | Inch | For | Pipe | No pipe |
| --- | --- | --- | :---: | :---: |
| 4.8 mm | 3/16" | Plate: M4 bolts to the deck | 3 | 3 |
| 4.8 mm | 3/16" | Plate: zip tie holes (pairs; any 3.0-4.8 mm fits a 2.5 mm tie) | 6 (3 XIAOs) | 10 (3 XIAOs + 2 across the ESP32) |
| 3.4 mm | 9/64" | Plate: bus board M3 | 1 (skip if the bus goes on the pipe) | 1 |
| 22.2 mm | 7/8" | Plate centre + enclosure top: 1/2" male pipe adapter thread | 2 (1 plate, 1 enclosure top) | - |
| 57 mm hole saw | 2-1/4" | Deck centre, opened up for the pipe | 1 | - |
| 25 mm | 1" | PoE splitter's 4" round box | - | 1 |
| 2.4 mm | 3/32" | Back panel: M2 posts for the printed-dipole panel (page 4; 4 per position, A and C) | 8 per panel, 24 for 3 | 8 per panel, 24 for 3 |
| 6.5 mm | 17/64" | Back panel: DIY dipole RP-SMA at the face centre (only for that antenna) | 1 per panel | 1 per panel |
| 6.5 mm | 17/64" | Plate: antenna holes (dotted on pages 2-3, reference only, not by design) | 0 (up to 9) | 0 (up to 9) |

Don't use 1/4" (6.35 mm) for the RP-SMA holes: the thread is 6.3 mm.

Zip ties: 2.5 mm wide (they fit the 4.8 mm holes and the HS-100 mounts' 3.2 mm slots). Lengths allow for the strap round the part plus a tail to pull on.

| Length | For | Pipe | No pipe |
| --- | --- | :---: | :---: |
| 100 mm (4") | Each XIAO to the plate, across its back through its hole pair | 3 | 3 |
| 100 mm (4") | Coax clamped in each 1/2" HS-100 tie mount | 3 | 3 |
| 150 mm (6") | ESP32 to the plate, through its two hole pairs (room for standoffs) | - | 2 |
| 150 mm (6") | ESP32 to the pipe (round the pipe and board) | 2 | - |
| 200 mm (8") | PoE splitter to the pipe (round the pipe and splitter body) | 2 | - |
| | **Total** | **6 x 100, 2 x 150, 2 x 200** | **6 x 100, 2 x 150** |

Buy a few spares, and 2 more 150 mm ties if the pipe build's bus board goes on the pipe. Also 3 x 1/2" HS-100 adhesive tie mounts (both builds).

## Next

- **Order the deck PCB:** [PCBWAY.md](PCBWAY.md): order steps, fab settings, what's on the board and the hole table.
- **Build or change the files:** [Using the scripts](#using-the-scripts): change a measurement, [lay out a plate in Inkscape](#lay-out-a-plate-in-inkscape), regenerate the Gerbers, PDF and SVGs, [when something goes wrong](#when-something-goes-wrong).

## Using the scripts

Everything here is generated from one file of numbers, [`parameters.csv`](parameters.csv). Change numbers there, or move parts in Inkscape and let the scripts write the numbers back. Don't hand-edit the outputs (Gerbers, PDF, SVGs): the next run overwrites them.

### Setup (once)

1. Install Python 3.10 or later.
2. `pip install reportlab`. This is only needed for the PDF templates; the deck Gerbers need nothing extra.
3. Install [Inkscape](https://inkscape.org) 1.x, but only if you want to lay out a plate by dragging parts.
4. Run every command from this `shield_deck/` folder.

### Files

| File | What it is | Made by |
| --- | --- | --- |
| `parameters.csv` | Every measurement, size, placement and clearance rule | You (or `read_plate_svg.py`) |
| `params.py` | Loads the CSV for the other scripts | - |
| `shield_deck_gerbers.zip`, `shield_deck_preview.svg`, `hole_table.csv` | Deck PCB Gerbers (any fab), a picture of it, hole coordinates | `make_shield_deck.py` |
| `shield_deck_templates.pdf` | 1:1 printable drill templates, stack views, wiring, design formulas | `make_templates.py` |
| `plate_layout.svg`, `pipe_plate_layout.svg` | No-pipe (alt) and pipe plates for laying out in Inkscape | `make_plate_svg.py` |

### Print the templates

1. `python make_templates.py`
2. Print `shield_deck_templates.pdf` at 100% ("Actual size", not "Fit to page").
3. Measure both 100 mm scale bars (across the top and down the left side) on each drill template with a ruler before you drill: the printer can scale one direction and not the other.

The pages, in order (pick one build type, pipe or no pipe, and print only its pages: [which pages](#quick-start-files-in-the-repo-no-software)):

1. Deck drill template (both)
2. Pipe plate (pipe only)
3. No-pipe split plate (no pipe only)
4. Back panel (both)
5. Pipe stack views, not to scale (pipe only)
6. Wiring diagram (both)
7. Design formulas (reference, not to size)

### Change a measurement or size

1. Open `parameters.csv` in a spreadsheet or text editor and change the `value` cell. Keep the name as it is.
2. Rebuild whatever uses it:
   - **Deck rows** (`group` = `deck`): run `python make_shield_deck.py` and re-order the board ([PCBWAY.md](PCBWAY.md)).
   - **Plate placement rows** (`alt` or `pipe`): run `python make_plate_svg.py` so the Inkscape files match the CSV, then `python read_plate_svg.py --check`.
   - **Anything else**: run `python make_templates.py`.

Some deck examples:

- **Wider enclosure:** if the enclosure is wider where the deck sits, raise `DISC_DIAMETER` (e.g. to 160). It's sized at 146 mm now; tape any gap at the edge.
- **Different patch panel:** `PATCH_OFFSET` is 7 because the measured panel's connector axis is in line with its housing back, so the panel stands 7 mm off the face to clear the plug nut. A different panel needs its own value.

How the cells read:

- **`value`:** one number, or several separated by spaces for a group of values. For example, `ESP32` is `x0 y0 w h` and `ALT_S0` is `x y angle`.
- **Units:** sizes are in mm and angles in degrees, counter-clockwise from +x. Placement coordinates use the plate's top view: 12 o'clock up, y up, origin at the plate centre. A value whose `unit` is `in` is converted to mm on load.
- **`source`:** says how far to trust a number:
  - `measured`
  - `spec` (datasheet or standard)
  - `estimated`
  - `assumed`
  - `design` (a choice)
  - `rule` (a clearance to keep)
  - `drawing` (only moves things on a page)
- **What isn't stored:** values worked out from others (`MOUNT_RADIUS`, `POST_SHIFT`, ...) are computed in the scripts, so they can't drift.
- **If you remeasure a part:** update its `value`, set `source` to `measured`, and add the date to `note`.

### Lay out a plate in Inkscape

1. `python make_plate_svg.py`. This redraws both SVGs from the CSV. Skip it if the SVGs already match (e.g. right after a pull).
2. Open `plate_layout.svg` (no-pipe plate) or `pipe_plate_layout.svg` (pipe plate) in Inkscape. The drawing is 1 unit = 1 mm, top view, plate 12 o'clock up. Dashed parts hang under the plate.
3. Arrange the parts:
   - **Moving parts:** click a part to select it as one group (outline plus its holes). Drag it and rotate it (click it again for the rotate handles). Don't scale, flip or ungroup it.
   - **Sliding a hole:** double-click into a part to move its tie-hole pair or the bus M3 hole along the part. Moves sideways are dropped.
   - **Locked layers:** the plate, the M4 and antenna holes and the deck jacks are locked. The antenna holes are drawn dotted: they are there for reference (deck and plate line up), and can be drilled, but not by design. The dotted red ring round each antenna hole is the 8 mm keep-out.
   - **Pipe plate:** move only S0. S1 and S2 are clones that follow it, turned 120 deg. The bus stays pointing outward, M3 toward the rim.
   - **Keep the page:** don't change the page size (Document Properties). The reader refuses a resized page.
4. Save as **Inkscape SVG**, same file name.
5. `python read_plate_svg.py --dry-run`. This lists what would change in the CSV and writes nothing.
6. `python read_plate_svg.py`. This writes the new positions into `parameters.csv` and checks the rules:
   - Every rule shows `ok` or `FAIL`, with the worst gap and where it is.
   - On a failure, move that part and repeat from step 5.
   - It only reads one plate if you name it: `python read_plate_svg.py alt` or `python read_plate_svg.py pipe`.
7. `python make_templates.py`, then print pages 2 and 3 (pipe and no-pipe plates) and check them against the real parts before drilling.
8. Commit `parameters.csv` and the SVG together so they stay in step.

### The rules

The `rules` rows of `parameters.csv` set the margins. Change one there and re-run `python read_plate_svg.py --check`.

| Rule | Default | Keeps |
| --- | --- | --- |
| `RULE_ANT_CLEAR` | 8 mm | Parts, tie mounts and holes this far from an antenna hole's edge (the stiff coax rises straight up from its jack) |
| `RULE_COAX_CLEAR` | 2 mm | Each coax run (IPEX4 -> tie mount -> its sector's antenna holes) this far from other parts |
| `RULE_PART_GAP` | 1.5 mm | Parts, and a hole and someone else's part, this far apart (on the pipe plate also clear of the adapter hex) |
| `RULE_HOLE_GAP` | 2 mm | Drilled holes this far apart, edge to edge |
| `RULE_RIM_HOLE`, `RULE_RIM_PART` | 3 mm | Holes and parts this far inside the plate rim |

The current layouts pass with little room to spare. The tightest gaps are 1.51 mm (S0's tie hole to the ESP32) and 8.49 mm (a no-pipe plate tie hole to S0's P2), so check those with the real parts.

### When something goes wrong

- **`no element with id 's0'`:** a part was ungrouped or its ID changed. Undo that, or run `make_plate_svg.py` and redo the move.
- **"is flipped" or "is scaled":** undo the flip or scale (Object > Transform). Flipping would swap which side the IPEX4 is on.
- **"page viewBox is ...":** the page size was changed. Run `make_plate_svg.py` and move the parts again.
- **`No module named reportlab`:** run `pip install reportlab`.
- **The CSV and SVG disagree:** whichever you edited last wins. After editing the CSV, run `make_plate_svg.py`. After moving parts in Inkscape, run `read_plate_svg.py`.
