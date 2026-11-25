#!/usr/bin/env python3
"""Write each mast build's BUILD.md (builds/pcb/BUILD.md, builds/hand/BUILD.md) from CSVs.

    python3 docs/make_build_docs.py            # both builds
    python3 docs/make_build_docs.py pcb        # one build

Nothing in a BUILD.md is typed into it. Per build, in builds/<build>/:
  - build_doc.csv: the doc's text, in order: one row per heading, paragraph, list item or table, each with the
    choice labels it applies to;
  - build_options.csv: the decisions before building, one row per option, each with its label (the boxed name the
    other rows use);
  - bom.csv: parts, one row per part and choice;
  - boards.csv (pcb): the PCBs to order; drills.csv and zip_ties.csv (hand).
Numbers come from the parameter CSVs: text writes {NAME} for a parameter (common/parameters.csv, the build's own
parameters.csv or fab/board_rules.csv), {NAME:0} for one element of a tuple, and {=NAME} for a value derived here
from common/layout.py or a generated board (DERIVED below). Each is written with an invisible marker,
<!--p:NAME-->value unit<!--/p-->, so a later check can find it. An unknown name or label stops the script.
"""
import csv
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "common"))
import params   # noqa: E402
import layout   # noqa: E402

ALL = "All builds"


def units():
    """{NAME: unit} over every parameter file and the fab rules."""
    out = {}
    paths = [params.csv_path(b) for b in (None,) + params.BUILDS] + [params.FAB_RULES]
    for p in paths:
        for r in params.rows(p):
            out[r["name"]] = r["unit"]
    return out


def inch(v):
    """2.25 -> '2-1/4'."""
    whole, frac = int(v), v - int(v)
    if frac < 1e-6:
        return f"{whole}"
    n = round(frac * 64)
    d = 64
    while n % 2 == 0 and d > 1:
        n, d = n // 2, d // 2
    return f"{whole}-{n}/{d}" if whole else f"{n}/{d}"


def show(v, unit):
    """A value with its unit, as a reader sees it."""
    if unit == "in":                   # params.parse() stores inches as mm
        return f"{inch(v / 25.4)} in"
    s = params.fmt(v)
    if isinstance(v, float) and v.is_integer():
        s = f"{v:g}"
    if unit in ("", "count", "ratio", "text", "pins", "name"):
        return s
    if unit == "x mm":                 # a size: (w, h) -> 'w x h mm'
        return " x ".join(f"{a:g}" for a in v) + " mm"
    if " " in unit:                    # tuple with one unit per element: '25.75 342' + 'mm deg'
        vs, us = s.split(), unit.split()
        return " / ".join(f"{a} {b}" for a, b in zip(vs, us))
    return f"{s} {unit}"


def drill_inch(mm):
    """Nearest drill at or just above `mm` from the usual fractional sets: 1/64 in up to 1/2 in, 1/16 in above."""
    step = 1 / 64 if mm <= 12.7 else 1 / 16
    k = math.ceil((mm - 0.05) / 25.4 / step)
    return inch(k * step) + '"'


