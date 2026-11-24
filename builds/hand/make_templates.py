"""1:1 printable PDF templates: shield deck drill template, electronics plate (both discs drawn the same way
round, plate 12 o'clock up), the plate wiring diagram, the pipe plate and its stack views, the no-pipe (alt) split plate, then the back panel
(reflector face). After the wiring diagram: the LED direction ring option (its power board and strip wiring), then
the unified power + LED stripboard option (pipe build).

Uses the same geometry as make_shield_deck.py and ../../common/layout.py. Run:  python make_templates.py
Print at 100% / "Actual size" and check the 100 mm scale bar with a ruler.
"""
import math
import os
import sys

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"))
import layout
from formulas_page import draw as formulas_page_draw  # noqa: E402
import make_shield_deck as g  # noqa: E402
import params  # noqa: E402

# Every number lives in ../../common/parameters.csv or this build's parameters.csv (all groups but "deck", which
# make_shield_deck.py reads). Only values derived
# from others are computed here.
globals().update(params.load(exclude=["deck"], build="hand"))

PAGE_W, PAGE_H = letter
FACE_WIDTH, HOLE_RPSMA, PATCH_OFFSET = (layout.P[k] for k in ("FACE_WIDTH", "HOLE_RPSMA", "PATCH_OFFSET"))
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
# clear of the hole. Its far side runs back: TX (D8, was D6 until 2026-11-19) to the sector's own
# ESP32 RX pin, the rest to the bus board at the top of the strip (rows: ESP TX to every D7, GND, spare, 5V). Zip ties through hole pairs; the bus board on one M3.
# Three M4 bolts on spacers tie the plate to the deck through the deck's mount holes. The plate is turned
# so its 12 o'clock is PLATE_TURN deg counter-clockwise of the deck's S0 arrow (top view); the bolts then land
# at 3, 7 and 11 o'clock on the plate, clear of the parts.


def scale_bar(c, x, y):
    """100 mm check bars in both directions: across from (x, y) and down from its left end, ticks outward."""
    c.setLineWidth(0.6)
    c.line(x * mm, y * mm, (x + 100) * mm, y * mm)
    c.line(x * mm, y * mm, x * mm, (y - 100) * mm)
    for k in range(0, 101, 10):
        h = 3 if k % 50 else 5
        c.line((x + k) * mm, y * mm, (x + k) * mm, (y + h) * mm)
        c.line(x * mm, (y - k) * mm, (x - h) * mm, (y - k) * mm)
    c.setFont("Helvetica", 8)
    c.drawString((x + 1.5) * mm, (y - 4) * mm, "0")
    c.drawRightString((x + 100) * mm, (y - 4) * mm, "100 mm each way - check both with a ruler before drilling")
    c.drawString((x + 1.5) * mm, (y - 100) * mm, "100 mm")


def crosshair(c, x, y, r):
    c.line((x - r - 2) * mm, y * mm, (x + r + 2) * mm, y * mm)
    c.line(x * mm, (y - r - 2) * mm, x * mm, (y + r + 2) * mm)


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
        "Dotted: mated JST pairs (unplug to reflash); far side D8 TX to its ESP32 RX pin, 3 wires to the bus.",
        "Dashed: ESP32-S3-ETH 72.8 x 21 mm; splitter from a photo - lay it on the printout, tie holes "
        "{:g} mm outside its edges.".format(TIE_CLEAR),
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (60 - n * 4.1) * mm, t)


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
JST_PINS = ((RED, "red", "5V (14)"), (BLACK, "black", "GND (13)"), (YELLOW, "yellow", "DATA D10 (11)"),
            (GREEN, "green", "CMD D7 (8)"))   # JST pins 1-4, crimp side, key peg up: protocol 4 Up port order
HEAD = 0              # star wiring (protocol 4, 2026-11-24, as PCB rev 3): S0 is the head on gateway pin 0,
BRANCHES = (1, 2)     # S1 -> head D0 (Branch 1), S2 -> head D1 (Branch 2), each by a wire soldered pad to pad
SECTOR_PINS = tuple(zip(SECTOR_RX_PINS, SECTOR_RX_GPIOS))   # (header pin, GPIO) of each sector's ESP32 RX
WIRING_XIAO_X = XIAO_X + WIRING_XIAO_DX
USBC_W, USBC_IN, USBC_OUT = 9.0, 6.0, 1.0   # wiring page only: USB-C outline, approximate (width, on board, overhang)
BOTTOM_VIEW_TOP = 3.0                      # wiring page only: top edge of the bottom-view XIAO, plate mm
WIRING_TEXT_TOP = 60.0                     # wiring page only: first line of the "wired the same" notes, above the radios
WIRING_XIAO_YS = (18.0,) + tuple(XIAO_YS[1:])   # wiring page only: the drawn radio sits under the notes


def esp_pin_y(n):
    return ESP_PIN40_Y - (40 - n) * 2.54


# Wiring page lanes, plate mm. Wires run straight in fixed lanes, so each bundle stays together:
# - XIAO tail: yellow over the top edge of the XIAO, the rest under its bottom edge, then up the gap to the JST.
# - Far tail: yellow left to its ESP32 RX pin; red up its bus column, black / green up lanes just left / right of
#   it. S1 and S2 red / black / green go up the strip's right side, past the far halves above, then left under
#   the bus. The ESP TX feed (green) goes up left of the bus and into the TX row from the side.


def jst_halves(i):
    """Wiring page only: x0, y0 of sector i's far half (in the strip) and XIAO half (off its USB end)."""
    return (FAR_X0, WIRING_JST_YS[i] - JST_W / 2), (WIRING_XIAO_X + XIAO_L / 2 + XIAO_JST_GAP, WIRING_XIAO_YS[i] - JST_W / 2)


def jst_pin_y(y0, n):
    return y0 + JST_W / 2 + (2.5 - n) * JST_PITCH


