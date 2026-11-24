"""Generate the deck PCBs (parts on the deck), the face PCB and the end plate PCB with KiCad 7's pcbnew API.

    python3 make_pcbs.py            # writes deck_d15, deck_d31, face_pcb and endplate_pcb .kicad_pcb, fills zones,
                                    # runs DRC, exports Gerber + drill zips, SVG previews, the 1:1 print PDF and
                                    # pcb_preview.png into out/ (preview one level up)

Sizes and rules come from parameters.csv here and ../../common/parameters.csv (groups deck, pcb, face, endplate).
Part placement and track routes are the tables below, in each core corner's local frame (u along the rim clockwise,
v out from the centre; see ../../boards/lib/kicad_lib.py).
Needs KiCad 7 or later (pcbnew Python module, kicad-cli).

Deck (revision 3, spec REV3_PLAN.md): top = electronics side (bare except the +5V tracks, the parts and the GND rim
ring), bottom = antenna side (solid GND, the shield). The three XIAOs sit inside the core, so every net runs inside the
shield; both layers carry signals there, clear of the seam strip. One deck per duck spacing in DECK_VARIANTS.
"""
import math
import os
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "common"))   # params.py, layout.py
sys.path.insert(0, os.path.join(HERE, "..", "..", "boards", "lib"))   # kicad_lib.py
import params  # noqa: E402
import kicad_lib as K  # noqa: E402
import layout  # noqa: E402
from kicad_lib import loc, pol  # noqa: E402

P = params.load(["deck", "pcb", "face", "panel", "plate", "endplate"], build="pcb")
globals().update(P)
ADAPTER_HOLE = params.load(["pipe"], build="pcb")["ADAPTER_HOLE"]
OUT = os.path.join(HERE, "out")

LAYOUT0 = layout.Layout(DECK_VARIANTS[0])     # spacing-independent values (common/layout.py)
INRADIUS = LAYOUT0.r_in
SECTORS = [0.0, 120.0, 240.0]
VERTICES = [60.0, 180.0, 300.0]       # core corners; XIAO U2 (head) / U3 / U4 sit on these
VIA_D, VIA_DRILL = VIA
F, B = pcbnew.F_Cu, pcbnew.B_Cu
FS, BS = pcbnew.F_SilkS, pcbnew.B_SilkS
CORE_LIM = LAYOUT0.core_lim


def deck_diameter(spacing):
    """Larger of DECK_MIN_DIAMETER and the D hole's exposed pad + DECK_EDGE_MARGIN (common/layout.py)."""
    return layout.Layout(spacing).deck_d


def core_ok(u, v, pad=0.0):
    """True if (u, v) in a corner frame is inside the core on the bottom, CORE_MARGIN clear of the seam strip."""
    return 0.866025 * abs(u) + 0.5 * v + pad <= CORE_LIM


def arc_pts(r, a0, a1, step=1.0):
    n = max(2, int(abs(a1 - a0) / step) + 1)
    return [pol(r, a0 + (a1 - a0) * i / (n - 1)) for i in range(n)]


def scale_bars(bd, x0, y0, x1, y1):
    """100 mm scale bars on Dwgs.User (horizontal below the board, vertical to its right) for checking a 1:1 print."""
    U = pcbnew.Dwgs_User
    for (ax, ay), (bx, by), lab, tpos, tang in (
            ((x0, y1), (x0 + 100, y1), "100 mm", (x0 + 50, y1 + 3), 0),
            ((x1, y0), (x1, y0 + 100), "100 mm", (x1 + 3, y0 + 50), 90)):
        bd.line(U, (ax, ay), (bx, by), 0.3)
        for k in range(11):
            t = k / 10
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            d = 2.5 if k % 5 == 0 else 1.2
            if ay == by:
                bd.line(U, (px, py - d), (px, py), 0.2)
            else:
                bd.line(U, (px - d, py), (px, py), 0.2)
        bd.text(U, lab, tpos, 2.0, angle=tang)


# --------------------------------------------------------------------------------------------- deck
# Layout (routes and via spots), corner frame of each XIAO. These are a layout, not measurements, so they live here.
PIN_U = XIAO_W / 2                    # castellated pad centres, both rows (pads run 1.7 mm past the board edge)
PAD_OUT = PIN_U + XIAO_PAD[0] / 2     # outer pad edge
VIA_U = 11.6                          # D7 / D10 / GND vias beside the clockwise pad row
LANE_5V_U = 13.0                      # +5V lane down the clockwise side
GND_VIA_V = XIAO_CENTRE_V + 3.5       # GND via, below the GND pad (out of the 5V pad's 2 mm pour back-off)
RING_5V = 14.2                        # top: +5V ring round the pipe hole
RING_CMD = 12.4                       # bottom: CMD ring round the pipe hole
SPOKE = [(11.2, 19.5), (10.4, 15.5)]  # bottom CMD spoke from the D7 via, between the M3 keep-out and J1 / J2
SPOKE_END = 45.0                      # ... meeting RING_CMD at this frame angle
LANE_5V = [(LANE_5V_U, 26.0), (10.5, 20.0)]
RING_5V_IN = 36.0                     # U3's +5V lane meets RING_5V at this frame angle
FACE_LANE_IN, FACE_LANE_OUT = 29.95, 30.45   # bottom branch lanes along face 0 (distance from centre)
FACE_LANE_240 = 30.2                  # U3's branch lane along face 240
UNDER_U4_V = 30.7                     # U3's lane crosses under U4 here (between its D7 and D10 vias)
HEAD_D0_VIA, HEAD_D1_VIA = (-12.6, 37.5), (-11.6, 39.58)
HEAD_DATA = [(7.5, 30.0), (5.0, 22.0)]   # bottom: head D10 via -> J1 DATA
GND_STUB_R = 21.0                     # J1 / J2 GND pins: bottom stub out past the 5V pin's pour back-off

RIGHT = ["5V", "GND", "3V3", "D10", "D9", "D8", "D7"]   # from the USB-C end (top view, USB-C up)
LEFT = [f"D{i}" for i in range(7)]


def pin_v(name):
    """v of a XIAO pin in its corner frame."""
    i = RIGHT.index(name) if name in RIGHT else LEFT.index(name)
    return XIAO_CENTRE_V + 3 * 2.54 - 2.54 * i


def cw_face_d(u, v):
    """Distance from the centre to (u, v) measured across the face clockwise of the corner (u > 0 side)."""
    return 0.866025 * u + 0.5 * v


def xiao_fp(bd, ref, theta, nets):
    """Seeed XIAO (21 x 17.8 mm), castellated pads lengthened for hand soldering. USB-C end at local -y (out)."""
    fp = K.custom_fp(bd, ref, "Seeed XIAO nRF54L15")
    pl, pw = XIAO_PAD
    for i in range(7):
        y = -3 * 2.54 + 2.54 * i
        K.smd_pad(fp, RIGHT[i], PIN_U, y, pl, pw, nets.get(RIGHT[i]), bd)
        K.smd_pad(fp, LEFT[i], -PIN_U, y, pl, pw, nets.get(LEFT[i]), bd)
    hl, hw = XIAO_L / 2, XIAO_W / 2
    K.fp_rect(fp, pcbnew.F_SilkS, (-hw - 0.1, -hl - 0.1), (hw + 0.1, hl + 0.1))
    # courtyard: the board + 0.25, wider over the pad rows only (the tie square passes the antenna-end corners)
    pr = PAD_OUT + 0.25
    py = 3 * 2.54 + pw / 2 + 0.25
    cy = [(-hw - 0.25, -hl - 0.25), (hw + 0.25, -hl - 0.25), (hw + 0.25, -py), (pr, -py), (pr, py), (hw + 0.25, py),
          (hw + 0.25, hl + 0.25), (-hw - 0.25, hl + 0.25), (-hw - 0.25, py), (-pr, py), (-pr, -py), (-hw - 0.25, -py)]
    for a, b in zip(cy, cy[1:] + cy[:1]):
        K.fp_line(fp, pcbnew.F_CrtYd, a, b, 0.05)
    K.fp_rect(fp, pcbnew.F_SilkS, (-4.5, -hl - 1.5), (4.5, -hl + 0.6))       # USB-C, overhangs the board
    ix, iy = XIAO_IPEX
    K.fp_circle(fp, pcbnew.F_SilkS, (-iy, ix), 1.3)                           # IPEX4, toward the antenna end
    bd.add_fp(fp, ref, "XIAO", loc(theta, 0, XIAO_CENTRE_V), K.fp_orient(theta))
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    return fp


