"""Record several scanners side by side over their USB consoles and compare them.

Each board's `list on` table is read in its own thread and stamped with the PC
second it arrived in (the boards' 1 s windows aren't aligned, so seconds match
to within one window). Works with firmware 0.3.0 (no `chan`) and later:
    python multi_compare.py --ports COM4 COM6 COM10 --secs 300
    python multi_compare.py --ports COM4 COM6 COM10 --secs 300 --chan 38 38 38

Reports per board: chip ID, version, unique addresses, devices/s, adverts/s;
addresses heard by every board vs only some; and, for addresses heard in at
least half the seconds by two boards, the median per-second RSSI difference
(board offset) and its spread.
"""

import argparse
import re
import statistics
import sys
import threading
import time
from collections import defaultdict
from itertools import combinations

import serial

SEP = re.compile(r"--- (\d+) devices, (\d+) adverts")
ROW = re.compile(r"([0-9A-F:]{17}) (random|public)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(-?\d*)\s+(\d+)\s*$")
CHIP = re.compile(r"chip ID ([0-9a-f]{16})")
VER = re.compile(r"version (\S+),")


class Board(threading.Thread):
    def __init__(self, name, chan, secs):
        super().__init__(daemon=True)
        self.name, self.chan, self.secs = name, chan, secs
        self.chip = self.version = "?"
        self.tables = {}  # PC second -> {addr: (med, n)}
        self.error = None

    def run(self):
        try:
            with serial.Serial(self.name, 115200, timeout=0.5) as port:
                port.dtr = True
                for cmd in ("print off", "filter off", "minrssi -127", "list off", "status"):
                    port.write((cmd + "\r\n").encode())
                t = time.monotonic()
                while time.monotonic() - t < 2:
                    line = port.readline().decode(errors="replace")
                    if m := CHIP.search(line):
                        self.chip = m.group(1)
                    if m := VER.search(line):
                        self.version = m.group(1)
                if self.chan:
                    port.write(f"chan {self.chan}\r\n".encode())
                port.write(b"list on\r\n")
                self.read(port)
                port.write(b"list off\r\nchan auto\r\n")
        except serial.SerialException as e:
            self.error = str(e)

    def read(self, port):
        cur = None
        t_end = START + 3 + self.secs
        while time.time() < t_end:
            line = port.readline().decode(errors="replace")
            if SEP.search(line):
                sec = int(time.time())
                cur = {} if sec >= START + 3 else None  # skip the first seconds
                if cur is not None:
                    self.tables[sec] = cur
                continue
            m = ROW.search(line)
            if m and cur is not None:
                cur[f"{m.group(1)} {m.group(2)[0]}"] = (int(m.group(3)), int(m.group(5)))


def main():
    global START
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ports", nargs="+", required=True)
    ap.add_argument("--secs", type=int, default=300)
    ap.add_argument("--chan", nargs="+", help="chan argument per board (0.3.1+), e.g. 38 38 38")
    args = ap.parse_args()
    chans = args.chan or [None] * len(args.ports)
    if len(chans) != len(args.ports):
        ap.error("--chan needs one value per port")

    START = int(time.time())
    boards = [Board(p, c, args.secs) for p, c in zip(args.ports, chans)]
    for b in boards:
        b.start()
    for b in boards:
        b.join()
    for b in boards:
        if b.error:
            print(f"{b.name}: {b.error}")
    boards = [b for b in boards if b.tables]

    print(f"\n{'port':6} {'chip ID':16} {'fw':7} {'chan':5} {'secs':>4} {'addrs':>5}"
          f" {'devices/s':>9} {'adverts/s':>9}")
    seen = {}
    for b in boards:
        addrs = {a for t in b.tables.values() for a in t}
        seen[b.name] = addrs
        print(f"{b.name:6} {b.chip:16} {b.version:7} {b.chan or 'auto':5} {len(b.tables):4}"
              f" {len(addrs):5} {statistics.mean(len(t) for t in b.tables.values()):9.1f}"
              f" {statistics.mean(sum(n for _, n in t.values()) for t in b.tables.values()):9.1f}")

    union = set().union(*seen.values())
    common = set.intersection(*seen.values())
    print(f"\n{len(union)} addresses in all, {len(common)} heard by every board")
    for b in boards:
        only = seen[b.name] - set().union(*(seen[o.name] for o in boards if o is not b))
        print(f"    only {b.name}: {len(only)}")

    print("\nboard offsets (addresses heard in >= 50% of seconds by both):")
    for a, b in combinations(boards, 2):
        secs = sorted(set(a.tables) & set(b.tables))
        per_addr = []
        for addr in common:
            both = [s for s in secs if addr in a.tables[s] and addr in b.tables[s]]
            if len(both) >= 0.5 * len(secs):
                diffs = [b.tables[s][addr][0] - a.tables[s][addr][0] for s in both]
                per_addr.append((addr, statistics.median(diffs), statistics.pstdev(diffs)))
        if not per_addr:
            print(f"    {b.name} - {a.name}: no address in common often enough")
            continue
        offs = [o for _, o, _ in per_addr]
        print(f"    {b.name} - {a.name}: median {statistics.median(offs):+.1f} dB over"
              f" {len(per_addr)} addresses (range {min(offs):+.1f} to {max(offs):+.1f},"
              f" mean per-second spread {statistics.mean(s for _, _, s in per_addr):.1f} dB)")

    print("\nper address: share of seconds heard / mean median RSSI")
    print(f"{'address':19}" + "".join(f"{b.name + ' ' + (b.chan or 'auto'):>17}" for b in boards))

    def share(b, addr):
        return sum(addr in t for t in b.tables.values()) / len(b.tables)

    for addr in sorted(union, key=lambda x: -max(share(b, x) for b in boards)):
        if max(share(b, addr) for b in boards) < 0.2:
            continue
        cells = []
        for b in boards:
            meds = [t[addr][0] for t in b.tables.values() if addr in t]
            cells.append(f"{share(b, addr):4.0%} {statistics.mean(meds):7.1f}" if meds else "-")
        print(f"{addr:19}" + "".join(f"{c:>17}" for c in cells))
    return 0


START = 0

if __name__ == "__main__":
    sys.exit(main())