def wiring_routes():
    """(colour, XIAO-tail points or None, far-tail points, XIAO-end label or None, ESP-end label or None), plate mm.
    XIAO tail: pad -> that pin on the XIAO half; far tail: same pin on the far half -> ESP32 pin or bus pad."""
    xr = WIRING_XIAO_X + XIAO_L / 2
    pad = [xr - 2.88 - k * 2.54 for k in range(7)]   # pad x from the USB end; top: D0..D6, bottom: 5V, GND, 3V3, D10..D7
    d10x, d7x, gndx, v5x = pad[3], pad[6], pad[1], pad[0]   # DATA on D10 (protocol 4, 2026-11-24): all four on one edge
    xr_, xb_, xy_, xg_ = (xr + d for d in XT_LANES)
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
    for i, yc in enumerate(WIRING_XIAO_YS):
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
        yellow = ((fx, fp(3)), (yl, fp(3)), (yl, esp_pin_y(rx)), (ESP_PAD_X, esp_pin_y(rx)))   # head only
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
        if i == HEAD:
            out.append((YELLOW, ((d10x, bot), (d10x, below - 2 * XT_STEP), (xy_, below - 2 * XT_STEP), (xy_, jp(3)),
                                 (jx, jp(3))), yellow,
                        f"D10 (11) -- JST 3 -- ESP GPIO{grx} ({rx})",
                        f"GPIO{grx} RX ({rx}) -- S{i} head DATA"))
        out += [
            (GREEN, ((d7x, bot), (d7x, below - 3 * XT_STEP), (xg_, below - 3 * XT_STEP), (xg_, jp(4)), (jx, jp(4))),
             green, f"CMD D7 (8) -- JST 4 -- bus TX row, col S{i}", None),
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
    used = {11: ("D10", YELLOW), 8: ("D7", GREEN), 13: ("GND", BLACK), 14: ("5V", RED), 1: ("D0", YELLOW),
            2: ("D1", YELLOW)}

    def usb_outline(yc):                 # USB-C receptacle, approximate, light grey, overhanging the USB end
        c.saveState()
        c.setStrokeGray(0.75)
        c.setLineWidth(0.4)
        c.roundRect(*P(xr - USBC_IN, yc - USBC_W / 2), R(USBC_IN + USBC_OUT), R(USBC_W), R(0.8))
        c.restoreState()

    def pin_labels(yc, flipped):
        """Pin number beside every pad (inside the board edge); used pins also named, in their wire colour.
        Top view: D0-D6 (pins 1-7) on the upper row; the flipped (bottom) view swaps the rows."""
        d_row, p_row = (-1, 1) if flipped else (1, -1)          # +1 = upper row
        for k, px in enumerate(pad):
            for side, n in ((d_row, k + 1), (p_row, 14 - k)):
                py = yc + side * XIAO_ROW
                c.setFillGray(0.25)
                c.setFont("Helvetica-Bold", 4.5)
                c.drawCentredString(*P(px, py - side * 1.5 - 0.4), str(n))
                if n in used:
                    name, col = used[n]
                    c.setFillColorRGB(*col)
                    if side == 1 and not flipped:   # top view, upper row: under the number (wires leave over the top)
                        c.drawCentredString(*P(px, py - 3.3), name)
                    else:
                        c.drawCentredString(*P(px, py - side * 2.6 - 0.4), name)
        c.setFillGray(0)

    for i, yc in enumerate(WIRING_XIAO_YS[:1]):     # one XIAO drawn: S1 and S2 are wired the same (note below it)
        c.setStrokeGray(0.4)
        c.setLineWidth(0.6)
        c.rect(*P(xl, yc - XIAO_W / 2), R(XIAO_L), R(XIAO_W))
        c.setLineWidth(0.3)
        for px in pad:
            c.circle(*P(px, yc + XIAO_ROW), R(0.5))
            c.circle(*P(px, yc - XIAO_ROW), R(0.5))
        c.setStrokeGray(0)
        usb_outline(yc)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(*P(xl, yc + XIAO_W / 2 + 4.6), "S0 HEAD XIAO nRF54L15 - TOP VIEW (parts side up)")
        pin_labels(yc, flipped=False)
        ix, iy = WIRING_XIAO_X - XIAO_IPEX[0], yc + XIAO_IPEX[1]     # IPEX4: two rings, not a pad
        c.setStrokeColorRGB(0.1, 0.3, 0.75)
        c.setLineWidth(0.8)
        c.circle(*P(ix, iy), R(1.1))
        c.setLineWidth(0.6)
        c.circle(*P(ix, iy), R(0.45))
        c.setFillColorRGB(0.1, 0.3, 0.75)
        c.drawString(*P(ix + 1.6, iy - 0.6), "IPEX4")
        c.setFillGray(0)
        c.setFont("Helvetica-Bold", 5.5)
        c.saveState()                            # ANTENNA: rotated, just off the antenna edge, level with the IPEX4
        c.translate(*P(xl - 1.2, iy))
        c.rotate(-90)
        c.drawCentredString(0, 0, "ANTENNA")
        c.restoreState()
        c.setFillGray(0)
        c.setStrokeGray(0)

    for r, (col, xiao, _, _, _) in enumerate(routes):   # XIAO tails: the head drawn; S1 / S2 the same, less DATA
        if xiao and r < 7:
            wire(col, xiao)
    yc = WIRING_XIAO_YS[HEAD]                           # branch inputs: D0 / D1 up off the top edge, then right,
    bend = []                                           # each a wire soldered straight to its branch's D10
    for k, (b, ly) in enumerate(zip(BRANCHES, (yc + XIAO_W / 2 + 0.9, yc + XIAO_W / 2 + 2.9))):
        pts = ((pad[k], yc + XIAO_ROW), (pad[k], ly), (BRANCH_STUB_X, ly))
        wire(YELLOW, pts)
        bend.append((b, k, pts[-1]))
    c.setStrokeColorRGB(0, 0, 0)

    for i in range(3):                  # the two JST halves: far half in the strip, XIAO half off the USB end
        for (x0, y0), name in list(zip(jst_halves(i), ("far half", "XIAO half")))[:2 if i == 0 else 1]:
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
        for seg in (xiao if r < 7 else None, far):
            if seg:
                for q in (seg[0], seg[-1]):
                    c.circle(*P(*q), R(0.45), fill=1, stroke=0)
    for b, k, (x, y) in bend:                            # branch wire ends: to that radio, no connector
        c.setFillColorRGB(*YELLOW)
        c.circle(*P(pad[k], yc + XIAO_ROW), R(0.45), fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 5.5)
        c.drawString(*P(x + 0.6, y - 0.6), f"S{b} D10 (11)")
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
            yc = WIRING_XIAO_YS[k // 4]
            k += 1
            if k <= 4:                                 # S0 only
                label(xl + 0.8, yc + xiao_label_y[col], xiao_end)
        if esp_end:
            y = pts[0][1] if pts[0][0] == ESP_PAD_X else pts[-1][1]
            label(ESP_PAD_X - 1.0, y - 0.6, esp_end, right=True)
    c.setFillGray(0)

    same = [                                           # where S1 / S2's XIAOs would be
        ("Helvetica-Bold", "STAR WIRING: S0 is the head."),
        ("Helvetica-Bold", "Every XIAO to its own JST, pad for pad:"),
        ("Helvetica-Bold", "5V (14) -> 1, GND (13) -> 2,"),
        ("Helvetica-Bold", "D7 CMD (8) -> 4. Head only: D10 (11) -> 3."),
        ("Helvetica", ""),
        ("Helvetica", "Shared by every radio on the bus: 5V,"),
        ("Helvetica", "GND and the ESP32 TX (GPIO21) into"),
        ("Helvetica", "every D7 (CMD). All radios hear the"),
        ("Helvetica", "same commands."),
        ("Helvetica", ""),
        ("Helvetica", "DATA: S1 and S2 send to the head, the"),
        ("Helvetica", "head relays all three to one ESP32 RX."),
        ("Helvetica", "S1 D10 (11) -> head D0 (1), S2 D10 (11)"),
        ("Helvetica", "-> head D1 (2): one wire each, soldered"),
        ("Helvetica", "pad to pad, no connector. Their JST pin 3"),
        ("Helvetica", "stays empty. Sector = gateway pin and"),
        ("Helvetica", "the head port (D0 / D1) the data came in."),
    ]
    # bottom view of the same XIAO: no wires, flipped over its long axis (USB-C stays on the right)
    yb = BOTTOM_VIEW_TOP - XIAO_W / 2
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(*P(xl, BOTTOM_VIEW_TOP + 1.6), "XIAO nRF54L15 [1,2,3] - BOTTOM VIEW (flipped, USB-C right)")
    usb_outline(yb)                      # drawn first: the board hides it, only the overhang shows
    c.saveState()
    c.setStrokeGray(0.4)
    c.setFillGray(1)
    c.setLineWidth(0.6)
    c.setDash(2, 1.5)
    c.rect(*P(xl, yb - XIAO_W / 2), R(XIAO_L), R(XIAO_W), fill=1)
    c.restoreState()
    c.setStrokeGray(0.4)
    c.setLineWidth(0.3)
    for px in pad:
        c.circle(*P(px, yb + XIAO_ROW), R(0.5))
        c.circle(*P(px, yb - XIAO_ROW), R(0.5))
    c.setStrokeGray(0)
    c.setFillGray(0.82)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(*P(WIRING_XIAO_X - 2.0, yb - 1.6), "BOTTOM")
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 5.5)
    ya = yb - XIAO_W / 2 + XIAO_W / 5            # antenna end: label off the edge, arrow in, 1/5 up from the bottom
    c.saveState()                                # ANTENNA: rotated, just off the antenna edge, 1/5 up from the bottom
    c.translate(*P(xl - 1.2, ya))
    c.rotate(-90)
    c.drawCentredString(0, 0, "ANTENNA")
    c.restoreState()
    c.drawString(*P(xr + USBC_OUT + 0.8, yb - 0.6), "USB-C")   # beside the overhang, no arrow
    pin_labels(yb, flipped=True)

    tx0, ty0 = WIRING_XIAO_X - XIAO_L / 2 - 2.0, WIRING_TEXT_TOP
    for n, (font, t) in enumerate(same):
        c.setFont(font, 6)
        c.drawString(*P(tx0, ty0 - n * 1.45), t)

    c.setFont("Helvetica", 8.5)
    ny = oy + sc * vy0 - 9
    notes = [
        "Head S0 D10 DATA -> ESP RX GPIO17 (34) (gateway pin 0). GPIO16 (32) and GPIO18 (31) stay free for 2 more heads.",
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
        "Pins left to right: 1 red 5V, 2 black GND, 3 yellow DATA, 4 green CMD (as the carrier",
        "Up port). Both halves carry the same colours in the same order on the crimp side.",
        "XIAO tail: red -> 5V (14), black -> GND (13), green -> D7 (8); head only: yellow -> D10 (11).",
        "Far tail: red -> bus 5V row, black -> bus GND row, green -> bus TX row; head only: yellow",
        "-> ESP RX GPIO17 (34). Branches: pin 3 empty. Female half on the far tail keeps 5V covered.",
    )):
        c.drawString(tx * mm, (top - 7 - n * 4) * mm, s)


# Option: LED direction ring (2026-11-16, user). A WS2812B strip wrapped into a ring above the deck, facing out,
# lights toward a detected beacon. Its 5 V comes from a second 4x4 pad board (same model as the bus board) that
# sits between the PoE splitter and the ESP32: a USB-C socket pigtail takes the splitter's plug, a USB-C plug
# pigtail feeds the ESP32, and the strip hangs off a fused row, so its current never passes through the ESP32.
# Rows (user): 1 and 4 are + and -, 2 is the fused 5 V out, 3 a second GND row (linked to row 4).
# Drawn from the pad side, connections only, in page mm (LED_PAGE: board centre x, y and the pad pitch as drawn).
# The capacitor is a leaded can (user's pick, 2026-11-16: LED_CAP_CAN_PART, size in LED_CAP_CAN), legs spread to
# rows 1 and 3; an 8 mm SMD can's 8.3 mm base is wider than the 7.6 mm pad field. Option (user, 2026-11-16): a 7343
# polymer tantalum chip (7.3 x 4.3 mm) over the end column, ends on rows 1 and 4.
LED_CAP_CAN_PART = "KEMET A750EM337M1CAAE015"
LED_CAP_CHIPS = (("T591X337M010ATE025", 125), ("T545Y337M010ATE035", 105), ("T525Y337M010ATE035", 125))  # user, 2026-11-16
LED_CAP_SEARCH = ("Mouser search: 330 uF, 2917 case, 10 to 16 V polymer tantalum, in stock",
                  "https://www.mouser.com/en/c/passive-components/capacitors/tantalum-capacitors/tantalum-capacitors-polymer/?capacitance=330%20uF&case%20code%20-%20in=2917&termination%20style=SMD%2FSMT&voltage%20rating%20dc=10%20VDC~~16%20VDC&instock=y&rp=passive-components%2Fcapacitors%2Ftantalum-capacitors%2Ftantalum-capacitors-polymer%7C~Voltage%20Rating%20DC&sort=pricing&qty=1")


