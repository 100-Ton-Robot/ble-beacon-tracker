"""Compare primary-channel scan modes on one scanner over its USB console.

Runs each mode of the console's `chan` command (firmware 0.3.1+) in turn for a
few seconds, repeats the round so the room's traffic averages out, and reads the
`[1s] ... ch=.. adverts=.. devices=..` lines:
    python chan_test.py --port COM4
    python chan_test.py --port COM4 --secs 30 --rounds 4 --modes auto 39 "rot 1"

Prints adverts/s and devices/s per mode (mean, min, max), per channel inside
`rot`, and the scan restart time (`switch=`) that each channel change costs.

--by-address reads the `list on` table instead and reports, per address, the
share of seconds it was heard and its median RSSI in each mode: an address that
`auto` hears but one channel rarely does is an advertiser that skips that
channel, and steady RSSI differences between channels show the channel map
really applies. Use fixed channels (default auto 37 38 39); `rot` can't be
split by channel in this mode:
    python chan_test.py --port COM4 --by-address --secs 10 --rounds 6

Needs pyserial (opened with DTR on, or the console stays silent). Leaves the
scanner on `chan auto` with the list off.
"""

import argparse
import re
import statistics
import sys
import time

import serial

LINE = re.compile(r"\[1s\] ant=\S+ ch=(\w+)(?: switch=(\d+)us)? adverts=(\d+) devices=(\d+)")


def send(port, cmd):
    port.write((cmd + "\r\n").encode())
    port.flush()


def collect(port, secs, skip=2):
    """[1s] lines after `skip` whole seconds (the mode changes at a boundary)."""
    rows = []
    seen = 0
    deadline = time.monotonic() + secs + skip + 3
    while len(rows) < secs and time.monotonic() < deadline:
        m = LINE.search(port.readline().decode(errors="replace"))
        if not m:
            continue
        seen += 1
        if seen > skip:
            ch, sw, adv, dev = m.groups()
            rows.append((ch, int(sw) if sw else None, int(adv), int(dev)))
    return rows


SEP = re.compile(r"--- (\d+) devices, (\d+) adverts")
ROW = re.compile(r"([0-9A-F:]{17}) (random|public)\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(-?\d*)\s+(\d+)\s*$")


def collect_table(port, secs, skip=2):
    """Per-second {address: (med, count, adv type)} from `list on`, after `skip` seconds."""
    tables = []
    cur = None
    seen = 0
    deadline = time.monotonic() + secs + skip + 3
    while time.monotonic() < deadline:
        line = port.readline().decode(errors="replace")
        if SEP.search(line):
            if cur is not None:
                tables.append(cur)
                if len(tables) == secs:
                    break
            seen += 1
            cur = {} if seen > skip else None
            continue
        m = ROW.search(line)
        if m and cur is not None:
            addr, kind, med, _, n, _, adv = m.groups()
            cur[f"{addr} {kind[0]}"] = (int(med), int(n), int(adv))
    return tables


