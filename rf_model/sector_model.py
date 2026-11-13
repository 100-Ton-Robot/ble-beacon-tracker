"""openEMS (FDTD) model of one mast sector: the copper deck, the triangular core and the D-hole antennas.

Geometry comes from shield_deck/parameters.csv (DISC_DIAMETER, FACE_WIDTH, FACE_H, DUCK_SPACING, RF_FREQ), so the
model follows the deck. Sector 0's antenna is fed; the other two sectors' antennas are there too, ended in 50 ohm
like their radios, so the pattern includes their coupling and the run also gives the isolation between sectors.

    python3 sector_model.py --antenna monopole            # quarter-wave whip straight down from the D jack
    python3 sector_model.py --antenna dipole              # rubber duck as a vertical half-wave dipole
    python3 sector_model.py --antenna dipole --centre 50  # its feed point this far below the deck
    python3 sector_model.py --coarse                      # quick check: coarser mesh, about 5x faster

Writes to out/<antenna>/ (or --out):
  pattern.csv   az_deg, el_deg, dbi: directivity, 5 deg grid. az clockwise from S0's face normal seen from above
                (the deck's own convention); el 0 = horizon, negative = below the deck (where the antennas hang).
                Sectors 1 and 2 are the same pattern turned by +120 / +240 deg.
  summary.txt   match (S11, input impedance), peak, beamwidth, front-to-back and sector isolation
  pattern.png   azimuth cuts at el 0, -15, -30 and -45 deg
  s11.png       S11 over the BLE band

Coordinates: mm, deck centre at the origin, z up (deck top / electronics up, core and antennas below at z < 0),
x = deck +X, y = deck +Y (S0's face normal). Needs openEMS + CSXCAD Python bindings, numpy, matplotlib,
h5py: on Windows, run it in the Docker image from this folder's Dockerfile (README). The raw FDTD data goes to a temp folder and is deleted afterwards unless --keep.

Not modelled: the enclosure, the electronics plate and its parts, the coax runs, the M4 bolts and spacers.
The core is a solid copper prism (only its outside matters to the pattern), the whips are thin wires.
"""
import argparse
import math
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shield_deck"))
import params  # noqa: E402
import runlog  # noqa: E402

P = params.load()
C0 = 299_792_458.0
SECTORS = [0.0, 120.0, 240.0]          # face normals, clockwise from +Y, as in make_shield_deck.py
INRADIUS = P["FACE_WIDTH"] / (2 * math.sqrt(3))
BAND = (2402e6, 2480e6)


def pol(r, deg):
    # rounded so e.g. sin(180) = 1e-16 can't sit beside 0 as a near-duplicate mesh line (smoothing then drops the
    # line a wire is on, and openEMS leaves that wire out)
    a = math.radians(deg)
    return round(r * math.sin(a), 4) + 0.0, round(r * math.cos(a), 4) + 0.0


def args_():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--antenna", choices=["monopole", "dipole"], default="monopole")
    ap.add_argument("--length", type=float, help="element length in mm (default 0.95 x lambda/4 monopole, "
                                                 "0.95 x lambda/2 dipole, at RF_FREQ)")
    ap.add_argument("--centre", type=float, default=45.0,
                    help="dipole only: feed point depth below the deck, mm (a duck's base sits on the jack, "
                         "its feed about a quarter wave down)")
    ap.add_argument("--spacing", type=float, default=P["DUCK_SPACING"],
                    help="antenna axis -> copper face, mm (default DUCK_SPACING, the D hole)")
    ap.add_argument("--gap", type=float, default=1.0, help="feed gap, mm")
    ap.add_argument("--freq", type=float, default=P["RF_FREQ"] * 1e6, help="Hz, default RF_FREQ")
    ap.add_argument("--single", action="store_true", help="leave out the other two sectors' antennas")
    ap.add_argument("--coarse", action="store_true", help="coarser mesh, fewer timesteps: a quick check")
    ap.add_argument("--out", help="output folder (default out/<antenna>)")
    ap.add_argument("--keep", action="store_true", help="keep the raw FDTD data (prints where)")
    return ap.parse_args()