def led_ring_length():
    return LED_PIXELS * 1000.0 / LED_PER_M


def led_page(c):
    cx, cy, p = LED_PAGE
    cols = [cx + (k - 1.5) * p for k in range(4)]            # a-d, left to right
    rows = [cy + (1.5 - k) * p for k in range(4)]            # rows 1-4, top to bottom
    top = PAGE_H / mm

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (top - 15) * mm, "Option: LED direction ring - power board")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (top - 21) * mm,
                 "Not to scale: shows connections only. A second 4x4 pad board, the same model as the bus board (page 6).")
    c.drawString(15 * mm, (top - 25.5) * mm,
                 "PoE splitter's USB-C plug -> socket pigtail -> this board -> plug pigtail -> ESP32; this board -> strip.")

    # board: outline, row copper, pads
    c.setStrokeGray(0.55)
    c.setLineWidth(0.6)
    c.rect((cols[0] - 12) * mm, (rows[3] - 12) * mm, (3 * p + 24) * mm, (3 * p + 24) * mm)
    c.setStrokeGray(0.85)
    c.setLineWidth(5)
    for y in rows:
        c.line(cols[0] * mm, y * mm, cols[3] * mm, y * mm)
    c.setStrokeGray(0.45)
    c.setLineWidth(0.5)
    for y in rows:
        for x in cols:
            c.setFillGray(0.85)
            c.circle(x * mm, y * mm, 2.0 * mm, fill=1)
            c.setFillGray(1)
            c.circle(x * mm, y * mm, 0.7 * mm, fill=1)
    c.setFillGray(0.35)
    c.setFont("Helvetica-Oblique", 6.5)
    c.drawCentredString(cols[2] * mm, (rows[0] + 8) * mm, "pad side (rows bridged)")
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 6.5)
    lx = cols[0] - 14
    c.drawRightString(lx * mm, (rows[0] + 1.6) * mm, "row 1: 5 V in (+)")
    c.drawRightString(lx * mm, (rows[1] - 0.8) * mm, "row 2: 5 V out, fused")
    c.drawRightString(lx * mm, (rows[2] - 3.6) * mm, "row 3: GND")
    c.drawRightString(lx * mm, (rows[3] - 3.6) * mm, "row 4: GND (-)")

    def wire(col, pts, w=1.1):           # white halo first, as on the wiring page
        for lw, setcol in ((3.0, lambda: c.setStrokeGray(1)), (w, lambda: c.setStrokeColorRGB(*col))):
            setcol()
            c.setLineWidth(lw)
            c.setLineJoin(1)
            path = c.beginPath()
            path.moveTo(pts[0][0] * mm, pts[0][1] * mm)
            for x, y in pts[1:]:
                path.lineTo(x * mm, y * mm)
            c.drawPath(path)
        c.setFillColorRGB(*col)
        for x, y in (pts[0], pts[-1]):
            c.circle(x * mm, y * mm, 0.8 * mm, fill=1, stroke=0)
        c.setFillGray(0)
        c.setStrokeGray(0)

    # C1, the bulk capacitor: leaded can lying beside the pads, legs spread to rows 1 (+) and 3 (-)
    capx, capy, caph = cols[0] - 50, rows[1], 10.0
    lead = (0.3, 0.3, 0.3)
    wire(lead, ((cols[0], rows[0]), (capx, rows[0]), (capx, capy + caph)), 0.8)
    wire(lead, ((cols[0], rows[2]), (capx, rows[2]), (capx, capy - caph)), 0.8)
    c.setLineWidth(0.8)
    c.setFillGray(0.9)
    c.roundRect((capx - 7) * mm, (capy - caph) * mm, 14 * mm, 2 * caph * mm, 2 * mm, fill=1)
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(capx * mm, (capy - 1.2) * mm, "C1")
    c.drawCentredString(capx * mm, (capy + caph - 4.5) * mm, "+")
    c.drawCentredString(capx * mm, (capy - caph + 2) * mm, "-")

    # C1 option: a 7343 polymer chip on the pad side over column a, ends on the same row 1 and row 4 pads
    c.saveState()
    c.setDash(3, 2)
    c.setStrokeGray(0.3)
    c.setLineWidth(0.8)
    c.roundRect((cols[0] - 10) * mm, (rows[3] - 4) * mm, 19 * mm, (3 * p + 8) * mm, 1.5 * mm)
    c.restoreState()
    c.setFont("Helvetica-Oblique", 6)
    c.setFillGray(0.3)
    c.drawCentredString((cols[0] - 0.5) * mm, (cy + 0.6) * mm, "C1 chip")
    c.drawCentredString((cols[0] - 0.5) * mm, (cy - 2.2) * mm, "(option)")
    c.setFillGray(0)

    # pigtails: socket on column b, plug on column d; red up from row 1, black down from row 4
    ytop, ybot = rows[0] + 18, rows[3] - 18
    wire(RED, ((cols[1], rows[0]), (cols[1], ytop)))
    wire(BLACK, ((cols[1], rows[3]), (cols[1], ybot)))
    wire(RED, ((cols[3], rows[0]), (cols[3], ytop)))
    wire(BLACK, ((cols[3], rows[3]), (cols[3], ybot)))
    c.setFont("Helvetica", 6.5)
    c.setFillColorRGB(*RED)
    c.drawRightString((cols[1] + 3) * mm, (ytop + 5.2) * mm, "red: USB-C socket pigtail")
    c.drawRightString((cols[1] + 3) * mm, (ytop + 2.2) * mm, "(5 V in, from the PoE splitter's plug)")
    c.drawString((cols[3] - 3) * mm, (ytop + 5.2) * mm, "red: USB-C plug pigtail")
    c.drawString((cols[3] - 3) * mm, (ytop + 2.2) * mm, "(5 V to the ESP32-S3-ETH's USB-C)")
    c.setFillGray(0)
    c.drawRightString((cols[1] + 3) * mm, (ybot - 3.8) * mm, "black: USB-C socket pigtail (GND)")
    c.drawString((cols[3] - 3) * mm, (ybot - 3.8) * mm, "black: USB-C plug pigtail")
    c.drawString((cols[3] - 3) * mm, (ybot - 6.8) * mm, "(GND)")

    # strip: 5 V from row 2, GND from row 3, data straight from the ESP32 through R
    sx, sw = cols[3] + 30, 24.0
    sy0, sy1 = rows[2] - 17, rows[1] + 8
    dinx = sx + 12
    wire(RED, ((cols[3], rows[1]), (sx, rows[1])))
    wire(BLACK, ((cols[3], rows[2]), (sx, rows[2])))
    wire(GREEN, ((dinx, sy0), (dinx, sy0 - 14)))
    c.setLineWidth(0.8)
    c.setFillGray(0.96)
    c.rect(sx * mm, sy0 * mm, sw * mm, (sy1 - sy0) * mm, fill=1)
    c.setFillGray(1)
    for k in range(3):                                       # a few pixels
        c.rect((sx + sw - 8) * mm, (sy1 - 9 - k * 11) * mm, 5 * mm, 5 * mm, fill=1)
    c.rect((dinx - 1.6) * mm, (sy0 - 10.5) * mm, 3.2 * mm, 7 * mm, fill=1)      # R in the data wire
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString((sx + 1.5) * mm, (rows[1] - 0.8) * mm, "5V")
    c.drawString((sx + 1.5) * mm, (rows[2] - 0.8) * mm, "GND")
    c.drawCentredString(dinx * mm, (sy0 + 1.5) * mm, "DIN")
    c.drawString((dinx + 2.6) * mm, (sy0 - 7.8) * mm, "R")
    c.drawString((sx - 12) * mm, (sy1 + 5.6) * mm, f"WS2812B strip, {LED_PIXELS} pixels")
    c.setFont("Helvetica-Oblique", 6)
    c.drawString((sx - 12) * mm, (sy1 + 2.4) * mm, "pad order differs between strips: go by the printing")
    c.setFont("Helvetica", 6.5)
    c.setFillColorRGB(*GREEN)
    c.drawString(sx * mm, (sy0 - 17.8) * mm, f"green: ESP32 GPIO{LED_DATA_GPIO}")
    c.drawString(sx * mm, (sy0 - 20.8) * mm, "(header pin: Waveshare's pinout)")
    c.setFillGray(0)

    # chip parts on the pad side, each across two pads that have no wire in them
    def chip(x, ya, yb, tag):
        c.setStrokeGray(0)
        c.setLineWidth(0.7)
        c.setFillGray(1)
        c.rect((x - 3) * mm, (yb - 2.6) * mm, 6 * mm, (ya - yb + 5.2) * mm, fill=1)
        c.setFillGray(0.35)
        c.rect((x - 3) * mm, (ya - 0.6) * mm, 6 * mm, 3.2 * mm, fill=1)
        c.rect((x - 3) * mm, (yb - 2.6) * mm, 6 * mm, 3.2 * mm, fill=1)
        c.setFillGray(0)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(x * mm, ((ya + yb) / 2 - 1) * mm, tag)

    chip(cols[2], rows[0], rows[1], "F")
    chip(cols[1], rows[1], rows[2], "C2")
    c.setStrokeGray(0.15)                                    # L: rows 3 and 4 joined
    c.setLineWidth(3)
    c.line(cols[2] * mm, rows[2] * mm, cols[2] * mm, rows[3] * mm)
    c.setStrokeGray(0)
    c.setFont("Helvetica-Bold", 7)
    c.drawString((cols[2] + 2.2) * mm, ((rows[2] + rows[3]) / 2 - 1) * mm, "L")

    ring_len = led_ring_length()
    white_a = LED_PIXELS * LED_PIXEL_MA[0] / 1000.0
    dark_a = LED_PIXELS * LED_PIXEL_MA[1] / 1000.0
    text = [
        ("B", "Parts. F, C2 and L go on the pad side, on pads with no wire in them; the wires and C1's legs come through"),
        ("B", "from the other side."),
        ("", f"C1   {LED_CAP_CAN_PART}: {LED_CAP_UF:g} uF 16 V aluminium polymer, leaded, {LED_CAP_CAN[0]:g} x {LED_CAP_CAN[1]:g} mm can, -55 to +105 C."),
        ("", f"       Spread the legs from {LED_CAP_CAN[2]:g} mm to reach rows 1 (+) and 3 (-); lay the can flat beside the pads and hold it"),
        ("", "       with a dab of RTV. Any leaded polymer can of 330 to 470 uF, 10 to 16 V, rated -55 C, does the same job."),
        ("", f"       Option (dashed): a {LED_CAP_CHIP_UF:g} uF 10 V polymer tantalum chip, 7343 (2917) case, on the pad side over the end"),
        ("", "       column, ends on rows 1 and 4, pushed out to the board edge. Polymer only: not solid (manganese dioxide)"),
        ("", "       tantalum. Coat the board against damp. KEMET, any of: " + ", ".join(
            f"{part} (to +{t} C)" for part, t in LED_CAP_CHIPS[:2]) + ","),
        ("link", f"       {LED_CAP_CHIPS[2][0]} (to +{LED_CAP_CHIPS[2][1]} C). Others that match: "),
        ("", f"C2   {LED_BYPASS_UF:g} uF 50 V X7R ceramic, 1206, flexible (soft) termination, across rows 2 and 3."),
        ("", f"F     {LED_FUSE_A:g} A chip fuse, 1206, across rows 1 and 2: the strip is fused, the ESP32's feed is not."),
        ("", f"L     link (solder bridge or wire) joining rows 3 and 4.        R     {LED_SERIES_OHM:g} ohm in the data wire."),
        ("", ""),
        ("B", "Notes"),
        ("", "Before soldering, plug the PoE splitter into the socket pigtail and meter red to black: +5 V, red positive."),
        ("", "The radios stay on VBUS (40) through the bus board (page 6). The strip's current never passes through the ESP32."),
        ("", f"Strip: {LED_PIXELS} pixels at {LED_PER_M} per m = {ring_len:.0f} mm = a {ring_len / math.pi:.0f} mm ring, inside the"
             f" {g.DISC_DIAMETER:g} mm deck. Mount it above the deck, facing out,"),
        ("", "and keep it and its wires above the deck: the copper shades the antennas from it."),
        ("", f"Current: about {dark_a:.2f} A all dark and {white_a:.1f} A all white. The splitter gives {LED_SUPPLY_A[0]:g} A; the gateway and"
             f" radios use about {LED_SUPPLY_A[1]:g} A."),
        ("", "The firmware must limit how many pixels light at once; the fuse backs that up."),
        ("", f"Data: GPIO{LED_DATA_GPIO} (GPIO2 is the other free pin). The gateway firmware does not drive the strip yet."),
        ("", "Outdoors: polymer and X7R parts hold their values down to -55 C; WS2812B is typically specified to -25 C only."),
    ]
    y = ybot - 20
    for style, s in text:
        c.setFont("Helvetica-Bold" if style == "B" else "Helvetica", 8.5)
        c.drawString(15 * mm, y * mm, s)
        if style == "link":                                  # clickable in the PDF; the README has the same link
            x0 = 15 * mm + c.stringWidth(s, "Helvetica", 8.5)
            w = c.stringWidth(LED_CAP_SEARCH[0], "Helvetica", 8.5)
            c.setFillColorRGB(0.05, 0.25, 0.7)
            c.drawString(x0, y * mm, LED_CAP_SEARCH[0])
            c.setStrokeColorRGB(0.05, 0.25, 0.7)
            c.setLineWidth(0.4)
            c.line(x0, y * mm - 1, x0 + w, y * mm - 1)
            c.linkURL(LED_CAP_SEARCH[1], (x0, y * mm - 2, x0 + w, y * mm + 8), relative=0)
            c.setFillGray(0)
            c.setStrokeGray(0)
        y -= 4.6


