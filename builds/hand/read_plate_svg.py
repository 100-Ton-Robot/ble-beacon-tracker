"""Read part placements back from the Inkscape plate layouts into parameters.csv, then check the clearance rules.

  python read_plate_svg.py            read plate_layout.svg + pipe_plate_layout.svg, update the CSV, check both
  python read_plate_svg.py alt        just the alt split plate (or: pipe)
  python read_plate_svg.py --dry-run  show what would change, write nothing
  python read_plate_svg.py --check    only check the layouts already in parameters.csv

Positions come from each part group's transform (whatever Inkscape wrote: translate, rotate, matrix), so a part may
be moved and rotated freely; scaling or flipping it is refused. Tie and M3 hole offsets come from their sub-groups.
Exit status 1 when a rule fails. Rules are the "rules" rows of parameters.csv.
"""
import argparse
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import params

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = {"alt": "plate_layout.svg", "pipe": "pipe_plate_layout.svg"}
VIEWBOX = "-85 -85 170 196"        # as make_plate_svg.py writes it
SVG = "{http://www.w3.org/2000/svg}"


# ---------------- SVG transforms ----------------

def mul(m, k):
    a, b, c, d, e, f = m
    A, B, C, D, E, F = k
    return (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f)


def parse_transform(s):
    m = (1, 0, 0, 1, 0, 0)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s or ""):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if name == "matrix":
            k = tuple(v)
        elif name == "translate":
            k = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            k = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate":
            r = math.radians(v[0])
            k = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            if len(v) == 3:
                k = mul(mul((1, 0, 0, 1, v[1], v[2]), k), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "skewX":
            k = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY":
            k = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            raise ValueError(f"unknown transform {name}")
        m = mul(m, k)
    return m


class Layout:
    def __init__(self, path):
        self.path = path
        self.root = ET.parse(path).getroot()
        vb = " ".join(self.root.get("viewBox", "").split())
        if vb != VIEWBOX:
            sys.exit(f"{path}: page viewBox is '{vb}', expected '{VIEWBOX}'. Don't resize the page "
                     "(Document Properties); re-run make_plate_svg.py and move the parts again.")
        self.parent = {c: p for p in self.root.iter() for c in p}
        self.by_id = {e.get("id"): e for e in self.root.iter() if e.get("id")}
        self.notes = []

    def elem(self, eid):
        if eid not in self.by_id:
            sys.exit(f"{self.path}: no element with id '{eid}' (was a group ungrouped or renamed?)")
        return self.by_id[eid]

    def matrix(self, eid):
        """Transform from the element's local frame to the page, through every ancestor."""
        e, chain = self.elem(eid), []
        while e is not None and e is not self.root:
            chain.append(e.get("transform"))
            e = self.parent.get(e)
        m = (1, 0, 0, 1, 0, 0)
        for tr in reversed(chain):
            m = mul(m, parse_transform(tr))
        return m

    def place(self, eid):
        """Part origin on the plate (x, y up) and the direction of its local +x axis (deg CCW)."""
        a, b, c, d, e, f = self.matrix(eid)
        if a * d - b * c < 0:
            sys.exit(f"{self.path}: '{eid}' is flipped (mirrored). Undo the flip: it would swap the part's sides.")
        if abs(math.hypot(a, b) - 1) > 1e-3 or abs(math.hypot(c, d) - 1) > 1e-3 or abs(a * c + b * d) > 1e-3:
            sys.exit(f"{self.path}: '{eid}' is scaled or skewed. Parts keep their real size: undo that.")
        return e, -f, math.degrees(math.atan2(-b, a)) % 360

    def offset(self, eid):
        """A slider sub-group's offset along its part's axis (sideways moves are reported and dropped)."""
        a, b, c, d, e, f = parse_transform(self.elem(eid).get("transform"))
        if abs(f) > 0.05:
            self.notes.append(f"'{eid}' was moved {abs(f):.2f} mm sideways: only its position along the part is kept")
        if abs(b) > 1e-3:
            self.notes.append(f"'{eid}' was rotated: rotation ignored")
        return e


def wrap180(v):
    return (v + 180) % 360 - 180


def read_alt(L):
    ch = {}
    for i in range(3):
        x, y, a = L.place(f"s{i}")
        ch[f"ALT_S{i}"] = (round(x, 2), round(y, 2), round(a, 2))
    ch["ALT_XIAO_TIE_S"] = tuple(round(L.offset(f"s{i}_tie"), 2) for i in range(3))
    x, y, a = L.place("esp32")
    ch["ALT_ESP32"], ch["ALT_ESP32_ANGLE"] = (round(x, 2), round(y, 2)), round(a, 2)
    ch["ALT_ESP32_TIES"] = tuple(round(L.offset(f"esp32_tie{k}"), 2) for k in range(2))
    x, y, a = L.place("bus")
    ch["ALT_BUS"], ch["ALT_BUS_ANGLE"] = (round(x, 2), round(y, 2)), round(a, 2)
    ch["ALT_BUS_HOLE_S"] = round(L.offset("bus_m3"), 2)
    return ch


def read_pipe(L, p):
    ch = {}
    x, y, a = L.place("s0")
    clock = math.degrees(math.atan2(x, y))
    ch["FL_XIAO_R"] = round(math.hypot(x, y), 2)
    ch["FL_XIAO_DA"] = round(wrap180(clock - p["PLATE_TURN"]), 2)             # S0's sector axis is clock 0
    ch["FL_XIAO_ROT"] = round(wrap180(a - math.degrees(math.atan2(-y, -x))), 2)
    ch["FL_TIE_S"] = round(L.offset("s0_tie"), 2)
    x, y, a = L.place("bus")
    clock = math.degrees(math.atan2(x, y)) % 360
    ch["FL_BUS"] = (round(clock, 2), round(math.hypot(x, y), 2))
    if abs(wrap180(a - (90 - clock))) > 0.5:
        L.notes.append(f"bus turned {wrap180(a - (90 - clock)):+.1f} deg off radial: the pipe plate keeps it radial "
                       "(M3 toward the rim), so only its position is kept")
    if abs(L.offset("bus_m3") - p["ALT_BUS_HOLE_S"]) > 0.05:
        L.notes.append("bus M3 hole moved: its offset (ALT_BUS_HOLE_S) is set in the alt layout, ignored here")
    return ch


# ---------------- geometry for the checks ----------------

def seg_pt(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    u = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2)) if L2 else 0.0
    return math.hypot(a[0] + u * dx - p[0], a[1] + u * dy - p[1])


