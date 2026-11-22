"""Generate the deck PCB (parts on the deck), the face PCB and the end plate PCB with KiCad 7's pcbnew API.

    python3 make_pcbs.py            # writes deck_pcb, face_pcb and endplate_pcb .kicad_pcb, fills zones, runs DRC,
                                    # exports Gerber + drill zips, SVG previews and the 1:1 print PDF into out/

Sizes and rules come from ../parameters.csv (groups deck, pcb, face, endplate). Part placement and track routes are the
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

P = params.load(["deck", "pcb", "face", "panel", "plate", "endplate"])
globals().update(P)
ADAPTER_HOLE = params.load(["pipe"])["ADAPTER_HOLE"]
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
    nets = {"5V": "+5V", "GND": "GND", "D7": "CMD_TX_S1" if sector == 1 else "CMD_TX",
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
    geoms = slot_polys() + [Polygon(opening_pts())]
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


ASSEMBLY_STEPS = ("ASSEMBLY\n"
                  "1 FACES TO DECK + END PLATE FIRST (BARE BOARDS)\n"
                  "2 CLEAN (IPA)\n"
                  "3 SMD PARTS, THEN J1 + J4, THEN XIAOS\n"
                  "4 C1: SMD CAN OR RADIAL\n"
                  "5 RP-SMAS, COAX, TIE MOUNTS\n"
                  "6 POWER LEAD TO J2\n"
                  "7 SWITCH INSTALLED: CUT SW1,\n"
                  "   THEN CHECK SERVICE = NO POWER")
POWER_WARNING = "SET SERVICE BEFORE USB\nDamage from ignoring this is not covered.\nBuild at your own risk."


def opening_pts(step=1.0):
    """Centre opening (radius PCB_OPENING / 2) with a trapezoidal bayonet lug into it at each core corner."""
    r0 = PCB_OPENING / 2
    depth, wb, wt = COLLAR_LUG
    hb = math.degrees(math.asin(wb / 2 / r0))
    pts = []
    lugs = sorted(VERTICES)
    for i, th in enumerate(lugs):
        prev = lugs[i - 1] - (360 if i == 0 else 0)
        pts += arc_pts(r0, prev + hb, th - hb, step)[1:]
        pts += [loc(th, -wt / 2, r0 - depth), loc(th, wt / 2, r0 - depth)]
    return pts


def c1_fp(bd, ref, pos, orient):
    """C1: one 8 mm can footprint, SMD (CP_Elec_8x10 pads) or radial leads (CP_Radial_D8.0mm_P3.50mm), overlapping.
    Pad 1 (+) on the -x side for both; pads of the same number are the same net."""
    dia, pitch = C1_CAN
    fp = K.custom_fp(bd, ref, "330u can")
    for name, sx, tx in (("1", -3.25, -pitch / 2), ("2", 3.25, pitch / 2)):
        K.smd_pad(fp, name, sx, 0, 3.5, 2.5, "+5V" if name == "1" else "GND", bd)
        K.th_pad(fp, name, tx, 0, 1.6, 0.8, "+5V" if name == "1" else "GND", bd)
    K.fp_circle(fp, pcbnew.F_SilkS, (0, 0), dia / 2 + 0.3, 0.15)
    K.fp_line(fp, pcbnew.F_SilkS, (-5.6, -3.6), (-4.4, -3.6), 0.15)   # + mark
    K.fp_line(fp, pcbnew.F_SilkS, (-5.0, -4.2), (-5.0, -3.0), 0.15)
    K.fp_rect(fp, pcbnew.F_CrtYd, (-5.5, -4.6), (5.5, 4.6), 0.05)
    bd.add_fp(fp, ref, "330u", pos, orient)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    return fp


def sw1_fp(bd, ref, pos, orient, a_sign=1):
    """Service switch loop: pads 1 (A, 5V_IN) and 2 (B, +5V) at the tips of a copper U that ships bridged
    (a net tie). The U's bridge points along -y and has a narrow neck to cut when a switch is wired to the pads.
    a_sign puts pad A on the +x (1) or -x (-1) side."""
    pw, ph = SW1_PAD
    pitch, arm, cw = SW1_LOOP
    nw, nl = SW1_NECK
    fp = K.custom_fp(bd, ref, "service switch / bridge")
    K.smd_pad(fp, "1", a_sign * pitch / 2, 0, pw, ph, "5V_IN", bd)
    K.smd_pad(fp, "2", -a_sign * pitch / 2, 0, pw, ph, "+5V", bd)
    yb = -(ph / 2 + arm)               # inner edge of the bridge
    yo = yb - cw                       # outer edge
    ym = (yb + yo) / 2                 # bridge centre line
    # copper as round-ended segments (KiCad 7 footprint polygons don't follow the footprint when it is placed)
    for x in (-pitch / 2, pitch / 2):  # arms, from the pad centre to the bridge centre line
        K.fp_line(fp, pcbnew.F_Cu, (x, 0), (x, ym), cw)
    K.fp_line(fp, pcbnew.F_Cu, (-pitch / 2, ym), (-nl / 2 - cw / 2, ym), cw)
    K.fp_line(fp, pcbnew.F_Cu, (nl / 2 + cw / 2, ym), (pitch / 2, ym), cw)
    K.fp_line(fp, pcbnew.F_Cu, (-nl / 2 - 0.4, ym), (nl / 2 + 0.4, ym), nw)   # the neck to cut
    fp.AddNetTiePadGroup("1, 2")
    for x in (-nl / 2 - 0.5, nl / 2 + 0.5):   # cut brackets
        K.fp_line(fp, pcbnew.F_SilkS, (x, yb + 1.2), (x, yo - 1.2), 0.2)
    K.fp_rect(fp, pcbnew.F_CrtYd, (-pitch / 2 - pw / 2 - 0.3, ph / 2 + 0.3), (pitch / 2 + pw / 2 + 0.3, yo - 0.3), 0.05)
    bd.add_fp(fp, ref, "loop / switch", pos, orient)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    return fp


def seam_guides(bd, layer, mirror, rmax=None):
    """Guide lines either side of each face's seam strip and a tick + label at each face centre. rmax clips the
    lines to a board radius (the end plate)."""
    for s in SECTORS:
        for off in (-(SEAM_STRIP / 2 + 0.6), SEAM_STRIP / 2 + 0.6):
            r = INRADIUS + off
            half = (FACE_WIDTH / 2) * r / INRADIUS - 1.0
            if rmax:
                half = min(half, math.sqrt(rmax ** 2 - r ** 2))
            bd.line(layer, loc(s, -half, r), loc(s, half, r), 0.2)
        bd.line(layer, loc(s, 0, INRADIUS + SEAM_STRIP / 2 + 0.6), loc(s, 0, INRADIUS + SEAM_STRIP / 2 + 6), 0.3)
        bd.text(layer, f"FACE S{SECTORS.index(s)} CENTRE", loc(s, 0, INRADIUS + 11), 1.5, angle=-s, mirror=mirror)


def arrow_arc(bd, layer, r, a0, a1, width=0.25):
    pts = arc_pts(r, a0, a1, 1.0)
    for p, q in zip(pts, pts[1:]):
        bd.line(layer, p, q, width)
    d = 1 if a1 > a0 else -1          # head at a1, pointing along the arc
    tip = pol(r, a1)
    back = a1 - d * math.degrees(1.6 / r)
    for dr in (-0.9, 0.9):
        bd.line(layer, tip, pol(r + dr, back), width)


def collar_arrows(bd):
    """Bottom: the collar locks clockwise seen from the bottom, i.e. toward decreasing angle in the top view."""
    r = PCB_OPENING / 2 + 1.8
    for th in (VERTICES[0], VERTICES[2]):
        arrow_arc(bd, BS, r, th - 2, th - 16)
        arrow_arc(bd, BS, r, th + 2, th + 16)
        bd.text(BS, "LOCK", pol(r + 2.2, th - 9), 1.0, angle=-(th - 9), mirror=True)
        bd.text(BS, "OPEN", pol(r + 2.2, th + 9), 1.0, angle=-(th + 9), mirror=True)


def build_deck():
    bd = K.Board()
    bd.rules(CLEARANCE, TRACK, VIA_D, VIA_DRILL, edge=EDGE_CLEAR)
    C = (K.CX, K.CY)

    # outline and opening
    bd.circle(pcbnew.Edge_Cuts, C, R, 0.1)
    bd.poly(pcbnew.Edge_Cuts, opening_pts(), 0.1)

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

    # XIAOs: 5V pad straight onto the +5V pour (no jumper, no diode), GND by a via
    for k, th in enumerate(VERTICES):
        xiao_fp(bd, f"U{k + 2}", th, k)
        bd.track([loc(th, 10.0, 75.08), loc(th, 11.35, 75.08)], "GND", 0.6)
        bd.via(loc(th, 11.35, 75.08), "GND", VIA_D, VIA_DRILL)

    t0, t1, t2 = VERTICES
    # ---- J1 (gateway harness) in the 60 deg corner; pin 4 (ESP32 5 V) straight onto the +5V pour
    J1_PINS = {"1": "S2_TX", "2": "CMD_TX", "3": "GND", "4": "+5V", "5": "LED_IN", "6": "S0_TX", "7": "S1_TX"}
    bd.lib_fp("Connector_JST", "JST_PH_B7B-PH-K_1x07_P2.00mm_Vertical", "J1", "B7B-PH-K-S",
              loc(t0, -6, J1_V), K.fp_orient(t0), J1_PINS)
    assert all(core_ok(u, J1_V, 1.0) for u in (-6, 6)), "J1 pins must be inside the core"
    for p in bd.b.FindFootprintByReference("J1").Pads():   # pin 4 sits in a pocket between tracks: no spokes
        if p.GetNumber() == "4":
            p.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
    L = lambda pts: [loc(t0, u, v) for u, v in pts]  # noqa: E731
    jo = J1_V + 2.2   # S0 jogs out past the pin row so S1 and LED_IN can pass under it
    # S0 to XIAO S0 (D8), CMD to XIAO S0 (D7) and on through the 0 ohm jumper R3 over S0 to the S1 arc
    bd.track(L([(4, J1_V), (4, jo), (11.6, jo), (11.6, 64.92), (10.0, 64.92)]), "S0_TX", TRACK)
    bd.track(L([(-4, J1_V), (-4, jo + 0.3), (9, 55), (9, 61.6)]), "CMD_TX", TRACK)
    jv = vr(11.6, BAND_OUT)
    bd.lib_fp("Resistor_SMD", "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", "R3", "0R jumper",
              loc(t0, 11.6, jv), K.fp_orient(t0, -math.degrees(math.asin(11.6 / BAND_OUT))),
              {"1": "CMD_TX", "2": "CMD_TX_S1"})
    p1 = bd.pad_xy("R3", "1")
    p2 = bd.pad_xy("R3", "2")
    bd.track([loc(t0, 9, jv), p1], "CMD_TX", TRACK)
    a_r3 = math.degrees(math.atan2(p2[0] - K.CX, K.CY - p2[1]))
    # S1 and LED_IN head clockwise to the 180 deg corner, under the S0 jog; LED_IN passes outside the collar M3
    bd.track(L([(6, J1_V), (14.8, J1_V), (14.8, vr(14.8, BAND_MID))]), "S1_TX", TRACK)
    bd.track(L([(2, J1_V), (2, 44.6), (16, 44.6), (16, vr(16, BAND_IN))]), "LED_IN", TRACK)
    # S2 and the CMD branch head counter-clockwise to the 300 deg corner; that CMD branch leaves J1 on the
    # bottom (inside the core) to a via, under S2
    bd.track(L([(-6, J1_V), (-6, vr(-6, BAND_OUT))]), "S2_TX", TRACK)
    cv = (-8.0, J1_V - 1.5)
    assert core_ok(cv[0], cv[1], VIA_D / 2) and core_ok(-4, J1_V, 1.0)
    bd.track(L([(-4, J1_V), (-4, cv[1]), cv]), "CMD_TX", TRACK, B)
    bd.via(loc(t0, *cv), "CMD_TX", VIA_D, VIA_DRILL)
    bd.track(L([cv, (-8.0, vr(-8.0, BAND_MID))]), "CMD_TX", TRACK)

    # arcs: 60 -> 180 (CMD outer, S1 middle, LED inner), 60 -> 300 (S2 outer, CMD middle)
    LED_U = -4.0   # LED_IN leaves its arc here in the 180 deg corner and drops to U1
    bd.track([p2] + arc_pts(BAND_OUT, a_r3 + 1.0, ang(t1, 9, BAND_OUT)), "CMD_TX_S1", TRACK)
    bd.track(arc_pts(BAND_MID, ang(t0, 14.8, BAND_MID), ang(t1, 11.6, BAND_MID)), "S1_TX", TRACK)
    bd.track(arc_pts(BAND_IN, ang(t0, 16, BAND_IN), ang(t1, LED_U, BAND_IN)), "LED_IN", TRACK)
    bd.track(arc_pts(BAND_OUT, ang(t0, -6, BAND_OUT), ang(t2, 11.6, BAND_OUT) - 360), "S2_TX", TRACK)
    bd.track(arc_pts(BAND_MID, ang(t0, -8, BAND_MID), ang(t2, 9, BAND_MID) - 360), "CMD_TX", TRACK)

    # taps at XIAO S1 (180) and S2 (300)
    for th, s in ((t1, "S1_TX"), (t2, "S2_TX")):
        L2 = lambda pts, th=th: [loc(th, u, v) for u, v in pts]  # noqa: E731
        bd.track(L2([(9, vr(9, BAND_OUT if th == t1 else BAND_MID)), (9, 61.6)]),
                 "CMD_TX_S1" if th == t1 else "CMD_TX", TRACK)
        bd.track(L2([(11.6, vr(11.6, BAND_MID if th == t1 else BAND_OUT)), (11.6, 64.92), (10.0, 64.92)]),
                 s, TRACK)

    # ---- power + LED block in the 180 deg corner (u < 0: U1, C1, R2, C3; u > 0: R1, F1, C2, J3, J4)
    Lb = lambda pts: [loc(t1, u, v) for u, v in pts]  # noqa: E731
    ori = K.fp_orient(t1)
    lp = lambda ref, n: K.to_local(t1, *bd.pad_xy(ref, n))  # noqa: E731
    # U1: channel 3 drives the strip (3A pin 9 in, 3Y pin 8 out, 3OE pin 10 low); channels 1, 2, 4 tied off
    bd.lib_fp("Package_SO", "SOIC-14_3.9x8.7mm_P1.27mm", "U1", "74HCT125", loc(t1, -9.5, 46.0), ori,
              {"1": "+5V", "2": "GND", "4": "+5V", "5": "GND", "7": "GND", "8": "BUF", "9": "LED_IN",
               "10": "GND", "12": "GND", "13": "+5V", "14": "+5V"})
    u9, v9 = lp("U1", "9")
    u8, v8 = lp("U1", "8")
    bd.track(Lb([(LED_U, vr(LED_U, BAND_IN)), (LED_U, v9), (u9, v9)]), "LED_IN", TRACK)
    for n in ("10", "12"):                       # right-hand GND pins: via between the pads and LED_IN
        u, v = lp("U1", n)
        bd.track(Lb([(u, v), (-5.25, v)]), "GND", 0.4)
        bd.via(loc(t1, -5.25, v), "GND", VIA_D, VIA_DRILL)
    for n in ("2", "5", "7"):                    # left-hand GND pins
        u, v = lp("U1", n)
        bd.track(Lb([(u, v), (-14.2, v)]), "GND", 0.4)
        bd.via(loc(t1, -14.2, v), "GND", VIA_D, VIA_DRILL)
    # 3Y (BUF) -> under the collar M3 on the bottom, inside the core -> R1
    bv0, bv1, by = (-3.0, v8), (3.2, 44.0), 44.0
    assert core_ok(*bv0, VIA_D / 2) and core_ok(*bv1, VIA_D / 2)
    bd.track(Lb([(u8, v8), bv0]), "BUF", TRACK)
    bd.via(loc(t1, *bv0), "BUF", VIA_D, VIA_DRILL)
    bd.track(Lb([bv0, (bv0[0], by), bv1]), "BUF", TRACK, B)
    bd.via(loc(t1, *bv1), "BUF", VIA_D, VIA_DRILL)
    bd.lib_fp("Resistor_SMD", "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", "R1", "330R",
              loc(t1, 6.0, by), ori, {"1": "BUF", "2": "DOUT"})
    bd.track(Lb([bv1, lp("R1", "1")]), "BUF", TRACK)
    # R2 pull-down sits on LED_IN; C3 decouples U1
    bd.lib_fp("Resistor_SMD", "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder", "R2", "10k",
              loc(t1, LED_U - 1.55, 52.5), ori, {"1": "GND", "2": "LED_IN"})
    bd.track(Lb([lp("R2", "1"), (-8.9, 52.5)]), "GND", 0.5)
    bd.via(loc(t1, -8.9, 52.5), "GND", VIA_D, VIA_DRILL)
    bd.lib_fp("Capacitor_SMD", "C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", "C3", "100n",
              loc(t1, -12.5, 52.2), ori, {"1": "GND", "2": "+5V"})
    bd.track(Lb([lp("C3", "1"), (-15.9, 51.0)]), "GND", 0.5)
    bd.via(loc(t1, -15.9, 51.0), "GND", VIA_D, VIA_DRILL)
    # C1: 8 mm can, SMD (8 x 10) or radial; the radial leads are inside the core
    c1u, c1v = -8.0, 36.5
    c1_fp(bd, "C1", loc(t1, c1u, c1v), ori)
    assert all(core_ok(c1u + du, c1v, 0.9) for du in (-C1_CAN[1] / 2, C1_CAN[1] / 2)), "C1 leads outside the core"
    # LED output: F1 -> +5V_LED; J3 pads (JST-SM pigtail) and J4 header, both 5V / DIN / GND
    bd.lib_fp("Fuse", "Fuse_1206_3216Metric_Pad1.42x1.75mm_HandSolder", "F1", "2A one-time",
              loc(t1, -0.5, 52.5), ori, {"1": "+5V", "2": "+5V_LED"})
    j4 = (1.0, 48.5)
    bd.lib_fp("Connector_PinHeader_2.54mm", "PinHeader_1x03_P2.54mm_Vertical", "J4", "1x3 2.54 mm",
              loc(t1, *j4), K.fp_orient(t1, 90), {"1": "+5V_LED", "2": "DOUT", "3": "GND"})
    bd.b.FindFootprintByReference("J4").Reference().SetVisible(False)
    for n in "123":
        u, v = lp("J4", n)
        assert abs(v - j4[1]) < 0.01 and core_ok(u, v, 0.85), f"J4 pin {n} at {u:.2f} {v:.2f}"
    assert lp("J4", "3")[0] > lp("J4", "1")[0]
    pads_fp(bd, "J3", "LED strip", t1, 6.5, 52.5, [("1", -3.5, "+5V_LED"), ("2", 0.0, "DOUT"), ("3", 3.5, "GND")],
            (2.0, 3.0))
    bd.lib_fp("Capacitor_SMD", "C_1206_3216Metric_Pad1.33x1.80mm_HandSolder", "C2", "100n",
              loc(t1, -2.1, 48.5), K.fp_orient(t1, 90), {"1": "GND", "2": "+5V_LED"})
    if lp("C2", "1")[1] > lp("C2", "2")[1]:      # GND pad inward
        raise RuntimeError("C2 orientation")
    u4_1, v4_1 = lp("J4", "1")
    u4_2, v4_2 = lp("J4", "2")
    uf2, vf2 = lp("F1", "2")
    bd.track(Lb([lp("R1", "2"), (7.55, 46.6), (u4_2, 46.6), (u4_2, v4_2)]), "DOUT", TRACK)
    bd.track(Lb([(u4_2, v4_2), (u4_2, 50.0), (6.5, 50.0), (6.5, 51.0)]), "DOUT", TRACK)
    bd.track(Lb([(uf2, vf2), (3.0, 52.5)]), "+5V_LED", TRACK_5V)
    bd.track(Lb([(uf2, vf2), (u4_1, 51.0), (u4_1, v4_1)]), "+5V_LED", TRACK_5V)
    bd.track(Lb([lp("C2", "2"), (u4_1, 51.0)]), "+5V_LED", TRACK_5V)
    bd.track(Lb([lp("C2", "1"), (-2.1, 45.4)]), "GND", 0.5)
    bd.via(loc(t1, -2.1, 45.4), "GND", VIA_D, VIA_DRILL)
    bd.track(Lb([(10.0, 52.5), (10.0, 50.0)]), "GND", 0.8)
    bd.via(loc(t1, 10.0, 50.0), "GND", VIA_D, VIA_DRILL)

    # ---- 5V IN (J2) and the service switch loop SW1, outside the band left of XIAO S1. SW1 is a U: pads in a
    # row with J2, the bridge (cut here when a switch is installed) hangs inward, clear of the rim
    j2u, j2v = -18.0, 69.5
    pads_fp(bd, "J2", "5V IN", t1, j2u, j2v, [("1", -2.5, "5V_IN"), ("2", 2.5, "GND")], (3.0, 4.0))
    bd.track(Lb([(j2u + 2.5, j2v), (-12.9, j2v)]), "GND", 1.0)
    bd.via(loc(t1, -12.9, j2v), "GND", VIA_D, VIA_DRILL)
    sw_pitch = SW1_LOOP[0]
    swu = j2u - 2.5 - SW1_PAD[0] / 2 - 2.0 - SW1_PAD[0] / 2 - sw_pitch / 2
    sw1_fp(bd, "SW1", loc(t1, swu, j2v), K.fp_orient(t1, 180), a_sign=-1)
    assert lp("SW1", "1")[0] > lp("SW1", "2")[0], "SW1 pad A must face J2"
    bd.track(Lb([(j2u - 2.5, j2v), lp("SW1", "1")]), "5V_IN", 1.5)
    sw_in = j2v - SW1_PAD[1] / 2 - SW1_LOOP[1] - SW1_LOOP[2]     # inner edge of the bridge
    ku = sw_pitch / 2 + SW1_LOOP[2] / 2 + 0.6                     # the +5V pour would fill over the netless
    ls = pcbnew.LSET()                                            # loop copper: keep pour out of the U
    ls.AddLayer(F)
    bd.keepout(ls, Lb([(swu - ku, sw_in - 0.6), (swu + ku, sw_in - 0.6),
                       (swu + ku, j2v - SW1_PAD[1] / 2), (swu - ku, j2v - SW1_PAD[1] / 2)]), tracks=False, vias=False)
    ub, vb = lp("SW1", "2")   # pad B joins the pour through a track: spokes would cross the loop copper
    for p in bd.b.FindFootprintByReference("SW1").Pads():
        if p.GetNumber() == "2":
            p.SetZoneConnection(pcbnew.ZONE_CONNECTION_NONE)
    bd.track(Lb([(ub, vb), (ub - 3.0, vb + 1.0)]), "+5V", 1.5)
    bd.text(FS, "+", loc(t1, j2u - 2.5, j2v - 3.2), 1.2, angle=-t1)
    bd.text(FS, "-", loc(t1, j2u + 2.5, j2v - 3.2), 1.2, angle=-t1)
    bd.text(FS, "5V IN (J2)", loc(t1, j2u, j2v + 3.4), 1.0, angle=-t1)
    bd.text(FS, "A", loc(t1, swu + sw_pitch / 2, j2v + 3.0), 1.0, angle=-t1)
    bd.text(FS, "B", loc(t1, swu - sw_pitch / 2, j2v + 3.0), 1.0, angle=-t1)
    bd.text(FS, "CUT IF SWITCH INSTALLED", loc(t1, swu, sw_in - 2.3), 0.9, angle=-t1)
    bd.text(FS, "SW1 SERVICE: SWITCH TO A + B", loc(t1, swu, sw_in - 3.9), 0.9, angle=-t1)

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

    # ---- silkscreen, bottom
    seam_guides(bd, BS, True)
    bd.text(BS, "BOTTOM - ANTENNA SIDE", pol(76, 330), 2.0, angle=-330, mirror=True)
    bd.text(BS, "SOLDER FACES BEFORE ANY PARTS", loc(240, 28.0, INRADIUS + 8.5), 1.2, angle=-240, mirror=True)
    collar_arrows(bd)

    # ---- silkscreen, top
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
            loc(t2, -13.0, 47.0), 0.9, angle=-t2)
    bd.text(FS, "COLLAR LOCKS FROM BOTTOM", loc(t2, 0, 34.6), 1.0, angle=-t2)
    bd.text(FS, "J4: 5V DIN GND", loc(t1, 12.8, 48.5), 0.8, angle=-t1)
    bd.text(FS, "J3 5V  DIN  GND", loc(t1, 6.5, 55.0), 0.9, angle=-t1)
    bd.text(FS, "C1", loc(t1, -14.8, c1v + 1.2), 1.0, angle=-t1)
    scale_bars(bd, K.CX - 50, K.CY - 50, K.CX + R + 8, K.CY + R + 6)
    bd.text(FS, POWER_WARNING, pol(66, 270), 1.1, angle=-270)
    bd.text(FS, ASSEMBLY_STEPS, pol(70, 90), 0.9, angle=-90)
    # tie mounts last, so they clear the parts and the silkscreen text
    for k, th in enumerate(VERTICES):
        place_mount(bd, f"TM{4 + k}", th, -20.0, 47.5, f"TIE S{k} COAX")
    place_mount(bd, "TM1", t1, -24.0, 48.0, "TIE 5V IN")
    place_mount(bd, "TM2", t1, 18.0, 46.0, "TIE LED")
    place_mount(bd, "TM3", t0, -15.0, 36.0, "TIE J1")
    for fp in bd.b.GetFootprints():   # report where they went
        if fp.GetReference().startswith("TM"):
            q = fp.GetPosition()
            print(f"  {fp.GetReference()} at r {math.hypot(pcbnew.ToMM(q.x) - K.CX, pcbnew.ToMM(q.y) - K.CY):.1f}")
    return bd


# --------------------------------------------------------------------------------------------- face
def build_face():
    """One face design for both ends: tabs, relief notches and exposed seam copper on the deck edge and on the
    end plate edge."""
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
    return bd


# --------------------------------------------------------------------------------------------- end plate
def build_endplate():
    """End plate across the far end of the triangle: bare GND copper both sides, slots for the face tabs, seam
    copper on the inside (top), the service switch hole, and a centre RP-SMA hole in a knockout that breaks out
    to pass the 1/2 in PVC male adapter thread. Top view from the deck side, sector S0 up, as on the deck."""
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
    # knockout: a routed ring (outer edge = ADAPTER_HOLE) broken by KO_BRIDGE bridges with mouse bites
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
    fp = K.custom_fp(bd, "H1", "RP-SMA")   # downward antenna; the disc is its own copper once the ring is routed
    K.th_pad(fp, "1", 0, 0, PAD_EXPOSE, HOLE_RPSMA, "GND_KO", bd)
    bd.add_fp(fp, "H1", "RP-SMA", C, 0)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    sw = loc(VERTICES[1], 0, SWITCH_R)
    assert core_ok(0, SWITCH_R, SWITCH_HOLE / 2 + 1), "switch hole outside the triangle"
    npth_fp(bd, "SW", sw, SWITCH_HOLE)
    # copper: GND both sides round the knockout, the disc on its own net
    circ = lambda r, n=180: [pol(r, 360 * i / n) for i in range(n)]  # noqa: E731
    for lay in (F, B):
        bd.zone(lay, circ(Re + 1), "GND", 0, holes=[circ(ro + 0.3)], thermal=False)
        bd.zone(lay, circ(ri), "GND_KO", 1, thermal=False)
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
    bd.text(FS, "SERVICE SWITCH\nWIRES TO DECK SW1", loc(VERTICES[1], 0, SWITCH_R - 8.5), 1.0, angle=-VERTICES[1])
    bd.text(FS, "RP-SMA", pol(7.6, 0), 0.9)
    # silkscreen, outside (bottom), read from below
    bd.text(BS, "RUN", loc(VERTICES[1], 0, SWITCH_R + 5.5), 1.5, angle=-VERTICES[1], mirror=True)
    bd.text(BS, "SERVICE", loc(VERTICES[1], 0, SWITCH_R - 5.5), 1.5, angle=-VERTICES[1], mirror=True)
    bd.text(BS, POWER_WARNING, pol(50, 240), 1.1, angle=-240, mirror=True)
    bd.text(BS, "END PLATE - OUTSIDE", pol(45, 60), 1.5, angle=-60 + 90, mirror=True)
    bd.text(BS, "KNOCKOUT: BREAK OUT FOR\n1/2 IN PVC ADAPTER", pol(16, 0), 1.0, mirror=True)
    scale_bars(bd, K.CX - 50, K.CY - 50, K.CX + Re + 8, K.CY + Re + 6)
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
    if name in ("deck_pcb", "endplate_pcb"):
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


def seam_clearance(path):
    """Heat margin report (best effort, no hard rule): each deck part's nearest pad edge to the bottom seam strip
    (where the faces are soldered) and to the face slots. Written to out/deck_part_clearance.csv."""
    from shapely.geometry import LineString, box
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
        pads = unary_union([box(pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetRight()),
                                pcbnew.ToMM(bb.GetBottom())) for bb in (p.GetBoundingBox() for p in fp.Pads())])
        rows.append((ref, fp.GetValue(), pads.distance(seam), pads.distance(slots)))
    rows.sort(key=lambda r: min(r[2], r[3]))
    out = os.path.join(OUT, "deck_part_clearance.csv")
    with open(out, "w") as f:
        f.write("ref,value,pad_edge_to_seam_strip_mm,pad_edge_to_slot_mm\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]},{r[2]:.1f},{r[3]:.1f}\n")
    return rows


def summary(txt):
    import re
    out = []
    for key in ("Found {} DRC violations", "Found {} unconnected pads", "Found {} Footprint errors"):
        m = re.search(key.replace("{}", r"(\d+)"), txt)
        out.append(key.format(m.group(1) if m else "?"))
    return "; ".join(out)


if __name__ == "__main__":
    for name, fn in (("deck_pcb", build_deck), ("face_pcb", build_face), ("endplate_pcb", build_endplate)):
        bd = fn()
        txt = finish(bd, name)
        print(name, summary(txt))
        if name == "deck_pcb":
            for ref, val, d_seam, d_slot in seam_clearance(os.path.join(OUT, name + ".kicad_pcb")):
                print(f"  {ref:4s} {val:22s} seam strip {d_seam:5.1f} mm  slot {d_slot:5.1f} mm")
    try:   # one PDF of the 1:1 print pages (deck top, deck bottom, face, end plate top, end plate bottom)
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter()
        for f in ("deck_pcb_print_top.pdf", "deck_pcb_print_bottom.pdf", "face_pcb_print_top.pdf",
                  "endplate_pcb_print_top.pdf", "endplate_pcb_print_bottom.pdf"):
            p = os.path.join(OUT, f)
            w.add_page(PdfReader(p).pages[0])
            os.remove(p)
        w.write(os.path.join(OUT, "pcb_print_1to1.pdf"))
    except ImportError:
        print("pypdf not installed: print pages left as separate PDFs")
