"""1:1 printable PDF templates: shield deck drill template, electronics plate (both discs drawn the same way
round, plate 12 o'clock up), the plate wiring diagram, then the back panel (reflector face).

Uses the same geometry as make_shield_deck.py. Run:  python make_templates.py
Print at 100% / "Actual size" and check the 100 mm scale bar with a ruler.
"""
import math
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

import make_shield_deck as g

PAGE_W, PAGE_H = letter
FACE_H = 120.0                 # back panel height: square 120 x 120 faces so the core fits the bucket
DIPOLE_HOLE = 6.5              # RP-SMA bulkhead at the face centre (DIY dipole option)
# Printed-dipole panel board (measured 60 x 50 mm) taken out of its housing and turned 90 deg,
# long bar vertical, centred across the face. Its own coax and stalk plug into the deck's P2 jack,
# which is on the right seen from the front, so the coax notch faces right.
BOARD_W, BOARD_H = 50.0, 60.0  # as mounted: short side across, long side down
BOARD_CY = 65.0                # board centre below the deck (A), 35-95 mm: as low as the coax reaches P2
                               # (position B, one hole pitch lower, was dropped: it ran to 119 mm on a 120 mm face)
BOARD_GAP = 7.0                # measured board -> foil reflector (8 mm over the post, minus 1 mm)
POST_X, POST_Y = 35.0, 24.0    # post hole centres across / down (measured 35 short side, 24 long side)
BOARD_HOLE = 2.45              # measured with a hole gauge: 2.4-2.5 mm (M2 clearance)
POST_HOLE = 2.4                # face hole: M2 nylon screws, 14 mm, on 6-8 mm standoffs
POST_EDGE = 2.8                # measured: board edge away from the notch -> edge of the nearest holes
POST_SHIFT = BOARD_W / 2 - (POST_EDGE + BOARD_HOLE / 2 + POST_X / 2)  # ~3.5 mm: hole pattern off the board
                                                                      # centre, away from the coax notch
# Test position C: board as it sat in the housing (long bar horizontal), coax notch up toward the deck.
# Placed so its holes keep >= 5.5 mm (an M3 head) from the A holes; its coax needs extending to reach P2.
BOARD_CY_C = 73.0              # rows at 59 / 94 mm, clear of the A rows at 53 / 77 mm

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
PLATE_DIAMETER = 152.0
PLATE_TURN = 30.0
PLATE_M4 = 4.5
PIGTAIL_HOLE = 10.0            # three coax + one MHF4 plug at a time; +-3 mm slack on the connector position
PIGTAIL_DX = 1.15             # hole this far left of the strip middle: between the yellow and the S1 / S2 lanes
IPEX_DY = 6.0                  # IPEX4 connector above the XIAO centre line (top view); ASSUMED, check on the board
JST_YS = (33.0, 5.0, -13.0)    # mated JST pairs in the strip: S0 under the bus board, S1 / S2 below the hole
TIE_HOLE = 3.5                 # small zip ties (2.5 mm wide)
TIE_CLEAR = 3.0                # part edge -> tie hole centre
XIAO_L, XIAO_W = 21.0, 17.8    # long axis radial, USB-C toward the rim, U.FL end toward the pigtail strip
XIAO_X = 30.5                  # XIAO centre, right of the plate centre
XIAO_YS = (37.0, 13.0, -13.0)  # S0, S1, S2; USB-C plugs pass above and below the 3 o'clock bolt
XIAO_TIE_DX = (4.0, -4.0, 4.0)  # tie offset along each XIAO so neighbouring tie holes don't meet
POWER = (4.0, 40.0, 12.7, 19.6)         # MBSS 4x4 pad board (0.5 x 0.77 in), top of the pigtail strip, hole end up
POWER_HOLE = (10.35, 55.6)              # its hole, ~4 mm in from the top end
PLATE_M3 = 3.4
SPLITTER = (-58.0, -43.0, 29.0, 86.0)   # x0, y0, w, h - estimated from a photo, place by eye
ESP32 = (-16.5, -36.0, 21.0, 72.8)      # Waveshare ESP32-S3-ETH, 72.8 x 21 mm (CNX spec list); RJ45 side up, RJ45 +
                                        # USB-C end at the top (north), so VBUS (pin 40) is the top right header pin