def rpsma_fp(bd, ref, pos):
    fp = K.custom_fp(bd, ref, "RP-SMA")
    K.th_pad(fp, "1", 0, 0, PAD_EXPOSE, HOLE_RPSMA, "GND", bd)
    bd.add_fp(fp, ref, "RP-SMA", pos, 0)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    return fp


def npth_fp(bd, ref, pos, d):
    fp = K.custom_fp(bd, ref, "hole")
    K.th_pad(fp, "", 0, 0, d, d, None, None, plated=False)
    bd.add_fp(fp, ref, "hole", pos, 0)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    return fp


def m3_fp(bd, ref, pos):
    """Registration M3: plated hole in a GND ring both sides, washer keep-out marked on both sides."""
    fp = K.custom_fp(bd, ref, "M3")
    K.th_pad(fp, "1", 0, 0, M3_PAD, COLLAR_HOLE, "GND", bd)
    K.fp_circle(fp, pcbnew.F_SilkS, (0, 0), M3_KEEPOUT / 2, 0.15)
    K.fp_circle(fp, pcbnew.B_SilkS, (0, 0), M3_KEEPOUT / 2, 0.15)
    K.fp_circle(fp, pcbnew.F_CrtYd, (0, 0), M3_KEEPOUT / 2, 0.05)
    bd.add_fp(fp, ref, "M3", pos, 0)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    circ = [(pos[0] + M3_KEEPOUT / 2 * math.cos(2 * math.pi * i / 48),
             pos[1] + M3_KEEPOUT / 2 * math.sin(2 * math.pi * i / 48)) for i in range(48)]
    ls = pcbnew.LSET()
    ls.AddLayer(F)
    ls.AddLayer(B)
    bd.keepout(ls, circ, tracks=True, vias=True, pads=False, pours=False)
    return fp


def tie_geom(theta):
    """Tie square for the XIAO on corner theta: (IPEX4, centre, cable direction, corners) in the corner frame
    (common/layout.py)."""
    return LAYOUT0.tie(theta)


def tie_fp(bd, ref, theta):
    """Adhesive tie-mount spot: silkscreen square + courtyard, turned square to the pigtail, no copper under it."""
    ipex, c, d, sq = tie_geom(theta)
    fp = K.custom_fp(bd, ref, "HS-100 tie mount")
    cw = loc(theta, *c)
    w = [loc(theta, *p) for p in sq]
    rel = [(x - cw[0], y - cw[1]) for x, y in w]
    for a, b in zip(rel, rel[1:] + rel[:1]):
        K.fp_line(fp, pcbnew.F_SilkS, a, b, 0.15)
    grow = [(x * (1 + 0.25 / (MOUNT_SQ / 2)), y * (1 + 0.25 / (MOUNT_SQ / 2))) for x, y in rel]
    for a, b in zip(grow, grow[1:] + grow[:1]):
        K.fp_line(fp, pcbnew.F_CrtYd, a, b, 0.05)
    bd.add_fp(fp, ref, "tie mount", cw, 0)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    a_cable = math.atan2(d[0], d[1])
    tang = (-(theta + math.degrees(a_cable)) + 90 + 90) % 180 - 90   # along the cable, never upside down
    off = MOUNT_SQ / 2 - 2.6                              # label beside the cable line, inside the square
    n = (math.cos(a_cable), -math.sin(a_cable))
    bd.text(FS, "ANT STRAIN\nRELIEF TIE", loc(theta, c[0] + off * n[0], c[1] + off * n[1]), 1.0, angle=tang)
    # dotted pigtail path: from the IPEX4 marker along the cable through the tie, then bent PIGTAIL_BEND toward
    # its sector, over the face line to the D / P / P2 holes; arrowhead before the slots
    b = math.radians(PIGTAIL_ANGLE + PIGTAIL_BEND)
    db = (math.sin(b), math.cos(b))
    face = lambda p: -0.866025 * p[0] + 0.5 * p[1]  # noqa: E731   distance across its sector's face (u < 0 side)
    stop = INRADIUS - SLOT_W / 2 - FACE_THICK / 2 - 1.6

    def dots(p0, dvec, length):
        t = 0.0
        while t <= length:
            q = (p0[0] + t * dvec[0], p0[1] + t * dvec[1])
            bd.line(FS, loc(theta, *q), loc(theta, q[0] + 0.3 * dvec[0], q[1] + 0.3 * dvec[1]), 0.25)
            t += 1.0
    dots((ipex[0] + 1.6 * d[0], ipex[1] + 1.6 * d[1]), d, TIE_FROM_IPEX - 1.6)
    t1 = 0.0
    while face((c[0] + (t1 + 0.1) * db[0], c[1] + (t1 + 0.1) * db[1])) < stop:
        t1 += 0.1
    dots(c, db, t1 - 0.4)
    tip = (c[0] + t1 * db[0], c[1] + t1 * db[1])
    for sgn in (-1, 1):
        r = b + math.pi + sgn * math.radians(28)
        bd.line(FS, loc(theta, *tip), loc(theta, tip[0] + 1.4 * math.sin(r), tip[1] + 1.4 * math.cos(r)), 0.2)
    s = theta - 60
    return fp, s


def slot_polys(gap=0.0):
    from shapely.geometry import Polygon
    out = []
    rv = INRADIUS - FACE_THICK / 2
    for s in SECTORS:
        for t in FACE_TABS:
            out.append(Polygon([loc(s, t + du, rv + dv) for du, dv in (
                (-SLOT_L / 2 - gap, -SLOT_W / 2 - gap), (SLOT_L / 2 + gap, -SLOT_W / 2 - gap),
                (SLOT_L / 2 + gap, SLOT_W / 2 + gap), (-SLOT_L / 2 - gap, SLOT_W / 2 + gap))]))
    return out


def tie_check(bd):
    """KiCad's DRC can't see silkscreen-only footprints: check each tie square against the pipe hole, the slots, the M3
    holes and every pad, MOUNT_GAP clear. Returns rows (ref, pipe, slot, nearest pad or hole) in mm."""
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    pipe = Point(K.CX, K.CY).buffer(ADAPTER_HOLE / 2, 128)
    slots = unary_union(slot_polys())
    pads = []
    for fp in bd.b.GetFootprints():
        if fp.GetReference().startswith("TM"):
            continue
        for p in fp.Pads():
            pads.append(Polygon(pad_poly(p, 0.0)))
        if fp.GetReference().startswith("M"):     # M3 washer keep-out
            q = fp.GetPosition()
            pads.append(Point(pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)).buffer(M3_KEEPOUT / 2, 64))
    pads = unary_union(pads)
    rows = []
    for k, th in enumerate(VERTICES):
        _, c, _, sq = tie_geom(th)
        poly = Polygon([loc(th, *p) for p in sq])
        row = (f"TM{k + 1}", poly.distance(pipe), poly.distance(slots), poly.distance(pads))
        if min(row[1:]) < MOUNT_GAP:
            raise RuntimeError(f"tie square {row[0]} too close: pipe {row[1]:.2f} slot {row[2]:.2f} pad {row[3]:.2f}")
        rows.append(row)
    return rows


