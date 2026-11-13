"""Bearing and range accuracy of the three-sector mast, from a sector pattern (sector_model.py's pattern.csv).

A beacon is placed at many bearings and distances round the mast. Each second, each sector hears it with
    RSSI = tx_1m - 10 n log10(d) + gain(sector, az, el) + room(sector, place) + fading(advert)
and reports the median of that second's adverts (the firmware's `med`). The tracker side is a least-squares fit:
it tries every bearing and elevation, lines the pattern's sector-to-sector differences up with the measured ones
(so the unknown transmit power and path loss cancel) and keeps the best. Range comes from the best fit's gain and
the log-distance model.

Noise, all in dB:
  --fading   per advert, per sector: fast multipath, a Rayleigh-like spread (default 5)
  --room     per sector, fixed for a place: reflections that don't average out over time (default 3)
  --shadow   common to all sectors, fixed for a place: walls, bodies. Moves range, not bearing (default 4)
  --adverts  adverts per second per sector on the compared channel (default 3)
  --window   seconds averaged by the tracker (default 1); each second's median is averaged in dB

    python3 bearing_sim.py out/monopole out/dipole            # compare antennas, default noise
    python3 bearing_sim.py out/monopole --room 0 --window 5   # what the antenna alone allows

Writes to out/bearing/ (or --out): summary.txt and, per pattern, error_vs_bearing.png and errors.csv.
Mast geometry: --height is how far the mast is above the beacon (default 1.4 m: a 2.4 m garage ceiling, beacon
at 1 m); distances 1-15 m along the floor. Elevation seen from the mast is then -atan(height / distance).
"""
import argparse
import csv
import math
import os

import numpy as np

import runlog

HERE = os.path.dirname(os.path.abspath(__file__))
SECTORS = (0.0, 120.0, 240.0)


def load_pattern(folder):
    """gain[el index, az index] on a 1 deg azimuth grid (interpolated round the circle), els as in the file."""
    rows = list(csv.DictReader(open(os.path.join(folder, "pattern.csv"))))
    els = sorted({int(r["el_deg"]) for r in rows})
    azs = sorted({int(r["az_deg"]) for r in rows})
    g = np.zeros((len(els), len(azs)))
    ei = {e: i for i, e in enumerate(els)}
    ai = {a: i for i, a in enumerate(azs)}
    for r in rows:
        g[ei[int(r["el_deg"])], ai[int(r["az_deg"])]] = float(r["dbi"])
    az1 = np.arange(360)
    xp = np.append(azs, 360)
    fine = np.array([np.interp(az1, xp, np.append(row, row[0])) for row in g])
    return np.array(els, float), fine


def gain(els, pat, az, el):
    """Gain of sector 0 at (az, el), az any real, el in the file's range: linear in el, nearest whole az."""
    a = np.round(np.asarray(az)).astype(int) % 360
    e = np.clip(np.asarray(el, float), els[0], els[-1])
    k = np.clip(np.searchsorted(els, e) - 1, 0, len(els) - 2)
    t = (e - els[k]) / (els[k + 1] - els[k])
    return pat[k, a] * (1 - t) + pat[k + 1, a] * t


def sector_gains(els, pat, az, el):
    """[..., 3]: gain of each sector toward (az, el). Sector s is sector 0 turned by s degrees clockwise."""
    return np.stack([gain(els, pat, np.asarray(az) - s, el) for s in SECTORS], axis=-1)


def ang_err(a, b):
    return (np.asarray(a) - np.asarray(b) + 180.0) % 360.0 - 180.0


def simulate(folder, a, rng):
    els, pat = load_pattern(folder)
    # tracker's lookup table: every whole bearing, elevations 0..-80 in 2 deg steps
    t_az = np.arange(360.0)
    t_el = np.arange(0.0, -81.0, -2.0)
    AZ, EL = np.meshgrid(t_az, t_el)
    table = sector_gains(els, pat, AZ, EL)                       # [el, az, 3]
    table_c = table - table.mean(axis=-1, keepdims=True)

    true_az = rng.uniform(0, 360, a.trials)
    dist = np.exp(rng.uniform(math.log(1.0), math.log(15.0), a.trials))
    true_el = -np.degrees(np.arctan2(a.height, dist))
    slant = np.hypot(dist, a.height)
    g = sector_gains(els, pat, true_az, true_el)                 # [trial, 3]
    room = rng.normal(0, a.room, (a.trials, 3))
    shadow = rng.normal(0, a.shadow, (a.trials, 1))
    base = a.tx1m - 10 * a.n * np.log10(slant)[:, None] + g + room + shadow
    secs = []
    for _ in range(a.window):
        fad = rng.normal(0, a.fading, (a.trials, 3, a.adverts))
        secs.append(np.median(base[:, :, None] + fad, axis=-1))
    rssi = np.mean(secs, axis=0)                                 # [trial, 3]

    meas_c = rssi - rssi.mean(axis=-1, keepdims=True)
    est_az = np.empty(a.trials)
    est_g = np.empty(a.trials)
    for i in range(a.trials):
        cost = ((table_c - meas_c[i]) ** 2).sum(axis=-1)
        k = np.unravel_index(int(np.argmin(cost)), cost.shape)
        est_az[i] = t_az[k[1]]
        best = int(np.argmax(rssi[i]))
        est_g[i] = table[k[0], k[1], best]
    best = rssi.max(axis=-1)
    est_slant = 10 ** ((a.tx1m - (best - est_g)) / (10 * a.n))
    est_dist = np.sqrt(np.maximum(est_slant ** 2 - a.height ** 2, 0.0))
    err = ang_err(est_az, true_az)
    sector_ok = np.argmax(sector_gains(els, pat, true_az, true_el), -1) == np.argmax(rssi, -1)
    return dict(true_az=true_az, dist=dist, err=err, est_dist=est_dist, sector_ok=sector_ok)


