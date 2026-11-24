"""Small helpers over KiCad 7's pcbnew API for every generated board: the mast boards (builds/pcb/make_pcbs.py: deck,
face, end plate) and the module boards under boards/.

Coordinates are mm. Board centre is (100, 100) in KiCad's frame (y down).
Angles are degrees clockwise from 12 o'clock (as in make_shield_deck.py): the deck's top view, Sector 0 up.
"Local" frames: for a direction theta, u runs toward increasing angle (clockwise) and v runs outward along theta.
"""
import math
import os

import pcbnew

CX = CY = 100.0
FP_LIB = "/usr/share/kicad/footprints"


def mm(v):
    return pcbnew.FromMM(v)


def V(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def pol(r, a):
    t = math.radians(a)
    return CX + r * math.sin(t), CY - r * math.cos(t)


def loc(theta, u, v):
    t = math.radians(theta)
    return CX + u * math.cos(t) + v * math.sin(t), CY + u * math.sin(t) - v * math.cos(t)


def to_local(theta, x, y):
    t = math.radians(theta)
    dx, dy = x - CX, y - CY
    return dx * math.cos(t) + dy * math.sin(t), dx * math.sin(t) - dy * math.cos(t)


class Board:
    def __init__(self):
        self.b = pcbnew.BOARD()
        self.b.SetCopperLayerCount(2)
        self.nets = {}
        self.text_min = 0.0       # silkscreen minimums, set by fab_rules(): text() draws at least this big
        self.line_min = 0.0

    # ---- nets ----
    def net(self, name):
        if name is None:
            return None
        if name not in self.nets:
            n = pcbnew.NETINFO_ITEM(self.b, name)
            self.b.Add(n)
            self.nets[name] = n
        return self.nets[name]

    # ---- rules ----
    def rules(self, clearance, track, via_d, via_drill, min_hole=0.3, edge=0.5):
        ds = self.b.GetDesignSettings()
        ds.m_TrackMinWidth = mm(track)
        ds.m_ViasMinSize = mm(via_d)
        ds.m_MinThroughDrill = mm(min_hole)
        ds.m_CopperEdgeClearance = mm(edge)
        ds.m_MinClearance = mm(clearance)
        nc = ds.m_NetSettings.m_DefaultNetClass
        nc.SetClearance(mm(clearance))
        nc.SetTrackWidth(mm(track))
        nc.SetViaDiameter(mm(via_d))
        nc.SetViaDrill(mm(via_drill))

    def fab_rules(self, R, edge):
        """Hold DRC to the fab rules R (params.load_fab()): the minimums the board house can make. The design's own
        sizes (net class above) must already be at or above them; the generator checks that before it draws."""
        ds = self.b.GetDesignSettings()
        ds.m_TrackMinWidth = mm(R["FAB_TRACK_MIN"])
        ds.m_MinClearance = mm(R["FAB_CLEARANCE_MIN"])
        ds.m_ViasMinSize = mm(R["FAB_VIA_DIA_MIN"])
        ds.m_ViasMinAnnularWidth = mm(R["FAB_ANNULAR_MIN"])
        ds.m_MinThroughDrill = mm(R["FAB_PTH_DRILL_MIN"])
        ds.m_CopperEdgeClearance = mm(max(edge, R["FAB_EDGE_CLEAR_MIN"]))
        ds.m_HoleClearance = mm(R["FAB_HOLE_CLEAR_MIN"])
        ds.m_SolderMaskMinWidth = mm(R["FAB_MASK_BRIDGE_MIN"])
        ds.m_MinSilkTextHeight = mm(R["FAB_SILK_TEXT_MIN"])
        ds.m_MinSilkTextThickness = mm(R["FAB_SILK_LINE_MIN"])
        self.text_min, self.line_min = R["FAB_SILK_TEXT_MIN"], R["FAB_SILK_LINE_MIN"]

    def ts(self, size):
        """A text size raised to the fab minimum: what text() will draw for `size`, for laying things out round it."""
        return max(size, self.text_min)

    # ---- graphics ----
    def shape(self, layer, kind, width=0.15, fill=False):
        s = pcbnew.PCB_SHAPE(self.b)
        s.SetShape(kind)
        s.SetLayer(layer)
        s.SetWidth(mm(width))
        if fill:
            s.SetFilled(True)
        self.b.Add(s)
        return s

    def circle(self, layer, c, r, width=0.15, fill=False):
        s = self.shape(layer, pcbnew.SHAPE_T_CIRCLE, width, fill)
        s.SetCenter(V(*c))
        s.SetEnd(V(c[0] + r, c[1]))
        return s

    def line(self, layer, a, b, width=0.15):
        s = self.shape(layer, pcbnew.SHAPE_T_SEGMENT, width)
        s.SetStart(V(*a))
        s.SetEnd(V(*b))
        return s

    def rect(self, layer, a, b, width=0.15):
        for p, q in ((a, (b[0], a[1])), ((b[0], a[1]), b), (b, (a[0], b[1])), ((a[0], b[1]), a)):
            self.line(layer, p, q, width)

    def poly(self, layer, pts, width=0.15):
        for i in range(len(pts)):
            self.line(layer, pts[i], pts[(i + 1) % len(pts)], width)

    def text(self, layer, s, pos, size=1.5, angle=0.0, mirror=False, thick=None):
        t = pcbnew.PCB_TEXT(self.b)
        t.SetText(s)
        t.SetLayer(layer)
        t.SetPosition(V(*pos))
        size = self.ts(size)
        t.SetTextSize(V(size, size))
        t.SetTextThickness(mm(max(thick if thick else size * 0.15, self.line_min)))
        t.SetTextAngleDegrees(angle)
        if mirror:
            t.SetMirrored(True)
        self.b.Add(t)
        return t

    # ---- copper ----
    def track(self, pts, net, width, layer=pcbnew.F_Cu):
        n = self.net(net)
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) < 1e-6:
                continue
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(V(*a))
            t.SetEnd(V(*b))
            t.SetWidth(mm(width))
            t.SetLayer(layer)
            t.SetNet(n)
            self.b.Add(t)

    def via(self, pos, net, d, drill):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(V(*pos))
        v.SetDrill(mm(drill))
        v.SetWidth(mm(d))
        v.SetNet(self.net(net))
        self.b.Add(v)
        return v

    def zone(self, layer, outline, net, priority=0, holes=(), clearance=0.3, min_width=0.25,
             thermal=True, name=""):
        z = pcbnew.ZONE(self.b)
        z.SetLayer(layer)
        z.SetNet(self.net(net))
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(mm(clearance))
        z.SetMinThickness(mm(min_width))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL if thermal else pcbnew.ZONE_CONNECTION_FULL)
        z.SetThermalReliefGap(mm(0.4))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        if name:
            z.SetZoneName(name)
        ol = z.Outline()
        ol.NewOutline()
        for p in outline:
            ol.Append(mm(p[0]), mm(p[1]))
        for h in holes:
            ol.NewHole()
            for p in h:
                ol.Append(mm(p[0]), mm(p[1]), 0, ol.OutlineCount() - 1)
        self.b.Add(z)
        return z

    def keepout(self, layer_set, outline, tracks=True, vias=True, pads=False, pours=True):
        z = pcbnew.ZONE(self.b)
        z.SetIsRuleArea(True)
        z.SetLayerSet(layer_set)
        z.SetDoNotAllowTracks(tracks)
        z.SetDoNotAllowVias(vias)
        z.SetDoNotAllowPads(pads)
        z.SetDoNotAllowCopperPour(pours)
        z.SetDoNotAllowFootprints(False)
        ol = z.Outline()
        ol.NewOutline()
        for p in outline:
            ol.Append(mm(p[0]), mm(p[1]))
        self.b.Add(z)
        return z

    # ---- footprints ----
    def add_fp(self, fp, ref, value, pos, orient):
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPosition(V(*pos))
        fp.SetOrientationDegrees(orient)
        self.b.Add(fp)
        return fp

    def lib_fp(self, lib, name, ref, value, pos, orient, nets):
        fp = pcbnew.FootprintLoad(os.path.join(FP_LIB, lib + ".pretty"), name)
        if fp is None:
            raise ValueError(f"footprint {lib}:{name} not found")
        self.add_fp(fp, ref, value, pos, orient)
        for p in fp.Pads():
            if p.GetNumber() in nets:
                p.SetNet(self.net(nets[p.GetNumber()]))
        fp.Value().SetVisible(False)
        return fp

    def pad_xy(self, ref, num):
        fp = self.b.FindFootprintByReference(ref)
        for p in fp.Pads():
            if p.GetNumber() == num:
                q = p.GetPosition()
                return pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
        raise KeyError(f"{ref}.{num}")

    def fab_silk(self, R):
        """Bring every silkscreen line and visible text up to the fab minimums (FAB_SILK_LINE_MIN,
        FAB_SILK_TEXT_MIN): thinner lines are widened, smaller text is enlarged with its stroke scaled to match.
        Library footprints are included. Returns (lines widened, texts enlarged)."""
        lmin, hmin = mm(R["FAB_SILK_LINE_MIN"]), mm(R["FAB_SILK_TEXT_MIN"])
        silk = (pcbnew.F_SilkS, pcbnew.B_SilkS)
        nl = nt = 0
        items = list(self.b.GetDrawings())
        for fp in self.b.GetFootprints():
            items += list(fp.GraphicalItems()) + [fp.Reference(), fp.Value()]
        for it in items:
            if it.GetLayer() not in silk:
                continue
            if hasattr(it, "GetTextHeight"):
                if not it.IsVisible():
                    continue
                h, w, t = it.GetTextHeight(), it.GetTextWidth(), it.GetTextThickness()
                if h < hmin:
                    k = hmin / h
                    it.SetTextSize(pcbnew.VECTOR2I(int(w * k), hmin))
                    t = int(t * k)
                    nt += 1
                if t < lmin:
                    t = lmin
                it.SetTextThickness(t)
            elif hasattr(it, "GetWidth") and 0 < it.GetWidth() < lmin:
                it.SetWidth(lmin)
                nl += 1
        return nl, nt

    def save(self, path):
        self.b.Save(path)


