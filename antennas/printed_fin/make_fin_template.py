"""1:1 print template for the hand-made printed-dipole fin (score and peel), from fin_model.geometry().

    python3 make_fin_template.py                         # defaults from fin_model.DEFAULTS
    python3 make_fin_template.py --result out/fin/result.json   # parameters (and results) from a model run
    python3 make_fin_template.py --set L=54 Lsh=7

Writes out/fin_template.pdf (US Letter, print at 100 % / "actual size"). Needs reportlab and shapely.
Page 1: side A (feed) and side B (ground) at 1:1, plus a scale check. Page 2: face slot template. Page 3: numbers.
"""
import argparse
import json
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from shapely.geometry import box
from shapely.ops import unary_union

import fin_model as fm

HERE = os.path.dirname(os.path.abspath(__file__))
GREY = (0.72, 0.72, 0.72)


def banner(c):
    """Every page: this design is shelved and has never been built or measured."""
    W, H = letter
    c.saveState()
    c.setFillColorRGB(0.8, 0, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(W - 15 * mm, H - 9 * mm, "SHELVED - NOT TESTED (simulation only)")
    c.restoreState()


def union(rects):
    return unary_union([box(*r) for r in rects])


def polys(geom):
    return list(geom.geoms) if hasattr(geom, "geoms") else [geom]


def draw_side(c, p, geo, side, ox, oy, mirror, label):
    """One side at 1:1. Board origin (u=0, v=0) at page point (ox, oy) mm; u to the right (left if mirror)."""
    sx = -1 if mirror else 1
    X = lambda u: (ox + sx * u) * mm          # noqa: E731
    Y = lambda v: (oy + v) * mm               # noqa: E731
    ou0, ov0, ou1, ov1 = geo["outline"]
    # board outline with tabs: cut line
    board = unary_union([box(*geo["outline"])] + [box(*t) for t in geo["tabs"]])
    c.setLineWidth(0.6)
    c.setStrokeColorRGB(0, 0, 0)
    for pg in polys(board):
        path = c.beginPath()
        pts = list(pg.exterior.coords)
        path.moveTo(X(pts[0][0]), Y(pts[0][1]))
        for u, v in pts[1:]:
            path.lineTo(X(u), Y(v))
        path.close()
        c.drawPath(path, stroke=1, fill=0)
    # kept copper: grey fill, its edge is the score line
    rects = geo[side] + (geo["tabs"] if side == "B" else [])
    cu = union(rects)
    c.setFillColorRGB(*GREY)
    c.setLineWidth(0.35)
    for pg in polys(cu):
        path = c.beginPath()
        pts = list(pg.exterior.coords)
        path.moveTo(X(pts[0][0]), Y(pts[0][1]))
        for u, v in pts[1:]:
            path.lineTo(X(u), Y(v))
        path.close()
        c.drawPath(path, stroke=1, fill=1)
    # face edge marker and feed point
    c.setDash(2, 2)
    c.setLineWidth(0.3)
    c.line(X(0), Y(ov0 - 4), X(0), Y(ov1 + 4))
    c.setDash()
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 7)
    c.drawCentredString(X(0), Y(ov1 + 5), "face edge")
    pu, pv, pw = geo["port"]
    c.circle(X(pu), Y(pv), 0.6 * mm, stroke=1, fill=1)
    c.setFont("Helvetica", 7)
    cx = (X(ou0) + X(ou1)) / 2
    c.drawCentredString(cx, Y(ov0) - 4 * mm, "dot: coax " + ("centre" if side == "A" else "shield"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(cx, Y(ov1) + 9 * mm, label)


def page_sides(c, p, geo, res):
    W, H = letter
    banner(c)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, H - 15 * mm, "BLE tracker printed-dipole fin - 1:1 template (score and peel)")
    c.setFont("Helvetica", 8)
    c.drawString(15 * mm, H - 21 * mm,
                 f"{p['t']:g} mm double-sided FR-4. Print at 100 % (actual size). Check the 50 mm bar first. "
                 "Grey = copper to keep. Score every grey edge, peel the rest.")
    ou0, ov0, ou1, ov1 = geo["outline"]
    cy = H / mm - 45 - ov1
    wb = ou1 - ou0 + p["tab_len"]
    gap = (W / mm - 30 - 6 * wb) / 5
    for k in range(3):
        left = 15 + 2 * k * (wb + gap)
        draw_side(c, p, geo, "A", left + p["tab_len"], cy, False, f"Fin {k + 1} side A")
        left += wb + gap
        draw_side(c, p, geo, "B", left + ou1, cy, True, f"Fin {k + 1} side B")
    c.setFont("Helvetica", 8)
    c.drawString(15 * mm, (cy + ov1 + 15) * mm,
                 "Side A = feed side. Side B = ground side, drawn as seen with the board turned over. Tabs point to "
                 "the face.")
    scale_bar(c)
    tx = 15
    ty = cy + ov0 - 18
    _lines(c, p, geo, ou0, ov0, ou1, ov1, tx, ty)


def scale_bar(c):
    y0 = 22
    c.setLineWidth(1)
    c.line(15 * mm, y0 * mm, 65 * mm, y0 * mm)
    for k in range(0, 51, 10):
        c.line((15 + k) * mm, y0 * mm, (15 + k) * mm, (y0 + (2.5 if k % 50 else 4)) * mm)
    c.setFont("Helvetica", 8)
    c.drawString(15 * mm, (y0 - 4) * mm, "50 mm - measure this before cutting")


def _lines(c, p, geo, ou0, ov0, ou1, ov1, tx, ty):
    c.setFont("Helvetica", 8)
    lines = [
        f"Board {ou1 - ou0:.1f} x {ov1 - ov0:.1f} mm, plus two tabs {p['tab_len']:.1f} x {p['tab_w']:.1f} mm "
        f"(overall {ou1 - ou0 + p['tab_len']:.1f} x {ov1 - ov0:.1f} mm).",
        f"Dipole arms {p['Wa']:.1f} mm wide, tip to tip {p['L']:.1f} mm, centre {p['S']:.1f} mm from the face; "
        f"slot {p['g']:.1f} mm; strips {p['Ws']:.1f} mm.",
        f"Feed line {p['Wf']:.1f} mm wide from {p['u0']:.1f} mm off the face; crossing leg at {p['uc']:.1f} mm; "
        f"stub return leg {p['Lsh']:.1f} mm.",
        "Cut the board to the outline first, then glue a template to each side lined up on the board edges "
        "(face side to face side).",
        "Side B's copper runs onto both tabs: they solder into the face slots. Side A has no copper on the tabs.",
    ]
    for i, t in enumerate(lines):
        c.drawString(tx * mm, (ty - 4.2 * i) * mm, t)


def page_face(c, p, geo):
    W, H = letter
    banner(c)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, H - 15 * mm, "Face slot template - 1:1, outside of the face")
    c.setFont("Helvetica", 8)
    c.drawString(15 * mm, H - 21 * mm,
                 f"Centre the circle on the existing {p['hole']:g} mm hole, slots vertical (along the face height). "
                 f"Cut slots {p['slot_w']:.1f} x {p['tab_w'] + 0.3:.1f} mm.")
    cx, cy = W / mm / 2, H / mm / 2 + 20
    c.setLineWidth(0.4)
    c.circle(cx * mm, cy * mm, p["hole"] / 2 * mm, stroke=1, fill=0)
    c.setDash(1, 2)
    c.line((cx - 15) * mm, cy * mm, (cx + 15) * mm, cy * mm)
    c.line(cx * mm, (cy - 20) * mm, cx * mm, (cy + 20) * mm)
    c.setDash()
    c.setFillColorRGB(0, 0, 0)
    for (u0, v0, u1, v1) in geo["tabs"]:
        sl = p["tab_w"] + 0.3
        vc = (v0 + v1) / 2
        c.rect((cx - p["slot_w"] / 2) * mm, (cy + vc - sl / 2) * mm, p["slot_w"] * mm, sl * mm, stroke=1, fill=1)
    c.setFont("Helvetica", 8)
    vt = [((t[1] + t[3]) / 2) for t in geo["tabs"]]
    c.drawString((cx + 6) * mm, (cy + vt[1]) * mm, f"slot centre {vt[1]:+.2f} mm from hole centre")
    c.drawString((cx + 6) * mm, (cy + vt[0]) * mm, f"slot centre {vt[0]:+.2f} mm from hole centre")
    c.drawString((cx + 6) * mm, (cy - 25) * mm, "The slots are symmetric, the fin is not: fit all three fins the same way up")
    c.drawString((cx + 6) * mm, (cy - 29) * mm, "(feed line toward the end plate, as modelled), so the three sectors match.")
    c.drawString((cx + 6) * mm, (cy - 33) * mm, f"Slot {p['slot_w']:.1f} mm wide: drill {p['slot_w']:.1f} mm at each end, file between.")
    # fin footprint (dashed) for orientation
    c.setDash(1, 1.5)
    ov0, ov1 = geo["outline"][1], geo["outline"][3]
    c.rect((cx - p["t"] / 2) * mm, (cy + ov0) * mm, p["t"] * mm, (ov1 - ov0) * mm, stroke=1, fill=0)
    c.setDash()
    c.drawString((cx + 6) * mm, (cy + ov1 - 2) * mm, "dashed: where the fin's face edge sits")
    scale_bar(c)