class Doc:
    def __init__(self, build):
        self.build = build
        self.dir = os.path.join(ROOT, "builds", build)
        self.P = dict(params.load(build=build))
        self.P.update(params.load_fab())
        self.U = units()
        self.D = {}                     # derived values: name -> (value, unit)
        self.opts = self.rows("build_options.csv")
        self.labels = [ALL] + [o["label"] for o in self.opts if o["label"]]
        self.used = set()

    def rows(self, name):
        p = os.path.join(self.dir, name)
        with open(p, newline="") as f:
            return [r for r in csv.DictReader(f) if not r.get("name", r.get("kind", "x")).startswith("#")]

    # -- values ------------------------------------------------------------------------------------------------
    def value(self, name, idx=None):
        if name.startswith("="):
            n = name[1:]
            if n not in self.D:
                raise SystemExit(f"{self.build}: derived value {n!r} is not defined in make_build_docs.py")
            v, u = self.D[n]
        else:
            n = name
            if n not in self.P:
                raise SystemExit(f"{self.build}: {{{n}}} is not a parameter")
            v, u = self.P[n], self.U.get(n, "")
        if idx is not None:
            v = v[idx]
            u = u.split()[idx] if " " in u else u
        self.used.add(n)
        return n, v, u

    def num(self, name, idx=None):
        return self.value(name, idx)[1]

    def fill(self, text):
        """{NAME}, {NAME:0}, {=DERIVED} -> marked values; [Label] -> boxed label (checked)."""
        def sub(m):
            n, v, u = self.value(m.group(1), int(m.group(2)) if m.group(2) else None)
            return f"<!--p:{n}-->{show(v, u)}<!--/p-->"
        text = re.sub(r"\{(=?[A-Z][A-Z0-9_]*)(?::(\d+))?\}", sub, text)
        return re.sub(r"\[\[([^\]]+)\]\]", lambda m: self.box(m.group(1)), text)

    def box(self, label):
        if label not in self.labels:
            raise SystemExit(f"{self.build}: label [{label}] is not in build_options.csv")
        return f"`[{label}]`"

    def boxes(self, tags):
        tags = [t.strip() for t in (tags or ALL).split(";") if t.strip()]
        return " ".join(self.box(t) for t in tags)

    # -- blocks ------------------------------------------------------------------------------------------------
    def options_table(self):
        out = ["| # | Decision | Option | Label | What it changes |", "| --- | --- | --- | --- | --- |"]
        last = None
        for o in self.opts:
            first = o["decision"] != last
            last = o["decision"]
            out.append(f"| {o['decision'] if first else ''} | {self.fill(o['question']) if first else ''} | "
                       f"{self.fill(o['option'])} | {self.box(o['label']) if o['label'] else '-'} | {self.fill(o['changes'])} |")
        return out

    def bom_table(self, part_of):
        rows = [r for r in self.rows("bom.csv") if r["table"] == part_of]
        cols = self.matrix_labels()
        if cols:
            head = "| Part | For | " + " | ".join(self.box(c) for c in cols) + " |"
            out = [head, "| --- | --- |" + " :---: |" * len(cols)]
            for r in rows:
                tags = [t.strip() for t in (r.get("applies_to") or ALL).split(";")]
                cells = [self.cell(r, c, tags) for c in cols]
                extra = [self.box(t) for t in tags if t != ALL and t not in cols]
                out.append(f"| {self.fill(r['part'])}{' ' + ' '.join(extra) if extra else ''} | "
                           f"{self.fill(r['note'])} | " + " | ".join(cells) + " |")
            return out
        out = ["| Ref | Part | Applies to | Qty | Note |", "| --- | --- | --- | --- | --- |"]
        for r in rows:
            out.append(f"| {r['ref'] or '-'} | {self.fill(r['part'])} | {self.boxes(r['applies_to'])} | "
                       f"{self.fill(r['qty'])} | {self.fill(r['note'])} |")
        return out

    def cell(self, r, label, tags):
        """Quantity for one label column: the row's own column of that name if it has one, else qty when the row
        applies to the label."""
        if label in r:
            return self.fill(r[label]) if r[label] else "-"
        return self.fill(r["qty"]) if (ALL in tags or label in tags) else "-"

    def matrix_labels(self):
        """Labels of the decision whose options become quantity columns (build_options.csv column `columns`)."""
        return [o["label"] for o in self.opts if o.get("columns", "").strip() == "yes"]

    def block(self, r):
        kind, text, tags = r["kind"], r["text"], r["applies_to"]
        pre = (self.boxes(tags) + " ") if tags else ""
        if kind == "h1":
            return ["# " + self.fill(text), ""]
        if kind == "h2":
            return ["## " + self.fill(text), ""]
        if kind == "h3":
            return ["### " + self.fill(text), ""]
        if kind == "p":
            return [pre + self.fill(text), ""]
        if kind == "note":
            return ["> " + pre + self.fill(text), ""]
        if kind == "li":
            return ["- " + pre + self.fill(text)]
        if kind == "check":
            return ["- [ ] " + pre + self.fill(text)]
        if kind == "step":
            return ["1. " + pre + self.fill(text)]
        if kind == "end":                     # closes a list
            return [""]
        if kind == "code":
            return ["```", self.fill(text).replace("\\n", "\n"), "```", ""]
        if kind == "mermaid":
            return ["```mermaid", text.replace("\\n", "\n"), "```", ""]
        if kind == "table":
            fn = getattr(self, "table_" + text)
            return fn() + [""]
        raise SystemExit(f"{self.build}: unknown kind {kind!r} in build_doc.csv")

    def table_options(self):
        return self.options_table()

    def table_bom(self):
        return self.bom_table("main")

    def table_bom_more(self):
        return self.bom_table("more")

    def write(self):
        body = []
        for r in self.rows("build_doc.csv"):
            body += self.block(r)
        head = body[:2]
        note = (f"<!-- Generated by docs/make_build_docs.py from builds/{self.build}/build_doc.csv and the CSVs beside "
                f"it, common/parameters.csv, builds/{self.build}/parameters.csv, fab/board_rules.csv and "
                f"common/layout.py. Do not edit by hand: change the CSVs and rerun the script. -->")
        text = "\n".join(head + [note, ""] + body[2:]).rstrip() + "\n"
        text = re.sub(r"\n{3,}", "\n\n", text)
        path = os.path.join(self.dir, "BUILD.md")
        with open(path, "w") as f:
            f.write(text)
        print(f"wrote {os.path.relpath(path, ROOT)} ({len(self.used)} values)")


