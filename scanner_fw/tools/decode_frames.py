"""Decode the scanner's gateway frames (format in src/main.c and the README).

Reads either the header UART itself through a 3.3 V USB-serial adapter on D6:
    python decode_frames.py --port COM5
or the hex printed by the console's `stream dump` command, pasted or saved:
    python decode_frames.py --hex dump.txt      (or --hex - for stdin)

The gateway (ESPHome component) does the same steps: split on 0x00, COBS-decode,
check the CRC, then read the header and 11-byte records.

It also builds gateway -> scanner commands (D7). D7 is shared by all scanners, so
a command goes to one chip ID (--id, as shown in frames and `status`) or, without
--id, to all of them (not allowed for sector). Without --port it prints the hex for
the console's `inject` command; with --port it sends them on the adapter's TX:
    python decode_frames.py --cmd "flash on" --id 1a2b3c4d5e6f7081
    python decode_frames.py --cmd "sector 2" --id 1a2b3c4d5e6f7081 --port COM5
Commands: listen on|off, flash on|off, ant int|ext, sector <0-254>, reboot

Frame v1 (firmware before 0.3.0, no chip ID) is still decoded.
"""

import argparse
import re
import struct
import sys

HDR = struct.Struct("<BBBBHBB")
CHIP_ID_LEN = 8
HDR_LEN = {1: HDR.size, 2: HDR.size + CHIP_ID_LEN}
REC_LEN = 11
ADV_TYPES = ["ind", "direct", "scan", "nonconn", "scanrsp", "ext", "6", "7"]


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


CMDS = {"listen": (1, {"off": 0, "on": 1}), "flash": (2, {"off": 0, "on": 1}),
        "ant": (3, {"int": 0, "ext": 1}), "sector": (4, None), "reboot": (5, None)}


def build_cmd(text: str, chip_id: bytes = bytes(CHIP_ID_LEN)) -> bytes:
    """'flash on' -> COBS-encoded command frame with its 0x00 delimiter.
    chip_id all zeros = every scanner."""
    if len(chip_id) != CHIP_ID_LEN:
        raise ValueError(f"chip ID must be {CHIP_ID_LEN} bytes")
    words = text.split()
    if not words or words[0] not in CMDS:
        raise ValueError(f"unknown command {text!r}")
    cmd, args = CMDS[words[0]]
    if words[0] == "reboot":
        arg = 0xA5
    elif words[0] == "sector":
        arg = int(words[1])
        if not 0 <= arg <= 254:
            raise ValueError("sector must be 0-254")
        if not any(chip_id):
            raise ValueError("sector needs --id (every scanner would take it)")
    else:
        arg = args[words[1]]
    raw = bytes([2]) + chip_id + bytes([cmd, arg])
    raw += struct.pack("<H", crc16_ccitt_false(raw))
    return cobs_encode(raw) + b"\x00"


def decode_frame(enc: bytes) -> dict:
    raw = cobs_decode(enc)
    if len(raw) < HDR.size + 2:
        raise ValueError(f"short frame ({len(raw)} bytes)")
    body, crc = raw[:-2], struct.unpack("<H", raw[-2:])[0]
    if crc16_ccitt_false(body) != crc:
        raise ValueError("CRC mismatch")
    ver, sector, seq, flags, adverts, n_devs, dropped = HDR.unpack_from(body)
    if ver not in HDR_LEN:
        raise ValueError(f"unknown version {ver}")
    hdr_len = HDR_LEN[ver]
    if len(body) != hdr_len + n_devs * REC_LEN:
        raise ValueError(f"length {len(body)} does not match {n_devs} devices")
    chip_id = body[HDR.size:hdr_len].hex() if ver >= 2 else None
    devs = []
    for k in range(n_devs):
        r = body[hdr_len + k * REC_LEN:hdr_len + (k + 1) * REC_LEN]
        rflags = r[6]
        devs.append({
            "addr": ":".join(f"{b:02X}" for b in r[:6]),
            "random": bool(rflags & 1),
            "adv": ADV_TYPES[(rflags >> 1) & 7],
            "med": struct.unpack("b", r[7:8])[0],
            "max": struct.unpack("b", r[8:9])[0],
            "count": r[9],
            "tx_1m": struct.unpack("b", r[10:11])[0] if rflags & 0x10 else None,
        })
    return {"ver": ver, "chip_id": chip_id, "sector": sector, "seq": seq, "ext": bool(flags & 1), "full": bool(flags & 2),
            "listening": not flags & 4, "flash": bool(flags & 8), "client": bool(flags & 16),
            "test_image": bool(flags & 32),
            "adverts": adverts, "dropped": dropped, "devs": devs}


def show(f: dict) -> None:
    state = [name for name, on in (("LISTENING OFF", not f["listening"]), ("FLASH MODE", f["flash"]),
                                   ("CLIENT", f["client"]), ("TEST IMAGE", f["test_image"]),
                                   ("TABLE FULL", f["full"])) if on]
    chip = f" chip {f['chip_id']}" if f["chip_id"] else ""
    print(f"sector {f['sector']}{chip} seq {f['seq']} ant={'ext' if f['ext'] else 'int'} "
          f"adverts={f['adverts']} devices={len(f['devs'])} dropped={f['dropped']}"
          f"{''.join(' ' + s for s in state)}")
    for d in f["devs"]:
        tx = "" if d["tx_1m"] is None else d["tx_1m"]
        print(f"  {d['addr']} {'random' if d['random'] else 'public':6} {d['med']:4} {d['max']:4} "
              f"{d['count']:3} {tx!s:>5} {d['adv']}")


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
    ap.add_argument("--cmd", help='command to send, e.g. "flash on"; prints inject hex without --port')
    ap.add_argument("--id", help="chip ID (16 hex digits) the command is for; omit for all scanners")
    args = ap.parse_args()

    if args.cmd:
        frame = build_cmd(args.cmd, bytes.fromhex(args.id) if args.id else bytes(CHIP_ID_LEN))
        if not args.port:
            print(f"inject {frame.hex()}")
            return
        import serial  # pip install pyserial
        serial.Serial(args.port, 115200, timeout=1).write(frame)
        print(f"sent {args.cmd!r}: {frame.hex(' ')}")
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
            show(decode_frame(enc))
        except ValueError as e:
            print(f"dropped frame: {e}")


if __name__ == "__main__":
    main()
