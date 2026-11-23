# Deck, face and end plate PCBs (parts on the deck)

Four boards for PCBWay (or any fab), generated with KiCad from [`make_pcbs.py`](make_pcbs.py). The deck comes in two sizes, one per duck spacing (the D hole's distance in front of each face); order the one that matches your antennas:

| Board | File to upload | Qty per mast | Order |
| --- | --- | --- | --- |
| Deck, 15 mm ducks, 144 mm round: the shield plate the antennas go through, with the three scanners on top | `out/deck_d15_gerbers.zip` | 1 (this or the next) | 5 (minimum) |
| Deck, 31 mm ducks, 146.3 mm round: the same deck with the D holes 31 mm off the faces | `out/deck_d31_gerbers.zip` | 1 (this or the previous) | 5 (minimum) |
| Face, 120 x 120 mm (+ tabs): one side of the triangle reflector core | `out/face_pcb_gerbers.zip` | 3 | 5 (minimum), so order 5 per mast and keep 2 spare, or 10 for 3 masts |
| End plate, 144 mm round, optional: a second shield plate across the far end of the triangle. With 15 mm ducks a second deck board turned over does the same job (see Deck as end plate) | `out/endplate_pcb_gerbers.zip` | 0 or 1 | 5 (minimum) |

This build replaces the hand-drilled acrylic electronics plate, the bus board / unified stripboard and the hand-cut copper-clad faces. The older deck (`../shield_deck_gerbers.zip`, 146 mm, no parts) and the plate templates stay in `..` for the older build. Status: **generated and DRC-clean, not yet ordered or built** (revision 3, 2026-11-23; spec [`REV3_PLAN.md`](REV3_PLAN.md)). Preview: [`pcb_preview.png`](pcb_preview.png).

> **Unplug PoE before plugging in USB.** All modules share one 5 V rail, with no diodes. Plugging a USB cable into a XIAO or the ESP32 while the PoE splitter is feeding the deck ties the computer's USB VBUS to the splitter's 5 V. Power from PoE OR from USB, never both. Damage to the boards, the splitter or the computer from ignoring this is not covered by anything in this repo; you build and power it at your own risk. The same warning is on the deck, on each face and on the end plate, and "UNPLUG POE / BEFORE USB" sits beside each XIAO's USB-C plug path and beside J2 (both sides).

> **Firmware:** this deck wires the radios for relay protocol 4 (star wiring: D10 uplink TX, D0 / D1 branch RX, D7 command RX). That firmware is not written yet; scanner firmware 0.8.0 and older (one TX per radio straight to the gateway) does not work on this deck.

## Build order

The deck's silkscreen carries the same list.

1. Deck: break out the centre knockout and file the bridge nubs flush, so the pipe adapter passes. (A deck board used as the end plate keeps its knockout unless the pipe goes through.)
2. Faces to the deck and the end plate first, on the bare boards: drop all three faces' tabs into the deck slots and the end plate slots together (dry fit), tack, check, then solder the seams. With both plates fitted no squareness jig is needed (see Face). Without the end plate, square the faces by eye or with a printed jig.
3. Clean (IPA).
4. J1 and J2 (either side, see Deck), then the XIAOs.
5. RP-SMAs, coax, antenna strain relief ties.
6. Splitter lead to J2.

To rework a seam later, remove the XIAOs first: their outer pad corners are 1.0 mm from the seam strip (`out/deck_d15_part_clearance.csv`).

## Deck

Revision 3 puts the three radios inside the triangle core, so every net runs inside the shield. The two deck files differ only in the diameter and the D hole positions.

- **Top (electronics side):** bare board except the parts, the +5 V tracks (0.8 mm), the signal stubs to the XIAO pads and the GND rim ring. **Bottom (antenna side):** solid GND, the shield. Inside the core (behind the reflectors, `CORE_MARGIN` 1 mm clear of the seam strip) both layers carry signals: the CMD ring and spokes, the two branch lanes along faces S0 and S2, the head's DATA track to J1, and the J1 / J2 pins. Outside the core the bottom copper is unbroken.
- **Rules:** a custom DRC rule (`out/*.kicad_dru`, written by the generator) keeps +5 V copper at least 0.5 mm from every other net (0.2 mm elsewhere). The bottom GND pour is held 2 mm back from every +5 V pad, inside the core only, so the seam strip stays whole.
- **Size:** diameter = larger of 144 mm (face corners at r 69.3 + 2.7 mm, as the end plate) and 2 x (inradius + duck spacing + 6 mm pad + 1.5 mm edge margin): 144 mm at 15 mm, 146.3 mm at 31 mm.
- **Holes:** D, P, P2 RP-SMA holes (6.5 mm, plated, 12 mm exposed GND pads both sides). One antenna per sector: D, P or P2 ("ONE ANTENNA: D, P OR P2" on the bottom). At 15 mm the D and P pads overlap; they are the same GND net and merge (holes 1.5 mm apart). A centre knockout, the same as the end plate's: a 2 mm routed ring (outer edge 22.2 mm, 7/8 in) held by four 2.5 mm bridges with three 0.5 mm mouse-bite holes each on the plate side, around a disc with a 6.5 mm RP-SMA hole (its own copper, net GND_KO). On a deck, break it out and file the nubs to pass the 1/2 in PVC pipe adapter (21.3 mm OD); no wires pass through the deck, Ethernet runs inside the pipe. Three M3 holes (3.4 mm, plated, 7 mm GND ring both sides) at r 25.75 mm, 342 / 102 / 222 deg, in the free ring between the radios: they register the deck to the collar, with a 10 mm washer keep-out marked on both sides (no tracks or vias in it). The 62 mm opening and the bayonet lugs are gone.
- **Exposed copper:** 4 mm rim ring both sides (36 stitching vias in it), the 6 mm seam strip under the faces on the bottom, the RP-SMA pads, the M3 rings.
- **Face slots:** three 2.0 x 9.4 mm milled slots per face along the seam lines (at the face centre and 17 mm either side), centred on the face board. A 2.0 mm slot has R 1.0 ends, so an 8.0 x 1.6 mm tab needs at least 8.8 mm; 9.4 mm keeps 0.2 mm at +-0.2 mm fab tolerance on tab and slot and leaves +-0.3 mm of slide. Top copper is kept 1 mm clear of every slot.
- **XIAOs (U2-U4):** one per core corner (60 / 180 / 300 deg), on the corner axis, USB-C end out toward the corner, antenna end in: antenna end 24 mm from the centre, centre 34.5 mm, USB-C end 45 mm. All castellated pads (lengthened for an iron) are inside the core; their outer corners are 1.0 mm from the seam strip, right on the 1 mm margin. The USB-C plug path (13 x 25 mm past the USB-C end, drawn on the print) runs out over the corner, clear of every antenna pad. Each radio feeds the sector 60 deg counter-clockwise of it: U2 (2 o'clock) -> S0, U3 (6 o'clock) -> S1, U4 (10 o'clock) -> S2.
- **Wiring (star, relay protocol 4):** U2 is the head. U2 D10 (uplink TX) -> J1 DATA. U3 D10 -> U2 D0 (Branch 1); U4 D10 -> U2 D1 (Branch 2). J1 CMD -> every D7. J1 and J2 5V -> every 5V pad. Each XIAO's GND pad goes by a via to the bottom shield. The other pads are solder for strength only.

| J1 pin | Net | Carrier Up port colour | ESP32-S3-ETH |
| --- | --- | --- | --- |
| 1 | 5V | red | 5V |
| 2 | GND | black | GND |
| 3 | DATA (head D10, uplink) | yellow | a gateway RX pin (GPIO17 = gateway pin 0) |
| 4 | CMD (every D7) | green | GPIO21 (command TX) |

- **J1:** JST B4B-PH-K-S (2.0 mm, vertical, through-hole), the same pinout as the XIAO carrier board's Up port, at r 17 mm, 76 deg, next to the head; pin row tangential, pin 1 (square pad) at the clockwise end. Its housing outline is printed on both sides: fit it on whichever side faces the ESP32.
- **J2 (5V in from the splitter):** a JST PH 2-pin footprint (B2B-PH-K-S), pin 1 = +5 V, pin 2 = GND, at r 17.5 mm, 322 deg, outline on both sides. Fit a B2B-PH-K-S and crimp the splitter lead, or solder the lead straight into the holes (0.75 mm drill, up to about 24 AWG).
- **Antenna strain relief ties:** three 12.5 mm squares ("ANT STRAIN RELIEF TIE"), one per XIAO pigtail, for 1/2 in HS-100 adhesive tie mounts (mask only underneath). Each pigtail leaves its IPEX4 at 236 deg in the corner frame (56 deg off straight in, toward its own sector); the square sits 15 mm along it (r 24.2 mm; 13 in the spec, moved out so it sits 3.3 mm clear of the XIAO and stays visible once the XIAO is on), turned so two sides are square to the cable. A dotted line runs from the IPEX4 marker along the pigtail through the square, then bends about 30 deg toward its sector's D, P or P2 hole and ends in an arrow before the face slots. Clearances, checked by the generator (KiCad's DRC can't see silkscreen-only footprints): 6.6 mm from the 22.2 mm hole edge (7.0 mm from the 21.3 mm pipe), 1.4 mm from the nearest face slot, 3.1 mm from the M3 washer keep-out, 2.2 mm from the nearest pad.
- **C1 (bulk capacitor): not on this revision.** The 8 mm dual footprint (SMD 8 x 10 or radial, 11 x 9.2 mm courtyard) has no clear spot inside the core. A search of the routed board found room for an 8 mm radial can only near the 6 o'clock XIAO (r 19.5 mm, 194 deg, about 33 mm from J2), and for a 6.3 mm can about 7 mm from J2 (r 19 mm, 300 deg). Open: owner to choose.
- **Removed in revision 3:** the LED block (U1, R1, R2, C2, C3, F1, J3, J4) and every LED net (the LED board has its own connector to the ESP32), the service switch loop SW1 and its silkscreen, the back-feed diodes, R3, the collar arrows.
- **Heat near the seams:** there is no hard keep-out. The XIAO pads are 1.0 mm from the seam strip and 7.0 mm from the nearest slot; J1 and J2 are 16 mm away (`out/deck_d15_part_clearance.csv`). Soldering the faces first, on the bare boards, is what protects them.
- **Bottom silkscreen:** guide lines either side of the seam strip, a tick at each face's centre ("FACE Sn CENTRE"), "ONE ANTENNA: D, P OR P2" per sector, "SOLDER FACES BEFORE ANY PARTS", "THIS SIDE TO THE CORE (AS DECK OR END PLATE)", the duck spacing, the J1 / J2 outlines, the repo URL.
- **Repo URL:** `github.com/100-Ton-Robot/ble-beacon-tracker` is on every silkscreen: both sides of the deck, the face and the end plate.
- **Deck as end plate:** with 15 mm ducks the deck and the end plate are both 144 mm, so a second deck board turned over (bottom up, to the core) works as the end plate: its seam strip faces the faces, the slots are symmetric, and its knockout stays in for a downward antenna (or comes out for the pipe). The XIAO, J1 / J2 pads and +5 V tracks end up outside, unused and unpowered; "AS END PLATE: THIS SIDE OUT, NO PARTS" is on the top. The RF model gives the same result as the end plate PCB (`../../rf_model/README.md`). At 31 mm the deck is 146.3 mm, past the ~146 mm where the earlier simulation saw a plate start to block the ducks' downward view: use the end plate PCB there. The end plate PCB stays as the option for both.

## Face

Solid GND both sides, one 6.5 mm plated RP-SMA hole at the centre with a 12 mm exposed nut pad, 3 mm of exposed copper along all four edges (seams to the other faces, the deck and the end plate), stitching vias. One design serves both plates: three 8 mm tabs on each end edge (centre and 17 mm either side), 1.6 mm long so they end flush with the deck's top and the end plate's outside, copper exposed for soldering into the slots. A router can't cut a sharp inside corner, so each tab root has a 2.2 x 1.2 mm relief notch on both sides: the bit's corner radius lands in the notch, and the edge that seats on the plate stays straight up to the tab. The notches end 23 mm from the face centre, well clear of the corners; the 2.2 mm gaps are far below a wavelength (~125 mm at 2.4 GHz) and the seam solder fills them. Tabs alone don't square a face (a 1.6 mm board in a 2.0 mm slot, 1.6 mm deep, can tilt up to ~19 deg), but held by both plates 120 mm apart the tilt is at most ~0.3 deg. Silkscreen: centre line, "OUTSIDE - DIPOLE SIDE" / "INSIDE - CORE SIDE", the tab marks at both ends and the power warning on the outside. No M2 posts and no other antenna holes.

## End plate (optional)

A second shield plate across the far end of the triangle, `FACE_H` (120 mm) below the deck. The RF model (openEMS, 2026-11-22) gave median bearing error 20 -> 16 deg and better back rejection at steep downward angles with a 140 mm plate; 144 mm was chosen to leave 2.7 mm of plate past the face corners (r 69.3 mm) and is under the ~146 mm where the plate starts to reach past the ducks. 144 mm itself was not simulated.

- **Copper:** solid GND both sides with stitching vias, no parts. The 6 mm seam strip is exposed on the inside (top), where the faces solder on.
- **Face slots:** the same nine 2.0 x 9.4 mm slots as the deck, with the same guide lines and face centre ticks.
- **Centre:** a 6.5 mm plated RP-SMA hole for a downward antenna, in a knockout. The knockout is a 2 mm routed ring (outer edge 22.2 mm, 7/8 in) held by four 2.5 mm bridges with three 0.5 mm mouse-bite holes each, on the plate side. Break it out (and file the nubs) to pass the 1/2 in PVC male adapter thread (21.3 mm OD). The disc is its own copper (net GND_KO), not tied to the plate once the ring is routed; an antenna in it is grounded through its coax.
- **Adapter:** the pipe glues into the adapter's socket from above, the adapter's shoulder sits on the plate inside the core, the thread goes down through the knockout and a 1/2 in IPS faucet mounting lock nut on the outside clamps the plate (mechanical only, no seal). A 54 mm keep-clear ring is marked on both sides (lock nut estimated at 50 mm across). Check on the dry fit that the assembly still comes out of the housing on the one post nut.
- **Silkscreen:** inside: "END PLATE - INSIDE", the build-order note; outside: the power warning, the knockout note. Revision 3 removed the service switch hole and its "RUN" / "SERVICE" marks.

## BOM (one mast)

| Ref | Part | Package | Qty |
| --- | --- | --- | --- |
| U2-U4 | Seeed XIAO nRF54L15 | castellated | 3 |
| J1 | JST B4B-PH-K-S; mating PHR-4 housing + SPH-002T-P0.5S crimps (4-wire harness to the ESP32, as the carrier Up port) | 2.0 mm TH | 1 |
| J2 | JST B2B-PH-K-S; mating PHR-2 + crimps on the splitter lead (or solder the lead into the holes) | 2.0 mm TH | 0 or 1 |
| - | 1/2 in HS-100 adhesive tie mounts | - | 3 |
| - | Deck PCB (15 or 31 mm ducks) | - | 1 |
| - | Face PCB | - | 3 |
| - | End plate PCB, optional | - | 0 or 1 |
| - | 1/2 in IPS faucet mounting lock nut (with the end plate and the pipe through it) | - | 0 or 1 |

C1 (bulk capacitor) is not on revision 3; see Deck.

## Order settings (PCBWay)

Same as the old deck ([../PCBWAY.md](../PCBWAY.md)) except:

| Setting | Deck | Face | End plate |
| --- | --- | --- | --- |
| Size | 144 x 144 mm (15 mm ducks) or 146.3 x 146.3 mm (31 mm ducks), round (outline, the knockout ring and the nine face slots in Edge_Cuts) | 120 x 123.2 mm (with the tabs) | 144 x 144 mm, round |
| Silkscreen | White, **both sides** | White, both sides | White, both sides |
| Min hole | 0.4 mm (vias) | 0.4 mm | 0.4 mm (vias); 0.5 mm mouse bites |
| Note to fab | "Round board, nine 2.0 mm milled slots (non-plated) and a routed centre knockout ring with mouse-bite bridges (keep the bridges). Large copper pour on the bottom is intentional (RF shield)." | "Tabs on two edges. Solid copper both sides is intentional (RF reflector)." | "Round board, nine 2.0 mm milled slots and a routed knockout ring with mouse-bite bridges (keep the bridges). Solid copper both sides is intentional (RF shield)." |

1.6 mm FR-4, 2 layers, 1 oz, HASL lead-free or ENIG (exposed copper must take solder). Check each in PCBWay's Gerber viewer before paying.

## Rebuild

```
python3 make_pcbs.py
```

Needs KiCad 7 or later with its Python module (`pcbnew`) and `kicad-cli` on the path (on Debian / Ubuntu `apt install kicad kicad-footprints`), plus `pip install shapely pypdf pillow` (tie-mount clearance check, seam distance table, merged print PDF, preview) and `rsvg-convert` (preview). Sizes and rules come from `../parameters.csv` (groups `pcb`, `face`, `endplate`, plus `deck` for the antenna hole geometry; `DECK_VARIANTS` lists the duck spacings built; `plate` for the XIAO size and `ADAPTER_HOLE` from `pipe`). Part positions and track routes are the tables in `make_pcbs.py`, in each corner's local frame: they are a layout, not measurements, so they live with the code.

Output in `out/`: `*.kicad_pcb` (open in KiCad 7+; KiCad 8 / 10 will upgrade the file on save), `*_gerbers.zip`, `*_drc.rpt`, `*.kicad_dru` (the +5 V clearance rule; keep it next to its board), `deck_d*_part_clearance.csv`, `*_copper.json` (each board's copper as polygons plus its plated holes, for the RF model: `../../rf_model/sector_model.py --deck d15 --copper`), and `../pcb_preview.png`. The DRC reports should show **0 errors**; the remaining warnings are silkscreen clipped by the exposed copper, "library not in configuration" for the generated footprints, and on the end plate "isolated copper fill" (its GND pour has no pads, only vias).

Routing is by hand in the script (no autorouter). If you move a part, re-run and read the DRC report: clearances, unconnected nets and courtyard overlaps are all checked there.

## Check a 1:1 print before ordering

`out/pcb_print_1to1.pdf` has seven A4 landscape pages: 15 mm deck top and bottom (mirrored, as seen from below), 31 mm deck top and bottom, one face, end plate inside, end plate outside (mirrored). Pads and exposed copper print black, with silkscreen, outline and holes. Print at 100% ("Actual size", not "Fit to page") and measure both 100 mm scale bars on each page before trusting it. Then lay the real parts on it: the XIAOs (castellations on the pads, IPEX4 on its circle; the outer pad corners have no spare against the core margin), a USB-C plug in each drawn plug path, J1 and J2, the tie mounts on their squares with a pigtail run to its sector's holes, the RP-SMA connectors in their holes, the pipe adapter in the 22.2 mm hole, an M3 washer on each 10 mm circle and the adapter / lock nut in the end plate's knockout ring.
