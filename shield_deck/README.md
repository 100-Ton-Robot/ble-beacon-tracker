# Shield deck: two ways to build the mast

The same mast (three 120 x 120 mm reflector faces in a triangle, a round shield deck with the antenna holes, an optional end plate) can be built two ways. The physical layout of antennas and plates is the same in both:

| Build | Doc | Files |
| --- | --- | --- |
| **PCB**: order the deck, faces and end plate from a PCB fab; the three scanners sit on the deck | [`pcb/README.md`](pcb/README.md) | `pcb/out/` (Gerbers, 1:1 print PDF), `pcb/make_pcbs.py` |
| **Hand build (scratch)**: copper-clad board, acrylic and stripboard, from printable 1:1 templates | [`HAND_BUILD.md`](HAND_BUILD.md) | `shield_deck_templates.pdf`, `make_templates.py`, plate SVGs |

Shared by both:

- [`parameters.csv`](parameters.csv): every number (loaded by [`params.py`](params.py)).
- [`layout.py`](layout.py): the derived geometry both builds use (deck size per duck spacing, antenna holes, core limit, M3 holes, XIAO and tie positions, J1 / J2), each value next to its formula. The PCB generator, the templates and the RF model (`../rf_model`) read it, so the builds can't drift apart.
