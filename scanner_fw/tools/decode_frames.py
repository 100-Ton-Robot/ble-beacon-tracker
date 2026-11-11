"""Decode the scanner's bucket stream (protocol 3: ../PROTOCOL.md, ../proto/bletracker.proto).

Needs `pip install protobuf pyserial`. bletracker_pb2.py next to this script is generated:
    protoc -I../proto --python_out=. ../proto/bletracker.proto
(the NCS toolchain has protoc in opt/nanopb/generator-bin).

Reads either the header UART itself through a 3.3 V USB-serial adapter on D6:
    python decode_frames.py --port COM5
or the hex printed by the console's `stream dump` command, pasted or saved:
    python decode_frames.py --hex dump.txt      (or --hex - for stdin)
--json prints one JSON object per bucket instead of the summary lines.

The gateway does the same steps: split on 0x00, COBS-decode, check the CRC-16 (last two
bytes, LE), then parse the rest as a protobuf Bucket.

It also builds gateway -> scanner commands (D7). D7 is shared by all scanners, so a command
goes to one chip ID (--id, as shown in buckets and `status`) or, without --id, to all of them.
Without --port it prints the hex for the console's `inject`
command; with --port it sends them on the adapter's TX:
    python decode_frames.py --cmd "flash on" --id 1a2b3c4d5e6f7081
    python decode_frames.py --cmd "ant ext" --id 1a2b3c4d5e6f7081 --port COM5
Commands: listen on|off, flash on|off, ant int|ext, reboot,
          payloads on|off, active on|off, budget <10-90>,
          intervals [rssi=N] [payload=N] [refresh=N] [status=N] [counters=N]   (ticks),
          ignore <addr>[/bits|/mask] [save], unignore <addr>[/bits|/mask],
          ignore clear boot|saved|all       (addr bytes may be *: C1:7D:2B:*:*:*),
          ignore list                       (the scanner sends its rules in the next bucket)
          debug tx1m on|off, debug off      (0.8.0+: per-second TxDrops summary, off at boot)
--seq sets the command's seq (echoed in the scanner's CMD_OK / CMD_REJECTED event).
"""

import argparse
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bletracker_pb2 as pb  # noqa: E402
from google.protobuf.json_format import MessageToDict  # noqa: E402

CHIP_ID_LEN = 8
ADV_TYPES = ["ind", "direct", "scan", "nonconn", "scanrsp", "ext", "6", "7"]
SEVERITY = {0: "INFO", 1: "WARN", 2: "ERROR"}


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def cobs_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0 or i + code > len(data):
            raise ValueError("bad COBS code")
        out += data[i + 1:i + code]
        i += code
        if code < 0xFF and i < len(data):
            out.append(0)
    return bytes(out)


def cobs_encode(data: bytes) -> bytes:
    out = bytearray([0])
    code_at, code = 0, 1
    for b in data:
        if b == 0:
            out[code_at] = code
            code_at, code = len(out), 1
            out.append(0)
            continue
        out.append(b)
        code += 1
        if code == 0xFF:
            out[code_at] = code
            code_at, code = len(out), 1
            out.append(0)
    out[code_at] = code
    return bytes(out)


def frame(payload: bytes) -> bytes:
    """Protobuf bytes -> COBS frame with CRC and the 0x00 delimiter."""
    raw = payload + struct.pack("<H", crc16_ccitt_false(payload))
    return cobs_encode(raw) + b"\x00"


def parse_rule(text: str) -> tuple[bytes, bytes]:
    """'C1:7D:2B:*:*:*', 'C1:7D:2B:00:00:00/24' or '<addr>/<mask>' -> (masked addr, mask),
    the same forms as the scanner's `ignore` command."""
    def six(s: str) -> tuple[bytes, bytes]:
        parts = s.split(":")
        if len(parts) != 6:
            raise ValueError(f"bad address {s!r}")
        return (bytes(0 if p == "*" else int(p, 16) for p in parts),
                bytes(0 if p == "*" else 0xFF for p in parts))
    a_txt, _, m_txt = text.partition("/")
    addr, mask = six(a_txt)
    if m_txt:
        if ":" in m_txt:
            m2, wild = six(m_txt)
            if wild != b"\xff" * 6:
                raise ValueError("no * in a mask")
        else:
            bits = int(m_txt)
            if not 1 <= bits <= 48:
                raise ValueError("prefix must be 1-48 bits")
            m2 = (((1 << bits) - 1) << (48 - bits)).to_bytes(6, "big")
        mask = bytes(x & y for x, y in zip(mask, m2))
    if not any(mask):
        raise ValueError("a mask of all zeros would ignore everything")
    return bytes(x & y for x, y in zip(addr, mask)), mask


