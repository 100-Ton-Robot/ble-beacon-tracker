# Scanner <-> gateway protocol (protocol 3)

Firmware 0.4.0 and later. The schema is [`proto/bletracker.proto`](proto/bletracker.proto);
this page covers framing, timing, the rules that keep old and new versions working together,
and what each record means. The scanner and the gateway must agree on it: change both, the
schema, this page and `tools/decode_frames.py` together.

Protocol 3 replaces frame/command v2 (fixed byte offsets, one frame per second) completely. A
v2 gateway can't read it.

## Wiring and framing

- `uart21`: **D6 = TX** to the gateway, **D7 = RX** from it, 115200 8N1, 3.3 V. Each scanner's
  D6 has its own gateway RX pin. One gateway TX drives every scanner's D7.
- Every message, in both directions: protobuf bytes, then a CRC-16/CCITT-FALSE of those bytes
  (poly 0x1021, init 0xFFFF, check "123456789" = 0x29B1, 2 bytes little-endian), COBS-encoded,
  then a 0x00 delimiter. Drop anything whose COBS, CRC or protobuf doesn't decode.
- Scanner -> gateway: one `Bucket` per tick. Gateway -> scanner: one `Command` per frame
  (at most 62 bytes before COBS).

## Compatibility rules

These are what make new fields and record kinds free to add without breaking older readers:

1. Never reuse or renumber a field number. Retire a field with `reserved`.
2. Never change a field's type or meaning. Add a new field instead.
3. Every field is optional. Readers must cope with any field being absent (proto3 reads absent
   numbers as 0 and absent bools as false, so give 0 a safe meaning).
4. New kinds of record are new members of `Record.kind`. Readers skip kinds they don't know
   (the gateway publishes them raw, see below).
5. Units are in the field name (`_dbm`, `_ms`, `_pct`, `_ticks`).

## Timing: ticks and service intervals

- A **tick** is 200 ms (`Bucket.tick_ms`). Every tick sends exactly one `Bucket`, even an empty
  one, so the gateway always sees the link alive. `seq` counts ticks since boot; a gap means
  buckets were lost (or skipped by the scanner, counted in `Counters.buckets_skipped`).
- `t_ms` is the scanner's uptime at the start of the tick. Scanners are not yet synchronised
  with each other: a gateway comparing sectors should line buckets up by arrival time for now.
- Each service has its own interval in ticks (`Status.intervals`; defaults below). A record
  covers the interval that ends with the tick it arrives in.

| service | default | what |
| --- | --- | --- |
| `rssi` | 1 tick (5 Hz) | RSSI per address heard in the interval. **Mast-wide**: a command may only change it when sent to all scanners, so sectors are always compared over the same window. |
| `payload` | 1 tick | Changed advert / scan response bytes (only while payload records are on). |
| `refresh` | 50 ticks (10 s) | Unchanged payloads are re-sent this often while the address is still heard. |
| `status` | 5 ticks (1 s) | `Status`. |
| `counters` | 50 ticks (10 s) | `Counters`. |
| events | next tick | `Event`s are queued and sent in the next bucket, never held back. |

Intervals, payload records on/off, active scanning and the budget are not saved (ignore rules
can be, see "Ignore list"): every boot
starts with the defaults (payloads off, passive), and the gateway sets what it wants again when
it sees a scanner (for example after a `BOOT` event).

## Records

A bucket's records come in this order: events, status, counters, RSSI (strongest mean first),
payloads (changed first, then refreshes).

- **`Rssi`**: one address over the RSSI interval. Mean = `rssi_sum_dbm / count`; `rssi_max_dbm`
  is the strongest advert. Scan responses are not counted, so RSSI means the same in passive
  and active mode. `tx_1m_dbm` is the advertised power at 1 m when the advert carries it
  (iBeacon, or Eddystone UID/URL minus 41 dB).
- **`Payload`** (`advert` or `scan_rsp`): the raw AD bytes as received (legacy PDUs, up to
  31 bytes), with the RSSI of the last advert that carried them. An address's advert and scan
  response are tracked separately. One goes out when its bytes change (at most once per payload
  interval: the last bytes heard in it) and every refresh interval while heard; `refresh` marks
  an unchanged re-send. `age_ticks` > 0 means it was held back by the budget. Payloads older
  than 5 s are dropped rather than sent late. Scan responses only exist with active scanning
  on (`active_scan`), which makes the scanner transmit a scan request to scannable
  advertisers. They often carry the device name.