# Option: unified power + LED board (2026-11-20, user). One stripboard in place of the bus board (page 6) and the LED
# power board (page 7), for the pipe build: it hangs on the pipe at the 11 o'clock corner (BUS_CLOCK), beside the
# PoE splitter and the ESP32. The two separate boards stay as they are. The XIAOs take 5 V from the splitter rail,
# not from the ESP32's VBUS (user), the fuse is one-time (user), the parts are through-hole (stripboard), and a
# 74HCT125 lifts the ESP32's 3.3 V data to 5 V for the WS2812B (user). Drawn from the component side, strips
# vertical (along the pipe), row 0 toward the deck. Layout is a table so the drawing and the text can't disagree.
UNI_PARTS = {           # ref: part number, what it is (user's picks 2026-11-20; C1 is the LED board's can)
    "PCB": ("BusBoard ST1 (Mouser 854-ST1)", "StripBoard-1, FR4, single-sided, 50 x 80 mm, strips along the 80 mm;"
                                            " one makes one board"),
    "U1": ("TI CD74HCT125E", "quad buffer, 3-state, HCT (TTL inputs, VIH 2 V at 5 V), PDIP-14, -55 to +125 C"),
    "F": ("Littelfuse 0251002.MXL", "2 A very fast, axial, 125 V AC/DC, one-time, -55 to +125 C"),
    "C1": (LED_CAP_CAN_PART, f"{LED_CAP_UF:g} uF 16 V aluminium polymer, radial, -55 to +105 C"),
    "C2": ("KEMET C320C104K5R5TA", "0.1 uF 50 V X7R, radial, 2.54 mm leads (strip supply)"),
    "C3": ("KEMET C320C104K5R5TA", "0.1 uF 50 V X7R, radial, 2.54 mm leads (U1 supply, beside pins 6/7)"),
    "R": ("Yageo CFR-25JB-52-330R", f"{LED_SERIES_OHM:g} ohm 1/4 W carbon film, axial, in the data line after U1"),
    "R2": ("Yageo CFR-25JB-52-10K", f"{UNI_PULLDOWN_OHM / 1000:g} kohm 1/4 W carbon film, axial, standing: pull-down on"
                                    " U1 1A so the strip stays dark while the ESP32 boots"),
}
UNI_STRIPS = (("A", "5V"), ("B", "GND"), ("C", "1OE|VCC"), ("D", "1A|VCC"), ("E", "DIN|1Y|VCC"),
              ("F", "VCC"), ("G", "VCC"), ("H", "VCC"), ("I", "GND"), ("J", "TX"))
UNI_CUTS = (("A", 5), ("E", 5), ("C", 10), ("D", 10), ("E", 10))     # strip, row: copper cut at that hole
UNI_DIP = ("C", 9, 12)          # U1: pin 1 at strip C row 9, pins 1-7 on C-I row 9, pins 14-8 on C-I row 12
UNI_AXIAL = (("F", "A", 3, 7), ("R", "E", 3, 7))                     # lie flat along the strip, across its cut
UNI_STANDING = (("R2", "C", "D", 4),)   # axial stood on end: body over the first hole, lead bent over to the second
UNI_RADIAL = (("C2", "A", "B", 2, ""), ("C1", "A", "B", 8, "+"), ("C3", "H", "I", 7, ""))
UNI_LINKS = ((("B", 7), ("C", 7), "bare"), (("C", 13), ("H", 13), "bare"),     # 1OE to GND; VCC bar C-H
             (("A", 14), ("C", 14), "insulated"), (("I", 15), ("B", 15), "insulated"))  # 5V in -> VCC; U1 GND -> GND
UNI_WIRES = (           # tag, strip, row, colour, where it goes
    (1, "A", 1, "red", "LED strip 5V (fused)"),
    (2, "B", 1, "black", "LED strip GND"),
    (3, "E", 1, "green", "LED strip DIN"),
    (4, "D", 6, "green", f"ESP32 GPIO{LED_DATA_GPIO} (LED data out, 3.3 V)"),
    (5, "A", 16, "red", "S0 XIAO 5V (JST 1)"), (6, "B", 16, "black", "S0 GND (JST 2)"),
    (7, "J", 16, "green", "S0 D7 RX (JST 4)"),
    (8, "A", 17, "red", "S1 XIAO 5V"), (9, "B", 17, "black", "S1 GND"), (10, "J", 17, "green", "S1 D7 RX"),
    (11, "A", 18, "red", "S2 XIAO 5V"), (12, "B", 18, "black", "S2 GND"), (13, "J", 18, "green", "S2 D7 RX"),
    (14, "B", 19, "black", "ESP32 GND (header pin 38)"),
    (15, "J", 19, "green", "ESP32 GPIO21 TX (header pin 35)"),
    (16, "A", 20, "red", "USB-C socket pigtail + (PoE splitter in)"),
    (17, "B", 20, "black", "USB-C socket pigtail -"),
    (18, "A", 21, "red", "USB-C plug pigtail + (to ESP32 USB-C)"),
    (19, "B", 21, "black", "USB-C plug pigtail -"),
)


