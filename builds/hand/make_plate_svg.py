"""Electronics plates as Inkscape SVGs for laying out by hand, drawn from parameters.csv:

  plate_layout.svg       alt split plate (page 2): S0, S1, S2, ESP32 and bus board each move on their own
  pipe_plate_layout.svg  pipe plate (page 3): move S0 and the bus board; S1 / S2 are clones of S0 turned 120 deg

Each part is one group (its own layer) holding its outline and the holes it needs, so dragging / rotating the group
moves its holes with it. Tie holes and the bus M3 hole are sub-groups: enter the group (double-click) and drag them
along the part to move them. The plate, its M4 bolt holes, the antenna holes (dotted, reference only: drillable but not by design) and the deck jacks below
are locked reference layers. After moving parts, run  python read_plate_svg.py  to write the new positions back into
parameters.csv and check the clearance rules, then  python make_templates.py  for the PDF.

1 user unit = 1 mm, top view, plate 12 o'clock up. Parts drawn dashed hang under the plate (seen through it).
Run:  python make_plate_svg.py
"""
import math
import os

import make_shield_deck as g
import make_templates as t

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = {"alt": "plate_layout.svg", "pipe": "pipe_plate_layout.svg"}
VIEWBOX = "-85 -85 170 196"     # read_plate_svg.py refuses a file whose page was changed

HOLE = 'fill="none" stroke="#d40000" stroke-width="0.3"'
UNDER = 'fill="none" stroke="#3060a0" stroke-width="0.35" stroke-dasharray="1.5,1"'
MOUNT = 'fill="#3060a0" fill-opacity="0.12" stroke="#3060a0" stroke-width="0.35" stroke-dasharray="1.5,1"'
REF = 'fill="none" stroke="#999" stroke-width="0.25" stroke-dasharray="0.6,0.8"'
BLUE = 'fill="none" stroke="#0059cc" stroke-width="0.35"'
TEXT = 'font-family="sans-serif" text-anchor="middle"'