def page_numbers(c, p, geo, res):
    W, H = letter
    banner(c)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, H - 15 * mm, "Model results, parameters and build notes")
    y = H / mm - 24
    c.setFont("Helvetica", 8)
    for t in (res or {}).get("notes", []):
        c.drawString(15 * mm, y * mm, t)
        y -= 4
    png = (res or {}).get("plot")
    if png and os.path.exists(png):
        c.drawImage(png, 15 * mm, (y - 82) * mm, width=155 * mm, height=80 * mm, preserveAspectRatio=True)
        y -= 88
    c.setFont("Helvetica-Bold", 9)
    c.drawString(15 * mm, y * mm, "Parameters (mm unless noted)")
    y -= 4.5
    c.setFont("Courier", 7.5)
    items = [(k, v) for k, v in p.items() if k != "etch"]
    half = (len(items) + 1) // 2
    for i, (k, v) in enumerate(items):
        col, row = divmod(i, half)
        c.drawString((15 + 60 * col) * mm, (y - 3.4 * row) * mm, f"{k:8s} {v:g}")
    y -= 3.4 * half + 4
    c.setFont("Helvetica", 8)
    bad = fm.check(p, geo)
    c.drawString(15 * mm, y * mm, "Score-and-peel / fit rules (gaps >= 1 mm, copper >= 1 mm from edges, tabs clear "
                 "of the hole): " + ("all OK" if not bad else "; ".join(bad)))
    y -= 7
    c.setFont("Helvetica-Bold", 9)
    c.drawString(15 * mm, y * mm, "Build")
    y -= 4.5
    c.setFont("Helvetica", 8)
    for t in ["1. Measure the board with calipers (model: 1.0 mm; 0.9-1.1 checked). Check the 50 mm bar on page 1.",
              "2. Cut the board to the outline including the tabs. Deburr.",
              "3. Glue a side A template on one face and the matching side B template on the other, lined up on the",
              "   board edges, face edge to face edge. Score every grey edge with a new blade on a steel rule.",
              "4. Warm the copper with the iron, lift a corner, peel the white areas low and slow. Wash off the paper.",
              "5. Meter: nothing across the slot on side B; side A feed not touching side B anywhere.",
              "6. Coax (half an IPEX4-IPEX4 jumper): shield flat on side B at its dot, centre round the face edge",
              "   to side A's dot. Glue or Kapton the coax to the fin.",
              "7. Face: cut the two slots (page 2). Fin through the slots, all three fins the same way up,",
              "   solder the side B tabs to the face copper inside. Burnish, then Incralac (mask the tab joints",
              "   until soldered)."]:
        c.drawString(15 * mm, y * mm, t)
        y -= 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result")
    ap.add_argument("--set", nargs="*")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "fin_template.pdf"))
    a = ap.parse_args()
    res = None
    if a.result:
        with open(a.result) as fh:
            res = json.load(fh)
        p = dict(fm.DEFAULTS, **res["params"])
    else:
        p = fm.parse_set(a.set)
    geo = fm.geometry(p)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    c = canvas.Canvas(a.out, pagesize=letter)
    c.setTitle("BLE tracker fin template")
    page_sides(c, p, geo, res)
    c.showPage()
    page_face(c, p, geo)
    c.showPage()
    page_numbers(c, p, geo, res)
    c.showPage()
    c.save()
    print("wrote", a.out)


if __name__ == "__main__":
    main()
