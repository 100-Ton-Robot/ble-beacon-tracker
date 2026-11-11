"""1:1 printable PDF templates: shield deck drill template, electronics plate (both discs drawn the same way
round, plate 12 o'clock up), the plate wiring diagram, the alt split plate, the pipe plate and its stack views, then the back panel
(reflector face).

Uses the same geometry as make_shield_deck.py. Run:  python make_templates.py
Print at 100% / "Actual size" and check the 100 mm scale bar with a ruler.
"""
import math
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

import make_shield_deck as g
import params

# Every number lives in parameters.csv (all groups but "deck", which make_shield_deck.py reads). Only values derived
# from others are computed here.
globals().update(params.load(exclude=["deck"]))

PAGE_W, PAGE_H = letter
# Printed-dipole panel board (measured 60 x 50 mm) taken out of its housing and turned 90 deg,
# long bar vertical, centred across the face. Its own coax and stalk plug into the deck's P2 jack,
# which is on the right seen from the front, so the coax notch faces right.
POST_SHIFT = BOARD_W / 2 - (POST_EDGE + BOARD_HOLE / 2 + POST_X / 2)  # ~3.5 mm: hole pattern off the board
                                                                      # centre, away from the coax notch
# Test position C: board as it sat in the housing (long bar horizontal), coax notch up toward the deck.
# Placed so its holes keep >= 5.5 mm (an M3 head) from the A holes. P2 sits 25 mm off the face centre (moved in
# 2026-11-10), so the coax reaches it from either position without extending.

# Electronics plate (separate ~152 mm acrylic disc). Top view: PoE splitter + ESP32 gateway on the left,
# 3 bare XIAOs on the right, all three pigtails through one hole in the strip between the ESP32 and the XIAOs,
# level with S1's IPEX4 connector (decided 2026-10-31): the coax sweep from their deck jacks to it without hard
# corners, MHF4 ends threaded up from below, and the hole (grommet or a dab of RTV) is their strain relief.
# Each XIAO has a 4-wire tail to an inline JST pair (90 mm tails each side); the mated pair lies in the strip,
# clear of the hole. Its far side runs back: TX (D6) to the sector's own
# ESP32 RX pin, the rest to the bus board at the top of the strip (rows: ESP TX to every D7, GND, spare, 5V). Zip ties through hole pairs; the bus board on one M3.
# Three M4 bolts on spacers tie the plate to the deck through the deck's mount holes. The plate is turned
# so its 12 o'clock is PLATE_TURN deg counter-clockwise of the deck's S0 arrow (top view); the bolts then land
# at 3, 7 and 11 o'clock on the plate, clear of the parts.


def scale_bar(c, x, y):
    c.setLineWidth(0.6)
    c.line(x * mm, y * mm, (x + 100) * mm, y * mm)
    for k in range(0, 101, 10):
        h = 3 if k % 50 else 5
        c.line((x + k) * mm, y * mm, (x + k) * mm, (y + h) * mm)
    c.setFont("Helvetica", 8)
    c.drawString(x * mm, (y - 4) * mm, "0")
    c.drawRightString((x + 100) * mm, (y - 4) * mm, "100 mm - check with a ruler before drilling")


def crosshair(c, x, y, r):
    c.line((x - r - 2) * mm, y * mm, (x + r + 2) * mm, y * mm)
    c.line(x * mm, (y - r - 2) * mm, x * mm, (y + r + 2) * mm)


def deck_page(c):
    ox = PAGE_W / mm / 2 - g.CX          # page offset so the disc is centred
    oy = 140 - g.CY
    turn = math.radians(PLATE_TURN)      # drawn turned like the plate page: plate 12 o'clock up, S0 arrow clockwise

    def P(p):
        dx, dy = p[0] - g.CX, p[1] - g.CY
        return (g.CX + dx * math.cos(turn) + dy * math.sin(turn) + ox,
                g.CY - dx * math.sin(turn) + dy * math.cos(turn) + oy)

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm, "Shield deck drill template - 146 mm disc - PRINT AT 100% (Actual size)")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Viewed from the TOP (electronics side). Tape to the board, centre-punch each crosshair, then drill.")
    scale_bar(c, 15, PAGE_H / mm - 32)

    cx, cy = P((g.CX, g.CY))
    c.setLineWidth(0.8)
    c.circle(cx * mm, cy * mm, g.R * mm)                     # cut line
    c.setLineWidth(0.3)
    crosshair(c, cx, cy, 4)

    # reflector faces (copper side on this line, facing out)
    c.setDash(3, 2)
    tri = [P(g.pol(g.CIRCUMRADIUS, v)) for v in g.VERTICES]
    path = c.beginPath()
    path.moveTo(tri[0][0] * mm, tri[0][1] * mm)
    for x, y in tri[1:]:
        path.lineTo(x * mm, y * mm)
    path.close()
    c.drawPath(path)
    # M4 nuts under the deck, flush in the core corners (two flats on the faces' inner sides)
    hr = g.NUT_AF / math.sqrt(3)
    for d, x, y, lab in g.holes:
        if lab == "M4 mount":
            hexa = [P((x + hr * math.sin(math.radians(a)), y + hr * math.cos(math.radians(a))))
                    for a in range(30, 390, 60)]
            path = c.beginPath()
            path.moveTo(hexa[0][0] * mm, hexa[0][1] * mm)
            for hx, hy in hexa[1:]:
                path.lineTo(hx * mm, hy * mm)
            path.close()
            c.drawPath(path)
    c.setDash()

    letters ={"duck/monopole": "D", "patch": "P", "patch end": "P2", "dipole coax": "C"}
    for d, x, y, lab in g.holes:
        if lab == "via":
            continue
        px, py = P((x, y))
        c.setLineWidth(0.5)
        c.circle(px * mm, py * mm, d / 2 * mm)
        c.setLineWidth(0.2)
        crosshair(c, px, py, d / 2)
        if lab == "core feed":     # centre hole: the disc's centre crosshair marks it
            c.setFont("Helvetica-Bold", 7)
            c.drawString((px + d / 2 + 2) * mm, (py + 2) * mm, f"core {d:g}")
            continue
        tag = "M4" if lab == "M4 mount" else letters[lab.split(" ", 1)[1]]
        # label just below each hole; patch holes sit close to the face line, so label them on the outer side
        c.setFont("Helvetica-Bold", 7)
        if tag == "P2":            # along the face toward the centre P hole, clear of the rim
            s = g.SECTORS[int(lab[1])]
            lx, ly = P(g.face_pt(s, g.PATCH_OFFSET, g.FACE_WIDTH / 2 - g.PATCH_END_INSET - 10))
            c.drawCentredString(lx * mm, (ly - 1) * mm, f"{tag} {d:g}")
        elif tag == "P" and px < cx - 1:
            c.drawRightString((px - d / 2 - 3) * mm, (py - 1) * mm, f"{tag} {d:g}")
        elif tag == "P":
            c.drawString((px + d / 2 + 3) * mm, (py - 1) * mm, f"{tag} {d:g}")
        elif py < cy - g.R + 20:   # near the bottom of the disc: beside the hole, clear of the rim
            c.drawRightString((px - d / 2 - 3) * mm, (py - 1) * mm, f"{tag} {d:g}")
        else:
            c.drawCentredString(px * mm, (py - d / 2 - 5) * mm, f"{tag} {d:g}")

    # pipe layout only: 2-1/4" hole saw at the centre for the pipe and its adapter (removes the C holes)
    c.saveState()
    c.setStrokeColorRGB(0.0, 0.35, 0.8)
    c.setFillColorRGB(0.0, 0.35, 0.8)
    c.setLineWidth(0.6)
    c.setDash(4, 2)
    c.circle(cx * mm, cy * mm, PIPE_SAW / 2 * mm)
    c.setDash()
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(cx * mm, (cy + PIPE_SAW / 2 + 2) * mm, "PIPE LAYOUT ONLY: 2-1/4\" hole saw")
    c.restoreState()

    for i, s in enumerate(g.SECTORS):
        lx, ly = P(g.pol(57, s + 20))
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(lx * mm, ly * mm, f"S{i}")
    arrow = [P((g.CX + dx, g.CY + 52 + dy)) for dx, dy in ((-3, -3), (0, 3), (3, -3))]   # S0 arrow, turned
    c.setLineWidth(0.6)
    for (x0, y0), (x1, y1) in zip(arrow, arrow[1:]):
        c.line(x0 * mm, y0 * mm, x1 * mm, y1 * mm)

    c.setFont("Helvetica", 8.5)
    lines = [
        "Solid circle = cut line (146 mm).  Dashed triangle = where the 120 mm back panels stand, copper side out.",
        f"D 6.5 mm = rubber duck / monopole / dipole whip ({g.DUCK_SPACING:g} mm in front of face)    "
        f"P / P2 6.5 mm = patch ({g.PATCH_OFFSET:g} mm in front of face; P2 {g.FACE_WIDTH / 2 - g.PATCH_END_INSET:g} mm off centre)",
        f"C 10 mm = dipole coax pass-through (inside core)    M4 {g.HOLE_M4:g} mm = bolts to the plate, nut flush in each core corner",
        "Core 10 mm at the centre = antenna coax into the core; open it up with a hole saw (centre mark) if needed.",
        f"Blue dashed {PIPE_SAW:.1f} mm (2-1/4\" hole saw) = pipe layout only (page 3): the pipe passes into the core;",
        "it removes the C holes. Other layouts keep the 10 mm core hole. EU: a 57 mm hole saw is the same size.",
        "Arrow points to Sector 0. Holes are symmetric, so the template also works flipped (labels read mirrored).",
        f"Drawn the same way round as the plates: plate 12 o'clock up, S0 arrow {PLATE_TURN:g} deg clockwise of it.",
    ]
    for n, t in enumerate(lines):
        c.drawString(15 * mm, (62 - n * 4.4) * mm, t)
    scale_bar(c, 15, 22)


