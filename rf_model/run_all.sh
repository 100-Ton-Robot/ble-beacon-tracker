#!/bin/sh
# Every simulation behind rf_model/README.md, in order. Re-run them all (about 4 min) after changing the model or
# parameters.csv, from the project folder:
#   docker run --rm -v "$(pwd):/work" -w /work/rf_model bletracker-openems sh run_all.sh
# Each run writes its folder under out/ (summary.txt starts with the command and date) and adds a row to
# out/runs.csv. Add new runs here, not only on the command line, so the set stays complete.
set -e
cd "$(dirname "$0")"

# antenna patterns (sector_model.py)
python3 sector_model.py --antenna monopole --coarse --out out/monopole_coarse   # mesh check for monopole
python3 sector_model.py --antenna monopole                                      # quarter-wave whip, 29.2 mm
python3 sector_model.py --antenna dipole                                        # sleeve-dipole duck, 58.4 mm, feed 45 mm down
python3 sector_model.py --antenna dipole --length 50 --out out/dipole_len50     # does the duck's match change its pattern?
# HiRO H50327 reference antenna: 108 mm long, swivel + connector ~20-25 mm, so its 2.4 GHz element sits
# somewhere 25-105 mm below the deck. Not published: bracket it with the feed 55, 65 and 75 mm down.
python3 sector_model.py --antenna dipole --centre 55 --out out/h50327_c55
python3 sector_model.py --antenna dipole --centre 65 --out out/h50327_c65
python3 sector_model.py --antenna dipole --centre 75 --out out/h50327_c75

# bearing and range accuracy (bearing_sim.py)
python3 bearing_sim.py out/monopole out/dipole --out out/bearing
python3 bearing_sim.py out/dipole out/h50327_c55 out/h50327_c65 out/h50327_c75 --out out/bearing_h50327

# antenna specs (spec_sweep.py)
python3 spec_sweep.py out/monopole out/dipole --out out/spec_sweep