def pad_poly(p, grow):
    """A pad's outline grown by `grow` mm, as a list of points (for pour keep-outs)."""
    from shapely.geometry import Polygon
    ps = p.GetEffectivePolygon()
    ol = ps.Outline(0)
    pts = [(pcbnew.ToMM(ol.CPoint(i).x), pcbnew.ToMM(ol.CPoint(i).y)) for i in range(ol.PointCount())]
    g = Polygon(pts).buffer(grow, 16).simplify(0.05) if grow else Polygon(pts)
    return list(g.exterior.coords)[:-1]


ASSEMBLY_STEPS = ("ASSEMBLY\n"
                  "1 DECK: BREAK OUT THE KNOCKOUT,\n"
                  "  FILE THE NUBS FLUSH\n"
                  "2 FACES TO DECK + END PLATE\n"
                  "  FIRST, ON THE BARE BOARDS\n"
                  "3 CLEAN (IPA)\n"
                  "4 J1 + J2, THEN THE XIAOS\n"
                  "5 RP-SMAS, COAX, TIE MOUNTS\n"
                  "6 SPLITTER LEAD TO J2")
REPO_URL = "github.com/100-Ton-Robot/ble-beacon-tracker"
USB_WARNING = "UNPLUG POE\nBEFORE USB"
POWER_WARNING = "UNPLUG POE BEFORE USB\nDamage from ignoring this is not covered.\nBuild at your own risk."
WARN_DECK = "UNPLUG POE BEFORE USB\nDamage from ignoring this\nis not covered.\nBuild at your own risk."


def seam_guides(bd, layer, mirror, rmax=None, label_at=(0.0, 11.0), size=1.5):
    """Guide lines either side of each face's seam strip and a tick + label at each face centre. rmax clips the
    lines to a board radius (the end plate). label_at: the label's (u, v - INRADIUS) in the sector frame."""
    for s in SECTORS:
        for off in (-(SEAM_STRIP / 2 + 0.6), SEAM_STRIP / 2 + 0.6):
            r = INRADIUS + off
            half = (FACE_WIDTH / 2) * r / INRADIUS - 1.0
            if rmax:
                half = min(half, math.sqrt(rmax ** 2 - r ** 2))
            bd.line(layer, loc(s, -half, r), loc(s, half, r), 0.2)
        bd.line(layer, loc(s, 0, INRADIUS + SEAM_STRIP / 2 + 0.6), loc(s, 0, INRADIUS + SEAM_STRIP / 2 + 6), 0.3)
        bd.text(layer, f"FACE S{SECTORS.index(s)} CENTRE", loc(s, label_at[0], INRADIUS + label_at[1]), size,
                angle=-s, mirror=mirror)


def jst_fp(bd, ref, lib_name, value, r, a, nets, label):
    """JST PH vertical through-hole at radius r, angle a: pin row tangential, pin 1 at the clockwise end, housing
    toward the rim. Housing outline on both sides (the builder fits it on either). Returns {pin: (u, v)} in frame a."""
    n = len(nets)
    fp = bd.lib_fp("Connector_JST", lib_name, ref, value, loc(a, (n - 1), r), K.fp_orient(a, 180), nets)
    fp.Reference().SetVisible(False)
    pins = {p: K.to_local(a, *bd.pad_xy(ref, p)) for p in nets}
    assert pins["1"][0] > pins[str(n)][0] and abs(pins["1"][0] + pins[str(n)][0]) < 0.01, f"{ref} pin order {pins}"
    p1 = bd.pad_xy(ref, "1")
    p2 = bd.pad_xy(ref, "2")
    ex = ((p2[0] - p1[0]) / 2, (p2[1] - p1[1]) / 2)
    ey = (-ex[1], ex[0])
    w = lambda x, y: (p1[0] + x * ex[0] + y * ey[0], p1[1] + x * ex[1] + y * ey[1])  # noqa: E731
    x1 = 2 * (n - 1) + 1.95
    body = [w(-1.95, -1.7), w(x1, -1.7), w(x1, 2.8), w(-1.95, 2.8)]
    bd.poly(BS, body, 0.15)
    for lay, mir in ((FS, False), (BS, True)):
        bd.text(lay, label, loc(a, 0, r + 4.4), 1.0, angle=-a, mirror=mir)
        bd.text(lay, "1", loc(a, pins["1"][0], r - 2.7), 0.9, angle=-a, mirror=mir)
    return pins


def knockout(bd, ref):
    """Centre knockout, the same on the deck and the end plate: a routed ring (outer edge = ADAPTER_HOLE, the hole
    once broken out) held by KO_BRIDGE bridges with mouse bites on the plate side, and an RP-SMA hole in the disc.
    The disc is its own copper (net GND_KO, both sides) once the ring is routed. Returns the ring's outer and inner
    radius."""
    ro = ADAPTER_HOLE / 2
    ri = ro - KO_CHANNEL
    rc = (ro + ri) / 2
    bw, nb = KO_BRIDGE
    hb = math.degrees(bw / 2 / rc)
    md, mp = MOUSE_BITE
    for k in range(nb):
        a0 = 45 + 360 * k / nb + hb
        a1 = 45 + 360 * (k + 1) / nb - hb
        bd.poly(pcbnew.Edge_Cuts, arc_pts(ro, a0, a1, 2.0) + arc_pts(ri, a1, a0, 2.0), 0.1)
        ab = 45 + 360 * k / nb
        for j in (-1, 0, 1):   # holes on the plate side of the bridge, tangent to the finished hole edge
            npth_fp(bd, f"MB{k * 3 + j + 2}", loc(ab, j * mp, ro - md / 2), md)
    fp = K.custom_fp(bd, ref, "RP-SMA")
    K.th_pad(fp, "1", 0, 0, PAD_EXPOSE, HOLE_RPSMA, "GND_KO", bd)
    bd.add_fp(fp, ref, "RP-SMA", (K.CX, K.CY), 0)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    circ = [pol(ri, 360 * i / 180) for i in range(180)]
    for lay in (F, B):
        bd.zone(lay, circ, "GND_KO", 1, thermal=False)
    return ro, ri


def warn_icon(bd, layer, text, pos, size, angle, side="before", height=4.0):
    """ISO 7010 W001-style caution sign (triangle with !) drawn in silkscreen lines beside a warning text: before
    its first character (side "before"), after its end ("after") or above it ("above"), upright with the text.
    The text's extent is estimated from its line lengths (KiCad's stroke font is ~0.9 x size per character)."""
    lines = text.split("\n")
    half_l = max(len(s) for s in lines) * size * 0.9 / 2
    half_h = len(lines) * size * 1.6 / 2
    A = math.radians(angle)
    b = (math.cos(A), -math.sin(A))      # baseline direction on the board (KiCad y down, angles counter-clockwise)
    up = (-math.sin(A), -math.cos(A))
    gap = height * 0.6 + 1.0
    k = {"before": (-(half_l + gap), 0.0), "after": (half_l + gap, 0.0), "above": (0.0, half_h + gap)}[side]
    c = (pos[0] + k[0] * b[0] + k[1] * up[0], pos[1] + k[0] * b[1] + k[1] * up[1])
    P = lambda x, y: (c[0] + x * b[0] + y * up[0], c[1] + x * b[1] + y * up[1])  # noqa: E731   local: x along, y up
    h = height
    s = h * 2 / math.sqrt(3)
    tri = [P(0, 2 * h / 3), P(s / 2, -h / 3), P(-s / 2, -h / 3)]
    bd.poly(layer, tri, 0.25)
    bd.line(layer, P(0, 0.32 * h), P(0, -0.05 * h), 0.35)
    bd.line(layer, P(0, -0.18 * h), P(0, -0.2 * h), 0.4)


