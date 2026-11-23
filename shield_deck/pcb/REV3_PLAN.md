# Shield deck PCB rev 3: plan (settled 2026-11-23, not implemented yet)

Rev 2 (commit 6788740) is what `make_pcbs.py` builds today. Rev 3 moves the radios inside the
core so every net runs inside the shield, drops the LED block and the service switch, and shrinks
the deck. This file is the spec the rev 3 pass implements. Drawing (to scale, top view):
`rev3_layout.png`.

Conventions as in `make_pcbs.py`: angles clockwise from deck 0 (`pol`), corner frame
`loc(theta, u, v)` with u toward the clockwise side and v outward. Core corners (XIAOs) at
60 / 180 / 300, faces (sectors) at 0 / 120 / 240. Usable core: `0.866|u| + 0.5v <= 30.64` (seam
strip inner edge minus `CORE_MARGIN` 1 mm), as `core_ok` checks now.

## Radios

- Three XIAO nRF54L15, one per core corner, on the corner axis, USB-C end outward (toward the
  corner), antenna end inward. Antenna end at v 24.0, centre v 34.5, USB end v 45.0. All castellated
  pads inside the core (the outer pad corners are the tight spot: ~0 mm spare against the 1 mm
  margin). The USB-C plug path (13 x 25 mm past the USB end) runs out over the corner, clear of
  every antenna pad.
- Each radio feeds the sector 60 deg counter-clockwise of it, as in rev 2 (2 o'clock radio ->
  12 o'clock face, 6 -> 4, 10 -> 8 in the drawing).
- Pins follow relay protocol 4 (not yet written up in `scanner_fw/README.md`): D10 uplink TX, D7 command RX,
  D0 / D1 branch RX, 5V, GND.

## Antenna strain relief

- One 12.5 mm tie-mount square per radio (`MOUNT_SQ`), silkscreen only, square to the cable
  trajectory: the square is rotated so two of its sides are perpendicular to the pigtail.
- The pigtail leaves the IPEX4 (`XIAO_IPEX`: 8.25 mm toward the antenna end, 3.9 mm toward the
  D0 edge) at 236 deg in the corner frame (56 deg off straight inward, toward the
  counter-clockwise side), i.e. toward its own sector. Tie centre 13.0 mm from the IPEX along that
  line: corner frame u -14.68, v 18.98 (r 24.0).
- Clearances from that spot: cable and square 7.0 mm from the pipe (owner: keep the cable well
  away from the pipe), square 2.7 mm from the nearest face slot, inside the core.
- Past the tie the pigtail bends ~30 deg and runs over the face line to its sector's D, P or P2
  hole. Add an arrow or dashed silk line from the tie toward the sector.

## Centre hole, registration, mounting

- Round 22.2 mm hole (`ADAPTER_HOLE`), 1/2 in PVC (21.3 mm OD). No key: the three M3 holes
  register the deck. The adapter nut sits outside the core and does not constrain the layout.
  Ethernet runs inside the pipe; no wires pass through the deck.
- Three M3 holes (`COLLAR_HOLE` 3.4 mm), 10 mm washer keep-out each, GND ring, at r 25.5-26.0, angles
  342 / 102 / 222 (in the free ring between the radios, 120 deg apart). Drop the rev 2 bayonet
  lugs and the 62 mm opening (`PCB_OPENING`, `COLLAR_LUG`, `COLLAR_RADIUS` retire or change).

## Connectors and power

- J1: JST PH 4-pin, vertical through-hole, 5V / GND / DATA / CMD (same as the carrier board's Up
  port), at r 17.0, angle 76, next to the head radio. Housing outline on both sides; the builder
  fits it toward the ESP32.
- J2: 5V in from the splitter, two pads (rev 2 style), at r 17.5, angle 322. Same both-side outline.
- Star wiring (protocol 4): the 2 o'clock XIAO is the head. Head D10 -> J1 DATA; the other two
  XIAOs' D10 -> head D0 / D1; J1 CMD -> every D7; J2 -> +5V to every 5V pad.
- +5V as tracks, not a pour: bare top except the tracks; 0.5 mm minimum clearance for +5V nets
  (custom DRC rule); GND pour on the bottom held 2 mm back from +5V pads inside the core. Both
  layers may carry signals inside the core (vias allowed there).
- Removed: SW1 service loop and its silk, the end plate switch hole and RUN / SERVICE silk, the
  back-feed diodes, the whole LED block (U1, R1, R2, C3, F1, J3, J4) and every LED net. The LED
  board is separate and has its own connector to the ESP32.
- C1 bulk cap: not settled in this pass; keep it on +5V near J2 if it fits, else ask.
- Warning silk (deck and faces): "UNPLUG POE BEFORE USB" replaces "SET SERVICE BEFORE USB"; keep
  the disclaimer lines. Assembly steps lose the switch step.

## Antennas and deck size (parametric)

- `DUCK_SPACING` stays a parameter; the generator builds both variants in one run: `deck_d15`
  (15 mm, best in the 2026-11-22 size sweep) and `deck_d31` (31 mm, today's holes). Each gets its
  own board file, Gerber zip, DRC report and print page.
- Deck diameter derived: max(144 mm, 2 x (inradius + spacing + 6 mm pad + 1.5 mm edge margin)) =
  144 mm at 15, ~147 mm at 31. 144 mm = face corners (r 69.3) + 2.7 mm, same as the end plate.
- One antenna per sector (D, P or P2). At 15 mm the D and P pads overlap; they are the same GND
  net and merge (holes stay 1.5 mm apart). Bottom silk per sector: "ONE ANTENNA: D, P OR P2".
- Follows the parameter: rim stitching via radius, silk text positions (move the warning and
  assembly text into the band outside the triangle), tie-mount and slot clearance checks.
- Faces and end plate: unchanged apart from the switch hole and warning text.

## Done when

- [ ] `make_pcbs.py` builds deck_d15, deck_d31, face, end plate; DRC 0 errors on all
- [ ] Gerbers and the 1:1 print PDF regenerated; part clearance table updated
- [ ] `README.md` (build order, BOM, wiring), `CHANGELOG.md`, `pcb_preview.png` updated
- [ ] `parameters.csv`: new rev 3 values, retired rev 2 values marked