def uni_page(c):
    x0, y0, p = UNI_PAGE
    nstrips, nrows = UNI_SIZE
    letters = [s for s, _ in UNI_STRIPS]
    top = PAGE_H / mm

    def at(strip, row):
        return x0 + letters.index(strip) * p, y0 - row * p

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (top - 15) * mm, "Option: unified power + LED board (pipe build)")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (top - 21) * mm,
                 "One stripboard instead of the bus board (page 6) and the LED power board (page 7). Not to scale: "
                 "component side, strips vertical.")
    c.drawString(15 * mm, (top - 25.5) * mm,
                 f"Cut {nstrips} strips x {nrows} holes ({nstrips * UNI_PITCH:.1f} x {nrows * UNI_PITCH:.1f} mm). "
                 "Hangs on the pipe at 11 o'clock, row 0 up (toward the deck), copper side to the pipe.")

    # board, strips (copper is underneath: drawn faint), holes, labels
    c.setStrokeGray(0.4)
    c.setLineWidth(0.6)
    c.rect((x0 - p * 0.7) * mm, (y0 - (nrows - 1) * p - p * 0.7) * mm,
           ((nstrips - 1) * p + 1.4 * p) * mm, ((nrows - 1) * p + 1.4 * p) * mm)
    c.setStrokeColorRGB(0.93, 0.8, 0.65)
    c.setLineWidth(p * 0.75 * mm)
    for k in range(nstrips):
        c.line((x0 + k * p) * mm, y0 * mm, (x0 + k * p) * mm, (y0 - (nrows - 1) * p) * mm)
    c.setStrokeGray(0.55)
    c.setLineWidth(0.3)
    c.setFillGray(1)
    for k in range(nstrips):
        for r in range(nrows):
            c.circle((x0 + k * p) * mm, (y0 - r * p) * mm, 0.45 * mm, fill=1)
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 8)
    for k, (s, net) in enumerate(UNI_STRIPS):
        c.drawCentredString((x0 + k * p) * mm, (y0 + p * 0.9) * mm, s)
    c.setFont("Helvetica", 5.5)
    for r in range(nrows):
        c.drawRightString((x0 - p * 0.9) * mm, (y0 - r * p - 0.7) * mm, str(r))
    c.setFont("Helvetica-Oblique", 6)
    c.drawString((x0 - p * 0.7) * mm, (y0 + p * 1.9) * mm, "toward the deck")

    # links: bare grey, insulated blue
    for (s1, r1), (s2, r2), kind in UNI_LINKS:
        (xa, ya), (xb, yb) = at(s1, r1), at(s2, r2)
        if kind == "bare":
            c.setStrokeGray(0.35)
            c.setLineWidth(1.6)
            c.line(xa * mm, ya * mm, xb * mm, yb * mm)
        else:
            c.setStrokeColorRGB(0.1, 0.35, 0.8)
            c.setLineWidth(1.6)
            path = c.beginPath()
            path.moveTo(xa * mm, ya * mm)
            path.curveTo(xa * mm, (ya - p * 0.6) * mm, xb * mm, (yb - p * 0.6) * mm, xb * mm, yb * mm)
            c.drawPath(path)
        c.setFillGray(0.2)
        for x, y in ((xa, ya), (xb, yb)):
            c.circle(x * mm, y * mm, 0.6 * mm, fill=1, stroke=0)

    # U1
    s, r1, r2 = UNI_DIP
    (xa, ya), (xb, yb) = at(s, r1), at(letters[letters.index(s) + 6], r2)
    c.setStrokeGray(0)
    c.setLineWidth(0.8)
    c.setFillGray(0.25)
    c.rect((xa - p * 0.45) * mm, (yb + p * 0.35) * mm, (xb - xa + p * 0.9) * mm, (ya - yb - p * 0.7) * mm, fill=1)
    c.setFillGray(1)
    c.circle((xa - p * 0.45) * mm, ((ya + yb) / 2) * mm, p * 0.3 * mm, fill=1, stroke=0)   # pin-1 end notch
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(((xa + xb) / 2) * mm, ((ya + yb) / 2 - 1) * mm, "U1  74HCT125")
    c.setFillGray(0)
    c.setFont("Helvetica", 4.8)
    names = ("1OE", "1A", "1Y", "2OE", "2A", "2Y", "GND", "3Y", "3A", "3OE", "4Y", "4A", "4OE", "VCC")
    for k in range(7):
        x = xa + k * p
        c.setFillGray(0)
        c.circle(x * mm, ya * mm, 0.55 * mm, fill=1, stroke=0)
        c.circle(x * mm, yb * mm, 0.55 * mm, fill=1, stroke=0)
        for yy, n, up in ((ya, k + 1, True), (yb, 14 - k, False)):
            c.saveState()
            c.translate(x * mm, (yy + (1.0 if up else -1.0)) * mm)
            c.rotate(90)
            (c.drawString if up else c.drawRightString)(0, 1.6, f"{n} {names[n - 1]}")
            c.restoreState()

    # axial parts along their strip, across the cut
    for ref, s, r1, r2 in UNI_AXIAL:
        (x, ya), (_, yb) = at(s, r1), at(s, r2)
        c.setStrokeGray(0)
        c.setLineWidth(0.7)
        c.line(x * mm, ya * mm, x * mm, yb * mm)
        c.setFillColorRGB(0.95, 0.9, 0.75) if ref == "F" else c.setFillColorRGB(0.8, 0.88, 0.98)
        c.roundRect((x - p * 0.33) * mm, (yb + p * 0.8) * mm, p * 0.66 * mm, (ya - yb - p * 1.6) * mm, 0.8 * mm, fill=1)
        c.setFillGray(0)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString((x + p * 0.42) * mm, ((ya + yb) / 2 - 1) * mm, ref)

    # radial parts across two neighbouring strips
    for ref, s1, s2, r, pol in UNI_RADIAL:
        (xa, y), (xb, _) = at(s1, r), at(s2, r)
        c.setStrokeGray(0)
        c.setLineWidth(0.7)
        big = ref == "C1"
        c.setFillColorRGB(0.85, 0.85, 0.85) if big else c.setFillColorRGB(1, 0.92, 0.6)
        if big:
            c.circle(((xa + xb) / 2) * mm, (y + p * 0.15) * mm, p * 0.7 * mm, fill=1)
        else:
            c.roundRect((xa - p * 0.15) * mm, (y - p * 0.3) * mm, (xb - xa + p * 0.3) * mm, p * 0.6 * mm, 1 * mm, fill=1)
        c.setFillGray(0)
        c.circle(xa * mm, y * mm, 0.5 * mm, fill=1, stroke=0)
        c.circle(xb * mm, y * mm, 0.5 * mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 6)
        if big:
            c.drawRightString((xa - p * 0.75) * mm, (y + p * 0.3) * mm, ref)
        else:
            c.drawCentredString(((xa + xb) / 2) * mm, (y + p * 0.42) * mm, ref)
        if pol:
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString((xa - p * 0.75) * mm, (y - 2.2) * mm, pol)

    # standing axial parts: body over the first hole, bent lead to the second
    for ref, s1, s2, r in UNI_STANDING:
        (xa, y), (xb, _) = at(s1, r), at(s2, r)
        c.setStrokeGray(0)
        c.setLineWidth(0.7)
        c.line(xa * mm, y * mm, xb * mm, y * mm)
        c.setFillColorRGB(0.8, 0.88, 0.98)
        c.circle(xa * mm, y * mm, p * 0.38 * mm, fill=1)
        c.setFillGray(0)
        c.circle(xb * mm, y * mm, 0.5 * mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(((xa + xb) / 2) * mm, (y + p * 0.5) * mm, ref)

    # off-board wires: coloured ring + tag at the hole
    cols = {"red": RED, "black": BLACK, "green": GREEN}
    for tag, s, r, colour, _ in UNI_WIRES:
        x, y = at(s, r)
        c.setStrokeColorRGB(*cols[colour])
        c.setLineWidth(1.3)
        c.setFillGray(1)
        c.circle(x * mm, y * mm, p * 0.36 * mm, fill=1)
        c.setFillColorRGB(*cols[colour])
        c.setFont("Helvetica-Bold", 5.2)
        c.drawCentredString(x * mm, (y - 0.9) * mm, str(tag))
    c.setFillGray(0)
    c.setStrokeGray(0)

    # cuts, on top of the parts that hide them (copper side)
    c.setStrokeColorRGB(0.8, 0, 0)
    c.setLineWidth(1.5)
    for s, r in UNI_CUTS:
        x, y = at(s, r)
        d = p * 0.32
        c.line((x - d) * mm, (y - d) * mm, (x + d) * mm, (y + d) * mm)
        c.line((x - d) * mm, (y + d) * mm, (x + d) * mm, (y - d) * mm)

    c.setStrokeGray(0)

    # strip nets and wire tags, right of the board
    lx = x0 + (nstrips - 1) * p + 12
    y = y0 + 2
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(lx * mm, y * mm, "Nets")
    y -= 4.4
    c.setFont("Helvetica", 7.2)
    for line in (
            "A  5V. Rows 0-4: fused 5 V to the strip (after F). Rows 6-22: 5 V in from the splitter,",
            "     which also feeds the ESP32 (plug pigtail) and the three XIAOs. Cut at A5.",
            "B  GND.   J  TX bus: ESP32 GPIO21 to every XIAO's D7.",
            "C-I  U1. Rows 0-9 above the chip, 12-22 below; C, D and E cut at row 10 under U1.",
            "     C top: 1OE, linked to B (row 7): gate 1 always on (also R2's GND end).",
            "     D top: 1A, from GPIO1; R2 (standing, C4-D4) pulls it to GND.",
            "     E: 1Y (rows 6-9), R across the cut at E5, DIN (rows 0-4).",
            "     C, D, E below U1 and F, G, H: VCC, joined by the bare bar on row 13 and fed",
            "     from A by the insulated link on row 14. I: U1 GND, to B by the insulated link on row 15.",
            "Gates 2-4 are off: their OE pins and inputs sit on VCC, outputs on VCC or GND (3-state).",
    ):
        c.drawString(lx * mm, y * mm, line)
        y -= 3.6
    y -= 2
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(lx * mm, y * mm, "Wires (numbered rings)")
    y -= 4.4
    c.setFont("Helvetica", 7.2)
    for tag, s, r, colour, what in UNI_WIRES:
        c.setFillColorRGB(*cols[colour])
        c.drawString(lx * mm, y * mm, f"{tag:>2}")
        c.setFillGray(0)
        c.drawString((lx + 5) * mm, y * mm, f"{s}{r}  {colour:<5}  {what}")
        y -= 3.4
    y -= 1.5
    c.setFont("Helvetica-Oblique", 6.8)
    for line in ("The yellow DATA wires don't touch this board: head S0 D10 runs to ESP32 GPIO17, S1 / S2 D10 to the",
                 "head's D0 / D1 (page 6). The ESP32 VBUS (pin 40) wire is not used: the XIAOs are on the splitter rail."):
        c.drawString(lx * mm, y * mm, line)
        y -= 3.3

    # legend
    y -= 2
    c.setFont("Helvetica", 6.8)
    c.setStrokeColorRGB(0.8, 0, 0)
    c.setLineWidth(1)
    c.line(lx * mm, (y + 0.6) * mm, (lx + 2.2) * mm, (y + 2.8) * mm)
    c.line(lx * mm, (y + 2.8) * mm, (lx + 2.2) * mm, (y + 0.6) * mm)
    c.drawString((lx + 4) * mm, y * mm, "track cut (5)")
    c.setStrokeGray(0.35)
    c.setLineWidth(1.6)
    c.line((lx + 24) * mm, (y + 1.7) * mm, (lx + 29) * mm, (y + 1.7) * mm)
    c.drawString((lx + 31) * mm, y * mm, "bare link")
    c.setStrokeColorRGB(0.1, 0.35, 0.8)
    c.line((lx + 46) * mm, (y + 1.7) * mm, (lx + 51) * mm, (y + 1.7) * mm)
    c.drawString((lx + 53) * mm, y * mm, "insulated link")
    c.setStrokeGray(0)

    # parts and notes, under the board
    yb = y0 - (nrows - 1) * p - 9
    text = [("B", "Parts (through-hole)")]
    for ref, (part, what) in UNI_PARTS.items():
        text.append(("", f"{ref:<4} {part}: {what}."))
    text += [
        ("", "Also: a USB-C socket pigtail and a USB-C plug pigtail (2-wire), bare tinned wire for the links"),
        ("", "and the strip reinforcement, insulated wire for the two long links, 2 x 150 mm ties and a thin insulating spacer."),
        ("", ""),
        ("B", "Notes"),
        ("", "Cut the five tracks and check each with a meter before fitting parts. Fit U1 last, or in a socket."),
        ("", "Solder bare tinned wire along A6-A22 and B0-B22: they carry the strip's current (up to ~1.5 A). Use 22-24 AWG"),
        ("", "for the pigtails and the strip's 5V and GND; the harness wire is fine for the XIAOs and data."),
        ("", "Before fitting U1, plug the splitter into the socket pigtail and meter A to B: +5 V; C, D, E (below U1) and F-H"),
        ("", "should read 5 V too. Then fit U1 and check: GPIO1 wire unplugged -> E1 low (R2); GPIO1 low -> E1 low;"),
        ("", "GPIO1 high -> E1 at about 5 V."),
        ("", "Insulating spacer between the copper and the pipe (needed on EMT). The separate boards on pages 6 and 7 still work."),
        ("", "Accepted risk (user, 2026-11-20): a short on the strip does not blow F. The splitter current-limits first (~2.6 A"),
        ("", "est.), F carries ~115% of its rating, the 5 V rail falls to ~0.35 V and the mast reboots until the short is cleared"),
        ("", "(sim/run_sim.py, strip_short). Fix if it matters: a 1 A fuse with a 0.8 A firmware cap, or an eFuse on the strip feed."),
    ]
    y = yb
    for style, s in text:
        c.setFont("Helvetica-Bold" if style == "B" else "Helvetica", 8)
        c.drawString(15 * mm, y * mm, s)
        y -= 4.1


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
                 f"NO-PIPE electronics plate (split) - {PLATE_DIAMETER:g} mm disc - PRINT AT 100% (Actual size)")
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
    for d, x, y, lab in deck_refs():
        c.circle(*P(x, y), d / 2 * mm)
        c.drawCentredString(*P(x, y + (d / 2 - 2.5 if lab.startswith("deck centre") else -1)), lab)
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
            ant_label(c, P, x, y, d, tag)
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
        "Positions: parameters.csv (lay out in plate_layout.svg). The ESP32 clears the deck's centre hole and M3 bolts (grey).",
        "OPTIONS (builder's choice): this no-pipe split plate or the pipe plate (page 2). Wiring: page 6.",
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (61 - n * 3.9) * mm, t)