def url_text(bd, layer, pos, angle=0.0, mirror=False, size=0.9, one_line=False):
    sep = "" if one_line else "\n"
    bd.text(layer, REPO_URL.replace("Robot/", "Robot/" + sep), pos, size, angle=angle, mirror=mirror)


def build_deck(spacing):
    bd = K.Board()
    bd.rules(CLEARANCE, TRACK, VIA_D, VIA_DRILL, edge=EDGE_CLEAR)
    C = (K.CX, K.CY)
    R = deck_diameter(spacing) / 2
    t0, t1, t2 = VERTICES

    # outline; centre knockout (broken out for the pipe on a deck, kept or broken out on a deck used as end plate)
    bd.circle(pcbnew.Edge_Cuts, C, R, 0.1)
    knockout(bd, "H10")

    # antenna holes (D, P, P2), plated, 12 mm exposed GND pads both sides; one antenna per sector
    LY = layout.Layout(spacing)
    a = INRADIUS
    p2_u = -LY.s_P2
    n = 0
    for s in SECTORS:
        for pos in (loc(s, 0, LY.r_D), loc(s, 0, LY.r_P), loc(s, p2_u, LY.r_P)):
            n += 1
            rpsma_fp(bd, f"H{n}", pos)
    for k, am in enumerate(LY.m3_angles):
        m3_fp(bd, f"M{k + 1}", pol(LY.m3_r, am))
    for k in range(STITCH_COUNT):
        bd.via(pol(R - RIM_MASK_WIDTH / 2, k * 360 / STITCH_COUNT), "GND", VIA_D, VIA_DRILL)

    # face slots: each face's tabs drop into these; centred on the face board (its outer copper is the face line)
    rv = INRADIUS - FACE_THICK / 2
    for s in SECTORS:
        for t in FACE_TABS:
            c = [loc(s, t + du, rv + dv) for du, dv in ((-SLOT_L / 2, -SLOT_W / 2), (SLOT_L / 2, -SLOT_W / 2),
                                                        (SLOT_L / 2, SLOT_W / 2), (-SLOT_L / 2, SLOT_W / 2))]
            bd.poly(pcbnew.Edge_Cuts, c, 0.1)
            k = [loc(s, t + du, rv + dv) for du, dv in ((-SLOT_L / 2 - 1, -SLOT_W / 2 - 1), (SLOT_L / 2 + 1, -SLOT_W / 2 - 1),
                                                        (SLOT_L / 2 + 1, SLOT_W / 2 + 1), (-SLOT_L / 2 - 1, SLOT_W / 2 + 1))]
            ls = pcbnew.LSET()
            ls.AddLayer(F)
            bd.keepout(ls, k)

    # ---- XIAOs: U2 head (60 deg, 2 o'clock), U3 (180, 6 o'clock) -> head D0 (Branch 1), U4 (300) -> head D1 (Branch 2)
    common = {"5V": "+5V", "GND": "GND", "D7": "CMD"}
    nets = {t0: dict(common, D10="DATA", D0="BRANCH1", D1="BRANCH2"),
            t1: dict(common, D10="BRANCH1"),
            t2: dict(common, D10="BRANCH2")}
    for k, th in enumerate(VERTICES):
        xiao_fp(bd, f"U{k + 2}", th, nets[th])
        ref = f"U{k + 2}"
        for pin in ("5V", "GND", "D7", "D10", "D0"):
            u, v = K.to_local(th, *bd.pad_xy(ref, pin))
            want = (PIN_U if pin != "D0" else -PIN_U, pin_v(pin))
            assert abs(u - want[0]) < 0.01 and abs(v - want[1]) < 0.01, f"{ref}.{pin} at {u:.2f} {v:.2f}"
        for u, v in ((-PAD_OUT, pin_v("D0") + XIAO_PAD[1] / 2), (PAD_OUT, pin_v("5V") + XIAO_PAD[1] / 2)):
            assert core_ok(u, v, -0.05), f"{ref} pad corner {u:.2f} {v:.2f} outside the core"

    # ---- J1 (to the ESP32, like the carrier Up port) and J2 (5V in)
    j1r, j1a = J1_POS
    j2r, j2a = J2_POS
    j1 = jst_fp(bd, "J1", "JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical", "B4B-PH-K-S", j1r, j1a,
                {"1": "+5V", "2": "GND", "3": "DATA", "4": "CMD"}, "J1 TO ESP32")
    j2 = jst_fp(bd, "J2", "JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical", "B2B-PH-K-S", j2r, j2a,
                {"1": "+5V", "2": "GND"}, "J2 5V IN")
    for p, (u, v) in list(j1.items()) + list(j2.items()):
        assert core_ok(u, v, 1.0), "J1 / J2 pins must be inside the core"
    w1 = {p: loc(j1a, *uv) for p, uv in j1.items()}   # world positions
    w2 = {p: loc(j2a, *uv) for p, uv in j2.items()}
    ang_of = lambda q: math.degrees(math.atan2(q[0] - K.CX, K.CY - q[1]))  # noqa: E731

    # ---- rings round the pipe hole: +5V on top, CMD on the bottom
    ring = lambda r: arc_pts(r, 0, 360, 2.0)  # noqa: E731
    bd.track(ring(RING_5V), "+5V", TRACK_5V, F)
    bd.track(ring(RING_CMD), "CMD", TRACK, B)

    # ---- per XIAO, clockwise pad row: GND, D7 and D10 to vias at VIA_U, +5V down a lane to the ring / J1 / J2
    for k, th in enumerate(VERTICES):
        L = lambda pts, th=th: [loc(th, u, v) for u, v in pts]  # noqa: E731
        circ = lambda r, ad, th=th: loc(th, r * math.sin(math.radians(ad)), r * math.cos(math.radians(ad)))  # noqa: E731
        vg, v7, v10, v5 = GND_VIA_V, pin_v("D7"), pin_v("D10"), pin_v("5V")
        bd.track(L([(PIN_U, pin_v("GND")), (VIA_U, vg)]), "GND", 0.5)
        bd.via(loc(th, VIA_U, vg), "GND", VIA_D, VIA_DRILL)
        bd.track(L([(PIN_U, v7), (VIA_U, v7)]), "CMD", TRACK)
        bd.via(loc(th, VIA_U, v7), "CMD", VIA_D, VIA_DRILL)
        bd.track(L([(VIA_U, v7)] + SPOKE) + [circ(RING_CMD, SPOKE_END)], "CMD", TRACK, B)
        d10 = nets[th]["D10"]
        bd.track(L([(PIN_U, v10), (VIA_U, v10)]), d10, TRACK)
        bd.via(loc(th, VIA_U, v10), d10, VIA_D, VIA_DRILL)
        for u, v in [(VIA_U, vg), (VIA_U, v7), (VIA_U, v10)] + SPOKE:
            assert core_ok(u, v, VIA_D / 2), f"via / spoke at {u} {v} outside the core"
        lane = L([(PIN_U, v5), (LANE_5V_U, v5)] + LANE_5V)
        if th == t0:
            lane.append(w1["1"])
        elif th == t2:
            lane.append(w2["1"])
        else:
            lane.append(circ(RING_5V, RING_5V_IN))
        bd.track(lane, "+5V", TRACK_5V)

    # J1 / J2: +5V pin straight in to the ring (top); J1 CMD straight in to its ring (bottom); GND pins out (bottom)
    for wp, r in ((w1["1"], RING_5V), (w2["1"], RING_5V)):
        bd.track([wp, pol(r, ang_of(wp))], "+5V", TRACK_5V)
    bd.track([w1["4"], pol(RING_CMD, ang_of(w1["4"]))], "CMD", TRACK, B)
    for wp in (w1["2"], w2["2"]):
        bd.track([wp, pol(GND_STUB_R, ang_of(wp))], "GND", 0.5, B)
    # head D10 -> J1 DATA, on the bottom under the head
    bd.track([loc(t0, VIA_U, pin_v("D10"))] + [loc(t0, u, v) for u, v in HEAD_DATA] + [w1["3"]], "DATA", TRACK, B)

    # ---- branches: head D0 / D1 down to vias on its counter-clockwise side (top), then bottom lanes along the faces
    for pin, via in (("D0", HEAD_D0_VIA), ("D1", HEAD_D1_VIA)):
        net = nets[t0][pin]
        v = pin_v(pin)
        pts = [(-PIN_U, v), (via[0], v), via] if pin == "D0" else [(-PIN_U, v), via]
        bd.track([loc(t0, *p) for p in pts], net, TRACK)
        bd.via(loc(t0, *via), net, VIA_D, VIA_DRILL)
        assert core_ok(*via, VIA_D / 2)
    s0 = lambda u, v: loc(0, u, v)  # noqa: E731      sector 0 frame (face 0 runs U4 -> head)
    d0u = K.to_local(0, *loc(t0, *HEAD_D0_VIA))[0]
    d1u = K.to_local(0, *loc(t0, *HEAD_D1_VIA))[0]
    v10 = pin_v("D10")
    ua = lambda d: (d - 0.5 * v10) / 0.866025  # noqa: E731     u (cw side) where the D10 row meets lane distance d
    # U4 -> head D1: outer lane on face 0
    bd.track([loc(t2, VIA_U, v10), loc(t2, ua(FACE_LANE_OUT), v10), s0(d1u - 0.7, FACE_LANE_OUT),
              loc(t0, *HEAD_D1_VIA)], "BRANCH2", TRACK, B)
    # U3 -> head D0: along face 240, under U4 (between its D7 and D10 vias), inner lane on face 0
    ub = (FACE_LANE_240 - 0.5 * UNDER_U4_V) / 0.866025
    uc = (FACE_LANE_IN - 0.5 * UNDER_U4_V) / 0.866025
    bd.track([loc(t1, VIA_U, v10), loc(t1, ua(FACE_LANE_240), v10), loc(t2, -ub, UNDER_U4_V),
              loc(t2, uc, UNDER_U4_V), s0(d0u - 0.6, FACE_LANE_IN), loc(t0, *HEAD_D0_VIA)], "BRANCH1", TRACK, B)
    for d in (FACE_LANE_IN, FACE_LANE_OUT, FACE_LANE_240):
        assert d + TRACK / 2 <= CORE_LIM, "branch lane outside the core"

    # ---- zones: bottom GND (shield), top GND rim ring; no +5V pour (tracks only)
    circ = lambda r, n=180: [pol(r, 360 * i / n) for i in range(n)]  # noqa: E731
    bd.zone(B, circ(R + 1), "GND", 0, thermal=False, name="shield")
    bd.zone(F, circ(R + 1), "GND", 2, holes=[circ(R - RIM_MASK_WIDTH)], thermal=False, name="rim")
    # bottom pour held GND_BACKOFF_5V back from every +5V pad, inside the core only (the seam strip stays whole)
    from shapely.geometry import Polygon
    core = Polygon([pol(2 * CORE_LIM, v) for v in VERTICES])
    lsb = pcbnew.LSET()
    lsb.AddLayer(B)
    for fp in list(bd.b.GetFootprints()):
        for p in fp.Pads():
            if p.GetNetname() == "+5V":
                g = Polygon(pad_poly(p, GND_BACKOFF_5V)).intersection(core)
                bd.keepout(lsb, list(g.exterior.coords)[:-1], tracks=False, vias=False, pads=False, pours=True)
    # mask: rim ring both sides, seam strip on the bottom
    for lay in (pcbnew.F_Mask, pcbnew.B_Mask):
        bd.circle(lay, C, R - RIM_MASK_WIDTH / 2, RIM_MASK_WIDTH)
    verts = [pol(2 * INRADIUS, v) for v in VERTICES]
    for i in range(3):
        bd.line(pcbnew.B_Mask, verts[i], verts[(i + 1) % 3], SEAM_STRIP)

    # ---- silkscreen, top
    band = lambda s, u, v: loc(s, u, v)  # noqa: E731   text goes in each sector's clockwise half, outside the triangle
    for i, s in enumerate(SECTORS):
        bd.text(FS, f"S{i}", loc(s, 9.5, a + PATCH_OFFSET), 2.0, angle=-s)
        bd.text(FS, "D", loc(s, -8.5, a + spacing), 1.5, angle=-s)
        bd.text(FS, "P", loc(s, -8.5, a + PATCH_OFFSET), 1.5, angle=-s)
        bd.text(FS, "P2", loc(s, p2_u, a + PATCH_OFFSET + 8.3), 1.5, angle=-s)
    for th, lab in ((t0, "U2 HEAD"), (t1, "U3 -> HEAD D0"), (t2, "U4 -> HEAD D1")):
        bd.text(FS, lab, loc(th, 0, XIAO_CENTRE_V + XIAO_L / 2 + 12.5), 1.0, angle=-th)
        # USB-C plug path (13 x 25 mm past the USB-C end), for the print check
        uw = loc(th, 0, XIAO_CENTRE_V + XIAO_L / 2 + 3.6)   # right in front of the USB-C plug, across its path
        bd.text(FS, USB_WARNING, uw, 0.9, angle=-th)
        warn_icon(bd, FS, USB_WARNING, uw, 0.9, -th, "above", 3.2)
        x = [(-6.5, 45.0), (6.5, 45.0), (6.5, 70.0), (-6.5, 70.0)]
        bd.poly(pcbnew.Dwgs_User, [loc(th, u, v) for u, v in x], 0.15)
    bd.text(FS, "TOP - ELECTRONICS SIDE", band(0, 19.5, a + 19.5), 1.3, angle=0)
    bd.text(FS, "J1 TO ESP32: 1 5V  2 GND\n3 DATA (HEAD D10)  4 CMD\nJ2 5V IN: 1 +  2 GND", band(0, 19.5, a + 14.5), 0.8,
            angle=0)
    bd.text(FS, WARN_DECK, band(120, 17.5, a + 14.0), 1.0, angle=-120)
    warn_icon(bd, FS, WARN_DECK, band(120, 17.5, a + 14.0), 1.0, -120, "after")
    bd.text(FS, ASSEMBLY_STEPS, band(240, 18.5, a + 15.0), 0.8, angle=-240)
    for lay, mir in ((FS, False), (BS, True)):   # beside J2 (5V in from PoE), both sides like its outline
        jw = loc(J2_POS[1], -7.0, J2_POS[0] - 1.5)   # counter-clockwise of J2, below U4's antenna end
        bd.text(lay, USB_WARNING, jw, 0.8, angle=-J2_POS[1], mirror=mir)
        warn_icon(bd, lay, USB_WARNING, jw, 0.8, -J2_POS[1], "before", 2.8)
    bd.text(FS, "AS END PLATE:\nTHIS SIDE OUT, NO PARTS", band(0, 19.5, a + 23.5), 0.9, angle=0)
    url_text(bd, FS, band(120, 19.5, a + 21.5), angle=-120)
    bd.text(FS, "KNOCKOUT", pol(7.6, 0), 0.8)
    scale_bars(bd, K.CX - 50, K.CY - 50, K.CX + R + 8, K.CY + R + 6)
    # tie mounts, one per XIAO pigtail
    for k, th in enumerate(VERTICES):
        tie_fp(bd, f"TM{k + 1}", th)

    # ---- silkscreen, bottom
    seam_guides(bd, BS, True, R - 1.0, label_at=(19.5, 5.2), size=1.2)
    for i, s in enumerate(SECTORS):
        bd.text(BS, "ONE ANTENNA: D, P OR P2", loc(s, 19.5, a + 8.2), 1.0, angle=-s, mirror=True)
    bd.text(BS, "BOTTOM - ANTENNA SIDE", band(0, 19.5, a + 12.0), 1.2, angle=0, mirror=True)
    bd.text(BS, "SOLDER FACES\nBEFORE ANY PARTS", band(120, 19.5, a + 12.8), 1.2, angle=-120, mirror=True)
    bd.text(BS, f"DUCK SPACING {spacing:g} MM", band(240, 19.5, a + 12.0), 1.2, angle=-240, mirror=True)
    bd.text(BS, "THIS SIDE TO THE CORE\n(AS DECK OR END PLATE)", band(0, 19.5, a + 16.5), 1.0, angle=0, mirror=True)
    url_text(bd, BS, band(240, 19.5, a + 16.8), angle=-240, mirror=True)
    bd.text(BS, "KNOCKOUT", pol(7.6, 0), 0.8, mirror=True)
    return bd


