"""openEMS (FDTD) model of one mast sector: the copper deck, the triangular core and the D-hole antennas.

Geometry comes from shield_deck/parameters.csv (DISC_DIAMETER, FACE_WIDTH, FACE_H, DUCK_SPACING, RF_FREQ), so the
model follows the deck. Sector 0's antenna is fed; the other two sectors' antennas are there too, ended in 50 ohm
like their radios, so the pattern includes their coupling and the run also gives the isolation between sectors.

    python3 sector_model.py --antenna monopole            # quarter-wave whip straight down from the D jack
    python3 sector_model.py --antenna dipole              # rubber duck as a vertical half-wave dipole
    python3 sector_model.py --antenna dipole --centre 50  # its feed point this far below the deck
    python3 sector_model.py --coarse                      # quick check: coarser mesh, about 5x faster
    python3 sector_model.py --deck d15 --end-plate        # rev 3 PCBs as outlines: deck disc + pipe hole, end plate
    python3 sector_model.py --deck d15 --end-plate --copper   # rev 3 PCBs' real copper, hollow core of face boards

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

PCB build (shield_deck/pcb, rev 3), two levels of detail to compare:
  --deck d15|d31     the deck PCB for that duck spacing as an outline: a copper disc of its diameter
                     (shield_deck/layout.py) with the 22.2 mm pipe hole, on the solid core; the antennas
                     go to its D holes (--spacing defaults to 15 / 31)
  --end-plate        add the 144 mm end plate across the far end of the core (outline: a solid disc)
  --end-plate deck   with --copper: a second deck board turned over as the end plate, knockout left in
  --copper           with --deck: the boards' real copper from shield_deck/pcb/out/*_copper.json (written by
                     make_pcbs.py): both deck layers 1.6 mm apart joined by the plated holes and vias, every hole,
                     slot and track gap, the end plate's copper, and a hollow core built from the three face
                     boards (1.6 mm slabs, tabs through the slots). The fed antennas' RP-SMA bodies fill their holes.
                     Tracks and gaps under the mesh size (1 mm, 2 mm coarse) are only roughly resolved.
"""
import argparse
import math
import os
import shutil
import sys
import tempfile

import json

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "shield_deck"))
import params  # noqa: E402
import runlog  # noqa: E402
import layout  # noqa: E402

P = params.load()
C0 = 299_792_458.0
SECTORS = [0.0, 120.0, 240.0]          # face normals, clockwise from +Y, as in make_shield_deck.py
INRADIUS = P["FACE_WIDTH"] / (2 * math.sqrt(3))
BAND = (2402e6, 2480e6)
PCB_OUT = os.path.join(HERE, "..", "shield_deck", "pcb", "out")
DECKS = {f"d{s:g}": s for s in (P["DECK_VARIANTS"] if isinstance(P["DECK_VARIANTS"], tuple) else (P["DECK_VARIANTS"],))}


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
    ap.add_argument("--spacing", type=float,
                    help="antenna axis -> copper face, mm (default DUCK_SPACING, the D hole; with --deck, its spacing)")
    ap.add_argument("--deck", choices=sorted(DECKS), help="rev 3 deck PCB for this duck spacing (outline, or "
                                                          "its real copper with --copper)")
    ap.add_argument("--end-plate", nargs="?", const="plate", choices=["plate", "deck"],
                    help="add a plate across the far end of the core: the end plate PCB (plate, the default) or, with "
                         "--copper, a second deck board turned over (deck), its knockout left in")
    ap.add_argument("--copper", action="store_true", help="with --deck: the PCBs' real copper and a hollow core")
    ap.add_argument("--gap", type=float, default=1.0, help="feed gap, mm")
    ap.add_argument("--freq", type=float, default=P["RF_FREQ"] * 1e6, help="Hz, default RF_FREQ")
    ap.add_argument("--single", action="store_true", help="leave out the other two sectors' antennas")
    ap.add_argument("--coarse", action="store_true", help="coarser mesh, fewer timesteps: a quick check")
    ap.add_argument("--out", help="output folder (default out/<antenna>)")
    ap.add_argument("--keep", action="store_true", help="keep the raw FDTD data (prints where)")
    a = ap.parse_args()
    if a.copper and not a.deck:
        ap.error("--copper needs --deck")
    if a.end_plate == "deck" and not a.copper:
        ap.error("--end-plate deck needs --copper (as an outline it is the same disc as the end plate at d15)")
    if a.spacing is None:
        a.spacing = DECKS[a.deck] if a.deck else P["DUCK_SPACING"]
    elif a.deck and a.spacing != DECKS[a.deck]:
        print(f"note: antennas {a.spacing:g} mm out, not at deck {a.deck}'s D holes ({DECKS[a.deck]:g} mm)")
    return a


