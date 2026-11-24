# Fab rules

What a board house can make, kept apart from the design numbers so a rule can change without touching the design.

- [`board_rules.csv`](board_rules.csv): the master. Every rule (`FAB_*`) the board generators use, set to the stricter of JLCPCB's and PCBWay's published standard 2-layer limits. The committed board outputs are built and checked with these.
- [`overrides/`](overrides/): one CSV per fab or per builder. Same columns as the master; a row replaces the master's value for that rule. An override may only change a rule the master has, never add one.
  - `jlcpcb.csv`: JLCPCB's own values where they are looser than the master.
  - `pcbway.csv`: PCBWay's own values where they are looser than the master.
  - Your own file (for example a stricter house, or a requirement such as larger silkscreen text): pass it with `--override`.

Use:

```
python3 builds/pcb/make_pcbs.py                                  # master rules -> builds/pcb/out/
python3 builds/pcb/make_pcbs.py --fab jlcpcb                     # master + overrides/jlcpcb.csv -> out_jlcpcb/
python3 builds/pcb/make_pcbs.py --fab pcbway --override mine.csv # then mine.csv, later files win -> out_pcbway-mine/
```

In Python: `params.load_fab(fab=None, overrides=())` (in `common/params.py`).

What the generator does with them (details in [`builds/pcb/README.md`](../builds/pcb/README.md#fab-rules)):

1. Stops if a design size is below a rule (track, clearance, via, annular ring, edge clearance, slot widths, the face tab and slot fits against the outline and thickness tolerances).
2. Sizes knockout bridges, mouse bites and silkscreen up to the rules.
3. Writes the rules into each board's DRC settings and `.kicad_dru`, so a broken rule is a DRC error.

Sources for the values: [JLCPCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities), [PCBWay capabilities](https://www.pcbway.com/capabilities.html). Check them again before an order; fabs change their limits.
