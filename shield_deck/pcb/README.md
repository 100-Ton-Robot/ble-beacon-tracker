# Deck and face PCBs (parts on the deck)

Two boards for PCBWay (or any fab), generated with KiCad from [`make_pcbs.py`](make_pcbs.py):

| Board | File to upload | Qty per mast | Order |
| --- | --- | --- | --- |
| Deck, 170 mm round: the shield plate the antennas go through, with the scanners and power on top | `out/deck_pcb_gerbers.zip` | 1 | 5 (minimum) |
| Face, 120 x 120 mm: one side of the triangle reflector core | `out/face_pcb_gerbers.zip` | 3 | 5 (minimum), so order 5 per mast and keep 2 spare, or 10 for 3 masts |

This build replaces the hand-drilled acrylic electronics plate, the bus board / unified stripboard and the hand-cut copper-clad faces. The older deck (`../shield_deck_gerbers.zip`, 146 mm, no parts) and the plate templates stay in `..` for the older build. Status: **generated and DRC-clean, not yet ordered or built** (2026-11-21).

> **Power the mast from PoE OR from USB, never both.** All modules share one 5 V rail. Plugging a USB cable into a XIAO or the ESP32 while the PoE splitter is feeding the deck ties the computer's USB VBUS to the splitter's 5 V. Unplug PoE before connecting USB to flash or read logs. Damage to the boards, the splitter or the computer from ignoring this is not covered by anything in this repo; you build and power it at your own risk. Fitting the optional diodes (below) reduces, but does not remove, the risk.

## Deck