def load_copper(name):
    with open(os.path.join(PCB_OUT, name + "_copper.json")) as fh:
        return json.load(fh)


def nest_depth(polys):
    """How many other polygons' holes each polygon sits in (an island inside a hole must win over that hole)."""
    from shapely.geometry import Point, Polygon
    holes = [Polygon(h) for g in polys for h in g["holes"]]
    out = []
    for g in polys:
        p = Point(Polygon(g["outer"]).representative_point())
        out.append(sum(1 for h in holes if h.contains(p)))
    return out


def without_knockout(polys):
    """The deck as fitted: its knockout broken out for the pipe (drop the copper inside the finished hole)."""
    from shapely.geometry import Point, Polygon
    hole = Point(0, 0).buffer(P["ADAPTER_HOLE"] / 2)
    return [g for g in polys if not hole.contains(Polygon(g["outer"]))]


def mirror_x(polys):
    """A board turned over about its S0 axis (top view x -> -x)."""
    return [{"outer": [[-x, y] for x, y in g["outer"]], "holes": [[[-x, y] for x, y in h] for h in g["holes"]]}
            for g in polys]


def add_sheet(csx, metal, air, polys, z, base=10):
    """Copper polygons with holes as a zero-thickness sheet at height z: each outline metal, each hole air one
    priority above it, islands in holes higher again."""
    for g, d in zip(polys, nest_depth(polys)):
        o = np.array(g["outer"]).T
        metal.AddPolygon(o, "z", z, priority=base + 2 * d)
        for h in g["holes"]:
            air.AddPolygon(np.array(h).T, "z", z, priority=base + 2 * d + 1)


def add_face(metal, air, face, sector, thick, base=30):
    """One face board as a solid slab (both copper layers and the FR-4 between, all metal here): outer copper on
    the face line (INRADIUS out), the slab reaching `thick` inward, holes as air. Face json: x along the face
    (clockwise), y = -60 at the deck edge and +60 at the end plate edge; the tabs pass through both plates' slots.
    Built for sector 0 (normal +y; LinPoly points are (z, x) for a y normal) and turned clockwise by `sector`."""
    for g in face["layers"]["F.Cu"]:
        for pts, kind, pr in [(g["outer"], metal, base)] + [(h, air, base + 1) for h in g["holes"]]:
            zx = np.array([[-(y + 60.0) for x, y in pts], [x for x, y in pts]])
            prim = kind.AddLinPoly(zx, "y", INRADIUS - thick, thick, priority=pr)
            prim.AddTransform("RotateAxis", "z", -sector)