def face_page(c):
    x0 = PAGE_W / mm / 2 - g.FACE_WIDTH / 2
    top = PAGE_H / mm - 45
    xc = x0 + g.FACE_WIDTH / 2

    def Y(d):                      # mm below the top (deck) edge -> page y
        return top - d

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm, f"Back panel (reflector face) template - {g.FACE_WIDTH:g} x {FACE_H:g} mm - PRINT AT 100%")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Make 3. Viewed from the FRONT (copper side, facing the antenna). Top edge goes against the shield deck.")
    scale_bar(c, 15, PAGE_H / mm - 32)

    c.setLineWidth(0.8)
    c.rect(x0 * mm, Y(FACE_H) * mm, g.FACE_WIDTH * mm, FACE_H * mm)   # cut line
    c.setLineWidth(0.2)
    c.setDash(1, 2)
    c.line(xc * mm, Y(0) * mm, xc * mm, Y(FACE_H) * mm)               # centre line
    c.setDash()
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(xc * mm, (Y(0) + 2) * mm, "TOP - against shield deck")

    # dipole feed hole at the face centre
    c.setLineWidth(0.5)
    c.circle(xc * mm, Y(FACE_H / 2) * mm, DIPOLE_HOLE / 2 * mm)
    crosshair(c, xc, Y(FACE_H / 2), DIPOLE_HOLE / 2)
    c.setFont("Helvetica", 7)

    # where the deck's patch jacks sit, 7 mm in front of this face: P over the centre, P2 to the right
    c.setLineWidth(0.4)
    c.setFont("Helvetica", 6.5)
    for jx, name in ((0, "P"), (g.FACE_WIDTH / 2 - g.PATCH_END_INSET, "P2")):
        c.line((xc + jx) * mm, Y(0) * mm, (xc + jx) * mm, Y(4) * mm)
        c.drawString((xc + jx + 1) * mm, Y(4) * mm, f"{name} jack above")

    # printed-dipole panel board, centred across the face, at test positions A (bar vertical, notch right)
    # and C (bar horizontal, notch up), with their post holes
    c.setLineWidth(0.3)
    c.setDash(3, 2)
    c.rect((xc - BOARD_W / 2) * mm, Y(BOARD_CY + BOARD_H / 2) * mm, BOARD_W * mm, BOARD_H * mm)
    c.setDash()
    holes = {(xc - POST_SHIFT + sx, BOARD_CY + sy) for sx in (-POST_X / 2, POST_X / 2)
             for sy in (-POST_Y / 2, POST_Y / 2)}
    yc = BOARD_CY_C
    c.setLineWidth(0.3)
    c.setStrokeGray(0.55)
    c.rect((xc - BOARD_H / 2) * mm, Y(yc + BOARD_W / 2) * mm, BOARD_H * mm, BOARD_W * mm)
    c.setStrokeGray(0)
    holes.update((xc + sx, yc + POST_SHIFT + sy) for sx in (-POST_Y / 2, POST_Y / 2)
                 for sy in (-POST_X / 2, POST_X / 2))
    c.setLineWidth(0.5)
    for hx, hy in holes:
        c.circle(hx * mm, Y(hy) * mm, POST_HOLE / 2 * mm)
        crosshair(c, hx, Y(hy), POST_HOLE / 2)
    c.drawCentredString(xc * mm, (Y(BOARD_CY - BOARD_H / 2) + 5.5) * mm,
                        f"{len(holes)} x {POST_HOLE:g} mm post holes - check against your board first.")
    c.drawCentredString(xc * mm, (Y(BOARD_CY - BOARD_H / 2) + 2) * mm,
                        "Holes under 10 mm don't affect the reflector.")

    def callout(tx, ty, lines, px, py, right=True):
        """Note at (tx, ty) page mm, top line first, with a leader to the point (px, py)."""
        c.setFont("Helvetica", 7)
        for n, t in enumerate(lines):
            (c.drawString if right else c.drawRightString)(tx * mm, (ty - n * 3.4) * mm, t)
        c.setLineWidth(0.25)
        c.line(((tx - 1) if right else (tx + 1)) * mm, (ty + 1) * mm, px * mm, py * mm)
        c.circle(px * mm, py * mm, 0.5 * mm, fill=1)

    xr = x0 + g.FACE_WIDTH + 4                 # right of the face
    xl = x0 - 4                                # left of the face
    callout(xr, Y(BOARD_CY - BOARD_H / 2 + 4), [
        f"A (dashed): panel board {BOARD_W:g} x {BOARD_H:g} mm,",
        "bar vertical, notch right,",
        f"{BOARD_CY - BOARD_H / 2:g}-{BOARD_CY + BOARD_H / 2:g} mm down.",
        "Its stalk reaches the P2 deck jack."], xc + BOARD_W / 2, Y(BOARD_CY - BOARD_H / 2 + 4))
    callout(xr, Y(76), [
        "C (grey): same board turned,",
        "bar horizontal, notch up,",
        f"{yc - BOARD_W / 2:g}-{yc + BOARD_W / 2:g} mm down.",
        "Its coax reaches P2 too."], xc + BOARD_H / 2, Y(76))
    callout(xr, Y(101), [
        f"Either way the board stands",
        f"{BOARD_GAP:g} mm off this face: M2 nylon",
        "screws + standoffs in the posts."], xc + POST_Y / 2, Y(yc + POST_SHIFT + POST_X / 2))
    callout(xl, Y(FACE_H / 2) + 14, [
        f"Centre {DIPOLE_HOLE:g} mm hole:",
        "DIY dipole RP-SMA only."], xc - DIPOLE_HOLE / 2, Y(FACE_H / 2), right=False)
    callout(xl, Y(8), [
        "Side edges: each meets the next",
        "panel at 120 deg to form the",
        "triangle; solder or tape the seam."], x0, Y(14), right=False)

    # dimensions
    c.setFont("Helvetica", 8)
    c.drawCentredString(xc * mm, (Y(FACE_H) - 6) * mm, f"{g.FACE_WIDTH:g} mm")
    c.drawString((x0 + g.FACE_WIDTH + 4) * mm, (Y(FACE_H) + 2) * mm, f"{FACE_H:g} mm tall, centre at {FACE_H / 2:g} mm")

    c.setFont("Helvetica", 8.5)                 # only notes about things not drawn on this page
    c.drawString(15 * mm, (Y(FACE_H) - 16) * mm,
                 "Whips (rubber duck / monopole / dipole) don't mount on this face: they hang on the deck's D holes,")
    c.drawString(15 * mm, (Y(FACE_H) - 20.5) * mm, f"{g.DUCK_SPACING:g} mm in front of it (page 1).")
    scale_bar(c, 15, 14)


def pigtail_x():
    return (ESP32[0] + ESP32[2] + XIAO_X - XIAO_L / 2) / 2      # middle of the strip


def pigtail_y():
    return XIAO_YS[1] + IPEX_DY                                 # level with S1's IPEX4 connector


def jst_box(i):
    """x0, y0 of sector i's mated JST pair in the strip, long axis across it."""
    return pigtail_x() - JST_L / 2, JST_YS[i] - JST_W / 2


def plate_holes():
    """(diameter, x, y, tag) in mm from the plate centre, y up."""
    out = [(PIGTAIL_HOLE, pigtail_x() - PIGTAIL_DX, pigtail_y(), "pigtail"), (PLATE_M3, *POWER_HOLE, "power")]
    for v in g.VERTICES:                              # deck mount holes, seen in the plate's frame
        a = math.radians(v + PLATE_TURN)
        out.append((PLATE_M4, g.MOUNT_RADIUS * math.sin(a), g.MOUNT_RADIUS * math.cos(a), "M4"))
    for i, (yc, dx) in enumerate(zip(XIAO_YS, XIAO_TIE_DX)):   # one tie across each XIAO
        for sy in (-1, 1):
            out.append((TIE_HOLE, XIAO_X + dx, yc + sy * (XIAO_W / 2 + TIE_CLEAR), f"S{i} tie"))
    for (x0, y0, w, h), ties in ((SPLITTER, SPLITTER_TIES), (ESP32, ESP32_TIES)):
        for ty in ties:
            out += [(TIE_HOLE, x0 - TIE_CLEAR, ty, "tie"), (TIE_HOLE, x0 + w + TIE_CLEAR, ty, "tie")]
    return out


# Centre pipe mount (user, 2026-11-09; replaces the CA2100C flange): a 1/2" PVC male adapter (socket x 1/2" male
# thread) under the plate, its thread up through the enclosure bottom and the plate's centre hole, a nut on top
# clamping both. The 1/2" pipe in its socket hangs into the core. Hole: 7/8" for the 1/2" thread (21.3 mm OD);
# the nut's size is an estimate (keep top-side parts clear of it).


def adapter_trace(c, P, ox, oy):
    c.saveState()
    c.setStrokeColorRGB(0.0, 0.35, 0.8)
    c.setFillColorRGB(0.0, 0.35, 0.8)
    c.setLineWidth(0.5)
    c.circle(*P(0, 0), ADAPTER_HOLE / 2 * mm)
    c.setLineWidth(0.4)
    c.setDash(4, 2)
    c.circle(*P(0, 0), NUT_OD / 2 * mm)
    c.setDash()
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(*P(0, -NUT_OD / 2 - 3), f"pipe adapter: {ADAPTER_HOLE:g} mm (7/8\") hole,")
    c.drawCentredString(*P(0, -NUT_OD / 2 - 5.6), "nut on top (dashed)")
    c.restoreState()


def plate_page(c):
    ox, oy = PAGE_W / mm / 2, 140

    def P(x, y):
        return (x + ox) * mm, (y + oy) * mm

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm,
                 f"Electronics plate template - {PLATE_DIAMETER:g} mm disc - PRINT AT 100% (Actual size)")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Viewed from the TOP (parts side). Gateway left, scanners right, one pigtail hole and the JST pairs between.")
    scale_bar(c, 15, PAGE_H / mm - 32)

    c.setLineWidth(0.8)
    c.circle(*P(0, 0), PLATE_DIAMETER / 2 * mm)
    c.setLineWidth(0.3)
    crosshair(c, ox, oy, 4)

    # part outlines
    c.setDash(3, 2)
    for x0, y0, w, h in (SPLITTER, ESP32):
        c.rect(*P(x0, y0), w * mm, h * mm)
    c.setDash()
    c.setFont("Helvetica", 7)
    c.drawCentredString(*P(SPLITTER[0] + SPLITTER[2] / 2, 0), "PoE splitter")
    c.drawCentredString(*P(ESP32[0] + ESP32[2] / 2, 0), "ESP32")
    c.drawCentredString(*P(ESP32[0] + ESP32[2] / 2, ESP32[1] + ESP32[3] - 5), "RJ45 + USB-C")
    c.rect(*P(POWER[0], POWER[1]), POWER[2] * mm, POWER[3] * mm)
    c.drawCentredString(*P(POWER[0] + POWER[2] / 2, POWER[1] + POWER[3] + 2), "TX / GND / 5V bus")
    c.setDash(1, 1.5)
    for i in range(3):                                   # mated JST pairs (the wiring page names them)
        jx, jy = jst_box(i)
        c.rect(*P(jx, jy), JST_L * mm, JST_W * mm)
    c.setDash()
    for i, yc in enumerate(XIAO_YS):
        c.setLineWidth(0.4)
        c.rect(*P(XIAO_X - XIAO_L / 2, yc - XIAO_W / 2), XIAO_L * mm, XIAO_W * mm)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(*P(XIAO_X + 1, yc - 1), f"S{i}")
        c.setFont("Helvetica", 6)
        c.drawCentredString(*P(XIAO_X + XIAO_L / 2 - 2.5, yc - 1), "USB")
        c.drawCentredString(*P(XIAO_X - XIAO_L / 2 + 3.5, yc + IPEX_DY - 1), "IPEX4")

    for d, x, y, tag in plate_holes():
        c.setLineWidth(0.5)
        c.circle(*P(x, y), d / 2 * mm)
        c.setLineWidth(0.2)
        crosshair(c, x + ox, y + oy, d / 2)
        if tag == "M4":
            c.setFont("Helvetica-Bold", 7)
            if x > 0:                                 # between the XIAOs: label beside, not below
                c.drawString(*P(x + d / 2 + 2, y - 1), "M4")
            else:
                c.drawCentredString(*P(x, y - d / 2 - 5), "M4")

    c.setFont("Helvetica", 8.5)
    notes = [
        f"{PIGTAIL_HOLE:g} mm: all three pigtails (MHF4 ends threaded up from below), level with S1's IPEX4 connector -",
        f"assumed {IPEX_DY:g} mm above the XIAO centre line: check on the board.  {PLATE_M3:g} mm (M3): bus board.",
        f"3 x {PLATE_M4:g} mm (M4, labelled): bolts to the deck, plate 12 o'clock {PLATE_TURN:g} deg counter-clockwise "
        "of the deck's S0 arrow, ~25 mm up.",
        f"Small holes: {TIE_HOLE:g} mm zip-tie pairs: one tie across each XIAO (USB-C toward the rim), two each across",
        "splitter and ESP32. Coax strain relief: grommet in the pigtail hole, or a dab of RTV once the coax are placed.",
        "Dotted: mated JST pairs (unplug to reflash); far side D6 to its ESP32 RX pin, 3 wires to the bus.",
        "Dashed: ESP32-S3-ETH 72.8 x 21 mm; splitter from a photo - lay it on the printout, tie holes "
        "{:g} mm outside its edges.".format(TIE_CLEAR),
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (60 - n * 4.1) * mm, t)
    scale_bar(c, 15, 22)