# --------------------------------------------------------------------------------------------- face
def build_face():
    """One face design for both ends: tabs, relief notches and exposed seam copper on the deck edge and on the
    end plate edge. Solid GND both sides, one plated RP-SMA hole at the centre (DIPOLE_HOLE)."""
    bd = K.Board()
    bd.rules(CLEARANCE, TRACK, VIA_D, VIA_DRILL, edge=0.3)
    w, h = FACE_W, FACE_H
    x0, y0 = K.CX - w / 2, K.CY - h / 2
    x1, y1 = x0 + w, y0 + h
    th = FACE_THICK
    rw, rd = TAB_RELIEF   # relief notch each side of a tab root, so the router's inside-corner radius lands
    outline = [(x0, y0)]  # in the notch, not on the edge that seats on the plate
    for t in sorted(FACE_TABS):                  # top edge (end plate), left to right
        cx = K.CX + t
        c, a = cx - TAB_W / 2, cx + TAB_W / 2
        outline += [(c - rw, y0), (c - rw, y0 + rd), (c, y0 + rd), (c, y0 - th),
                    (a, y0 - th), (a, y0 + rd), (a + rw, y0 + rd), (a + rw, y0)]
    outline += [(x1, y0), (x1, y1)]
    for t in sorted(FACE_TABS, reverse=True):    # bottom edge (deck), right to left
        cx = K.CX + t
        a, c = cx + TAB_W / 2, cx - TAB_W / 2
        outline += [(a + rw, y1), (a + rw, y1 - rd), (a, y1 - rd), (a, y1 + th),
                    (c, y1 + th), (c, y1 - rd), (c - rw, y1 - rd), (c - rw, y1)]
    outline += [(x0, y1)]
    bd.poly(pcbnew.Edge_Cuts, outline, 0.1)
    fp = K.custom_fp(bd, "H1", "RP-SMA")
    K.th_pad(fp, "1", 0, 0, PAD_EXPOSE, DIPOLE_HOLE, "GND", bd)
    bd.add_fp(fp, "H1", "RP-SMA", (K.CX, K.CY), 0)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    rect = [(x0 - 1, y0 - th - 1), (x1 + 1, y0 - th - 1), (x1 + 1, y1 + th + 1), (x0 - 1, y1 + th + 1)]
    bd.zone(F, rect, "GND", 0, thermal=False)
    bd.zone(B, rect, "GND", 0, thermal=False)
    for k in range(4):   # stitching vias round the hole and along the edges
        bd.via((K.CX + 9 * math.cos(k * math.pi / 2 + math.pi / 4), K.CY + 9 * math.sin(k * math.pi / 2 + math.pi / 4)),
               "GND", VIA_D, VIA_DRILL)
    for t in range(1, 12):
        for x, y in ((x0 + 5, y0 + 10 * t), (x1 - 5, y0 + 10 * t), (x0 + 10 * t, y1 - 5), (x0 + 10 * t, y0 + 5)):
            bd.via((x, y), "GND", VIA_D, VIA_DRILL)
    e = FACE_EDGE_EXPOSE
    for lay in (pcbnew.F_Mask, pcbnew.B_Mask):   # exposed seam edges: left, right, deck end, end plate end
        bd.line(lay, (x0 + e / 2, y0), (x0 + e / 2, y1), e)
        bd.line(lay, (x1 - e / 2, y0), (x1 - e / 2, y1), e)
        bd.line(lay, (x0, y1 - e / 2), (x1, y1 - e / 2), e)
        bd.line(lay, (x0, y0 + e / 2), (x1, y0 + e / 2), e)
        for t in FACE_TABS:
            bd.line(lay, (K.CX + t, y1 - e), (K.CX + t, y1 + th), TAB_W)
            bd.line(lay, (K.CX + t, y0 + e), (K.CX + t, y0 - th), TAB_W)
    for lay, mir in ((FS, False), (BS, True)):
        bd.line(lay, (K.CX, y0 + e + 0.6), (K.CX, K.CY - PAD_EXPOSE / 2 - 1), 0.2)
        bd.line(lay, (K.CX, K.CY + PAD_EXPOSE / 2 + 1), (K.CX, y1 - e - 0.6), 0.2)
        for y in (y1 - e - 0.6, y0 + e + 0.6):
            bd.line(lay, (K.CX - 6, y), (K.CX + 6, y), 0.3)
        bd.text(lay, "TABS INTO THE DECK OR END PLATE SLOTS", (K.CX + (-30 if mir else 30), y1 - 10), 1.3, mirror=mir)
        bd.text(lay, "TABS INTO THE DECK OR END PLATE SLOTS", (K.CX + (-30 if mir else 30), y0 + 10), 1.3, mirror=mir)
    scale_bars(bd, K.CX - 50, K.CY - 50, x1 + 8, y1 + th + 6)
    bd.text(FS, "OUTSIDE - DIPOLE SIDE", (K.CX - 28, y0 + 16), 2.0)
    bd.text(BS, "INSIDE - CORE SIDE", (K.CX + 28, y0 + 16), 2.0, mirror=True)
    bd.text(FS, POWER_WARNING, (K.CX - 31, K.CY), 1.1)
    warn_icon(bd, FS, POWER_WARNING, (K.CX - 31, K.CY), 1.1, 0, "above", 5.0)
    url_text(bd, FS, (K.CX + 28, K.CY + 20), size=1.2, one_line=True)
    url_text(bd, BS, (K.CX - 28, K.CY + 20), mirror=True, size=1.2, one_line=True)
    return bd


