# Hand build (scratch): deck, faces and plate templates

Build the mast by hand from copper-clad board, acrylic and stripboard, with printable 1:1 templates. The PCB build is the other way to build the same mast: [`../pcb/README.md`](../pcb/README.md). Both builds share the same physical layout of antennas and plates (deck size per duck spacing, antenna holes, faces, pipe hole, M3 registration holes), computed once in [`common/layout.py`](../../common/layout.py) from [`common/parameters.csv`](../../common/parameters.csv). This build's own numbers (templates, plates, wiring, the copper deck, the LED ring and unified board options) are in [`parameters.csv`](parameters.csv) here.

> **Status (2026-11-24): the templates follow the shared layout and the star wiring.**
> - **Updated:** page 1 (one deck drill template for both duck spacings: D15 and D31 holes, 2-1/4" centre hole for the pipe build, 146.3 mm cut line with the 144 mm line dashed, no part positions; drawn in the plates' frame so every hole lines up with them), pages 2-3 (plates: dotted D15 and D31 reference holes; the no-pipe plate shows the deck's centre hole and M3 bolts), page 4 (plain face, one 6.5 mm centre hole, butt joints), page 6 (star wiring, relay protocol 4) and page 9 (formulas, printed from `common/layout.py`).
> - **Not updated yet:** page 7 (LED ring) and page 8 (unified board: its wire list still shows each radio's own data wire).
> - **Decided:** electronics on the acrylic plate above the deck (the on-deck layout is the PCB build's); the plate keeps its three M4 bolts in the deck's core corners, with spacers, so its radios sit near the deck. Faces are plain butt-jointed squares. The LED ring stays as an option.
> - `shield_deck_gerbers.zip` (`make_shield_deck.py`, a bare 146 mm deck for 31 mm ducks) is the older layout and is superseded by the deck template and the PCB decks; it stays in the repo.

## Firmware and pins (both builds)

Both builds run the same scanner firmware ([`scanner_fw/`](../../scanner_fw/README.md)), but today the pins don't agree:

| | Uplink TX (to the gateway or the head radio) | Command RX | Branch RX |
| --- | --- | --- | --- |
| Hand build, templates page 6 (2026-11-24, relay protocol 4) | D10 (head S0 to the ESP32, S1 / S2 to the head) | D7 | head D0 (S1) / D1 (S2) |
| Hand build, masts wired before 2026-11-24 | D6 (issue #1's move to D8 is cancelled) | D7 | - |
| Scanner firmware 0.8.0 (`scanner_fw/app.overlay`) | D8 | D7 | - |
| PCB deck rev 3 (relay protocol 4) | D10 (head to J1 DATA, the other two to the head) | D7 | head D0 / D1 |

D8 has no UART on the nRF54L15, so the D8 wiring of issue #1 and firmware 0.8.0 can't carry the stream. Both builds are now drawn on the protocol 4 pins (D10, D7, D0 / D1), the one firmware for both; it isn't in `scanner_fw/` yet (0.8.0 is still per-radio D8).

Star wiring on the plate: S0 is the head (as U2 on the PCB deck). Its D10 goes through JST pin 3 to the ESP32's GPIO17 (header pin 34, gateway pin 0); S1's D10 goes to the head's D0 and S2's D10 to its D1, each one wire soldered pad to pad (no connector), so their JST pin 3 stays empty. 5V, GND and CMD (every D7, from the ESP32's GPIO21) run through the bus board as before. GPIO16 and GPIO18 are left free for two more heads.

## Quick start (files in the repo, no software)

**Use the 15 mm duck spacing (D15) and pick one plate (pipe or no pipe).** Print and use only the pages you need. 15 mm is the recommended spacing (2026-11-24): in the RF model it is as good or better than 31 mm for every antenna tried, about the same for the H50327 ducks (15 / 38 deg median / 90% bearing error against 15 / 40) and much better for a stubby monopole (29 / 89 against 36 / 105), and it lets the deck be 144 mm. D31 stays on the template for 31 mm builds; its one advantage is a better duck match (S11 about -5 dB against -3 dB in the model). See [`../../rf_model/README.md`](../../rf_model/README.md). (The electronics on the deck, inside the core, is the PCB build: [`../pcb/README.md`](../pcb/README.md).)

| Page | What | Status |
| --- | --- | --- |
| 1 | Deck drill template, 15 and 31 mm ducks (144 / 146.3 mm) | updated |
| 2 | Pipe plate (acrylic) | updated (reference holes) |
| 3 | No-pipe split plate (acrylic) | updated (reference holes) |
| 4 | Face (make 3) | updated |
| 5 | Pipe stack views (not to scale) | older layout |
| 6 | Wiring diagram (star wiring) | updated |
| 7 | Option: LED direction ring, its power board and strip wiring | older layout |
| 8 | Option: unified power + LED board | older wiring |
| 9 | Design formulas (reference, no need to print), without the PCB deck's radio placement | updated |

- **Pipe:** pages 1, 2, 4, 5, 6. PoE splitter and ESP32 hang on a 1/2" PVC pipe inside the core; they go in through the deck's 2-1/4" centre hole.
- **No pipe:** pages 1, 3, 4, 6. ESP32 and bus board hang under the plate; the PoE splitter sits in its own box.

**Pipe option, 1/2" EMT instead of PVC** (page 5 notes):
- **Size:** 17.9 mm OD and a 15.8 mm bore (`EMT_OD` / `EMT_ID`). The PVC pipe is 21.3 / 15.8 mm.
- **Mounting:** a set-screw or compression connector and locknut go in the same 7/8" (22.2 mm) hole.
- **RJ45:** a crimped head only just fits inside 1/2" EMT, so make sure there is no boot or crimp sleeve on the plug when it goes through. Check the connector's throat too.
- **Bushings:** fit one on every cut or drilled hole a cable passes near or through (the side slot, the tube ends), even when it's deburred properly.
- **Bonding:** bond the tube to the deck all round where it passes through: a copper collar, a ground clamp and braid, or conductive copper tape. Solder won't take on galvanized steel. Outdoors, seal the joint against zinc-copper corrosion.
- **ESP32 antenna:** mount it in a plastic cap or insulating bushing, not on the bare steel end.

1. Print your pages of `hand_build_shield_deck_templates.pdf` at 100% ("Actual size", not "Fit to page"). Measure both 100 mm scale bars (across the top and down the left side) on each drill template with a ruler before you drill: the printer can scale one direction and not the other.
2. Make the deck: drill copper-clad board from the deck template (page 1): only the antenna jack you use in each sector (D15 for ducks, the recommended spacing; D31 for a 31 mm build; P or P2 for a patch), or order a PCB deck ([../pcb/README.md](../pcb/README.md)). The older bare 146 mm deck (`shield_deck_gerbers.zip`) is superseded; its order notes (`PCBWAY.md`) were retired on 2026-11-23 and are in git history.
3. Lay out your plate (page 2 or 3). Its layout is only a suggestion: lay your own parts on the printout and check every hole against them before drilling.
4. Drill the plate and the faces (page 4); sizes, counts and zip ties: [Drill sizes and zip ties](#drill-sizes-and-zip-ties). The plates' dotted antenna holes sit over the deck's (page 1) when the M4 holes line up.
5. Put it together with the wiring diagram (page 6), and for the pipe the stack views (page 5).

**Option: LED direction ring** (page 7). A WS2812B strip wrapped into a ring above the deck, facing out, to light toward a detected beacon:

- **Power:** a second 4x4 pad board between the PoE splitter and the ESP32. A USB-C socket pigtail takes the splitter's plug, a USB-C plug pigtail feeds the ESP32, and the strip hangs off a fused row, so its current never passes through the ESP32.
- **Size:** 24 pixels of 60-per-metre strip make a 127 mm ring, inside the 146 mm deck (`LED_PIXELS`, `LED_PER_M`). Keep the strip and its wires above the deck: the copper shades the antennas from them.
- **Parts:** chosen for outdoor cold and heat (polymer capacitor, X7R ceramic, chip fuse); the page lists them.
- **Bulk capacitor:** KEMET A750EM337M1CAAE015, a leaded aluminium polymer can (330 uF 16 V, 6.3 x 9 mm, -55 to +105 C), legs spread to rows 1 and 3. Any leaded polymer can of 330 to 470 uF, 10 to 16 V, does the same job.
- **Bulk capacitor, surface-mount option:** a 330 uF 10 V polymer tantalum chip in the 7343 (2917) case, in place of the leaded can: KEMET T591X337M010ATE025, T545Y337M010ATE035 or T525Y337M010ATE035. Others that match: [Mouser search](https://www.mouser.com/en/c/passive-components/capacitors/tantalum-capacitors/tantalum-capacitors-polymer/?capacitance=330%20uF&case%20code%20-%20in=2917&termination%20style=SMD%2FSMT&voltage%20rating%20dc=10%20VDC~~16%20VDC&instock=y&rp=passive-components%2Fcapacitors%2Ftantalum-capacitors%2Ftantalum-capacitors-polymer%7C~Voltage%20Rating%20DC&sort=pricing&qty=1). Polymer only, not solid (manganese dioxide) tantalum.
- **Status:** wiring only. The gateway firmware does not drive the strip yet, and the ring's effect on reception has not been measured.

**Option: unified power + LED board** (page 8, pipe build, 2026-11-20). One 0.1 in stripboard (10 strips x 23 holes, 25.4 x 58.4 mm) in place of the bus board (page 6) and the LED power board (page 7), which both stay as they are. It hangs on the pipe at the 11 o'clock corner beside the splitter and the ESP32:

- **Power:** the splitter's USB-C plug goes into a socket pigtail on the board; a plug pigtail feeds the ESP32. The three XIAOs take 5 V from the same splitter rail, not from the ESP32's VBUS (pin 40), so that wire goes. The strip is fused (one-time, 2 A); the ESP32 and XIAO feed is not.
- **Data:** a 74HCT125 buffer (U1, gate 1; gates 2-4 tied off) lifts the ESP32's 3.3 V GPIO1 to 5 V for the WS2812B, then the 330 ohm series resistor. A 10 kohm pull-down (R2) on the buffer's input keeps the strip dark while the ESP32 boots and GPIO1 floats. The TX bus (GPIO21 to every D7) is a strip of its own.
- **Board:** BusBoard ST1 StripBoard-1 (Mouser 854-ST1), FR4, 50 x 80 mm with the strips along the 80 mm; one makes one board.
- **Parts, all through-hole:** TI CD74HCT125E, Littelfuse 0251002.MXL, KEMET A750EM337M1CAAE015 (C1), 2 x KEMET C320C104K5R5TA (C2, C3), Yageo CFR-25JB-52-330R, Yageo CFR-25JB-52-10K (R2). Five track cuts, two bare links and two insulated links; the page has the strip map, the wire list and the checks.
- **Accepted risk (user, 2026-11-20): a strip short reboots the mast.** The PoE splitter current-limits (about 2.6 A, estimated) before the 2 A fuse opens: the fuse carries about 115% of its rating, where the 251 series has no maximum opening time, and the shared 5 V rail falls to about 0.35 V, so the ESP32 and XIAOs reset until the short is cleared. See `sim/` (case `strip_short`). If it starts to matter: a 1 A fuse with a 0.8 A firmware cap (a short is then 260%, opening within 1 s, still with a brief reboot) or an eFuse / high-side switch on the strip feed. Measuring the splitter's real limit may also change the picture.
- **Status:** drawn only, not built. The layout is a table in `make_templates.py` (`UNI_*`), sizes in `parameters.csv` (group `uni`).

Page 9 shows how the parts are sized: the monopole (D hole) spacing from the wavelength, the triangle core and back panels, and every hole radius on the baseplate (shield deck), worked out from the current `parameters.csv` values. It leaves out the PCB deck's radio placement (XIAOs, IPEX4, tie squares, J1 / J2): the same page with the radios is the last page of `../pcb/out/pcb_print_1to1.pdf`. Both come from `common/formulas_page.py`.

### Drill sizes and zip ties

Holes you drill yourself (the deck PCB comes drilled from the fab). Counts are for one mast. Inch sizes are the nearest drill that works.

| Drill | Inch | For | Pipe | No pipe |
| --- | --- | --- | :---: | :---: |
| 4.8 mm | 3/16" | Plate: M4 bolts to the deck | 3 | 3 |
| 4.8 mm | 3/16" | Plate: zip tie holes (pairs; any 3.0-4.8 mm fits a 2.5 mm tie) | 6 (3 XIAOs) | 10 (3 XIAOs + 2 across the ESP32) |
| 3.4 mm | 9/64" | Plate: bus board M3 | 1 (skip if the bus goes on the pipe) | 1 |
| 22.2 mm | 7/8" | Plate centre + enclosure top: 1/2" male pipe adapter thread | 2 (1 plate, 1 enclosure top) | - |
| 57 mm hole saw | 2-1/4" | Deck centre, pipe build: splitter and ESP32 pass into the core (cuts away the M3 holes) | 1 | - |
| 22.2 mm | 7/8" | Deck centre, no pipe | - | 1 (optional) |
| 6.5 mm | 17/64" | Deck: RP-SMA antenna jack, one per sector (D15, D31, P or P2) | 3 | 3 |
| 4.8 mm | 3/16" | Deck: M4 bolts in the core corners (plate spacers) | 3 | 3 |
| 3.4 mm | 9/64" | Deck: M3 registration to the collar (optional, as the PCB deck) | 0 or 3 | 0 or 3 |
| 25 mm | 1" | PoE splitter's 4" round box | - | 1 |
| 6.5 mm | 17/64" | Face: RP-SMA bulkhead at the face centre (only for a face antenna: dipole or printed fin; page 4) | 0 or 1 per face | 0 or 1 per face |
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

## BOM (one mast)

Plate build, star wiring. Drill sizes and zip ties are in the tables above.

| Part | For | Pipe | No pipe |
| --- | --- | :---: | :---: |
| Seeed XIAO nRF54L15 | Radios S0 (head), S1, S2 | 3 | 3 |
| Waveshare ESP32-S3-ETH | Gateway | 1 | 1 |
| PoE splitter, 5 V USB-C out | Power | 1 | 1 |
| Copper-clad FR-4, 1.6 mm, single or double sided | Deck (144 mm disc for 15 mm ducks, recommended; 146.3 mm for 31 mm) and 3 faces (120 x 120 mm) | 1 deck + 3 faces | 1 deck + 3 faces |
| Acrylic disc, 152 mm | Electronics plate (page 2 or 3) | 1 | 1 |
| RP-SMA female bulkhead | Deck jacks, one per sector | 3 | 3 |
| IPEX4 (MHF4) to RP-SMA bulkhead pigtail | Radio to its deck jack | 3 | 3 |
| Antenna: 2.4 GHz duck (RP-SMA) or patch | One per sector | 3 | 3 |
| Pad board, 4x4 (MBSS) | Bus: 5V, GND, CMD rows | 1 | 1 |
| Inline 4-pin JST pair, ~90 mm tails each side | One per radio (pin 3 used on the head only) | 3 | 3 |
| Hook-up wire, 24-26 AWG: red, black, yellow, green | Tails, bus feed; 2 yellow branch wires S1 / S2 D10 to head D0 / D1, soldered direct | 1 set | 1 set |
| M4 bolt + 25-30 mm spacer + washer, M4 nut in the core corner | Plate to deck | 3 | 3 |
| M3 x 8 bolt + nut | Bus board to the plate | 1 (0 if the bus goes on the pipe) | 1 |
| 1/2 in HS-100 adhesive tie mount | Coax strain relief | 3 | 3 |
| Zip ties, 2.5 mm | See the zip tie table | 6 x 100, 2 x 150, 2 x 200 | 6 x 100, 2 x 150 |
| 1/2 in PVC pipe, male adapter, nut, cap (page 5) | Pipe mount | 1 set | - |
| 4 in round electrical box | PoE splitter | - | 1 |
| Copper tape, Kapton tape | Face seams, insulation | 1 roll each | 1 roll each |

Optional: the LED ring (page 7) and the unified board (page 8) list their own parts.

## Next

- **Order a PCB deck instead:** [../pcb/README.md](../pcb/README.md), with its fab settings. The older bare 146 mm deck (`shield_deck_gerbers.zip`) is superseded; its order notes (`PCBWAY.md`) were retired on 2026-11-23 and are in git history.
- **Build or change the files:** [Using the scripts](#using-the-scripts): change a measurement, [lay out a plate in Inkscape](#lay-out-a-plate-in-inkscape), regenerate the Gerbers, PDF and SVGs, [when something goes wrong](#when-something-goes-wrong).

## Using the scripts

Everything here is generated from two files of numbers: this build's [`parameters.csv`](parameters.csv) and the shared [`common/parameters.csv`](../../common/parameters.csv) (the geometry the PCB build uses too). Each name is in one of them only. Change numbers there, or move parts in Inkscape and let the scripts write the numbers back. Don't hand-edit the outputs (Gerbers, PDF, SVGs): the next run overwrites them.

### Setup (once)

1. Install Python 3.10 or later.
2. `pip install reportlab`. This is only needed for the PDF templates; the deck Gerbers need nothing extra.
3. Install [Inkscape](https://inkscape.org) 1.x, but only if you want to lay out a plate by dragging parts.
4. Run every command from this `builds/hand/` folder.

### Files

| File | What it is | Made by |
| --- | --- | --- |
| `parameters.csv` | This build's measurements, sizes, placements and clearance rules | You (or `read_plate_svg.py`) |
| `../../common/parameters.csv` | Shared with the PCB build: faces and core, duck spacing, pipe, XIAO and radio positions, enclosure, RF | You |
| `../../common/params.py`, `../../common/layout.py` | Load the CSVs; derive the shared layout (deck size, holes, core limit) | - |
| `shield_deck_gerbers.zip`, `shield_deck_preview.svg`, `hole_table.csv` | Deck PCB Gerbers (any fab), a picture of it, hole coordinates | `make_shield_deck.py` |
| `hand_build_shield_deck_templates.pdf` | 1:1 printable drill templates, stack views, wiring, LED ring option, unified board option, design formulas | `make_templates.py` |
| `plate_layout.svg`, `pipe_plate_layout.svg` | No-pipe (alt) and pipe plates for laying out in Inkscape | `make_plate_svg.py` |

### Print the templates

1. `python make_templates.py`
2. Print `hand_build_shield_deck_templates.pdf` at 100% ("Actual size", not "Fit to page").
3. Measure both 100 mm scale bars (across the top and down the left side) on each drill template with a ruler before you drill: the printer can scale one direction and not the other.

The pages, in order (pick one build type, pipe or no pipe, and print only its pages: [which pages](#quick-start-files-in-the-repo-no-software)):

1. Deck drill template (both)
2. Pipe plate (pipe only)
3. No-pipe split plate (no pipe only)
4. Face (both)
5. Pipe stack views, not to scale (pipe only)
6. Wiring diagram (both)
7. Option: LED direction ring (both, only if you add the ring)
8. Option: unified power + LED board (pipe, only if you use it instead of the bus and LED boards)
9. Design formulas (reference, not to size; radio placement is in the PCB print PDF)

### Change a measurement or size

1. Find the name in `parameters.csv` here or in `../../common/parameters.csv` (it is in one of them only), open that file in a spreadsheet or text editor and change the `value` cell. Keep the name as it is. A shared value changes the PCB build too: re-run `../pcb/make_pcbs.py` as well.
2. Rebuild whatever uses it:
   - **Deck rows** (`group` = `deck`): run `python make_shield_deck.py` (the superseded bare deck's Gerbers and `hole_table.csv`).
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
6. `python read_plate_svg.py`. This writes the new positions into this build's `parameters.csv` and checks the rules:
   - Every rule shows `ok` or `FAIL`, with the worst gap and where it is.
   - On a failure, move that part and repeat from step 5.
   - It only reads one plate if you name it: `python read_plate_svg.py alt` or `python read_plate_svg.py pipe`.
7. `python make_templates.py`, then print pages 2 and 3 (pipe and no-pipe plates) and check them against the real parts before drilling.
8. Commit `parameters.csv` and the SVG together so they stay in step.

### The rules

The `rules` rows of this build's `parameters.csv` set the margins. Change one there and re-run `python read_plate_svg.py --check`.

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
