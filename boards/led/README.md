# LED add-on board

Drives the optional LED direction ring as a separate board, so the radio boards carry no LED parts (rev 3 of the
deck dropped its LED block). Today the ring is drawn as a hand-build option: templates pages for the LED ring and
the unified power + LED board, values in the `led` and `uni` groups of
[`builds/hand/parameters.csv`](../../builds/hand/parameters.csv), and an ngspice model in [`sim/`](../../sim/README.md).

**Status:** not designed in this repo yet. [`parameters.csv`](parameters.csv) is empty until the board's numbers
land here; values that move from the hand build's file move, they are not copied (one name, one file).
