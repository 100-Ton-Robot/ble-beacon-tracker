"""How small can the mast get? Sweep the core's sector count, face size and antenna spacing, then score each pattern.

Every dimension comes from ../shield_deck/parameters.csv. Each geometry is one sector_model.py run whose overrides
are passed as --set NAME=VALUE, so the command logged in out/runs.csv and each summary.txt reproduces that run alone.

For each sector count N (core = regular N-gon), face width W, face height (--heights; 0 = square faces), antenna
spacing S off the face and element:
  deck       the rev 3 rule (shield_deck/pcb/deck_size.py) scaled to the core: the larger of
             2 x (corners + DECK_MIN_DIAMETER's margin past today's corners) and
             2 x (inradius + S + PAD_EXPOSE / 2 + DECK_EDGE_MARGIN)
  end plate  with --end-plate: 2 x (corners + ENDPLATE_DIAMETER's margin past today's corners)
             (both margins are 2.7 mm with today's values: 144 mm around 120 mm faces)
Elements:
  dipole  half-wave (0.95 lambda/2 at RF_FREQ, about 58 mm), feed at mid face height
  h50327  the reference duck: half-wave dipole fed DUCK_FEED_DEPTH below the deck (it hangs from its deck jack,
          so its depth doesn't follow the face height)
  short   CHIP_STANDIN_LENGTH centre-fed dipole at mid face height: a pattern stand-in for a chip antenna. An
          electrically short radiator has nearly the same pattern as a half-wave one, so the directivity is
          meaningful; the match is not, and the chip's carrier ground isn't modelled.

Writes each pattern to <out>/<name>/, then runs the bearing simulation (bearing_sim.py, default noise) and the
back-level measure from spec_sweep.py, and writes <out>/summary.txt and summary.csv.

    python3 size_sweep.py                              # default sweep
    python3 size_sweep.py --sectors 3 4 --widths 120 80 60 --spacings 15 --elements h50327 --heights 120 --end-plate
    python3 size_sweep.py --score-only                 # re-score existing patterns
"""
import argparse
import math
import os
import sys

import runlog
import sector_model as sm                         # puts ../shield_deck on the path
import params  # noqa: E402
import spec_sweep as ss

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "size")
BASE = params.load()                              # parameters.csv as it is: the margins come from today's boards
C0 = 299_792_458.0


def corner_margin(name):
    """How far a board of today's diameter `name` reaches past today's (3-sector) core corners, mm."""
    return BASE[name] / 2 - sm.circumradius(BASE["FACE_WIDTH"], 3)


def deck_diameter(n, w, s):
    by_pad = 2 * (sm.inradius(w, n) + s + BASE["PAD_EXPOSE"] / 2 + BASE["DECK_EDGE_MARGIN"])
    by_core = 2 * (sm.circumradius(w, n) + corner_margin("DECK_MIN_DIAMETER"))
    return math.ceil(max(by_pad, by_core) * 10 - 1e-9) / 10


def end_plate(c):
    """End plate diameter for a config, or 0 for none."""
    if not c.get("ep"):
        return 0.0
    return math.ceil(2 * (sm.circumradius(c["width"], c["sectors"]) + corner_margin("ENDPLATE_DIAMETER")) * 10
                     - 1e-9) / 10


def half_wave():
    return 0.95 * C0 / (BASE["RF_FREQ"] * 1e6) * 1e3 / 2


def configs(sectors, widths, spacings, elements, heights=(0,), ep=False):
    for n in sectors:
        for w in widths:
            for h in heights:
                for s in spacings:
                    for e in elements:
                        if h == w and 0 in heights:               # same as the square-face run
                            continue
                        H = h or w
                        if e == "dipole" and H < half_wave():       # doesn't fit beside a shorter face
                            continue
                        if ep and e == "h50327" and H < BASE["DUCK_FEED_DEPTH"] + half_wave() / 2 + 5:
                            continue                                # the duck would hang through the plate
                        pre = "" if n == 3 else f"n{n}_"
                        hh = f"_h{h:g}" if h else ""
                        yield dict(name=f"{pre}w{w:g}{hh}_s{s:g}_{e}" + ("_ep" if ep else ""), sectors=n, width=w,
                                   height=H, spacing=s, element=e, ep=ep)


