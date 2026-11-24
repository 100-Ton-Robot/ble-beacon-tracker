"""Printed dipole "fin" for one sector: geometry (shared with the print template) and an openEMS model.

The fin is a small double-sided board standing straight out from a face, at the face centre, in a vertical plane
through the face normal. Fin-local coordinates, mm:
  u  out from the face's outer copper (u = 0 at the face, tabs at u < 0 go through the face slots)
  v  along the face height, v = 0 on the fin's slot centre line, which sits on the face hole (face centre)
Side B ("ground" side): two strips from the face out to the dipole, a slot of width `g` between them (the balun:
a slotline shorted by the face, about a quarter wave long), each strip turning into one dipole arm at u = S.
Side A ("feed" side): a 50 ohm microstrip over the lower strip from the face end, crossing the slot at u = uc and
ending in an open stub over the upper strip that runs back toward the face.
Everything is rectangles with straight edges and >= 1 mm gaps, so it can be scored and peeled by hand.

    python3 fin_model.py                       # one fin on a single sector, S11 over the BLE band
    python3 fin_model.py --coarse              # quick look
    python3 fin_model.py --set L=52 Lsh=7      # override parameters
    python3 fin_model.py --all --nf2ff         # all three sectors (other two in 50 ohm), pattern.csv for bearing_sim

Geometry for the global model follows sector_model.py: deck at z = 0, core below to -FACE_H, sector 0's face
normal +y, its outer copper at y = INRADIUS.
"""
import argparse
import json
import math
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

C0 = 299_792_458.0
EPS0 = 8.854187817e-12

# The fin's own numbers: parameters.csv beside this file (tuned 2026-11-23). The face thickness and hole come from
# common/parameters.csv (FACE_THICK, DIPOLE_HOLE), so the fin follows the mast.
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "common"))
import params  # noqa: E402
import layout  # noqa: E402


def _load_defaults():
    import csv
    d = {}
    with open(os.path.join(HERE, "parameters.csv"), newline="") as fh:
        for row in csv.DictReader(fh):
            d[row["name"]] = float(row["value"])
    C = params.load()
    d["face_t"] = float(C["FACE_THICK"])
    d["hole"] = float(C["DIPOLE_HOLE"])
    return d


DEFAULTS = _load_defaults()
MIN_GAP = 1.0     # score-and-peel: no copper gap under this
MIN_EDGE = 1.0    # copper -> board edge


def h_diel(p):
    return round(p["t"] - 2 * p["cu"], 3)


def geometry(p):
    """All copper as rectangles (u0, v0, u1, v1) per side, plus outline and tabs. Pure function of p."""
    g2 = p["g"] / 2
    S, Wa, L, Ws, Wf = p["S"], p["Wa"], p["L"], p["Ws"], p["Wf"]
    ua0, ua1 = S - Wa / 2, S + Wa / 2
    B = [
        (0.0, -g2 - Ws, ua1, -g2),          # lower strip (face -> arm)
        (0.0, g2, ua1, g2 + Ws),            # upper strip
        (ua0, -L / 2, ua1, -g2),            # lower arm
        (ua0, g2, ua1, L / 2),              # upper arm
    ]
    vf = -g2 - Ws / 2                       # feed centre line, on the lower strip's centre
    vs = g2 + Ws / 2                        # stub's return leg centre line, on the upper strip's centre
    uc = p["uc"]
    A = [
        (p["u0"], vf - Wf / 2, uc + Wf / 2, vf + Wf / 2),          # feed along u
        (uc - Wf / 2, vf - Wf / 2, uc + Wf / 2, vs + Wf / 2),       # leg across the slot
        (uc - Wf / 2 - p["Lsh"], vs - Wf / 2, uc + Wf / 2, vs + Wf / 2),  # open stub back toward the face
    ]
    e = p.get("etch", 0.0)
    if e:
        grow = lambda r, keep_u0: (r[0] if keep_u0 else r[0] - e, r[1] - e, r[2] + e, r[3] + e)  # noqa: E731
        B = [grow(r, r[0] == 0.0) for r in B]
        A = [grow(r, i == 0) for i, r in enumerate(A)]   # feed keeps its start (the port) at u0
    # board: from the face out to past the arms, arms' length plus margin
    ob = (0.0, -L / 2 - p["m"], ua1 + p["m"], L / 2 + p["m"])
    # tabs: on side B's strips, at their outer edges (clear of the face hole round v = 0)
    tv = [-g2 - Ws + p["m"] / 2 + p["tab_w"] / 2, g2 + Ws - p["m"] / 2 - p["tab_w"] / 2]
    tabs = [(-p["tab_len"], v - p["tab_w"] / 2, 0.0, v + p["tab_w"] / 2) for v in tv]
    stub_len = (vs + Wf / 2 - g2) + p["Lsh"]      # open stub length past the slot, along its centre roughly
    return dict(A=A, B=B, outline=ob, tabs=tabs, vf=vf, vs=vs, port=(p["u0"], vf, Wf + 2 * e), stub_len=stub_len)


