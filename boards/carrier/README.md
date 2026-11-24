# Carrier board: one radio, Up + two branch ports

One XIAO nRF54L15 per board, with three ports on the same 4-pin pinout (1 5V, 2 GND, 3 DATA, 4 CMD):

- **Up**, toward the gateway (or the radio nearer to it): DATA is this radio's D10 TX out; CMD is its D7 RX.
- **Branch 1** and **Branch 2**, from the next radios out: DATA in on D0 and D1; 5V and CMD pass through.

So radios can chain or branch toward one gateway cable (relay protocol 4).

**Status:** designed outside this repo, not generated yet: no generator, no Gerbers. [`parameters.csv`](parameters.csv)
is empty until the board's numbers land here.