def stats(r):
    e = np.abs(r["err"])
    ratio = r["est_dist"] / r["dist"]
    near = r["dist"] <= 5
    return dict(med=np.median(e), p90=np.percentile(e, 90), rms=math.sqrt(np.mean(e ** 2)),
                med_near=np.median(e[near]), med_far=np.median(e[~near]),
                sector=100 * r["sector_ok"].mean(),
                range_med=100 * np.median(np.abs(ratio - 1)),
                range_p90=100 * np.percentile(np.abs(ratio - 1), 90))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("patterns", nargs="+", help="folders holding pattern.csv (e.g. out/monopole)")
    ap.add_argument("--fading", type=float, default=5.0)
    ap.add_argument("--room", type=float, default=3.0)
    ap.add_argument("--shadow", type=float, default=4.0)
    ap.add_argument("--adverts", type=int, default=3)
    ap.add_argument("--window", type=int, default=1)
    ap.add_argument("--height", type=float, default=1.4, help="m, mast above the beacon")
    ap.add_argument("--n", type=float, default=2.2, help="path-loss exponent (indoor, line of sight ~2-2.5)")
    ap.add_argument("--tx1m", type=float, default=-59.0, help="dBm at 1 m (iBeacon's usual measured power)")
    ap.add_argument("--trials", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(HERE, "out", "bearing"))
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)

    noise = (f"fading {a.fading} dB/advert, {a.adverts} adverts/s, room {a.room} dB, shadow {a.shadow} dB, "
             f"window {a.window} s, mast {a.height} m above the beacon, beacons 1-15 m out, n {a.n}")
    lines = [noise, "",
             "pattern      |bearing error| deg: median  90%   rms   (<=5 m / >5 m median)   right sector   "
             "range error: median  90%"]
    results = {}
    for folder in a.patterns:
        name = os.path.basename(os.path.normpath(folder))
        r = simulate(folder, a, np.random.default_rng(a.seed))
        results[name] = r
        s = stats(r)
        lines.append(f"{name:12s}                     {s['med']:5.0f} {s['p90']:5.0f} {s['rms']:5.0f}"
                     f"      ({s['med_near']:3.0f} / {s['med_far']:3.0f})             {s['sector']:5.1f}%"
                     f"             {s['range_med']:4.0f}% {s['range_p90']:4.0f}%")
        with open(os.path.join(a.out, f"errors_{name}.csv"), "w") as fh:
            fh.write("true_az,dist_m,err_deg,est_dist_m\n")
            for i in range(len(r["err"])):
                fh.write(f"{r['true_az'][i]:.1f},{r['dist'][i]:.2f},{r['err'][i]:.1f},{r['est_dist'][i]:.2f}\n")

    # the same noise swept, so the antenna's share and the room's share show separately
    lines += ["", "median |bearing error| deg, room reflections x tracker window (fading, adverts, shadow as above):"]
    hdr = "  room dB  window s  " + "  ".join(f"{os.path.basename(os.path.normpath(p)):>10s}" for p in a.patterns)
    lines.append(hdr)
    for room in (0.0, 2.0, 3.0, 5.0):
        for win in (1, 5):
            b = argparse.Namespace(**{**vars(a), "room": room, "window": win, "trials": min(a.trials, 2000)})
            vals = [np.median(np.abs(simulate(p, b, np.random.default_rng(a.seed))["err"])) for p in a.patterns]
            lines.append(f"  {room:7.0f}  {win:8d}  " + "  ".join(f"{v:10.0f}" for v in vals))
    text = runlog.header() + "\n".join(lines) + "\n"
    with open(os.path.join(a.out, "summary.txt"), "w") as fh:
        fh.write(text)
    print(text)
    runlog.record(a.out, "median bearing error: " + ", ".join(
        f"{n} {np.median(np.abs(r['err'])):.0f} deg" for n, r in results.items()))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = np.arange(0, 361, 10)
    for name, r in results.items():
        k = np.digitize(r["true_az"], bins) - 1
        med = [np.median(np.abs(r["err"][k == i])) for i in range(len(bins) - 1)]
        ax.plot(bins[:-1] + 5, med, marker="o", ms=3, label=name)
    for s in SECTORS:
        ax.axvline(s, color="0.6", lw=0.8)
        ax.axvline(s + 60, color="0.6", lw=0.8, ls="--")
    ax.set_xlabel("true bearing, deg (solid: sector facings, dashed: edges between sectors)")
    ax.set_ylabel("median |bearing error|, deg")
    ax.set_xlim(0, 360)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.4)
    ax.legend()
    ax.set_title("Bearing error round the mast\n" + noise, fontsize=9)
    fig.savefig(os.path.join(a.out, "error_vs_bearing.png"), dpi=120, bbox_inches="tight")

    fig, ax = plt.subplots(figsize=(6, 6))
    for name, r in results.items():
        est = (r["true_az"] + r["err"]) % 360
        ax.scatter(r["true_az"][:800], est[:800], s=4, alpha=0.5, label=name)
    ax.plot([0, 360], [0, 360], color="k", lw=0.8)
    ax.set_xlabel("true bearing, deg")
    ax.set_ylabel("estimated bearing, deg")
    ax.set_xlim(0, 360)
    ax.set_ylim(0, 360)
    ax.legend()
    ax.set_title("Estimated vs true bearing (800 beacons each)", fontsize=10)
    fig.savefig(os.path.join(a.out, "estimate_vs_true.png"), dpi=120, bbox_inches="tight")


if __name__ == "__main__":
    main()