def check(p, geo=None):
    """Score-and-peel / fit rules. Returns a list of problems (empty = OK)."""
    geo = geo or geometry(p)
    bad = []
    g2 = p["g"] / 2
    if p["g"] < MIN_GAP:
        bad.append(f"slot gap {p['g']} < {MIN_GAP}")
    # stub end must stay clear of the face end (gap to u = 0, where the board meets the face)
    stub_u0 = p["uc"] - p["Wf"] / 2 - p["Lsh"]
    if stub_u0 < MIN_GAP:
        bad.append(f"stub runs to u {stub_u0:.2f}, within {MIN_GAP} of the face")
    # crossing leg must stay off the arm (gap along u to the arm's face-side edge is bare on side A: fine, but keep
    # the leg over the strips so the microstrip has ground under it)
    if p["uc"] + p["Wf"] / 2 > p["S"] - p["Wa"] / 2:
        bad.append("crossing leg runs onto the arm region")
    # feed and stub must sit over their strips
    if p["Wf"] > p["Ws"] - 2:
        bad.append("strip too narrow for the feed (need Ws >= Wf + 2)")
    # stub vs feed: different strips, so separated by at least the slot; check the leg vs stub on side A are one piece
    # tabs clear of the face hole
    r = p["hole"] / 2
    for (u0, v0, u1, v1) in geo["tabs"]:
        if min(abs(v0), abs(v1)) < r + 1.0 and v0 * v1 > 0:
            bad.append(f"tab at v {v0:.1f}..{v1:.1f} within 1 mm of the face hole")
    # copper to board edge
    ou0, ov0, ou1, ov1 = geo["outline"]
    for side in ("A", "B"):
        for (u0, v0, u1, v1) in geo[side]:
            if v0 < ov0 + MIN_EDGE - 1e-9 or v1 > ov1 - MIN_EDGE + 1e-9 or u1 > ou1 - MIN_EDGE + 1e-9:
                bad.append(f"side {side} copper within {MIN_EDGE} mm of the board edge")
    return bad


# --------------------------------------------------------------------------------------------------- openEMS model