SPLITTER_TIES = (30.0, -30.0)           # tie y positions (ties run across the part)
ESP32_TIES = (-4.0, -30.0)             # right-hand holes in the gaps between the S1 / S2 JST pairs and below
JST_L, JST_W = 15.0, 12.0              # mated inline pair, estimated; lies across the strip
JST_PITCH = 2.5                        # pin rows inside the mated pair, pin 1 at the top


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
    c.setDash()

    letters = {"duck/monopole": "D", "patch": "P", "patch end": "P2", "dipole coax": "C"}
    for d, x, y, lab in g.holes:
        if lab == "via":
            continue
        px, py = P((x, y))
        c.setLineWidth(0.5)
        c.circle(px * mm, py * mm, d / 2 * mm)
        c.setLineWidth(0.2)
        crosshair(c, px, py, d / 2)
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
        f"D 6.5 mm = rubber duck / monopole ({g.DUCK_SPACING:g} mm in front of face)    "
        f"P / P2 6.5 mm = patch ({g.PATCH_OFFSET:g} mm in front of face; P2 {g.PATCH_END_INSET:g} mm from the face end)",
        "C 10 mm = dipole coax pass-through (inside core)    M4 4.5 mm = bolts to the electronics plate (inside core)",
        "Arrow points to Sector 0. Holes are symmetric, so the template also works flipped (labels read mirrored).",
        f"Drawn the same way round as the plate (page 2): plate 12 o'clock up, S0 arrow {PLATE_TURN:g} deg clockwise of it.",
    ]
    for n, t in enumerate(lines):
        c.drawString(15 * mm, (52 - n * 5) * mm, t)
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
    legend = [
        f"A (dashed): bar vertical, notch right, board {BOARD_CY - BOARD_H / 2:g}-{BOARD_CY + BOARD_H / 2:g} mm "
        "down - stalk reaches the P2 deck jack",
        f"C (grey): bar horizontal, notch up, board {yc - BOARD_W / 2:g}-{yc + BOARD_W / 2:g} mm down",
        "Centre 6.5 mm hole: DIY dipole RP-SMA only",
    ]
    for n, t in enumerate(legend):
        c.drawCentredString(xc * mm, (Y(FACE_H) - 13 - n * 4) * mm, t)
    holes.update((xc + sx, yc + POST_SHIFT + sy) for sx in (-POST_Y / 2, POST_Y / 2)
                 for sy in (-POST_X / 2, POST_X / 2))
    c.setLineWidth(0.5)
    for hx, hy in holes:
        c.circle(hx * mm, Y(hy) * mm, POST_HOLE / 2 * mm)
        crosshair(c, hx, Y(hy), POST_HOLE / 2)
    c.drawCentredString(xc * mm, (Y(BOARD_CY - BOARD_H / 2) + 2) * mm,
                        f"{len(holes)} x {POST_HOLE:g} mm post holes - check against your board first")

    # dimensions
    c.setFont("Helvetica", 8)
    c.drawCentredString(xc * mm, (Y(FACE_H) - 6) * mm, f"{g.FACE_WIDTH:g} mm")
    c.drawString((x0 + g.FACE_WIDTH + 3) * mm, Y(FACE_H / 2) * mm, f"{FACE_H:g} mm")
    c.drawString((x0 + g.FACE_WIDTH + 3) * mm, (Y(FACE_H / 2) - 4) * mm, f"centre at {FACE_H / 2:g} mm")

    c.setFont("Helvetica", 8.5)
    notes = [
        "Rubber duck / monopole / dipole sit 31 mm in front of this face (on the D hole).",
        f"Panel board {BOARD_W:g} x {BOARD_H:g} mm: {BOARD_GAP:g} mm off this face on nylon standoffs. "
        "A = stalk on the P2 deck jack; C = coax may need extending.",
        "Corners meet at 120 deg to form the triangle; solder or tape the seams. Holes under 10 mm don't affect the reflector.",
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (35 - n * 5) * mm, t)
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
        c.drawString(15 * mm, (58 - n * 4.5) * mm, t)
    scale_bar(c, 15, 22)