# Wiring diagram (last page), drawn over the wired part of the plate layout. Pin numbers: XIAO pins 1-7 = D0-D6,
# 8-14 = D7, D8, D9, D10, 3V3, GND, 5V; ESP32-S3-ETH header pins as on Waveshare's pinout. The board lies RJ45 side
# up with the RJ45 / USB-C end north, so pins 40 (VBUS, top) to 21 run along the edge facing the radios (decided
# 2026-10-31). Pad positions are approximate.
# Wires run in straight lanes (see the lane constants below); the JST pair sits in the wire (pin number in the
# XIAO-end label).
ESP_PAD_X = ESP32[0] + ESP32[2] - 1.3   # header pads just inside the ESP32's right edge
ESP_PIN40_Y = ESP32[1] + ESP32[3] - 2.5
BUS_COLS = tuple(POWER[0] + POWER[2] / 2 + k * 2.54 for k in (-1.5, -0.5, 0.5, 1.5))  # cols 1-4: ESP, S0, S1, S2
RED, BLACK, YELLOW, GREEN = (0.85, 0.0, 0.0), (0.0, 0.0, 0.0), (0.85, 0.65, 0.0), (0.0, 0.6, 0.2)  # JST wire colours
JST_PINS = ((RED, "red", "5V (14)"), (BLACK, "black", "GND (13)"), (YELLOW, "yellow", "D6 TX (7)"),
            (GREEN, "green", "D7 RX (8)"))   # JST pins 1-4, crimp side, key peg up, left to right
SECTOR_PINS = tuple(zip(SECTOR_RX_PINS, SECTOR_RX_GPIOS))   # (header pin, GPIO) of each sector's ESP32 RX
WIRING_XIAO_X = XIAO_X + WIRING_XIAO_DX


def esp_pin_y(n):
    return ESP_PIN40_Y - (40 - n) * 2.54


# Wiring page lanes, plate mm. Wires run straight in fixed lanes, so each bundle stays together:
# - XIAO tail: yellow over the top edge of the XIAO, the rest under its bottom edge, then up the gap to the JST.
# - Far tail: yellow left to its ESP32 RX pin; red up its bus column, black / green up lanes just left / right of
#   it. S1 and S2 red / black / green go up the strip's right side, past the far halves above, then left under
#   the bus. The ESP TX feed (green) goes up left of the bus and into the TX row from the side.


def jst_halves(i):
    """Wiring page only: x0, y0 of sector i's far half (in the strip) and XIAO half (off its USB end)."""
    return (FAR_X0, WIRING_JST_YS[i] - JST_W / 2), (WIRING_XIAO_X + XIAO_L / 2 + XIAO_JST_GAP, XIAO_YS[i] - JST_W / 2)


def jst_pin_y(y0, n):
    return y0 + JST_W / 2 + (2.5 - n) * JST_PITCH


def wiring_routes():
    """(colour, XIAO-tail points or None, far-tail points, XIAO-end label or None, ESP-end label or None), plate mm.
    XIAO tail: pad -> that pin on the XIAO half; far tail: same pin on the far half -> ESP32 pin or bus pad."""
    xr = WIRING_XIAO_X + XIAO_L / 2
    pad = [xr - 2.88 - k * 2.54 for k in range(7)]   # pad x from the USB end; top: D0..D6, bottom: 5V, GND, 3V3, D10..D7
    d6x, gndx, v5x = pad[6], pad[1], pad[0]
    xy_, xr_, xb_, xg_ = (xr + d for d in XT_LANES)
    txr, gnd, v5 = BUS_ROWS[0], BUS_ROWS[1], BUS_ROWS[3]
    etx, getx = ESP_TX

    def bx(k):                                       # black lane, just left of bus column k
        return BUS_COLS[k] - BUS_LANE

    def gx(k):                                       # green lane, just right of bus column k
        return BUS_COLS[k] + BUS_LANE

    out = [
        (RED, None, ((ESP_PAD_X, esp_pin_y(40)), (BUS_COLS[0], esp_pin_y(40)), (BUS_COLS[0], v5)),
         None, "VBUS (40) -- bus 5V row"),
        (BLACK, None, ((ESP_PAD_X, esp_pin_y(38)), (bx(0), esp_pin_y(38)), (bx(0), gnd), (BUS_COLS[0], gnd)),
         None, "GND (38) -- bus GND row"),
        (GREEN, None, ((ESP_PAD_X, esp_pin_y(etx)), (FEED_TX_LANE, esp_pin_y(etx)), (FEED_TX_LANE, txr),
                       (BUS_COLS[0], txr)),
         None, f"GPIO{getx} TX ({etx}) -- bus TX row"),
    ]
    for i, yc in enumerate(XIAO_YS):
        top, bot = yc + XIAO_ROW, yc - XIAO_ROW
        above, below = yc + XIAO_W / 2 + XT_STEP, yc - XIAO_W / 2 - XT_STEP
        rx, grx = SECTOR_PINS[i]
        (fx, fy), (jx, jy) = jst_halves(i)
        s = f"S{i} XIAO"

        def jp(n):
            return jst_pin_y(jy, n)

        def fp(n):
            return jst_pin_y(fy, n)

        c = BUS_COLS[i + 1]
        yl = YELLOW_LANES[i]
        yellow = ((fx, fp(3)), (yl, fp(3)), (yl, esp_pin_y(rx)), (ESP_PAD_X, esp_pin_y(rx)))
        if i == 0:                                   # straight up the left side of the strip
            red = ((fx, fp(1)), (c, fp(1)), (c, v5))
            black = ((fx, fp(2)), (bx(1), fp(2)), (bx(1), gnd), (c, gnd))
            green = ((fx, fp(4)), (gx(1), fp(4)), (gx(1), txr), (c, txr))
        else:                                        # up the right side, then left under the bus
            top_f = fy + JST_W
            lb, lr, lg = RIGHT_LANES[3 * i - 3:3 * i]
            tb, tr, tg = TOP_TURNS[3 * i - 3:3 * i]
            green = ((fx, fp(4)), (GREEN_RISE_X, fp(4)), (GREEN_RISE_X, top_f + RISE[0]), (lg, top_f + RISE[0]),
                     (lg, tg), (gx(i + 1), tg), (gx(i + 1), txr), (c, txr))
            red = ((fx, fp(1)), (BUS_COLS[1], fp(1)), (BUS_COLS[1], top_f + RISE[1]), (lr, top_f + RISE[1]),
                   (lr, tr), (c, tr), (c, v5))
            black = ((fx, fp(2)), (bx(1), fp(2)), (bx(1), top_f + RISE[2]), (lb, top_f + RISE[2]),
                     (lb, tb), (bx(i + 1), tb), (bx(i + 1), gnd), (c, gnd))
        out += [
            (YELLOW, ((d6x, top), (d6x, above), (xy_, above), (xy_, jp(3)), (jx, jp(3))), yellow,
             f"D6 TX (7) -- JST 3 -- ESP32 GPIO{grx} RX ({rx})", f"GPIO{grx} RX ({rx}) -- {s} D6 TX (7)"),
            (GREEN, ((d6x, bot), (d6x, below - 2 * XT_STEP), (xg_, below - 2 * XT_STEP), (xg_, jp(4)), (jx, jp(4))),
             green, f"D7 RX (8) -- JST 4 -- bus TX row, col S{i}", None),
            (BLACK, ((gndx, bot), (gndx, below - XT_STEP), (xb_, below - XT_STEP), (xb_, jp(2)), (jx, jp(2))),
             black, f"GND (13) -- JST 2 -- bus GND row, col S{i}", None),
            (RED, ((v5x, bot), (v5x, below), (xr_, below), (xr_, jp(1)), (jx, jp(1))),
             red, f"5V (14) -- JST 1 -- bus 5V row, col S{i}", None),
        ]
    return out