def inside(p, poly):
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[-1:] + poly[:-1]):
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1:
            c = not c
    return c


def edges(poly):
    return list(zip(poly, poly[1:] + poly[:1]))


def pt_poly(p, poly):
    """Distance from a point to a polygon's outline, negative inside."""
    d = min(seg_pt(p, a, b) for a, b in edges(poly))
    return -d if inside(p, poly) else d


def cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def seg_seg(a, b, c, d):
    if cross(a, b, c, d):
        return 0.0
    return min(seg_pt(a, c, d), seg_pt(b, c, d), seg_pt(c, a, b), seg_pt(d, a, b))


def poly_poly(A, B):
    if inside(A[0], B) or inside(B[0], A):
        return -1.0
    return min(seg_seg(a, b, c, d) for a, b in edges(A) for c, d in edges(B))


def seg_poly(a, b, poly):
    if inside(a, poly) or inside(b, poly):
        return 0.0
    return min(seg_seg(a, b, c, d) for c, d in edges(poly))


def layout_geometry(t, which):
    """parts [(name, owner, polygon)], holes [(d, x, y, tag, owner)], coax [(name, owner, a, b)], plate frame."""
    ants = t.plate_antenna_holes()
    parts, coax = [], []
    if which == "alt":
        holes = [(d, x, y, tag, tag.split()[0] if tag.startswith("S") else tag) for d, x, y, tag in t.alt_plate_holes()]
        xiaos = [(cx, cy, a, t.ALT_XIAO_TIE_S[i], 1) for i, (cx, cy, a) in enumerate(t.ALT_XIAOS)]
        parts.append(("ESP32", "ESP32", t.alt_quad(*t.ALT_ESP32, t.ESP32[3] / 2, t.ESP32[2] / 2, t.ALT_ESP32_ANGLE)))
        parts.append(("bus", "bus", t.alt_quad(*t.ALT_BUS, t.POWER[3] / 2, t.POWER[2] / 2, t.ALT_BUS_ANGLE)))
        # the ESP32's ties belong to it, the M3 to the bus
        holes = [(d, x, y, tag, {"tie": "ESP32", "power": "bus"}.get(tag, o)) for d, x, y, tag, o in holes]
    else:
        holes = [(d, x, y, tag, {"power": "bus"}.get(tag, tag.split()[0] if tag.startswith("S") else tag))
                 for d, x, y, tag in t.fl_plate_holes()]
        xiaos = [(cx, cy, a, t.FL_TIE_S, t.FL_UNDER_SIDE) for cx, cy, a, _ in t.fl_xiaos()]
        bx, by = t.clock(t.FL_BUS[1], t.FL_BUS[0])
        parts.append(("bus", "bus", t.alt_quad(bx, by, t.POWER[3] / 2, t.POWER[2] / 2, 90 - t.FL_BUS[0])))
    for i, (cx, cy, a, tie_s, side) in enumerate(xiaos):
        board, *_ = t.alt_xiao(cx, cy, a, tie_s)
        ipex = t.alt_at(cx, cy, a, t.XIAO_IPEX[0], side * t.XIAO_IPEX[1])
        mount_c = t.alt_at(cx, cy, a, t.ALT_MOUNT, side * t.XIAO_IPEX[1])
        mount = t.alt_quad(*mount_c, t.ALT_MOUNT_SIDE / 2, t.ALT_MOUNT_SIDE / 2, a)
        parts += [(f"S{i}", f"S{i}", board), (f"S{i} mount", f"S{i}", mount)]
        coax.append((f"S{i} IPEX4->mount", f"S{i}", ipex, mount_c))
        for _, hx, hy, tag in ants:
            if tag.startswith(f"S{i} "):
                coax.append((f"S{i} mount->{tag[:-4].split()[1]}", f"S{i}", mount_c, (hx, hy)))
    return parts, holes, coax, ants


