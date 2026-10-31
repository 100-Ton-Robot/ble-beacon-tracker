"""What per-device time slots keep and lose, from real adverts (frame v3 design).

Captures raw adverts from one scanner's USB console (`print on`, timestamped on
arrival here, a few ms of USB jitter), on one fixed channel so no second mixes
channels, as in one second of the lockstep channel plan:
    python slot_sim.py --port COM4 --secs 120 --chan 38 --out adverts.csv
then rebuilds every 1 s window per address with each slot count (each slot =
mean time, mean RSSI, count k of the adverts in it) and compares with the raw
adverts:
    python slot_sim.py --in adverts.csv --slots 1 5 10 20 32 40 100

Columns:
  entries/s    advert entries a frame would carry per second (all devices)
  bytes/s      at 3 bytes per entry (offset, rssi, k)
  merged       share of adverts that share a slot with another one
  smear ms     mean distance of an advert's time from its slot's mean time
  med err dB   |median of slot means - median of raw adverts| per address-second
               with n >= 3 (mean, 95th percentile)
  spread kept  std of a second's entries / std of its raw adverts (how much of
               the within-second variation survives)
The k-weighted mean RSSI and n are exact at any slot count.
"""

import argparse
import csv
import re
import statistics
import sys
import time
from collections import defaultdict

ADV = re.compile(r"([0-9A-F:]{17} \((?:random|public)\)) rssi=(-?\d+) type=(\d+)")


def capture(port_name, secs, chan, out):
    import serial

    n = 0
    with serial.Serial(port_name, 115200, timeout=0.2) as port, \
            open(out, "w", newline="") as f:
        port.dtr = True
        w = csv.writer(f)
        w.writerow(["t", "addr", "rssi"])
        for cmd in ("list off", "filter off", "chan " + chan):
            port.write((cmd + "\r\n").encode())
        time.sleep(2.5)  # the channel changes at the next 1 s boundary
        port.reset_input_buffer()
        port.write(b"print on\r\n")
        t0 = time.monotonic()
        while time.monotonic() - t0 < secs:
            line = port.readline()
            m = ADV.search(line.decode(errors="replace"))
            if m:
                w.writerow([f"{time.monotonic() - t0:.4f}", m.group(1), m.group(2)])
                n += 1
        port.write(b"print off\r\nchan auto\r\n")
    print(f"{n} adverts in {secs} s -> {out}")


def load(path):
    with open(path, newline="") as f:
        return [(float(r["t"]), r["addr"], int(r["rssi"])) for r in csv.DictReader(f)]


def slots_of(advs, n_slots):
    """[(mean offset, mean rssi, k)] for one address-second; advs = [(offset, rssi)]."""
    acc = defaultdict(list)
    for off, rssi in advs:
        acc[min(int(off * n_slots), n_slots - 1)].append((off, rssi))
    return [(statistics.mean(o for o, _ in v), statistics.mean(r for _, r in v), len(v))
            for _, v in sorted(acc.items())]


def analyse(rows, slot_counts):
    secs = int(max(t for t, _, _ in rows))
    windows = defaultdict(list)  # (second, addr) -> [(offset, rssi)]
    for t, addr, rssi in rows:
        s = int(t)
        if s < secs:
            windows[(s, addr)].append((t - s, rssi))
    n_adv = sum(len(v) for v in windows.values())
    print(f"{n_adv} adverts, {secs} s, {len({a for _, a in windows})} addresses, "
          f"{len(windows)} address-seconds, busiest {max(len(v) for v in windows.values())}/s")
    print("\nslots  entries/s  bytes/s  merged  smear ms  med err dB (mean / p95)  spread kept")
    print(f"  raw  {n_adv / secs:9.1f}  {2 * n_adv / secs:7.0f}       -         -"
          f"                      -            -")
    for n_slots in slot_counts:
        entries = merged = 0
        smear = []
        med_err = []
        spread = []
        for advs in windows.values():
            sl = slots_of(advs, n_slots)
            entries += len(sl)
            merged += sum(k for _, _, k in sl if k > 1)
            for off, _ in advs:
                i = min(int(off * n_slots), n_slots - 1)
                mean_t = next(o for o, _, _ in sl if min(int(o * n_slots), n_slots - 1) == i)
                smear.append(abs(off - mean_t) * 1000)
            if len(advs) >= 3:
                med_err.append(abs(statistics.median(r for _, r, _ in sl)
                                   - statistics.median(r for _, r in advs)))
                raw_sd = statistics.pstdev(r for _, r in advs)
                if raw_sd > 0:
                    spread.append(statistics.pstdev(r for _, r, _ in sl) / raw_sd
                                  if len(sl) > 1 else 0.0)
        med_err.sort()
        p95 = med_err[int(0.95 * (len(med_err) - 1))] if med_err else 0
        print(f"{n_slots:5}  {entries / secs:9.1f}  {3 * entries / secs:7.0f}"
              f"  {merged / n_adv:5.0%}  {statistics.mean(smear):8.1f}"
              f"  {statistics.mean(med_err) if med_err else 0:9.2f} / {p95:4.1f}"
              f"            {statistics.mean(spread) if spread else 0:4.0%}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port")
    ap.add_argument("--secs", type=int, default=120)
    ap.add_argument("--chan", default="38", help="chan command argument (default 38)")
    ap.add_argument("--out", default="adverts.csv")
    ap.add_argument("--in", dest="inp", help="analyse a capture instead of recording")
    ap.add_argument("--slots", type=int, nargs="+", default=[1, 5, 10, 20, 32, 40, 100])
    args = ap.parse_args()
    if args.inp:
        analyse(load(args.inp), args.slots)
    elif args.port:
        capture(args.port, args.secs, args.chan, args.out)
        analyse(load(args.out), args.slots)
    else:
        ap.error("--port or --in")
    return 0


if __name__ == "__main__":
    sys.exit(main())