def by_address(port, modes, secs, rounds):
    tables = {m: [] for m in modes}
    send(port, "list on")
    for r in range(rounds):
        for mode in modes:
            send(port, "chan " + mode)
            t = collect_table(port, secs)
            tables[mode] += t
            print(f"round {r + 1} {mode:>6}: {len(t)} s, {len({a for s in t for a in s})} addresses",
                  flush=True)
    send(port, "list off")
    send(port, "chan auto")

    stats = {}  # addr -> mode -> (share of seconds heard, adverts/s, mean median RSSI)
    for mode, ts in tables.items():
        heard = {}
        for sec in ts:
            for addr, v in sec.items():
                heard.setdefault(addr, []).append(v)
        for addr, vs in heard.items():
            stats.setdefault(addr, {})[mode] = (
                len(vs) / len(ts), sum(n for _, n, _ in vs) / len(ts),
                statistics.mean(med for med, _, _ in vs), vs[-1][2])

    def share(addr, mode):
        return stats[addr].get(mode, (0, 0, None, None))[0]

    base = modes[0]
    order = sorted(stats, key=lambda a: -max(share(a, m) for m in modes))
    print(f"\nshare of seconds heard / adverts per s / mean median RSSI"
          f" ({', '.join(f'{m} {len(tables[m])} s' for m in modes)})")
    print("address             adv " + "".join(f"{m:>18}" for m in modes))
    for addr in order:
        if max(share(addr, m) for m in modes) < 0.2:
            continue
        adv = next(v[3] for v in stats[addr].values())
        cells = []
        for m in modes:
            s = stats[addr].get(m)
            cells.append(f"{s[0]:4.0%} {s[1]:4.1f} {s[2]:6.1f}" if s else f"{'-':>17}")
        print(f"{addr}  {adv:3} " + "".join(f"{c:>18}" for c in cells))

    rare = [a for a in order if share(a, base) >= 0.5
            and min(share(a, m) for m in modes[1:]) < 0.25 * share(a, base)]
    print(f"\nheard in >= 50% of {base} seconds but < 1/4 as often on some channel:"
          f" {len(rare)}")
    for addr in rare:
        print("    " + addr + "  " + ", ".join(f"{m} {share(addr, m):.0%}" for m in modes))

    steady = [a for a in order if all(share(a, m) >= 0.8 for m in modes)]
    if steady and len(modes) > 2:
        spreads = [max(stats[a][m][2] for m in modes[1:]) - min(stats[a][m][2] for m in modes[1:])
                   for a in steady]
        print(f"\n{len(steady)} addresses heard in >= 80% of seconds in every mode;"
              f" spread of their mean RSSI across {', '.join(modes[1:])}:"
              f" {summary([round(s, 1) for s in spreads])} dB")


def summary(vals):
    if not vals:
        return "-"
    return f"{statistics.mean(vals):6.1f} ({min(vals)}-{max(vals)})"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", required=True)
    ap.add_argument("--secs", type=int, default=20, help="seconds per mode per round")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--modes", nargs="+",
                    help='default auto 37 38 39 "rot 1" (--by-address: auto 37 38 39)')
    ap.add_argument("--by-address", action="store_true")
    args = ap.parse_args()
    modes = args.modes or (["auto", "37", "38", "39"] if args.by_address
                           else ["auto", "37", "38", "39", "rot 1"])

    results = {m: [] for m in modes}
    with serial.Serial(args.port, 115200, timeout=1) as port:
        port.dtr = True
        send(port, "print off")
        send(port, "list off")
        send(port, "filter off")
        send(port, "minrssi -127")
        if args.by_address:
            by_address(port, modes, args.secs, args.rounds)
            return 0
        for r in range(args.rounds):
            for mode in modes:
                send(port, "chan " + mode)
                rows = collect(port, args.secs)
                results[mode] += rows
                adv = [a for _, _, a, _ in rows]
                print(f"round {r + 1} {mode:>6}: {len(rows)} s, adverts/s {summary(adv)}",
                      flush=True)
        send(port, "chan auto")

    print("\nmode      seconds  adverts/s            devices/s")
    for mode, rows in results.items():
        adv = [a for _, _, a, _ in rows]
        dev = [d for _, _, _, d in rows]
        print(f"{mode:>6}  {len(rows):9}  {summary(adv):20} {summary(dev)}")

    for mode, rows in results.items():
        if not mode.startswith("rot"):
            continue
        print(f"\n{mode}, by channel:")
        for ch in ("37", "38", "39"):
            sel = [row for row in rows if row[0] == ch]
            print(f"    {ch}  {len(sel):4} s  adverts/s {summary([a for _, _, a, _ in sel]):20}"
                  f" devices/s {summary([d for _, _, _, d in sel])}")
        gaps = [sw for _, sw, _, _ in rows if sw is not None]
        if gaps:
            print(f"    scan restart: {summary(gaps)} us over {len(gaps)} switches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