# Pipe plate (2026-11-01, called the flange plate until the flange was dropped 2026-11-09): the PoE splitter and
# ESP32 hang inside the core on a 1/2" pipe whose male adapter is clamped through the plate's centre (adapter_trace),
# so the plate carries only the three XIAOs and the bus board, on top, in the ring between the nut and the rim. Each XIAO sits beside its own sector axis (FL_XIAO_DA, clear of the antenna holes), between the M4 bolts, long axis
# turned FL_XIAO_ROT off radial (nearly along the rim since P2 moved in, 2026-11-10). No pigtail hole (user, 2026-11-10): the coax runs flat from
# IPEX4 to a 1/2" (12.5 mm) HS-100 adhesive tie mount past the IPEX4 end, then down its sector's nearest antenna
# hole to the deck jack. 5V / GND / D7 run over the top to the bus board; D8 (TX) runs over the top to the feed hole and
# down it to its ESP32 RX pin in the core, beside TX, GND and VBUS coming up to the bus. The pipe carries the ESP antenna's
# pigtail and is capped (stack views), so the PoE cable passes the plate rim instead.
FL_UNDER_SIDE = -FL_IPEX_SIDE  # the XIAOs hang component side down under the plate (user, 2026-11-10), so seen
                               # from the top through the plate the IPEX4 is on the other side
# No feed hole since 2026-11-10: the bus is under the plate, so TX, GND, VBUS and the three D8 TX wires pass the deck's
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


def deck_refs():
    """Deck parts under the no-pipe plate, plate frame, drawn for reference (2026-11-24, page 1's deck): the centre
    hole and the M3 collar bolts with their washer keep-out. [(diameter, x, y, label)]"""
    L = layout.Layout(layout.VARIANTS[0])
    out = [(L.pipe_d, 0.0, 0.0, f"deck centre {L.pipe_d:g} mm")]
    return out + [(M3_KEEPOUT, *to_plate(x, y), "deck M3") for x, y in L.m3()]


def ant_label(c, P, x, y, d, tag):
    """Antenna reference hole label beside the hole, across its sector axis (D / P / D15 sit in a row along it): to
    alternating sides so neighbours' labels don't meet: P and the outer D on the clockwise side, the inner D on the
    other, P2 on its far side, away from the axis."""
    i = int(tag[1])
    kind = tag.split()[1]
    nx, ny = to_plate(*layout.xy(layout.SECTORS[i], 1.0, 0.0))
    if kind == "P2" or kind == f"D{layout.VARIANTS[0]:g}":
        nx, ny = -nx, -ny
    k = d / 2 + (1.5 if abs(nx) > 0.5 else 3.2)
    px, py = P(x + nx * k, y + ny * k - 1)
    text = f"{tag[:-4]} ref"
    if abs(nx) <= 0.5:
        c.drawCentredString(px, py, text)
    elif nx > 0:
        c.drawString(px, py, text)
    else:
        c.drawRightString(px, py, text)


def plate_antenna_holes():
    """The deck's 6.5 mm antenna jack holes (D, P, P2) in the plate frame, drawn dotted on both plates for reference
    so deck, plate and every page line up; they can be drilled but are not by design (user, 2026-11-10).
    Both duck spacings (2026-11-24): D15 (closer to the face) and D31, from layout.py like the deck page."""
    out = []
    for i, s in enumerate(layout.SECTORS):
        for kind, x, y in deck_antenna_holes(s):
            out.append((HOLE_RPSMA, *to_plate(x, y), f"S{i} {kind} ant"))
    return out


def deck_antenna_holes(s):
    """[(kind, x, y)] deck top view, for sector angle s: D for every duck spacing (D15, D31), then P and P2."""
    out = [(f"D{v:g}", *layout.Layout(v).hole("D", s)) for v in layout.VARIANTS]
    L = layout.Layout(layout.VARIANTS[0])
    return out + [(k, *L.hole(k, s)) for k in ("P", "P2")]