def rule_str(addr: bytes, mask: bytes) -> str:
    """(addr, mask) -> 'C1:7D:2B:00:00:00/24' etc., as the scanner's console prints it."""
    bits = format(int.from_bytes(mask, "big"), "048b")
    a = ":".join(f"{x:02X}" for x in addr)
    if bits == "1" * 48:
        return a
    n = bits.find("0")
    if "1" not in bits[n:]:
        return f"{a}/{n}"
    return a + "/" + ":".join(f"{x:02X}" for x in mask)


def build_cmd(text: str, chip_id: bytes = b"", seq: int = 0) -> bytes:
    """'flash on' -> framed Command. chip_id empty or all zeros = every scanner."""
    if chip_id and len(chip_id) != CHIP_ID_LEN:
        raise ValueError(f"chip ID must be {CHIP_ID_LEN} bytes")
    words = text.split()
    if not words:
        raise ValueError("empty command")
    on_off = {"on": True, "off": False}
    c = pb.Command(target=chip_id, seq=seq)
    name, args = words[0], words[1:]
    if name in ("listen", "flash", "payloads", "active"):
        setattr(c, {"active": "active_scan"}.get(name, name), on_off[args[0]])
    elif name == "ant":
        c.ext_antenna = {"int": False, "ext": True}[args[0]]
    elif name == "reboot":
        c.reboot = 0xA5
    elif name == "budget":
        c.budget_pct = int(args[0])
    elif name == "intervals":
        c.intervals.SetInParent()
        for a in args:
            key, val = a.split("=")
            setattr(c.intervals, key, int(val))
    elif name == "debug" and args in (["off"], ["tx1m", "off"]):
        c.debug = 0
    elif name == "debug" and args == ["tx1m", "on"]:
        c.debug = pb.DEBUG_TX_1M
    elif name == "ignore" and args == ["list"]:
        c.ignore_list = True
    elif name == "ignore" and args and args[0] == "clear":
        c.ignore_clear = {"boot": pb.IGNORE_CLEAR_TEMP, "saved": pb.IGNORE_CLEAR_SAVED,
                          "all": pb.IGNORE_CLEAR_ALL}[args[1]]
    elif name in ("ignore", "unignore"):
        if not args or len(args) > 2 or (args[1:] and (name, args[1]) != ("ignore", "save")):
            raise ValueError(f"usage: {name} <addr>[/bits|/mask]" + (" [save]" if name == "ignore" else ""))
        a, m = parse_rule(args[0])
        rule = getattr(c, name)
        rule.addr = a
        if m != b"\xff" * 6:
            rule.mask = m
        rule.save = args[1:] == ["save"]
    else:
        raise ValueError(f"unknown command {text!r}")
    return frame(c.SerializeToString())


def decode_frame(enc: bytes) -> pb.Bucket:
    raw = cobs_decode(enc)
    if len(raw) < 3:
        raise ValueError(f"short frame ({len(raw)} bytes)")
    body, crc = raw[:-2], struct.unpack("<H", raw[-2:])[0]
    if crc16_ccitt_false(body) != crc:
        raise ValueError("CRC mismatch")
    b = pb.Bucket()
    b.ParseFromString(body)
    return b


def addr(a: bytes) -> str:
    return ":".join(f"{x:02X}" for x in a)


