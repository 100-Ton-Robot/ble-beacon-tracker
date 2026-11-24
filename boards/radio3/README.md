# Three-radio board: three radios, one Up cable

All three XIAO nRF54L15 radios on one board with one Up cable to the gateway (same 4-pin pinout: 1 5V, 2 GND,
3 DATA, 4 CMD). The radios form a fixed star in board traces, as on the rev 3 deck: the head radio's D10 goes to
Up; the other two radios' D10 go to the head's D0 and D1; CMD reaches every radio's D7.

**Status:** an alternative to the per-radio [carrier](../carrier/README.md), being explored outside this repo; not
generated yet. [`parameters.csv`](parameters.csv) is empty until the board's numbers land here.
