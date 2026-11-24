"""The design formulas page, shared by both builds' PDFs: every derived dimension from common/layout.py, per duck
spacing, with a top view. The hand build's templates print it without the PCB deck's radio placement; the PCB print
PDF prints it with. Needs reportlab.

    from formulas_page import draw;  draw(canvas, radios=True)
"""
import math
import os
import sys

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout   # noqa: E402
import params   # noqa: E402

P = params.load()
PAGE_W, PAGE_H = letter
LIGHT_MM_PER_NS = 299.792458            # speed of light: wavelength in mm = this / frequency in GHz
DIM_INK = (0.1, 0.35, 0.7)
COPPER_INK = (0.72, 0.42, 0.15)
FORMULA_SCALE = P["FORMULA_SCALE"]
RF_FREQ = P["RF_FREQ"]
HOLE_RPSMA = P["HOLE_RPSMA"]
COLLAR_HOLE = P["COLLAR_HOLE"]
XIAO_L = P["XIAO_L"]
XIAO_W = P["XIAO_W"]


def page(path, radios, title):
    """One-page PDF of the formulas page."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=letter)
    draw(c, radios, title)
    c.showPage()
    c.save()


def draw(c, radios, title="Design formulas (NOT a template, not to size)"):
    """Reference page: every derived dimension, printed from layout.py (the code the PCBs and templates use), for
    each duck spacing, plus a top view with the main ones dimensioned. radios=False (hand build PDF) leaves out the
    PCB deck's radio placement (the RADIOS rows, the XIAOs and tie squares in the top view); radios=True (PCB print
    PDF) shows it."""
    Ls = [layout.Layout(s) for s in layout.VARIANTS]
    L = Ls[0]
    k = FORMULA_SCALE
    lam = LIGHT_MM_PER_NS / (RF_FREQ / 1000)

    def dim(p0, p1, text, dx=0.0, dy=0.0, anchor="c", size=6.5):
        c.saveState()
        c.setStrokeColorRGB(*DIM_INK)
        c.setFillColorRGB(*DIM_INK)
        c.setLineWidth(0.4)
        c.line(*p0, *p1)
        ux, uy = p1[0] - p0[0], p1[1] - p0[1]
        n = math.hypot(ux, uy) or 1
        tx_, ty_ = -uy / n * 1.2 * mm, ux / n * 1.2 * mm
        for q in (p0, p1):
            c.line(q[0] - tx_, q[1] - ty_, q[0] + tx_, q[1] + ty_)
        c.setFont("Helvetica-Bold", size)
        mx, my = (p0[0] + p1[0]) / 2 + dx * mm, (p0[1] + p1[1]) / 2 + dy * mm
        {"c": c.drawCentredString, "l": c.drawString, "r": c.drawRightString}[anchor](mx, my, text)
        c.restoreState()

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm, title)
    c.setFont("Helvetica", 8.5)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Printed from common/layout.py, the same code that places the PCB deck and these templates: each "
                 "value is computed once, next to its formula.")
    c.drawString(15 * mm, (PAGE_H / mm - 25.5) * mm,
                 "Change common/parameters.csv, re-run make_templates.py and builds/pcb/make_pcbs.py, and both builds follow. "
                 "Names in capitals are parameters.csv rows.")

    # ---- top view, first variant, S0 up
    tx, ty = 52.0, 195.0

    def T(r, deg):
        q = math.radians(deg)
        return (tx + r * k * math.sin(q)) * mm, (ty + r * k * math.cos(q)) * mm

    def TF(t, u, v):
        x, y = layout.xy(t, u, v)
        return (tx + x * k) * mm, (ty + y * k) * mm

    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(tx * mm, (ty + L.deck_r * k + 4) * mm, f"TOP VIEW, {L.spacing:g} mm ducks, S0 up, scale {k:g}")
    c.setLineWidth(0.6)
    c.circle(tx * mm, ty * mm, L.deck_r * k * mm)
    c.circle(tx * mm, ty * mm, L.pipe_d / 2 * k * mm)
    c.saveState()
    c.setStrokeColorRGB(*COPPER_INK)
    c.setLineWidth(1.0)
    tri = [T(L.r_c, v) for v in layout.VERTICES]
    path = c.beginPath()
    path.moveTo(*tri[0])
    for q in tri[1:]:
        path.lineTo(*q)
    path.close()
    c.drawPath(path)
    c.restoreState()
    c.setLineWidth(0.4)
    for kind, i, x, y in L.holes():
        c.circle((tx + x * k) * mm, (ty + y * k) * mm, HOLE_RPSMA / 2 * k * mm)
    for x, y in L.m3():
        c.circle((tx + x * k) * mm, (ty + y * k) * mm, COLLAR_HOLE / 2 * k * mm)
    if radios:
        hl, hw = XIAO_L / 2, XIAO_W / 2
        c.setStrokeGray(0.45)
        for t in layout.VERTICES:
            pts = [TF(t, u, v) for u, v in ((-hw, L.xiao_v - hl), (hw, L.xiao_v - hl), (hw, L.xiao_v + hl),
                                             (-hw, L.xiao_v + hl))]
            path = c.beginPath()
            path.moveTo(*pts[0])
            for q in pts[1:]:
                path.lineTo(*q)
            path.close()
            c.drawPath(path)
            _, tc, _, sq = L.tie(t)
            pts = [TF(t, *q) for q in sq]
            path = c.beginPath()
            path.moveTo(*pts[0])
            for q in pts[1:]:
                path.lineTo(*q)
            path.close()
            c.drawPath(path)
    c.setStrokeGray(0)
    dim(T(0, 0), T(L.r_in, 0), "r_in", dx=-1.2, anchor="r")
    dim(T(L.r_in, 0), T(L.r_D, 0), "d", dx=-1.2, anchor="r")
    dim(T(0, 60), T(L.r_c, 60), "R_c", dx=1.2, dy=-2.5, anchor="l")
    dim(T(0, 270), T(L.deck_r, 270), "R", dy=1.2)
    dim(T(0, 120), T(L.r_P, 120), "r_P", dx=3.0, dy=-2.5, anchor="l")
    dim(T(0, L.m3_angles[0]), T(L.m3_r, L.m3_angles[0]), "r_M3", dx=-1.0, dy=1.0, anchor="r")
    if radios:
        dim(T(0, 180), TF(180, 0, L.xiao_v), "v_X", dx=1.2, anchor="l")
    dim(T(L.r_P, 0), T(L.r_P2, -L.a_P2), "s", dy=1.5)
    c.setFont("Helvetica", 6)
    c.setFillGray(0.35)
    c.drawCentredString(tx * mm, (ty - L.deck_r * k - 5) * mm,
                        "Copper = the faces' outer surface. Blue = dimensions in the table."
                        + (" Grey = XIAOs and tie squares (PCB deck)." if radios else
                           " Radios: PCB print PDF."))
    c.setFillGray(0)

    # ---- table: formula, value per variant
    x, y = 104.0, PAGE_H / mm - 44
    cols = [x + 86 + 16 * j for j in range(len(Ls))]
    c.setFont("Helvetica-Bold", 7)
    for j, Lv in enumerate(Ls):
        c.drawRightString(cols[j] * mm, y * mm, f"{Lv.spacing:g} mm")
    y -= 4
    section = None
    for n, row in enumerate(L.rows):
        sec, sym, formula, _, unit, note = row
        if sec == "RADIOS" and not radios:
            continue
        vals = [Lv.rows[n][3] for Lv in Ls]
        if sec != section:
            section = sec
            y -= 1.5
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(x * mm, y * mm, sec)
            y -= 4
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x * mm, y * mm, sym)
        c.setFont("Helvetica", 7)
        words, lines_, cur = ("= " + formula).split(" "), [], ""
        for w_ in words:                       # wrap the formula to the column left of the values
            if c.stringWidth(cur + " " + w_, "Helvetica", 7) > (cols[0] - 16 - x - 14) * mm and cur:
                lines_.append(cur)
                cur = "  " + w_
            else:
                cur = (cur + " " + w_).strip(" ") if cur else w_
        lines_.append(cur)
        c.setFont("Helvetica-Bold", 7)
        for j, v in enumerate(vals):
            c.drawRightString(cols[j] * mm, y * mm, f"{v:.2f}".rstrip("0").rstrip("."))
        c.setFont("Helvetica", 7)
        for line in lines_:
            c.drawString((x + 14) * mm, y * mm, line)
            y -= 3.1
        y -= 0.2
        if note:
            c.setFont("Helvetica", 6)
            c.setFillGray(0.4)
            for line in note.split("\n"):
                c.drawString((x + 16) * mm, y * mm, line)
                y -= 2.9
            c.setFillGray(0)
        y -= 0.6
    # ---- RF: spacing in wavelengths
    y = min(y, 120) - 4
    rows = [("f", "RF_FREQ (BLE band centre)", f"{RF_FREQ:g} MHz"),
            ("lambda", "c / f", f"{lam:.1f} mm")]
    rows += [("d / lambda", f"{Lv.spacing:g} mm ducks", f"{Lv.spacing / lam:.3f}") for Lv in Ls]
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(15 * mm, 112 * mm, "RF")
    yy = 107
    for sym, formula, val in rows:
        c.setFont("Helvetica-Bold", 7)
        c.drawString(15 * mm, yy * mm, sym)
        c.setFont("Helvetica", 7)
        c.drawString(33 * mm, yy * mm, "= " + formula)
        c.setFont("Helvetica-Bold", 7)
        c.drawRightString(95 * mm, yy * mm, val)
        yy -= 3.6
    c.setFont("Helvetica", 6.5)
    c.setFillGray(0.35)
    for n, t in enumerate([
            "The duck spacings come from simulation (rf_model/),",
            "not from a quarter-wave rule: 15 mm gives the narrower",
            "beam and the better bearing with the H50327 ducks;",
            "31 mm (about lambda / 4) is the older spacing, kept as",
            "the second deck size. Numbers: rf_model/README.md."]):
        c.drawString(15 * mm, (yy - 2 - n * 3) * mm, t)
    c.setFillGray(0)
    c.setFont("Helvetica", 7.5)
    c.drawString(15 * mm, 14 * mm,
                 "Units: mm and degrees, clockwise from S0 (top view) unless marked. Values rounded to 0.01 mm.")

