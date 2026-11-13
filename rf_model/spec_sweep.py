"""Which antenna specs give the best bearing: idealised sector beams swept through bearing_sim.

Each idealised beam has a set -3 dB horizontal beamwidth and a floor behind it (how far the whole back sits below
the front), the same at every elevation:
    gain(az) = 10 log10((1 - b) * ((1 + cos az) / 2) ** m + b),  b = 10 ** (-floor / 10)
with m chosen for the beamwidth. Each runs through bearing_sim.simulate() with its default noise (and two other
noise cases), next to the real patterns given on the command line, whose back-third level is measured so they can
be placed on the same scale.

    python3 spec_sweep.py out/monopole out/dipole

Writes out/spec_sweep/summary.txt. The idealised patterns go to a temp folder and are deleted.
"""
import argparse
import csv
import math
import os
import shutil
import tempfile

import numpy as np

import bearing_sim as bs

HERE = os.path.dirname(os.path.abspath(__file__))
BEAMWIDTHS = [60, 80, 90, 100, 110, 120, 140, 160, 180]
FLOORS = [6, 10, 15, 20, 30]
NOISE = [("default noise: room 3 dB, 1 s window", {}),
         ("averaged: room 3 dB, 5 s window", {"window": 5}),
         ("antenna-limited: no room reflections, 5 s window", {"room": 0.0, "window": 5})]


def write_pattern(root, bw, floor):
    m = math.log(0.5) / math.log((1 + math.cos(math.radians(bw / 2))) / 2)
    b = 10 ** (-floor / 10)
    d = os.path.join(root, f"bw{bw}_floor{floor}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "pattern.csv"), "w") as fh:
        fh.write("az_deg,el_deg,dbi\n")
        for el in range(-90, 91, 5):
            for az in range(0, 360, 5):
                g = (1 - b) * ((1 + math.cos(math.radians(az))) / 2) ** m + b
                fh.write(f"{az},{el},{10 * math.log10(g):.2f}\n")
    return d


def run(folder, trials, **kw):
    a = argparse.Namespace(fading=5.0, room=3.0, shadow=4.0, adverts=3, window=1, height=1.4, n=2.2,
                           tx1m=-59.0, trials=trials, seed=1)
    for k, v in kw.items():
        setattr(a, k, v)
    r = bs.simulate(folder, a, np.random.default_rng(1))
    e = np.abs(r["err"])
    near = r["dist"] <= 5
    return dict(med=np.median(e), p90=np.percentile(e, 90), sector=100 * r["sector_ok"].mean(),
                near=np.median(e[near]), far=np.median(e[~near]))


def back_levels(folder):
    """{el: (level at az 90, worst level over az 120-240)}, both relative to az 0."""
    g = {}
    for r in csv.DictReader(open(os.path.join(folder, "pattern.csv"))):
        g.setdefault(int(r["el_deg"]), {})[int(r["az_deg"])] = float(r["dbi"])
    out = {}
    for el in (0, -15, -30, -45, -55):
        row = g[el]
        out[el] = (row[0], row[90] - row[0], max(v for a, v in row.items() if 120 <= a <= 240) - row[0])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("patterns", nargs="*", help="real pattern folders to compare (e.g. out/monopole out/dipole)")
    ap.add_argument("--trials", type=int, default=2000)
    ap.add_argument("--out", default=os.path.join(HERE, "out", "spec_sweep"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="spec_sweep_")
    lines = ["Idealised sector beams through bearing_sim (beacons 1-15 m out, mast 1.4 m above them,",
             "fading 5 dB/advert, 3 adverts/s, shadow 4 dB). Floor = how far the whole back sits below the front.",
             "Tables: median |bearing error| in deg; rows -3 dB beamwidth, columns floor in dB."]
    try:
        for label, kw in NOISE:
            lines += ["", label, "   bw  " + "".join(f"{f:>7d}" for f in FLOORS)]
            for bw in BEAMWIDTHS:
                vals = [run(write_pattern(tmp, bw, f), a.trials, **kw)["med"] for f in FLOORS]
                lines.append(f"  {bw:3d}  " + "".join(f"{v:7.0f}" for v in vals))
        lines += ["", "default noise, floor 20 dB: median, 90th percentile, right sector",
                  "  pattern          median   p90   right sector   (<=5 m / >5 m median)"]
        for bw in BEAMWIDTHS:
            s = run(write_pattern(tmp, bw, 20), a.trials)
            lines.append(f"  bw {bw:3d}          {s['med']:6.0f} {s['p90']:5.0f}   {s['sector']:9.1f}%"
                         f"      ({s['near']:3.0f} / {s['far']:3.0f})")
        for folder in a.patterns:
            s = run(folder, a.trials)
            name = os.path.basename(os.path.normpath(folder))
            lines.append(f"  {name:15s} {s['med']:6.0f} {s['p90']:5.0f}   {s['sector']:9.1f}%"
                         f"      ({s['near']:3.0f} / {s['far']:3.0f})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for folder in a.patterns:
        name = os.path.basename(os.path.normpath(folder))
        lines += ["", f"{name}: front gain and back levels relative to it (compare with the floor above)",
                  "   el   front dBi   az 90   worst az 120-240"]
        for el, (front, side, back) in back_levels(folder).items():
            lines.append(f"  {el:4d}   {front:8.1f}  {side:+6.1f}   {back:+8.1f} dB")
    text = "\n".join(lines) + "\n"
    with open(os.path.join(a.out, "summary.txt"), "w") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