def to_plate(x, y):
    """Deck top view (S0 up) -> plate frame (plate 12 o'clock up, S0 PLATE_TURN deg clockwise of it)."""
    t = math.radians(PLATE_TURN)
    return x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)


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
            ant_label(c, P, x, y, d, tag)
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
        "jacks is in use, straight below its hole. 5V, GND, D7 to the bus beside them; star wiring (page 6): head S0 D10 down",
        "the deck's centre hole to ESP32 GPIO17 beside TX, GND, VBUS coming up; S1 / S2 D10 soldered to the head's D0 / D1.",
        "Seen from the top the IPEX4 is on the left (the board is flipped).",
        "OPTIONS (builder's choice): this pipe plate or the no-pipe split plate (page 3); bus board under the plate by the adapter,",
        "or on the pipe inside the core (page 5: then skip the bus M3).",
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (59 - n * 3.4) * mm, t)


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
                 "Hanging from the ceiling, top down: nut, enclosure top, module plate, modules, deck, core, ESP antenna. Frame: page 2.")

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
        "module plate and the enclosure top; the nut on top clamps both. Modules and the bus hang under the plate (page 2).",
        "OPTION: the bus board can go on the pipe (dashed, 11 o'clock, opposite the ESP32 and splitter) instead of on the plate.",
        "Side: dashed box = PoE splitter, behind the cut. XIAOs, tie mounts: as page 2. Estimates: adapter, nut,",
        "enclosure top, splitter size, board depths, antenna length.",
        "EU parts: 20 mm PVC-U pressure pipe (20 mm OD, 1.3 mm under 1/2\" Sch 40; same holes), a 20 mm solvent-weld end cap,",
        "a 20 mm x 1/2\" BSP male adaptor and a 1/2\" BSP backnut, and a 57 mm hole saw for the deck. The RP-SMA bulkhead's",
        "thread is 1/4\"-36 UNS everywhere: if that tap is hard to find, drill the cap 6.5 mm and use the bulkhead's own nut.",
    ]
    for n, t in enumerate(notes):
        c.drawString(15 * mm, (72 - n * 3.6) * mm, t)

    emt_notes = [                              # EMT option, in the free space right of the antenna line
        "OPTION: 1/2\" EMT (steel conduit) instead of the PVC",
        f"EMT: {EMT_OD:g} mm OD, {EMT_ID:g} mm bore (PVC: {PIPE_OD:g} / {PIPE_ID:g} mm).",
        "Set-screw or compression connector + locknut in the",
        f"same 7/8\" ({ADAPTER_HOLE:g} mm) hole; the deck hole stays.",
        f"RJ45: a crimped head only just fits the {EMT_ID:g} mm bore",
        "(check the connector's throat too). Make sure there is",
        "NO boot or crimp sleeve on the plug going through.",
        "Bond the tube to the deck all round where it passes:",
        "copper collar, ground clamp + braid, or conductive",
        "copper tape (solder won't take on galvanized steel).",
        "ESP antenna: plastic cap or bushing, not bare steel.",
        "Bushing on every cut or drilled hole a cable passes",
        "near or through (side slot, tube ends), even deburred.",
        "Outdoors: seal the zinc-copper bond (corrosion).",
        "The drawing shows the PVC pipe.",
    ]
    c.setFont("Helvetica-Bold", 7)
    c.drawString(143 * mm, 128.5 * mm, emt_notes[0])
    c.setFont("Helvetica", 7)
    for n, t in enumerate(emt_notes[1:], 1):
        c.drawString(143 * mm, (128.5 - n * 3.4) * mm, t)

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


LIGHT_MM_PER_NS = 299.792458            # speed of light: wavelength in mm = this / frequency in GHz
DIM_INK = (0.1, 0.35, 0.7)
COPPER_INK = (0.72, 0.42, 0.15)


def _poly(c, pts, close=True):
    path = c.beginPath()
    path.moveTo(pts[0][0] * mm, pts[0][1] * mm)
    for x, y in pts[1:]:
        path.lineTo(x * mm, y * mm)
    if close:
        path.close()
    c.drawPath(path)


def deck_page(c):
    """Deck drill template, both duck spacings on one page (user, 2026-11-24: pages for d15 / d31 merged, no radio
    placement). Drawn in the plate frame (plate 12 o'clock up, S0 PLATE_TURN deg clockwise of it), so every hole lines
    up with the plates' dotted reference holes. Holes and outlines from layout.py, as the PCB decks."""
    Ls = [layout.Layout(v) for v in layout.VARIANTS]
    L = Ls[0]
    big = max(Ls, key=lambda x: x.deck_d)
    cx, cy = PAGE_W / mm / 2, 140.0                    # deck centre on the page

    def Q(x, y):                                       # deck top view -> page
        px, py = to_plate(x, y)
        return cx + px, cy + py

    def F(t, u, v):                                    # corner / sector frame -> page
        return Q(*layout.xy(t, u, v))

    def hole(x, y, d):
        px, py = Q(x, y)
        c.setLineWidth(0.5)
        c.circle(px * mm, py * mm, d / 2 * mm)
        c.setLineWidth(0.2)
        crosshair(c, px, py, d / 2)
        return px, py

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm,
                 f"Deck drill template - {' / '.join(f'{v:g}' for v in layout.VARIANTS)} mm ducks - "
                 "PRINT AT 100% (Actual size)")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Viewed from the TOP. Tape to the board, centre-punch each crosshair you need, then drill. "
                 "Same frame as the plates (pages 2 and 3).")
    scale_bar(c, 15, PAGE_H / mm - 32)

    for Lv in sorted(Ls, key=lambda x: -x.deck_d):     # cut lines: largest solid, the others dashed
        c.setLineWidth(0.8 if Lv is big else 0.5)
        if Lv is not big:
            c.setDash(4, 2)
        c.circle(cx * mm, cy * mm, Lv.deck_r * mm)
        c.setDash()
    lab = [f"{Lv.deck_d:g} mm ({Lv.spacing:g} mm ducks)" for Lv in sorted(Ls, key=lambda x: -x.deck_d)]
    c.setFont("Helvetica", 6.5)
    lx, ly = cx + big.deck_r * math.sin(math.radians(205)), cy + big.deck_r * math.cos(math.radians(205))
    c.drawRightString((lx - 2) * mm, (ly - 1) * mm, "cut: " + " / ".join(lab))

    hole(0, 0, L.pipe_d)                               # pipe hole
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(cx * mm, (cy - L.pipe_d / 2 - 3.5) * mm, f"pipe {L.pipe_d:g} (7/8 in)")
    saw = PIPE_SAW                                     # pipe build: 2-1/4 in hole saw round the same centre (re-added
    c.setLineWidth(0.6)                                # 2026-11-24): splitter and ESP32 pass into the core
    c.circle(cx * mm, cy * mm, saw / 2 * mm)
    c.drawCentredString(cx * mm, (cy - saw / 2 + 1.5) * mm, f"pipe build: 2-1/4 in hole saw ({saw:.1f})")

    c.saveState()                                      # faces: copper side out on this line
    c.setStrokeColorRGB(*COPPER_INK)
    c.setLineWidth(1.0)
    _poly(c, [Q(*layout.pol(L.r_c, v)) for v in layout.VERTICES])
    c.restoreState()

    for i, s in enumerate(layout.SECTORS):             # antenna jacks: D per duck spacing, P, P2
        for kind, x, y in deck_antenna_holes(s):
            hole(x, y, HOLE_RPSMA)
            u, v = layout.frame(s, x, y)
            px, py = F(s, u - 6.0, v) if kind != "P2" else F(s, u, v + 6.0)
            c.setFont("Helvetica-Bold", 6.5)
            if kind == "P2":
                c.drawCentredString(px * mm, (py - 1) * mm, kind)
            else:
                c.drawRightString((px + 1.5) * mm, (py - 1) * mm, kind)
        lx, ly = F(s, 11.0, L.r_P + 4)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(lx * mm, (ly - 1.5) * mm, f"S{i}")
        arrow = [F(s, dx, L.r_in - 14 + dy) for dx, dy in ((-3, -3), (0, 3), (3, -3))]   # S0 arrow, pointing out
        c.setLineWidth(0.6)
        for (x0, y0), (x1, y1) in zip(arrow, arrow[1:]):
            if i == 0:                                 # S0 arrow only
                c.line(x0 * mm, y0 * mm, x1 * mm, y1 * mm)

    for x, y in L.m3():                                # M3 collar registration, washer keep-out dashed
        px, py = hole(x, y, COLLAR_HOLE)
        c.setDash(1.5, 1.5)
        c.circle(px * mm, py * mm, M3_KEEPOUT / 2 * mm)
        c.setDash()
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(px * mm, (py + M3_KEEPOUT / 2 + 1) * mm, f"M3 {COLLAR_HOLE:g}")

    hr = g.NUT_AF / math.sqrt(3)                       # core-corner M4: the plate's bolts, nut in the corner
    for t in layout.VERTICES:
        px, py = hole(*layout.pol(L.m4_r, t), g.HOLE_M4)
        c.setDash(1.5, 1.5)
        _poly(c, [(px + hr * math.sin(math.radians(a)), py + hr * math.cos(math.radians(a)))
                  for a in range(30, 390, 60)])
        c.setDash()
        lx, ly = F(t, 0, L.m4_r - 9.0)
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(lx * mm, (ly - 1) * mm, f"M4 {g.HOLE_M4:g}")

    c.setFont("Helvetica", 8.5)
    ducks = " / ".join(f"D{Lv.spacing:g} = duck {Lv.spacing:g} mm" for Lv in Ls)
    lines = [
        "Solid circle = cut line " + f"({big.deck_d:g} mm, fits both duck spacings); dashed = " +
        ", ".join(f"{Lv.deck_d:g} mm" for Lv in Ls if Lv is not big) + " if you only use the "
        + ", ".join(f"{Lv.spacing:g}" for Lv in Ls if Lv is not big) + " mm ducks.",
        f"Copper triangle = the faces' outer (copper) surface: stand each {FACE_WIDTH:g} x {FACE_H:g} mm face on its "
        "line, copper out, butt the",
        "corners together and solder or copper-tape the seams.",
        f"Antenna jacks, RP-SMA {HOLE_RPSMA:g} mm, drill ONE per sector for the antenna you fit: {ducks} in front of "
        "the face,",
        f"P / P2 = patch {PATCH_OFFSET:g} mm in front (P2 {L.s_P2:g} mm along the face). D{layout.VARIANTS[0]:g} and "
        "P are close: never drill both.",
        f"Centre: pipe build 2-1/4 in ({PIPE_SAW:.1f} mm) hole saw, for the splitter and ESP32 (page 5); "
        f"otherwise {L.pipe_d:g} mm (1/2 in PVC adapter).",
        f"M3 {COLLAR_HOLE:g} mm x3 = registration to the collar (dashed: {M3_KEEPOUT:g} mm washer keep-out); the "
        "2-1/4 in hole cuts them away.",
        f"M4 {g.HOLE_M4:g} mm x3 in the core corners = bolts + spacers for the electronics plate (pages 2 and 3), nut "
        "in the corner (dashed hex).",
        f"Turned like the plates: plate 12 o'clock up, S0 arrow {PLATE_TURN:g} deg clockwise of it, so the plates' "
        "dotted holes sit on these.",
        "Every number: common/layout.py and parameters.csv (formulas page).",
    ]
    for n, t in enumerate(lines):
        c.drawString(15 * mm, (58 - n * 4.4) * mm, t)


