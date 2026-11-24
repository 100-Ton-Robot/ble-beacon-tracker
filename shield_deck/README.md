# Moved: the mast builds are in `builds/` and `common/`

This folder held both builds of the mast until 2026-11-23. They now live in their own folders, each with its own
parameter file, and share one set of geometry:

| Was | Now |
| --- | --- |
| `shield_deck/pcb/` (PCB build: `make_pcbs.py`, `out/`, `REV3_PLAN.md`, previews) | [`builds/pcb/`](../builds/pcb/README.md) |
| `shield_deck/PCBWAY.md` | [`builds/pcb/PCBWAY.md`](../builds/pcb/PCBWAY.md) |
| `shield_deck/HAND_BUILD.md` and the hand build's scripts, templates PDF, plate SVGs, copper deck Gerbers, `hole_table.csv` | [`builds/hand/`](../builds/hand/README.md) (`HAND_BUILD.md` is now its `README.md`) |
| `shield_deck/parameters.csv` | split three ways: [`common/parameters.csv`](../common/parameters.csv) (shared by both builds), [`builds/pcb/parameters.csv`](../builds/pcb/parameters.csv), [`builds/hand/parameters.csv`](../builds/hand/parameters.csv). Each name is in exactly one file. |
| `shield_deck/params.py`, `shield_deck/layout.py` | [`common/params.py`](../common/params.py), [`common/layout.py`](../common/layout.py) |
| `shield_deck/pcb/kicad_lib.py` | [`boards/lib/kicad_lib.py`](../boards/lib/kicad_lib.py), shared with the module boards in [`boards/`](../boards/README.md) |

The physical layout of antennas and plates is the same in both builds: it is computed once in `common/layout.py`
from `common/parameters.csv`.