def wiring_page(c):
    sc = WIRING_SCALE
    vx0, vy0, vx1, vy1 = WIRING_VIEW
    ox = PAGE_W / mm / 2 - sc * (vx0 + vx1) / 2
    oy = PAGE_H / mm - 30 - sc * vy1

    def P(x, y):
        return (ox + sc * x) * mm, (oy + sc * y) * mm

    def R(r):
        return sc * r * mm

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm, "Wiring diagram - XIAO radios, JST pairs, bus board, ESP32")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Not to scale for mounting: shows connections only. Pin numbers in brackets. Pad positions approximate.")
    c.drawString(15 * mm, (PAGE_H / mm - 25.5) * mm,
                 "JST halves drawn apart: XIAO half beside the radio, far half by the bus; same name = they plug together.")

    # layout in grey, clipped to the view
    c.saveState()
    clip = c.beginPath()
    clip.rect(*P(vx0, vy0), R(vx1 - vx0), R(vy1 - vy0))
    c.clipPath(clip, stroke=1, fill=0)
    c.setStrokeGray(0.7)
    c.setLineWidth(0.5)
    c.setDash(3, 2)
    c.rect(*P(ESP32[0], ESP32[1]), R(ESP32[2]), R(ESP32[3]))
    c.setDash()
    c.rect(*P(POWER[0], POWER[1]), R(POWER[2]), R(POWER[3]))
    for d, x, y, tag in plate_holes():          # the bus board's own M3 mounting hole
        if tag == "power":
            c.circle(*P(x, y), R(d / 2))
    c.restoreState()
    c.setFillGray(0.5)
    c.setFont("Helvetica", 8)
    c.drawCentredString(*P(ESP32[0] + ESP32[2] / 2 - 2, 0), "ESP32-S3-ETH")
    c.drawCentredString(*P(ESP32[0] + ESP32[2] / 2 - 2, ESP32[1] + ESP32[3] + 1.5), "RJ45 + USB-C end")
    c.setFont("Helvetica", 6.5)
    c.setFillGray(0)

    # ESP32 header pads 21-40
    c.setStrokeGray(0.5)
    c.setLineWidth(0.3)
    for n in range(21, 41):
        c.circle(*P(ESP_PAD_X, esp_pin_y(n)), R(0.5))

    # bus board: pads, row names, column names in the unused row C (no wire passes there)
    for y in BUS_ROWS:
        for x in BUS_COLS:
            c.circle(*P(x, y), R(0.55))
    c.setStrokeGray(0)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(*P(POWER[0] + POWER[2] / 2, POWER[1] + POWER[3] + 1.2), "TX / GND / 5V bus")
    c.setFont("Helvetica", 5)
    c.drawRightString(*P(POWER[0] - 0.6, BUS_ROWS[0] - 0.5), "TX row (1st)")
    c.drawRightString(*P(POWER[0] - 0.6, BUS_ROWS[1] - 0.5), "GND row (2nd)")
    c.drawRightString(*P(POWER[0] - 0.6, BUS_ROWS[3] - 0.5), "5V row (4th)")

    # wires, then the end labels
    routes = wiring_routes()
    def wire(col, pts):                  # white halo first, so crossings read as breaks
        for w, setcol in ((2.6, lambda: c.setStrokeGray(1)), (0.9, lambda: c.setStrokeColorRGB(*col))):
            setcol()
            c.setLineWidth(w)
            c.setLineJoin(1)
            p = c.beginPath()
            p.moveTo(*P(*pts[0]))
            for q in pts[1:]:
                p.lineTo(*P(*q))
            c.drawPath(p)

    for col, _, far, _, _ in routes:
        wire(col, far)
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillGray(0)

    # XIAOs: outline, pads, name (no wire crosses a board)
    xl, xr = WIRING_XIAO_X - XIAO_L / 2, WIRING_XIAO_X + XIAO_L / 2
    pad = [xr - 2.88 - k * 2.54 for k in range(7)]
    for i, yc in enumerate(XIAO_YS[:1]):     # one XIAO drawn: S1 and S2 are wired the same (note below it)
        c.setStrokeGray(0.4)
        c.setLineWidth(0.6)
        c.rect(*P(xl, yc - XIAO_W / 2), R(XIAO_L), R(XIAO_W))
        c.setLineWidth(0.3)
        for px in pad:
            c.circle(*P(px, yc + XIAO_ROW), R(0.5))
            c.circle(*P(px, yc - XIAO_ROW), R(0.5))
        c.setStrokeGray(0)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(*P(WIRING_XIAO_X + 2.0, yc + 3.3), f"S{i} XIAO")
        c.setFont("Helvetica", 5.5)
        c.drawRightString(*P(xr - 0.6, yc + 5.4), "USB-C")
        ix, iy = WIRING_XIAO_X - XIAO_IPEX[0], yc + XIAO_IPEX[1]     # IPEX4: two rings, not a pad
        c.setStrokeColorRGB(0.1, 0.3, 0.75)
        c.setLineWidth(0.8)
        c.circle(*P(ix, iy), R(1.1))
        c.setLineWidth(0.6)
        c.circle(*P(ix, iy), R(0.45))
        c.setFillColorRGB(0.1, 0.3, 0.75)
        c.drawString(*P(ix + 1.6, iy - 0.6), "IPEX4")
        c.setFillGray(0)
        c.setStrokeGray(0)

    for r, (col, xiao, _, _, _) in enumerate(routes):   # XIAO tails: S0 in full, S1 / S2 as stubs into their half
        if xiao:
            wire(col, xiao if r < 7 else xiao[-1:] and ((xiao[-1][0] - 4.0, xiao[-1][1]), xiao[-1]))
    c.setStrokeColorRGB(0, 0, 0)
    c.setFont("Helvetica-Oblique", 6)
    for i in (1, 2):
        (_, _), (jx, jy) = jst_halves(i)
        c.drawRightString(*P(jx + JST_HALF, jy + JST_W + 2.6), f"from S{i} XIAO,")
        c.drawRightString(*P(jx + JST_HALF, jy + JST_W + 0.8), "wired as S0")

    for i in range(3):                  # the two JST halves: far half in the strip, XIAO half off the USB end
        for (x0, y0), name in zip(jst_halves(i), ("far half", "XIAO half")):
            c.saveState()
            c.setFillGray(1)
            c.setFillAlpha(0.85)
            c.setStrokeGray(0.2)
            c.setLineWidth(0.7)
            c.rect(*P(x0, y0), R(JST_HALF), R(JST_W), fill=1)
            c.restoreState()
            c.setFont("Helvetica-Bold", 5.5)
            c.drawCentredString(*P(x0 + JST_HALF / 2, y0 + JST_W - 1.4), f"JST S{i}")
            c.setFont("Helvetica", 4.5)
            c.drawCentredString(*P(x0 + JST_HALF / 2, y0 + 0.6), name)
            c.setFont("Helvetica-Bold", 4.5)
            for n in range(1, 5):
                c.drawString(*P(x0 + 0.9, jst_pin_y(y0, n) - 0.5), str(n))
    for r, (col, xiao, far, _, _) in enumerate(routes):  # wire ends and JST pins on top
        c.setFillColorRGB(*col)
        for seg in (xiao if r < 7 else (xiao and xiao[-1:]), far):
            if seg:
                for q in (seg[0], seg[-1]):
                    c.circle(*P(*q), R(0.45), fill=1, stroke=0)
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 4.5)
    for x, t in zip(BUS_COLS, ("ESP", "S0", "S1", "S2")):
        c.setFillGray(1)
        c.rect(*P(x - 0.95, BUS_ROWS[2] - 0.75), R(1.9), R(1.5), fill=1, stroke=0)
        c.setFillGray(0)
        c.drawCentredString(*P(x, BUS_ROWS[2] - 0.45), t)

    def label(x, y, text, right=False):   # on a white patch so wires passing under it don't hide it
        w = c.stringWidth(text, "Helvetica", 5.5) / mm / sc
        x0 = x - w if right else x
        c.saveState()
        c.setFillGray(1)
        c.rect(*P(x0 - 0.3, y - 0.45), R(w + 0.6), R(1.75), fill=1, stroke=0)
        c.restoreState()
        (c.drawRightString if right else c.drawString)(*P(x, y), text)

    xiao_label_y = {YELLOW: 1.0, GREEN: -0.6, BLACK: -2.2, RED: -3.8}   # from each XIAO's centre line
    c.setFont("Helvetica", 5.5)
    k = 0
    for col, _, pts, xiao_end, esp_end in routes:
        c.setFillColorRGB(*col)
        if xiao_end:
            yc = XIAO_YS[k // 4]
            k += 1
            if k <= 4:                                 # S0 only
                label(xl + 0.8, yc + xiao_label_y[col], xiao_end)
        if esp_end:
            y = pts[0][1] if pts[0][0] == ESP_PAD_X else pts[-1][1]
            label(ESP_PAD_X - 1.0, y - 0.6, esp_end, right=True)
    c.setFillGray(0)

    same = [                                           # where S1 / S2's XIAOs would be
        ("Helvetica-Bold", "All three XIAOs are wired the same,"),
        ("Helvetica-Bold", "pad for pad, to their own JST:"),
        ("Helvetica-Bold", "5V (14) -> 1, GND (13) -> 2,"),
        ("Helvetica-Bold", "D6 TX (7) -> 3, D7 RX (8) -> 4."),
        ("Helvetica", ""),
        ("Helvetica", "Shared by every radio on the bus: 5V,"),
        ("Helvetica", "GND and the ESP32 TX (GPIO21) into"),
        ("Helvetica", "every D7. All radios hear the same"),
        ("Helvetica", "commands; each names one chip ID (or"),
        ("Helvetica", "all), and only the named radios act."),
        ("Helvetica", ""),
        ("Helvetica", "Only D6 TX differs: each radio talks"),
        ("Helvetica", "back on its own ESP32 RX pin, and"),
        ("Helvetica", "that pin is the sector. More radios ="),
        ("Helvetica", "one more JST pair, bus column and ESP"),
        ("Helvetica", "RX each. The ESP32-S3's 3 hardware"),
        ("Helvetica", "UARTs are all used: a 4th radio needs"),
        ("Helvetica", "another UART or a second gateway."),
    ]
    tx0, ty0 = WIRING_XIAO_X - XIAO_L / 2 - 2.0, XIAO_YS[0] - XIAO_W / 2 - 5.5
    for n, (font, t) in enumerate(same):
        c.setFont(font, 6.5)
        c.drawString(*P(tx0, ty0 - n * 1.75), t)

    c.setFont("Helvetica", 8.5)
    ny = oy + sc * vy0 - 9
    notes = [
        "D6 -> its own ESP RX (the pin is the sector): S0 GPIO17 (34), S1 GPIO16 (32), S2 GPIO18 (31).",
        "ESP TX GPIO21 (35) -> bus TX row -> every D7. Feed: TX (35) -> TX row, VBUS (40) -> 5V row, GND (38) -> GND row.",
        "Bus: hole end up, rows bridged, 3rd row spare. ESP32 as drawn (RJ45 side up): VBUS (40) is the top right header pin.",
    ]
    for n, s in enumerate(notes):
        c.drawString(15 * mm, (ny - n * 4.6) * mm, s)
    jst_head(c, 15, ny - 15)


def jst_head(c, x0, top):
    """The 4-pin JST head as wired: crimp (wire) side, key peg up, page mm from the top-left corner."""
    pitch, hw = 14.0, 4 * 14.0 + 4
    hy = top - 14                       # housing bottom edge
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0 * mm, top * mm, "JST head (either half), crimp side, key peg up:")
    c.setLineWidth(0.8)
    c.setStrokeGray(0)
    c.setFillGray(0.92)
    c.rect(x0 * mm, hy * mm, hw * mm, 6 * mm, fill=1)
    c.rect((x0 + hw / 2 - 4) * mm, (hy + 6) * mm, 8 * mm, 1.6 * mm, fill=1)   # key peg
    c.setFillGray(0)
    c.setFont("Helvetica", 6)
    c.drawCentredString((x0 + hw / 2) * mm, (hy + 8.4) * mm, "key peg")
    for n, (col, name, xiao) in enumerate(JST_PINS):
        x = x0 + 2 + pitch / 2 + n * pitch
        c.setFillGray(1)
        c.circle(x * mm, (hy + 3) * mm, 1.5 * mm, fill=1)
        c.setFillGray(0)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(x * mm, (hy + 2.25) * mm, str(n + 1))
        c.setStrokeColorRGB(*col)
        c.setLineWidth(3)
        c.line(x * mm, hy * mm, x * mm, (hy - 7) * mm)
        c.setStrokeGray(0)
        c.setLineWidth(0.8)
        c.setFillColorRGB(*col)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(x * mm, (hy - 10) * mm, name)
        c.setFillGray(0)
        c.setFont("Helvetica", 6.5)
        net, pin = xiao.split(" (")
        c.drawCentredString(x * mm, (hy - 13.5) * mm, net)
        c.drawCentredString(x * mm, (hy - 16.5) * mm, "XIAO " + pin.rstrip(")"))
    tx = x0 + hw + 7
    c.setFont("Helvetica", 8.5)
    for n, s in enumerate((
        "Pins left to right: 1 red 5V, 2 black GND, 3 yellow D6 TX, 4 green D7 RX.",
        "Male and female halves carry the same colours in the same order on the crimp side,",
        "so the XIAO tail and the far tail match colour for colour through the joint.",
        "XIAO tail: red -> 5V (14), black -> GND (13), yellow -> D6 (7), green -> D7 (8).",
        "Far tail: red -> bus 5V row, black -> bus GND row, green -> bus TX row, yellow -> that",
        "sector's ESP RX pin (labels on the drawing). Female half on the far tail keeps 5V covered.",
    )):
        c.drawString(tx * mm, (top - 7 - n * 4) * mm, s)


# Alternative split plate (2026-10-31; faces swapped 2026-11-10, user): no pigtail hole. The three XIAOs sit on the
# TOP face, each IPEX4 end on a flat run to an adhesive HS-100 tie mount (12.5 mm square) that clamps the pigtail
# before it goes down its own antenna hole to its deck jack. ESP32 and bus board hang on the UNDERSIDE (deck side,
# in the ~25 mm spacer gap); the PoE splitter goes in a 4" round electrical box (1" hole), fed by a 90 deg adapter
# on the ESP32's RJ45. Each XIAO's 4-wire tail goes down through its own harness hole to the JST pair underneath. Same plate frame as above: 12 o'clock up, M4 bolts unchanged.
# Layout (user, 2026-10-31): S0 parallel to the ESP32, S1 / S2 are S0 turned -120 / +120 deg about the plate
# centre, so each radio sits the same way to its own deck jacks and bolts. Positions fine-tuned by search: each
# XIAO is held by VHB plus one zip tie across it, its tie holes and the strap's run over the top face stay clear
# of the ESP32 and bus board, the ESP32's straps under the plate miss the XIAOs, holes stay 3 mm inside the rim,
# and the underside keeps clear of the deck's centre hole into the core.