def n(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def hole(x, y, d, label=""):
    """Drilled hole with a crosshair (local mm, y down)."""
    r = d / 2
    s = f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" {HOLE}/>'
    s += (f'<path d="M{x - r - 1:.2f},{y:.2f}H{x + r + 1:.2f}M{x:.2f},{y - r - 1:.2f}V{y + r + 1:.2f}" '
          f'stroke="#d40000" stroke-width="0.15"/>')
    if label:
        s += f'<title>{label}</title>'
    return s


def rect(cx, cy, w, h, style):
    return f'<rect x="{cx - w / 2:.2f}" y="{cy - h / 2:.2f}" width="{w:.2f}" height="{h:.2f}" {style}/>'


def text(x, y, s, size=2.5, fill="#000"):
    return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{fill}" {TEXT}>{s}</text>'


def layer(lid, label, body, locked=False, hidden=False):
    attrs = f'id="{lid}" inkscape:groupmode="layer" inkscape:label="{label}"'
    if locked:
        attrs += ' sodipodi:insensitive="true"'
    if hidden:
        attrs += ' style="display:none"'
    return f'<g {attrs}>\n{body}\n</g>\n'


def part(pid, x, y, angle, body, label):
    """One movable group: local frame x along the part, y down; placed at plate (x, y up), angle CCW (deg).
    read_plate_svg.py reads the placement back from this group's transform."""
    return (f'<g id="{pid}" inkscape:label="{label}" transform="translate({n(x)},{n(-y)}) rotate({n(-angle)})">'
            f'{body}</g>')


def slider(sid, s, body, label):
    """Sub-group inside a part, offset s along the part's axis (read back as that offset)."""
    return f'<g id="{sid}" inkscape:label="{label}" transform="translate({n(s)},0)">{body}</g>'


def tie_pair(sid, s, half_width, label):
    o = half_width + t.TIE_CLEAR
    b = f'<path d="M0,{-o}V{o}" stroke="#000" stroke-width="0.6" opacity="0.5"/>'          # the strap
    b += hole(0, -o, t.TIE_HOLE, "tie") + hole(0, o, t.TIE_HOLE, "tie")
    return slider(sid, s, b, label)


def xiao_body(pid, tie_s, side, name):
    """XIAO seen from the top; side = +1 when its IPEX4 is left of the axis (toward the IPEX4 end)."""
    along, off = t.XIAO_IPEX
    y = -side * off                                   # local y down
    b = rect(0, 0, t.XIAO_L, t.XIAO_W, UNDER)
    b += rect(t.ALT_MOUNT, y, t.ALT_MOUNT_SIDE, t.ALT_MOUNT_SIDE, MOUNT)
    b += f'<path d="M{along},{y}H{t.ALT_MOUNT}" stroke="#e08000" stroke-width="0.8"/>'       # coax to the mount
    b += f'<circle cx="{along}" cy="{y}" r="1" fill="#000"/>'
    b += tie_pair(f"{pid}_tie", tie_s, t.XIAO_W / 2, f"{name} tie (slide along)")
    b += text(0, 1, name, 4)
    b += text(-t.XIAO_L / 2 + 2.2, 0.8, "USB", 1.6)
    b += text(along - 1, y - 1.6 * side, "IPEX4", 1.4)
    b += text(t.ALT_MOUNT, y + 0.6, "tie mount", 1.6)
    return b


def esp32_body():
    L, W = t.ESP32[3], t.ESP32[2]
    b = rect(0, 0, L, W, UNDER)
    b += rect(L / 2 - 9, -2, 16, 15, UNDER.replace('stroke-width="0.35"', 'stroke-width="0.25"'))   # RJ45, approx
    b += text(L / 2 - 9, -1, "RJ45", 2.2)
    b += text(L / 2 - 9, 7.5, "RJ45 side down", 1.6)
    b += f'<path d="M{-L / 2 + 6},{-W / 2 + 1.3}H{L / 2 - 4}" stroke="#000" stroke-width="0.8" stroke-dasharray="0.6,1.94"/>'
    b += text(-6, -W / 2 + 4, "header 21-40 (hung RJ45 side down), VBUS (40) at RJ45 end", 1.8)
    b += text(-10, 0, "ESP32-S3-ETH", 3.5)
    for k, ts in enumerate(t.ALT_ESP32_TIES):
        b += tie_pair(f"esp32_tie{k}", ts, W / 2, f"ESP32 tie {k} (slide along)")
    return b


def bus_body(hole_s):
    w, h = t.POWER[3], t.POWER[2]
    b = rect(0, 0, w, h, UNDER)
    for k in range(4):
        for j in range(4):
            b += f'<circle cx="{-5.5 + k * 2.54 - 1.9:.2f}" cy="{(j - 1.5) * 2.54:.2f}" r="0.5" fill="none" stroke="#000" stroke-width="0.15"/>'
    b += slider("bus_m3", hole_s, hole(0, 0, t.PLATE_M3, "M3"), "bus M3 hole (slide along)")
    b += text(-1.9, -h / 2 - 0.8, "bus", 2.2)
    return b


def plate():
    R = t.PLATE_DIAMETER / 2
    b = f'<circle r="{R}" fill="#f4f0e8" stroke="#000" stroke-width="0.5"/>'
    b += '<path d="M-4,0H4M0,-4V4" stroke="#000" stroke-width="0.2"/>'
    b += text(0, -R + 5, "12 o'clock", 2.5, "#666")
    return layer("layer_plate", f"Plate {t.PLATE_DIAMETER:g} mm (locked)", b, locked=True)


def m4_and_antennas():
    b = ""
    for d, x, y, tag in t.alt_plate_holes():
        if tag == "M4":
            b += hole(x, -y, d, "M4 bolt to deck")
            b += f'<circle cx="{x:.2f}" cy="{-y:.2f}" r="4" {REF}/>'                 # spacer, approx
            b += text(x, -y + 7, "M4", 2.5, "#d40000")
    for d, x, y, tag in t.plate_antenna_holes():                               # reference only (dotted), over the deck jacks
        b += hole(x, -y, d, f"{tag[:-4]} antenna hole (reference, not by design)").replace(
            "/>", ' stroke-dasharray="0.6 0.9"/>', 2)
        b += f'<circle cx="{x:.2f}" cy="{-y:.2f}" r="{d / 2 + t.RULE_ANT_CLEAR:.2f}" {REF.replace("#999", "#d40000")} opacity="0.5"/>'
        b += text(x, -y - d / 2 - 1, f"{tag[:-4]} ref", 2, "#d40000")
    return layer("layer_m4", f"M4 + antenna holes, {t.RULE_ANT_CLEAR:g} mm keep-out (locked)", b, locked=True)


def deck_jacks(centre):
    letters = {"duck/monopole": "D", "patch": "P", "patch end": "P2", "dipole coax": "C"}
    turn = math.radians(t.PLATE_TURN)
    b = ""
    if centre == "alt":                       # the pipe layout's hole saw removes the C holes
        for d, x, y, lab in g.holes:
            if lab in ("via", "M4 mount", "core feed") or d == g.HOLE_RPSMA:   # 6.5 mm jacks: drilled, M4 layer
                continue
            dx, dy = x - g.CX, y - g.CY
            px, py = dx * math.cos(turn) + dy * math.sin(turn), -dx * math.sin(turn) + dy * math.cos(turn)
            b += f'<circle cx="{px:.2f}" cy="{-py:.2f}" r="{t.ALT_DECK_JACK / 2}" {REF}/>'
            b += text(px, -py + 0.8, f"{lab[:2]} {letters[lab.split(' ', 1)[1]]}", 2, "#999")
        b += f'<circle r="{t.ALT_CORE_HOLE / 2}" {REF}/>' + text(0, -t.ALT_CORE_HOLE / 2 - 1, "deck core 10", 2, "#999")
    else:
        b += f'<circle r="{t.PIPE_SAW / 2:.2f}" {REF}/>' + text(0, t.PIPE_SAW / 2 - 1.5, "deck hole saw", 2, "#999")
    return layer("layer_jacks", "Deck jacks below (reference, locked)", b, locked=True)


def adapter():
    b = f'<circle r="{t.ADAPTER_HOLE / 2}" {BLUE}/>'
    b += f'<circle r="{t.NUT_OD / 2}" {BLUE} stroke-dasharray="2,1"/>'
    b += f'<circle r="{t.ADP_HEX_W / 2}" {REF.replace("#999", "#0059cc")}/>'
    b += text(0, -t.NUT_OD / 2 - 1.2, f"adapter {t.ADAPTER_HOLE:g} hole, nut on top", 2, "#0059cc")
    b += text(0, t.ADP_HEX_W / 2 + 2.6, "adapter hex under the plate", 1.8, "#0059cc")
    return layer("layer_adapter", "Pipe adapter + nut (locked)", b, locked=True)


def poe_box():
    # 4" round electrical box with its 1" hole; whether it sits on the plate is undecided
    b = (f'<circle r="50.8" {REF.replace("#999", "#008000")}/>'
         f'<circle r="12.7" fill="none" stroke="#008000" stroke-width="0.3"/>'
         + text(0, -30, '4" box (PoE splitter)', 3, "#008000") + text(0, 17, '1" hole', 2.2, "#008000"))
    return layer("layer_box", "PoE 4in box", f'<g id="box">{b}</g>', hidden=True)


def notes(lines):
    b = "".join(f'<text x="-83" y="{80 + k * 3.2:.1f}" font-size="2.4" font-family="sans-serif">{s}</text>'
                for k, s in enumerate(lines))
    return layer("layer_notes", "Notes (locked)", b, locked=True)


HOWTO = [
    "Move / rotate whole part groups (don't scale or flip them). Double-click a part to slide its tie or M3 hole along it.",
    "Then: python read_plate_svg.py  (positions -> parameters.csv + clearance check),  python make_templates.py  (PDF).",
    "Dashed parts hang under the plate. Red dotted rings: antenna-hole keep-out. Coax runs on to the jacks are checked, not drawn.",
]


def alt_svg():
    body = plate() + deck_jacks("alt") + m4_and_antennas()
    for i, (cx, cy, a) in enumerate(t.ALT_XIAOS):
        body += layer(f"layer_s{i}", f"S{i} XIAO (underside)",
                      part(f"s{i}", cx, cy, a, xiao_body(f"s{i}", t.ALT_XIAO_TIE_S[i], 1, f"S{i}"), f"S{i} XIAO"))
    body += poe_box()
    body += layer("layer_esp32", "ESP32 (underside)",
                  part("esp32", *t.ALT_ESP32, t.ALT_ESP32_ANGLE, esp32_body(), "ESP32"))
    body += layer("layer_bus", "Bus board (underside)",
                  part("bus", *t.ALT_BUS, t.ALT_BUS_ANGLE, bus_body(t.ALT_BUS_HOLE_S), "bus board"))
    return body + notes(["ALT SPLIT PLATE: S0, S1, S2, ESP32 and bus move on their own."] + HOWTO)


def pipe_svg():
    cx, cy, a, _ = t.fl_xiaos()[0]
    body = plate() + deck_jacks("pipe") + adapter() + m4_and_antennas()
    body += layer("layer_s0", "S0 XIAO (underside; S1 / S2 follow)",
                  part("s0", cx, cy, a, xiao_body("s0", t.FL_TIE_S, t.FL_UNDER_SIDE, "XIAO"), "S0 XIAO"))
    clones = "".join(f'<use id="s{k}_clone" xlink:href="#s0" transform="rotate({k * 120})"/>' for k in (1, 2))
    body += layer("layer_clones", "S1 + S2 (clones of S0, locked)", clones, locked=True)
    bx, by = t.clock(t.FL_BUS[1], t.FL_BUS[0])
    body += layer("layer_bus", "Bus board (underside)",
                  part("bus", bx, by, 90 - t.FL_BUS[0], bus_body(t.ALT_BUS_HOLE_S), "bus board"))
    return body + notes(["PIPE PLATE: move S0 (S1 / S2 are clones turned 120 deg) and the bus (kept radial, M3 toward the rim).",
                         "The bus M3 offset is shared with the alt plate: set it there."] + HOWTO)


def write(which):
    body = alt_svg() if which == "alt" else pipe_svg()
    w, h = (float(v) for v in VIEWBOX.split()[2:])
    svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
           'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
           f'width="{w:g}mm" height="{h:g}mm" viewBox="{VIEWBOX}">\n'
           '<sodipodi:namedview inkscape:document-units="mm" showgrid="false"/>\n'
           + body + '</svg>\n')
    out = os.path.join(HERE, FILES[which])
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", out)


def main():
    for which in FILES:
        write(which)


if __name__ == "__main__":
    main()
