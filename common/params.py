"""Read and write the parameter files: every shield deck / plate / template / PCB number lives in exactly one of them.

    common/parameters.csv        geometry both builds must agree on (faces and core, duck spacing, pipe, enclosure,
                                 RF, the derived layout's inputs)
    builds/pcb/parameters.csv    the PCB build only (make_pcbs.py)
    builds/hand/parameters.csv   the hand build only (templates, plate SVGs, copper deck, LED ring add-on)

    import params
    P = params.load(build="pcb")                  # common + the PCB build's file
    P = params.load(["deck", "pipe"], build="hand")
    P = params.load()                             # common only

A name may appear in one file only: a name in two files is an error, never an override.

Columns: name, value, unit, source, group, note.
- value: one number, or several separated by spaces (a tuple, e.g. "33.0 5.0 -13.0"). Whole numbers written without a
  decimal point load as int (counts, pin numbers, signs); everything else loads as float.
- unit: mm, deg, in (converted to mm on load), count, pin, sign, ratio. Shown for people; only "in" changes the value.
- source: measured / spec (datasheet, standard) / estimated / assumed / design (a choice) / rule (a clearance the
  layout must keep; read_plate_svg.py checks them) / drawing (only changes how a page is drawn).
- group: what the row is about. Hand build: deck (make_shield_deck.py), the rest make_templates.py and the SVG tools
  (panel, plate, wiring, alt, pipe, stack, rules, formulas, led, uni). PCB build: pcb, face, endplate
  (make_pcbs.py). rf is ../rf_model (sector_model.py, size_sweep.py). A group can span files: the file says which
  build reads the row, the group what it is about. Group retired holds values a later revision dropped, kept with
  a note saying what replaced them, in the file of the build they came from; no script loads it.

Values derived from others (MOUNT_RADIUS, POST_SHIFT, BUS_COLS, ...) stay computed in the scripts (the shared ones in
layout.py) so they can't drift out of step with what they're derived from.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILDS = ("pcb", "hand")
CSV_PATH = os.path.join(HERE, "parameters.csv")
FIELDS = ["name", "value", "unit", "source", "group", "note"]


def csv_path(build=None):
    """The file for one build ("pcb", "hand"), or common/parameters.csv for None."""
    if build is None:
        return CSV_PATH
    if build not in BUILDS:
        raise ValueError(f"build {build!r}: expected one of {BUILDS}")
    return os.path.join(ROOT, "builds", build, "parameters.csv")


def _num(tok, unit):
    v = int(tok) if tok.lstrip("+-").isdigit() else float(tok)
    return v * 25.4 if unit == "in" else v


def parse(value, unit=""):
    toks = value.split()
    if not toks:
        raise ValueError("empty value")
    vals = tuple(_num(t, unit) for t in toks)
    return vals[0] if len(vals) == 1 else vals


def rows(path=CSV_PATH):
    with open(path, newline="", encoding="utf-8") as f:
        out = list(csv.DictReader(f))
    names = [r["name"] for r in out]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise ValueError(f"{path}: duplicate names {sorted(dup)}")
    return out


def _check_unique():
    """Every name in exactly one file, across common and every build (so a value can't hide behind another)."""
    seen = {}
    for b in (None,) + BUILDS:
        p = csv_path(b)
        if not os.path.exists(p):
            continue
        for r in rows(p):
            if r["name"] in seen:
                raise ValueError(f"{r['name']} is in both {os.path.relpath(seen[r['name']], ROOT)} and "
                                 f"{os.path.relpath(p, ROOT)}: every value lives in one file")
            seen[r["name"]] = p


def build_rows(build=None):
    """Rows of common/parameters.csv, then the build's own file."""
    _check_unique()
    out = rows(CSV_PATH)
    if build is not None:
        out += rows(csv_path(build))
    return out


def load(groups=None, exclude=(), build=None, path=None):
    """{name: value} for the rows in `groups` (all when None), minus the groups in `exclude`, from common plus
    `build`'s file (common only when build is None), or from the one file `path`."""
    out = {}
    src = rows(path) if path else build_rows(build)
    for r in src:
        if (groups is None or r["group"] in groups) and r["group"] not in exclude:
            try:
                out[r["name"]] = parse(r["value"], r["unit"])
            except ValueError as e:
                raise ValueError(f"{r['name']}: bad value {r['value']!r} ({e})") from None
    return out


def fmt(v):
    """Number(s) back to CSV text: 2 decimals at most, trailing zeros trimmed but floats keep one decimal."""
    if isinstance(v, (tuple, list)):
        return " ".join(fmt(x) for x in v)
    if isinstance(v, int):
        return str(v)
    s = f"{round(v, 2):.2f}".rstrip("0")
    s = s + "0" if s.endswith(".") else s
    return "0.0" if s == "-0.0" else s


def update(changes, path=CSV_PATH):
    """Write new values {name: number or tuple} into the CSV `path`, keeping every other column and row as it is.
    Every name must be in that file. Returns {name: (old text, new text)} for the rows that changed."""
    rs = rows(path)
    by = {r["name"]: r for r in rs}
    missing = set(changes) - set(by)
    if missing:
        raise KeyError(f"not in {path}: {sorted(missing)}")
    done = {}
    for n, v in changes.items():
        new = fmt(v)
        if by[n]["value"] != new:
            done[n] = (by[n]["value"], new)
            by[n]["value"] = new
    if done:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(rs)
    return done
