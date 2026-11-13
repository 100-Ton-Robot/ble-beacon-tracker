"""Read and write parameters.csv, the one place every shield deck / plate / template number lives.

Columns: name, value, unit, source, group, note.
- value: one number, or several separated by spaces (a tuple, e.g. "33.0 5.0 -13.0"). Whole numbers written without a
  decimal point load as int (counts, pin numbers, signs); everything else loads as float.
- unit: mm, deg, in (converted to mm on load), count, pin, sign, ratio. Shown for people; only "in" changes the value.
- source: measured / spec (datasheet, standard) / estimated / assumed / design (a choice) / rule (a clearance the
  layout must keep; read_plate_svg.py checks them) / drawing (only changes how a page is drawn).
- group: deck (make_shield_deck.py), the rest make_templates.py and the SVG tools (panel, plate, wiring, alt, pipe,
  stack, rules, formulas).

Values derived from others (MOUNT_RADIUS, POST_SHIFT, BUS_COLS, ...) stay computed in the scripts so they can't
drift out of step with what they're derived from.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "parameters.csv")
FIELDS = ["name", "value", "unit", "source", "group", "note"]


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


def load(groups=None, exclude=(), path=CSV_PATH):
    """{name: value} for the rows in `groups` (all when None), minus the groups in `exclude`."""
    out = {}
    for r in rows(path):
        if (groups is None or r["group"] in groups) and r["group"] not in exclude:
            try:
                out[r["name"]] = parse(r["value"], r["unit"])
            except ValueError as e:
                raise ValueError(f"{path}: {r['name']}: bad value {r['value']!r} ({e})") from None
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
    """Write new values {name: number or tuple} into the CSV, keeping every other column and row as it is.
    Returns {name: (old text, new text)} for the rows that changed."""
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