def show(b: pb.Bucket) -> None:
    kinds = {}
    for r in b.records:
        k = r.WhichOneof("kind")
        kinds[k] = kinds.get(k, 0) + 1
    summary = " ".join(f"{k}={n}" for k, n in kinds.items())
    print(f"chip {b.chip_id.hex()} seq {b.seq} t={b.t_ms} ms "
          f"ch={b.chan or 'all'} load={b.load} {summary}")
    for r in b.records:
        k = r.WhichOneof("kind")
        if k == "rssi":
            x = r.rssi
            mean = x.rssi_sum_dbm / x.count if x.count else 0
            tx = x.tx_1m_dbm if x.HasField("tx_1m_dbm") else ""
            print(f"  rssi    {addr(x.addr)} {'random' if x.random else 'public':6} "
                  f"mean {mean:6.1f} max {x.rssi_max_dbm:4} n {x.count:2} "
                  f"{ADV_TYPES[x.adv_type & 7]:7} {tx}")
        elif k in ("advert", "scan_rsp"):
            x = getattr(r, k)
            print(f"  {k:8} {addr(x.addr)} rssi {x.rssi_dbm:4} age {x.age_ticks} "
                  f"{'refresh ' if x.refresh else ''}{x.data.hex()}")
        elif k == "event":
            e = r.event
            cat = pb.Event.Category.Name(e.category)
            print(f"  event   [{cat} {SEVERITY.get(e.severity, e.severity)}] "
                  f"{pb.Event.Code.Name(e.code)}: {e.text}")
        elif k == "status":
            s = r.status
            print(f"  status  {s.version} ant={'ext' if s.ext_antenna else 'int'} "
                  f"listening={s.listening} active={s.active_scan} payloads={s.payloads} "
                  f"flash={s.flash_mode} test_image={s.test_image} adverts={s.adverts} "
                  f"devices={s.devices} dropped={s.dropped} budget={s.budget_pct}% "
                  f"peak={s.line_peak_pct}% reasons={s.load_reasons} baud={s.baud} "
                  f"ignore={s.ignore_rules}({s.ignore_saved} saved) ignored={s.ignored} debug={s.debug} "
                  f"intervals=({MessageToDict(s.intervals)})")
        elif k == "ignore_list":
            lst = r.ignore_list
            print(f"  ignore  {len(lst.rules)} rules{' (PAUSED)' if lst.paused else ''}")
            for e in lst.rules:
                print(f"          {rule_str(e.addr, e.mask):36} {'saved' if e.saved else 'until reboot':12} "
                      f"{e.hits} hits")
        elif k == "counters":
            print(f"  counters {MessageToDict(r.counters)}")
        elif k == "tx_drops":
            t = r.tx_drops
            print(f"  txdrops {len(t.drops)} addresses, {t.omitted} omitted")
            for x in t.drops:
                fmt = pb.TxFormat.Name(x.format).replace("TX_FORMAT_", "").lower()
                print(f"          {addr(x.addr)} {'random' if x.random else 'public':6} {fmt:14} "
                      f"raw {x.raw_dbm:4} -> 1 m {x.tx_1m_dbm:4} x{x.count}")
        else:
            print(f"  unknown record {r}")


def frames_in(stream):
    """Yield the bytes between 0x00 delimiters; the first may be partial."""
    buf = bytearray()
    for chunk in stream:
        for b in chunk:
            if b == 0:
                if buf:
                    yield bytes(buf)
                buf.clear()
            else:
                buf.append(b)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--port", help="serial port wired to D6 (TX) and D7 (RX), 115200 8N1")
    src.add_argument("--hex", help="file with `stream dump` output, or - for stdin")
    ap.add_argument("--json", action="store_true", help="one JSON object per bucket")
    ap.add_argument("--cmd", help='command to send, e.g. "flash on"; prints inject hex without --port')
    ap.add_argument("--id", help="chip ID (16 hex digits) the command is for; omit for all scanners")
    ap.add_argument("--seq", type=int, default=1, help="command seq (default 1)")
    args = ap.parse_args()

    if args.cmd:
        frm = build_cmd(args.cmd, bytes.fromhex(args.id) if args.id else b"", args.seq)
        if not args.port:
            print(f"inject {frm.hex()}")
            return
        import serial  # pip install pyserial
        serial.Serial(args.port, 115200, timeout=1).write(frm)
        print(f"sent {args.cmd!r}: {frm.hex(' ')}")
        return
    if not args.port and not args.hex:
        ap.error("one of --port, --hex or --cmd is required")

    if args.hex:
        text = sys.stdin.read() if args.hex == "-" else open(args.hex, encoding="utf-8", errors="replace").read()
        # Each dump: "frame (N bytes):" then lines of hex pairs only
        stream = []
        for dump in text.split("frame (")[1:]:
            lines = dump.splitlines()[1:]
            hex_lines = []
            for line in lines:
                if not line.strip():
                    continue  # \r\r\n from some terminals
                if not re.fullmatch(r"\s*([0-9a-f]{2}\s*)+", line):
                    break
                hex_lines.append(line)
            stream.append(bytes.fromhex(" ".join(hex_lines)))
    else:
        import serial  # pip install pyserial
        port = serial.Serial(args.port, 115200, timeout=1)
        stream = iter(lambda: port.read(256), None)

    for enc in frames_in(stream):
        try:
            b = decode_frame(enc)
        except Exception as e:  # noqa: BLE001 - a bad frame must not stop the reader
            print(f"dropped frame: {e}")
            continue
        if args.json:
            print(json.dumps(MessageToDict(b, preserving_proto_field_name=True)))
        else:
            show(b)


if __name__ == "__main__":
    main()