ALT_XIAOS = (ALT_S0, ALT_S1, ALT_S2)   # S0-S2: centre x, y and angle of the IPEX4 end




def alt_quad(cx, cy, hl, hw, a):
    ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
    return [(cx + sx * hl * ux - sy * hw * uy, cy + sx * hl * uy + sy * hw * ux)
            for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]


def alt_xiao(cx, cy, a, tie_s=0.0):
    """Board outline, IPEX4 point, tie mount outline, USB-end point, harness hole, tie holes for one XIAO."""
    ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
    along, side = XIAO_IPEX
    ipex = (cx + along * ux - side * uy, cy + along * uy + side * ux)
    mount = alt_quad(cx + ALT_MOUNT * ux - side * uy, cy + ALT_MOUNT * uy + side * ux,
                     ALT_MOUNT_SIDE / 2, ALT_MOUNT_SIDE / 2, a)
    usb = (cx - (XIAO_L / 2 - 2.5) * ux, cy - (XIAO_L / 2 - 2.5) * uy)
    harness = (cx - ALT_HARNESS_S * ux, cy - ALT_HARNESS_S * uy)
    o = XIAO_W / 2 + TIE_CLEAR
    ties = [(cx + tie_s * ux - k * o * uy, cy + tie_s * uy + k * o * ux) for k in (-1, 1)]
    return alt_quad(cx, cy, XIAO_L / 2, XIAO_W / 2, a), ipex, mount, usb, harness, ties


def alt_at(cx, cy, a, s, n=0.0):
    """Point s along and n left of a part's axis (angle a) from its centre."""
    ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
    return cx + s * ux - n * uy, cy + s * uy + n * ux


def alt_plate_holes():
    out = plate_antenna_holes() + [(PLATE_M3, *alt_at(*ALT_BUS, ALT_BUS_ANGLE, ALT_BUS_HOLE_S), "power")]
    for v in g.VERTICES:
        a = math.radians(v + PLATE_TURN)
        out.append((PLATE_M4, g.MOUNT_RADIUS * math.sin(a), g.MOUNT_RADIUS * math.cos(a), "M4"))
    for i, (x, tie_s) in enumerate(zip(ALT_XIAOS, ALT_XIAO_TIE_S)):
        *_, harness, ties = alt_xiao(*x, tie_s)
        out += [(TIE_HOLE, tx, ty, f"S{i} tie") for tx, ty in ties]
    for ts in ALT_ESP32_TIES:
        for sy in (-1, 1):
            out.append((TIE_HOLE, *alt_at(*ALT_ESP32, ALT_ESP32_ANGLE, ts, sy * (ESP32[2] / 2 + TIE_CLEAR)), "tie"))
    return out


def alt_plate_page(c):
    ox, oy = PAGE_W / mm / 2, 140

    def P(x, y):
        return (x + ox) * mm, (y + oy) * mm

    def poly(pts, fill=0):
        p = c.beginPath()
        p.moveTo(*P(*pts[0]))
        for q in pts[1:]:
            p.lineTo(*P(*q))
        p.close()
        c.drawPath(p, fill=fill)

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm,
                 f"ALT electronics plate (split) - {PLATE_DIAMETER:g} mm disc - PRINT AT 100% (Actual size)")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Viewed from the TOP. Radios, tie mounts, ESP32 + bus all hang UNDER the plate (dashed, seen through it).")
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.75, 0.1, 0.1)
    c.drawString(15 * mm, (PAGE_H / mm - 26) * mm,
                 "This layout is only a suggestion. Lay out your own parts and check every hole before drilling.")
    c.setFillGray(0)
    scale_bar(c, 15, PAGE_H / mm - 32)

    c.setLineWidth(0.8)
    c.circle(*P(0, 0), PLATE_DIAMETER / 2 * mm)
    c.setLineWidth(0.3)
    crosshair(c, ox, oy, 4)

    # deck jacks below the plate (not drilled here): the hanging radios and coax keep clear of them
    c.setStrokeGray(0.65)
    c.setFillGray(0.55)
    c.setFont("Helvetica", 5.5)
    c.setDash(0.6, 1.2)
    letters = {"duck/monopole": "D", "patch": "P", "patch end": "P2", "dipole coax": "C"}
    turn = math.radians(PLATE_TURN)
    for d, x, y, lab in g.holes:
        if lab in ("via", "M4 mount", "core feed") or d == 6.5:   # 6.5 mm jacks are drawn below (dotted, reference)
            continue
        dx, dy = x - g.CX, y - g.CY
        px, py = dx * math.cos(turn) + dy * math.sin(turn), -dx * math.sin(turn) + dy * math.cos(turn)
        c.circle(*P(px, py), ALT_DECK_JACK / 2 * mm)
        c.drawCentredString(*P(px, py - 1), f"{lab[:2]} {letters[lab.split(' ', 1)[1]]}")
    c.circle(*P(0, 0), ALT_CORE_HOLE / 2 * mm)
    c.drawCentredString(*P(0, -ALT_CORE_HOLE / 2 + 2), "deck centre 10 mm")
    c.setDash()

    # underside: ESP32 and bus board (dashed, seen through the plate)
    c.setStrokeGray(0.45)
    c.setFillGray(0.35)
    c.setLineWidth(0.4)
    for (px, py), ang, draw in ((ALT_ESP32, ALT_ESP32_ANGLE, "esp"), (ALT_BUS, ALT_BUS_ANGLE, "bus")):
        c.saveState()                                             # drawn in each part's own frame
        c.translate(*P(px, py))
        c.rotate(ang)
        c.setDash(2, 1.5)
        if draw == "esp":
            L, W = ESP32[3] * mm, ESP32[2] * mm
            c.rect(-L / 2, -W / 2, L, W)
            c.setDash()
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(-6 * mm, -1 * mm, "ESP32-S3-ETH (under)")
            c.setFont("Helvetica", 6)
            c.drawRightString(25 * mm, 1.5 * mm, "RJ45 end, down")      # left of the RJ45-end strap
            c.drawRightString(25 * mm, -3.5 * mm, "VBUS (40) this end")
            c.drawCentredString(2 * mm, W / 2 - 3.2 * mm, "header 21-40 this edge")
        else:
            w, h = POWER[3] * mm, POWER[2] * mm
            c.rect(-w / 2, -h / 2, w, h)
            c.setDash()
            c.drawCentredString(-2 * mm, -1 * mm, "bus (under)")
        c.restoreState()
    c.setStrokeGray(0.6)                     # the ESP32's zip ties: straps across the top face, hole to hole
    c.setLineWidth(1.2)
    for ts in ALT_ESP32_TIES:
        c.line(*P(*alt_at(*ALT_ESP32, ALT_ESP32_ANGLE, ts, -(ESP32[2] / 2 + TIE_CLEAR))),
               *P(*alt_at(*ALT_ESP32, ALT_ESP32_ANGLE, ts, ESP32[2] / 2 + TIE_CLEAR)))
    c.setStrokeGray(0)
    c.setFillGray(0)

    # underside too: XIAOs, IPEX4 dots, tie mounts, coax runs down to the jacks below
    ants = {tag.split()[0]: [] for _, _, _, tag in plate_antenna_holes()}
    for _, hx, hy, tag in plate_antenna_holes():
        ants[tag.split()[0]].append((hx, hy))
    for i, (cx, cy, a) in enumerate(ALT_XIAOS):
        board, ipex, mount, usb, _, ties = alt_xiao(cx, cy, a, ALT_XIAO_TIE_S[i])
        mx = sum(p[0] for p in mount) / 4
        my = sum(p[1] for p in mount) / 4
        c.setStrokeColorRGB(0.9, 0.55, 0.1)       # coax options: mount -> each of its sector's antenna holes
        c.setLineWidth(0.6)
        c.setDash(1.5, 1)
        for hx, hy in ants[f"S{i}"]:
            c.line(*P(mx, my), *P(hx, hy))
        c.setDash()
        c.setStrokeGray(0.35)                # under the plate: dashed
        c.setLineWidth(0.5)
        c.setDash(2, 1.5)
        poly(board)
        c.setFillGray(0.88)
        poly(mount, fill=1)
        c.setDash()
        c.setStrokeGray(0.6)                 # its zip tie: strap round the board, across the top, through both holes
        c.setLineWidth(1.2)
        c.line(*P(*ties[0]), *P(*ties[1]))
        c.setFillGray(0)
        c.circle(*P(*ipex), 0.9 * mm, fill=1, stroke=0)
        c.setStrokeColorRGB(0.9, 0.55, 0.1)
        c.setLineWidth(1.6)
        c.line(*P(*ipex), *P(mx, my))
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(*P(cx, cy - 1.5), f"S{i}")
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(*P(mx, my - 0.8), "mount")
    c.setStrokeGray(0)
    c.setFillGray(0)

    holes = alt_plate_holes()
    for d, x, y, tag in holes:
        if tag.endswith(" ant"):               # antenna holes: dotted, for reference only (not by design)
            c.setDash(0.6, 1.2)
        c.setLineWidth(0.5)
        c.circle(*P(x, y), d / 2 * mm)
        c.setLineWidth(0.2)
        crosshair(c, x + ox, y + oy, d / 2)
        c.setDash()
        c.setFont("Helvetica-Bold", 7)
        if tag == "M4":                        # outward from the centre, clear of the parts
            r = math.hypot(x, y)
            c.drawCentredString(*P(x * (r + 8) / r, y * (r + 8) / r - 1), f"M4 {d:g}")
        elif tag.endswith("harness"):          # labelled toward the plate centre
            c.setFont("Helvetica", 6)
            k = 1 - (d / 2 + 5) / math.hypot(x, y)    # lands on the USB-C end of the board
            c.drawCentredString(*P(x * k, y * k - 1), f"{tag.split()[0]} wires {d:g}")
        elif tag.endswith(" ant"):             # antenna jack holes: name + size, above
            c.setFont("Helvetica", 6)
            c.drawCentredString(*P(x, ant_label_y(x, y, d, holes)), f"{tag[:-4]} {d:g} ref")
        elif tag.endswith("tie"):              # every tie hole: its size just outward of it
            c.setFont("Helvetica", 5.5)
            r = math.hypot(x, y)
            k = (r + d / 2 + 3.2) / r
            c.drawCentredString(*P(x * k, y * k - 0.8), f"tie {d:g}")
        elif tag == "power":
            c.setFont("Helvetica", 5.5)
            c.drawString(*P(x + d / 2 + 0.5, y + d / 2), f"M3 {d:g}")

    c.setFont("Helvetica", 8.5)
    notes = [
        "Hanging from the ceiling, top down: enclosure top, this module plate, everything else under it, deck, core.",
        f"Drill: 3 x {PLATE_M4:g} mm (M4) bolts to the deck, on the deck's M4 holes; {PLATE_M3:g} mm (M3) bus board. No harness holes.",
        f"Tie hole pairs {TIE_HOLE:g} mm (any 3.0-{TIE_HOLE:g} mm fits a 2.5 mm tie): one across each XIAO, two across the ESP32.",
        "Antenna holes (dotted, 9 x 6.5 mm): the deck's D / P / P2 jacks, shown for reference only. Not by design; drill if you like.",
        "XIAOs (in the gaps between the sectors' holes) on VHB + a zip tie (grey bar), IPEX4 dot -> orange coax -> 1/2\" HS-100",
        "tie mount, which clamps it, then on (dashed orange) to its own sector's D / P / P2 jack in use: one smooth sweep, bending",
        "down through the spacer gap. Nothing sits within 8 mm of an antenna hole (the coax rises straight from its jack).",
        "ESP32: across the middle, RJ45 / USB-C end toward 10 o'clock, hung RJ45 side down; USB-C then faces the plate: standoffs or a",
        "slim right-angle plug. A 90 deg adapter turns the RJ45 sideways; patch + USB-C lead to the PoE splitter's 4\" box.",
        "Bus by the ESP32's RJ45 end (VBUS 40). Spacers 25-30 mm. Clearances are tight (~2-3 mm): check with the real parts.",
        "Positions: parameters.csv (lay out in plate_layout.svg). The ESP32 only clears the deck's 10 mm centre hole: no hole saw.",
        "OPTIONS (builder's choice): this alt split plate or the pipe plate (page 3). Wiring: page 6.",
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (61 - n * 3.9) * mm, t)
    scale_bar(c, 15, 12)