# --------------------------------------------------------------------------------------------- end plate
def build_endplate():
    """End plate across the far end of the triangle: bare GND copper both sides, slots for the face tabs, seam
    copper on the inside (top) and a centre RP-SMA hole in a knockout that breaks out to pass the 1/2 in PVC male
    adapter thread. Top view from the deck side, sector S0 up, as on the deck."""
    bd = K.Board()
    bd.rules(CLEARANCE, TRACK, VIA_D, VIA_DRILL, edge=EDGE_CLEAR)
    Re = ENDPLATE_DIAMETER / 2
    C = (K.CX, K.CY)
    bd.circle(pcbnew.Edge_Cuts, C, Re, 0.1)
    rv = INRADIUS - FACE_THICK / 2
    for s in SECTORS:                         # face slots, as on the deck
        for t in FACE_TABS:
            bd.poly(pcbnew.Edge_Cuts, [loc(s, t + du, rv + dv) for du, dv in (
                (-SLOT_L / 2, -SLOT_W / 2), (SLOT_L / 2, -SLOT_W / 2), (SLOT_L / 2, SLOT_W / 2), (-SLOT_L / 2, SLOT_W / 2))], 0.1)
    ro, ri = knockout(bd, "H1")
    # copper: GND both sides round the knockout
    circ = lambda r, n=180: [pol(r, 360 * i / n) for i in range(n)]  # noqa: E731
    for lay in (F, B):
        bd.zone(lay, circ(Re + 1), "GND", 0, holes=[circ(ro + 0.3)], thermal=False)
    rs, ns = ENDPLATE_STITCH
    for k in range(ns):
        bd.via(pol(rs, k * 360 / ns), "GND", VIA_D, VIA_DRILL)
    for k in range(24):
        bd.via(pol(55.0, 7.5 + k * 15), "GND", VIA_D, VIA_DRILL)
    # mask: seam strips on the inside (top), where the faces solder on
    verts = [pol(2 * INRADIUS, v) for v in VERTICES]
    for i in range(3):
        bd.line(pcbnew.F_Mask, verts[i], verts[(i + 1) % 3], SEAM_STRIP)
    # silkscreen, inside (top)
    seam_guides(bd, FS, False, Re - 1.0)
    nk = (ENDPLATE_NUT_OD + 4) / 2
    for lay, mir, lab in ((FS, False, "ADAPTER SHOULDER - KEEP CLEAR"), (BS, True, "LOCK NUT - KEEP CLEAR")):
        bd.circle(lay, C, nk, 0.2)
        bd.text(lay, lab, pol(nk + 1.6, 180), 1.0, angle=-180, mirror=mir)
    bd.text(FS, "END PLATE - INSIDE", pol(45, 60), 1.5, angle=-60 + 90)
    bd.text(FS, "SOLDER FACES TO DECK AND END PLATE\nFIRST, ON THE BARE BOARDS", pol(45, 300), 0.9, angle=-300 + 90)
    bd.text(FS, "RP-SMA", pol(7.6, 0), 0.9)
    # silkscreen, outside (bottom), read from below
    bd.text(BS, POWER_WARNING, pol(50, 240), 1.1, angle=-240, mirror=True)
    warn_icon(bd, BS, POWER_WARNING, pol(50, 240), 1.1, -240, "above", 5.0)
    bd.text(BS, "END PLATE - OUTSIDE", pol(45, 60), 1.5, angle=-60 + 90, mirror=True)
    bd.text(BS, "KNOCKOUT: BREAK OUT FOR\n1/2 IN PVC ADAPTER", pol(16, 0), 1.0, mirror=True)
    for lay, mir in ((FS, False), (BS, True)):
        url_text(bd, lay, loc(120, 19.5, INRADIUS + 14.0), angle=-120, mirror=mir)
    scale_bars(bd, K.CX - 50, K.CY - 50, K.CX + Re + 8, K.CY + Re + 6)
    return bd