def build(p, a):
    from CSXCAD import ContinuousStructure
    from openEMS import openEMS

    P = params.load()
    INRADIUS = round(P["FACE_WIDTH"] / (2 * math.sqrt(3)), 3)
    H = P["FACE_H"]
    R = layout.deck_diameter(p["S"]) / 2   # the D15 deck when S = 15
    f0 = 2.44e9
    lam = C0 / f0 * 1e3
    geo = geometry(p)
    h = h_diel(p)
    zc = -H / 2                           # slot centre line on the face hole, mid face

    def q(v):
        return [round(c, 3) + 0.0 for c in v]

    fdtd = openEMS(NrTS=80000, EndCriteria=(1e-3 if a.coarse else 1e-4))
    fdtd.SetGaussExcite(f0, 0.6e9)
    fdtd.SetBoundaryCond(["PML_8"] * 6)
    csx = ContinuousStructure()
    fdtd.SetCSX(csx)
    mesh = csx.GetGrid()
    mesh.SetDeltaUnit(1e-3)
    pec = csx.AddMetal("copper")
    air = csx.AddMaterial("air", epsilon=1.0)
    kappa = 2 * math.pi * f0 * EPS0 * p["er"] * p["tand"]
    fr4 = csx.AddMaterial("fr4", epsilon=p["er"], kappa=kappa)

    circ = lambda r, n=72: np.array([[r * math.cos(2 * math.pi * i / n) for i in range(n)],  # noqa: E731
                                     [r * math.sin(2 * math.pi * i / n) for i in range(n)]])

    def pol(r, deg):
        t = math.radians(deg)
        return round(r * math.sin(t), 4) + 0.0, round(r * math.cos(t), 4) + 0.0

    verts = [pol(2 * INRADIUS, v) for v in (60.0, 180.0, 300.0)]
    pec.AddPolygon(circ(R), "z", 0.0, priority=10)
    air.AddPolygon(circ(P["ADAPTER_HOLE"] / 2, 48), "z", 0.0, priority=11)
    tri = np.array([[v[0] for v in verts], [v[1] for v in verts]])
    pec.AddLinPoly(tri, "z", -H, H, priority=10)
    if not a.no_end_plate:
        pec.AddPolygon(circ(P["ENDPLATE_DIAMETER"] / 2), "z", -H, priority=10)

    sectors = [0.0, 120.0, 240.0] if a.all else [0.0]
    ports = []
    for i, s in enumerate(sectors):
        # build for sector 0 (fin plane x = 0, u -> +y, v -> +z), then turn clockwise by s about z
        prims = []
        # face hole: 1.6 mm deep air into the solid core (the real core is hollow behind it)
        hc = air.AddCylinder([0, INRADIUS - p["face_t"], zc], [0, INRADIUS, zc], p["hole"] / 2, priority=12)
        prims.append(hc)
        ou0, ov0, ou1, ov1 = geo["outline"]
        prims.append(fr4.AddBox(q([-h / 2, INRADIUS + ou0, zc + ov0]), q([h / 2, INRADIUS + ou1, zc + ov1]), priority=20))
        for side, x in (("A", h / 2), ("B", -h / 2)):
            for (u0, v0, u1, v1) in geo[side]:
                prims.append(pec.AddBox(q([x, INRADIUS + u0, zc + v0]), q([x, INRADIUS + u1, zc + v1]), priority=30))
        for (u0, v0, u1, v1) in geo["tabs"]:   # soldered into the face: copper on side B through the face
            prims.append(pec.AddBox(q([-h / 2, INRADIUS + u0, zc + v0]), q([-h / 2, INRADIUS + u1, zc + v1]), priority=30))
        pu, pv, pw = geo["port"]
        if i == 0:
            ports.append(fdtd.AddLumpedPort(1, 50, q([-h / 2, INRADIUS + pu, zc + pv - pw / 2]),
                                            q([h / 2, INRADIUS + pu, zc + pv + pw / 2]), "x", excite=1.0, priority=40))
        else:
            # the other radios: a 50 ohm resistive block across the feed (lumped ports can't be rotated)
            dl = 0.5
            sig = (h * 1e-3) / (50.0 * dl * 1e-3 * pw * 1e-3)
            res = csx.AddMaterial(f"load{i}", kappa=sig)
            prims.append(res.AddBox(q([-h / 2, INRADIUS + pu, zc + pv - pw / 2]), q([h / 2, INRADIUS + pu + dl, zc + pv + pw / 2]), priority=40))
            for pr in prims:
                pr.AddTransform("RotateAxis", "z", -s)

    # mesh: fine inside the fin region (sector 0), smoothed outward
    fine = 1.0 if a.coarse else 0.5
    coarse = lam / (15 if a.coarse else 20)
    margin = lam / (4 if not a.nf2ff else 2)
    ou0, ov0, ou1, ov1 = geo["outline"]
    def lines(edges, lo, hi, extra=()):
        """Structural edges kept exactly; a uniform fill at `fine` dropped wherever it falls within fine/3 of an
        edge; edges themselves merged when closer than 0.05 mm (no near-duplicates)."""
        e = sorted(set(round(v, 3) for v in edges))
        keep = []
        for v in e:
            if not keep or v - keep[-1] > 0.05:
                keep.append(v)
        fill = [v for v in np.arange(lo, hi + 1e-9, fine) if min(abs(v - k) for k in keep) > fine / 3]
        return sorted(keep + [round(v, 3) for v in fill]) + list(extra)

    yI = round(INRADIUS, 3)
    xs = lines([-h / 2, 0.0, h / 2], -3, 3, [-R - margin, R + margin])
    ys = lines([yI + u for side in ("A", "B") for r in geo[side] for u in (r[0], r[2])] + [yI, yI - p["face_t"]],
               yI + ou0 - 2, yI + ou1 + 2, [-R - margin, R + margin])
    zs = lines([zc + v for side in ("A", "B") for r in geo[side] for v in (r[1], r[3])] + [zc + ov0, zc + ov1],
               zc + ov0 - 2, zc + ov1 + 2, [0.0, -H, -H - margin, margin])
    mesh.AddLine("x", xs)
    mesh.AddLine("y", ys)
    mesh.AddLine("z", zs)
    for d in "xyz":
        mesh.SmoothMeshLines(d, coarse, 1.4)
    nf2ff = fdtd.CreateNF2FFBox() if a.nf2ff else None
    return fdtd, csx, ports, nf2ff, dict(cells=[len(mesh.GetLines(d)) for d in "xyz"], f0=f0)