# Wiring diagram (page 3), drawn over the wired part of the plate layout. Pin numbers: XIAO pins 1-7 = D0-D6,
# 8-14 = D7, D8, D9, D10, 3V3, GND, 5V; ESP32-S3-ETH header pins as on Waveshare's pinout. The board lies RJ45 side
# up with the RJ45 / USB-C end north, so pins 40 (VBUS, top) to 21 run along the edge facing the radios (decided
# 2026-10-31). Pad positions are approximate.
# Wires run in straight lanes (see the lane constants below); the JST pair sits in the wire (pin number in the
# XIAO-end label).
XIAO_ROW = 7.6                 # pad rows +- this from the XIAO centre line
ESP_PAD_X = ESP32[0] + ESP32[2] - 1.3   # header pads just inside the ESP32's right edge
ESP_PIN40_Y = ESP32[1] + ESP32[3] - 2.5
BUS_ROWS = (50.6, 48.1, 45.6, 43.1)     # pad rows A-D, top to bottom; A = ESP TX (every D7), B = GND, D = 5V
BUS_COLS = tuple(POWER[0] + POWER[2] / 2 + k * 2.54 for k in (-1.5, -0.5, 0.5, 1.5))  # cols 1-4: ESP, S0, S1, S2
RED, BLACK, YELLOW, GREEN = (0.85, 0.0, 0.0), (0.0, 0.0, 0.0), (0.85, 0.65, 0.0), (0.0, 0.6, 0.2)  # JST wire colours
JST_PINS = ((RED, "red", "5V (14)"), (BLACK, "black", "GND (13)"), (YELLOW, "yellow", "D6 TX (7)"),
            (GREEN, "green", "D7 RX (8)"))   # JST pins 1-4, crimp side, key peg up, left to right
SECTOR_PINS = ((34, 17), (32, 16), (31, 18))  # ESP32 RX for each sector's D6 (TX): header pin, GPIO; RX on 31-34,
                                               # then TX (35), GND (38), VBUS (40): grouped by function
ESP_TX = (35, 21)                              # ESP32 TX to the bus TX row, which feeds every XIAO's D7 (RX)
WIRING_SCALE = 2.0             # enlarged for reading; not a drilling template
WIRING_VIEW = (-15.0, -27.0, 62.0, 62.0)   # plate area shown: x0, y0, x1, y1


def esp_pin_y(n):
    return ESP_PIN40_Y - (40 - n) * 2.54


JST_HALF = 5.0                 # one half of the pair as drawn on the wiring page (halves drawn apart)
FAR_X0 = 10.8                  # far halves sit a little right of the strip middle, leaving lanes on both sides
XIAO_JST_GAP = 6.0             # XIAO USB end -> XIAO half: room for the 4 tail lanes

