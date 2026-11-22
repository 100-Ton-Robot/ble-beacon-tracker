# Deck, face and end plate PCBs (parts on the deck)

Three boards for PCBWay (or any fab), generated with KiCad from [`make_pcbs.py`](make_pcbs.py):

| Board | File to upload | Qty per mast | Order |
| --- | --- | --- | --- |
| Deck, 170 mm round: the shield plate the antennas go through, with the scanners and power on top | `out/deck_pcb_gerbers.zip` | 1 | 5 (minimum) |
| Face, 120 x 120 mm (+ tabs): one side of the triangle reflector core | `out/face_pcb_gerbers.zip` | 3 | 5 (minimum), so order 5 per mast and keep 2 spare, or 10 for 3 masts |
| End plate, 144 mm round, optional: a second shield plate across the far end of the triangle; carries the service switch | `out/endplate_pcb_gerbers.zip` | 0 or 1 | 5 (minimum) |

This build replaces the hand-drilled acrylic electronics plate, the bus board / unified stripboard and the hand-cut copper-clad faces. The older deck (`../shield_deck_gerbers.zip`, 146 mm, no parts) and the plate templates stay in `..` for the older build. Status: **generated and DRC-clean, not yet ordered or built** (revision 2, 2026-11-22). Preview: [`pcb_preview.png`](pcb_preview.png).

> **Set the service switch to SERVICE before plugging in USB.** All modules share one 5 V rail, with no diodes. Plugging a USB cable into a XIAO or the ESP32 while the PoE splitter is feeding the deck ties the computer's USB VBUS to the splitter's 5 V. The service switch (SW1, below) cuts the splitter's feed; without a switch, unplug PoE instead. Power from PoE OR from USB, never both. Damage to the boards, the splitter or the computer from ignoring this is not covered by anything in this repo; you build and power it at your own risk. The same warning is on the deck, on each face and on the end plate.

## Build order

The deck's silkscreen carries the same list.

1. Faces to the deck and the end plate first, on the bare boards: drop all three faces' tabs into the deck slots and the end plate slots together (dry fit), tack, check, then solder the seams. With both plates fitted no squareness jig is needed (see Face). Without the end plate, square the faces by eye or with a printed jig.
2. Clean (IPA).
3. SMD parts, then J1 and J4, then the XIAOs.
4. C1: the SMD can or the radial can, not both.
5. RP-SMAs, coax, tie mounts.
6. Power lead to J2.
7. Service switch installed: cut SW1's neck, wire the switch to SW1 A and B, then check that SERVICE gives no power on the rail.

To rework a seam later, remove the parts near it first: the deck's part distances to the seam strip are in `out/deck_part_clearance.csv` (several sit right over it, see Deck).

## Deck

