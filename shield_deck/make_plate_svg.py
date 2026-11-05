"""Electronics plate as an Inkscape SVG for laying out by hand: one layer per part, each part's outline and the
holes it needs in one group, so dragging / rotating the group moves its holes with it. The plate and its M4
bolt holes (and the deck jacks below, for reference) are locked layers. Parts start where the alt split layout
(page 4 of the templates) puts them, all overlapping the plate as assembled.

Run:  python make_plate_svg.py  ->  plate_layout.svg (1 user unit = 1 mm, top view, plate 12 o'clock up)
"""
import math
import os

import make_shield_deck as g
import make_templates as t

HOLE = 'fill="none" stroke="#d40000" stroke-width="0.3"'
TOP = 'fill="none" stroke="#000" stroke-width="0.35"'
UNDER = 'fill="none" stroke="#3060a0" stroke-width="0.35" stroke-dasharray="1.5,1"'
REF = 'fill="none" stroke="#999" stroke-width="0.25" stroke-dasharray="0.6,0.8"'
TEXT = 'font-family="sans-serif" text-anchor="middle"'


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


def part(pid, x, y, angle, body):
    """One movable group: local frame x along the part, y down; placed at plate (x, y up), angle CCW."""
    return f'<g id="{pid}" transform="translate({x:.2f},{-y:.2f}) rotate({-angle:g})">{body}</g>'


def xiao(i):
    cx, cy, a = t.ALT_XIAOS[i]
    s = t.ALT_XIAO_TIE_S[i]
    along, side = t.ALT_IPEX
    o = t.XIAO_W / 2 + t.TIE_CLEAR
    b = rect(0, 0, t.XIAO_L, t.XIAO_W, UNDER)
    b += rect(t.ALT_MOUNT, -side, t.ALT_MOUNT_SIDE, t.ALT_MOUNT_SIDE, UNDER.replace('fill="none"', 'fill="#3060a0" fill-opacity="0.12"'))
    b += f'<circle cx="{along}" cy="{-side}" r="1" fill="#3060a0"/>'
    b += (f'<path d="M{along},{-side}H{t.ALT_MOUNT}" stroke="#e08000" stroke-width="0.8"/>')
    b += f'<path d="M{s},{-o}V{o}" stroke="#3060a0" stroke-width="0.6" opacity="0.5"/>'     # zip tie
    b += hole(s, -o, t.TIE_HOLE, "tie") + hole(s, o, t.TIE_HOLE, "tie")
    b += hole(-t.ALT_HARNESS_S, 0, t.ALT_HARNESS_HOLE, "harness")
    b += text(0, 1, f"S{i}", 4, "#3060a0")
    b += text(-t.XIAO_L / 2 + 2.2, 0.8, "USB", 1.6, "#3060a0")
    b += text(along - 1, -side - 1.6, "IPEX4", 1.4, "#3060a0")
    b += text(t.ALT_MOUNT, -side + 0.6, "tie mount", 1.6, "#3060a0")
    return layer(f"layer_s{i}", f"S{i} XIAO (underside)", part(f"s{i}", cx, cy, a, b))


def esp32():
    ex, ey = t.ALT_ESP32
    L, W = t.ESP32[3], t.ESP32[2]
    b = rect(0, 0, L, W, TOP)
    b += rect(L / 2 - 9, -2, 16, 15, TOP.replace('stroke-width="0.35"', 'stroke-width="0.25"'))   # RJ45, approx
    b += text(L / 2 - 9, -1, "RJ45", 2.2)
    b += text(L / 2 - 9, 7.5, "USB-C under", 1.6)
    b += f'<path d="M{-L / 2 + 6},{W / 2 - 1.3}H{L / 2 - 4}" stroke="#000" stroke-width="0.8" stroke-dasharray="0.6,1.94"/>'
    b += text(-6, W / 2 - 3, "header 21-40, VBUS (40) at RJ45 end", 1.8)
    b += text(-10, 0, "ESP32-S3-ETH", 3.5)
    for ts in t.ALT_ESP32_TIES:
        o = W / 2 + t.TIE_CLEAR
        b += hole(ts, -o, t.TIE_HOLE, "tie") + hole(ts, o, t.TIE_HOLE, "tie")
    return layer("layer_esp32", "ESP32 (top)", part("esp32", ex, ey, t.ALT_ESP32_ANGLE, b))