def fp_orient(theta, extra=0.0):
    """Footprint orientation so its local +x points along u and its local -y (up) along v of the frame theta,
    plus `extra` degrees counter-clockwise (KiCad's sense). Checked against pad positions in the generator."""
    return -theta + extra


def custom_fp(board, ref, value):
    fp = pcbnew.FOOTPRINT(board.b)
    fp.SetReference(ref)
    fp.SetValue(value)
    return fp


def smd_pad(fp, name, x, y, w, h, net=None, board=None, layers="F"):
    p = pcbnew.PAD(fp)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(V(w, h))
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu if layers == "F" else pcbnew.B_Cu)
    ls.AddLayer(pcbnew.F_Mask if layers == "F" else pcbnew.B_Mask)
    p.SetLayerSet(ls)
    p.SetNumber(name)
    p.SetPos0(V(x, y)) if hasattr(p, "SetPos0") else None
    p.SetPosition(V(x, y))
    if net and board:
        p.SetNet(board.net(net))
    fp.Add(p)
    return p


def th_pad(fp, name, x, y, dia, drill, net=None, board=None, plated=True):
    p = pcbnew.PAD(fp)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if plated else pcbnew.PAD_ATTRIB_NPTH)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(V(dia, dia))
    p.SetDrillSize(V(drill, drill))
    ls = pcbnew.LSET.AllCuMask() if plated else pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Mask)
    ls.AddLayer(pcbnew.B_Mask)
    p.SetLayerSet(ls)
    p.SetNumber(name)
    p.SetPos0(V(x, y)) if hasattr(p, "SetPos0") else None
    p.SetPosition(V(x, y))
    if net and board:
        p.SetNet(board.net(net))
    fp.Add(p)
    return p