def run_one(c, coarse, fine=False):
    w, s, n, H = c["width"], c["spacing"], c["sectors"], c["height"]
    centre = BASE["DUCK_FEED_DEPTH"] if c["element"] == "h50327" else H / 2
    argv = ["sector_model.py", "--antenna", "dipole", "--sectors", str(n), "--spacing", f"{s:g}",
            "--centre", f"{centre:g}"]
    if c["element"] == "short":
        argv += ["--length", f"{BASE['CHIP_STANDIN_LENGTH']:g}"]
    argv += ["--set", f"FACE_WIDTH={w:g}", "--set", f"FACE_H={H:g}",
             "--set", f"DISC_DIAMETER={deck_diameter(n, w, s):g}"]
    if end_plate(c):
        argv += ["--end-plate", "--set", f"ENDPLATE_DIAMETER={end_plate(c):g}"]
    if coarse:
        argv.append("--coarse")
    if fine:
        argv.append("--fine")
    argv += ["--out", os.path.relpath(os.path.join(OUT, c["name"]), HERE)]
    sm.P.clear()
    sm.P.update(params.load())                     # each run starts from parameters.csv
    sys.argv = argv
    os.chdir(HERE)                                 # openEMS leaves the working directory in its (deleted) temp folder
    sm.main()


def score(c):
    folder = os.path.join(OUT, c["name"])
    r = ss.run(folder, 4000)
    back = ss.back_levels(folder)
    worst_back = max(v[2] for v in back.values())           # worst over el 0..-55, az 120-240, rel. az 0
    peak = max(float(l.split()[1]) for l in open(os.path.join(folder, "summary.txt")) if l.startswith("peak"))
    return dict(**c, disc=deck_diameter(c["sectors"], c["width"], c["spacing"]), plate=end_plate(c),
                med=r["med"], p90=r["p90"], sector=r["sector"], peak=peak,
                back0=back[0][2], back30=back[-30][2], back55=back[-55][2], worst=worst_back)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sectors", type=int, nargs="+", default=[BASE["RF_SECTORS"]],
                    help="sector counts (core sides), e.g. 3 4; default RF_SECTORS")
    ap.add_argument("--widths", type=float, nargs="+", default=[BASE["FACE_WIDTH"], 100, 80, 60],
                    help="face widths, mm; default FACE_WIDTH and 100 80 60")
    ap.add_argument("--spacings", type=float, nargs="+", default=[BASE["DUCK_SPACING"], 15],
                    help="antenna axis -> face, mm; default DUCK_SPACING and 15")
    ap.add_argument("--elements", nargs="+", default=["h50327"], choices=["dipole", "short", "h50327"])
    ap.add_argument("--end-plate", action="store_true", help="add an end plate across the far end of the core")
    ap.add_argument("--heights", type=float, nargs="+", default=[0], help="face heights, mm (0 = same as width)")
    ap.add_argument("--coarse", action="store_true", help="coarser mesh: not good enough for size work")
    ap.add_argument("--fine", action="store_true", help="finer mesh (convergence check)")
    ap.add_argument("--out", help="output folder (default out/size)")
    ap.add_argument("--score-only", action="store_true")
    a = ap.parse_args()
    global OUT
    if a.out:
        OUT = os.path.abspath(a.out)
    cmd = runlog.header()
    cs = list(configs(a.sectors, a.widths, a.spacings, a.elements, a.heights, a.end_plate))
    if not a.score_only:
        for c in cs:
            print("====", c["name"], flush=True)
            run_one(c, a.coarse, a.fine)
    rows = [score(c) for c in cs if os.path.exists(os.path.join(OUT, c["name"], "pattern.csv"))]
    lines = ["Size sweep: N-gon core, deck and end plate scaled from today's boards (see size_sweep.py).",
             "Bearing: bearing_sim.py default noise (fading 5, room 3, shadow 4 dB, 3 adverts/s, 1 s window).",
             "Back = worst level over az 120-240 relative to az 0 (dB, more negative is better); target <= -20.",
             "",
             "name                          N  face  high  disc plate   peak dBi  back el0  el-30  el-55  worst"
             "   median  90%   right sector"]
    for r in rows:
        lines.append(f"{r['name']:29s} {r['sectors']:d} {r['width']:4.0f}  {r['height']:4.0f} {r['disc']:5.0f} "
                     f"{r['plate']:5.0f}   {r['peak']:6.1f}   "
                     f"{r['back0']:6.1f} {r['back30']:6.1f} {r['back55']:6.1f} {r['worst']:6.1f}   "
                     f"{r['med']:5.0f} {r['p90']:5.0f}   {r['sector']:5.1f}%")
    text = cmd + "\n".join(lines) + "\n"
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "summary.txt"), "w") as fh:
        fh.write(text)
    with open(os.path.join(OUT, "summary.csv"), "w") as fh:
        keys = ["name", "sectors", "width", "height", "spacing", "element", "disc", "plate", "peak", "back0",
                "back30", "back55", "worst", "med", "p90", "sector"]
        fh.write(",".join(keys) + "\n")
        for r in rows:
            fh.write(",".join(f"{r[k]:.2f}" if isinstance(r[k], float) else str(r[k]) for k in keys) + "\n")
    print(text)
    runlog.record(OUT, "size sweep: " + ", ".join(f"{r['name']} {r['med']:.0f} deg" for r in rows))


if __name__ == "__main__":
    main()
