# Simulation: unified power + LED board

ngspice models of the unified power + LED stripboard (shield deck templates page 8) and a model of the
24-pixel LED direction ring. They check the 5 V rail under the strip's load, the 3.3 V to 5 V data path
through U1, the pull-down while the ESP32 boots, and what a short on the strip does.

```sh
sudo apt install ngspice python3-numpy python3-matplotlib
sim/run_sim.sh            # all cases, then the ring model; add --no-plots to skip the PNGs
```

Results go to `sim/out/` (ignored by git): `summary.md` with every figure and check, a `.dat` trace and a
`.png` plot per case, and the generated netlists and parameter files that produced them. The script
exits 1 if a check fails.

## Files

| File | What |
|---|---|
| `parameters.csv` | Model values: splitter, wiring, loads, U1 and WS2812B input figures. Same columns as `shield_deck/parameters.csv`; `source` says which are datasheet values and which are estimates. |
| `netlists/power.cir` | Splitter (with a current limit), cord, pigtails, C1, ESP32 and XIAO loads, fuse, C2, strip feed and the strip as a PWM current load. |
| `netlists/data.cir` | ESP32 GPIO1, U1 gate 1 (behavioural: threshold, delay, output resistance), R, the data wire and the strip's DIN. |
| `netlists/boot.cir` | GPIO1 high-impedance while the ESP32 boots: U1's input leakage against R2. |
| `run_sim.py` | Fills the netlists from both CSVs, runs the cases, writes the summary and plots. |
| `ring.py` | Ring lighting toward beacon bearings, strip current against the firmware cap, over a 60 s scenario. |

The board's own values (C1, C2, R, R2, the fuse rating, pixel count and current) come from
`shield_deck/parameters.csv`, so the simulation follows any change there. Netlists hold no numbers.

## Cases

| Case | What it shows |
|---|---|
| `power_up` | PoE soft start with everything connected. |
| `hot_plug` | USB-C plugged into a splitter that is already up: the inrush into C1. |
| `full_white`, `half_pwm` | Strip from dark to 1.46 A, steady and as 400 Hz PWM with every pixel in phase. |
| `strip_short` | A short at the strip end: C1's dump through the fuse, then the splitter's current limit. |
| `data_shift`, `data_direct` | WS2812 bits (800 kHz) at DIN through U1, and straight from 3.3 V. |
| `boot_pulldown`, `boot_floating` | GPIO1 floating at boot, with and without R2. |

## Results (2026-11-20)

All checks pass; two warnings, both in `strip_short`:

- The strip at full white leaves the ESP32 and XIAO feed at 4.88 V and the strip end at 4.73 V.
- Through U1, DIN swings 0 to 5 V with 793 / 393 ns highs. Straight from 3.3 V it never reaches the
  WS2812B's 0.7 x VDD.
- With R2, DIN stays at 0 V while GPIO1 floats. Without it, DIN goes high after about 8 us.
- A strip short: the splitter limits at about 2.6 A, so the fuse carries 2.3 A (115% of 2 A), where
  the 251 series has no maximum opening time, and the 5 V rail falls to 0.35 V. The ESP32 and XIAOs
  reset. C1's dump (29 A peak, 0.055 A2s) is far below what melts the fuse.
- Hot plug: about 36 A through the connector for under 50 us. Connect the board before the PoE cable.
- Ring: 25 phones close by would ask 1.26 A; a 1 A firmware cap holds it.

The splitter's limit, output capacitance and cord resistance are estimates and decide the last two
points most. Measure them on the bench and update `parameters.csv`.

The strip-short warning is an accepted risk (user, 2026-11-20): a strip short reboots the mast. It stays a
warning so a change to the splitter or fuse values shows whether it still applies.
