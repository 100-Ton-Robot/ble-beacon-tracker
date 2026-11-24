# Module boards

Small PCBs that either build of the mast can use: on the PCB build's deck or on the hand build's plate. The mast
boards themselves (deck, faces, end plate) are in [`builds/pcb/`](../builds/pcb/README.md).

| Folder | Board | Status |
| --- | --- | --- |
| [`carrier/`](carrier/README.md) | One radio, with an Up port and two branch ports, to chain or branch radios toward the gateway | not in the repo yet |
| [`radio3/`](radio3/README.md) | Three radios on one board, one Up cable to the gateway | not in the repo yet |
| [`led/`](led/README.md) | LED add-on board for the optional LED direction ring | not in the repo yet |
| [`lib/`](lib/) | `kicad_lib.py`: KiCad 7 `pcbnew` helpers shared by every board generator, the mast boards included | in use |

Each board gets its own `parameters.csv` here (empty until the board is designed), its generator and an `out/`
folder, like [`builds/pcb/`](../builds/pcb/README.md). Its numbers load with
`params.load(boards=["carrier"])` (plus `build=` when a build's values are needed too); a name may be in one file
only, across [`common/`](../common/parameters.csv), both builds and every board.

All of them use the same 4-pin cable on every port (1 5V, 2 GND, 3 DATA, 4 CMD) and the relay protocol 4 pins:
D10 uplink TX, D7 command RX, D0 / D1 branch RX. That firmware is not written yet; see
[Firmware and pins](../builds/pcb/README.md#firmware-and-pins-both-builds).
