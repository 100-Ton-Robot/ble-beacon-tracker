"""Generate the gateway self-test data (components/sector_scanner/selftest_data.h).

The gateway checks itself at boot (`self_test: true`) against data made here, independently of
its C++ code:
  - the command test vectors from the ble_sector_gateway_contract atom, checked here against
    scanner_fw/tools/decode_frames.py, must encode byte for byte the same;
  - sample buckets built and framed with the reference protobuf code (bletracker_pb2), fed to a
    test sector on pin 0, must produce exactly the MQTT messages this script expects (MQTT
    layout v3, written here from the spec, not from the C++).

    python make_selftest.py [output .h]   (default: ../components/sector_scanner/selftest_data.h)

Needs `pip install protobuf` and scanner_fw/tools/bletracker_pb2.py.
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scanner_fw", "tools"))
import bletracker_pb2 as pb  # noqa: E402
import decode_frames as ref  # noqa: E402

PREFIX = "selftest"
MAST = "selftest"
PIN = 0

# From the contract atom (2026-11-02): text, chip ID ("" = all), framed hex incl. trailing 00, seq 1
CMD_VECTORS = [
    ("payloads on", "", "0710014001bab500"),
    ("payloads off", "", "04100140039ba500"),
    ("active on", "", "0710014801133c00"),
    ("active off", "", "0410014803322c00"),
    ("listen off", "", "04100118038d2200"),
    ("listen on", "", "0710011801ac3200"),
    ("flash on", "", "071001200190be00"),
    ("flash off", "", "0410012003b1ae00"),
    ("ant ext", "", "0710012801393700"),
    ("ant int", "", "0410012803182700"),
    ("reboot", "", "08100138a5014cfd00"),
    ("intervals rssi=1", "", "091001520208017ed100"),
    ("budget 50", "", "0710015832503900"),
    # Added after the contract atom (checked against decode_frames.py like the rest)
    ("ignore list", "", "0710017801863900"),
    ("debug tx1m on", "", "081001800101a87b00"),
    ("debug off", "", "051001800103896b00"),
]

CHIP = bytes.fromhex("38cd69b0ed39e516")
CATEGORY = ["GENERAL", "SECURITY", "LOAD", "COMMAND"]
SEVERITY = ["INFO", "WARN", "ERROR"]
CODES = ["UNKNOWN", "BOOT", "VERSION_CHANGED", "TEST_IMAGE", "IMAGE_CONFIRMED", "FLASH_MODE_ON",
         "FLASH_MODE_OFF", "CLIENT_CONNECTED", "CLIENT_DISCONNECTED", "SETTING_CHANGED", "CMD_OK",
         "CMD_REJECTED", "BAD_COMMANDS", "LOAD_LEVEL", "SECTOR_NOT_SET", "EVENTS_LOST"]


# ------------------------------------------------------------------ JSON as the gateway writes it

class Raw(str):
    """Inserted verbatim (numbers already formatted)."""


def dumps(v):
    import json
    if isinstance(v, Raw):
        return str(v)
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ",".join(dumps(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(dumps(k) + ":" + dumps(x) for k, x in v.items()) + "}"
    raise TypeError(type(v))


def mean1(s, c):
    if c == 0:
        return Raw("null")
    num = s * 10
    q = (2 * abs(num) + c) // (2 * c)
    return Raw(f"{'-' if num < 0 and q else ''}{q // 10}.{q % 10}")


def addr(a, sep=":"):
    return sep.join(f"{x:02X}" for x in a)


def name_str(b):
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return "".join(chr(x) if x < 0x80 else "?" for x in b)


def clean_text(b, limit):
    """Scanner text as the gateway passes it on: at most `limit` bytes, control characters and
    DEL as '?', every non-ASCII byte too unless the whole text is valid UTF-8."""
    b = b[:limit]
    try:
        b.decode("utf-8")
        utf8 = True
    except UnicodeDecodeError:
        utf8 = False
    return bytes(0x3F if x < 0x20 or x == 0x7F or (x >= 0x80 and not utf8) else x
                 for x in b).decode("utf-8")


def uuid_str(b):
    if len(b) == 2:
        return f"0x{int.from_bytes(b, 'little'):04x}"
    if len(b) == 4:
        return f"0x{int.from_bytes(b, 'little'):08x}"
    h = b[::-1].hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def ad_fields(data):
    """Theengs-style fields from raw AD bytes: first name (complete preferred), first
    manufacturer data, first service data, first tx power, every listed UUID."""
    out, name, complete, uuids = {}, None, False, []
    manu = svc = txp = None
    i = 0
    while i < len(data):
        n = data[i]
        if n == 0 or i + 1 + n > len(data):
            break
        t, v = data[i + 1], data[i + 2:i + 1 + n]
        if t in (0x08, 0x09) and (name is None or (t == 0x09 and not complete)):
            name, complete = v, t == 0x09
        elif t == 0xFF and manu is None:
            manu = v
        elif t in (0x16, 0x20, 0x21):
            ul = {0x16: 2, 0x20: 4, 0x21: 16}[t]
            if svc is None and len(v) >= ul:
                svc = (v[:ul], v[ul:])
        elif t == 0x0A and txp is None and len(v) >= 1:
            txp = struct.unpack("b", v[:1])[0]
        elif 0x02 <= t <= 0x07:
            ul = 2 if t <= 0x03 else 4 if t <= 0x05 else 16
            uuids += [uuid_str(v[k:k + ul]) for k in range(0, len(v) - ul + 1, ul)]
        i += 1 + n
    if name is not None:
        out["name"] = name_str(name)
    if manu is not None:
        out["manufacturerdata"] = manu.hex()
    if svc is not None:
        out["servicedata"] = svc[1].hex()
        out["servicedatauuid"] = uuid_str(svc[0])
    if txp is not None:
        out["txpower"] = txp
    if uuids:
        out["uuids"] = uuids
    return out


class Sector:
    """What the gateway publishes for one RX pin (non-retained topics only)."""

    def __init__(self, pin):
        self.pin, self.lost, self.bad, self.last_seq = pin, 0, 0, None
        self.bad_records = 0
        self.rssi_interval = 1
        self.out = []

    def pub(self, sub, payload):
        self.out.append((f"{PREFIX}/{self.pin}/{sub}", payload))

    def event(self, scanner, cat, sev, code, value, value2, cmd_seq, text):
        e = {"t": None, "source": "scanner" if scanner else "gateway", "sector": self.pin,
             "chip": CHIP.hex(), "category": CATEGORY[cat], "severity": SEVERITY[sev], "code": code,
             "value": value, "value2": value2, "cmd_seq": cmd_seq, "text": text}
        self.out.append((f"{PREFIX}/events", dumps(e)))
        if cat == 1:
            self.out.append((f"{PREFIX}/security", dumps(e)))

    def bad_frame(self):
        self.bad += 1

    def bucket(self, b, unknown_records=(), extra=()):
        """extra: records after b's own, in wire order: pb.Record, ("event", cat, sev, code,
        text bytes) for text a pb2 string can't hold, ("raw", num, payload) for unknown kinds,
        ("bad",) for a record the gateway must drop as malformed"""
        chip = b.chip_id.hex()
        if self.last_seq is not None and b.seq > self.last_seq:
            self.lost += b.seq - self.last_seq - 1
        self.last_seq = b.seq
        suspect = False  # no expected_chip on the test sector; the RX pin is the sector

        devs = []
        for r in list(b.records) + list(extra):
            if isinstance(r, tuple):
                if r[0] == "event":
                    _, cat, sev, code, text = r
                    self.event(True, cat, sev, CODES[code], 0, 0, 0, clean_text(text, 64))
                elif r[0] == "raw" and r[1] <= 63:
                    self.pub(f"raw/{r[1]}", r[2].hex())
                else:
                    self.bad_records += 1
                continue
            k = r.WhichOneof("kind")
            if k == "event":
                e = r.event
                self.event(True, e.category, e.severity, CODES[e.code], e.value, e.value2,
                           e.cmd_seq, clean_text(e.text.encode(), 64))
            elif k == "status":
                s = r.status
                st = {"t": None, "chip": chip, "seq": b.seq, "pin_sector": self.pin,
                      "suspect": suspect, "lost": self.lost, "bad": self.bad,
                      "bad_records": self.bad_records, "rx_overflow": 0,
                      "version": clean_text(s.version.encode(), 24)}
                for f in ("ext_antenna", "listening", "active_scan", "payloads", "flash_mode",
                          "client", "test_image", "adverts", "dropped", "devices", "load_reasons",
                          "line_peak_pct", "budget_pct"):
                    st[f] = getattr(s, f)
                st["intervals"] = {f: getattr(s.intervals, f)
                                   for f in ("rssi", "payload", "refresh", "status", "counters")}
                st["baud"] = s.baud
                self.rssi_interval = s.intervals.rssi
                self.pub("status", dumps(st))
            elif k == "counters":
                c = {"t": None, "chip": chip, "seq": b.seq}
                for f in pb.Counters.DESCRIPTOR.fields:
                    c[f.name] = getattr(r.counters, f.name)
                self.pub("counters", dumps(c))
            elif k == "rssi":
                x = r.rssi
                if len(x.addr) != 6:
                    self.bad_records += 1
                    continue
                devs.append([addr(x.addr), x.random, x.adv_type, mean1(x.rssi_sum_dbm, x.count),
                             x.rssi_max_dbm, x.count,
                             x.tx_1m_dbm if x.HasField("tx_1m_dbm") else None])
            elif k in ("advert", "scan_rsp"):
                x = getattr(r, k)
                if len(x.addr) != 6 or len(x.data) > 31:
                    self.bad_records += 1
                    continue
                a = {"id": addr(x.addr), "mast": MAST, "sector": self.pin, "chip": chip, "t": None,
                     "suspect": suspect, "kind": "adv" if k == "advert" else "scan_rsp",
                     "rssi": x.rssi_dbm, "random": x.random, "adv_type": x.adv_type,
                     "refresh": x.refresh, "age_ms": x.age_ticks * b.tick_ms, "data": x.data.hex()}
                a.update(ad_fields(x.data))
                self.pub(f"adv/{addr(x.addr, '')}", dumps(a))
            elif k == "tx_drops":
                t = r.tx_drops
                drops, omitted = [], t.omitted
                for x in t.drops:
                    if len(x.addr) != 6:
                        omitted += 1  # not published
                        continue
                    drops.append({"id": addr(x.addr), "random": x.random,
                                  "format": pb.TxFormat.Name(x.format)[len("TX_FORMAT_"):].lower(),
                                  "raw_dbm": x.raw_dbm, "tx_1m_dbm": x.tx_1m_dbm, "count": x.count})
                self.pub("debug/tx_1m", dumps({"t": None, "chip": chip, "seq": b.seq, "drops": drops,
                                               "omitted": omitted}))
        # Records this pb2 doesn't know: the generator appends them last, so they come last
        for num, payload in unknown_records:
            if num <= 63:
                self.pub(f"raw/{num}", payload.hex())
            else:
                self.bad_records += 1
        if devs or self.rssi_interval == 1:
            rs = {"t": None, "seq": b.seq, "t_ms": b.t_ms, "tick_ms": b.tick_ms, "chan": b.chan,
                  "load": b.load, "chip": chip, "suspect": suspect,
                  "devs": [Raw(dumps(d)) for d in devs]}
            self.pub("rssi", dumps(rs))


# ------------------------------------------------------------------ sample buckets

def key(num, wt):
    return ref_varint((num << 3) | wt)


def ref_varint(v):
    out = bytearray()
    while v >= 0x80:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.append(v)
    return bytes(out)


def ld(num, payload):
    return key(num, 2) + ref_varint(len(payload)) + payload


def status(**kw):
    s = pb.Status(version="0.4.0", listening=True, budget_pct=70, baud=115200,
                  intervals=pb.Intervals(rssi=1, payload=1, refresh=50, status=5, counters=50))
    for k, v in kw.items():
        setattr(s, k, v)
    return pb.Record(status=s)


def bucket_a():
    b = pb.Bucket(chip_id=CHIP, seq=100, t_ms=20000, tick_ms=200, chan=0, load=1)
    E = pb.Event
    b.records.add(event=E(category=E.SECURITY, severity=E.INFO, code=E.BOOT, value=1, value2=7,
                          text="power-on"))
    b.records.add(event=E(category=E.COMMAND, severity=E.INFO, code=E.CMD_OK, value=8, cmd_seq=5))
    b.records.add(event=E(category=E.LOAD, severity=E.WARN, code=E.LOAD_LEVEL, value=1, value2=1,
                          text="line"))
    b.records.append(status(active_scan=True, payloads=True, test_image=True, adverts=123,
                            devices=3, load_reasons=1, line_peak_pct=88))
    b.records.add(counters=pb.Counters(**{f.name: i + 1 for i, f in
                                          enumerate(pb.Counters.DESCRIPTOR.fields)}))
    R = pb.Rssi
    b.records.add(rssi=R(addr=bytes.fromhex("c0ffee000001"), random=True, adv_type=3,
                         rssi_sum_dbm=-201, count=3, rssi_max_dbm=-60, tx_1m_dbm=-59))
    b.records.add(rssi=R(addr=bytes.fromhex("112233445566"), adv_type=0, rssi_sum_dbm=-135,
                         count=2, rssi_max_dbm=-66))
    b.records.add(rssi=R(addr=bytes.fromhex("aabbccddeeff"), random=True, adv_type=2,
                         rssi_sum_dbm=-5, count=4, rssi_max_dbm=-1, tx_1m_dbm=4))
    adv = (bytes([2, 0x01, 0x06]) + bytes([7, 0x09]) + 'T"Ä"\x01'.encode() +
           bytes([7, 0xFF, 0x4C, 0x00, 0x02, 0x15, 0xAA, 0xBB]) +
           bytes([6, 0x16, 0x1A, 0x18, 1, 2, 3]) + bytes([2, 0x0A, 0xFC]))
    b.records.add(advert=pb.Payload(addr=bytes.fromhex("c0ffee000001"), random=True, adv_type=3,
                                    rssi_dbm=-61, data=adv))
    rsp = (bytes([17, 0x07]) + bytes(range(16)) + bytes([5, 0x08]) + b"Shrt" +
           bytes([5, 0x03, 0x0F, 0x18, 0xAA, 0xFE]))
    b.records.add(scan_rsp=pb.Payload(addr=bytes.fromhex("112233445566"), adv_type=4,
                                      rssi_dbm=-70, data=rsp, refresh=True, age_ticks=2))
    assert len(adv) <= 31 and len(rsp) <= 31
    # Unknown record kind (Record field 9) and unknown Bucket field 20, both to be skipped, and
    # the retired sector claim (Bucket field 2) a scanner before 0.5.0 still sends: ignored
    unknown = bytes([0x08, 0x2A])
    body = (b.SerializeToString() + ld(15, ld(9, unknown)) + key(20, 0) + ref_varint(1) +
            key(2, 0) + ref_varint(1))
    return b, body, [(9, unknown)]


def bucket_b():
    b = pb.Bucket(chip_id=CHIP, seq=103, t_ms=20600, tick_ms=200, chan=37, load=0)
    b.records.append(status())
    b.records.add(rssi=pb.Rssi(addr=bytes.fromhex("c0ffee000001"), random=True, adv_type=3,
                               rssi_sum_dbm=-70, count=1, rssi_max_dbm=-70))
    bad_ad = bytes([4, 0x09, ord("a"), 0xFF, ord("b"), 5, 0x16, 0x1A])  # bad UTF-8, truncated AD
    b.records.add(advert=pb.Payload(addr=bytes.fromhex("c0ffee000001"), random=True, adv_type=3,
                                    rssi_dbm=-70, data=bad_ad))
    return b, b.SerializeToString(), []


def bucket_d():
    b = pb.Bucket(chip_id=CHIP, seq=104, t_ms=20800, tick_ms=200, chan=0, load=0)
    b.records.append(status())
    # Debug summary (scanner 0.8.0+): the 3-byte address is left out and counted in omitted
    td = b.records.add().tx_drops
    td.drops.add(addr=bytes.fromhex("c0ffee000002"), random=True, format=pb.TX_FORMAT_IBEACON,
                 raw_dbm=127, tx_1m_dbm=127, count=3)
    td.drops.add(addr=bytes.fromhex("c0ffee000003"), format=pb.TX_FORMAT_EDDYSTONE_UID,
                 raw_dbm=-100, tx_1m_dbm=-141, count=1)
    td.drops.add(addr=bytes.fromhex("c0ffee"), format=pb.TX_FORMAT_EDDYSTONE_URL, raw_dbm=90,
                 tx_1m_dbm=49, count=2)
    td.omitted = 2
    return b, b.SerializeToString(), []


def bucket_e():
    """Malformed input the gateway must clean or drop, then a status showing bad_records"""
    b = pb.Bucket(chip_id=CHIP, seq=105, t_ms=21000, tick_ms=200, chan=0, load=0)
    bad_text = b"bad \xff\x1b[31m red"
    event = key(1, 0) + ref_varint(0) + key(2, 0) + ref_varint(1) + ld(7, bad_text)
    long_ad = bytes([39, 0xFF]) + bytes(38)
    st = status()
    st.status.version = "0.9\x1b[2J"
    wire = [
        (ld(5, event), ("event", 0, 1, 0, bad_text)),
        (pb.Record(rssi=pb.Rssi(addr=bytes(5), count=1)).SerializeToString(), ("bad",)),
        (pb.Record(advert=pb.Payload(addr=bytes(6), data=long_ad)).SerializeToString(), ("bad",)),
        (ld(100, bytes([0x08, 0x01])), ("bad",)),               # unknown kind past 63
        (key(2, 0) + ref_varint(5), ("bad",)),                  # known kind, not a sub-message
        (ld(10, bytes([0x08, 0x2A])), ("raw", 10, bytes([0x08, 0x2A]))),
        (st.SerializeToString(), st),
    ]
    body = b.SerializeToString() + b"".join(ld(15, w) for w, _ in wire)
    return b, body, [], [m for _, m in wire]


def bad_chip():
    """A bucket whose chip ID isn't 8 bytes: dropped whole, counted as a bad frame"""
    return ref.frame(pb.Bucket(chip_id=CHIP[:7], seq=106).SerializeToString())


