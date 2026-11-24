"""The mast's physical layout, shared by every build: the PCB generator (builds/pcb/make_pcbs.py), the
scratch-build templates (builds/hand/make_templates.py) and the RF model (rf_model/sector_model.py). One number, one
place: each derived value is computed here once, next to the formula that the templates' formulas page prints for it,
so the page can't drift from what the boards and templates actually use.

    import layout
    L = layout.Layout(15)            # one duck spacing (a DECK_VARIANTS value)
    L.deck_r, L.hole("D", 0), L.tie(60), L.rows   # rows: (section, symbol, formula, value, unit, note)

Frames: top view, mm, centre at the origin, x right, y up (S0's face normal). Angles clockwise from +y. A corner
or sector frame at angle t has v along t (out from the centre) and u at t + 90 (clockwise); xy(t, u, v) turns it
into x, y. Every value comes from common/parameters.csv: layout.py reads no build's own file, so both builds get the
same numbers.
"""
import math

import params

P = params.load(["deck", "pcb", "plate", "pipe", "endplate", "face", "panel"])
SECTORS = (0.0, 120.0, 240.0)        # face normals (antenna sectors S0, S1, S2)
VERTICES = (60.0, 180.0, 300.0)      # core corners: XIAOs U2 (head, 2 o'clock), U3 (6 o'clock), U4 (10 o'clock)
VARIANTS = tuple(P["DECK_VARIANTS"]) if isinstance(P["DECK_VARIANTS"], tuple) else (P["DECK_VARIANTS"],)


def xy(t, u, v):
    """Frame (u, v) at angle t -> top-view x, y."""
    a = math.radians(t)
    return u * math.cos(a) + v * math.sin(a), -u * math.sin(a) + v * math.cos(a)


def pol(r, t):
    return xy(t, 0.0, r)


def frame(t, x, y):
    """Top-view x, y -> (u, v) in the frame at angle t."""
    a = math.radians(t)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