# Pipe plate (2026-11-01, called the flange plate until the flange was dropped 2026-11-09): the PoE splitter and
# ESP32 hang inside the core on a 1/2" pipe whose male adapter is clamped through the plate's centre (adapter_trace),
# so the plate carries only the three XIAOs and the bus board, on top, in the ring between the nut and the rim. Each XIAO sits beside its own sector axis (FL_XIAO_DA, clear of the antenna holes), between the M4 bolts, long axis
# turned FL_XIAO_ROT off radial (nearly along the rim since P2 moved in, 2026-11-10). No pigtail hole (user, 2026-11-10): the coax runs flat from
# IPEX4 to a 1/2" (12.5 mm) HS-100 adhesive tie mount past the IPEX4 end, then down its sector's nearest antenna
# hole to the deck jack. 5V / GND / D7 run over the top to the bus board; D6 runs over the top to the feed hole and
# down it to its ESP32 RX pin in the core, beside TX, GND and VBUS coming up to the bus. The pipe carries the ESP antenna's
# pigtail and is capped (stack views), so the PoE cable passes the plate rim instead.
FL_UNDER_SIDE = -FL_IPEX_SIDE  # the XIAOs hang component side down under the plate (user, 2026-11-10), so seen
                               # from the top through the plate the IPEX4 is on the other side
# No feed hole since 2026-11-10: the bus is under the plate, so TX, GND, VBUS and the three D6 pass the deck's
# 2-1/4" centre hole between the core and the bus without crossing the plate.


def clock(r, a):
    return r * math.sin(math.radians(a)), r * math.cos(math.radians(a))


def fl_xiaos():
    """Centre, angle of the IPEX4 end (inward, maths convention) and clock angle for S0-S2."""
    out = []
    for s in g.SECTORS:
        a = s + PLATE_TURN + FL_XIAO_DA             # each XIAO beside its own sector axis (bolts at the corners)
        cx, cy = clock(FL_XIAO_R, a)
        out.append((cx, cy, math.degrees(math.atan2(-cy, -cx)) + FL_XIAO_ROT, a))
    return out


def ant_label_y(x, y, d, holes):
    """Antenna hole label above the hole, or below it when another hole sits on the label."""
    up = y + d / 2 + 3.2
    if any(abs(hx - x) < 8 and 0 < hy - y < d / 2 + 6 + hd / 2 for hd, hx, hy, _ in holes):
        return y - d / 2 - 4.6
    return up


def plate_antenna_holes():
    """The deck's 6.5 mm antenna jack holes (D, P, P2) in the plate frame, drawn dotted on both plates for reference
    so deck, plate and every page line up; they can be drilled but are not by design (user, 2026-11-10)."""
    letters = {"duck/monopole": "D", "patch": "P", "patch end": "P2"}
    turn = math.radians(PLATE_TURN)
    out = []
    for d, x, y, lab in g.holes:
        sector, kind = lab.split(" ", 1) if " " in lab else (lab, "")
        if kind not in letters:
            continue
        dx, dy = x - g.CX, y - g.CY
        out.append((d, dx * math.cos(turn) + dy * math.sin(turn), -dx * math.sin(turn) + dy * math.cos(turn),
                    f"{sector} {letters[kind]} ant"))
    return out


def fl_plate_holes():
    out = plate_antenna_holes()
    for v in g.VERTICES:
        a = math.radians(v + PLATE_TURN)
        out.append((PLATE_M4, g.MOUNT_RADIUS * math.sin(a), g.MOUNT_RADIUS * math.cos(a), "M4"))
    for i, (cx, cy, a, _) in enumerate(fl_xiaos()):
        *_, ties = alt_xiao(cx, cy, a, FL_TIE_S)
        out += [(TIE_HOLE, x, y, f"S{i} tie") for x, y in ties]
    bx, by = clock(FL_BUS[1], FL_BUS[0])
    out.append((PLATE_M3, *alt_at(bx, by, 90 - FL_BUS[0], ALT_BUS_HOLE_S), "power"))
    return out