def corrupt(body):
    raw = body + struct.pack("<H", ref.crc16_ccitt_false(body) ^ 0x0101)
    return ref.cobs_encode(raw) + b"\x00"


def c_str(s):
    """C string literal, every non-printable or non-ASCII byte as a 3-digit octal escape."""
    out = []
    for x in s.encode() if isinstance(s, str) else s:
        out.append(chr(x) if 0x20 <= x < 0x7F and chr(x) not in '"\\?' else f"\\{x:03o}")
    return '"' + "".join(out) + '"'


def main():
    dst = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        HERE, "..", "components", "sector_scanner", "selftest_data.h")

    for text, chip, hexstr in CMD_VECTORS:
        got = ref.build_cmd(text, bytes.fromhex(chip), 1).hex()
        assert got == hexstr, (text, chip, got, hexstr)

    sec = Sector(PIN)
    frames = []
    for make in (bucket_a, bucket_b, None, bucket_d, bad_chip, bucket_e):
        if make is bad_chip:
            frames.append(bad_chip())
            sec.bad_frame()
            continue
        if make is bucket_e:
            b, body, unknown, extra = make()
            frames.append(ref.frame(body))
            sec.bucket(b, unknown, extra)
            continue
        if make is None:
            frames.append(corrupt(bucket_d()[1]))
            try:
                ref.decode_frame(frames[-1][:-1])
                raise AssertionError("corrupt frame decoded")
            except ValueError:
                pass
            sec.bad_frame()
            continue
        b, body, unknown = make()
        frames.append(ref.frame(body))
        assert ref.decode_frame(frames[-1][:-1]).SerializeToString() is not None
        sec.bucket(b, unknown)

    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write("#pragma once\n// Generated by gateway/tools/make_selftest.py -- do not edit.\n\n")
        f.write("namespace esphome {\nnamespace sector_scanner {\nnamespace selftest {\n\n")
        f.write("struct CmdVector {\n  const char *text;\n  const char *chip;\n  const char *hex;\n};\n")
        f.write("static const CmdVector CMD_VECTORS[] = {\n")
        for text, chip, hexstr in CMD_VECTORS:
            f.write(f"    {{{c_str(text)}, {c_str(chip)}, {c_str(hexstr)}}},\n")
        f.write("};\n\n// Framed buckets (hex, each ending in 00); the third has a bad CRC, the fifth a 7-byte chip ID\n")
        f.write("static const char *const FRAMES[] = {\n")
        for fr in frames:
            f.write(f"    {c_str(fr.hex())},\n")
        f.write("};\n\n")
        f.write(f"static const char *const PREFIX = {c_str(PREFIX)};\n")
        f.write(f"static const char *const MAST = {c_str(MAST)};\n")
        f.write(f"static const unsigned PIN = {PIN};\n\n")
        f.write("struct Message {\n  const char *topic;\n  const char *payload;\n};\n")
        f.write("static const Message MESSAGES[] = {\n")
        for topic, payload in sec.out:
            f.write(f"    {{{c_str(topic)}, {c_str(payload)}}},\n")
        f.write("};\n\n}  // namespace selftest\n}  // namespace sector_scanner\n}  // namespace esphome\n")
    print(f"{len(CMD_VECTORS)} command vectors, {len(frames)} frames, {len(sec.out)} messages -> {dst}")
    for topic, payload in sec.out:
        print(f"  {topic}  {payload}")


if __name__ == "__main__":
    main()
