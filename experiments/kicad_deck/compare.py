"""Compare the KiCad-exported deck (out/gerbers/) with the script's shield_deck_gerbers.zip.

Drill: hole-by-hole match. Layers: both rasterised at PX_PER_MM, then the differing area in mm^2.
Writes out/diff_<layer>.png (grey = both, red = script only, blue = KiCad only) and out/compare.txt.
"""
import glob
import io
import os
import sys
import zipfile

from PIL import Image, ImageDraw, ImageChops
from gerbonara import GerberFile, ExcellonFile
from gerbonara.graphic_primitives import Circle, Line, Arc, ArcPoly, Rectangle
from gerbonara.utils import MM

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT_ZIP = os.path.join(HERE, "..", "..", "shield_deck", "shield_deck_gerbers.zip")
KICAD_DIR = os.path.join(HERE, "out", "gerbers")
OUT = os.path.join(HERE, "out")

PX_PER_MM = 20
LO, HI = -2.0, 148.0          # raster window (mm), both axes
SIZE = int((HI - LO) * PX_PER_MM)

# layer name -> (file in the script zip, glob in KiCad's output)
LAYERS = {
    "top copper": ("shield_deck.GTL", "*F_Cu*"),
    "bottom copper": ("shield_deck.GBL", "*B_Cu*"),
    "top mask": ("shield_deck.GTS", "*F_Mask*"),
    "bottom mask": ("shield_deck.GBS", "*B_Mask*"),
    "top silk": ("shield_deck.GTO", "*F_Silk*"),
    "outline": ("shield_deck.GKO", "*Edge_Cuts*"),
}


def px(x, y):
    return (x - LO) * PX_PER_MM, (HI - y) * PX_PER_MM


def draw_prim(d, p):
    fill = 255 if p.polarity_dark else 0
    if isinstance(p, Circle):
        (x, y), r = px(p.x, p.y), p.r * PX_PER_MM
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)
    elif isinstance(p, Line):
        w = p.width * PX_PER_MM
        a, b = px(p.x1, p.y1), px(p.x2, p.y2)
        d.line([a, b], fill=fill, width=max(1, round(w)))
        for x, y in (a, b):  # round caps
            d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=fill)
    elif isinstance(p, Arc):
        from gerbonara.graphic_primitives import approximate_arc
        pts = list(approximate_arc(p.cx, p.cy, p.x1, p.y1, p.x2, p.y2, p.clockwise, max_error=0.005))
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            draw_prim(d, Line(x1, y1, x2, y2, p.width, polarity_dark=p.polarity_dark))
    elif isinstance(p, (ArcPoly, Rectangle)):
        poly = p.to_arc_poly() if isinstance(p, Rectangle) else p
        pts = [px(x, y) for x, y in poly.approximate_arcs(max_error=0.005).outline]
        if len(pts) >= 3:
            d.polygon(pts, fill=fill)
    else:
        raise TypeError(type(p))


def render_gerber(f):
    img = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(img)
    for obj in f.objects:
        for p in obj.to_primitives(MM):
            draw_prim(d, p)
    return img.point(lambda v: 255 if v > 127 else 0)


def render_holes(holes):
    img = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(img)
    for dia, x, y in holes:
        draw_prim(d, Circle(x, y, dia / 2))
    return img


def holes_of(excellon_files):
    out = []
    for f in excellon_files:
        for obj in f.drills():
            out.append((round(obj.tool.diameter, 3), round(obj.x, 3), round(obj.y, 3)))
    return sorted(out)


def load_script():
    z = zipfile.ZipFile(SCRIPT_ZIP)
    layers = {name: GerberFile.from_string(z.read(fn).decode(), filename=fn)
              for name, (fn, _) in LAYERS.items()}
    drl = ExcellonFile.from_string(z.read("shield_deck.DRL").decode(), filename="shield_deck.DRL")
    return layers, [drl]


def load_kicad():
    layers = {}
    for name, (_, pat) in LAYERS.items():
        hits = glob.glob(os.path.join(KICAD_DIR, pat))
        if len(hits) != 1:
            sys.exit(f"expected one KiCad file for {name} ({pat}), found {hits}")
        layers[name] = GerberFile.open(hits[0])
    drills = [ExcellonFile.open(p) for p in sorted(glob.glob(os.path.join(KICAD_DIR, "*.drl")))]
    return layers, drills


def diff_image(a, b):
    both = ImageChops.multiply(a, b)
    only_a = ImageChops.subtract(a, b)
    only_b = ImageChops.subtract(b, a)
    neither = ImageChops.invert(ImageChops.lighter(a, b))

    def level(mask, v):
        return mask.point(lambda p: v if p else 0)

    # the four masks are disjoint, so adding them paints each pixel once
    base = ImageChops.add(level(both, 150), level(neither, 255))
    r = ImageChops.add(base, level(only_a, 220))
    bl = ImageChops.add(base, level(only_b, 220))
    return Image.merge("RGB", (r, base, bl)), only_a, only_b


def area_mm2(img):
    return sum(1 for v in img.getdata() if v) / PX_PER_MM ** 2


def main():
    s_layers, s_drl = load_script()
    k_layers, k_drl = load_kicad()
    report = []

    s_holes, k_holes = holes_of(s_drl), holes_of(k_drl)
    report.append(f"Drill: script {len(s_holes)} holes, KiCad {len(k_holes)} holes")
    unmatched = []
    pool = list(k_holes)
    for h in s_holes:
        m = next((k for k in pool if k[0] == h[0] and abs(k[1] - h[1]) < 0.005 and abs(k[2] - h[2]) < 0.005), None)
        if m:
            pool.remove(m)
        else:
            unmatched.append(("script only", h))
    unmatched += [("KiCad only", k) for k in pool]
    report.append("  all holes match (size exact, position within 0.005 mm)" if not unmatched
                  else "\n".join(f"  {w}: {h}" for w, h in unmatched))

    s_hole_img = render_holes(s_holes)
    for name in LAYERS:
        a, b = render_gerber(s_layers[name]), render_gerber(k_layers[name])
        if "copper" in name:
            # KiCad flashes pads over the holes; the script knocks them out. Compare copper as built.
            a = ImageChops.subtract(a, s_hole_img)
            b = ImageChops.subtract(b, s_hole_img)
        img, only_a, only_b = diff_image(a, b)
        img.save(os.path.join(OUT, f"diff_{name.replace(' ', '_')}.png"))
        report.append(f"{name:14s} script {area_mm2(a):9.1f} mm2  KiCad {area_mm2(b):9.1f} mm2  "
                      f"script-only {area_mm2(only_a):7.1f}  KiCad-only {area_mm2(only_b):7.1f}")

    text = "\n".join(report)
    print(text)
    with open(os.path.join(OUT, "compare.txt"), "w") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