class Layout:
    """Every derived dimension for one duck spacing (mm). Each is computed by _f, which also records the row the
    formulas page prints."""

    def __init__(self, spacing):
        p = P
        self.spacing = spacing
        self.rows = []
        f = self._f
        a = p["FACE_WIDTH"]
        # ---- triangle core
        f("TRIANGLE CORE", "a", "FACE_WIDTH (side of the triangle)", a, "mm")
        self.r_in = f("TRIANGLE CORE", "r_in", "a / (2 x sqrt 3)", a / (2 * math.sqrt(3)), "mm", "centre -> face")
        self.r_c = f("TRIANGLE CORE", "R_c", "2 x r_in = a / sqrt 3", 2 * self.r_in, "mm",
                     "centre -> corner (circumradius)")
        f("TRIANGLE CORE", "h", "FACE_H (face height, below the deck)", p["FACE_H"], "mm", "make 3 faces a x h")
        self.core_lim = f("TRIANGLE CORE", "r_core", "r_in - SEAM_STRIP / 2 - CORE_MARGIN", self.r_in -
                          p["SEAM_STRIP"] / 2 - p["CORE_MARGIN"], "mm",
                          "parts and wiring inside the core stay inside this distance from the centre,\n"
                          "measured across each face (1 mm clear of the seam)")
        self.m4_r = f("TRIANGLE CORE", "r_M4", "2 x (r_in - FACE_THICK - NUT_AF / 2 - NUT_GAP)",
                      2 * (self.r_in - p["FACE_THICK"] - p["NUT_AF"] / 2 - p["NUT_GAP"]), "mm",
                      "core-corner M4 nut / bolt centre: nut flats against both faces' inner sides")
        # ---- antenna holes
        self.r_D = f("ANTENNA HOLES", "r_D", "r_in + d  (d = duck spacing)", self.r_in + spacing, "mm",
                     "D hole: duck / monopole, on each face normal (0 / 120 / 240 deg)")
        self.r_P = f("ANTENNA HOLES", "r_P", "r_in + PATCH_OFFSET", self.r_in + p["PATCH_OFFSET"], "mm",
                     "P hole: patch, on each face normal")
        self.s_P2 = f("ANTENNA HOLES", "s", "a / 2 - PATCH_END_INSET  (along the face)", a / 2 - p["PATCH_END_INSET"],
                      "mm")
        self.r_P2 = f("ANTENNA HOLES", "r_P2", "sqrt(r_P^2 + s^2)", math.hypot(self.r_P, self.s_P2), "mm")
        self.a_P2 = f("ANTENNA HOLES", "t_P2", "atan(s / r_P), counter-clockwise of the face normal",
                      math.degrees(math.atan2(self.s_P2, self.r_P)), "deg")
        # ---- deck
        d_min = p["DECK_MIN_DIAMETER"]
        need = 2 * (self.r_D + p["PAD_EXPOSE"] / 2 + p["DECK_EDGE_MARGIN"])
        f("DECK", "D_need", "2 x (r_D + PAD_EXPOSE / 2 + DECK_EDGE_MARGIN)", need, "mm",
          "the D hole's exposed pad plus an edge margin")
        self.deck_d = f("DECK", "D_deck", "max(DECK_MIN_DIAMETER, D_need), up to 0.1 mm",
                        max(d_min, math.ceil(need * 10 - 1e-9) / 10), "mm",
                        f"DECK_MIN_DIAMETER = {d_min:g} = face corners (2 x R_c) + 2.7 mm, as the end plate")
        self.deck_r = self.deck_d / 2
        f("DECK", "R - R_c", "corner clearance (deck rim past the face corners)", self.deck_r - self.r_c, "mm")
        self.pipe_d = f("DECK", "pipe hole", "ADAPTER_HOLE (7/8 in, 1/2 in PVC adapter, 21.3 mm OD)",
                        p["ADAPTER_HOLE"], "mm", "the knockout's outer edge on the PCBs")
        self.m3_r, m3_a = p["M3_POS"]
        self.m3_angles = tuple((m3_a + 120 * k) % 360 for k in range(3))
        f("DECK", "r_M3", f"M3_POS, at {self.m3_angles[0]:g} / {self.m3_angles[1]:g} / {self.m3_angles[2]:g} deg",
          self.m3_r, "mm", f"{p['COLLAR_HOLE']:g} mm holes, {p['M3_KEEPOUT']:g} mm washer keep-out, between the radios")
        self.end_d = f("DECK", "D_end", "ENDPLATE_DIAMETER", p["ENDPLATE_DIAMETER"], "mm")
        # ---- radios (XIAO nRF54L15 on each core corner axis, USB-C out, antenna end in)
        hl = p["XIAO_L"] / 2
        self.xiao_v = f("RADIOS", "v_X", "XIAO_CENTRE_V (along the corner axis)", p["XIAO_CENTRE_V"], "mm")
        f("RADIOS", "v_ant", "v_X - XIAO_L / 2  (antenna end)", self.xiao_v - hl, "mm")
        f("RADIOS", "v_USB", "v_X + XIAO_L / 2  (USB-C end)", self.xiao_v + hl, "mm")
        pad_u = p["XIAO_W"] / 2 + p["XIAO_PAD"][0] / 2
        pad_v = self.xiao_v + 3 * 2.54 + p["XIAO_PAD"][1] / 2
        f("RADIOS", "pad corner", "0.866 x (XIAO_W / 2 + pad) + 0.5 x (v_X + 3 x 2.54 + pad / 2)",
          0.866025 * pad_u + 0.5 * pad_v, "mm", f"outer pad corner across the face: must be <= r_core "
                                                f"({self.core_lim:.2f})")
        ix, iy = p["XIAO_IPEX"]
        self.ipex = (-iy, self.xiao_v - ix)
        f("RADIOS", "IPEX4", "(u, v) = (-XIAO_IPEX y, v_X - XIAO_IPEX x)", self.ipex[1], "mm", f"u = {self.ipex[0]:g}")
        phi = math.radians(p["PIGTAIL_ANGLE"])
        self.pig_dir = (math.sin(phi), math.cos(phi))
        tl = p["TIE_FROM_IPEX"]
        self.tie_uv = (self.ipex[0] + tl * self.pig_dir[0], self.ipex[1] + tl * self.pig_dir[1])
        self.tie_r = f("RADIOS", "r_tie", "|IPEX4 + TIE_FROM_IPEX x (sin PIGTAIL_ANGLE, cos PIGTAIL_ANGLE)|",
                       math.hypot(*self.tie_uv), "mm",
                       f"tie square centre (u, v) = ({self.tie_uv[0]:.2f}, {self.tie_uv[1]:.2f}) in the corner frame,\n"
                       f"{p['MOUNT_SQ']:g} mm square turned square to the pigtail")
        self.j1 = tuple(p["J1_POS"])
        self.j2 = tuple(p["J2_POS"])
        f("RADIOS", "J1", "J1_POS (r, angle): to the ESP32, 5V / GND / DATA / CMD", self.j1[0], "mm",
          f"at {self.j1[1]:g} deg")
        f("RADIOS", "J2", "J2_POS (r, angle): 5V in from the splitter", self.j2[0], "mm", f"at {self.j2[1]:g} deg")

    def _f(self, section, sym, formula, value, unit, note=""):
        self.rows.append((section, sym, formula, value, unit, note))
        return value

    # ---- positions, top view
    def hole(self, kind, s):
        """Antenna hole kind ("D", "P", "P2") of sector angle s -> x, y."""
        if kind == "D":
            return xy(s, 0.0, self.r_D)
        if kind == "P":
            return xy(s, 0.0, self.r_P)
        return xy(s, -self.s_P2, self.r_P)

    def holes(self):
        """[(kind, sector index, x, y)] for all nine antenna holes."""
        return [(k, i, *self.hole(k, s)) for i, s in enumerate(SECTORS) for k in ("D", "P", "P2")]

    def m3(self):
        return [pol(self.m3_r, a) for a in self.m3_angles]

    def tie(self, t):
        """Tie square of the XIAO on corner t: centre, cable direction and corners, all in the corner frame."""
        c, d = self.tie_uv, self.pig_dir
        n = (d[1], -d[0])
        h = P["MOUNT_SQ"] / 2
        sq = [(c[0] + h * (sd * d[0] + sn * n[0]), c[1] + h * (sd * d[1] + sn * n[1]))
              for sd, sn in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
        return self.ipex, c, d, sq

    def gusset(self, r0, r1, proud):
        """Corner gusset in the corner frame (u across, v along the corner axis, out): the trapezoid between the two
        faces' inner surfaces from v = r0 to r1, plus one tab per side as a rectangle square to its face, from the
        inner surface out through the face and `proud` past it. Returns (trapezoid, [tab, tab], (s_a, s_b)) with s
        the distance along each face's inner surface from the inner corner."""
        vi = 2 * (self.r_in - P["FACE_THICK"])                 # faces' inner surfaces meet here
        t30 = math.tan(math.radians(30))
        trap = [((vi - r0) * t30, r0), ((vi - r1) * t30, r1), (-(vi - r1) * t30, r1), (-(vi - r0) * t30, r0)]
        c30 = math.cos(math.radians(30))
        s_a, s_b = (vi - r1) / c30, (vi - r0) / c30
        tabs = []
        for sg in (1, -1):
            d = (sg * 0.5, -c30)                               # along the face, from the corner in
            n = (sg * c30, 0.5)                                # out through the face
            t = P["FACE_THICK"] + proud
            tabs.append([(sg * 0 + s * d[0] + w * n[0], vi + s * d[1] + w * n[1])
                         for s, w in ((s_a, 0.0), (s_b, 0.0), (s_b, t), (s_a, t))])
        return trap, tabs, (s_a, s_b)

    def face_inner_half(self):
        """Distance along a face from its centre to the faces' inner corner, on the inner surface."""
        return (self.r_in - P["FACE_THICK"]) * math.sqrt(3)

    def core_ok(self, u, v, pad=0.0):
        """(u, v) in a corner frame is inside the core, r_core from the centre across both neighbouring faces."""
        return 0.866025 * abs(u) + 0.5 * v + pad <= self.core_lim


def deck_diameter(spacing):
    return Layout(spacing).deck_d