def run(p, a, out):
    from openEMS import openEMS  # noqa: F401
    os.makedirs(out, exist_ok=True)
    sim = tempfile.mkdtemp(prefix="fin_")
    fdtd, csx, ports, nf2ff, info = build(p, a)
    csx.Write2XML(os.path.join(out, "model.xml"))
    print(f"mesh {info['cells']} = {np.prod(info['cells']) / 1e6:.2f} M cells", flush=True)
    fdtd.Run(sim, cleanup=True, verbose=0)
    f = np.linspace(2.3e9, 2.6e9, 301)
    for pt in ports:
        pt.CalcPort(sim, f)
    p1 = ports[0]
    s11 = p1.uf_ref / p1.uf_inc
    zin = p1.uf_tot / p1.if_tot
    s11db = 20 * np.log10(np.abs(s11))
    band = (f >= 2.400e9) & (f <= 2.4835e9)
    res = dict(params=p, worst_band_db=float(s11db[band].max()),
               f_min_mhz=float(f[np.argmin(s11db)] / 1e6), min_db=float(s11db.min()),
               s11_db={f"{fm:.0f}": float(s11db[np.argmin(abs(f - fm * 1e6))]) for fm in (2400, 2440, 2483)},
               zin_2440=[float(zin[np.argmin(abs(f - 2.44e9))].real), float(zin[np.argmin(abs(f - 2.44e9))].imag)],
               cells=info["cells"])
    np.savetxt(os.path.join(out, "s11.csv"), np.c_[f / 1e6, s11db, zin.real, zin.imag], delimiter=",",
               header="MHz,S11_dB,R,X", comments="")
    if nf2ff is not None:
        theta = np.arange(0.0, 181.0, 5.0)
        phi = np.arange(0.0, 360.0, 5.0)
        r = nf2ff.CalcNF2FF(sim, info["f0"], theta, phi, center=[0, 0, 0])
        E = r.E_norm[0]
        dbi = 20 * np.log10(E / E.max()) + 10 * np.log10(r.Dmax[0])
        el = 90.0 - theta
        az = (90.0 - phi) % 360.0
        order = np.argsort(az)
        az, dbi = az[order], dbi[:, order]
        with open(os.path.join(out, "pattern.csv"), "w") as fh:
            fh.write("az_deg,el_deg,dbi\n")
            for ti in range(len(el)):
                for pi in range(len(az)):
                    fh.write(f"{az[pi]:.0f},{el[ti]:.0f},{dbi[ti, pi]:.2f}\n")
        res["peak_dbi"] = float(dbi.max())
        if len(ports) > 1:
            i0 = int(np.argmin(abs(f - info["f0"])))
            res["isolation_db"] = [float(20 * np.log10(abs(pt.uf_tot[i0] / p1.uf_inc[i0]))) for pt in ports[1:]]
    with open(os.path.join(out, "result.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    shutil.rmtree(sim, ignore_errors=True)
    print(json.dumps({k: v for k, v in res.items() if k != "params"}), flush=True)
    return res


def parse_set(items):
    p = dict(DEFAULTS)
    for it in items or []:
        k, v = it.split("=")
        if k not in p:
            raise SystemExit(f"unknown parameter {k}")
        p[k] = float(v)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--set", nargs="*", help="parameter overrides, k=v")
    ap.add_argument("--coarse", action="store_true")
    ap.add_argument("--all", action="store_true", help="fins on all three sectors (others 50 ohm)")
    ap.add_argument("--nf2ff", action="store_true", help="far field -> pattern.csv")
    ap.add_argument("--no-end-plate", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "fin"))
    a = ap.parse_args()
    p = parse_set(a.set)
    bad = check(p)
    if bad:
        print("rule problems:", *bad, sep="\n  ")
    run(p, a, os.path.abspath(a.out))


if __name__ == "__main__":
    main()