def bus():
    bx, by = t.ALT_BUS
    w, h = t.POWER[3], t.POWER[2]
    b = rect(0, 0, w, h, TOP)
    for k in range(4):
        for j in range(4):
            b += f'<circle cx="{-5.5 + k * 2.54 - 1.9:.2f}" cy="{(j - 1.5) * 2.54:.2f}" r="0.5" fill="none" stroke="#000" stroke-width="0.15"/>'
    b += hole(t.ALT_BUS_HOLE_S, 0, t.PLATE_M3, "M3")
    b += text(-1.9, -h / 2 - 0.8, "bus", 2.2)
    return layer("layer_bus", "Bus board (top)", part("bus", bx, by, t.ALT_BUS_ANGLE, b))


def jst():
    # the alt layout doesn't place them yet: parked in a row in the free space at the top
    b = ""
    for i, (x, y) in enumerate(((-12, 52), (2, 52), (16, 52))):
        b += part(f"jst{i}", x, y, 90, rect(0, 0, t.JST_L, t.JST_W, TOP) + text(0, 1, f"JST S{i}", 2.2))
    return layer("layer_jst", "JST pairs (top)", b)


def poe_box():
    # 4" round electrical box with its 1" hole; whether it sits on the plate is undecided
    b = (f'<circle r="50.8" {REF.replace("#999", "#008000")}/>'
         f'<circle r="12.7" fill="none" stroke="#008000" stroke-width="0.3"/>'
         + text(0, -30, '4" box (PoE splitter)', 3, "#008000") + text(0, 17, '1" hole', 2.2, "#008000"))
    return layer("layer_box", "PoE 4in box", part("box", 0, 0, 0, b), hidden=True)


def plate():
    R = t.PLATE_DIAMETER / 2
    b = f'<circle r="{R}" fill="#f4f0e8" stroke="#000" stroke-width="0.5"/>'
    b += '<path d="M-4,0H4M0,-4V4" stroke="#000" stroke-width="0.2"/>'
    b += text(0, -R + 5, "12 o'clock", 2.5, "#666")
    return layer("layer_plate", "Plate 152 mm (locked)", b, locked=True)


def m4():
    b = ""
    for v in g.VERTICES:
        a = math.radians(v + t.PLATE_TURN)
        x, y = g.MOUNT_RADIUS * math.sin(a), g.MOUNT_RADIUS * math.cos(a)
        b += hole(x, -y, t.PLATE_M4, "M4 bolt to deck")
        b += f'<circle cx="{x:.2f}" cy="{-y:.2f}" r="4" {REF}/>'                 # spacer, approx
        b += text(x, -y + 7, "M4", 2.5, "#d40000")
    return layer("layer_m4", "M4 mount holes (locked)", b, locked=True)


def deck_jacks():
    letters = {"duck/monopole": "D", "patch": "P", "patch end": "P2", "dipole coax": "C"}
    turn = math.radians(t.PLATE_TURN)
    b = ""
    for d, x, y, lab in g.holes:
        if lab in ("via", "M4 mount", "core feed"):
            continue
        dx, dy = x - g.CX, y - g.CY
        px, py = dx * math.cos(turn) + dy * math.sin(turn), -dx * math.sin(turn) + dy * math.cos(turn)
        b += f'<circle cx="{px:.2f}" cy="{-py:.2f}" r="{t.ALT_DECK_JACK / 2}" {REF}/>'
        b += text(px, -py + 0.8, f"{lab[:2]} {letters[lab.split(' ', 1)[1]]}", 2, "#999")
    b += f'<circle r="{t.ALT_CORE_HOLE / 2}" {REF}/>' + text(0, t.ALT_CORE_HOLE / 2 - 2, "keep clear: hole saw room", 2, "#999")
    b += f'<circle r="{g.HOLE_CORE / 2}" {REF}/>' + text(0, -g.HOLE_CORE / 2 - 1, "deck core 10", 2, "#999")
    return layer("layer_jacks", "Deck jacks below (reference, locked)", b, locked=True)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "plate_layout.svg")
    body = (plate() + deck_jacks() + m4() + xiao(0) + xiao(1) + xiao(2) + poe_box() + esp32() + bus() + jst())
    svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<svg xmlns="http://www.w3.org/2000/svg" '
           'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
           'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
           'width="170mm" height="170mm" viewBox="-85 -85 170 170">\n'
           '<sodipodi:namedview inkscape:document-units="mm" showgrid="false"/>\n'
           + body + '</svg>\n')
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", out)


if __name__ == "__main__":
    main()