# Wiring page lanes, plate mm. Wires run straight in fixed lanes, so each bundle stays together:
# - XIAO tail: yellow over the top edge of the XIAO, the rest under its bottom edge, then up the gap to the JST.
# - Far tail: yellow left to its ESP32 RX pin; red up its bus column, black / green up lanes just left / right of
#   it. S1 and S2 red / black / green go up the strip's right side, past the far halves above, then left under
#   the bus. The ESP TX feed (green) goes up left of the bus and into the TX row from the side.
XT_LANES = (1.0, 2.2, 3.4, 4.6)          # XIAO tail verticals right of the USB end: yellow, red, black, green
XT_STEP = 0.6                            # lane spacing above / below the XIAO
YELLOW_LANES = (6.0, 6.0, 5.2)           # yellow verticals to the ESP32 RX pins (S2 apart: it ends just below S1's)
FEED_TX_LANE = 4.8                       # ESP TX feed vertical, left of the bus board's pads
BUS_LANE = 0.85                          # black lane this far left of its bus column, green this far right
RISE = (0.6, 1.3, 2.0)                   # S1 / S2 green, red, black: rise above the far half before turning right
GREEN_RISE_X = 10.0                      # S1 / S2 green rises here, between the red rise and the far half
RIGHT_LANES = (16.2, 16.85, 17.5, 18.15, 18.8, 19.45)  # S1 black, red, green, S2 black, red, green, up the right
TOP_TURNS = (36.6, 37.4, 38.2, 39.0, 39.8, 40.6)       # same wires, turning left under the bus board


def jst_halves(i):
    """Wiring page only: x0, y0 of sector i's far half (in the strip) and XIAO half (off its USB end)."""
    return (FAR_X0, JST_YS[i] - JST_W / 2), (XIAO_X + XIAO_L / 2 + XIAO_JST_GAP, XIAO_YS[i] - JST_W / 2)


def jst_pin_y(y0, n):
    return y0 + JST_W / 2 + (2.5 - n) * JST_PITCH