- **Top (electronics side):** a +5 V pour, every part, all hand-solderable. **Bottom (antenna side):** solid GND, the shield. Bottom copper is broken only inside the core (behind the reflectors): the J1 pins and one short CMD track to a via.
- **Holes:** D, P, P2 RP-SMA holes as before (6.5 mm, plated, 12 mm exposed GND pads both sides), a 57 mm centre opening (pipe, ESP32 + PoE bundle end-on, the three dipole coaxes), three M3 holes round it at the core corners for a printed collar or saddle to the pipe. The C holes, the 10 mm core hole and the M4 holes are gone.
- **Exposed copper:** 4 mm rim ring both sides (36 stitching vias in it), the 6 mm seam strip under the faces on the bottom, the RP-SMA pads.
- **Face slots:** three 2.0 x 10.4 mm milled slots per face along the seam lines (at the face centre and 17 mm either side), centred on the face board. Each face's three tabs drop into them, which sets the triangle's position and squareness; then solder the seams as before. The top pour is kept 1 mm clear of every slot.
- **Bottom silkscreen:** guide lines either side of the seam strip and a tick at each face's centre ("FACE Sn CENTRE"), as a cross-check.
- **XIAOs (U2-U4):** on the core corners (60 / 180 / 300 deg), castellated pads lengthened for an iron, USB-C end out to the rim, IPEX4 end inward. Only the right-hand row is wired: 5V, GND, D7 (RX, from the gateway's command TX) and D8 (TX, to the gateway). The left row is solder for strength only. To flash or read logs, take the assembly out of the housing (one nut on the post) and unplug PoE first; the USB-C ports then face straight out at the rim.
- **J1:** JST B7B-PH-K-S (2.0 mm, vertical, through-hole) inside the core at the 60 deg corner; the harness plugs straight down into the board. Pin 1 is marked.

| J1 pin | Net | ESP32-S3-ETH |
| --- | --- | --- |
| 1 | S2 TX | GPIO18 (header 31) |
| 2 | CMD TX | GPIO21 (header 35) |
| 3 | GND | GND |
| 4 | 5 V (through JP4 / D4) | 5V |
| 5 | LED data in | GPIO1 |
| 6 | S0 TX | GPIO17 (header 34) |
| 7 | S1 TX | GPIO16 (header 32) |

The ESP32 stays on the pipe and is fed 5 V through J1, so its USB-C power pigtail goes. A different ESP32 board only needs a new harness.

- **5V IN (J2):** two large pads, + and -. Solder on whatever brings regulated 5 V: a female USB-C pigtail for a PoE splitter with a USB-C plug (the current build), or bare leads.
- **LED strip (J3):** DIN, 5V, GND pads. The 74HCT125 (U1) lifts GPIO1 to 5 V, R1 330 ohm in series, R2 10 k pull-down keeps the strip dark while the ESP32 boots. F1 (2 A, one-time) feeds only the strip; the accepted-risk note in `../README.md` (a strip short reboots the mast) still applies.
- **5 V links, JP1-JP4 and D1-D4:** each module (XIAO S0-S2, ESP32) gets its 5 V through a solder jumper with an SMA Schottky footprint beside it. **Default: bridge each JP with solder, leave D empty.** For diodes: leave JP open and fit D (SS34 or similar 3 A SMA Schottky, about 0.3-0.4 V drop). Either can be changed later.
- **R3:** a 0 ohm 1206 jumper carrying CMD to S1 over the S0 track. Fit it.
- **Tie mounts:** six 12.5 mm squares (TIE 5V IN, TIE LED, TIE J1, TIE Sn COAX) for 1/2 in HS-100 adhesive tie mounts. Mask only underneath, nothing to catch the adhesive.

## Face

Solid GND both sides, one 6.5 mm plated RP-SMA hole at the centre with a 12 mm exposed nut pad, 3 mm of exposed copper along both side edges and the bottom edge (seams to the other faces and to the deck), stitching vias. Three 8 mm tabs on the bottom edge (centre and 17 mm either side), 1.6 mm long so they end flush with the deck's top, copper exposed for soldering into the slots. Silkscreen: centre line, "OUTSIDE - DIPOLE SIDE" / "INSIDE - CORE SIDE", and the deck-edge mark. No M2 posts and no other antenna holes.

## BOM (one mast)

| Ref | Part | Package | Qty |
| --- | --- | --- | --- |
| U1 | 74HCT125 (e.g. TI CD74HCT125M) | SOIC-14 | 1 |
| U2-U4 | Seeed XIAO nRF54L15 | castellated | 3 |
| J1 | JST B7B-PH-K-S; mating PHR-7 housing + SPH-002T-P0.5S crimps | 2.0 mm TH | 1 |
| C1 | 330 uF 10 V polymer tantalum (KEMET T591X337M010ATE025, T545Y337M010ATE035 or T525Y337M010ATE035) | 7343 | 1 |
| C2, C3 | 100 nF X7R | 1206 | 2 |
| R1 | 330 ohm | 1206 | 1 |
| R2 | 10 k | 1206 | 1 |
| R3 | 0 ohm jumper | 1206 | 1 |
| F1 | 2 A fast-acting one-time chip fuse, >= 6 V (check the datasheet's opening time at the splitter's current limit) | 1206 | 1 |
| D1-D4 | SS34 or similar Schottky, optional (see 5 V links) | SMA | 0 or 4 |
| - | Female USB-C power pigtail, optional (PoE splitter with a USB-C plug) | - | 0 or 1 |
| - | 1/2 in HS-100 adhesive tie mounts | - | 6 |
| - | Face PCB | - | 3 |

## Order settings (PCBWay)

Same as the old deck ([../PCBWAY.md](../PCBWAY.md)) except:

| Setting | Deck | Face |
| --- | --- | --- |
| Size | 170 x 170 mm, round (outline, centre opening and the nine face slots in Edge_Cuts) | 120 x 121.6 mm (with the tabs) |
| Silkscreen | White, **both sides** | White, both sides |
| Min hole | 0.4 mm (vias) | 0.4 mm |
| Note to fab | "Round board with a 57 mm internal cutout and nine 2.0 mm milled slots (non-plated). Large copper pours on both layers are intentional (RF shield)." | "Tabs on one edge. Solid copper both sides is intentional (RF reflector)." |

1.6 mm FR-4, 2 layers, 1 oz, HASL lead-free or ENIG (exposed copper must take solder). Check both in PCBWay's Gerber viewer before paying.

## Rebuild

```
python3 make_pcbs.py
```

Needs KiCad 7 or later with its Python module (`pcbnew`) and `kicad-cli` on the path; on Debian / Ubuntu `apt install kicad kicad-footprints`. Sizes and rules come from `../parameters.csv` (groups `pcb`, `face`, plus `deck` for the antenna hole geometry and `plate` for the XIAO size). Part positions and track routes are the tables in `make_pcbs.py`, in each corner's local frame: they are a layout, not measurements, so they live with the code.

Output in `out/`: `*.kicad_pcb` (open in KiCad 7+; KiCad 8 / 10 will upgrade the file on save), `*_gerbers.zip`, `*_drc.rpt`. The DRC report should show **0 errors**; the remaining warnings are silkscreen clipped by the exposed copper and "library not in configuration" for the generated footprints.

Routing is by hand in the script (no autorouter). If you move a part, re-run and read the DRC report: clearances, unconnected nets and courtyard overlaps are all checked there.

## Check a 1:1 print before ordering

`out/pcb_print_1to1.pdf` has three A4 landscape pages: deck top, deck bottom (mirrored, as seen from below), one face. Pads and exposed copper print black, with silkscreen, outline and holes. Print at 100% ("Actual size", not "Fit to page") and measure both 100 mm scale bars on each page before trusting it. Then lay the real parts on it: the XIAOs (castellations on the pads, IPEX4 on its circle), J1, the SOIC, the RP-SMA connectors in their holes, and the pipe and ESP32 bundle through the opening.