def face_page(c):
    L0 = layout.Layout(layout.VARIANTS[0])
    x0 = PAGE_W / mm / 2 - FACE_WIDTH / 2
    top = PAGE_H / mm - 45
    xc = x0 + FACE_WIDTH / 2

    def Y(d):                      # mm below the top (deck) edge -> page y
        return top - d

    c.setFont("Helvetica-Bold", 13)
    c.drawString(15 * mm, (PAGE_H / mm - 15) * mm,
                 f"Face (reflector) template - {FACE_WIDTH:g} x {FACE_H:g} mm - PRINT AT 100%")
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, (PAGE_H / mm - 21) * mm,
                 "Make 3 from copper-clad board. Viewed from the FRONT (copper side, facing the antenna). "
                 f"{DIPOLE_HOLE:g} mm centre hole. Top edge to the deck.")
    scale_bar(c, 15, PAGE_H / mm - 32)

    c.setLineWidth(0.8)
    c.rect(x0 * mm, Y(FACE_H) * mm, FACE_WIDTH * mm, FACE_H * mm)   # cut line
    c.setLineWidth(0.2)
    c.setDash(1, 2)
    c.line(xc * mm, Y(0) * mm, xc * mm, Y(FACE_H) * mm)               # centre line
    c.setDash()
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(xc * mm, (Y(0) + 2) * mm, "TOP - against the deck")
    # centre hole: RP-SMA bulkhead for a dipole or the printed fin's feed
    c.setLineWidth(0.5)
    c.circle(xc * mm, Y(FACE_H / 2) * mm, DIPOLE_HOLE / 2 * mm)
    crosshair(c, xc, Y(FACE_H / 2), DIPOLE_HOLE / 2)
    c.setFont("Helvetica", 7)
    c.drawString((xc + DIPOLE_HOLE / 2 + 3) * mm, (Y(FACE_H / 2) + 1) * mm, f"Centre {DIPOLE_HOLE:g} mm: RP-SMA bulkhead")
    c.drawString((xc + DIPOLE_HOLE / 2 + 3) * mm, (Y(FACE_H / 2) - 2.5) * mm, "(dipole or printed fin feed)")
    # where the deck's antenna jacks sit in front of this face: P (and D) over the centre, P2 toward one end
    c.setLineWidth(0.4)
    c.setFont("Helvetica", 6.5)
    for jx, name in ((0, "D / P jacks above"), (L0.s_P2, "P2 jack above")):
        c.line((xc + jx) * mm, Y(0) * mm, (xc + jx) * mm, Y(4) * mm)
        c.drawString((xc + jx + 1) * mm, Y(4) * mm, name)
    c.setFont("Helvetica", 8)
    c.drawCentredString(xc * mm, (Y(FACE_H) - 6) * mm, f"{FACE_WIDTH:g} mm")
    c.drawString((x0 + FACE_WIDTH + 4) * mm, (Y(FACE_H / 2)) * mm, f"{FACE_H:g} mm")

    c.setFont("Helvetica", 8.5)
    lines = [
        "Plain butt joints: the three faces stand on the deck's copper triangle, corners touching, and are soldered or",
        "copper-taped along each seam (inside, outside or both; tack-solder tape every 10-15 mm). The PCB faces have",
        "tabs; this cut-by-hand face doesn't need them, the finished triangle is the same.",
        f"Whips hang on the deck's D holes in front of the face (page 1); P / P2 hold a patch {PATCH_OFFSET:g} mm "
        "in front of it.",
        f"Centre {DIPOLE_HOLE:g} mm hole: RP-SMA bulkhead for an antenna on the face (dipole or the printed fin); the nut",
        "goes on the inside, so keep it clear of anything mounted inside the core. No other holes in the face.",
    ]
    for n, t in enumerate(lines):
        c.drawString(15 * mm, (Y(FACE_H) - 16 - n * 4.4) * mm, t)


def formulas_page(c):
    """Design formulas (common/formulas_page.py), without the PCB deck's radio placement: that page, with the radios,
    is in builds/pcb/out/pcb_print_1to1.pdf."""
    formulas_page_draw(c, radios=False, title="Design formulas - hand build (NOT a template, not to size)")

BUILD_TAGS = {           # which build type each page belongs to (user, 2026-11-10): builders pick one, alt or pipe
    deck_page: ("BOTH BUILDS", "pipe and no pipe, both duck spacings", (0.3, 0.3, 0.3)),
    alt_plate_page: ("NO PIPE", "pick one: pipe or no pipe", (0.1, 0.35, 0.7)),
    fl_plate_page: ("PIPE BUILD ONLY", "pick one: pipe or no pipe", (0.1, 0.5, 0.25)),
    face_page: ("BOTH BUILDS", "pipe and no pipe", (0.3, 0.3, 0.3)),
    stack_page: ("PIPE BUILD ONLY", "pick one: pipe or no pipe", (0.1, 0.5, 0.25)),
    wiring_page: ("BOTH BUILDS", "pipe and no pipe", (0.3, 0.3, 0.3)),
    led_page: ("OPTION", "LED direction ring; pipe and no pipe", (0.55, 0.35, 0.05)),
    uni_page: ("OPTION", "unified power + LED board; pipe build", (0.55, 0.35, 0.05)),
    formulas_page: ("REFERENCE", "no radio placement (PCB PDF); no need to print", (0.3, 0.3, 0.3)),
}


def build_tag(c, page, n):
    """Box naming the build type the page is for, plus the page set of each build. Right of the scale bar,
    below the titles; on the wiring page (no room there) beside the title."""
    head, sub, rgb = BUILD_TAGS[page]
    sets = "Pipe: pages 1, 2, 4, 5, 6   No pipe: pages 1, 3, 4, 6"
    x1 = PAGE_W - 12 * mm
    y1 = PAGE_H - (6.5 if page in (wiring_page, led_page, uni_page) else 27.5) * mm
    w = max(c.stringWidth(head, "Helvetica-Bold", 8.5), c.stringWidth(sub, "Helvetica", 6),
            c.stringWidth(sets, "Helvetica", 6)) + 4 * mm
    h = 10 * mm
    c.saveState()
    c.setStrokeColorRGB(*rgb)
    c.setLineWidth(1)
    c.setFillColorRGB(*(1 - (1 - v) * 0.1 for v in rgb))
    c.roundRect(x1 - w, y1 - h, w, h, 1.5 * mm, fill=1)
    c.setFillColorRGB(*rgb)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x1 - w + 2 * mm, y1 - 3.6 * mm, head)
    c.setFont("Helvetica", 6)
    c.drawString(x1 - w + 2 * mm, y1 - 6.3 * mm, sub)
    c.setFillGray(0.3)
    c.drawString(x1 - w + 2 * mm, y1 - 8.8 * mm, sets)
    c.restoreState()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "hand_build_shield_deck_templates.pdf")
    c = canvas.Canvas(out, pagesize=letter)
    c.setTitle("Shield deck, back panel, electronics plate templates and plate wiring")
    # drill templates first (deck, plates, back panel), then the stack view and wiring diagram (user, 2026-11-09),
    # the LED direction ring option after the wiring it adds to (2026-11-16), then the unified power + LED board
    # option that can replace the bus and LED boards (2026-11-20), design formulas at the very end as a
    # reference page (2026-11-12)
    pages = (deck_page, fl_plate_page, alt_plate_page, face_page, stack_page, wiring_page, led_page, uni_page,
             formulas_page)
    for n, page in enumerate(pages, 1):
        page(c)
        build_tag(c, page, n)
        c.setFont("Helvetica", 8)                                  # page number, bottom centre
        c.setFillGray(0)
        c.drawCentredString(PAGE_W / 2, 6 * mm, f"Page {n} of {len(pages)}")
        c.showPage()
    c.save()
    print("wrote", out)


if __name__ == "__main__":
    main()
