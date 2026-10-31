"""Experiment: build the shield deck as a KiCad board from the same geometry as make_shield_deck.py.

Writes shield_deck.kicad_pcb (plain s-expression text, no KiCad needed for this step). Then
build.py runs kicad-cli to fill the copper zone, check DRC and export Gerbers + drill, and
compare.py checks them against ../../shield_deck/shield_deck_gerbers.zip.

Nothing in shield_deck/ is changed; the geometry is imported from it.
"""
import math
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "shield_deck"))
import make_shield_deck as deck  # noqa: E402

# KiCad's y axis points down. Put the deck's lower-left corner at (OX, OY) on the sheet and make
# that the drill/plot origin, so exported coordinates match the script's Gerbers 1:1.
OX, OY = 50.0, 50.0 + deck.DISC_DIAMETER


def k(p):
    return f"{OX + p[0]:.4f} {OY - p[1]:.4f}"


def uid():
    return f'(uuid "{uuid.uuid4()}")'


LAYERS = """  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings")
    (41 "Cmts.User" user "User.Comments")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
  )"""


def footprint(ref, d, x, y, mask_open):
    # Plated hole tied to GND. RP-SMA holes get a pad the size of the exposed nut-contact ring so the
    # mask opening comes from the pad itself; the others are copper-only (mask stays on, as in the script).
    if mask_open:
        size, layers = deck.PAD_EXPOSE, '"*.Cu" "*.Mask"'
    else:
        size, layers = d + 1.0, '"*.Cu"'
    return f"""  (footprint "deck:Hole_{d:g}mm" (layer "F.Cu") {uid()} (at {k((x, y))})
    (property "Reference" "{ref}" (at 0 0 0) (layer "F.Fab") {uid()}
      (effects (font (size 1 1) (thickness 0.15))))
    (property "Value" "Hole_{d:g}mm" (at 0 1.5 0) (layer "F.Fab") {uid()}
      (effects (font (size 1 1) (thickness 0.15))))
    (attr exclude_from_pos_files exclude_from_bom)
    (pad "1" thru_hole circle (at 0 0) (size {size:g} {size:g}) (drill {d:g}) (layers {layers})
      (net 1 "GND") (zone_connect 2) {uid()})
  )"""


def line(a, b, width, layer):
    return (f'  (gr_line (start {k(a)}) (end {k(b)}) (stroke (width {width:g}) (type solid)) '
            f'(layer "{layer}") {uid()})')


def circle(c, r, width, layer, filled=False):
    fill = "solid" if filled else "none"
    return (f'  (gr_circle (center {k(c)}) (end {k((c[0] + r, c[1]))}) '
            f'(stroke (width {width:g}) (type solid)) (fill {fill}) (layer "{layer}") {uid()})')


def board():
    centre = (deck.CX, deck.CY)
    out = [f"""(kicad_pcb (version 20240108) (generator "make_deck_kicad") (generator_version "8.0")
  (general (thickness 1.6) (legacy_teardrops no))
  (paper "A4")
{LAYERS}
  (setup
    (pad_to_mask_clearance 0)
    (allow_soldermask_bridges_in_footprints no)
    (aux_axis_origin {OX:g} {OY:g})
    (grid_origin {OX:g} {OY:g})
  )
  (net 0 "")
  (net 1 "GND")"""]

    n = 0
    for d, x, y, label in deck.holes:
        if label == "via":
            out.append(f'  (via (at {k((x, y))}) (size {d + 0.4:g}) (drill {d:g}) (layers "F.Cu" "B.Cu") '
                       f'(net 1) {uid()})')
        else:
            n += 1
            out.append(footprint(f"H{n}", d, x, y, mask_open=(d == deck.HOLE_RPSMA)))

    # Board outline
    out.append(circle(centre, deck.R, 0.1, "Edge.Cuts"))

    # Mask openings (KiCad mask layers are negative: drawn = bare copper)
    ring_r = deck.R - deck.RIM_MASK_WIDTH / 2
    for layer in ("F.Mask", "B.Mask"):
        out.append(circle(centre, ring_r, deck.RIM_MASK_WIDTH, layer))
    for a, b in deck.seams:
        out.append(line(a, b, deck.SEAM_STRIP, "B.Mask"))

    # Silkscreen: same stroke font as the script, for a like-for-like comparison
    for stroke in deck.silk:
        for a, b in zip(stroke, stroke[1:]):
            out.append(line(a, b, 0.25, "F.SilkS"))

    # Solid GND pour on both sides. Drawn as a square larger than the disc; KiCad trims it to the
    # board edge minus the copper-to-edge clearance (EDGE_CLEAR, set in the .kicad_pro rules below).
    s = deck.DISC_DIAMETER + 2
    sq = [(-1, -1), (s - 1, -1), (s - 1, s - 1), (-1, s - 1)]
    pts = " ".join(f"(xy {k(p)})" for p in sq)
    out.append(f"""  (zone (net 1) (net_name "GND") (layers "F.Cu" "B.Cu") {uid()} (name "shield")
    (hatch edge 0.5)
    (connect_pads yes (clearance 0.3))
    (min_thickness 0.25) (filled_areas_thickness no)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts {pts}))
  )""")
    out.append(")")
    return "\n".join(out) + "\n"


def project():
    # Minimal project file: board edge clearance = the script's copper pull-back, 0.6 mm min drill
    return """{
  "board": {
    "design_settings": {
      "rules": {
        "min_copper_edge_clearance": %g,
        "min_through_hole_diameter": 0.6,
        "min_via_diameter": 0.9,
        "min_via_annular_width": 0.15,
        "min_hole_clearance": 0.25,
        "min_clearance": 0.2
      }
    }
  },
  "meta": {"filename": "shield_deck.kicad_pro", "version": 1}
}
""" % deck.EDGE_CLEAR


def main():
    with open(os.path.join(HERE, "shield_deck.kicad_pcb"), "w", newline="\n") as f:
        f.write(board())
    with open(os.path.join(HERE, "shield_deck.kicad_pro"), "w", newline="\n") as f:
        f.write(project())
    print("wrote shield_deck.kicad_pcb and shield_deck.kicad_pro")


if __name__ == "__main__":
    main()