- **Top (electronics side):** a +5 V pour, every part, all hand-solderable. **Bottom (antenna side):** solid GND, the shield. Bottom copper is broken only inside the core (behind the reflectors): the J1, J4 and C1 radial pins, one short CMD track and one short BUF track (under the collar M3 in the 180 deg corner), each through a via.
- **Holes:** D, P, P2 RP-SMA holes as before (6.5 mm, plated, 12 mm exposed GND pads both sides), a 62 mm centre opening (pipe, ESP32 + PoE bundle end-on, the three dipole coaxes, the end plate's switch wires) with three 3 mm bayonet lugs at the core corners (tips ~56 mm apart), and three M3 holes at r 41 mm on the core corners, inside the triangle. A printed collar on the bottom, inside the triangle, takes the lugs and the M3s; it locks clockwise seen from the bottom ("LOCK" / "OPEN" arrows on the bottom silkscreen, "COLLAR LOCKS FROM BOTTOM" on top). 62 mm is the most the centre face slots allow (1.8 mm of board between the opening and their inner edge).
- **Exposed copper:** 4 mm rim ring both sides (36 stitching vias in it), the 6 mm seam strip under the faces on the bottom, the RP-SMA pads.
- **Face slots:** three 2.0 x 9.4 mm milled slots per face along the seam lines (at the face centre and 17 mm either side), centred on the face board. A 2.0 mm slot has R 1.0 ends, so an 8.0 x 1.6 mm tab needs at least 8.8 mm; 9.4 mm keeps 0.2 mm at +-0.2 mm fab tolerance on tab and slot and leaves +-0.3 mm of slide. The top pour is kept 1 mm clear of every slot.
- **Bottom silkscreen:** guide lines either side of the seam strip, a tick at each face's centre ("FACE Sn CENTRE"), "SOLDER FACES BEFORE ANY PARTS", the collar arrows.
- **XIAOs (U2-U4):** on the core corners (60 / 180 / 300 deg), castellated pads lengthened for an iron, USB-C end out to the rim, IPEX4 end inward. Only the right-hand row is wired: 5V (straight onto the +5 V pour), GND, D7 (RX, from the gateway's command TX) and D8 (TX, to the gateway). The left row is solder for strength only. To flash or read logs, take the assembly out of the housing (one nut on the post) and set the service switch first; the USB-C ports then face straight out at the rim.
- **J1:** JST B7B-PH-K-S (2.0 mm, vertical, through-hole) inside the core at the 60 deg corner, pin row 48 mm out (clear of the collar M3); the harness plugs straight down into the board. Pin 1 is the square pad.

| J1 pin | Net | ESP32-S3-ETH |
| --- | --- | --- |
| 1 | S2 TX | GPIO18 (header 31) |
| 2 | CMD TX | GPIO21 (header 35) |
| 3 | GND | GND |
| 4 | 5 V (straight from the rail) | 5V |
| 5 | LED data in | GPIO1 |
| 6 | S0 TX | GPIO17 (header 34) |
| 7 | S1 TX | GPIO16 (header 32) |

The ESP32 stays on the pipe and is fed 5 V through J1, so its USB-C power pigtail goes. A different ESP32 board only needs a new harness.

- **5V IN (J2) and the service switch (SW1):** outside the signal band at the 180 deg corner, beside XIAO S1. J2 is two large pads, + and -: solder on whatever brings regulated 5 V (a female USB-C pigtail for a PoE splitter with a USB-C plug, or bare leads). J2 + feeds SW1 pad A; SW1 pad B feeds the +5 V pour. SW1 is a copper U: A and B are the contact pads at its tips, and its bridge ships **closed**, so a deck without a switch needs nothing. To fit the service switch, cut the bridge at its narrow neck (1.5 x 2 mm, between the silkscreen brackets, "CUT IF SWITCH INSTALLED") and wire the switch to A and B. The bridge is 2.5 mm copper and the neck 1.5 mm (1 oz: ~1.1 mm carries 3 A at a 10 C rise, IPC-2221 outer layer). Then check: switch on SERVICE, no power on the rail.
- **Service mode:** with SW1 open and a USB cable plugged into one module, that cable feeds the whole rail (ESP32, the other XIAOs, the LED strip's idle current) from a port that may give only 500 mA. Not measured.
- **LED strip (J3, J4):** J3 is three pads for a JST-SM pigtail, J4 a 1 x 3 2.54 mm male header (Dupont, through-hole, inside the core); both are 5V / DIN / GND in that order, pin 1 (5V) the square pad on J4. The 74HCT125 (U1, channel 3; the other channels tied off) lifts GPIO1 to 5 V, R1 330 ohm in series, R2 10 k pull-down keeps the strip dark while the ESP32 boots. F1 (2 A, one-time) feeds only the strip.
- **Strip short (accepted risk):** the splitter current-limits at about 2.6 A (estimated), about 130 % of F1's rating. The 466 series opens within 5 s at 200 % and 0.2 s at 300 % but has no maximum opening time below 200 %, so a short on the strip can sit on the splitter's limit and reboot the mast until it is cleared, as accepted for the stripboard build in `../README.md`.
- **C1:** one 8 mm can footprint, two ways: SMD (8 x 10 mm can pads) or radial (3.5 mm lead pitch), overlapping, same nets on the same side (+ marked). The radial leads come through inside the core, so clipped leads sit behind the reflectors.
- **R3:** a 0 ohm 1206 jumper carrying CMD to S1 over the S0 track. Fit it.
- **Tie mounts:** six 12.5 mm squares (TIE 5V IN, TIE LED, TIE J1, TIE Sn COAX) for 1/2 in HS-100 adhesive tie mounts. Mask only underneath, nothing to catch the adhesive. The generator places each one at the clear spot nearest its preferred position, `MOUNT_GAP` (1 mm) clear of the slots, the opening, holes, pads, courtyards and silkscreen text, inside the rim ring (KiCad's DRC can't check silkscreen-only footprints).
- **Heat near the seams:** there is no hard keep-out. The XIAOs sit over the corner seams, and U1, R2, R3, C3 and J3 overlap the seam strip in plan; J1, J4, C1, R1, F1 and C2 are 1-4 mm from it (`out/deck_part_clearance.csv`, pad edge to seam strip and to slot). Soldering the faces first, on the bare boards, is what protects them.

## Face

Solid GND both sides, one 6.5 mm plated RP-SMA hole at the centre with a 12 mm exposed nut pad, 3 mm of exposed copper along all four edges (seams to the other faces, the deck and the end plate), stitching vias. One design serves both plates: three 8 mm tabs on each end edge (centre and 17 mm either side), 1.6 mm long so they end flush with the deck's top and the end plate's outside, copper exposed for soldering into the slots. A router can't cut a sharp inside corner, so each tab root has a 2.2 x 1.2 mm relief notch on both sides: the bit's corner radius lands in the notch, and the edge that seats on the plate stays straight up to the tab. The notches end 23 mm from the face centre, well clear of the corners; the 2.2 mm gaps are far below a wavelength (~125 mm at 2.4 GHz) and the seam solder fills them. Tabs alone don't square a face (a 1.6 mm board in a 2.0 mm slot, 1.6 mm deep, can tilt up to ~19 deg), but held by both plates 120 mm apart the tilt is at most ~0.3 deg. Silkscreen: centre line, "OUTSIDE - DIPOLE SIDE" / "INSIDE - CORE SIDE", the tab marks at both ends and the power warning on the outside. No M2 posts and no other antenna holes.

## End plate (optional)

A second shield plate across the far end of the triangle, `FACE_H` (120 mm) below the deck. The RF model (openEMS, 2026-11-22) gave median bearing error 20 -> 16 deg and better back rejection at steep downward angles with a 140 mm plate; 144 mm was chosen to leave 2.7 mm of plate past the face corners (r 69.3 mm) and is under the ~146 mm where the plate starts to reach past the ducks. 144 mm itself was not simulated.

- **Copper:** solid GND both sides with stitching vias, no parts. The 6 mm seam strip is exposed on the inside (top), where the faces solder on.
- **Face slots:** the same nine 2.0 x 9.4 mm slots as the deck, with the same guide lines and face centre ticks.
- **Centre:** a 6.5 mm plated RP-SMA hole for a downward antenna, in a knockout. The knockout is a 2 mm routed ring (outer edge 22.2 mm, 7/8 in) held by four 2.5 mm bridges with three 0.5 mm mouse-bite holes each, on the plate side. Break it out (and file the nubs) to pass the 1/2 in PVC male adapter thread (21.3 mm OD). The disc is its own copper (net GND_KO), not tied to the plate once the ring is routed; an antenna in it is grounded through its coax.
- **Adapter:** the pipe glues into the adapter's socket from above, the adapter's shoulder sits on the plate inside the core, the thread goes down through the knockout and a 1/2 in IPS faucet mounting lock nut on the outside clamps the plate (mechanical only, no seal). A 54 mm keep-clear ring is marked on both sides (lock nut estimated at 50 mm across). Check on the dry fit that the assembly still comes out of the housing on the one post nut.
- **Service switch:** a 6.5 mm hole at the 180 deg corner (below the deck's J2 / SW1), 45 mm from the centre, inside the triangle, for a panel-mount SPST toggle rated at least 3 A DC with a 1/4 in bushing. Body inside the core, lever below, reachable from underneath (the mast hangs from the ceiling). Mount it so the lever points at "RUN" when closed and at "SERVICE" when open. Its two wires run up the core and through the deck opening to SW1 A and B (cut SW1's bridge first). Without an end plate, a switch can go in the pigtail's + lead instead.
- **Silkscreen:** inside: "END PLATE - INSIDE", the build-order note, the switch note; outside: "RUN" / "SERVICE", the power warning, the knockout note.

## BOM (one mast)

| Ref | Part | Package | Qty |
| --- | --- | --- | --- |
| U1 | 74HCT125 (e.g. TI CD74HCT125M) | SOIC-14 | 1 |
| U2-U4 | Seeed XIAO nRF54L15 | castellated | 3 |
| J1 | JST B7B-PH-K-S; mating PHR-7 housing + SPH-002T-P0.5S crimps | 2.0 mm TH | 1 |
| J3 | JST-SM 3-pin pigtail for the LED strip (soldered to the pads), optional | - | 0 or 1 |
| J4 | 1 x 3 male pin header, 2.54 mm, vertical | TH | 1 |
| C1 | 330 uF >= 10 V low-ESR aluminium (polymer or standard), 8 mm can: SMD 8 x 10 mm or radial 3.5 mm pitch; part number to pick | 8 mm can | 1 |
| C2, C3 | 100 nF X7R | 1206 | 2 |
| R1 | 330 ohm | 1206 | 1 |
| R2 | 10 k | 1206 | 1 |
| R3 | 0 ohm jumper | 1206 | 1 |
| F1 | Littelfuse 0466002.NR: 2 A very fast-acting, one-time, 63 V, 50 A interrupt (alternate Bourns SF-1206F200-2) | 1206 | 1 |
| SW1 | Copper loop on the deck; with the end plate: panel-mount SPST toggle, >= 3 A DC, 1/4 in bushing (part number to pick) | - | 0 or 1 |
| - | Female USB-C power pigtail, optional (PoE splitter with a USB-C plug) | - | 0 or 1 |
| - | 1/2 in HS-100 adhesive tie mounts | - | 6 |
| - | Face PCB | - | 3 |
| - | End plate PCB, optional | - | 0 or 1 |
| - | 1/2 in IPS faucet mounting lock nut (with the end plate and the pipe through it) | - | 0 or 1 |

## Order settings (PCBWay)

Same as the old deck ([../PCBWAY.md](../PCBWAY.md)) except:

| Setting | Deck | Face | End plate |
| --- | --- | --- | --- |
| Size | 170 x 170 mm, round (outline, centre opening with lugs and the nine face slots in Edge_Cuts) | 120 x 123.2 mm (with the tabs) | 144 x 144 mm, round |
| Silkscreen | White, **both sides** | White, both sides | White, both sides |
| Min hole | 0.4 mm (vias) | 0.4 mm | 0.4 mm (vias); 0.5 mm mouse bites |
| Note to fab | "Round board with a 62 mm internal cutout (three lugs) and nine 2.0 mm milled slots (non-plated). Large copper pours on both layers are intentional (RF shield)." | "Tabs on two edges. Solid copper both sides is intentional (RF reflector)." | "Round board, nine 2.0 mm milled slots and a routed knockout ring with mouse-bite bridges (keep the bridges). Solid copper both sides is intentional (RF shield)." |

1.6 mm FR-4, 2 layers, 1 oz, HASL lead-free or ENIG (exposed copper must take solder). Check each in PCBWay's Gerber viewer before paying.

## Rebuild

```
python3 make_pcbs.py
```

Needs KiCad 7 or later with its Python module (`pcbnew`) and `kicad-cli` on the path (on Debian / Ubuntu `apt install kicad kicad-footprints`), plus `pip install shapely pypdf` (tie-mount clearance check, seam distance table, merged print PDF). Sizes and rules come from `../parameters.csv` (groups `pcb`, `face`, `endplate`, plus `deck` for the antenna hole geometry, `plate` for the XIAO size and `ADAPTER_HOLE` from `pipe`). Part positions and track routes are the tables in `make_pcbs.py`, in each corner's local frame: they are a layout, not measurements, so they live with the code.

Output in `out/`: `*.kicad_pcb` (open in KiCad 7+; KiCad 8 / 10 will upgrade the file on save), `*_gerbers.zip`, `*_drc.rpt`, `deck_part_clearance.csv`. The DRC reports should show **0 errors**; the remaining warnings are silkscreen clipped by the exposed copper or a board edge, "library not in configuration" for the generated footprints, and on the end plate "isolated copper fill" (its GND pour has no pads, only vias).

Routing is by hand in the script (no autorouter). If you move a part, re-run and read the DRC report: clearances, unconnected nets and courtyard overlaps are all checked there.

## Check a 1:1 print before ordering

`out/pcb_print_1to1.pdf` has five A4 landscape pages: deck top, deck bottom (mirrored, as seen from below), one face, end plate inside, end plate outside (mirrored). Pads and exposed copper print black, with silkscreen, outline and holes. Print at 100% ("Actual size", not "Fit to page") and measure both 100 mm scale bars on each page before trusting it. Then lay the real parts on it: the XIAOs (castellations on the pads, IPEX4 on its circle), J1, J4, the SOIC, C1, the RP-SMA connectors in their holes, the pipe and ESP32 bundle through the opening, the toggle in its hole and the adapter / lock nut in the knockout ring.