class PcbDoc(Doc):
    def __init__(self):
        super().__init__("pcb")
        for s in self.P["DECK_VARIANTS"]:
            self.D[f"DECK_DIAMETER_D{s:g}"] = (layout.deck_diameter(float(s)), "mm")
        self.D["FACE_SIZE"] = ((self.P["FACE_W"], round(self.P["FACE_H"] + 2 * self.P["FACE_THICK"], 1)), "x mm")
        self.D["KO_BRIDGE_W"] = (max(self.P["KO_BRIDGE"][0], self.P["FAB_BREAKAWAY_TAB_MIN"]), "mm")
        rc = self.P["ADAPTER_HOLE"] / 2 - self.P["KO_CHANNEL"] / 2
        n = int(self.P["KO_BRIDGE"][1])
        self.D["KO_GAP_L"] = (round((2 * math.pi * rc - n * self.D["KO_BRIDGE_W"][0]) / n, 1), "mm")
        self.D["GUSSET_SIZE"] = (self.board_size("gusset_pcb"), "x mm")
        self.D["SLOT_COUNT"] = (3 * len(self.P["FACE_TABS"]), "count")

    def board_size(self, stem):
        """Board outline size from the generated KiCad file, (w, h) rounded to 0.1 mm."""
        import pcbnew
        b = pcbnew.LoadBoard(os.path.join(self.dir, "out", stem + ".kicad_pcb"))
        outline = pcbnew.SHAPE_POLY_SET()
        b.GetBoardPolygonOutlines(outline)
        bb = outline.BBox()                  # the routed outline itself, without the Edge.Cuts line width
        return (round(pcbnew.ToMM(bb.GetWidth()), 1), round(pcbnew.ToMM(bb.GetHeight()), 1))

    def order_qty(self, need):
        m = int(self.P["FAB_MIN_QTY"])
        return max(m, math.ceil(need / m) * m)

    def table_boards(self):
        """One row per board design. Order counts: the most a mast can need (with the end plate), for 1 and 3 masts,
        rounded up to FAB_MIN_QTY."""
        out = ["| Board | Applies to | File | Size | Per mast | Order, 1 mast | Order, 3 masts |",
               "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in self.rows("boards.csv"):
            per, more = int(r["per_mast"]), int(r["per_mast_end_plate"] or r["per_mast"])
            each = f"{per}" if more == per else f"{per} ({more} with {self.box('End plate')})"
            out.append(f"| {self.fill(r['board'])} | {self.boxes(r['applies_to'])} | `out/{r['file']}_gerbers.zip` | "
                       f"{self.fill(r['size'])} | {each} | {self.order_qty(more)} | {self.order_qty(3 * more)} |")
        return out


class HandDoc(Doc):
    def __init__(self):
        super().__init__("hand")
        for s in self.P["DECK_VARIANTS"]:
            self.D[f"DECK_DIAMETER_D{s:g}"] = (layout.deck_diameter(float(s)), "mm")

    def table_drills(self):
        cols = self.matrix_labels()
        out = ["| Drill | Inch | For | " + " | ".join(self.box(c) for c in cols) + " |",
               "| --- | --- | --- |" + " :---: |" * len(cols)]
        for r in self.rows("drills.csv"):
            n, v, u = self.value(r["hole"])
            mm = v                              # inches are stored as mm
            size = f"<!--p:{n}-->{show(v, u)}<!--/p-->"
            if r["tool"]:
                size += f" {r['tool']}"
            ins = inch(v / 25.4) + '"' if u == "in" else drill_inch(mm)
            if u == "in":
                size += f" ({mm:.0f} mm)"
            cells = [self.cell(r, c, [ALL]) for c in cols]
            out.append(f"| {size} | {ins} | {self.fill(r['for'])} | " + " | ".join(cells) + " |")
        return out

    def table_zip_ties(self):
        cols = self.matrix_labels()
        out = ["| Length | For | " + " | ".join(self.box(c) for c in cols) + " |",
               "| --- | --- |" + " :---: |" * len(cols)]
        tot = {c: {} for c in cols}
        for r in self.rows("zip_ties.csv"):
            cells = []
            for c in cols:
                q = r.get(c, "")
                cells.append(q or "-")
                if q:
                    tot[c][r["length_mm"]] = tot[c].get(r["length_mm"], 0) + int(q)
            mm = float(r["length_mm"])
            out.append(f"| {mm:g} mm ({round(mm / 25.4):g}\") | {self.fill(r['for'])} | " + " | ".join(cells) + " |")
        out.append("| | **Total** | " + " | ".join(
            "**" + ", ".join(f"{q} x {float(l):g}" for l, q in sorted(tot[c].items(), key=lambda kv: float(kv[0])))
            + "**" for c in cols) + " |")
        return out


BUILDS = {"pcb": PcbDoc, "hand": HandDoc}

if __name__ == "__main__":
    for b in (sys.argv[1:] or list(BUILDS)):
        BUILDS[b]().write()