def build(a):
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS

    f0 = a.freq
    lam = C0 / f0 * 1e3
    length = a.length or 0.95 * lam / (4 if a.antenna == "monopole" else 2)
    R = P["DISC_DIAMETER"] / 2
    H = P["FACE_H"]

    fdtd = openEMS(NrTS=20000 if a.coarse else 60000, EndCriteria=1e-4)
    fdtd.SetGaussExcite(f0, 0.5e9)                    # covers about 1.9-3.0 GHz
    fdtd.SetBoundaryCond(["PML_8"] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)

    pec = csx.AddMetal("copper")
    # deck: zero-thickness disc at z = 0
    n = 72
    ring = np.array([[R * math.cos(2 * math.pi * i / n) for i in range(n)],
                     [R * math.sin(2 * math.pi * i / n) for i in range(n)]])
    pec.AddPolygon(ring, "z", 0.0, priority=10)
    # core: solid triangular prism from the deck down to FACE_H, vertices between the faces
    verts = [pol(2 * INRADIUS, v) for v in (60.0, 180.0, 300.0)]
    tri = np.array([[v[0] for v in verts], [v[1] for v in verts]])
    pec.AddLinPoly(tri, "z", -H, H, priority=10)

    # antennas at the D holes, hanging straight down; sector 0 fed, the others 50 ohm loads
    ports = []
    feeds = SECTORS if not a.single else SECTORS[:1]
    zl = [0.0]
    for i, s in enumerate(feeds):
        x, y = pol(INRADIUS + a.spacing, s)
        if a.antenna == "monopole":
            z_feed_top, z_feed_bot = 0.0, -a.gap
            pec.AddBox([x, y, z_feed_bot], [x, y, -length], priority=10)
            zl += [z_feed_bot, -length]
        else:
            zc = -a.centre
            z_feed_top, z_feed_bot = zc + a.gap / 2, zc - a.gap / 2
            pec.AddBox([x, y, z_feed_top], [x, y, zc + length / 2], priority=10)
            pec.AddBox([x, y, z_feed_bot], [x, y, zc - length / 2], priority=10)
            zl += [z_feed_top, z_feed_bot, zc + length / 2, zc - length / 2]
        ports.append(fdtd.AddLumpedPort(i + 1, 50, [x, y, z_feed_bot], [x, y, z_feed_top], "z",
                                        excite=1.0 if i == 0 else 0.0, priority=5))
        mesh.AddLine("x", [x])
        mesh.AddLine("y", [y])

    # mesh: fixed lines at the structure's edges, then smoothed; air margin about lambda/2 past the parts
    fine = 2.0 if a.coarse else 1.0
    coarse = lam / (15 if a.coarse else 22)
    margin = lam / 2
    lowest = min(min(zl), -H)
    mesh.AddLine("x", [-R, R, *[v[0] for v in verts], -R - margin, R + margin])
    mesh.AddLine("y", [-R, R, *[v[1] for v in verts], -R - margin, R + margin])
    mesh.AddLine("z", [*zl, -H, lowest - margin, margin])
    x0, y0 = pol(INRADIUS + a.spacing, 0.0)
    mesh.AddLine("y", [y0 - fine, y0 + fine])
    mesh.AddLine("x", [x0 - fine, x0 + fine])
    for d in "xyz":
        mesh.SmoothMeshLines(d, coarse, 1.4)
    nf2ff = fdtd.CreateNF2FFBox()
    info = dict(f0=f0, lam=lam, length=length, cells=[len(mesh.GetLines(d)) for d in "xyz"])
    return fdtd, csx, ports, nf2ff, info


def beamwidth(az, dbi):
    """-3 dB width of the lobe around the peak, wrapping round 360 deg."""
    k = int(np.argmax(dbi))
    lim = dbi[k] - 3.0
    n = len(az)
    step = az[1] - az[0]
    left = right = 0
    while left < n and dbi[(k - left - 1) % n] >= lim:
        left += 1
    while right < n and dbi[(k + right + 1) % n] >= lim:
        right += 1
    return min(360.0, (left + right + 1) * step)