def wiring_routes():
    """(colour, XIAO-tail points or None, far-tail points, XIAO-end label or None, ESP-end label or None), plate mm.
    XIAO tail: pad -> that pin on the XIAO half; far tail: same pin on the far half -> ESP32 pin or bus pad."""
    xr = XIAO_X + XIAO_L / 2
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
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm, "Electronics plate wiring - same layout as the drill template")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 f"Top view of the radio side, {WIRING_SCALE:g}x (not for drilling). Pin numbers in brackets. "
                 "Pad positions approximate.")
    c.drawString(15 * mm, (PAGE_H / mm - 25.5) * mm,
                 "JST halves drawn apart: XIAO half right of each radio, far half in the strip; same name = they plug together.")

    # layout in grey, clipped to the view
    c.saveState()
    clip = c.beginPath()
    clip.rect(*P(vx0, vy0), R(vx1 - vx0), R(vy1 - vy0))
    c.clipPath(clip, stroke=1, fill=0)
    c.setStrokeGray(0.7)
    c.setLineWidth(0.5)
    c.circle(*P(0, 0), R(PLATE_DIAMETER / 2))
    c.setDash(3, 2)
    c.rect(*P(ESP32[0], ESP32[1]), R(ESP32[2]), R(ESP32[3]))
    c.setDash()
    c.rect(*P(POWER[0], POWER[1]), R(POWER[2]), R(POWER[3]))
    for d, x, y, tag in plate_holes():
        if tag in ("pigtail", "M4", "power"):
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
    xl, xr = XIAO_X - XIAO_L / 2, XIAO_X + XIAO_L / 2
    pad = [xr - 2.88 - k * 2.54 for k in range(7)]
    for i, yc in enumerate(XIAO_YS):
        c.setStrokeGray(0.4)
        c.setLineWidth(0.6)
        c.rect(*P(xl, yc - XIAO_W / 2), R(XIAO_L), R(XIAO_W))
        c.setLineWidth(0.3)
        for px in pad:
            c.circle(*P(px, yc + XIAO_ROW), R(0.5))
            c.circle(*P(px, yc - XIAO_ROW), R(0.5))
        c.setStrokeGray(0)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(*P(XIAO_X, yc + 3.3), f"S{i} XIAO")
        c.setFont("Helvetica", 5.5)
        c.drawString(*P(xl + 0.6, yc + 5.4), "IPEX4")
        c.drawRightString(*P(xr - 0.6, yc + 5.4), "USB-C")

    for col, xiao, _, _, _ in routes:    # XIAO tails, around the boards
        if xiao:
            wire(col, xiao)
    c.setStrokeColorRGB(0, 0, 0)

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
    for col, xiao, far, _, _ in routes:  # wire ends and JST pins on top
        c.setFillColorRGB(*col)
        for seg in (xiao, far):
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
            label(xl + 0.8, yc + xiao_label_y[col], xiao_end)
        if esp_end:
            y = pts[0][1] if pts[0][0] == ESP_PAD_X else pts[-1][1]
            label(ESP_PAD_X - 1.0, y - 0.6, esp_end, right=True)
    c.setFillGray(0)

    c.setFont("Helvetica", 8.5)
    ny = oy + sc * vy0 - 9
    notes = [
        "D6 -> its own ESP RX (the pin is the sector): S0 GPIO17 (34), S1 GPIO16 (32), S2 GPIO18 (31).",
        "ESP TX GPIO21 (35) -> bus TX row -> every D7. Feed: TX (35) -> TX row, VBUS (40) -> 5V row, GND (38) -> GND row.",
        "Bus: hole end up, rows bridged, 3rd row spare. ESP32 RJ45 side up, RJ45 / USB-C end north: VBUS (40) top right pin.",
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


# Alternative split plate (2026-10-31): no pigtail hole. The three XIAOs hang on the UNDERSIDE (deck side, in the
# ~25 mm spacer gap), each IPEX4 end on a flat run to an adhesive HS-100 tie mount (12.5 mm square) that clamps the
# pigtail before it bends to its deck jack. ESP32 and bus board on the top face; the PoE splitter goes in a 4" round
# electrical box (1" hole), fed by a 90 deg adapter on the ESP32's RJ45. Each XIAO's 4-wire tail goes up through
# its own harness hole to the JST pair on the top. Same plate frame as above: 12 o'clock up, M4 bolts unchanged.
# Placed by search (2026-10-31): each XIAO is held by VHB plus one zip tie across it, so its tie holes and the
# strap's run over the top face stay clear of the ESP32 and bus board, and the ESP32's straps under the plate
# miss the XIAOs.
ALT_XIAOS = ((-7.0, 26.0, 45.0), (-4.0, -34.0, 285.0), (-37.0, 26.0, 135.0))  # S0-S2: centre, angle of IPEX4 end
ALT_XIAO_TIE_S = (2.0, -3.0, -3.0)  # tie across each XIAO this far along its axis (+ toward the IPEX4 end)
ALT_IPEX = (8.25, 3.9)        # IPEX4 centre from the XIAO centre: toward its end, toward the pin edge (measured)
ALT_MOUNT = 18.25             # tie mount centre along the XIAO axis (1.5 mm past the board end)
ALT_MOUNT_SIDE = 12.5         # HS-100 adhesive mount, 3.2 mm slots
ALT_HARNESS_S = 15.0          # harness hole on the XIAO axis, this far back from its centre (past the USB-C end)
ALT_HARNESS_HOLE = 5.0        # 4 wires through; chamfer both edges
ALT_ESP32 = (-24.0, 0.0)      # ESP32-S3-ETH centre, long axis east-west, RJ45 / USB-C end east (toward the centre),
                              # so the header (VBUS 40 at the east end) is the south edge, facing the bus board
ALT_ESP32_TIES = (-52.0, 0.0)  # tie x positions, holes ESP32_W / 2 + TIE_CLEAR above and below
ALT_BUS = (-24.0, -21.0)      # bus board centre, long side east-west, hole at the east end
ALT_BUS_HOLE = (-18.2, -21.0)
ALT_DECK_JACK = 9.2           # RP-SMA bulkhead hex across corners: drawn where each deck jack sits under the plate


def alt_quad(cx, cy, hl, hw, a):
    ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
    return [(cx + sx * hl * ux - sy * hw * uy, cy + sx * hl * uy + sy * hw * ux)
            for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))]