def fl_plate_page(c):
    ox, oy = PAGE_W / mm / 2, 140

    def P(x, y):
        return (x + ox) * mm, (y + oy) * mm

    def poly(pts):
        p = c.beginPath()
        p.moveTo(*P(*pts[0]))
        for q in pts[1:]:
            p.lineTo(*P(*q))
        p.close()
        c.drawPath(p)

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm,
                 f"PIPE electronics plate - {PLATE_DIAMETER:g} mm disc - PRINT AT 100% (Actual size)")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Viewed from the TOP. XIAOs, mounts + bus hang UNDER the plate (dashed); PoE splitter + ESP32 inside the core.")
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.75, 0.1, 0.1)
    c.drawString(15 * mm, (PAGE_H / mm - 26) * mm,
                 "This layout is only a suggestion. Lay out your own parts and check every hole before drilling.")
    c.setFillGray(0)
    scale_bar(c, 15, PAGE_H / mm - 32)

    c.setLineWidth(0.8)
    c.circle(*P(0, 0), PLATE_DIAMETER / 2 * mm)
    c.setLineWidth(0.3)
    crosshair(c, ox, oy, 4)
    adapter_trace(c, P, ox, oy)

    c.setLineWidth(0.4)
    ants = {}
    for _, hx, hy, tag in plate_antenna_holes():
        ants.setdefault(tag.split()[0], []).append((hx, hy))
    for i, (cx, cy, a, ca) in enumerate(fl_xiaos()):
        board, ipex, *_, ties = alt_xiao(cx, cy, a, FL_TIE_S)
        ix, iy = alt_at(cx, cy, a, XIAO_IPEX[0], FL_UNDER_SIDE * XIAO_IPEX[1])
        mx, my = alt_at(cx, cy, a, ALT_MOUNT, FL_UNDER_SIDE * XIAO_IPEX[1])     # 1/2" tie mount past the IPEX4 end
        c.setStrokeColorRGB(0.9, 0.55, 0.1)       # coax options: mount -> each of its sector's antenna holes
        c.setLineWidth(0.6)
        c.setDash(1.5, 1)
        for hx, hy in ants[f"S{i}"]:
            c.line(*P(mx, my), *P(hx, hy))
        c.setDash()
        c.setStrokeGray(0.35)
        c.setLineWidth(0.4)
        c.setDash(2, 1.5)
        c.setFillGray(0.88)
        p_ = c.beginPath()
        mq = alt_quad(mx, my, ALT_MOUNT_SIDE / 2, ALT_MOUNT_SIDE / 2, a)
        p_.moveTo(*P(*mq[0]))
        for q in mq[1:]:
            p_.lineTo(*P(*q))
        p_.close()
        c.drawPath(p_, fill=1)
        c.setDash()
        c.setFillGray(0)
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(*P(mx, my - 0.8), "mount")
        c.setStrokeColorRGB(0.9, 0.55, 0.1)
        c.setLineWidth(1.6)
        c.line(*P(ix, iy), *P(mx, my))
        c.setStrokeGray(0.35)
        c.setLineWidth(0.4)
        c.setDash(2, 1.5)
        poly(board)
        c.setDash()
        c.setStrokeGray(0.6)                 # its zip tie: strap round the board, through both holes
        c.setLineWidth(1.2)
        c.line(*P(*ties[0]), *P(*ties[1]))
        c.setStrokeGray(0)
        c.setLineWidth(0.4)
        ix, iy = alt_at(cx, cy, a, XIAO_IPEX[0], FL_UNDER_SIDE * XIAO_IPEX[1])
        c.circle(*P(ix, iy), 0.9 * mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(*P(*alt_at(cx, cy, a, -1, 0)), f"S{i}")
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(*P(*alt_at(cx, cy, a, -7.5, 0)), "USB")
        c.drawCentredString(*P(*alt_at(cx, cy, a, XIAO_IPEX[0] - 2.2, FL_UNDER_SIDE * XIAO_IPEX[1])), "IPEX4")
    bx, by = clock(FL_BUS[1], FL_BUS[0])
    c.saveState()
    c.translate(*P(bx, by))
    c.rotate(90 - FL_BUS[0])
    c.setStrokeGray(0.35)
    c.setDash(2, 1.5)
    c.rect(-POWER[3] / 2 * mm, -POWER[2] / 2 * mm, POWER[3] * mm, POWER[2] * mm)
    c.setDash()
    c.setStrokeGray(0)
    c.setFont("Helvetica", 6)
    c.drawCentredString(-3 * mm, -1 * mm, "bus (under)")
    c.restoreState()

    holes = fl_plate_holes()
    for d, x, y, tag in holes:
        if tag.endswith(" ant"):               # antenna holes: dotted, for reference only (not by design)
            c.setDash(0.6, 1.2)
        c.setLineWidth(0.5)
        c.circle(*P(x, y), d / 2 * mm)
        c.setLineWidth(0.2)
        crosshair(c, x + ox, y + oy, d / 2)
        c.setDash()
        c.setFont("Helvetica-Bold", 7)
        r = math.hypot(x, y)
        if tag == "M4":
            c.drawCentredString(*P(x * (r + 8) / r, y * (r + 8) / r - 1), f"M4 {d:g}")
        elif tag.endswith(" ant"):             # antenna jack holes: name + size, above
            c.setFont("Helvetica", 6)
            c.drawCentredString(*P(x, ant_label_y(x, y, d, holes)), f"{tag[:-4]} {d:g} ref")
        elif tag.endswith("tie"):                     # every tie hole: its size beside it
            c.setFont("Helvetica", 5.5)
            c.drawString(*P(x + d / 2 + 0.5, y + d / 2), f"tie {d:g}")
        elif tag == "power":
            c.setFont("Helvetica", 5.5)
            c.drawString(*P(x + d / 2 + 0.5, y + d / 2), f"M3 {d:g}")

    c.setFont("Helvetica", 8.5)
    notes = [
        "Hanging from the ceiling, top down: nut, enclosure top, this module plate, modules + wiring under it, deck, core.",
        f"Drill: 3 x {PLATE_M4:g} mm (M4) bolts to the deck, on the deck's M4 holes; {PLATE_M3:g} mm (M3) bus board;",
        f"tie hole pairs {TIE_HOLE:g} mm (3.0-{TIE_HOLE:g} fits a 2.5 mm tie), one per XIAO. No pigtail or feed holes: the parts hang under the plate.",
        "Antenna holes (dotted, 9 x 6.5 mm): the deck's D / P / P2 jacks, shown for reference only. Not by design; drill if you like.",
        f"Centre (blue): {ADAPTER_HOLE:g} mm (7/8\") hole for the 1/2\" male adapter's thread, which also goes through the",
        "enclosure top; the nut on top (dashed, size est.) clamps both. Ethernet comes down the pipe (page 5).",
        "EU: a 20 mm x 1/2\" BSP male adaptor (R 1/2, 21 mm thread) fits the same 22 mm hole, held by a 1/2\" BSP backnut.",
        "Each XIAO (under the plate, component side down, beside its own sector): IPEX4 dot -> orange flat coax run ->",
        "1/2\" HS-100 tie mount (grey), which clamps it, then (dashed orange) down to whichever of its sector's D / P / P2",
        "jacks is in use, straight below its hole. 5V, GND, D7 to the bus beside them; D6 through the deck's centre hole to",
        "its ESP32 RX pin, beside TX, GND, VBUS coming up. Seen from the top the IPEX4 is on the left (the board is flipped).",
        "OPTIONS (builder's choice): this pipe plate or the alt split plate (page 2); bus board under the plate by the adapter,",
        "or on the pipe inside the core (page 5: then skip the bus M3).",
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (59 - n * 3.4) * mm, t)
    scale_bar(c, 15, 9)


# Stack views for the pipe plate (2026-11-01; flange replaced 2026-11-09): a 1/2" PVC male adapter's thread goes up
# through the enclosure bottom and the plate, a nut on top clamping both; the 1/2" PVC pipe in its socket runs through
# the deck's 2-1/4" centre hole the full height of the core and is capped flush with the core's far end. The cap
# is drilled and tapped for the ESP32 antenna's RP-SMA bulkhead (threaded straight in, no nut) and notched at its
# rim so the U.FL pigtail from the board gets inside (user, 2026-11-09). The antenna screwed onto the bulkhead
# clamps the copper end plate that closes the core (optional, shape not final, must leave access). The PoE splitter and ESP32
# hang on the pipe toward two of the core's corners, where the triangle is widest; the third corner is left for the
# antenna pigtail and cables. Drawn to scale (STACK_SCALE), not a drilling template; adapter, nut, splitter, board depths
# and the antenna are estimates.


def stack_page(c):
    k = STACK_SCALE
    tx, ty = 55.0, 178.0                       # top view centre (page mm)
    sx, sy = 140.0, PAGE_H / mm - 52           # side view: plate top surface

    def T(x, y):
        return (tx + x * k) * mm, (ty + y * k) * mm

    def S(x, z):
        return (sx + x * k) * mm, (sy + z * k) * mm

    def rect(F, x0, y0, x1, y1, dash=None, fill=None):
        if dash:
            c.setDash(*dash)
        (a, b), (p, q) = F(x0, y0), F(x1, y1)
        if fill is not None:
            c.setFillGray(fill)
        c.rect(min(a, p), min(b, q), abs(p - a), abs(q - b), fill=fill is not None)
        c.setFillGray(0)
        c.setDash()

    def label(F, x, y, s, size=6, anchor="c"):
        c.setFont("Helvetica", size)
        {"c": c.drawCentredString, "l": c.drawString, "r": c.drawRightString}[anchor](*F(x, y), s)

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm, "Pipe stack - top and side views - scale 0.6 (NOT a drilling template)")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Hanging from the ceiling, top down: nut, enclosure top, module plate, modules, deck, core, ESP antenna. Frame: page 3.")

    # ---- top view: a cut through the core below the deck, looking down ----
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(tx * mm, (ty + 54) * mm, "TOP: inside the core, looking down")
    tri_o = [clock(g.CIRCUMRADIUS, v + PLATE_TURN) for v in g.VERTICES]
    tri_i = [clock(2 * (g.INRADIUS - g.FACE_THICK), v + PLATE_TURN) for v in g.VERTICES]
    for pts, w in ((tri_o, 1.0), (tri_i, 0.3)):
        c.setLineWidth(w)
        p = c.beginPath()
        p.moveTo(*T(*pts[0]))
        for q in pts[1:]:
            p.lineTo(*T(*q))
        p.close()
        c.drawPath(p)
    c.setLineWidth(0.3)
    c.setDash(1, 1.5)
    c.circle(*T(0, 0), ADP_HEX_W / 2 * k * mm)                 # adapter hex, above the deck
    c.circle(*T(0, 0), PIPE_SAW / 2 * k * mm)               # deck centre hole
    c.setDash()
    c.circle(*T(0, 0), PIPE_OD / 2 * k * mm)
    c.circle(*T(0, 0), PIPE_ID / 2 * k * mm)
    hr = g.NUT_AF / math.sqrt(3)
    c.setDash(1, 1)
    for v in g.VERTICES:                                       # M4 nuts in the corners, under the deck
        nx, ny = clock(g.MOUNT_RADIUS, v + PLATE_TURN)
        hexa = [T(nx + hr * math.sin(math.radians(a)), ny + hr * math.cos(math.radians(a))) for a in range(30, 390, 60)]
        p = c.beginPath()
        p.moveTo(*hexa[0])
        for q in hexa[1:]:
            p.lineTo(*q)
        p.close()
        c.drawPath(p)
    c.setDash()
    for ang, depth, half, name in ((ESP_CLOCK, ESP_DEPTH, ESP32[2] / 2, "ESP32"),
                                   (SPL_CLOCK, SPL_DEPTH, SPLITTER[2] / 2, "PoE")):
        r0 = PIPE_OD / 2 + BOARD_OFF
        ux, uy = clock(1, ang)
        vx, vy = uy, -ux
        quad = [(ux * r + vx * t, uy * r + vy * t) for r, t in ((r0, -half), (r0 + depth, -half),
                                                                (r0 + depth, half), (r0, half))]
        c.setFillGray(0.85)
        p = c.beginPath()
        p.moveTo(*T(*quad[0]))
        for q in quad[1:]:
            p.lineTo(*T(*q))
        p.close()
        c.drawPath(p, fill=1)
        c.setFillGray(0)
        label(T, ux * (r0 + depth + 7), uy * (r0 + depth + 7) - 1, name, 6.5)
    r0 = PIPE_OD / 2 + BOARD_OFF                               # option: bus board on the pipe (dashed)
    ux, uy = clock(1, BUS_CLOCK)
    vx, vy = uy, -ux
    half = POWER[2] / 2
    quad = [(ux * r + vx * t, uy * r + vy * t) for r, t in ((r0, -half), (r0 + BUS_DEPTH, -half),
                                                            (r0 + BUS_DEPTH, half), (r0, half))]
    c.setDash(1.5, 1)
    p = c.beginPath()
    p.moveTo(*T(*quad[0]))
    for q in quad[1:]:
        p.lineTo(*T(*q))
    p.close()
    c.drawPath(p)
    c.setDash()
    label(T, ux * (r0 + BUS_DEPTH + 9) + 7, uy * (r0 + BUS_DEPTH + 9) - 3, "bus (option)", 5.5)
    for i, s in enumerate(g.SECTORS):
        label(T, *clock(g.INRADIUS + 9, s + PLATE_TURN), f"S{i} face", 6)
    fx, fy = clock(46, 330.0)
    label(T, fx, fy, "11 o'clock corner:", 5.5)
    label(T, fx, fy - 4, "cables (+ bus option)", 5.5)
    c.setFont("Helvetica", 5.5)
    for n, t in enumerate(["dotted: adapter hex (above the deck)", "and the 2-1/4\" deck hole;",
                           "dotted hexes: M4 nuts under the deck"]):
        c.drawString((tx - 45) * mm, (ty - 50 - n * 3) * mm, t)

    # ---- side view: a cut through the centre along 3 o'clock - 9 o'clock ----
    zd = -(ENC_T + PLATE_T + SPACER)           # deck top
    zc = zd - DECK_T - FACE_H                  # core far end
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(sx * mm, (sy + 10) * mm, "SIDE: cut through 3 - 9 o'clock")
    c.setLineWidth(0.6)
    rect(S, -g.R - 6, 0, g.R + 6, -ENC_T, fill=0.75)                          # enclosure top (hanging)
    label(S, -g.R - 7, -2, "enclosure top", 5.5, "r")
    rect(S, -PLATE_DIAMETER / 2, -ENC_T, PLATE_DIAMETER / 2, -ENC_T - PLATE_T, fill=0.92)   # module plate under it
    label(S, -PLATE_DIAMETER / 2 - 1, -ENC_T - PLATE_T - 1.5, "module plate", 5.5, "r")
    zx = -ENC_T - PLATE_T                                                    # S2 XIAO hangs under the plate,
    c.rect(*S(-FL_XIAO_R - XIAO_L / 2, zx - 3.5), XIAO_L * k * mm, 3.5 * k * mm)   # between the plates (user,
    label(S, -FL_XIAO_R, zx - 9, "S2 XIAO (under the plate)", 5.5)            # 2026-11-10)
    hole = PIPE_SAW / 2
    rect(S, -g.R, zd, -hole, zd - DECK_T, fill=0.6)
    rect(S, hole, zd, g.R, zd - DECK_T, fill=0.6)
    label(S, -g.R + 1, zd + 2, "deck", 5.5, "l")
    rect(S, -NUT_OD / 2, 0, NUT_OD / 2, NUT_H, fill=0.4)                     # nut on top
    label(S, -NUT_OD / 2 - 1, NUT_H / 2 - 1, "nut", 5.5, "r")
    za = -PLATE_T - ENC_T                                                    # adapter shoulder
    rect(S, -ADP_HEX_W / 2, za, ADP_HEX_W / 2, za - ADP_HEX_H, fill=0.8)
    rect(S, -ADP_SOCK_OD / 2, za - ADP_HEX_H, ADP_SOCK_OD / 2, za - ADP_HEX_H - ADP_SOCK_H, fill=0.8)
    label(S, ADP_SOCK_OD / 2 + 1, za - ADP_HEX_H - 8, "1/2\" male adapter", 5.5, "l")
    # M4 bolt at 3 o'clock: spacer, bolt, nut in the corner under the deck
    rect(S, g.MOUNT_RADIUS - 4, -ENC_T - PLATE_T, g.MOUNT_RADIUS + 4, zd)
    c.setLineWidth(0.3)
    c.line(*S(g.MOUNT_RADIUS, 1.5), *S(g.MOUNT_RADIUS, zd - DECK_T - 3.2))
    rect(S, g.MOUNT_RADIUS - g.NUT_AF / 2, zd - DECK_T, g.MOUNT_RADIUS + g.NUT_AF / 2, zd - DECK_T - 3.2, fill=0.4)
    label(S, g.MOUNT_RADIUS + 5, zd + 5, "M4 + spacer", 5.5, "l")
    # core: the S2 face on the left, the corner between S0 and S1 on the right
    for x0, x1 in ((-g.INRADIUS, -g.INRADIUS + g.FACE_THICK), (2 * (g.INRADIUS - g.FACE_THICK), g.CIRCUMRADIUS)):
        rect(S, x0, zd - DECK_T, x1, zc, fill=0.55)
    label(S, -g.INRADIUS - 2, zd - 40, "S2 face", 5.5, "r")
    label(S, g.CIRCUMRADIUS + 2, zd - 40, "corner", 5.5, "l")
    c.setLineWidth(1.4)
    c.setDash(3, 2)
    c.line(*S(-g.INRADIUS + g.FACE_THICK, zc), *S(2 * (g.INRADIUS - g.FACE_THICK), zc))
    c.setDash()
    label(S, 25, zc - 5, "copper end plate (optional): bond all 3 edges or leave it off", 5.5, "l")
    # pipe, cap, antenna
    c.setLineWidth(0.5)
    rect(S, -PIPE_OD / 2, za - ADP_HEX_H - ADP_SOCK_H, PIPE_OD / 2, zc + CAP_H - 3)
    rect(S, -CAP_OD / 2, zc + CAP_H, CAP_OD / 2, zc, fill=0.8)
    c.setFillGray(1)                           # pigtail notch in the cap rim, ESP32 side
    c.rect(*S(CAP_OD / 2 - 3, zc + CAP_H), 3 * k * mm, -NOTCH_H * k * mm, fill=1)
    c.setFillGray(0)
    label(S, -3, zc - 6, "1/2\" cap, drilled and", 5.5, "r")
    label(S, -3, zc - 10, "tapped for the RP-SMA", 5.5, "r")
    c.setLineWidth(0.6)                        # pigtail: board -> notch -> bulkhead
    c.setDash(0.8, 0.8)
    pz = zd - DECK_T - BOARD_DROP - ESP32[3]   # board's lower end
    c.line(*S(CAP_OD / 2 + 1.5, pz), *S(CAP_OD / 2 + 1.5, zc + CAP_H - NOTCH_H / 2))
    c.line(*S(CAP_OD / 2 + 1.5, zc + CAP_H - NOTCH_H / 2), *S(0, zc + 3))
    c.setDash()
    label(S, CAP_OD / 2 + 3, zc + CAP_H + 3, "pigtail in via notch", 5.5, "l")
    label(S, -PIPE_OD / 2 - 9, zd - 70, "1/2\" PVC", 5.5, "r")
    c.setLineWidth(1.2)
    c.setDash(2, 1.5)
    c.line(*S(0, zc), *S(0, zc - ESP_ANT_L))
    c.setDash()
    label(S, 2, zc - ESP_ANT_L + 4, "ESP antenna (RP-SMA in the cap)", 5.5, "l")
    # boards on the pipe: ESP32 in the cut (3 o'clock), splitter behind (7 o'clock, dashed)
    r0 = PIPE_OD / 2 + BOARD_OFF
    zb = zd - DECK_T - BOARD_DROP
    c.setLineWidth(0.5)
    rect(S, r0, zb, r0 + ESP_DEPTH, zb - ESP32[3], fill=0.85)
    label(S, r0 + ESP_DEPTH / 2, zb - 6, "RJ45", 5)
    label(S, r0 + ESP_DEPTH / 2, zb - ESP32[3] / 2, "ESP32", 6)
    bxx = [clock(r, BUS_CLOCK)[0] for r in (r0, r0 + BUS_DEPTH)]          # option: bus on the pipe, behind the cut
    c.setDash(0.8, 0.8)
    rect(S, min(bxx), zb, max(bxx), zb - POWER[3])
    c.setDash()
    label(S, -PIPE_OD / 2 - SPL_DEPTH / 2 - 13, zb - 3, "bus", 5.5, "r")
    label(S, -PIPE_OD / 2 - SPL_DEPTH / 2 - 13, zb - 8, "(option)", 5.5, "r")
    sxx = [clock(r, SPL_CLOCK)[0] for r in (r0, r0 + SPL_DEPTH)]
    rect(S, min(sxx), zb, max(sxx), zb - SPLITTER[3], dash=(2, 1.5))
    label(S, sum(sxx) / 2, zb - SPLITTER[3] / 2, "PoE", 5.5)            # dashed: behind the cut
    c.setStrokeColorRGB(0.1, 0.45, 0.2)        # Ethernet: down from the ceiling through the pipe, out a side slot
    c.setLineWidth(1.0)
    ex, ez = -PIPE_OD / 2 + 3, zb - 12
    c.line(*S(ex, NUT_H + 7), *S(ex, ez))
    c.line(*S(ex, ez), *S(min(sxx) + 1, ez))
    c.setStrokeGray(0)
    c.setFillColorRGB(0.1, 0.45, 0.2)
    label(S, ex - 2, NUT_H + 4, "Ethernet (PoE) from the ceiling, down the pipe", 5.5, "r")
    label(S, ex + 1.5, ez - 4.5, "side slot", 5.5, "l")
    c.setFillGray(0)

    c.setFont("Helvetica", 8.5)
    notes = [
        f"Pipe: 1/2\" PVC ({PIPE_OD:g} mm OD) from the male adapter's socket through the 2-1/4\" deck hole, ~{-zc - PLATE_T - ENC_T - ADP_HEX_H - 4:.0f} mm "
        "long (check the",
        "socket depth), capped flush with the core's far end. The cap is drilled and tapped: the ESP antenna's RP-SMA bulkhead",
        "threads into it, and the U.FL pigtail from the ESP32 enters through a notch in the cap rim. The antenna, screwed onto",
        "the bulkhead, clamps the copper end plate that closes the core (optional; see END PLATE, left).",
        "Splitter and ESP32 zip-tied to the pipe facing the 3 and 7 o'clock corners (widest room), RJ45 / USB-C end up;",
        "the 11 o'clock corner is left for cables (and the bus option). Ethernet (PoE, green): from the ceiling down the adapter's",
        "bore and the pipe, out a side slot (about 12 x 16 mm, cut before gluing) beside the splitter. An RJ45 plug (11.7 mm wide)",
        "fits the ~16 mm bore: pull it through before fitting any boot, or crimp after. The adapter's thread goes up through the",
        "module plate and the enclosure top; the nut on top clamps both. Modules and the bus hang under the plate (page 3).",
        "OPTION: the bus board can go on the pipe (dashed, 11 o'clock, opposite the ESP32 and splitter) instead of on the plate.",
        "Side: dashed box = PoE splitter, behind the cut. XIAOs, tie mounts: as page 3. Estimates: adapter, nut,",
        "enclosure top, splitter size, board depths, antenna length.",
        "EU parts: 20 mm PVC-U pressure pipe (20 mm OD, 1.3 mm under 1/2\" Sch 40; same holes), a 20 mm solvent-weld end cap,",
        "a 20 mm x 1/2\" BSP male adaptor and a 1/2\" BSP backnut, and a 57 mm hole saw for the deck. The RP-SMA bulkhead's",
        "thread is 1/4\"-36 UNS everywhere: if that tap is hard to find, drill the cap 6.5 mm and use the bulkhead's own nut.",
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (72 - n * 3.6) * mm, t)

    end_notes = [                              # end plate guidance, in the free space under the top view
        "END PLATE: leave it off, or bond it all round - never",
        "held by the antenna screw alone.",
        "Worst: plate on the antenna screw only. Its loose edges",
        "make slots (a face is 120 mm; ~62 mm resonates at",
        "2.4 GHz) that re-radiate and can detune the antennas.",
        "Fine: no plate. The faces still shield the sides; the",
        "open end leaks ESP32 / splitter noise downward.",
        "Best: plate bonded along all 3 edges, gaps < ~25 mm",
        "(copper tape over the seams, or spring tabs / screws",
        "every 20-25 mm), star washer under the antenna nut.",
        "No plate: use a self-contained antenna on the cap",
        "(a sleeve-dipole rubber duck), not a bare 1/4-wave whip.",
        "Build without it first; add a bonded plate only if the",
        "XIAOs see noise with the ESP32 and splitter running.",
    ]
    c.setFont("Helvetica-Bold", 7)
    c.drawString(15 * mm, 116 * mm, end_notes[0])
    c.setFont("Helvetica", 7)
    for n, t in enumerate(end_notes[1:], 1):
        c.drawString(15 * mm, (116 - n * 3.0) * mm, t)
    c.setLineWidth(0.6)                        # 50 mm at drawing scale
    c.line(15 * mm, 14 * mm, (15 + 50 * k) * mm, 14 * mm)
    for t in (0, 25, 50):
        c.line((15 + t * k) * mm, 14 * mm, (15 + t * k) * mm, 16.5 * mm)
    c.setFont("Helvetica", 7)
    c.drawString((18 + 50 * k) * mm, 13.5 * mm, "50 mm at drawing scale")


