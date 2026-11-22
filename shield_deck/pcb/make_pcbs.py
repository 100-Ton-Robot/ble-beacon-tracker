"""Generate the deck PCB (parts on the deck) and the face PCB with KiCad 7's pcbnew API.

    python3 make_pcbs.py            # writes deck_pcb.kicad_pcb, face_pcb.kicad_pcb, fills zones, runs DRC,
                                    # exports Gerber + drill zips and SVG previews into out/

Sizes and rules come from ../parameters.csv (groups deck, pcb, face). Part placement and track routes are the
LAYOUT tables below, in each core corner's local frame (u along the rim clockwise, v out from the centre; see
kicad_lib.py). Needs KiCad 7 or later (pcbnew Python module, kicad-cli).

Deck: top = electronics side (+5 V pour, all parts), bottom = antenna side (solid GND, the shield). Bottom
copper carries tracks / vias only inside the core (behind the reflectors), clear of the seam strip.
"""
import math
import os
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import params  # noqa: E402
import kicad_lib as K  # noqa: E402
from kicad_lib import loc, pol  # noqa: E402

P = params.load(["deck", "pcb", "face", "panel", "plate"])
globals().update(P)
OUT = os.path.join(HERE, "out")

R = PCB_DIAMETER / 2
INRADIUS = FACE_WIDTH / (2 * math.sqrt(3))
SECTORS = [0.0, 120.0, 240.0]
VERTICES = [60.0, 180.0, 300.0]       # core corners; XIAO S0 / S1 / S2 sit on these
VIA_D, VIA_DRILL = VIA
BAND_IN, BAND_MID, BAND_OUT = BAND_R
F, B = pcbnew.F_Cu, pcbnew.B_Cu
FS, BS = pcbnew.F_SilkS, pcbnew.B_SilkS


def core_ok(u, v, pad=0.0):
    """True if (u, v) in a corner frame is inside the core on the bottom, CORE_MARGIN clear of the seam strip."""
    lim = INRADIUS - SEAM_STRIP / 2 - CORE_MARGIN
    return 0.866025 * abs(u) + 0.5 * v + pad <= lim


def arc_pts(r, a0, a1, step=1.0):
    n = max(2, int(abs(a1 - a0) / step) + 1)
    return [pol(r, a0 + (a1 - a0) * i / (n - 1)) for i in range(n)]


def ang(theta, u, r):
    """World angle of the point on radius r whose u (in frame theta) is u."""
    return theta + math.degrees(math.asin(u / r))


def vr(u, r):
    return math.sqrt(r * r - u * u)


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
def xiao_fp(bd, ref, theta, sector):
    """Seeed XIAO (21 x 17.8 mm), castellated pads lengthened for hand soldering. USB-C end at local -y."""
    fp = K.custom_fp(bd, ref, "Seeed XIAO nRF54L15")
    pl, pw = XIAO_PAD
    edge = XIAO_W / 2
    right = ["5V", "GND", "3V3", "D10", "D9", "D8", "D7"]
    left = [f"D{i}" for i in range(7)]
    nets = {"5V": f"+5V_S{sector}", "GND": "GND", "D7": "CMD_TX_S1" if sector == 1 else "CMD_TX",
            "D8": f"S{sector}_TX"}
    for i in range(7):
        y = -3 * 2.54 + 2.54 * i
        K.smd_pad(fp, right[i], edge - pl / 2 + 1.7, y, pl, pw, nets.get(right[i]), bd)
        K.smd_pad(fp, left[i], -(edge - pl / 2 + 1.7), y, pl, pw, None, bd)
    hl, hw = XIAO_L / 2, edge
    K.fp_rect(fp, pcbnew.F_SilkS, (-hw - 0.1, -hl - 0.1), (hw + 0.1, hl + 0.1))
    K.fp_rect(fp, pcbnew.F_CrtYd, (-hw - 2.0, -hl - 1.6), (hw + 2.0, hl + 0.3), 0.05)
    K.fp_rect(fp, pcbnew.F_SilkS, (-4.5, -hl - 1.5), (4.5, -hl + 0.6))       # USB-C, overhangs the board
    ix, iy = XIAO_IPEX
    K.fp_circle(fp, pcbnew.F_SilkS, (-iy, ix), 1.3)                           # IPEX4, toward the inner end
    bd.add_fp(fp, ref, "XIAO", loc(theta, 0, XIAO_RADIUS), K.fp_orient(theta))
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
    bd.add_fp(fp, ref, "M3", pos, 0)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    return fp