def alt_xiao(cx, cy, a, tie_s=0.0):
    """Board outline, IPEX4 point, tie mount outline, USB-end point, harness hole, tie holes for one XIAO."""
    ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
    along, side = ALT_IPEX
    ipex = (cx + along * ux - side * uy, cy + along * uy + side * ux)
    mount = alt_quad(cx + ALT_MOUNT * ux - side * uy, cy + ALT_MOUNT * uy + side * ux,
                     ALT_MOUNT_SIDE / 2, ALT_MOUNT_SIDE / 2, a)
    usb = (cx - (XIAO_L / 2 - 2.5) * ux, cy - (XIAO_L / 2 - 2.5) * uy)
    harness = (cx - ALT_HARNESS_S * ux, cy - ALT_HARNESS_S * uy)
    o = XIAO_W / 2 + TIE_CLEAR
    ties = [(cx + tie_s * ux - k * o * uy, cy + tie_s * uy + k * o * ux) for k in (-1, 1)]
    return alt_quad(cx, cy, XIAO_L / 2, XIAO_W / 2, a), ipex, mount, usb, harness, ties


def alt_plate_holes():
    out = [(PLATE_M3, *ALT_BUS_HOLE, "power")]
    for v in g.VERTICES:
        a = math.radians(v + PLATE_TURN)
        out.append((PLATE_M4, g.MOUNT_RADIUS * math.sin(a), g.MOUNT_RADIUS * math.cos(a), "M4"))
    for i, (x, tie_s) in enumerate(zip(ALT_XIAOS, ALT_XIAO_TIE_S)):
        *_, harness, ties = alt_xiao(*x, tie_s)
        out.append((ALT_HARNESS_HOLE, *harness, f"S{i} harness"))
        out += [(TIE_HOLE, tx, ty, f"S{i} tie") for tx, ty in ties]
    for tx in ALT_ESP32_TIES:
        for sy in (-1, 1):
            out.append((TIE_HOLE, tx, ALT_ESP32[1] + sy * (ESP32[2] / 2 + TIE_CLEAR), "tie"))
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
                 "Viewed from the TOP. Radios on the UNDERSIDE (grey, seen through the plate); ESP32 + bus on top. No pigtail hole.")
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
        if lab in ("via", "M4 mount"):
            continue
        dx, dy = x - g.CX, y - g.CY
        px, py = dx * math.cos(turn) + dy * math.sin(turn), -dx * math.sin(turn) + dy * math.cos(turn)
        c.circle(*P(px, py), ALT_DECK_JACK / 2 * mm)
        c.drawCentredString(*P(px, py - 1), f"{lab[:2]} {letters[lab.split(' ', 1)[1]]}")
    c.setDash()

    # underside: XIAOs, IPEX4 dots, tie mounts, coax start
    for i, (cx, cy, a) in enumerate(ALT_XIAOS):
        board, ipex, mount, usb, _, ties = alt_xiao(cx, cy, a, ALT_XIAO_TIE_S[i])
        c.setStrokeGray(0.6)                 # its zip tie: strap over the board, through both holes
        c.setLineWidth(1.2)
        c.line(*P(*ties[0]), *P(*ties[1]))
        c.setStrokeGray(0.45)
        c.setLineWidth(0.4)
        c.setDash(2, 1.5)
        poly(board)
        c.setFillGray(0.88)
        poly(mount, fill=1)
        c.setDash()
        c.setFillGray(0.4)
        c.circle(*P(*ipex), 0.9 * mm, fill=1, stroke=0)
        mx = sum(p[0] for p in mount) / 4
        my = sum(p[1] for p in mount) / 4
        c.setStrokeColorRGB(0.9, 0.55, 0.1)
        c.setLineWidth(1.6)
        c.line(*P(*ipex), *P(mx, my))
        c.setFillGray(0.35)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(*P(cx, cy - 1.5), f"S{i}")
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(*P(*usb), "USB")
        c.drawCentredString(*P(mx, my - 0.8), "mount")
    c.setStrokeGray(0)
    c.setFillGray(0)

    # top face: ESP32 and bus board
    c.setLineWidth(0.5)
    ex, ey = ALT_ESP32
    c.rect(*P(ex - ESP32[3] / 2, ey - ESP32[2] / 2), ESP32[3] * mm, ESP32[2] * mm)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(*P(ex - 6, ey - 1), "ESP32-S3-ETH (top)")
    c.setFont("Helvetica", 6)
    c.drawRightString(*P(ex + ESP32[3] / 2 - 1.5, ey + 1.5), "RJ45 + 90 deg")
    c.drawRightString(*P(ex + ESP32[3] / 2 - 1.5, ey - 3.5), "USB-C under")
    c.drawCentredString(*P(ex - 6, ey - ESP32[2] / 2 + 1.5), "header pins 21-40 this edge, VBUS (40) east")
    bx, by = ALT_BUS
    c.rect(*P(bx - POWER[3] / 2, by - POWER[2] / 2), POWER[3] * mm, POWER[2] * mm)
    c.drawCentredString(*P(bx - 2, by - 1), "bus (top)")

    for d, x, y, tag in alt_plate_holes():
        c.setLineWidth(0.5)
        c.circle(*P(x, y), d / 2 * mm)
        c.setLineWidth(0.2)
        crosshair(c, x + ox, y + oy, d / 2)
        c.setFont("Helvetica-Bold", 7)
        if tag == "M4" and y > 0:              # top-left bolt: tie holes below and right, label on the left
            c.drawRightString(*P(x - d / 2 - 2.5, y - 1), "M4")
        elif tag == "M4":
            c.drawCentredString(*P(x, y - d / 2 - 5), "M4")
        elif tag.endswith("harness"):          # S0 and S2 holes sit side by side: S2 labelled left, others right
            c.setFont("Helvetica", 6)
            if tag.startswith("S2"):
                c.drawRightString(*P(x - d / 2 - 1.5, y - 1), "S2 wires")
            else:
                c.drawString(*P(x + d / 2 + 1.5, y - 1), f"{tag.split()[0]} wires")

    c.setFont("Helvetica", 8.5)
    notes = [
        f"Drill: 3 x {PLATE_M4:g} mm (M4) bolts to the deck, same as page 2; {PLATE_M3:g} mm (M3) bus board; "
        f"3 x {ALT_HARNESS_HOLE:g} mm harness holes",
        f"(chamfered): each XIAO's 4-wire tail up to its JST pair on top; {TIE_HOLE:g} mm pairs: one tie across each "
        "XIAO, two across the ESP32.",
        "Underside (grey): XIAOs on VHB + a zip tie (grey bar), IPEX4 dot -> orange flat coax run -> HS-100 tie mount,",
        "which clamps it; bend only after the mount, down to its deck jack. Dotted circles: deck jacks below, not drilled.",
        "Top: ESP32 RJ45 / USB-C end east, near the centre. A 90 deg adapter turns the RJ45 up; patch cable and the USB-C",
        "power lead run through the 4\" box's 1\" hole to the PoE splitter. USB-C is under the board: slim plug.",
        "Spacers 25-30 mm: the radios and the bulkhead backs share that gap.",
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (58 - n * 4.5) * mm, t)
    scale_bar(c, 15, 22)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "shield_deck_templates.pdf")
    c = canvas.Canvas(out, pagesize=letter)
    c.setTitle("Shield deck, back panel, electronics plate templates and plate wiring")
    for page in (deck_page, plate_page, wiring_page, alt_plate_page, face_page):  # discs together, panel last
        page(c)
        c.showPage()
    c.save()
    print("wrote", out)


if __name__ == "__main__":
    main()