def main():
    a = args_()
    # absolute: openEMS changes the working directory while it runs
    out = os.path.abspath(a.out or os.path.join(HERE, "out", a.antenna))
    os.makedirs(out, exist_ok=True)
    sim = tempfile.mkdtemp(prefix=f"sector_{a.antenna}_")

    fdtd, csx, ports, nf2ff, info = build(a)
    csx.Write2XML(os.path.join(out, "model.xml"))     # open in AppCSXCAD to look at the geometry
    print(f"mesh {info['cells']} = {np.prod(info['cells']) / 1e6:.2f} M cells, element {info['length']:.1f} mm")
    fdtd.Run(sim, cleanup=True)

    f = np.linspace(2.3e9, 2.6e9, 301)
    for p in ports:
        p.CalcPort(sim, f)
    p1 = ports[0]
    s11 = p1.uf_ref / p1.uf_inc
    zin = p1.uf_tot / p1.if_tot
    i0 = int(np.argmin(abs(f - info["f0"])))

    theta = np.arange(0.0, 181.0, 5.0)
    phi = np.arange(0.0, 360.0, 5.0)
    res = nf2ff.CalcNF2FF(sim, info["f0"], theta, phi, center=[0, 0, 0])
    E = res.E_norm[0]
    dbi = 20 * np.log10(E / E.max()) + 10 * np.log10(res.Dmax[0])   # [theta, phi]

    # to the deck's convention: az clockwise from +Y seen from above, el up from the horizon
    el = 90.0 - theta
    az = (90.0 - phi) % 360.0
    order = np.argsort(az)
    az, dbi = az[order], dbi[:, order]
    with open(os.path.join(out, "pattern.csv"), "w") as fh:
        fh.write("az_deg,el_deg,dbi\n")
        for ti in range(len(el)):
            for pi in range(len(az)):
                fh.write(f"{az[pi]:.0f},{el[ti]:.0f},{dbi[ti, pi]:.2f}\n")

    lines = [f"antenna: {a.antenna}, element {info['length']:.1f} mm, {a.spacing:g} mm in front of the face"
             + (f", feed {a.centre:.0f} mm below the deck" if a.antenna == "dipole" else "")
             + (", other sectors left out" if a.single else ", other sectors' antennas in, 50 ohm"),
             f"f0 {info['f0'] / 1e6:.0f} MHz, mesh {info['cells']} cells{' (coarse)' if a.coarse else ''}",
             "",
             "match (sector 0 port, 50 ohm):"]
    for fb in (BAND[0], info["f0"], BAND[1]):
        k = int(np.argmin(abs(f - fb)))
        lines.append(f"  {f[k] / 1e6:.0f} MHz  S11 {20 * np.log10(abs(s11[k])):6.1f} dB  "
                     f"Zin {zin[k].real:6.1f} {zin[k].imag:+6.1f}j ohm")
    tk, pk = np.unravel_index(int(np.argmax(dbi)), dbi.shape)
    lines += ["", f"peak {dbi[tk, pk]:.1f} dBi at az {az[pk]:.0f}, el {el[tk]:.0f} deg",
              "", "elevation   max dBi   at az   -3 dB width   front-to-back (az 0 vs 180)"]
    for e in (0, -15, -30, -45, -60):
        t = int(np.argmin(abs(el - e)))
        row = dbi[t]
        fb = row[int(np.argmin(abs(az - 0)))] - row[int(np.argmin(abs(az - 180)))]
        lines.append(f"  {e:4d}      {row.max():6.1f}   {az[int(np.argmax(row))]:5.0f}   "
                     f"{beamwidth(az, row):6.0f} deg     {fb:6.1f} dB")
    if len(ports) > 1:
        lines += ["", "isolation, sector 0 -> other sectors' ports (|S21|):"]
        for j, p in enumerate(ports[1:], start=1):
            s21 = p.uf_tot[i0] / p1.uf_inc[i0]
            lines.append(f"  S{j}: {20 * np.log10(abs(s21)):.1f} dB")
    text = runlog.header() + "\n".join(lines) + "\n"
    s11c = 20 * np.log10(abs(s11[i0]))
    runlog.record(out, f"peak {dbi[tk, pk]:.1f} dBi at el {el[tk]:.0f}, S11 {s11c:.1f} dB at f0"
                  + (f", isolation {20 * np.log10(abs(ports[1].uf_tot[i0] / p1.uf_inc[i0])):.1f} dB"
                     if len(ports) > 1 else ""))
    with open(os.path.join(out, "summary.txt"), "w") as fh:
        fh.write(text)
    print(text)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(6.5, 6.5))
        ax = fig.add_subplot(projection="polar")
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)                  # clockwise, as seen from above
        for e in (0, -15, -30, -45):
            t = int(np.argmin(abs(el - e)))
            ax.plot(np.radians(np.append(az, az[0] + 360)), np.append(dbi[t], dbi[t, 0]), label=f"el {e}")
        top = math.ceil(dbi.max())
        ax.set_rlim(top - 30, top)
        ax.set_title(f"Sector 0 directivity (dBi), {a.antenna}, {info['f0'] / 1e6:.0f} MHz\n"
                     "seen from above, 0 = S0 face normal")
        ax.legend(loc="lower left", bbox_to_anchor=(-0.1, -0.1))
        fig.savefig(os.path.join(out, "pattern.png"), dpi=120, bbox_inches="tight")
        fig = plt.figure(figsize=(6.5, 4))
        plt.plot(f / 1e6, 20 * np.log10(abs(s11)))
        plt.axvspan(BAND[0] / 1e6, BAND[1] / 1e6, alpha=0.15)
        plt.xlabel("MHz")
        plt.ylabel("S11 dB")
        plt.grid(True)
        plt.title(f"Sector 0 match, {a.antenna}")
        fig.savefig(os.path.join(out, "s11.png"), dpi=120, bbox_inches="tight")
    except ImportError:
        print("matplotlib not installed: no plots")

    if a.keep:
        print("raw FDTD data in", sim)
    else:
        shutil.rmtree(sim, ignore_errors=True)


if __name__ == "__main__":
    main()