BUILD_TAGS = {           # which build type each page belongs to (user, 2026-11-10): builders pick one, alt or pipe
    deck_page: ("BOTH BUILDS", "alt and pipe (the 2-1/4\" hole-saw circle is pipe only)", (0.3, 0.3, 0.3)),
    alt_plate_page: ("ALT BUILD ONLY (no pipe)", "pick one: alt or pipe", (0.1, 0.35, 0.7)),
    fl_plate_page: ("PIPE BUILD ONLY", "pick one: alt or pipe", (0.1, 0.5, 0.25)),
    face_page: ("BOTH BUILDS", "alt and pipe", (0.3, 0.3, 0.3)),
    stack_page: ("PIPE BUILD ONLY", "pick one: alt or pipe", (0.1, 0.5, 0.25)),
    wiring_page: ("BOTH BUILDS", "alt and pipe", (0.3, 0.3, 0.3)),
}


def build_tag(c, page, n):
    """Box naming the build type the page is for, plus the page set of each build. Right of the scale bar,
    below the titles; on the wiring page (no room there) beside the title."""
    head, sub, rgb = BUILD_TAGS[page]
    sets = "Alt: pages 1, 2, 4, 6   Pipe: pages 1, 3, 4, 5, 6"
    x1 = PAGE_W - 12 * mm
    y1 = PAGE_H - (6.5 if page is wiring_page else 27.5) * mm
    w = max(c.stringWidth(f"p{n}  {head}", "Helvetica-Bold", 8.5), c.stringWidth(sub, "Helvetica", 6),
            c.stringWidth(sets, "Helvetica", 6)) + 4 * mm
    h = 10 * mm
    c.saveState()
    c.setStrokeColorRGB(*rgb)
    c.setLineWidth(1)
    c.setFillColorRGB(*(1 - (1 - v) * 0.1 for v in rgb))
    c.roundRect(x1 - w, y1 - h, w, h, 1.5 * mm, fill=1)
    c.setFillColorRGB(*rgb)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x1 - w + 2 * mm, y1 - 3.6 * mm, f"p{n}  {head}")
    c.setFont("Helvetica", 6)
    c.drawString(x1 - w + 2 * mm, y1 - 6.3 * mm, sub)
    c.setFillGray(0.3)
    c.drawString(x1 - w + 2 * mm, y1 - 8.8 * mm, sets)
    c.restoreState()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "shield_deck_templates.pdf")
    c = canvas.Canvas(out, pagesize=letter)
    c.setTitle("Shield deck, back panel, electronics plate templates and plate wiring")
    # drill templates first (deck, plates, back panel), then the stack view, wiring diagram last (user, 2026-11-09)
    for n, page in enumerate((deck_page, alt_plate_page, fl_plate_page, face_page, stack_page, wiring_page), 1):
        page(c)
        build_tag(c, page, n)
        c.showPage()
    c.save()
    print("wrote", out)


if __name__ == "__main__":
    main()
