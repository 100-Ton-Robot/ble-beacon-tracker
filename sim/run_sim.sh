#!/bin/sh
# Run the unified board simulations and the ring model from any directory.
# Needs ngspice and python3 with numpy (matplotlib for the plots). Results land in sim/out/.
set -e
cd "$(dirname "$0")/.."
python3 sim/run_sim.py "$@"
python3 sim/ring.py
