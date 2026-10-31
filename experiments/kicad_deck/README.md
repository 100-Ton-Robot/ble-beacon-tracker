# Experiment: shield deck through KiCad

Is KiCad a workable replacement for the hand-written Gerber writer in `shield_deck/make_shield_deck.py`?
Nothing in `shield_deck/` is changed. This folder imports that script's geometry and builds the same board as a KiCad project.

## Run

```
python build.py
```

Needs KiCad 10 (`winget install KiCad.KiCad`, which installs per-user to `%LOCALAPPDATA%\Programs\KiCad\10.0`).
The results below are from a run on 2026-10-30. `out/` is not committed (it's in `.gitignore`); run `build.py` to regenerate it.
Steps:
1. `make_deck_kicad.py` writes `shield_deck.kicad_pcb` + `.kicad_pro` as plain text (KiCad isn't needed for this step).
2. `kicad-cli pcb drc --refill-zones --save-board` fills the GND pour and checks DRC (`out/drc.rpt`).
3. `kicad-cli` exports Gerbers + Excellon (`out/gerbers/`) and 3D renders (`out/render_*.png`).
4. `compare.py` matches the drill holes and pixel-diffs each layer against `shield_deck_gerbers.zip` (`out/compare.txt`, `out/diff_*.png`: grey = both, red = script only, blue = KiCad only).

## Result (2026-10-30, KiCad 10.0.6)

| Layer | Script mm² | KiCad mm² | Differs |
| --- | --- | --- | --- |
| Drill | 51 holes | 51 holes | none (size exact, position < 0.005 mm) |
| Top / bottom copper | 15919.0 | 15919.4 | ~2.5 mm² on each side, rim only |
| Top mask | 2763.5 | 2763.6 | ~2.5 |
| Bottom mask | 4779.2 | 4779.3 | ~2.5 |
| Top silk | 89.7 | 89.7 | 0 |
| Outline | same circle (r 73, 0.1 mm) | | rasteriser artifact: KiCad draws it clockwise |

The residual differences come from KiCad turning the round pour edge into a polygon (0.005 mm max error) and from rasterising at 0.05 mm/px.
The two outputs are interchangeable for fabrication. DRC: 0 errors. The only warnings are 15 "footprint library 'deck' not configured" (cosmetic).

## Findings

- **Feasible**: same geometry, and about the same amount of code (166-line generator vs 261-line writer, which also does the SVG preview and hole table).
- **Gains**: DRC, including the 0.5 mm copper-to-edge pull-back, which KiCad applies itself from a project rule; a 3D render; a Gerber job file (`.gbrjob`); the board opens in the KiCad GUI.
- **Costs**: a ~1.5 GB KiCad install becomes a build dependency, and the zone fill needs `kicad-cli`. Copper Gerbers grow from 1.5 KB to 16 KB (polygonised pour). KiCad saves the board in its own newer format (10.0) on refill.
- **Workflow clash**: edits made in the KiCad GUI are lost on the next `build.py`, which conflicts with "regenerate from scripts".
  KiCad pays off only if the board is then maintained in KiCad, or for a new board with real parts and nets (e.g. a XIAO/JST carrier PCB), where its footprint libraries and DRC matter.
