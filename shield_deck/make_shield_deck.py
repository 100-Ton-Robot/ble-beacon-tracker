"""Generate PCBWay-ready Gerber + Excellon files for the round copper shield deck.

Edit the PARAMETERS block and re-run:  python make_shield_deck.py
Output: shield_deck_gerbers.zip (upload to PCBWay) and shield_deck_preview.svg.
"""
import math
import os
import zipfile

# ---------------- PARAMETERS (mm) ----------------
DISC_DIAMETER = 146.0      # 6" pipe (~150-154 mm ID); tape the edge gap
FACE_WIDTH = 120.0         # triangular reflector core face width
DUCK_SPACING = 31.0        # antenna axis -> copper face (rubber duck / monopole hole)
PATCH_OFFSET = 7.0         # patch connector axis -> copper face. Measured panel: axis in line with
                           # the housing back, so the panel stands this far off the face (plug nut clearance)
PATCH_END_INSET = 14.0     # second patch hole per face: same offset, this far in from the face's end
                           # (the counter-clockwise end seen from the top)
COAX_PASS_RADIUS = 20.0    # dipole coax pass-through, inside the core
MOUNT_RADIUS = 45.0        # M4 bolts to the electronics plate, inside the core, toward the corners
EDGE_CLEAR = 0.5           # copper pull-back from the board edge
RIM_MASK_WIDTH = 4.0       # exposed copper ring at the rim (copper-tape edge seal)
SEAM_STRIP = 6.0           # exposed strip on the bottom for soldering the core seams
PAD_EXPOSE = 12.0          # exposed copper around each RP-SMA hole (nut contact)
STITCH_RADIUS = 71.0       # ring of stitching vias tying top and bottom copper
STITCH_COUNT = 36

HOLE_RPSMA = 6.5           # RP-SMA bulkhead
HOLE_COAX = 10.0           # coax + RP-SMA end pass-through
HOLE_M4 = 4.5
HOLE_VIA = 0.6
# -------------------------------------------------

R = DISC_DIAMETER / 2
CX = CY = R                     # board origin at lower-left of the bounding square
INRADIUS = FACE_WIDTH / (2 * math.sqrt(3))
CIRCUMRADIUS = 2 * INRADIUS
SECTORS = [0.0, 120.0, 240.0]   # face normals, clockwise from +Y (Sector 0 up)
VERTICES = [60.0, 180.0, 300.0]


def pol(r, deg):
    a = math.radians(deg)
    return CX + r * math.sin(a), CY + r * math.cos(a)


def face_pt(s, out, along):
    """Point `out` mm in front of face s and `along` mm from its centre toward its counter-clockwise end."""
    a = INRADIUS + out
    return pol(math.hypot(a, along), s - math.degrees(math.atan2(along, a)))


def fmt(v):
    return str(int(round(v * 1_000_000)))


def xy(p):
    return f"X{fmt(p[0])}Y{fmt(p[1])}"


# ---- holes ----
holes = []  # (diameter, x, y, label)
for i, s in enumerate(SECTORS):
    holes.append((HOLE_RPSMA, *pol(INRADIUS + DUCK_SPACING, s), f"S{i} duck/monopole"))
    holes.append((HOLE_RPSMA, *pol(INRADIUS + PATCH_OFFSET, s), f"S{i} patch"))
    holes.append((HOLE_RPSMA, *face_pt(s, PATCH_OFFSET, FACE_WIDTH / 2 - PATCH_END_INSET), f"S{i} patch end"))
    holes.append((HOLE_COAX, *pol(COAX_PASS_RADIUS, s), f"S{i} dipole coax"))
for v in VERTICES:
    holes.append((HOLE_M4, *pol(MOUNT_RADIUS, v), "M4 mount"))
for k in range(STITCH_COUNT):
    holes.append((HOLE_VIA, *pol(STITCH_RADIUS, k * 360 / STITCH_COUNT), "via"))