def pads_fp(bd, ref, value, theta, u, v, pads, size, label=None):
    """Row of plain SMD solder pads (wire / pigtail pads). pads: [(name, du, net)]."""
    fp = K.custom_fp(bd, ref, value)
    for name, du, net in pads:
        K.smd_pad(fp, name, du, 0, size[0], size[1], net, bd)
    bd.add_fp(fp, ref, value, loc(theta, u, v), K.fp_orient(theta))
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    return fp


def mount_fp(bd, ref, theta, u, v, label):
    """Adhesive tie mount spot: silkscreen square + courtyard, no copper features under it."""
    fp = K.custom_fp(bd, ref, "HS-100 tie mount")
    h = MOUNT_SQ / 2
    K.fp_rect(fp, pcbnew.F_SilkS, (-h, -h), (h, h), 0.15)
    K.fp_rect(fp, pcbnew.F_CrtYd, (-h - 0.25, -h - 0.25), (h + 0.25, h + 0.25), 0.05)
    bd.add_fp(fp, ref, "tie mount", loc(theta, u, v), K.fp_orient(theta))
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    x, y = loc(theta, u, v)
    bd.text(FS, label, (x, y), 1.2, angle=-theta)
    return fp


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


def mount_obstacles(bd):
    """Everything a tie-mount square must stay clear of: slots, the opening, every footprint's courtyard
    (or pads when it has none), and the squares already placed."""
    from shapely.geometry import Point, Polygon, box
    from shapely.ops import unary_union
    geoms = slot_polys() + [Point(K.CX, K.CY).buffer(PCB_OPENING / 2, 64)]
    for fp in bd.b.GetFootprints():
        fp.BuildCourtyardCaches()
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount():
            for i in range(cy.OutlineCount()):
                ol = cy.Outline(i)
                pts = [(pcbnew.ToMM(ol.CPoint(k).x), pcbnew.ToMM(ol.CPoint(k).y)) for k in range(ol.PointCount())]
                if len(pts) >= 3:
                    geoms.append(Polygon(pts).buffer(0))
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            geoms.append(box(pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                             pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    for d in bd.b.GetDrawings():   # silkscreen text (legends, labels)
        if isinstance(d, pcbnew.PCB_TEXT) and d.GetLayer() == pcbnew.F_SilkS:
            bb = d.GetBoundingBox()
            geoms.append(box(pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                             pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    return unary_union(geoms)


def place_mount(bd, ref, theta, u0, v0, label):
    """Put a tie-mount square at the clear spot nearest (u0, v0) in frame theta: MOUNT_GAP clear of every
    obstacle, inside the rim ring. KiCad's DRC can't see silkscreen-only footprints, so this is the check."""
    from shapely.geometry import Point, Polygon
    obst = mount_obstacles(bd)
    rim = Point(K.CX, K.CY).buffer(R - RIM_MASK_WIDTH - MOUNT_GAP, 128)
    h = MOUNT_SQ / 2
    best = None
    for i in range(-70, 71):
        for j in range(-60, 61):
            u, v = u0 + i * 0.5, v0 + j * 0.5
            d = math.hypot(u - u0, v - v0)
            if best and d >= best[0]:
                continue
            sq = Polygon([loc(theta, u + du, v + dv) for du, dv in ((-h, -h), (h, -h), (h, h), (-h, h))])
            if rim.contains(sq) and not sq.buffer(MOUNT_GAP).intersects(obst):
                best = (d, u, v)
    if best is None:
        raise RuntimeError(f"{ref}: no clear spot for the tie mount")
    return mount_fp(bd, ref, theta, best[1], best[2], label)


def build_deck():
    bd = K.Board()
    bd.rules(CLEARANCE, TRACK, VIA_D, VIA_DRILL, edge=EDGE_CLEAR)
    C = (K.CX, K.CY)

    # outline and opening
    bd.circle(pcbnew.Edge_Cuts, C, R, 0.1)
    bd.circle(pcbnew.Edge_Cuts, C, PCB_OPENING / 2, 0.1)

    # antenna holes (D, P, P2), plated, 12 mm exposed GND pads both sides
    n = 0
    for i, s in enumerate(SECTORS):
        a = INRADIUS
        for pos in (pol(a + DUCK_SPACING, s), pol(a + PATCH_OFFSET, s),
                    pol(math.hypot(a + PATCH_OFFSET, FACE_WIDTH / 2 - PATCH_END_INSET),
                        s - math.degrees(math.atan2(FACE_WIDTH / 2 - PATCH_END_INSET, a + PATCH_OFFSET)))):
            n += 1
            rpsma_fp(bd, f"H{n}", pos)
    for k, v in enumerate(VERTICES):
        npth_fp(bd, f"M{k + 1}", pol(COLLAR_RADIUS, v), COLLAR_HOLE)
    for k in range(STITCH_COUNT):
        bd.via(pol(PCB_STITCH_RADIUS, k * 360 / STITCH_COUNT), "GND", VIA_D, VIA_DRILL)

    # face slots: each face's tabs drop into these; centred on the face board (its outer copper is the face line)
    for s in SECTORS:
        rv = INRADIUS - FACE_THICK / 2
        for t in FACE_TABS:
            c = [loc(s, t + du, rv + dv) for du, dv in ((-SLOT_L / 2, -SLOT_W / 2), (SLOT_L / 2, -SLOT_W / 2),
                                                        (SLOT_L / 2, SLOT_W / 2), (-SLOT_L / 2, SLOT_W / 2))]
            bd.poly(pcbnew.Edge_Cuts, c, 0.1)
            k = [loc(s, t + du, rv + dv) for du, dv in ((-SLOT_L / 2 - 1, -SLOT_W / 2 - 1), (SLOT_L / 2 + 1, -SLOT_W / 2 - 1),
                                                        (SLOT_L / 2 + 1, SLOT_W / 2 + 1), (-SLOT_L / 2 - 1, SLOT_W / 2 + 1))]
            ls = pcbnew.LSET()
            ls.AddLayer(F)
            bd.keepout(ls, k)

    # XIAOs, their 5 V links (solder jumper JPn, optional Schottky Dn) and GND via
    for k, th in enumerate(VERTICES):
        xiao_fp(bd, f"U{k + 2}", th, k)
        bd.lib_fp("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", f"JP{k + 1}", "bridge",
                  loc(th, 12.85, 77.62), K.fp_orient(th), {"1": f"+5V_S{k}", "2": "+5V"})
        bd.lib_fp("Diode_SMD", "D_SMA_Handsoldering", f"D{k + 1}", "SS34 (optional)",
                  loc(th, 16.5, 73.3), K.fp_orient(th), {"1": f"+5V_S{k}", "2": "+5V"})
        bd.track([loc(th, 10.0, 77.62), loc(th, 12.2, 77.62)], f"+5V_S{k}", 0.6)
        bd.track([loc(th, 12.2, 77.62), loc(th, 12.2, 75.9), loc(th, 14.0, 74.2)], f"+5V_S{k}", 0.6)
        bd.track([loc(th, 10.0, 75.08), loc(th, 11.35, 75.08)], "GND", 0.6)
        bd.via(loc(th, 11.35, 75.08), "GND", VIA_D, VIA_DRILL)

    t0, t1, t2 = VERTICES
    # ---- J1 (gateway harness) and ESP32 5 V link, in the 60 deg corner
    J1_PINS = {"1": "S2_TX", "2": "CMD_TX", "3": "GND", "4": "+5V_ESP", "5": "LED_IN", "6": "S0_TX", "7": "S1_TX"}
    bd.lib_fp("Connector_JST", "JST_PH_B7B-PH-K_1x07_P2.00mm_Vertical", "J1", "B7B-PH-K-S",
              loc(t0, -6, J1_V), K.fp_orient(t0), J1_PINS)
    bd.lib_fp("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", "JP4", "bridge",
              loc(t0, 0, 38.9), K.fp_orient(t0), {"1": "+5V_ESP", "2": "+5V"})
    bd.lib_fp("Diode_SMD", "D_SMA_Handsoldering", "D4", "SS34 (optional)",
              loc(t0, -1.0, 35.6), K.fp_orient(t0), {"1": "+5V_ESP", "2": "+5V"})
    L = lambda pts: [loc(t0, u, v) for u, v in pts]  # noqa: E731
    bd.track(L([(0, J1_V), (0, 41.0), (-0.65, 40.0), (-0.65, 38.9)]), "+5V_ESP", TRACK_5V)
    bd.track(L([(-0.65, 38.9), (-0.65, 38.0), (-2.7, 36.0)]), "+5V_ESP", TRACK_5V)

    # S0 to XIAO S0 (D8), CMD to XIAO S0 (D7) and on through the 0 ohm jumper R3 over S0 to the S1 arc
    bd.track(L([(4, J1_V), (4, 46.2), (11.6, 46.2), (11.6, 64.92), (10.0, 64.92)]), "S0_TX", TRACK)
    bd.track(L([(-4, J1_V), (-4, 50), (9, 55), (9, 61.6)]), "CMD_TX", TRACK)
    jv = vr(11.6, BAND_OUT)
    bd.lib_fp("Resistor_SMD", "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", "R3", "0R jumper",
              loc(t0, 11.6, jv), K.fp_orient(t0, -math.degrees(math.asin(11.6 / BAND_OUT))),
              {"1": "CMD_TX", "2": "CMD_TX_S1"})
    p1 = bd.pad_xy("R3", "1")
    p2 = bd.pad_xy("R3", "2")
    bd.track([loc(t0, 9, jv), p1], "CMD_TX", TRACK)
    a_r3 = math.degrees(math.atan2(p2[0] - K.CX, K.CY - p2[1]))
    # S1 and LED_IN head clockwise to the 180 deg corner
    bd.track(L([(6, J1_V), (14.8, J1_V), (14.8, vr(14.8, BAND_MID))]), "S1_TX", TRACK)
    bd.track(L([(2, J1_V), (2, 42.3), (16, 42.3), (16, vr(16, BAND_IN))]), "LED_IN", TRACK)
    # S2 and the CMD branch head counter-clockwise to the 300 deg corner; that CMD branch leaves J1 on the
    # bottom (inside the core) to a via, under S2
    bd.track(L([(-6, J1_V), (-6, vr(-6, BAND_OUT))]), "S2_TX", TRACK)
    cv = (-8.0, 46.5)
    assert core_ok(cv[0], cv[1], VIA_D / 2) and core_ok(-4, J1_V, 1.0)
    bd.track(L([(-4, J1_V), (-4, 46.5), cv]), "CMD_TX", TRACK, B)
    bd.via(loc(t0, *cv), "CMD_TX", VIA_D, VIA_DRILL)
    bd.track(L([cv, (-8.0, vr(-8.0, BAND_MID))]), "CMD_TX", TRACK)

    # arcs: 60 -> 180 (CMD outer, S1 middle, LED inner), 60 -> 300 (S2 outer, CMD middle)
    bd.track([p2] + arc_pts(BAND_OUT, a_r3 + 1.0, ang(t1, 9, BAND_OUT)), "CMD_TX_S1", TRACK)
    bd.track(arc_pts(BAND_MID, ang(t0, 14.8, BAND_MID), ang(t1, 11.6, BAND_MID)), "S1_TX", TRACK)
    bd.track(arc_pts(BAND_IN, ang(t0, 16, BAND_IN), ang(t1, 1.0, BAND_IN)), "LED_IN", TRACK)
    bd.track(arc_pts(BAND_OUT, ang(t0, -6, BAND_OUT), ang(t2, 11.6, BAND_OUT) - 360), "S2_TX", TRACK)
    bd.track(arc_pts(BAND_MID, ang(t0, -8, BAND_MID), ang(t2, 9, BAND_MID) - 360), "CMD_TX", TRACK)

    # taps at XIAO S1 (180) and S2 (300)
    for th, s in ((t1, "S1_TX"), (t2, "S2_TX")):
        L2 = lambda pts, th=th: [loc(th, u, v) for u, v in pts]  # noqa: E731
        bd.track(L2([(9, vr(9, BAND_OUT if th == t1 else BAND_MID)), (9, 61.6)]),
                 "CMD_TX_S1" if th == t1 else "CMD_TX", TRACK)
        bd.track(L2([(11.6, vr(11.6, BAND_MID if th == t1 else BAND_OUT)), (11.6, 64.92), (10.0, 64.92)]),
                 s, TRACK)

    # ---- power + LED block in the 180 deg corner
    Lb = lambda pts: [loc(t1, u, v) for u, v in pts]  # noqa: E731
    ori = K.fp_orient(t1)
    bd.lib_fp("Package_SO", "SOIC-14_3.9x8.7mm_P1.27mm", "U1", "74HCT125", loc(t1, -4, 43.0),
              K.fp_orient(t1, 180),
              {"1": "GND", "2": "LED_IN", "3": "BUF", "4": "+5V", "5": "GND", "7": "GND",
               "9": "GND", "10": "+5V", "12": "GND", "13": "+5V", "14": "+5V"})
    bd.lib_fp("Resistor_SMD", "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", "R1", "330R",
              loc(t1, 3, 35.5), ori, {"1": "BUF", "2": "DOUT"})
    bd.lib_fp("Resistor_SMD", "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", "R2", "10k",
              loc(t1, 3, 44.5), K.fp_orient(t1, 90), {"1": "GND", "2": "LED_IN"})
    bd.lib_fp("Capacitor_SMD", "C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", "C3", "100n",
              loc(t1, -8.0, 37.2), ori, {"1": "GND", "2": "+5V"})
    bd.lib_fp("Capacitor_Tantalum_SMD", "CP_EIA-7343-31_Kemet-D_Pad2.25x2.55mm_HandSolder", "C1",
              "330u 10V polymer", loc(t1, 11.5, 40.5), ori, {"1": "+5V", "2": "GND"})
    bd.lib_fp("Fuse", "Fuse_1206_3216Metric_Pad1.42x1.75mm_HandSolder", "F1", "2A one-time",
              loc(t1, 10.0, 44.6), ori, {"1": "+5V", "2": "+5V_LED"})
    bd.lib_fp("Capacitor_SMD", "C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", "C2", "100n",
              loc(t1, 13.0, 47.3), ori, {"1": "+5V_LED", "2": "GND"})
    pads_fp(bd, "J2", "5V IN", t1, 12.0, 35.5, [("1", -2.5, "+5V"), ("2", 2.5, "GND")], (3.0, 4.0))
    pads_fp(bd, "J3", "LED strip", t1, 10.0, 50.8, [("1", -4.0, "DOUT"), ("2", 1.5, "+5V_LED"),
                                                    ("3", 5.0, "GND")], (2.0, 3.0))
    # LED_IN down from its arc to U1 1A, with R2 pull-down
    bd.track(Lb([(1.0, vr(1.0, BAND_IN)), (1.0, 40.46), (-1.0, 40.46)]), "LED_IN", TRACK)
    bd.track(Lb([(1.0, 46.05), (2.4, 46.05)]), "LED_IN", TRACK)
    bd.track(Lb([(3.0, 42.95), (3.0, 41.6)]), "GND", 0.5)
    bd.via(loc(t1, 3.0, 41.3), "GND", VIA_D, VIA_DRILL)
    # 1Y -> R1 under the SOIC body, R1 -> strip DIN
    bd.track(Lb([(-1.2, 41.73), (-4.0, 41.73), (-4.0, 35.5), (1.45, 35.5)]), "BUF", TRACK)
    bd.track(Lb([(4.55, 35.5), (6.0, 37.0), (6.0, 49.3)]), "DOUT", TRACK)
    # U1 GND pins
    bd.track(Lb([(-1.2, 39.19), (1.0, 38.7)]), "GND", 0.4)
    bd.via(loc(t1, 1.0, 38.6), "GND", VIA_D, VIA_DRILL)
    for v in (44.27, 46.81):
        bd.track(Lb([(-2.0, v), (-4.0, v)]), "GND", 0.4)
        bd.via(loc(t1, -4.0, v), "GND", VIA_D, VIA_DRILL)
    for v in (41.73, 45.54):
        bd.track(Lb([(-6.9, v), (-8.6, v)]), "GND", 0.4)
        bd.via(loc(t1, -8.6, v), "GND", VIA_D, VIA_DRILL)
    bd.track(Lb([(-9.55, 37.2), (-9.55, 35.6)]), "GND", 0.5)
    bd.via(loc(t1, -9.55, 35.4), "GND", VIA_D, VIA_DRILL)
    # 5 V IN GND, C1-, F1 -> strip 5 V, C2, strip GND
    for v in (34.0, 37.0):
        bd.via(loc(t1, 16.6, v), "GND", VIA_D, VIA_DRILL)
        bd.track(Lb([(14.5, v), (16.6, v)]), "GND", 0.8)
    bd.track(Lb([(14.7, 39.4), (14.5, 37.4)]), "GND", 0.8)
    bd.track(Lb([(11.55, 44.6), (11.55, 49.3)]), "+5V_LED", TRACK_5V)
    bd.track(Lb([(14.6, 47.3), (14.6, 45.6)]), "GND", 0.5)
    bd.via(loc(t1, 14.6, 45.3), "GND", VIA_D, VIA_DRILL)
    bd.track(Lb([(15.0, 50.8), (17.0, 50.8)]), "GND", 0.8)
    bd.via(loc(t1, 17.0, 50.8), "GND", VIA_D, VIA_DRILL)

    # tie mounts

    # ---- zones: bottom GND (shield), top +5V pour, top GND rim ring
    circ = lambda r, n=180: [pol(r, 360 * i / n) for i in range(n)]  # noqa: E731
    bd.zone(B, circ(R + 1), "GND", 0, thermal=False, name="shield")
    bd.zone(F, circ(R + 1), "+5V", 0, name="5V")
    bd.zone(F, circ(R + 1), "GND", 2, holes=[circ(R - RIM_MASK_WIDTH)], thermal=False, name="rim")
    # mask: rim ring both sides, seam strip on the bottom
    for lay in (pcbnew.F_Mask, pcbnew.B_Mask):
        bd.circle(lay, C, R - RIM_MASK_WIDTH / 2, RIM_MASK_WIDTH)
    verts = [pol(2 * INRADIUS, v) for v in VERTICES]
    for i in range(3):
        bd.line(pcbnew.B_Mask, verts[i], verts[(i + 1) % 3], SEAM_STRIP)

    # ---- silkscreen
    for s in SECTORS:   # bottom: guide lines either side of the seam strip, a tick at each face centre
        for off in (-(SEAM_STRIP / 2 + 0.6), SEAM_STRIP / 2 + 0.6):
            r = INRADIUS + off
            half = (FACE_WIDTH / 2) * r / INRADIUS - 1.0
            p = loc(s, -half, r)
            q = loc(s, half, r)
            bd.line(BS, p, q, 0.2)
        bd.line(BS, loc(s, 0, INRADIUS + SEAM_STRIP / 2 + 0.6), loc(s, 0, INRADIUS + SEAM_STRIP / 2 + 6), 0.3)
        bd.text(BS, f"FACE S{SECTORS.index(s)} CENTRE", loc(s, 0, INRADIUS + 11), 1.5, angle=-s, mirror=True)
    bd.text(BS, "BOTTOM - ANTENNA SIDE", pol(46, 300), 2.0, angle=-300 + 90, mirror=True)

    bd.text(FS, "TOP - ELECTRONICS SIDE", pol(64, 211), 1.6, angle=-211 + 90)
    for i, s in enumerate(SECTORS):
        bd.text(FS, f"S{i}", loc(s, 0, 52), 2.0, angle=-s)
        a = INRADIUS
        bd.text(FS, "D", loc(s, -8.5, a + DUCK_SPACING), 1.5, angle=-s)
        bd.text(FS, "P", loc(s, -8.5, a + PATCH_OFFSET), 1.5, angle=-s)
    bd.line(FS, loc(0, 0, 47), loc(0, 0, 44), 0.3)
    bd.line(FS, loc(0, 0, 47), loc(0, -1.2, 45.5), 0.3)
    bd.line(FS, loc(0, 0, 47), loc(0, 1.2, 45.5), 0.3)
    bd.text(FS, "J1 (to ESP32)\n1 S2 TX\n2 CMD TX\n3 GND\n4 5V\n5 LED\n6 S0 TX\n7 S1 TX",
            loc(t2, -3.0, 45.0), 0.9, angle=-t2)
    bd.text(FS, "1", loc(t0, -6, J1_V + 2.2), 1.0, angle=-t0)
    bd.text(FS, "J1", loc(t0, 9.5, 40.0), 1.2, angle=-t0)
    bd.text(FS, "5V +   -", loc(t1, 12.0, 31.4), 1.1, angle=-t1)
    bd.text(FS, "DIN  5V  GND", loc(t1, 10.0, 53.4), 0.9, angle=-t1)
    scale_bars(bd, K.CX - 50, K.CY - 50, K.CX + R + 8, K.CY + R + 6)
    bd.text(FS, "POWER FROM PoE OR USB\nNEVER BOTH", loc(t2, 9.0, 52.0), 1.1, angle=-t2)
    bd.text(FS, "JP1-4 bridged = no diode\nJP open + D fitted = diode", loc(t2, 9.5, 36.5), 0.8, angle=-t2)
    # tie mounts last, so they clear the parts and the silkscreen text
    for k, th in enumerate(VERTICES):
        place_mount(bd, f"TM{4 + k}", th, -20.0, 47.5, f"TIE S{k} COAX")
    place_mount(bd, "TM1", t1, -17.0, 33.0, "TIE 5V IN")
    place_mount(bd, "TM2", t2, -15.0, 34.0, "TIE LED")
    place_mount(bd, "TM3", t0, -15.0, 34.0, "TIE J1")
    for fp in bd.b.GetFootprints():   # report where they went
        if fp.GetReference().startswith("TM"):
            q = fp.GetPosition()
            print(f"  {fp.GetReference()} at r {math.hypot(pcbnew.ToMM(q.x) - K.CX, pcbnew.ToMM(q.y) - K.CY):.1f}")
    return bd


# --------------------------------------------------------------------------------------------- face
def build_face():
    bd = K.Board()
    bd.rules(CLEARANCE, TRACK, VIA_D, VIA_DRILL, edge=0.3)
    w, h = FACE_W, FACE_H
    x0, y0 = K.CX - w / 2, K.CY - h / 2
    x1, y1 = x0 + w, y0 + h
    th = FACE_THICK
    outline = [(x0, y0), (x1, y0), (x1, y1)]
    rw, rd = TAB_RELIEF   # relief notch each side of a tab root, so the router's inside-corner radius lands
    for t in sorted(FACE_TABS, reverse=True):   # in the notch, not on the edge that seats on the deck
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
    rect = [(x0 - 1, y0 - 1), (x1 + 1, y0 - 1), (x1 + 1, y1 + th + 1), (x0 - 1, y1 + th + 1)]
    bd.zone(F, rect, "GND", 0, thermal=False)
    bd.zone(B, rect, "GND", 0, thermal=False)
    for k in range(4):   # stitching vias round the hole and along the edges
        bd.via((K.CX + 9 * math.cos(k * math.pi / 2 + math.pi / 4), K.CY + 9 * math.sin(k * math.pi / 2 + math.pi / 4)),
               "GND", VIA_D, VIA_DRILL)
    for t in range(1, 12):
        for x, y in ((x0 + 5, y0 + 10 * t), (x1 - 5, y0 + 10 * t), (x0 + 10 * t, y1 - 5)):
            bd.via((x, y), "GND", VIA_D, VIA_DRILL)
    e = FACE_EDGE_EXPOSE
    for lay in (pcbnew.F_Mask, pcbnew.B_Mask):   # exposed seam edges: left, right, bottom (deck side)
        bd.line(lay, (x0 + e / 2, y0), (x0 + e / 2, y1), e)
        bd.line(lay, (x1 - e / 2, y0), (x1 - e / 2, y1), e)
        bd.line(lay, (x0, y1 - e / 2), (x1, y1 - e / 2), e)
        for t in FACE_TABS:
            bd.line(lay, (K.CX + t, y1 - e), (K.CX + t, y1 + th), TAB_W)
    for lay, mir in ((FS, False), (BS, True)):
        bd.line(lay, (K.CX, y0 + 3), (K.CX, K.CY - PAD_EXPOSE / 2 - 1), 0.2)
        bd.line(lay, (K.CX, K.CY + PAD_EXPOSE / 2 + 1), (K.CX, y1 - e - 0.6), 0.2)
        bd.line(lay, (K.CX - 6, y1 - e - 0.6), (K.CX + 6, y1 - e - 0.6), 0.3)
        bd.text(lay, "DECK EDGE: TABS INTO THE DECK SLOTS", (K.CX + (-28 if mir else 28), y1 - 10), 1.3, mirror=mir)
    scale_bars(bd, K.CX - 50, K.CY - 50, x1 + 8, y1 + 6)
    bd.text(FS, "OUTSIDE - DIPOLE SIDE", (K.CX - 28, y0 + 12), 2.0)
    bd.text(BS, "INSIDE - CORE SIDE", (K.CX + 28, y0 + 12), 2.0, mirror=True)
    return bd


# --------------------------------------------------------------------------------------------- outputs
def finish(bd, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".kicad_pcb")
    bd.save(path)
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
    if name == "deck_pcb":
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


def summary(txt):
    import re
    out = []
    for key in ("Found {} DRC violations", "Found {} unconnected pads", "Found {} Footprint errors"):
        m = re.search(key.replace("{}", r"(\d+)"), txt)
        out.append(key.format(m.group(1) if m else "?"))
    return "; ".join(out)


if __name__ == "__main__":
    for name, fn in (("deck_pcb", build_deck), ("face_pcb", build_face)):
        bd = fn()
        txt = finish(bd, name)
        print(name, summary(txt))
    try:   # one PDF of the 1:1 print pages (deck top, deck bottom, face)
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter()
        for f in ("deck_pcb_print_top.pdf", "deck_pcb_print_bottom.pdf", "face_pcb_print_top.pdf"):
            p = os.path.join(OUT, f)
            w.add_page(PdfReader(p).pages[0])
            os.remove(p)
        w.write(os.path.join(OUT, "pcb_print_1to1.pdf"))
    except ImportError:
        print("pypdf not installed: print pages left as separate PDFs")
