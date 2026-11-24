#!/bin/sh
# Every simulation behind rf_model/README.md, in order. Re-run them all (about 4 min) after changing the model or
# the parameter files (common/, builds/*/parameters.csv), from the project folder:
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
# Is the D hole (31 mm in front of the face) the best spot? H50327 at the middle depth, moved in and out.
# 34 mm is as far out as a 6.5 mm hole fits on the 146 mm deck (about 1 mm of copper left at the rim).
python3 sector_model.py --antenna dipole --centre 65 --spacing 15 --out out/h50327_c65_s15
python3 sector_model.py --antenna dipole --centre 65 --spacing 20 --out out/h50327_c65_s20
python3 sector_model.py --antenna dipole --centre 65 --spacing 25 --out out/h50327_c65_s25
python3 sector_model.py --antenna dipole --centre 65 --spacing 34 --out out/h50327_c65_s34
# Runs without --deck model the hand build (--build hand, a plain DISC_DIAMETER disc).
# Rev 3 PCBs (builds/pcb, --build pcb), H50327 at the middle depth, end plate fitted: each deck as an outline (disc + pipe
# hole on the solid core) and as its real copper (both layers, holes, slots, hollow face-board core). Needs
# builds/pcb/out/*_copper.json from make_pcbs.py.
python3 sector_model.py --build pcb --antenna dipole --centre 65 --deck d15 --end-plate --out out/rev3_d15_outline
python3 sector_model.py --build pcb --antenna dipole --centre 65 --deck d15 --end-plate --copper --out out/rev3_d15_copper
python3 sector_model.py --build pcb --antenna dipole --centre 65 --deck d15 --end-plate deck --copper --out out/rev3_d15_copper_deckplate
python3 sector_model.py --build pcb --antenna dipole --centre 65 --deck d31 --end-plate --out out/rev3_d31_outline
python3 sector_model.py --build pcb --antenna dipole --centre 65 --deck d31 --end-plate --copper --out out/rev3_d31_copper

# bearing and range accuracy (bearing_sim.py)
python3 bearing_sim.py out/monopole out/dipole --out out/bearing
python3 bearing_sim.py out/dipole out/h50327_c55 out/h50327_c65 out/h50327_c75 --out out/bearing_h50327
python3 bearing_sim.py out/h50327_c65_s15 out/h50327_c65_s20 out/h50327_c65_s25 out/h50327_c65 out/h50327_c65_s34 \
    --out out/bearing_spacing
python3 bearing_sim.py out/rev3_d15_outline out/rev3_d15_copper out/rev3_d15_copper_deckplate out/rev3_d31_outline out/rev3_d31_copper \
    --out out/bearing_rev3

# antenna specs (spec_sweep.py)
python3 spec_sweep.py out/monopole out/dipole --out out/spec_sweep

# end plate reference: H50327, 170 mm deck, no plate / 140 mm plate
python3 sector_model.py --antenna dipole --centre 65 --set DISC_DIAMETER=170 --out out/ep_ref_0
python3 sector_model.py --antenna dipole --centre 65 --set DISC_DIAMETER=170 --end-plate --set ENDPLATE_DIAMETER=140 \
    --out out/ep_ref_140
python3 bearing_sim.py out/ep_ref_0 out/ep_ref_140 --out out/bearing_ep_ref

# mast size, sector count and end plate (size_sweep.py: each geometry is a sector_model.py run with --set overrides,
# then scored; each sweep writes its own summary.txt)
python3 size_sweep.py --sectors 3 4 --widths 120 100 80 60 --heights 120 --spacings 31 15 --elements h50327 \
    --end-plate --out out/size_h50327_ep
python3 size_sweep.py --sectors 3 4 --widths 120 100 80 60 45 --spacings 31 15 8 --elements short --end-plate \
    --out out/size_ep
python3 size_sweep.py --sectors 3 4 --widths 120 100 80 60 --heights 0 120 --spacings 31 15 --elements h50327 \
    --out out/size_h50327
python3 size_sweep.py --sectors 3 4 --widths 120 100 80 60 45 --spacings 31 15 8 --elements short --out out/size
# fine-mesh checks
python3 size_sweep.py --fine --end-plate --sectors 3 --widths 45 60 --spacings 15 --elements short --out out/size_ep_fine
python3 size_sweep.py --fine --end-plate --sectors 3 --widths 60 --heights 120 --spacings 15 --elements h50327 \
    --out out/size_h50327_ep_fine
