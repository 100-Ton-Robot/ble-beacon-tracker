#!/usr/bin/env python3
"""LED direction ring model: each beacon lights a blob toward its bearing; the firmware scales the whole
frame down when the strip would draw more than the cap. Prints the strip current over a 60 s scenario.

Assumptions (the ring isn't built): pixel 0 on the deck's S0 arrow, numbered clockwise; blob width =
the tracker's bearing uncertainty (sigma, deg); brightness falls linearly to zero at 50 m.

    python3 sim/ring.py [--cap 1000]    # cap in mA
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shield_deck"))
import params  # noqa: E402

P = params.load(groups=("led",))
NPIX = P["LED_PIXELS"]
MA_WHITE, MA_DARK = P["LED_PIXEL_MA"]
MA_CH = MA_WHITE / 3


def frame(beacons, cap_ma=None):
    """Pixel RGB (0-255) after the cap, strip mA after the cap, strip mA the frame asked for."""
    pix = np.zeros((NPIX, 3))
    ang = np.arange(NPIX) * 360 / NPIX
    for b in beacons:
        d = (ang - b["bearing"] + 180) % 360 - 180
        w = np.exp(-d ** 2 / (2 * b["sigma"] ** 2)) * max(0.0, 1 - b["range"] / 50)
        pix += np.outer(w, np.array(b["rgb"]) * 255)
    pix = np.clip(pix, 0, 255)
    lit = pix.sum() / 255 * MA_CH
    scale = 1.0
    if cap_ma is not None and lit > cap_ma - NPIX * MA_DARK:
        scale = (cap_ma - NPIX * MA_DARK) / lit
    return pix * scale, NPIX * MA_DARK + lit * scale, NPIX * MA_DARK + lit


def scenario(cap_ma):
    """Walker circling at 15 m; car passing at 40 m from 20 to 45 s; 25 phones at 2-6 m from 30 to 40 s."""
    import colorsys
    rng = np.random.default_rng(7)
    crowd = [dict(bearing=float(rng.uniform(0, 360)), sigma=15, range=float(rng.uniform(2, 6)),
                  rgb=colorsys.hsv_to_rgb(rng.uniform(), 1, 1)) for _ in range(25)]
    out = []
    for t in np.arange(0, 60, 0.1):
        bs = [dict(bearing=(t * 6) % 360, sigma=12, range=15, rgb=(1, 1, 1))]
        if 20 < t < 45:
            bs.append(dict(bearing=200 + (t - 20) * 4, sigma=18, range=40, rgb=colorsys.hsv_to_rgb(0.6, 1, 1)))
        if 30 <= t < 40:
            bs += crowd
        _, capped, raw = frame(bs, cap_ma)
        out.append((t, raw, capped))
    return np.array(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=1000, help="firmware strip current cap, mA")
    a = ap.parse_args()
    r = scenario(a.cap)
    print(f"{NPIX} pixels, full white {NPIX * (MA_DARK + MA_WHITE):.0f} mA")
    print(f"scenario: uncapped peak {r[:, 1].max():.0f} mA, with a {a.cap:.0f} mA cap {r[:, 2].max():.0f} mA")