# ---- simple stroke font (units of a 4 x 6 cell) ----
FONT = {
    "S": [[(4, 6), (0, 6), (0, 3), (4, 3), (4, 0), (0, 0)]],
    "0": [[(0, 0), (4, 0), (4, 6), (0, 6), (0, 0)], [(0, 0), (4, 6)]],
    "1": [[(1, 5), (2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "2": [[(0, 6), (4, 6), (4, 3), (0, 3), (0, 0), (4, 0)]],
    "D": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 1), (3, 0), (0, 0)]],
    "P": [[(0, 0), (0, 6), (4, 6), (4, 3), (0, 3)]],
    "C": [[(4, 6), (0, 6), (0, 0), (4, 0)]],
    "T": [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    "O": [[(0, 0), (4, 0), (4, 6), (0, 6), (0, 0)]],
    "M": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    "3": [[(0, 6), (4, 6), (4, 0), (0, 0)], [(1, 3), (4, 3)]],
    "4": [[(3, 0), (3, 6), (0, 2), (4, 2)]],
}


def text_strokes(s, cx, cy, h=4.0):
    k = h / 6
    w = len(s) * 5 * k - k
    x0, y0 = cx - w / 2, cy - h / 2
    out = []
    for n, ch in enumerate(s):
        for line in FONT[ch]:
            out.append([(x0 + (n * 5 + px) * k, y0 + py * k) for px, py in line])
    return out


silk = []
silk += text_strokes("TOP", CX, CY)
for i, s in enumerate(SECTORS):
    silk += text_strokes(f"S{i}", *pol(60, s + 20), h=5)
    silk += text_strokes("D", *pol(INRADIUS + DUCK_SPACING, s - 12))
    silk += text_strokes("P", *pol(INRADIUS + PATCH_OFFSET, s - 16))
    silk += text_strokes("P2", *face_pt(s, PATCH_OFFSET, FACE_WIDTH / 2 - PATCH_END_INSET - 10))
    silk += text_strokes("C", *pol(COAX_PASS_RADIUS, s + 32))
for v in VERTICES:
    silk += text_strokes("M4", *pol(MOUNT_RADIUS, v + 13), h=3)
# Sector 0 arrow, pointing outward
ax, ay = pol(52, 0)
silk.append([(ax - 3, ay - 3), (ax, ay + 3), (ax + 3, ay - 3)])

tri = [pol(CIRCUMRADIUS, v) for v in VERTICES]

seams = [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]


def header(name, func, polarity="Positive"):
    return [
        "%FSLAX46Y46*%", "%MOMM*%",
        f"%TF.FileFunction,{func}*%", f"%TF.FilePolarity,{polarity}*%",
        f"G04 BLE tracker shield deck - {name}*", "%LPD*%",
    ]


def circle_region(r):
    sx, sy = CX + r, CY
    # two half-circle arcs: some viewers mishandle a single 360-degree arc
    return ["G36*", f"{xy((sx, sy))}D02*", "G75*",
            f"G03{xy((CX - r, CY))}I{fmt(-r)}J0D01*",
            f"G03{xy((sx, sy))}I{fmt(r)}J0D01*", "G37*"]


def circle_stroke(r, ap):
    sx, sy = CX + r, CY
    return [f"{ap}*", f"{xy((sx, sy))}D02*", "G75*",
            f"G03{xy((CX - r, CY))}I{fmt(-r)}J0D01*",
            f"G03{xy((sx, sy))}I{fmt(r)}J0D01*"]


def polyline(pts):
    out = [f"{xy(pts[0])}D02*", "G01*"]
    out += [f"{xy(p)}D01*" for p in pts[1:]]
    return out


def copper(name, func):
    lines = header(name, func)
    sizes = sorted({d for d, *_ in holes})
    lines += [f"%ADD{20 + n}C,{d:.3f}*%" for n, d in enumerate(sizes)]
    lines += circle_region(R - EDGE_CLEAR)
    # Knock the holes out of the pour so every viewer shows them on the copper layers too
    lines.append("%LPC*%")
    for n, d in enumerate(sizes):
        lines.append(f"D{20 + n}*")
        lines += [f"{xy((x, y))}D03*" for dd, x, y, _ in holes if dd == d]
    lines += ["%LPD*%", "M02*"]
    return "\n".join(lines) + "\n"


def mask(name, func, bottom):
    lines = header(name, func, "Negative")
    lines += [f"%ADD11C,{PAD_EXPOSE:.3f}*%", f"%ADD12C,{RIM_MASK_WIDTH:.3f}*%",
              f"%ADD13C,{SEAM_STRIP:.3f}*%"]
    lines += circle_stroke(R - RIM_MASK_WIDTH / 2, "D12")
    lines.append("D11*")
    for d, x, y, _ in holes:
        if d == HOLE_RPSMA:
            lines.append(f"{xy((x, y))}D03*")
    if bottom:
        lines.append("D13*")
        for a, b in seams:
            lines += polyline([a, b])
    lines.append("M02*")
    return "\n".join(lines) + "\n"


def silkscreen():
    lines = header("Top silkscreen", "Legend,Top")
    lines += ["%ADD10C,0.250*%", "D10*"]
    for s in silk:
        lines += polyline(s)
    lines.append("M02*")
    return "\n".join(lines) + "\n"


def outline():
    lines = header("Board outline", "Profile,NP")
    lines += ["%ADD14C,0.100*%"] + circle_stroke(R, "D14") + ["M02*"]
    return "\n".join(lines) + "\n"


def drill():
    sizes = sorted({d for d, *_ in holes})
    # KiCad-style Excellon: metric, absolute, explicit decimal points
    out = ["M48", "; DRILL file - BLE tracker shield deck, plated holes",
           "; FORMAT={-:-/ absolute / metric / decimal}", "FMAT,2", "METRIC"]
    for n, d in enumerate(sizes, 1):
        out.append(f"T{n}C{d:.3f}")
    out += ["G90", "%", "G05"]
    for n, d in enumerate(sizes, 1):
        out.append(f"T{n}")
        for dd, x, y, _ in holes:
            if dd == d:
                out.append(f"X{x:.3f}Y{y:.3f}")
    out += ["T0", "M30"]
    return "\n".join(out) + "\n"


def preview_svg():
    s = 4  # px per mm
    W = DISC_DIAMETER * s + 40
    def P(x, y):
        return 20 + x * s, 20 + (DISC_DIAMETER - y) * s
    el = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{W}" viewBox="0 0 {W} {W}">',
          '<rect width="100%" height="100%" fill="#ffffff"/>']
    cx, cy = P(CX, CY)
    el.append(f'<circle cx="{cx}" cy="{cy}" r="{R*s}" fill="#c98a3a" stroke="#333"/>')
    el.append(f'<circle cx="{cx}" cy="{cy}" r="{(R-RIM_MASK_WIDTH)*s}" fill="#2e7d32"/>')
    pts = " ".join(f"{P(*p)[0]},{P(*p)[1]}" for p in tri)
    el.append(f'<polygon points="{pts}" fill="none" stroke="#e0b060" stroke-width="{SEAM_STRIP*s}" opacity="0.6"/>')
    for d, x, y, _ in holes:
        px, py = P(x, y)
        if d == HOLE_RPSMA:
            el.append(f'<circle cx="{px}" cy="{py}" r="{PAD_EXPOSE/2*s}" fill="#c98a3a"/>')
        el.append(f'<circle cx="{px}" cy="{py}" r="{d/2*s}" fill="#ffffff" stroke="#333" stroke-width="0.5"/>')
    for st in silk:
        pts = " ".join(f"{P(*p)[0]},{P(*p)[1]}" for p in st)
        el.append(f'<polyline points="{pts}" fill="none" stroke="#ffffff" stroke-width="1.2"/>')
    el.append("</svg>")
    return "\n".join(el)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    files = {
        "shield_deck.GTL": copper("Top copper", "Copper,L1,Top"),
        "shield_deck.GBL": copper("Bottom copper", "Copper,L2,Bot"),
        "shield_deck.GTS": mask("Top solder mask", "Soldermask,Top", bottom=False),
        "shield_deck.GBS": mask("Bottom solder mask", "Soldermask,Bot", bottom=True),
        "shield_deck.GTO": silkscreen(),
        "shield_deck.GKO": outline(),
        "shield_deck.DRL": drill(),
    }
    zpath = os.path.join(here, "shield_deck_gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    with open(os.path.join(here, "shield_deck_preview.svg"), "w") as f:
        f.write(preview_svg())
    with open(os.path.join(here, "hole_table.csv"), "w") as f:
        f.write("label,diameter_mm,x_mm,y_mm,radius_from_centre_mm\n")
        for d, x, y, lab in holes:
            if lab != "via":
                f.write(f"{lab},{d},{x:.2f},{y:.2f},{math.hypot(x-CX, y-CY):.2f}\n")
    print("wrote", zpath)


if __name__ == "__main__":
    main()