- **`Status`**: firmware version, antenna, listening, active scanning, payloads on, flash mode,
  update client connected, test image, adverts / addresses / queue drops in the last second,
  the throttle reasons and peak use since the last status, budget, intervals and baud rate;
  since 0.6.0 the ignore list's size (and how many saved) and adverts ignored in the last second.
- **`Counters`**: totals since boot (buckets sent and skipped, commands ok / bad / for other
  scanners, D7 UART errors, payloads sent and held, RSSI records trimmed, payload table
  evictions, events lost, adverts ignored) plus `boots` and `flash_opens`, which are saved in
  flash.
- **`Event`**: `category` (GENERAL, SECURITY, LOAD, COMMAND), `severity` (INFO, WARN, ERROR),
  `code`, `value`/`value2` (meaning per code, below), `cmd_seq` for command acks, and a short
  `text`. The scanner prints each one on its USB console too (`[SECURITY WARN] ...`).

### Event codes

| code | category / severity | value, value2, text |
| --- | --- | --- |
| `BOOT` | SECURITY, INFO (WARN if the reset cause isn't power-on, software or debugger) | reset cause bits (Zephyr `hwinfo`), boot count |
| `VERSION_CHANGED` | SECURITY, WARN | text "old -> new" (also after an MCUboot revert) |
| `TEST_IMAGE` | SECURITY, WARN | running an unconfirmed image |
| `IMAGE_CONFIRMED` | SECURITY, INFO | test image confirmed itself |
| `FLASH_MODE_ON` | SECURITY, WARN | Source (0 console, 1 gateway, 2 test-image window), flash-mode open count |
| `FLASH_MODE_OFF` | SECURITY, INFO | 0 command, 1 timeout |
| `CLIENT_CONNECTED` / `CLIENT_DISCONNECTED` | SECURITY, WARN / INFO | –, HCI reason |
| `SETTING_CHANGED` | SECURITY, INFO | Setting (2 antenna, 3 ignore list), new value (ignore list: rules listed), text = what changed and source |
| `BAD_COMMANDS` | SECURITY, WARN | 3 or more bad command frames on D7 within 10 s: count |
| `CMD_OK` / `CMD_REJECTED` | COMMAND, INFO / WARN | Command action field number, `cmd_seq` = the command's `seq` |
| `LOAD_LEVEL` | LOAD, INFO (back to 0), WARN (1-3), ERROR (4) | new level, reasons |
| `EVENTS_LOST` | GENERAL, WARN | events dropped because the queue was full |

## Sector

The scanner doesn't know its sector. Each scanner's D6 is wired to its own gateway RX pin,
and the gateway assigns the sector to that pin; wiring is the only source of truth. 0.4.x
scanners sent a saved sector claim (`Bucket.sector`, field 2), had a `sector` command
(field 6), a `SECTOR_NOT_SET` event (14) and a `SECTOR` setting (1); all are retired in 0.5.0
(`reserved` in the schema, never reuse the numbers). A 0.5.0 scanner deletes the old saved
value at boot. The chip ID in every bucket still lets the gateway notice a board swap.

## Budget and throttle

- The **budget** is `budget_pct` (default 70 %) of what the line carries in one tick: at
  115200 baud, 1612 bytes. Events, status and counters always go out; RSSI and payloads must fit.
- **Load levels** (`Bucket.load`, `LoadLevel`), RSSI kept to the last:

| level | meaning |
| --- | --- |
| 0 `NORMAL` | everything sent |
| 1 `REFRESH_SLOWED` | payload refreshes at 3x their interval |
| 2 `REFRESH_OFF` | changed payloads only |
| 3 `PAYLOADS_OFF` | RSSI, status and events only |
| 4 `RSSI_TRIMMED` | RSSI records left out, weakest first |

- **Up**: one level each time payloads are held back by the budget (up to 3), or each second
  with adverts dropped from the scanner's queue while payloads are on. Straight to 4 when RSSI
  doesn't fit.
- **Down**: one level after 50 ticks (10 s) under half the budget with nothing held back
  (from 4: after 50 ticks without trimming).
- `Status.load_reasons` (`LoadReason` bits): 1 line (didn't fit), 2 queue (adverts dropped),
  4 table (more than 96 addresses in one RSSI interval), 8 payload table evicting addresses.

## Commands

`Command`: `target` = chip ID from a bucket (8 bytes; empty or all zeros = every scanner), `seq`
(echoed in the ack), and one action:

| action | argument | notes |
| --- | --- | --- |
| `listen` | bool | start/stop scanning |
| `flash` | bool | open flash mode for 10 min (each open extends) / close it |
| `ext_antenna` | bool | saved |
| `reboot` | 0xA5 | anything else is rejected |
| `payloads` | bool | payload records on/off |
| `active_scan` | bool | active scanning on/off |
| `intervals` | `Intervals` | fields left at 0 are unchanged; `rssi` only to all scanners; limits: rssi/payload/status 1-50, refresh/counters 1-3000 |
| `budget_pct` | 10-90 | |
| `ignore` | `IgnoreRule` | add a rule, or change whether it is saved (0.6.0+, below) |
| `unignore` | `IgnoreRule` | remove the rule with exactly this `addr` and `mask`; rejected if there is none |
| `ignore_clear` | `IgnoreClear` 1-3 | remove the rules kept until reboot (1), the saved ones (2) or all (3) |

### Ignore list (0.6.0+)

Adverts from ignored addresses are dropped as the scanner hears them: no RSSI or payload records,
no console lines, and they don't count in `adverts`, `devices` or the load. An `IgnoreRule` is
`addr` (6 bytes, most significant first, as in `Rssi.addr`) and `mask` (6 bytes, same order;
left out = all ones, this address only). An address matches when `(address & mask) == (addr &
mask)`; public/random isn't compared. A mask of all zeros is rejected (that's `listen off`).

- `save` true: kept in flash across reboots. False: kept until the next reboot. Sending a
  saved rule again with `save` false removes it from flash but keeps it until reboot.
- Up to 32 rules per scanner, saved and unsaved together; a 33rd is rejected.
- Rules are per scanner: send to all (empty target) to apply them mast-wide.
- Every change is a `SETTING_CHANGED` security event (`value` 3 = `IGNORE_LIST`, `value2` = rules
  now listed, text = the rule and `saved`/`boot`, then `gw` or `usb`): a rule can hide a device.
  Acks: `ignore added` / `changed` / `unchanged`, `unignored`, `ignore cleared`; `... NOT SAVED`
  when the flash write failed (the change still holds until reboot).
- `Status.ignore_rules`, `ignore_saved` and `ignored` (adverts dropped in the last second) and
  `Counters.ignored` (since boot) show it working. The rules themselves are only listed on the
  console (`ignore`).

Text forms (console, `decode_frames.py --cmd`, gateway MQTT): `ignore <addr>[/<bits>|/<mask>]
[save]`, `unignore <addr>[/<bits>|/<mask>]`, `ignore clear boot|saved|all`. Any address byte
may be `*`: `C1:7D:2B:*:*:*` = `C1:7D:2B:00:00:00/24`.

Every accepted command is answered with a `CMD_OK` event in the scanner's next bucket, every
rejected one (bad argument, rssi interval to one scanner) with `CMD_REJECTED`.
Frames that don't decode are only counted (`Counters.cmds_bad`, the scanner's `cmdlog`) and
raise a `BAD_COMMANDS` security event when three or more arrive within 10 s. Valid commands for
another chip ID are counted in `cmds_other`.

`python tools/decode_frames.py --cmd "payloads on" --id <chip ID>` prints a command's bytes for
the console's `inject`, or sends them with `--port`.

## Sizes

At 115200 baud a tick carries 2304 bytes. An RSSI record is about 18-22 bytes, a payload record
up to about 50, a status about 70. 64 addresses heard in a tick is about 1.4 KB of RSSI, within
the 1612-byte budget; payloads then wait or are shed by the throttle.