def check(which, p):
    import make_templates as t          # imported here so it sees the CSV just written
    parts, holes, coax, ants = layout_geometry(t, which)
    R = t.PLATE_DIAMETER / 2
    drilled = holes                     # includes the antenna holes
    own = [h for h in holes if not h[3].endswith(" ant")]
    results = []                        # (rule, limit, worst value, where, all failures)

    def rule(name, limit, items):
        items = sorted(items)
        fails = [f"{w} {v:.2f}" for v, w in items if v < limit - 1e-6]
        results.append((name, limit, items[0][0] if items else None, items[0][1] if items else "-", fails))

    rule("RULE_ANT_CLEAR", p["RULE_ANT_CLEAR"],
         [(pt_poly((x, y), poly) - d / 2, f"{n} / {tag[:-4]}") for n, _, poly in parts for d, x, y, tag in ants]
         + [(math.hypot(x - ax, y - ay) - d / 2 - ad / 2, f"{tag} hole / {atag[:-4]}")
            for d, x, y, tag, _ in own for ad, ax, ay, atag in ants])
    rule("RULE_PART_GAP", p["RULE_PART_GAP"],
         [(poly_poly(A, B), f"{na} / {nb}") for k, (na, oa, A) in enumerate(parts)
          for nb, ob, B in parts[k + 1:] if oa != ob]
         + [(pt_poly((x, y), poly) - d / 2, f"{tag} hole / {n}") for d, x, y, tag, o in own
            for n, po, poly in parts if po != o]
         + ([(pt_poly((0, 0), poly) - t.ADP_HEX_W / 2, f"{n} / adapter hex") for n, _, poly in parts]
            if which == "pipe" else []))
    rule("RULE_COAX_CLEAR", p["RULE_COAX_CLEAR"],
         [(seg_poly(a, b, poly), f"{cn} / {n}") for cn, co, a, b in coax for n, o, poly in parts if o != co])
    rule("RULE_HOLE_GAP", p["RULE_HOLE_GAP"],
         [(math.hypot(a[1] - b[1], a[2] - b[2]) - a[0] / 2 - b[0] / 2, f"{a[3]} / {b[3]}")
          for k, a in enumerate(drilled) for b in drilled[k + 1:]])
    rule("RULE_RIM_HOLE", p["RULE_RIM_HOLE"], [(R - math.hypot(x, y) - d / 2, tag) for d, x, y, tag, _ in drilled])
    rule("RULE_RIM_PART", p["RULE_RIM_PART"],
         [(R - max(math.hypot(*q) for q in poly), n) for n, _, poly in parts])

    print(f"\n{which} plate                limit  worst   at")
    bad = False
    for name, limit, worst, where, fails in results:
        flag = "ok  " if not fails else "FAIL"
        print(f"  {flag} {name:16s} {limit:5.1f}  {worst:6.2f}  {where}")
        for f in fails[:12]:
            print(f"         {f}")
        if len(fails) > 12:
            print(f"         ... {len(fails) - 12} more")
        bad |= bool(fails)
    return not bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("which", nargs="*", help="alt and / or pipe (default both)")
    ap.add_argument("--dry-run", action="store_true", help="show changes, write nothing")
    ap.add_argument("--check", action="store_true", help="only check the layouts in parameters.csv")
    args = ap.parse_args()
    which = args.which or list(FILES)
    if set(which) - set(FILES):
        ap.error(f"unknown layout {sorted(set(which) - set(FILES))}: use alt and / or pipe")

    p = params.load()
    if not args.check:
        changes = {}
        for w in which:
            L = Layout(os.path.join(HERE, FILES[w]))
            changes.update(read_alt(L) if w == "alt" else read_pipe(L, p))
            for note in L.notes:
                print(f"{FILES[w]}: note: {note}")
        if args.dry_run:
            cur = {r["name"]: r["value"] for r in params.rows()}
            diff = {k: (cur[k], params.fmt(v)) for k, v in changes.items() if cur[k] != params.fmt(v)}
        else:
            diff = params.update(changes)
        print("parameters.csv:", "no changes" if not diff else ("would change" if args.dry_run else "changed"))
        for k, (old, new) in diff.items():
            print(f"  {k:16s} {old:>22s} -> {new}")
        if args.dry_run:
            return
    ok = all([check(w, params.load()) for w in which])
    print("\nall rules pass" if ok else "\nsome rules FAIL: move the parts and run this again before printing")
    if not args.check:
        print("next: python make_templates.py  (PDF)   python make_plate_svg.py  (redraw the SVGs from the CSV)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