def fp_line(fp, layer, a, b, width=0.12):
    s = pcbnew.FP_SHAPE(fp) if hasattr(pcbnew, "FP_SHAPE") else pcbnew.PCB_SHAPE(fp)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    s.SetStart(V(*a))
    s.SetEnd(V(*b))
    if hasattr(s, "SetLocalCoord"):
        s.SetStart0(V(*a))
        s.SetEnd0(V(*b))
    fp.Add(s)
    return s


def fp_rect(fp, layer, a, b, width=0.12):
    for p, q in ((a, (b[0], a[1])), ((b[0], a[1]), b), (b, (a[0], b[1])), ((a[0], b[1]), a)):
        fp_line(fp, layer, p, q, width)


def fp_circle(fp, layer, c, r, width=0.12):
    s = pcbnew.FP_SHAPE(fp) if hasattr(pcbnew, "FP_SHAPE") else pcbnew.PCB_SHAPE(fp)
    s.SetShape(pcbnew.SHAPE_T_CIRCLE)
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    s.SetCenter(V(*c))
    s.SetEnd(V(c[0] + r, c[1]))
    if hasattr(s, "SetStart0"):
        s.SetStart0(V(*c))
        s.SetEnd0(V(c[0] + r, c[1]))
    fp.Add(s)
    return s