# --------------------------------------------------------------------------------------------- outputs
DRU = """(version 1)
(rule "+5V clearance"
  (constraint clearance (min {c}mm))
  (condition "A.NetName == '+5V' && B.NetName != '+5V'"))
"""


def finish(bd, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".kicad_pcb")
    bd.save(path)
    with open(path[:-len(".kicad_pcb")] + ".kicad_dru", "w") as f:   # custom rules, read by DRC next to the board
        f.write(DRU.format(c=CLEARANCE_5V))
    b = pcbnew.LoadBoard(path)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.Save(path)
    rpt = os.path.join(OUT, name + "_drc.rpt")
    pcbnew.WriteDRCReport(b, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    gdir = os.path.join(OUT, name + "_gerbers")
    os.makedirs(gdir, exist_ok=True)
    pc = pcbnew.PLOT_CONTROLLER(b)
    po = pc.GetPlotOptions()
    po.SetOutputDirectory(gdir)
    po.SetUseGerberProtelExtensions(True)
    po.SetUseAuxOrigin(False)
    po.SetSubtractMaskFromSilk(True)
    po.SetPlotFrameRef(False)
    for lay, suf in ((pcbnew.F_Cu, "F_Cu"), (pcbnew.B_Cu, "B_Cu"), (pcbnew.F_Mask, "F_Mask"),
                     (pcbnew.B_Mask, "B_Mask"), (pcbnew.F_SilkS, "F_Silkscreen"),
                     (pcbnew.B_SilkS, "B_Silkscreen"), (pcbnew.Edge_Cuts, "Edge_Cuts")):
        pc.SetLayer(lay)
        pc.OpenPlotfile(suf, pcbnew.PLOT_FORMAT_GERBER, suf)
        pc.PlotLayer()
    pc.ClosePlot()
    dw = pcbnew.EXCELLON_WRITER(b)
    dw.SetOptions(False, False, b.GetDesignSettings().GetAuxOrigin(), False)
    dw.SetFormat(True)
    dw.CreateDrillandMapFilesSet(gdir, True, False)
    zpath = os.path.join(OUT, name + "_gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(gdir)):
            z.write(os.path.join(gdir, f), f)
    for side, layers in (("top", "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts"), ("bottom", "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts")):
        cmd = ["kicad-cli", "pcb", "export", "svg", "--layers", layers, "--page-size-mode", "2",
               "--exclude-drawing-sheet", "-o", os.path.join(OUT, f"{name}_{side}.svg"), path]
        if side == "bottom":
            cmd.insert(4, "--mirror")
        subprocess.run(cmd, check=False, capture_output=True)
    pages = [("top", "F.Mask,F.Silkscreen,Edge.Cuts,Dwgs.User", False)]
    if name != "face_pcb":
        pages.append(("bottom", "B.Mask,B.Silkscreen,Edge.Cuts,Dwgs.User", True))
    for side, layers, mir in pages:
        cmd = ["kicad-cli", "pcb", "export", "pdf", "--layers", layers, "--black-and-white",
               "-o", os.path.join(OUT, f"{name}_print_{side}.pdf"), path]
        if mir:
            cmd.insert(4, "--mirror")
        subprocess.run(cmd, check=False, capture_output=True)
    with open(rpt) as f:
        txt = f.read()
    return txt


def export_copper(path, name):
    """<name>_copper.json for the RF model (rf_model/sector_model.py --copper): each copper layer as polygons with
    holes (filled zones, tracks, pads and vias merged, drill holes cut out), the plated barrels joining the layers,
    and the board outline. Model coordinates: mm, board centre at the origin, x = KiCad x - 100, y = 100 - KiCad y
    (deck and end plate: +y = S0's face normal, top view; face: x along the face, y = -60 at the deck edge and
    +60 at the end plate edge, tabs past both)."""
    import json
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    b = pcbnew.LoadBoard(path)
    to = lambda p: (round(pcbnew.ToMM(p.x) - K.CX, 4), round(K.CY - pcbnew.ToMM(p.y), 4))  # noqa: E731

    def polys(ps):
        out = []
        for i in range(ps.OutlineCount()):
            ol = ps.Outline(i)
            outer = [to(ol.CPoint(k)) for k in range(ol.PointCount())]
            holes = []
            for h in range(ps.HoleCount(i)):
                hl = ps.Hole(i, h)
                holes.append([to(hl.CPoint(k)) for k in range(hl.PointCount())])
            if len(outer) >= 3:
                out.append(Polygon(outer, [hh for hh in holes if len(hh) >= 3]).buffer(0))
        return out

    layers = {}
    drills = []
    barrels = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetDrillSize().x > 0:   # round drills only on these boards
                assert p.GetDrillSize().x == p.GetDrillSize().y, f"{fp.GetReference()} oval drill"
                drills.append(Point(to(p.GetPosition())).buffer(pcbnew.ToMM(p.GetDrillSize().x) / 2, 32))
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                    q = to(p.GetPosition())
                    barrels.append([q[0], q[1], round(pcbnew.ToMM(p.GetDrillSize().x), 3)])
    for t in b.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            q = to(t.GetPosition())
            barrels.append([q[0], q[1], round(pcbnew.ToMM(t.GetDrillValue()), 3)])
    for lay, lname in ((F, "F.Cu"), (B, "B.Cu")):
        geoms = []
        for z in b.Zones():
            if not z.GetIsRuleArea() and z.IsOnLayer(lay) and z.HasFilledPolysForLayer(lay):
                geoms += polys(z.GetFilledPolysList(lay))
        for t in b.GetTracks():
            if not t.IsOnLayer(lay):
                continue
            if isinstance(t, pcbnew.PCB_VIA):
                geoms.append(Point(to(t.GetPosition())).buffer(pcbnew.ToMM(t.GetWidth()) / 2, 16))
            else:   # straight tracks only on these boards; round ends, as KiCad draws them
                geoms.append(LineString([to(t.GetStart()), to(t.GetEnd())]).buffer(pcbnew.ToMM(t.GetWidth()) / 2, 8))
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.IsOnLayer(lay):
                    geoms += polys(p.GetEffectivePolygon())
            assert not any(g.GetLayer() in (F, B) for g in fp.GraphicalItems()), "footprint copper drawing"
        cu = unary_union(geoms).difference(unary_union(drills)).simplify(0.02)
        parts = [cu] if cu.geom_type == "Polygon" else list(cu.geoms)
        layers[lname] = [{"outer": [list(c) for c in g.exterior.coords[:-1]],
                          "holes": [[list(c) for c in r.coords[:-1]] for r in g.interiors]}
                         for g in parts if g.area > 0.01]
    bb = b.GetBoardEdgesBoundingBox()
    data = {"board": name, "units": "mm", "thickness": FACE_THICK, "layers": layers, "barrels": barrels,
            "bbox": [pcbnew.ToMM(bb.GetLeft()) - K.CX, K.CY - pcbnew.ToMM(bb.GetBottom()),
                     pcbnew.ToMM(bb.GetRight()) - K.CX, K.CY - pcbnew.ToMM(bb.GetTop())]}
    with open(os.path.join(OUT, name + "_copper.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    return {k: (len(v), sum(len(g["holes"]) for g in v)) for k, v in layers.items()}, len(barrels)


def seam_clearance(path, name):
    """Heat margin report (best effort, no hard rule): each deck part's nearest pad edge to the bottom seam strip
    (where the faces are soldered) and to the face slots. Written to out/<name>_part_clearance.csv."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    b = pcbnew.LoadBoard(path)
    verts = [pol(2 * INRADIUS, v) for v in VERTICES]
    seam = unary_union([LineString([verts[i], verts[(i + 1) % 3]]).buffer(SEAM_STRIP / 2, cap_style=2)
                        for i in range(3)])
    slots = unary_union(slot_polys())
    rows = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref[0] in "HMT" or not len(fp.Pads()):
            continue
        pads = unary_union([Polygon(pad_poly(p, 0.0)) for p in fp.Pads()])
        rows.append((ref, fp.GetValue(), pads.distance(seam), pads.distance(slots)))
    rows.sort(key=lambda r: (min(r[2], r[3]), r[0]))
    out = os.path.join(OUT, name + "_part_clearance.csv")
    with open(out, "w") as f:
        f.write("ref,value,pad_edge_to_seam_strip_mm,pad_edge_to_slot_mm\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]},{r[2]:.1f},{r[3]:.1f}\n")
    return rows


def summary(txt):
    import re
    out = [f"{txt.count('Severity: error')} errors"]
    for key in ("Found {} DRC violations", "Found {} unconnected pads", "Found {} Footprint errors"):
        m = re.search(key.replace("{}", r"(\d+)"), txt)
        out.append(key.format(m.group(1) if m else "?"))
    return "; ".join(out)


def make_preview(names, path):
    """pcb_preview.png: the kicad-cli SVG renders of each board side, tiled with captions (needs rsvg-convert)."""
    from PIL import Image, ImageDraw, ImageFont
    tiles = []
    for name, side, cap in names:
        svg = os.path.join(OUT, f"{name}_{side}.svg")
        png = svg[:-4] + ".png"
        subprocess.run(["rsvg-convert", "-w", "640", "-b", "white", "-o", png, svg], check=True)
        tiles.append((Image.open(png).convert("RGB"), cap))
    cols = 3
    w = max(im.width for im, _ in tiles)
    h = max(im.height for im, _ in tiles) + 40
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), "white")
    dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for k, (im, cap) in enumerate(tiles):
        x, y = (k % cols) * w, (k // cols) * h
        sheet.paste(im, (x + (w - im.width) // 2, y + 40))
        tw = dr.textlength(cap, font=font)
        dr.text((x + (w - tw) / 2, y + 8), cap, fill="black", font=font)
    sheet.save(path)


if __name__ == "__main__":
    decks = [(f"deck_d{s:g}", s) for s in DECK_VARIANTS]
    boards = [(n, (lambda s=s: build_deck(s))) for n, s in decks] + [("face_pcb", build_face),
                                                                    ("endplate_pcb", build_endplate)]
    for name, fn in boards:
        bd = fn()
        if name.startswith("deck"):
            for ref, d_pipe, d_slot, d_pad in tie_check(bd):
                print(f"  {ref} tie square: pipe {d_pipe:.1f} mm, slot {d_slot:.1f} mm, nearest pad / M3 keep-out "
                      f"{d_pad:.1f} mm")
        txt = finish(bd, name)
        print(name, summary(txt))
        cu, nb = export_copper(os.path.join(OUT, name + ".kicad_pcb"), name)
        print(f"  copper for the RF model: {cu} (polygons, holes) per layer, {nb} plated barrels")
        if name.startswith("deck"):
            print(f"  diameter {deck_diameter(dict(decks)[name]):.1f} mm")
            for ref, val, d_seam, d_slot in seam_clearance(os.path.join(OUT, name + ".kicad_pcb"), name):
                print(f"  {ref:4s} {val:22s} seam strip {d_seam:5.1f} mm  slot {d_slot:5.1f} mm")
    try:   # one PDF of the 1:1 print pages (each deck top + bottom, face, end plate top + bottom)
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter()
        pages = [f"{n}_print_{side}.pdf" for n, _ in decks for side in ("top", "bottom")]
        pages += ["face_pcb_print_top.pdf", "endplate_pcb_print_top.pdf", "endplate_pcb_print_bottom.pdf"]
        for f in pages:
            p = os.path.join(OUT, f)
            w.add_page(PdfReader(p).pages[0])
            os.remove(p)
        w.write(os.path.join(OUT, "pcb_print_1to1.pdf"))
    except ImportError:
        print("pypdf not installed: print pages left as separate PDFs")
    (d0, s0), (d1, s1) = decks[0], decks[-1]
    make_preview([(d0, "top", f"DECK, {s0:g} MM DUCKS, TOP (electronics side)"),
                  (d0, "bottom", f"DECK, {s0:g} MM DUCKS, BOTTOM (antenna side, mirrored)"),
                  (d1, "top", f"DECK, {s1:g} MM DUCKS, TOP"),
                  ("face_pcb", "top", "FACE x3 (outside)"),
                  ("endplate_pcb", "top", "END PLATE INSIDE (top)"),
                  ("endplate_pcb", "bottom", "END PLATE OUTSIDE (mirrored)")],
                 os.path.join(HERE, "pcb_preview.png"))
