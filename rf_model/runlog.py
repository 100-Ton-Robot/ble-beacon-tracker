"""Keep a record of every run: out/runs.csv gets one row per run, and each run's summary starts with its command.

Columns: date (UTC), script, out (folder, relative to rf_model/), command, result (one line from the run).
"""
import csv
import datetime
import os
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "out", "runs.csv")


def command():
    return "python3 " + " ".join(shlex.quote(a) for a in [os.path.basename(sys.argv[0])] + sys.argv[1:])


def header():
    """First lines for a summary.txt: what made it and when."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"command: {command()}\ndate: {now}\n"


def record(out_dir, result):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    new = not os.path.exists(LOG)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    with open(LOG, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["date_utc", "script", "out", "command", "result"])
        w.writerow([now, os.path.basename(sys.argv[0]), os.path.relpath(out_dir, HERE), command(), result])