def build(a):
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS

    f0 = a.freq
    lam = C0 / f0 * 1e3
    length = a.length or 0.95 * lam / (4 if a.antenna == "monopole" else 2)
    R = (layout.deck_diameter(DECKS[a.deck]) if a.deck else P["DISC_DIAMETER"]) / 2
    H = P["FACE_H"]
    T = P["FACE_THICK"]                               # board thickness: deck top copper at z = T with --copper

    fdtd = openEMS(NrTS=20000 if a.coarse else 60000, EndCriteria=1e-4)
    fdtd.SetGaussExcite(f0, 0.5e9)                    # covers about 1.9-3.0 GHz
    fdtd.SetBoundaryCond(["PML_8"] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)

    pec = csx.AddMetal("copper")
    air = csx.AddMaterial("air", epsilon=1.0)       # holes in copper sheets (higher priority than the sheet)
    circ = lambda r, n=72: np.array([[r * math.cos(2 * math.pi * i / n) for i in range(n)],  # noqa: E731
                                     [r * math.sin(2 * math.pi * i / n) for i in range(n)]])
    verts = [pol(2 * INRADIUS, v) for v in (60.0, 180.0, 300.0)]
    zl = [0.0]
    if not a.copper:
        # deck: zero-thickness disc at z = 0 (the rev 3 deck: its diameter and the pipe hole)
        pec.AddPolygon(circ(R), "z", 0.0, priority=10)
        if a.deck:
            air.AddPolygon(circ(P["ADAPTER_HOLE"] / 2, 48), "z", 0.0, priority=11)
        # core: solid triangular prism from the deck down to FACE_H, vertices between the faces
        tri = np.array([[v[0] for v in verts], [v[1] for v in verts]])
        pec.AddLinPoly(tri, "z", -H, H, priority=10)
        if a.end_plate:
            pec.AddPolygon(circ(P["ENDPLATE_DIAMETER"] / 2), "z", -H, priority=10)
    else:
        # the PCBs' copper: deck bottom (shield) at z = 0, top at z = T, joined by the plated barrels
        deck = load_copper(f"deck_{a.deck}")
        ko = P["ADAPTER_HOLE"] / 2

        def barrels(z0, z1, flip=False, keep_ko=True):
            for x, y, d in deck["barrels"]:
                if not keep_ko and math.hypot(x, y) < ko:
                    continue
                x = -x if flip else x
                pts = [(x, y)] if d <= 1.0 else [(x + d / 2 * math.cos(k * math.pi / 2),
                                                   y + d / 2 * math.sin(k * math.pi / 2)) for k in range(4)]
                for px, py in pts:
                    pec.AddBox([px, py, z0], [px, py, z1], priority=40)
        add_sheet(csx, pec, air, without_knockout(deck["layers"]["B.Cu"]), 0.0)
        add_sheet(csx, pec, air, without_knockout(deck["layers"]["F.Cu"]), T)
        barrels(0.0, T, keep_ko=False)
        # hollow core: the three face boards
        face = load_copper("face_pcb")
        for s in SECTORS:
            add_face(pec, air, face, s, T)
        if a.end_plate == "plate":   # inside copper at z = -H (the two layers are the same GND copper; one sheet)
            add_sheet(csx, pec, air, load_copper("endplate_pcb")["layers"]["F.Cu"], -H)
        elif a.end_plate == "deck":  # a deck turned over: its bottom (shield) up to the core at -H, top 1.6 below
            add_sheet(csx, pec, air, mirror_x(deck["layers"]["B.Cu"]), -H)
            add_sheet(csx, pec, air, mirror_x(deck["layers"]["F.Cu"]), -H - T)
            barrels(-H - T, -H, flip=True)
            zl += [-H - T]
        zl += [T]

    # antennas at the D holes, hanging straight down; sector 0 fed, the others 50 ohm loads
    ports = []
    feeds = SECTORS if not a.single else SECTORS[:1]
    for i, s in enumerate(feeds):
        x, y = pol(INRADIUS + a.spacing, s)
        if a.copper:   # the RP-SMA bulkhead body fills its hole and bonds both deck layers
            pec.AddCylinder([x, y, 0.0], [x, y, T], P["HOLE_RPSMA"] / 2, priority=40)
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
    if a.copper:   # the face slabs: both surfaces of face 0 (normal +y); the others are slanted (staircased)
        mesh.AddLine("y", [round(INRADIUS - T, 4), round(INRADIUS, 4)])   # rounded as pol(): no near-duplicates
    x0, y0 = pol(INRADIUS + a.spacing, 0.0)
    mesh.AddLine("y", [y0 - fine, y0 + fine])
    mesh.AddLine("x", [x0 - fine, x0 + fine])
    for d in "xyz":
        mesh.SmoothMeshLines(d, coarse, 1.4)
    nf2ff = fdtd.CreateNF2FFBox()
    info = dict(f0=f0, lam=lam, length=length, R=R, cells=[len(mesh.GetLines(d)) for d in "xyz"])
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

    lines = [(f"PCBs (rev 3): deck {a.deck}, {2 * info['R']:.1f} mm, "
              + ("real copper, hollow face-board core" if a.copper else "outline: disc + pipe hole, solid core")
              + ({"plate": ", end plate", "deck": ", a second deck board as end plate (knockout in)"}.get(a.end_plate,
                                                                                                     ", no end plate"))
              ) if a.deck else
             f"deck: {2 * info['R']:.0f} mm disc, solid core" + (", end plate" if a.end_plate else ""),
             f"antenna: {a.antenna}, element {info['length']:.1f} mm, {a.spacing:g} mm in front of the face"
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
