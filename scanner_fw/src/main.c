/*
 * BLE scanner, one per sector. It doesn't know its sector: that is the gateway RX pin
 * its D6 is wired to.
 *   1. boots, prints a banner, blinks the LED once a second
 *   2. passive scan at 100% duty, duplicates kept (active scanning on command)
 *   3. RF switch control so onboard vs external antenna can be compared
 *   4. 1 s aggregation per address for the console: median/max RSSI, count, 1 m power
 *   5. bucket stream to the gateway (D6 TX, D7 RX): one protobuf Bucket per 200 ms tick,
 *      typed records (RSSI, advert and scan response bytes, status, events, counters),
 *      each service on its own interval, a byte budget per tick and a throttle that
 *      sheds payloads before RSSI. Schema: proto/bletracker.proto, rules: PROTOCOL.md.
 *      Each scanner's D6 has its own gateway RX pin; D7 is shared by all three
 *   6. commands from the gateway on D7 (protobuf Command), addressed by chip ID since
 *      every scanner hears them, acknowledged with an event
 *   7. flash mode: connectable BLE with MCUmgr SMP so MCUboot images can be
 *      uploaded with the box sealed; only on a serial command (and for 2 min
 *      after an update, while the new image is on trial)
 *   8. antenna choice kept in flash
 *   9. security events (flash mode, updates, resets, settings, bad commands) with
 *      boot and flash-mode counts kept in flash
 *  10. ignore list: address/mask rules whose adverts are dropped as they are heard,
 *      each saved in flash or kept until reboot (console or gateway command), sent to
 *      the gateway whole at boot, after each change and on request
 *
 * Shell commands:
 *   status                 version, chip ID, antenna, listening, flash mode, stream
 *   ant [int|ext]          show or switch antenna (saved in flash)
 *   scan [on|off]          show or start/stop listening (always on after boot)
 *   active [on|off]        show or switch active scanning (passive after boot)
 *   data [on|off]          show or switch payload records (off after boot)
 *   budget [10-90]         show or set the stream budget, % of the line per tick
 *   flash [on|off]         show or enter/leave flash mode (on = 10 min)
 *   reboot                 restart
 *   inject <hex>           feed bytes to the D7 command decoder (bench test)
 *   cmdlog                 last rejected D7 command frames
 *   filter <addr>|off      only track one address, print a 1 s summary for it
 *   print on|off           raw line per advert with its bytes (off by default: floods)
 *   list on|csv|off        per-device table each second
 *   minrssi <dBm>          hide devices whose median is below this in the list
 *   stream [dump]          bucket stats; dump = hex of the next bucket frame
 *   chan [auto|37|38|39|rot [s]]  primary channels scanned (bench test, not saved)
 *   ignore [list]          ignore rules and their hits
 *   ignore <addr>[/bits|/mask] [save]  ignore until reboot, or saved ("*" = any byte)
 *   ignore clear boot|saved|all, ignore off|on (pause, until reboot)
 *   unignore <addr>[/bits|/mask]|all   remove a rule
 */

#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/hwinfo.h>
#include <zephyr/drivers/regulator.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/crc.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/addr.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/mgmt/mcumgr/transport/smp_bt.h>
#include <zephyr/dfu/mcuboot.h>
#include <zephyr/settings/settings.h>
#include <zephyr/shell/shell.h>
#include <app_version.h>
#include <bluetooth/hci_vs_sdc.h>
#include <pb_encode.h>
#include <pb_decode.h>
#include <proto/bletracker.pb.h>

/*
 * The board devicetree models the RF switch as two fixed regulators, both
 * regulator-boot-on (so refcount 1 after init):
 *   rfsw-pwr: P2.03, active high, switch power
 *   rfsw-ctl: P2.05, active low; enabled = P2.05 low = onboard ceramic,
 *             disabled = P2.05 high = external IPEX
 * Polarity measured 2026-10-29 with nothing on the IPEX connector: P2.05 low
 * heard ~48 adverts/s, high ~18/s.
 */
static const struct device *const rfsw_pwr = DEVICE_DT_GET(DT_NODELABEL(rfsw_pwr));
static const struct device *const rfsw_ctl = DEVICE_DT_GET(DT_NODELABEL(rfsw_ctl));
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET_OR(DT_ALIAS(led0), gpios, {0});

/* Advertised power at 1 m not present in the advert */
#define TX_UNKNOWN INT8_MAX
/* Legacy advert or scan response payload (extended adverts aren't scanned) */
#define AD_MAX 31

struct adv_evt {
	bt_addr_le_t addr;
	int8_t rssi;
	uint8_t type;
	int8_t tx_1m;
	uint8_t len;
	uint8_t data[AD_MAX];
};

/* One second of adverts from one address for the console, main thread only */
#define MAX_DEVS 64
#define MAX_SAMPLES 32

struct dev_agg {
	bt_addr_le_t addr;
	uint8_t adv_type;
	int8_t tx_1m;
	int8_t rssi_max;
	int8_t rssi_med;
	uint16_t count;
	int8_t samples[MAX_SAMPLES];
};

static struct dev_agg devs[MAX_DEVS];
static uint8_t n_devs;
static uint32_t devs_full;
static uint8_t order[MAX_DEVS]; /* devs[] indices, strongest median first */

/*
 * Bucket stream on uart21 (D6 TX, D7 RX), 115200 8N1. Each tick (TICK_MS) one frame:
 * protobuf Bucket (header fields, then Record submessages encoded one at a time), then
 * CRC-16/CCITT-FALSE (poly 0x1021, init 0xffff, LE) of the protobuf bytes, COBS-encoded,
 * followed by a 0x00 delimiter. Records per tick, in this order:
 *   events     all queued, never held back
 *   status     every intervals.status ticks
 *   counters   every intervals.counters ticks
 *   rssi       every intervals.rssi ticks, per address heard in that interval, strongest
 *              mean first; the budget can trim the weakest (load level 4)
 *   payloads   every intervals.payload ticks while payload records are on: changed
 *              advert/scan response bytes first, then refreshes, until the budget is used;
 *              the rest wait (load levels 1-3 slow, then stop them)
 *   ignore     the whole ignore list, after boot, a change or a request; outside the
 *              budget but within 90% of the line, else the next tick
 * The budget is budget_pct of the bytes the line carries in one tick; events, status and
 * the ignore list may go over it.
 */
#define TICK_MS 200
#define TICKS_PER_S (1000 / TICK_MS)
#define FRAME_RAW_MAX 4096
/* COBS adds one byte per 254, plus the delimiter */
#define FRAME_TX_MAX (FRAME_RAW_MAX + FRAME_RAW_MAX / 254 + 2)
#define BUCKET_RECORDS_TAG 15	/* Bucket.records (FT_IGNORE in the options: encoded here) */
#define BUDGET_PCT_DEFAULT 70

static const struct device *const gw_uart = DEVICE_DT_GET(DT_NODELABEL(uart21));
static uint8_t frame_raw[FRAME_RAW_MAX];
static uint8_t frame_tx[FRAME_TX_MAX];
static volatile size_t frame_tx_len;
static volatile size_t frame_tx_pos;
static uint32_t tick_seq;
static uint32_t buckets_sent;
static uint32_t buckets_skipped; /* previous bucket still going out */
static uint32_t uart_baud = 115200;
static uint8_t budget_pct = BUDGET_PCT_DEFAULT;
static bool frame_dump;

static bletracker_Intervals intervals = {
	.rssi = 1, .payload = 1, .refresh = 50, .status = TICKS_PER_S, .counters = 50,
};

/* RSSI of each address over the current RSSI interval, main thread only */
#define MAX_TICK_DEVS 96

struct tick_dev {
	bt_addr_le_t addr;
	uint8_t adv_type;
	int8_t tx_1m;
	int8_t rssi_max;
	uint16_t count;
	int32_t sum;
};

static struct tick_dev tdevs[MAX_TICK_DEVS];
static uint8_t n_tdevs;
static bool tdevs_full;
static uint8_t torder[MAX_TICK_DEVS];

/*
 * Payloads per address across ticks, main thread only: [0] advert, [1] scan response.
 * A payload is due when heard since it was last sent and either its bytes changed
 * (or were never sent) or the refresh interval has passed; not once it's AD_STALE_MS
 * old. Changed ones first, then the ones sent longest ago.
 */
#define MAX_SEEN 128
#define AD_STALE_MS 5000

struct seen_part {
	int64_t heard_at;	/* 0 = never */
	int64_t sent_at;	/* 0 = never */
	uint32_t hash;
	uint32_t sent_hash;
	int8_t rssi;
	uint8_t type;
	uint8_t len;
	uint8_t data[AD_MAX];
};

struct seen_dev {
	bt_addr_le_t addr;
	int64_t heard_at;
	struct seen_part p[2];
};

static struct seen_dev seen[MAX_SEEN];
static uint8_t n_seen;
static bool payloads_on;
static bool scan_active;

/* Throttle: level and the reasons seen since the last status record */
#define CALM_TICKS 50		/* ticks under half the budget before going down a level */

static uint8_t load_level;
static uint32_t load_reasons;
static uint32_t calm_ticks;
static uint32_t line_peak_pct;
static uint32_t payloads_sent;
static uint32_t payloads_held;
static uint32_t rssi_trimmed;
static uint32_t seen_evicted;

/*
 * Events: queued from any thread, sent first in the next bucket. Each is also printed
 * on the console, security ones tagged SECURITY.
 */
#define EVENT_Q_LEN 16
static char __aligned(4) event_q_buf[EVENT_Q_LEN * sizeof(bletracker_Event)];
static struct k_msgq event_q;
static atomic_t events_lost;
static atomic_t events_lost_reported;

/* Saved in flash: boot and flash-mode counts, last version booted */
static uint32_t boot_count;
static uint32_t flash_opens;
static char last_version[24];

/*
 * Gateway command, on uart21 RX (D7), same framing as buckets (COBS + 0x00, CRC-16 LE
 * after the protobuf bytes). A protobuf Command: target chip ID (empty or zeros = every
 * scanner), seq, one action. Each is answered with a CMD_OK or CMD_REJECTED event.
 */
#define CMD_ENC_MAX 72
#define CMD_RAW_MAX 64
#define CMD_REBOOT_MAGIC 0xa5

struct cmd_msg {
	uint8_t len;
	uint8_t enc[CMD_ENC_MAX];
};

/* Receive state, uart ISR only (or inject from the shell on the bench) */
static uint8_t cmd_enc[CMD_ENC_MAX];
static uint8_t cmd_enc_len;
static bool cmd_overflow;

static char __aligned(4) cmd_q_buf[4 * sizeof(struct cmd_msg)];
static struct k_msgq cmd_q;
static struct k_work cmd_work;
static atomic_t cmds_ok;
static atomic_t cmds_bad;
static atomic_t cmds_other;	/* valid, for another scanner */
static atomic_t cmd_rx_bytes;
static atomic_t cmd_rx_errors;	/* UART framing/parity/overrun/break on D7 */

/* Last few rejected frames, for `cmdlog` (written from the ISR too) */
enum cmd_bad_reason {
	BAD_LONG,	/* no 0x00 within CMD_ENC_MAX bytes */
	BAD_QUEUE,	/* queue full */
	BAD_FRAME,	/* COBS or length wrong */
	BAD_CRC,
	BAD_DECODE,	/* not a valid Command */
	BAD_ARG,	/* no action, unknown action or argument out of range */
};
static const char *const cmd_bad_names[] = {
	"too long", "queue full", "bad COBS/length", "bad CRC", "bad protobuf", "bad action/arg",
};

#define CMD_BAD_SHOW 16

struct cmd_bad {
	int64_t t;
	uint8_t reason;
	uint8_t len;
	uint8_t b[CMD_BAD_SHOW];
};

#define CMD_BAD_LOG 8
static struct cmd_bad cmd_bad_log[CMD_BAD_LOG];
static unsigned int cmd_bad_next;

static void cmd_bad_note(enum cmd_bad_reason reason, const uint8_t *b, uint8_t len)
{
	unsigned int key = irq_lock();
	struct cmd_bad *e = &cmd_bad_log[cmd_bad_next++ % CMD_BAD_LOG];

	e->t = k_uptime_get();
	e->reason = reason;
	e->len = MIN(len, CMD_BAD_SHOW);
	memcpy(e->b, b, e->len);
	irq_unlock(key);
	atomic_inc(&cmds_bad);
}

/*
 * Flash mode: connectable advertising as "bletracker-<last 6 hex digits of
 * the chip ID>" with the SMP
 * service, so nRF Connect Device Manager or smpmgr can upload a signed image.
 * Opened only by a serial command (gateway D7 or console), never at a normal
 * boot. Ends after FLASH_MODE_S without a connected client, or on command.
 * A test image is the exception: it opens flash mode for FLASH_TEST_WINDOW_S
 * so the self-check below can see advertising work and the uploader can
 * reconnect.
 */
#define FLASH_MODE_S 600
#define FLASH_TEST_WINDOW_S 120
/* A test image confirms itself after this long if BLE, scanning and flash mode work */
#define CONFIRM_AFTER_MS 60000

static bool flash_mode;
static int64_t flash_until;
static struct bt_conn *smp_conn;
static struct k_work adv_work;
static char flash_name[20];
static bool flash_adv_ok;  /* flash mode advertising has started at least once */
static bool img_confirmed;

static const struct bt_data flash_ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, SMP_BT_SVC_UUID_VAL),
};

/*
 * Scan callback runs in the BT RX thread: queue and get out, handle in main.
 * Not K_MSGQ_DEFINE: its __noinit buffer gets a section name built from the
 * file path, which breaks the assembler when the path contains spaces.
 */
#define ADV_Q_LEN 256
static char __aligned(4) adv_q_buf[ADV_Q_LEN * sizeof(struct adv_evt)];
static struct k_msgq adv_q;
static atomic_t dropped;

enum list_mode { LIST_OFF, LIST_TABLE, LIST_CSV };

static bool ant_external;
static bool ant_saved_external; /* from flash, applied at boot */
static bool scanning;
static bool print_raw;
static enum list_mode list_mode;
static int8_t list_min_rssi = -127;
static uint8_t chip_id[8];
static char chip_id_str[17];
static bool filter_on;
static bt_addr_t filter_addr;

/* Per-second counters, main thread only; last_* = the last whole second */
static uint32_t sec_total;
static uint32_t sec_n;
static int32_t sec_sum;
static int8_t sec_min;
static int8_t sec_max;
static uint32_t last_adverts;
static uint32_t last_dropped;
static uint32_t last_devices;

static const char *const sev_names[] = { "INFO", "WARN", "ERROR" };

static void event_post(bletracker_Event_Category cat, bletracker_Event_Severity sev,
		       bletracker_Event_Code code, int32_t value, int32_t value2, uint32_t cmd_seq,
		       const char *fmt, ...)
{
	bletracker_Event ev = bletracker_Event_init_zero;
	va_list ap;

	ev.category = cat;
	ev.severity = sev;
	ev.code = code;
	ev.value = value;
	ev.value2 = value2;
	ev.cmd_seq = cmd_seq;
	va_start(ap, fmt);
	vsnprintk(ev.text, sizeof(ev.text), fmt, ap);
	va_end(ap);

	printk("[%s%s] %s\n", cat == bletracker_Event_Category_SECURITY ? "SECURITY " : "",
	       sev_names[MIN(sev, 2)], ev.text);
	if (k_msgq_put(&event_q, &ev, K_NO_WAIT) != 0) {
		atomic_inc(&events_lost);
	}
}

#define SECURITY_EVENT(sev, code, v, v2, ...) \
	event_post(bletracker_Event_Category_SECURITY, bletracker_Event_Severity_##sev, \
		   bletracker_Event_Code_##code, v, v2, 0, __VA_ARGS__)

/*
 * Ignore list: adverts from matching addresses are dropped in the scan callback, before
 * they take queue space or main-thread time (no RSSI, payloads or console lines). A rule
 * is an address and a mask, bytes in printed order (most significant first); it matches
 * when (address & mask) == addr, addr being stored already masked. Address type isn't
 * compared. Saved rules are kept in flash ("scanner/ign"), the others until reboot.
 * Every change is a security event: a rule can hide a device from the tracker. Gateway
 * commands must go to all scanners (the list is mast-wide); the console is for the bench.
 * ign[] is read in the BT RX thread under ign_lock; changes (shell thread, system
 * workqueue) also hold ign_mutex so flash writes go out in order.
 */
#define IGNORE_MAX 32
#define ADDR_LEN 6

struct ignore_rule {
	uint8_t addr[ADDR_LEN];
	uint8_t mask[ADDR_LEN];
	bool saved;
	uint32_t hits;
};

/* What "scanner/ign" holds: the saved rules, one after another */
struct ignore_flash {
	uint8_t addr[ADDR_LEN];
	uint8_t mask[ADDR_LEN];
};

static struct ignore_rule ign[IGNORE_MAX];
static uint8_t n_ign;
static bool ign_paused;		/* console `ignore off`: rules kept, not applied */
static struct k_spinlock ign_lock;
K_MUTEX_DEFINE(ign_mutex);
static atomic_t ign_total;	/* adverts ignored since boot */
static atomic_t ign_sec;	/* this second */
static uint32_t last_ignored;	/* last whole second */
/* IgnoreList record due in the next bucket: at boot, after a change, on request */
static atomic_t ign_report = ATOMIC_INIT(1);

/* Settings under "scanner/": ant (1 byte), boots, fopens (u32), ver (string), ign (saved
 * ignore rules). A "sector" key left by 0.4.x is ignored and deleted at boot. */
static int settings_set_cb(const char *key, size_t len, settings_read_cb read_cb, void *cb_arg)
{
	uint8_t v;

	if (strcmp(key, "ign") == 0) {
		struct ignore_flash f[IGNORE_MAX];
		size_t n = len / sizeof(f[0]);

		if (len % sizeof(f[0]) != 0 || n > IGNORE_MAX || read_cb(cb_arg, f, len) != len) {
			return -EINVAL;
		}
		/* Loaded once at boot, before scanning starts */
		n_ign = 0;
		for (size_t i = 0; i < n; i++) {
			struct ignore_rule *r = &ign[n_ign++];

			memset(r, 0, sizeof(*r));
			memcpy(r->mask, f[i].mask, ADDR_LEN);
			for (int b = 0; b < ADDR_LEN; b++) {
				r->addr[b] = f[i].addr[b] & f[i].mask[b];
			}
			r->saved = true;
		}
		return 0;
	}
	if (strcmp(key, "boots") == 0 || strcmp(key, "fopens") == 0) {
		uint32_t n;

		if (len != sizeof(n) || read_cb(cb_arg, &n, sizeof(n)) != sizeof(n)) {
			return -EINVAL;
		}
		*(key[0] == 'b' ? &boot_count : &flash_opens) = n;
		return 0;
	}
	if (strcmp(key, "ver") == 0) {
		if (len >= sizeof(last_version) || read_cb(cb_arg, last_version, len) != len) {
			return -EINVAL;
		}
		last_version[len] = '\0';
		return 0;
	}
	if (len != 1 || read_cb(cb_arg, &v, 1) != 1) {
		return -EINVAL;
	}
	if (strcmp(key, "ant") == 0) {
		ant_saved_external = v != 0;
	}
	return 0;
}

SETTINGS_STATIC_HANDLER_DEFINE(scanner, "scanner", NULL, settings_set_cb, NULL, NULL);

/* Scan callback (BT RX thread): true = drop this advert */
static bool ignore_match(const bt_addr_t *a)
{
	k_spinlock_key_t key;
	bool hit = false;

	if (n_ign == 0 || ign_paused) {
		return false;
	}
	key = k_spin_lock(&ign_lock);
	for (uint8_t i = 0; i < n_ign && !hit; i++) {
		struct ignore_rule *r = &ign[i];

		hit = true;
		for (int b = 0; b < ADDR_LEN; b++) {
			if ((a->val[ADDR_LEN - 1 - b] & r->mask[b]) != r->addr[b]) {
				hit = false;
				break;
			}
		}
		if (hit) {
			r->hits++;
		}
	}
	k_spin_unlock(&ign_lock, key);
	if (hit) {
		atomic_inc(&ign_total);
		atomic_inc(&ign_sec);
	}
	return hit;
}

/* Prefix length if the mask is one (ones then zeros), else -1 */
static int mask_prefix(const uint8_t mask[ADDR_LEN])
{
	int bits = 0;

	for (int b = 0; b < ADDR_LEN; b++) {
		for (int k = 7; k >= 0; k--) {
			if (!(mask[b] & BIT(k))) {
				goto zeros;
			}
			bits++;
		}
	}
	return bits;
zeros:
	for (int i = bits; i < 8 * ADDR_LEN; i++) {
		if (mask[i / 8] & BIT(7 - i % 8)) {
			return -1;
		}
	}
	return bits;
}

/* "C1:7D:2B:AC:03:BC", "C1:7D:2B:00:00:00/24" or "C1:7D:00:AC:00:00/FF:FF:00:FF:00:00" */
static void ignore_fmt(char *buf, size_t size, const uint8_t addr[ADDR_LEN],
		       const uint8_t mask[ADDR_LEN])
{
	int bits = mask_prefix(mask);
	int n = snprintk(buf, size, "%02X:%02X:%02X:%02X:%02X:%02X", addr[0], addr[1], addr[2],
			 addr[3], addr[4], addr[5]);

	if (bits == 8 * ADDR_LEN) {
		return;
	}
	if (bits >= 0) {
		snprintk(buf + n, size - n, "/%d", bits);
	} else {
		snprintk(buf + n, size - n, "/%02X:%02X:%02X:%02X:%02X:%02X", mask[0], mask[1],
			 mask[2], mask[3], mask[4], mask[5]);
	}
}

/* 6 bytes "AA:BB:...", any byte may be "*" (mask byte 0); end of the parsed text or NULL */
static const char *addr6_parse(const char *s, uint8_t v[ADDR_LEN], uint8_t m[ADDR_LEN])
{
	for (int b = 0; b < ADDR_LEN; b++) {
		if (*s == '*') {
			v[b] = 0;
			m[b] = 0;
			s++;
		} else if (hex2bin(s, 2, &v[b], 1) == 1) {
			m[b] = 0xff;
			s += 2;
		} else {
			return NULL;
		}
		if (b < ADDR_LEN - 1 && *s++ != ':') {
			return NULL;
		}
	}
	return s;
}

/* Console rule: <addr>[/<bits 1-48>|/<mask>], "*" bytes allowed; false if malformed or the
 * mask is all zeros (that would ignore everything: use `scan off`) */
static bool ignore_parse(const char *s, uint8_t addr[ADDR_LEN], uint8_t mask[ADDR_LEN])
{
	const char *end = addr6_parse(s, addr, mask);
	bool any = false;

	if (end == NULL || (*end != '\0' && *end != '/')) {
		return false;
	}
	if (*end == '/') {
		const char *m = end + 1;
		uint8_t m2[ADDR_LEN];
		uint8_t wild[ADDR_LEN];

		if (strchr(m, ':') != NULL) {
			end = addr6_parse(m, m2, wild);
			if (end == NULL || *end != '\0' || memchr(wild, 0, ADDR_LEN) != NULL) {
				return false;
			}
		} else {
			char *e;
			long bits = strtol(m, &e, 10);

			if (e == m || *e != '\0' || bits < 1 || bits > 8 * ADDR_LEN) {
				return false;
			}
			for (int b = 0; b < ADDR_LEN; b++) {
				long n = CLAMP(bits - 8 * b, 0, 8);

				m2[b] = (uint8_t)(0xff00 >> n);
			}
		}
		for (int b = 0; b < ADDR_LEN; b++) {
			mask[b] &= m2[b];
		}
	}
	for (int b = 0; b < ADDR_LEN; b++) {
		addr[b] &= mask[b];
		any |= mask[b] != 0;
	}
	return any;
}

static int ignore_find(const uint8_t addr[ADDR_LEN], const uint8_t mask[ADDR_LEN])
{
	for (uint8_t i = 0; i < n_ign; i++) {
		if (memcmp(ign[i].addr, addr, ADDR_LEN) == 0 &&
		    memcmp(ign[i].mask, mask, ADDR_LEN) == 0) {
			return i;
		}
	}
	return -1;
}

/* Saved rules to flash; call with ign_mutex held (it guards f, kept off the work queue's
 * stack) */
static int ignore_store(void)
{
	static struct ignore_flash f[IGNORE_MAX];
	size_t n = 0;
	k_spinlock_key_t key = k_spin_lock(&ign_lock);

	for (uint8_t i = 0; i < n_ign; i++) {
		if (ign[i].saved) {
			memcpy(f[n].addr, ign[i].addr, ADDR_LEN);
			memcpy(f[n].mask, ign[i].mask, ADDR_LEN);
			n++;
		}
	}
	k_spin_unlock(&ign_lock, key);
	return n ? settings_save_one("scanner/ign", f, n * sizeof(f[0])) :
		   settings_delete("scanner/ign");
}

static const char *src_short(bletracker_Event_Source src)
{
	/* Event text is 63 characters at most: keep it short */
	return src == bletracker_Event_Source_GATEWAY ? "gw" : "usb";
}

enum ignore_result {
	IGN_ADDED,	/* new rule */
	IGN_CHANGED,	/* existing rule, now saved / no longer saved */
	IGN_SAME,	/* already there as asked */
	IGN_FULL,
	IGN_FLASH_ERR,	/* in the list, but saving to flash failed (kept until reboot) */
};

/* Add a rule, or change whether an existing one is saved (save false: until reboot) */
static enum ignore_result ignore_add(const uint8_t addr[ADDR_LEN], const uint8_t mask[ADDR_LEN],
				     bool save, bletracker_Event_Source src)
{
	enum ignore_result res;
	char str[48];
	k_spinlock_key_t key;
	int i;

	k_mutex_lock(&ign_mutex, K_FOREVER);
	key = k_spin_lock(&ign_lock);
	i = ignore_find(addr, mask);
	if (i < 0 && n_ign == IGNORE_MAX) {
		k_spin_unlock(&ign_lock, key);
		k_mutex_unlock(&ign_mutex);
		return IGN_FULL;
	}
	if (i < 0) {
		i = n_ign;
		memset(&ign[i], 0, sizeof(ign[i]));
		memcpy(ign[i].addr, addr, ADDR_LEN);
		memcpy(ign[i].mask, mask, ADDR_LEN);
		ign[i].saved = save;
		n_ign++;
		res = IGN_ADDED;
	} else {
		res = ign[i].saved == save ? IGN_SAME : IGN_CHANGED;
		ign[i].saved = save;
	}
	k_spin_unlock(&ign_lock, key);

	if ((res == IGN_ADDED && save) || res == IGN_CHANGED) {
		if (ignore_store() != 0) {
			ign[i].saved = false;
			res = IGN_FLASH_ERR;
		}
	}
	if (res != IGN_SAME) {
		atomic_set(&ign_report, 1);
		ignore_fmt(str, sizeof(str), addr, mask);
		SECURITY_EVENT(INFO, SETTING_CHANGED, bletracker_Event_Setting_IGNORE_LIST, n_ign,
			       "ignore %s %s %s", str, ign[i].saved ? "saved" : "boot", src_short(src));
	}
	k_mutex_unlock(&ign_mutex);
	return res;
}

/* Remove one rule (exact addr and mask); -ENOENT if not listed, -EIO if flash failed */
static int ignore_del(const uint8_t addr[ADDR_LEN], const uint8_t mask[ADDR_LEN],
		      bletracker_Event_Source src)
{
	char str[48];
	k_spinlock_key_t key;
	bool was_saved;
	int err = 0;
	int i;

	k_mutex_lock(&ign_mutex, K_FOREVER);
	key = k_spin_lock(&ign_lock);
	i = ignore_find(addr, mask);
	if (i < 0) {
		k_spin_unlock(&ign_lock, key);
		k_mutex_unlock(&ign_mutex);
		return -ENOENT;
	}
	was_saved = ign[i].saved;
	ign[i] = ign[--n_ign];
	k_spin_unlock(&ign_lock, key);

	if (was_saved) {
		err = ignore_store() ? -EIO : 0;
	}
	atomic_set(&ign_report, 1);
	ignore_fmt(str, sizeof(str), addr, mask);
	SECURITY_EVENT(INFO, SETTING_CHANGED, bletracker_Event_Setting_IGNORE_LIST, n_ign,
		       "unignore %s %s", str, src_short(src));
	k_mutex_unlock(&ign_mutex);
	return err;
}

/* Remove the rules kept until reboot, the saved ones, or all; how many went (-EIO: flash) */
static int ignore_clear(bletracker_IgnoreClear which, bletracker_Event_Source src)
{
	static const char *const names[] = { "", "boot", "saved", "all" };
	bool drop_temp = which == bletracker_IgnoreClear_IGNORE_CLEAR_TEMP ||
			 which == bletracker_IgnoreClear_IGNORE_CLEAR_ALL;
	bool drop_saved = which == bletracker_IgnoreClear_IGNORE_CLEAR_SAVED ||
			  which == bletracker_IgnoreClear_IGNORE_CLEAR_ALL;
	k_spinlock_key_t key;
	uint8_t kept = 0;
	int removed;
	bool saved_gone = false;

	k_mutex_lock(&ign_mutex, K_FOREVER);
	key = k_spin_lock(&ign_lock);
	for (uint8_t i = 0; i < n_ign; i++) {
		if (ign[i].saved ? drop_saved : drop_temp) {
			saved_gone |= ign[i].saved;
		} else {
			ign[kept++] = ign[i];
		}
	}
	removed = n_ign - kept;
	n_ign = kept;
	k_spin_unlock(&ign_lock, key);

	if (removed != 0) {
		atomic_set(&ign_report, 1);
		SECURITY_EVENT(INFO, SETTING_CHANGED, bletracker_Event_Setting_IGNORE_LIST, n_ign,
			       "ignore clear %s: %d gone %s", names[which], removed,
			       src_short(src));
	}
	if (saved_gone && ignore_store() != 0) {
		removed = -EIO;
	}
	k_mutex_unlock(&ign_mutex);
	return removed;
}

static uint8_t ignore_saved_count(void)
{
	uint8_t n = 0;

	for (uint8_t i = 0; i < n_ign; i++) {
		n += ign[i].saved;
	}
	return n;
}

static void antenna_select(bool external)
{
	/* Only call on a change so the refcount stays at 0 or 1 */
	if (external == ant_external || !device_is_ready(rfsw_ctl)) {
		return;
	}
	if (external) {
		regulator_disable(rfsw_ctl);
	} else {
		regulator_enable(rfsw_ctl);
	}
	ant_external = external;
}

static void antenna_set(bool external, bletracker_Event_Source src)
{
	uint8_t v = external;
	bool changed = external != ant_external;

	antenna_select(external);
	settings_save_one("scanner/ant", &v, 1);
	if (changed) {
		SECURITY_EVENT(INFO, SETTING_CHANGED, bletracker_Event_Setting_ANTENNA, v,
			       "antenna %s (%s)", v ? "ext" : "int",
			       src == bletracker_Event_Source_GATEWAY ? "gateway" : "console");
	}
}

static int antenna_init(void)
{
	if (!device_is_ready(rfsw_pwr) || !device_is_ready(rfsw_ctl)) {
		return -ENODEV;
	}
	if (!regulator_is_enabled(rfsw_pwr)) {
		regulator_enable(rfsw_pwr);
	}
	/* Onboard (rfsw-ctl enabled) first, then whatever was saved */
	if (!regulator_is_enabled(rfsw_ctl)) {
		regulator_enable(rfsw_ctl);
	}
	ant_external = false;
	antenna_select(ant_saved_external);
	return 0;
}

/* Pick the 1 m power out of iBeacon or Eddystone UID/URL adverts */
static bool ad_tx_cb(struct bt_data *data, void *user_data)
{
	int8_t *tx_1m = user_data;

	/* iBeacon: 4C 00 02 15, UUID(16), major(2), minor(2), measured power */
	if (data->type == BT_DATA_MANUFACTURER_DATA && data->data_len == 25 &&
	    data->data[0] == 0x4c && data->data[1] == 0x00 &&
	    data->data[2] == 0x02 && data->data[3] == 0x15) {
		*tx_1m = (int8_t)data->data[24];
		return false;
	}

	/* Eddystone UID (0x00) or URL (0x10): power is at 0 m, ~41 dB above 1 m */
	if (data->type == BT_DATA_SVC_DATA16 && data->data_len >= 4 &&
	    data->data[0] == 0xaa && data->data[1] == 0xfe &&
	    (data->data[2] == 0x00 || data->data[2] == 0x10)) {
		*tx_1m = (int8_t)data->data[3] - 41;
		return false;
	}

	return true;
}

static void scan_cb(const bt_addr_le_t *addr, int8_t rssi, uint8_t adv_type,
		    struct net_buf_simple *ad)
{
	struct adv_evt evt = { .rssi = rssi, .type = adv_type, .tx_1m = TX_UNKNOWN };

	if (filter_on && !bt_addr_eq(&addr->a, &filter_addr)) {
		return;
	}
	if (ignore_match(&addr->a)) {
		return;
	}
	bt_addr_le_copy(&evt.addr, addr);
	evt.len = MIN(ad->len, AD_MAX);
	memcpy(evt.data, ad->data, evt.len);
	bt_data_parse(ad, ad_tx_cb, &evt.tx_1m);
	if (k_msgq_put(&adv_q, &evt, K_NO_WAIT) != 0) {
		atomic_inc(&dropped);
	}
}

/*
 * Primary channel bench test (chan command). The SoftDevice applies a scan
 * channel map only when scanning starts, so each change is stop + map + start;
 * chan_gap_us is how long the last one took. Changes happen in the main
 * thread at the 1 s boundary, after that second's report.
 */
enum chan_mode { CHAN_AUTO, CHAN_FIXED, CHAN_ROTATE };

static enum chan_mode chan_mode;
static uint8_t chan_fixed = 39;
static uint8_t chan_dwell = 1;
static uint8_t chan_now; /* 37-39, 0 = all three (controller rotates) */
static uint32_t chan_secs;
static uint32_t chan_gap_us;

static int chan_map_set(uint8_t ch)
{
	/* Bits 0-36 must stay set; bits 37-39 (byte 4 bits 5-7) pick the channels */
	sdc_hci_cmd_vs_scan_channel_map_set_t p = {
		.channel_map = { 0xff, 0xff, 0xff, 0xff, ch ? 0x1f | BIT(ch - 32) : 0xff },
	};

	return hci_vs_sdc_scan_channel_map_set(&p);
}

static int scan_start(void)
{
	/* Interval == window: radio listens all the time. No duplicate filter. */
	struct bt_le_scan_param param = {
		.type = scan_active ? BT_LE_SCAN_TYPE_ACTIVE : BT_LE_SCAN_TYPE_PASSIVE,
		.options = BT_LE_SCAN_OPT_NONE,
		.interval = 0x0030, /* 30 ms */
		.window = 0x0030,
	};
	int err = chan_map_set(chan_now);

	if (err) {
		printk("scan channel map %u failed (%d)\n", chan_now, err);
	}
	return bt_le_scan_start(&param, scan_cb);
}

static int listen_set(bool on)
{
	int err;

	if (on == scanning) {
		return 0;
	}
	err = on ? scan_start() : bt_le_scan_stop();
	if (err == 0) {
		scanning = on;
	}
	return err;
}

/* Active scanning sends a scan request to each scannable advertiser and hears its reply */
static int active_set(bool on)
{
	int err;

	if (on == scan_active) {
		return 0;
	}
	scan_active = on;
	if (!scanning) {
		return 0; /* scan_start applies it */
	}
	err = bt_le_scan_stop();
	if (err == 0) {
		err = scan_start();
	}
	if (err) {
		scanning = false;
		printk("scan restart failed (%d), listening off\n", err);
	}
	return err;
}

static int flash_adv_start(void)
{
	const struct bt_le_adv_param *param =
		BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN, BT_GAP_ADV_FAST_INT_MIN_2,
				BT_GAP_ADV_FAST_INT_MAX_2, NULL);
	struct bt_data sd[1];
	int err;

	snprintk(flash_name, sizeof(flash_name), "bletracker-%.6s", &chip_id_str[10]);
	sd[0] = (struct bt_data)BT_DATA(BT_DATA_NAME_COMPLETE, flash_name, strlen(flash_name));
	err = bt_le_adv_start(param, flash_ad, ARRAY_SIZE(flash_ad), sd, ARRAY_SIZE(sd));
	if (err == -EALREADY) {
		err = 0;
	}
	if (err == 0) {
		flash_adv_ok = true;
	} else {
		printk("flash mode: bt_le_adv_start failed (%d)\n", err);
	}
	return err;
}

static const char *const source_names[] = { "console", "gateway", "test image window" };

/* timeout: closed because flash_until passed (not by a command) */
static int flash_mode_set(bool on, uint32_t secs, bletracker_Event_Source src, bool timeout)
{
	int err = 0;

	if (!on) {
		if (flash_mode) {
			SECURITY_EVENT(INFO, FLASH_MODE_OFF, timeout, 0, "flash mode off (%s)",
				       timeout ? "timeout" : source_names[src]);
		}
		flash_mode = false;
		bt_le_adv_stop();
		if (smp_conn != NULL) {
			bt_conn_disconnect(smp_conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
		}
		return 0;
	}

	flash_until = k_uptime_get() + (int64_t)secs * 1000;
	if (!flash_mode) {
		flash_mode = true;
		if (smp_conn == NULL) {
			err = flash_adv_start();
		}
		if (err) {
			flash_mode = false;
			return err;
		}
		flash_opens++;
		settings_save_one("scanner/fopens", &flash_opens, sizeof(flash_opens));
		SECURITY_EVENT(WARN, FLASH_MODE_ON, src, flash_opens,
			       "flash mode on for %u s (%s)", secs, source_names[src]);
	}
	return err;
}

/* Advertising stops when a client connects; start it again when it leaves */
static void adv_work_handler(struct k_work *work)
{
	ARG_UNUSED(work);

	if (flash_mode && smp_conn == NULL && flash_adv_start() != 0) {
		printk("flash mode: advertising restart failed\n");
	}
}

static void connected(struct bt_conn *conn, uint8_t err)
{
	char addr_str[BT_ADDR_LE_STR_LEN];

	if (err) {
		k_work_submit(&adv_work);
		return;
	}
	bt_addr_le_to_str(bt_conn_get_dst(conn), addr_str, sizeof(addr_str));
	smp_conn = bt_conn_ref(conn);
	if (!flash_mode) {
		bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
		return;
	}
	SECURITY_EVENT(WARN, CLIENT_CONNECTED, 0, 0, "update client %s", addr_str);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	if (smp_conn == conn) {
		bt_conn_unref(smp_conn);
		smp_conn = NULL;
		SECURITY_EVENT(INFO, CLIENT_DISCONNECTED, reason, 0,
			       "update client left (0x%02x)", reason);
	}
}

/* The connection object is free again only now; advertising started from
 * disconnected() fails with -EAGAIN (seen on hardware 2026-10-30)
 */
static void recycled(void)
{
	k_work_submit(&adv_work);
}

BT_CONN_CB_DEFINE(conn_cbs) = {
	.connected = connected,
	.disconnected = disconnected,
	.recycled = recycled,
};

static void agg_add(const struct adv_evt *evt)
{
	struct dev_agg *d = NULL;

	for (uint8_t i = 0; i < n_devs; i++) {
		if (bt_addr_le_eq(&devs[i].addr, &evt->addr)) {
			d = &devs[i];
			break;
		}
	}
	if (d == NULL) {
		if (n_devs == MAX_DEVS) {
			devs_full++;
			return;
		}
		d = &devs[n_devs++];
		bt_addr_le_copy(&d->addr, &evt->addr);
		d->count = 0;
		d->rssi_max = evt->rssi;
		d->tx_1m = TX_UNKNOWN;
	}

	/* Past MAX_SAMPLES the oldest samples are overwritten */
	d->samples[d->count % MAX_SAMPLES] = evt->rssi;
	d->count++;
	d->adv_type = evt->type;
	if (evt->rssi > d->rssi_max) {
		d->rssi_max = evt->rssi;
	}
	if (evt->tx_1m != TX_UNKNOWN) {
		d->tx_1m = evt->tx_1m;
	}
}

static void tick_add(const struct adv_evt *evt)
{
	struct tick_dev *d = NULL;

	for (uint8_t i = 0; i < n_tdevs; i++) {
		if (bt_addr_le_eq(&tdevs[i].addr, &evt->addr)) {
			d = &tdevs[i];
			break;
		}
	}
	if (d == NULL) {
		if (n_tdevs == MAX_TICK_DEVS) {
			tdevs_full = true;
			return;
		}
		d = &tdevs[n_tdevs++];
		bt_addr_le_copy(&d->addr, &evt->addr);
		d->count = 0;
		d->sum = 0;
		d->rssi_max = evt->rssi;
		d->tx_1m = TX_UNKNOWN;
	}
	d->count++;
	d->sum += evt->rssi;
	d->adv_type = evt->type;
	if (evt->rssi > d->rssi_max) {
		d->rssi_max = evt->rssi;
	}
	if (evt->tx_1m != TX_UNKNOWN) {
		d->tx_1m = evt->tx_1m;
	}
}

/* Keep this advert's bytes as the address's latest advert or scan response */
static void seen_add(const struct adv_evt *evt, int64_t now)
{
	struct seen_dev *s = NULL;
	struct seen_part *p;

	for (uint8_t i = 0; i < n_seen; i++) {
		if (bt_addr_le_eq(&seen[i].addr, &evt->addr)) {
			s = &seen[i];
			break;
		}
	}
	if (s == NULL) {
		if (n_seen < MAX_SEEN) {
			s = &seen[n_seen++];
		} else {
			/* Full: reuse the address heard longest ago */
			s = &seen[0];
			for (uint8_t i = 1; i < n_seen; i++) {
				if (seen[i].heard_at < s->heard_at) {
					s = &seen[i];
				}
			}
			seen_evicted++;
			load_reasons |= bletracker_LoadReason_LOAD_SEEN;
		}
		memset(s, 0, sizeof(*s));
		bt_addr_le_copy(&s->addr, &evt->addr);
	}

	s->heard_at = now;
	p = &s->p[evt->type == BT_GAP_ADV_TYPE_SCAN_RSP ? 1 : 0];
	p->heard_at = now;
	p->hash = crc32_ieee_update(crc32_ieee(&evt->type, 1), evt->data, evt->len);
	p->rssi = evt->rssi;
	p->type = evt->type;
	p->len = evt->len;
	memcpy(p->data, evt->data, evt->len);
}

/* 0 = not due, 2 = changed (or never sent), 1 = refresh; refresh_ms 0 = no refreshes */
static int seen_due(const struct seen_part *p, int64_t now, int64_t refresh_ms)
{
	if (p->heard_at == 0 || p->heard_at <= p->sent_at || now - p->heard_at >= AD_STALE_MS) {
		return 0;
	}
	if (p->sent_at == 0 || p->hash != p->sent_hash) {
		return 2;
	}
	return (refresh_ms && now - p->sent_at >= refresh_ms) ? 1 : 0;
}

static int8_t median(const int8_t *samples, uint16_t n)
{
	int8_t s[MAX_SAMPLES];

	memcpy(s, samples, n);
	for (uint16_t i = 1; i < n; i++) {
		int8_t v = s[i];
		uint16_t j = i;

		while (j > 0 && s[j - 1] > v) {
			s[j] = s[j - 1];
			j--;
		}
		s[j] = v;
	}
	return (int8_t)((s[(n - 1) / 2] + s[n / 2]) / 2);
}

/* Medians for the second, and order[] strongest median first */
static void agg_finish(void)
{
	for (uint8_t i = 0; i < n_devs; i++) {
		uint8_t j = i;

		devs[i].rssi_med = median(devs[i].samples, MIN(devs[i].count, MAX_SAMPLES));
		while (j > 0 && devs[order[j - 1]].rssi_med < devs[i].rssi_med) {
			order[j] = order[j - 1];
			j--;
		}
		order[j] = i;
	}
}

/* One received byte of a gateway command; ISR (or shell inject) context */
static void cmd_rx_byte(uint8_t b)
{
	atomic_inc(&cmd_rx_bytes);
	if (b != 0x00) {
		if (cmd_enc_len < CMD_ENC_MAX) {
			cmd_enc[cmd_enc_len++] = b;
		} else {
			cmd_overflow = true;
		}
		return;
	}

	if (cmd_overflow) {
		cmd_bad_note(BAD_LONG, cmd_enc, cmd_enc_len);
	} else if (cmd_enc_len > 0) {
		struct cmd_msg m = { .len = cmd_enc_len };

		memcpy(m.enc, cmd_enc, cmd_enc_len);
		if (k_msgq_put(&cmd_q, &m, K_NO_WAIT) == 0) {
			k_work_submit(&cmd_work);
		} else {
			cmd_bad_note(BAD_QUEUE, cmd_enc, cmd_enc_len);
		}
	}
	cmd_enc_len = 0;
	cmd_overflow = false;
}

static void gw_uart_isr(const struct device *dev, void *user_data)
{
	ARG_UNUSED(user_data);

	if (!uart_irq_update(dev)) {
		return;
	}
	if (uart_err_check(dev) > 0) {
		atomic_inc(&cmd_rx_errors);
	}
	if (uart_irq_rx_ready(dev)) {
		uint8_t buf[16];
		int n = uart_fifo_read(dev, buf, sizeof(buf));

		for (int i = 0; i < n; i++) {
			cmd_rx_byte(buf[i]);
		}
	}
	if (uart_irq_tx_ready(dev)) {
		if (frame_tx_pos < frame_tx_len) {
			frame_tx_pos += uart_fifo_fill(dev, &frame_tx[frame_tx_pos],
						       frame_tx_len - frame_tx_pos);
		}
		if (frame_tx_pos >= frame_tx_len) {
			uart_irq_tx_disable(dev);
		}
	}
}

static int gw_uart_init(void)
{
	struct uart_config cfg;
	int err;

	if (!device_is_ready(gw_uart)) {
		return -ENODEV;
	}
	if (uart_config_get(gw_uart, &cfg) == 0) {
		uart_baud = cfg.baudrate;
	}
	err = uart_irq_callback_user_data_set(gw_uart, gw_uart_isr, NULL);
	if (err == 0) {
		uart_irq_rx_enable(gw_uart);
	}
	return err;
}

static size_t cobs_encode(const uint8_t *in, size_t len, uint8_t *out)
{
	size_t code_at = 0;
	size_t o = 1;
	uint8_t code = 1;

	for (size_t i = 0; i < len; i++) {
		if (in[i] == 0) {
			out[code_at] = code;
			code_at = o++;
			code = 1;
			continue;
		}
		out[o++] = in[i];
		if (++code == 0xff) {
			out[code_at] = code;
			code_at = o++;
			code = 1;
		}
	}
	out[code_at] = code;
	return o;
}

/* Decoded length, or -1 if the input isn't valid COBS or doesn't fit */
static int cobs_decode(const uint8_t *in, size_t len, uint8_t *out, size_t out_max)
{
	size_t i = 0;
	size_t o = 0;

	while (i < len) {
		uint8_t code = in[i++];

		if (code == 0 || i + code - 1 > len) {
			return -1;
		}
		for (uint8_t k = 1; k < code; k++) {
			if (o >= out_max) {
				return -1;
			}
			out[o++] = in[i++];
		}
		if (code < 0xff && i < len) {
			if (o >= out_max) {
				return -1;
			}
			out[o++] = 0x00;
		}
	}
	return o;
}

/* IgnoreRule -> masked addr and mask; false if malformed or the mask is all zeros */
static bool ignore_from_pb(const bletracker_IgnoreRule *r, uint8_t addr[ADDR_LEN],
			   uint8_t mask[ADDR_LEN])
{
	bool any = false;

	if (r->addr.size != ADDR_LEN || (r->mask.size != 0 && r->mask.size != ADDR_LEN)) {
		return false;
	}
	for (int b = 0; b < ADDR_LEN; b++) {
		mask[b] = r->mask.size ? r->mask.bytes[b] : 0xff;
		addr[b] = r->addr.bytes[b] & mask[b];
		any |= mask[b] != 0;
	}
	return any;
}

/* NULL = rejected (argument out of range); else what was done, for the ack */
static const char *cmd_apply(const bletracker_Command *c, bool to_all)
{
	const bletracker_Event_Source gw = bletracker_Event_Source_GATEWAY;
	uint8_t addr[ADDR_LEN];
	uint8_t mask[ADDR_LEN];

	switch (c->which_action) {
	/* The ignore list is mast-wide: every scanner ignores the same addresses, so these are
	 * only accepted in a command to all scanners (like the rssi interval)
	 */
	case bletracker_Command_ignore_tag: {
		static const char *const done[] = {
			[IGN_ADDED] = "ignore added", [IGN_CHANGED] = "ignore changed",
			[IGN_SAME] = "ignore unchanged", [IGN_FLASH_ERR] = "ignore NOT SAVED",
		};
		enum ignore_result res;

		if (!to_all || !ignore_from_pb(&c->action.ignore, addr, mask)) {
			return NULL;
		}
		res = ignore_add(addr, mask, c->action.ignore.save, gw);
		return res == IGN_FULL ? NULL : done[res];
	}
	case bletracker_Command_unignore_tag: {
		int err;

		if (!to_all || !ignore_from_pb(&c->action.unignore, addr, mask)) {
			return NULL;
		}
		err = ignore_del(addr, mask, gw);
		return err == -ENOENT ? NULL : err ? "unignore NOT SAVED" : "unignored";
	}
	case bletracker_Command_ignore_list_tag:
		/* Reading is fine per scanner: comparing them is the point */
		if (!c->action.ignore_list) {
			return NULL;
		}
		atomic_set(&ign_report, 1);
		return "ignore list in next bucket";
	case bletracker_Command_ignore_clear_tag: {
		int n;

		if (!to_all || c->action.ignore_clear < bletracker_IgnoreClear_IGNORE_CLEAR_TEMP ||
		    c->action.ignore_clear > bletracker_IgnoreClear_IGNORE_CLEAR_ALL) {
			return NULL;
		}
		n = ignore_clear(c->action.ignore_clear, gw);
		return n < 0 ? "ignore clear NOT SAVED" : "ignore cleared";
	}
	case bletracker_Command_listen_tag:
		return listen_set(c->action.listen) ? "listen FAILED" :
		       (c->action.listen ? "listen on" : "listen off");
	case bletracker_Command_flash_tag:
		return flash_mode_set(c->action.flash, FLASH_MODE_S, gw, false) ? "flash FAILED" :
		       (c->action.flash ? "flash on" : "flash off");
	case bletracker_Command_ext_antenna_tag:
		antenna_set(c->action.ext_antenna, gw);
		return c->action.ext_antenna ? "ant ext" : "ant int";
	case bletracker_Command_reboot_tag:
		if (c->action.reboot != CMD_REBOOT_MAGIC) {
			return NULL;
		}
		printk("gateway command: reboot\n");
		k_sleep(K_MSEC(50));
		sys_reboot(SYS_REBOOT_COLD);
		return NULL;
	case bletracker_Command_payloads_tag:
		payloads_on = c->action.payloads;
		return payloads_on ? "payloads on" : "payloads off";
	case bletracker_Command_active_scan_tag:
		return active_set(c->action.active_scan) ? "active FAILED" :
		       (c->action.active_scan ? "active on" : "active off");
	case bletracker_Command_intervals_tag: {
		const bletracker_Intervals *iv = &c->action.intervals;

		/* RSSI timing is mast-wide: sectors are compared over the same window */
		if ((iv->rssi && !to_all) || iv->rssi > 50 || iv->payload > 50 ||
		    iv->refresh > 3000 || iv->status > 50 || iv->counters > 3000) {
			return NULL;
		}
		intervals.rssi = iv->rssi ? iv->rssi : intervals.rssi;
		intervals.payload = iv->payload ? iv->payload : intervals.payload;
		intervals.refresh = iv->refresh ? iv->refresh : intervals.refresh;
		intervals.status = iv->status ? iv->status : intervals.status;
		intervals.counters = iv->counters ? iv->counters : intervals.counters;
		return "intervals set";
	}
	case bletracker_Command_budget_pct_tag:
		if (c->action.budget_pct < 10 || c->action.budget_pct > 90) {
			return NULL;
		}
		budget_pct = c->action.budget_pct;
		return "budget set";
	default:
		return NULL;
	}
}

/* Decode, check and run queued gateway commands (system workqueue) */
static void cmd_work_handler(struct k_work *work)
{
	static const uint8_t all[sizeof(chip_id)];
	struct cmd_msg m;

	ARG_UNUSED(work);

	while (k_msgq_get(&cmd_q, &m, K_NO_WAIT) == 0) {
		bletracker_Command c = bletracker_Command_init_zero;
		uint8_t raw[CMD_RAW_MAX];
		int len = cobs_decode(m.enc, m.len, raw, sizeof(raw));
		pb_istream_t is;
		bool to_all;
		const char *result;

		if (len < 3) {
			cmd_bad_note(BAD_FRAME, m.enc, m.len);
			continue;
		}
		if (crc16_itu_t(0xffff, raw, len - 2) != sys_get_le16(&raw[len - 2])) {
			cmd_bad_note(BAD_CRC, m.enc, m.len);
			continue;
		}
		is = pb_istream_from_buffer(raw, len - 2);
		if (!pb_decode(&is, bletracker_Command_fields, &c) ||
		    (c.target.size != 0 && c.target.size != sizeof(chip_id))) {
			cmd_bad_note(BAD_DECODE, m.enc, m.len);
			continue;
		}
		to_all = c.target.size == 0 || memcmp(c.target.bytes, all, sizeof(chip_id)) == 0;
		if (!to_all && memcmp(c.target.bytes, chip_id, sizeof(chip_id)) != 0) {
			atomic_inc(&cmds_other);
			continue;
		}
		result = cmd_apply(&c, to_all);
		if (result == NULL) {
			cmd_bad_note(BAD_ARG, m.enc, m.len);
			event_post(bletracker_Event_Category_COMMAND, bletracker_Event_Severity_WARN,
				   bletracker_Event_Code_CMD_REJECTED, c.which_action, 0, c.seq,
				   "command %u (action %u)%s rejected", c.seq, c.which_action,
				   to_all ? " to all" : "");
			continue;
		}
		atomic_inc(&cmds_ok);
		event_post(bletracker_Event_Category_COMMAND, bletracker_Event_Severity_INFO,
			   bletracker_Event_Code_CMD_OK, c.which_action, 0, c.seq,
			   "command %u: %s%s", c.seq, result, to_all ? " (to all)" : "");
	}
}

/* Append one Record as Bucket.records; false if it would pass `limit` bytes */
static bool record_put(pb_ostream_t *s, const bletracker_Record *rec, size_t limit)
{
	size_t size;
	size_t need;

	if (!pb_get_encoded_size(&size, bletracker_Record_fields, rec)) {
		return false;
	}
	need = 1 + (size < 128 ? 1 : 2) + size;
	if (s->bytes_written + need > limit) {
		return false;
	}
	return pb_encode_tag(s, PB_WT_STRING, BUCKET_RECORDS_TAG) &&
	       pb_encode_submessage(s, bletracker_Record_fields, rec);
}

static void addr_put(uint8_t out[6], const bt_addr_le_t *addr)
{
	for (int b = 0; b < 6; b++) {
		out[b] = addr->a.val[5 - b];
	}
}

static void level_set(uint8_t level)
{
	static const char *const names[] = {
		"normal", "payload refresh slowed", "payload refresh off", "payloads off",
		"RSSI trimmed",
	};

	if (level == load_level) {
		return;
	}
	load_level = level;
	event_post(bletracker_Event_Category_LOAD,
		   level == 0 ? bletracker_Event_Severity_INFO :
		   level < bletracker_LoadLevel_RSSI_TRIMMED ? bletracker_Event_Severity_WARN :
		   bletracker_Event_Severity_ERROR,
		   bletracker_Event_Code_LOAD_LEVEL, level, load_reasons, 0, "load level %u: %s",
		   level, names[level]);
}

static void ignore_list_fill(bletracker_IgnoreList *l)
{
	k_spinlock_key_t key = k_spin_lock(&ign_lock);

	l->rules_count = n_ign;
	for (uint8_t i = 0; i < n_ign; i++) {
		bletracker_IgnoreEntry *e = &l->rules[i];

		memcpy(e->addr, ign[i].addr, ADDR_LEN);
		memcpy(e->mask, ign[i].mask, ADDR_LEN);
		e->saved = ign[i].saved;
		e->hits = ign[i].hits;
	}
	k_spin_unlock(&ign_lock, key);
	l->paused = ign_paused;
}

static void status_fill(bletracker_Status *st)
{
	strncpy(st->version, APP_VERSION_STRING, sizeof(st->version) - 1);
	st->ext_antenna = ant_external;
	st->listening = scanning;
	st->active_scan = scan_active;
	st->payloads = payloads_on;
	st->flash_mode = flash_mode;
	st->client = smp_conn != NULL;
	st->test_image = !img_confirmed;
	st->adverts = last_adverts;
	st->dropped = last_dropped;
	st->devices = last_devices;
	st->load_reasons = load_reasons;
	st->line_peak_pct = line_peak_pct;
	st->budget_pct = budget_pct;
	st->has_intervals = true;
	st->intervals = intervals;
	st->baud = uart_baud;
	st->ignore_rules = n_ign;
	st->ignore_saved = ignore_saved_count();
	st->ignored = last_ignored;
}

static void counters_fill(bletracker_Counters *c)
{
	c->uptime_s = k_uptime_get() / 1000;
	c->buckets_sent = buckets_sent;
	c->buckets_skipped = buckets_skipped;
	c->cmds_ok = atomic_get(&cmds_ok);
	c->cmds_bad = atomic_get(&cmds_bad);
	c->cmds_other = atomic_get(&cmds_other);
	c->rx_errors = atomic_get(&cmd_rx_errors);
	c->payloads_sent = payloads_sent;
	c->payloads_held = payloads_held;
	c->rssi_trimmed = rssi_trimmed;
	c->seen_evicted = seen_evicted;
	c->events_lost = atomic_get(&events_lost);
	c->boots = boot_count;
	c->flash_opens = flash_opens;
	c->ignored = atomic_get(&ign_total);
}

/* RSSI records strongest mean first; true if any were left out */
static bool rssi_put(pb_ostream_t *s, bletracker_Record *rec, size_t budget)
{
	bool trimmed = false;

	for (uint8_t i = 0; i < n_tdevs; i++) {
		uint8_t j = i;

		/* mean_i > mean_j  <=>  sum_i * n_j > sum_j * n_i (counts are positive) */
		while (j > 0 && (int64_t)tdevs[i].sum * tdevs[torder[j - 1]].count >
				(int64_t)tdevs[torder[j - 1]].sum * tdevs[i].count) {
			torder[j] = torder[j - 1];
			j--;
		}
		torder[j] = i;
	}

	for (uint8_t k = 0; k < n_tdevs; k++) {
		const struct tick_dev *d = &tdevs[torder[k]];
		bletracker_Rssi *r = &rec->kind.rssi;

		*rec = (bletracker_Record)bletracker_Record_init_zero;
		rec->which_kind = bletracker_Record_rssi_tag;
		addr_put(r->addr, &d->addr);
		r->random = d->addr.type & 1;
		r->adv_type = d->adv_type;
		r->rssi_sum_dbm = d->sum;
		r->count = d->count;
		r->rssi_max_dbm = d->rssi_max;
		r->has_tx_1m_dbm = d->tx_1m != TX_UNKNOWN;
		r->tx_1m_dbm = r->has_tx_1m_dbm ? d->tx_1m : 0;
		if (!record_put(s, rec, budget)) {
			rssi_trimmed += n_tdevs - k;
			trimmed = true;
			break;
		}
	}
	n_tdevs = 0;
	tdevs_full = false;
	return trimmed;
}

/* Due payloads, changed first, until the budget is used; true if any were held back */
static bool payloads_put(pb_ostream_t *s, bletracker_Record *rec, size_t budget, int64_t now)
{
	int64_t refresh_ms = load_level >= bletracker_LoadLevel_REFRESH_OFF ? 0 :
			     (int64_t)intervals.refresh * TICK_MS *
			     (load_level == bletracker_LoadLevel_REFRESH_SLOWED ? 3 : 1);

	for (;;) {
		struct seen_dev *best_s = NULL;
		struct seen_part *best = NULL;
		int best_due = 0;
		bletracker_Payload *p;

		for (uint8_t i = 0; i < n_seen; i++) {
			for (int k = 0; k < 2; k++) {
				struct seen_part *c = &seen[i].p[k];
				int due = seen_due(c, now, refresh_ms);

				if (due > best_due ||
				    (due && due == best_due && c->sent_at < best->sent_at)) {
					best_s = &seen[i];
					best = c;
					best_due = due;
				}
			}
		}
		if (best == NULL) {
			return false;
		}

		*rec = (bletracker_Record)bletracker_Record_init_zero;
		if (best->type == BT_GAP_ADV_TYPE_SCAN_RSP) {
			rec->which_kind = bletracker_Record_scan_rsp_tag;
			p = &rec->kind.scan_rsp;
		} else {
			rec->which_kind = bletracker_Record_advert_tag;
			p = &rec->kind.advert;
		}
		addr_put(p->addr, &best_s->addr);
		p->random = best_s->addr.type & 1;
		p->adv_type = best->type;
		p->rssi_dbm = best->rssi;
		p->data.size = best->len;
		memcpy(p->data.bytes, best->data, best->len);
		p->refresh = best_due == 1;
		p->age_ticks = (now - best->heard_at) / TICK_MS;
		if (!record_put(s, rec, budget)) {
			for (uint8_t i = 0; i < n_seen; i++) {
				payloads_held += (seen_due(&seen[i].p[0], now, refresh_ms) != 0) +
						 (seen_due(&seen[i].p[1], now, refresh_ms) != 0);
			}
			return true;
		}
		best->sent_at = now;
		best->sent_hash = best->hash;
		payloads_sent++;
	}
}

/* Build and send this tick's bucket; the throttle follows how full it was */
static void tick_send(int64_t now, int64_t t_start)
{
	static bletracker_Record rec;
	bletracker_Bucket hdr = bletracker_Bucket_init_zero;
	bletracker_Event ev;
	uint32_t seq = tick_seq++;
	size_t budget = (size_t)uart_baud / 10 * TICK_MS / 1000 * budget_pct / 100;
	size_t raw_len;
	size_t tx_len;
	pb_ostream_t s;
	bool rssi_due = (seq + 1) % intervals.rssi == 0;
	bool trimmed = false;
	bool held = false;
	uint32_t lost;
	uint32_t pct;

	if (!device_is_ready(gw_uart)) {
		return;
	}
	if (frame_tx_pos < frame_tx_len) {
		/* The gateway sees the gap; this tick's RSSI is lost with it */
		buckets_skipped++;
		load_reasons |= bletracker_LoadReason_LOAD_LINE;
		if (rssi_due) {
			n_tdevs = 0;
		}
		return;
	}

	s = pb_ostream_from_buffer(frame_raw, sizeof(frame_raw) - 2);
	memcpy(hdr.chip_id, chip_id, sizeof(chip_id));
	hdr.seq = seq;
	hdr.t_ms = (uint32_t)t_start;
	hdr.tick_ms = TICK_MS;
	hdr.chan = chan_now;
	hdr.load = load_level;
	pb_encode(&s, bletracker_Bucket_fields, &hdr);

	lost = atomic_get(&events_lost);
	if (lost != (uint32_t)atomic_get(&events_lost_reported)) {
		atomic_set(&events_lost_reported, lost);
		event_post(bletracker_Event_Category_GENERAL, bletracker_Event_Severity_WARN,
			   bletracker_Event_Code_EVENTS_LOST, lost, 0, 0, "%u events lost", lost);
	}
	while (k_msgq_get(&event_q, &ev, K_NO_WAIT) == 0) {
		rec = (bletracker_Record)bletracker_Record_init_zero;
		rec.which_kind = bletracker_Record_event_tag;
		rec.kind.event = ev;
		if (!record_put(&s, &rec, s.max_size)) {
			atomic_inc(&events_lost);
			break;
		}
	}

	if (seq % intervals.status == 0) {
		rec = (bletracker_Record)bletracker_Record_init_zero;
		rec.which_kind = bletracker_Record_status_tag;
		status_fill(&rec.kind.status);
		if (record_put(&s, &rec, s.max_size)) {
			load_reasons = 0;
			line_peak_pct = 0;
		}
	}
	if (seq % intervals.counters == 0) {
		rec = (bletracker_Record)bletracker_Record_init_zero;
		rec.which_kind = bletracker_Record_counters_tag;
		counters_fill(&rec.kind.counters);
		record_put(&s, &rec, s.max_size);
	}

	if (rssi_due) {
		if (tdevs_full) {
			load_reasons |= bletracker_LoadReason_LOAD_TABLE;
		}
		trimmed = rssi_put(&s, &rec, MAX(budget, s.bytes_written));
	}
	if (payloads_on && load_level < bletracker_LoadLevel_PAYLOADS_OFF &&
	    (seq + 1) % intervals.payload == 0) {
		held = payloads_put(&s, &rec, budget, now);
	}

	pct = s.bytes_written * 100 / budget;
	line_peak_pct = MAX(line_peak_pct, pct);
	if (trimmed || held) {
		load_reasons |= bletracker_LoadReason_LOAD_LINE;
	}

	/* Throttle: straight to 4 on a trim, up one step when payloads are held back,
	 * down one step after CALM_TICKS quiet ticks (level 4: without a trim)
	 */
	if (trimmed) {
		calm_ticks = 0;
		level_set(bletracker_LoadLevel_RSSI_TRIMMED);
	} else if (held) {
		calm_ticks = 0;
		level_set(MIN(load_level + 1, bletracker_LoadLevel_PAYLOADS_OFF));
	} else if (load_level == bletracker_LoadLevel_RSSI_TRIMMED || pct < 50) {
		if (load_level > 0 && ++calm_ticks >= CALM_TICKS) {
			calm_ticks = 0;
			level_set(load_level - 1);
		}
	} else {
		calm_ticks = 0;
	}

	/* Ignore list (up to ~830 bytes) last, after the throttle has measured the tick, so it never
	 * trims RSSI; it may pass the budget but not 90% of the line, else it waits a tick
	 */
	if (atomic_cas(&ign_report, 1, 0)) {
		rec = (bletracker_Record)bletracker_Record_init_zero;
		rec.which_kind = bletracker_Record_ignore_list_tag;
		ignore_list_fill(&rec.kind.ignore_list);
		if (!record_put(&s, &rec, (size_t)uart_baud / 10 * TICK_MS / 1000 * 9 / 10)) {
			atomic_set(&ign_report, 1);
		}
	}

	raw_len = s.bytes_written;
	sys_put_le16(crc16_itu_t(0xffff, frame_raw, raw_len), &frame_raw[raw_len]);
	raw_len += 2;

	tx_len = cobs_encode(frame_raw, raw_len, frame_tx);
	frame_tx[tx_len++] = 0x00;

	if (frame_dump) {
		frame_dump = false;
		printk("frame (%u bytes):", tx_len);
		for (size_t i = 0; i < tx_len; i++) {
			printk("%s%02x", (i % 32) ? " " : "\n", frame_tx[i]);
		}
		printk("\n");
	}

	frame_tx_pos = 0;
	frame_tx_len = tx_len;
	buckets_sent++;
	uart_irq_tx_enable(gw_uart);
}

static void list_print(void)
{
	uint8_t shown = 0;

	if (list_mode == LIST_TABLE) {
		printk("--- %u devices, %u adverts, ant=%s ---\n", n_devs, sec_total,
		       ant_external ? "ext" : "int");
		printk("address           type   med  max   n  tx1m adv\n");
	}

	for (uint8_t k = 0; k < n_devs; k++) {
		const struct dev_agg *d = &devs[order[k]];
		char addr_str[BT_ADDR_STR_LEN];
		char tx_str[8] = "";

		if (d->rssi_med < list_min_rssi) {
			continue;
		}
		shown++;
		bt_addr_to_str(&d->addr.a, addr_str, sizeof(addr_str));
		if (d->tx_1m != TX_UNKNOWN) {
			snprintk(tx_str, sizeof(tx_str), "%d", d->tx_1m);
		}

		if (list_mode == LIST_CSV) {
			/* address, addr_type, rssi_med, rssi_max, count, tx_1m */
			printk("%s,%s,%d,%d,%u,%s\n", addr_str,
			       (d->addr.type & 1) ? "random" : "public", d->rssi_med,
			       d->rssi_max, d->count, tx_str);
		} else {
			printk("%s %-6s %4d %4d %3u %5s %u\n", addr_str,
			       (d->addr.type & 1) ? "random" : "public", d->rssi_med,
			       d->rssi_max, d->count, tx_str, d->adv_type);
		}
	}

	if (list_mode == LIST_TABLE && shown < n_devs) {
		printk("(%u below %d dBm hidden)\n", n_devs - shown, list_min_rssi);
	}
	if (devs_full) {
		printk("(table full: %u adverts from extra devices ignored)\n", devs_full);
	}
}

static void handle_adv(const struct adv_evt *evt)
{
	sec_total++;
	if (payloads_on) {
		seen_add(evt, k_uptime_get());
	}

	if (print_raw) {
		char addr_str[BT_ADDR_LE_STR_LEN];
		char hex[2 * AD_MAX + 1];

		bt_addr_le_to_str(&evt->addr, addr_str, sizeof(addr_str));
		bin2hex(evt->data, evt->len, hex, sizeof(hex));
		printk("%s rssi=%d type=%u ad=%s\n", addr_str, evt->rssi, evt->type,
		       evt->len ? hex : "-");
	}

	/* Scan responses only feed payloads, so RSSI means the same in both scan modes */
	if (evt->type == BT_GAP_ADV_TYPE_SCAN_RSP) {
		return;
	}
	agg_add(evt);
	tick_add(evt);

	if (filter_on) {
		if (sec_n == 0 || evt->rssi < sec_min) {
			sec_min = evt->rssi;
		}
		if (sec_n == 0 || evt->rssi > sec_max) {
			sec_max = evt->rssi;
		}
		sec_sum += evt->rssi;
		sec_n++;
	}
}

/* Once a second: flash mode timeout, confirming a test image, periodic warnings */
static void housekeeping(int64_t now)
{
	static uint32_t secs;
	static uint32_t bad_seen;

	if (flash_mode && smp_conn == NULL && now >= flash_until) {
		flash_mode_set(false, 0, bletracker_Event_Source_GATEWAY, true);
	}

	if (!img_confirmed && now >= CONFIRM_AFTER_MS && scanning && flash_adv_ok) {
		if (boot_write_img_confirmed() == 0) {
			img_confirmed = true;
			SECURITY_EVENT(INFO, IMAGE_CONFIRMED, 0, 0, "image %s confirmed",
				       APP_VERSION_STRING);
		}
	}

	secs++;
	if (secs % 10 == 0) {
		uint32_t bad = atomic_get(&cmds_bad);

		if (bad - bad_seen >= 3) {
			SECURITY_EVENT(WARN, BAD_COMMANDS, bad - bad_seen, 0,
				       "%u bad command frames on D7 in 10 s", bad - bad_seen);
		}
		bad_seen = bad;
	}
}

/* At the 1 s boundary: pick the channel for the coming second */
static void chan_tick(void)
{
	uint8_t want;
	uint32_t t0;
	int err;

	switch (chan_mode) {
	case CHAN_FIXED:
		want = chan_fixed;
		break;
	case CHAN_ROTATE:
		want = 37 + (chan_secs / chan_dwell) % 3;
		break;
	default:
		want = 0;
		break;
	}
	chan_secs++;
	if (want == chan_now) {
		return;
	}
	chan_now = want;
	if (!scanning) {
		return; /* scan_start applies it */
	}
	t0 = k_cycle_get_32();
	err = bt_le_scan_stop();
	if (err == 0) {
		err = scan_start();
	}
	chan_gap_us = k_cyc_to_us_floor32(k_cycle_get_32() - t0);
	if (err) {
		scanning = false;
		printk("channel switch failed (%d), listening off\n", err);
	}
}

static void report_second(void)
{
	uint32_t drops = (uint32_t)atomic_set(&dropped, 0);
	const char *ant = ant_external ? "ext" : "int";

	agg_finish();
	last_adverts = sec_total;
	last_dropped = drops;
	last_devices = n_devs;
	last_ignored = (uint32_t)atomic_set(&ign_sec, 0);
	if (drops) {
		load_reasons |= bletracker_LoadReason_LOAD_QUEUE;
		/* Payload handling costs main-thread time: shed it */
		if (payloads_on && load_level < bletracker_LoadLevel_PAYLOADS_OFF) {
			level_set(load_level + 1);
		}
	}

	if (filter_on) {
		if (sec_n > 0) {
			int32_t mean10 = (sec_sum * 10) / (int32_t)sec_n;

			printk("[1s] ant=%s n=%u mean=%d.%d min=%d max=%d\n", ant, sec_n,
			       mean10 / 10, abs(mean10 % 10), sec_min, sec_max);
		} else {
			printk("[1s] ant=%s n=0\n", ant);
		}
	} else if (list_mode != LIST_OFF) {
		list_print();
	} else if (!print_raw) {
		char ch[24];
		char ig[24] = "";
		int len = chan_now ? snprintk(ch, sizeof(ch), "%u", chan_now)
				   : snprintk(ch, sizeof(ch), "all");

		/* The switch made at the start of this second, if any */
		if (chan_gap_us) {
			snprintk(ch + len, sizeof(ch) - len, " switch=%uus", chan_gap_us);
		}
		if (n_ign) {
			snprintk(ig, sizeof(ig), ign_paused ? " ignored=off" : " ignored=%u",
				 last_ignored);
		}
		printk("[1s] ant=%s ch=%s adverts=%u devices=%u dropped=%u%s load=%u%s%s\n", ant,
		       ch, sec_total, n_devs, drops, ig, load_level,
		       scanning ? "" : " (listening off)", flash_mode ? " (flash mode)" : "");
	}
	chan_gap_us = 0;
	chan_tick();

	n_devs = 0;
	devs_full = 0;
	sec_total = 0;
	sec_n = 0;
	sec_sum = 0;
}

/* Boot count, reset cause, version change and test image, as security events */
static void boot_events(void)
{
	uint32_t cause = 0;

	boot_count++;
	settings_save_one("scanner/boots", &boot_count, sizeof(boot_count));
	if (hwinfo_get_reset_cause(&cause) == 0) {
		hwinfo_clear_reset_cause();
	}
	/* Anything but power-on, a software reset or the debugger is worth a look */
	if (cause & ~(RESET_POR | RESET_SOFTWARE | RESET_DEBUG)) {
		SECURITY_EVENT(WARN, BOOT, cause, boot_count, "boot %u, reset cause 0x%x",
			       boot_count, cause);
	} else {
		SECURITY_EVENT(INFO, BOOT, cause, boot_count, "boot %u, reset cause 0x%x",
			       boot_count, cause);
	}

	if (strcmp(last_version, APP_VERSION_STRING) != 0) {
		SECURITY_EVENT(WARN, VERSION_CHANGED, 0, 0, "version %s -> %s",
			       last_version[0] ? last_version : "?", APP_VERSION_STRING);
		settings_save_one("scanner/ver", APP_VERSION_STRING, strlen(APP_VERSION_STRING));
	}
	if (!img_confirmed) {
		SECURITY_EVENT(WARN, TEST_IMAGE, 0, 0, "test image %s (confirms after 60 s)",
			       APP_VERSION_STRING);
	}
}

static int cmd_status(const struct shell *sh, size_t argc, char **argv)
{
	shell_print(sh, "version %s, image %s", APP_VERSION_STRING,
		    img_confirmed ? "confirmed" : "TEST (not confirmed yet)");
	shell_print(sh, "chip ID %s, boot %u, flash mode opened %u times", chip_id_str,
		    boot_count, flash_opens);
	shell_print(sh, "antenna %s", ant_external ? "ext" : "int");
	shell_print(sh, "listening %s (%s), payloads %s", scanning ? "on" : "off",
		    scan_active ? "active" : "passive", payloads_on ? "on" : "off");
	if (flash_mode) {
		shell_print(sh, "flash mode on as %s, %s, %lld s left", flash_name,
			    smp_conn ? "client connected" : "advertising",
			    MAX(0, (flash_until - k_uptime_get()) / 1000));
	} else {
		shell_print(sh, "flash mode off");
	}
	shell_print(sh, "stream: %u ms ticks, %u baud, budget %u%%, load level %u", TICK_MS,
		    uart_baud, budget_pct, load_level);
	shell_print(sh, "intervals (ticks): rssi %u, payload %u, refresh %u, status %u, "
		    "counters %u", intervals.rssi, intervals.payload, intervals.refresh,
		    intervals.status, intervals.counters);
	shell_print(sh, "payloads sent %u, held %u; rssi trimmed %u; addresses kept %u, "
		    "evicted %u; events lost %u", payloads_sent, payloads_held, rssi_trimmed,
		    n_seen, seen_evicted, (unsigned)atomic_get(&events_lost));
	shell_print(sh, "gateway commands: %u ok, %u bad (cmdlog shows them), %u for others",
		    (unsigned)atomic_get(&cmds_ok), (unsigned)atomic_get(&cmds_bad),
		    (unsigned)atomic_get(&cmds_other));
	shell_print(sh, "D7 line: %u bytes received, %u UART errors",
		    (unsigned)atomic_get(&cmd_rx_bytes), (unsigned)atomic_get(&cmd_rx_errors));
	shell_print(sh, "ignore list: %u rules (%u saved)%s, %u adverts ignored", n_ign,
		    ignore_saved_count(), ign_paused ? ", PAUSED" : "",
		    (unsigned)atomic_get(&ign_total));
	return 0;
}

static void ignore_list(const struct shell *sh)
{
	shell_print(sh, "%u of %u rules (%u saved), %s, %u adverts ignored since boot", n_ign,
		    IGNORE_MAX, ignore_saved_count(), ign_paused ? "PAUSED (ignore on)" : "on",
		    (unsigned)atomic_get(&ign_total));
	/* One rule at a time off the shell's stack; a change meanwhile may skip or repeat one */
	for (uint8_t i = 0;; i++) {
		struct ignore_rule r;
		k_spinlock_key_t key = k_spin_lock(&ign_lock);
		bool more = i < n_ign;
		char str[48];

		if (more) {
			r = ign[i];
		}
		k_spin_unlock(&ign_lock, key);
		if (!more) {
			break;
		}
		ignore_fmt(str, sizeof(str), r.addr, r.mask);
		shell_print(sh, "  %-36s %-12s %u hits", str, r.saved ? "saved" : "until reboot",
			    r.hits);
	}
}

static const char ignore_usage[] =
	"ignore [list]                      show the rules\n"
	"ignore <addr>[/bits|/mask] [save]  ignore until reboot, or saved in flash\n"
	"                                   (* for any byte: C1:7D:2B:*:*:*)\n"
	"ignore clear boot|saved|all        remove rules\n"
	"ignore off|on                      pause / resume (until reboot)\n"
	"unignore <addr>[/bits|/mask]|all   remove one rule (as listed) or all";

static int cmd_ignore(const struct shell *sh, size_t argc, char **argv)
{
	const bletracker_Event_Source con = bletracker_Event_Source_CONSOLE;
	uint8_t addr[ADDR_LEN];
	uint8_t mask[ADDR_LEN];
	char str[48];

	if (argc == 1 || (argc == 2 && strcmp(argv[1], "list") == 0)) {
		ignore_list(sh);
		return 0;
	}
	if (argc == 2 && (strcmp(argv[1], "on") == 0 || strcmp(argv[1], "off") == 0)) {
		ign_paused = argv[1][1] == 'f';
		atomic_set(&ign_report, 1);
		shell_print(sh, "ignore list %s", ign_paused ? "paused until `ignore on` or reboot" :
			    "on");
		return 0;
	}
	if (argc == 3 && strcmp(argv[1], "clear") == 0) {
		static const char *const kinds[] = { "", "boot", "saved", "all" };
		int n;

		for (size_t k = 1; k < ARRAY_SIZE(kinds); k++) {
			if (strcmp(argv[2], kinds[k]) == 0) {
				n = ignore_clear((bletracker_IgnoreClear)k, con);
				if (n < 0) {
					shell_error(sh, "flash write failed");
					return n;
				}
				shell_print(sh, "%d rules removed, %u left", n, n_ign);
				return 0;
			}
		}
	}
	if ((argc == 2 || (argc == 3 && strcmp(argv[2], "save") == 0)) &&
	    ignore_parse(argv[1], addr, mask)) {
		bool save = argc == 3;

		ignore_fmt(str, sizeof(str), addr, mask);
		switch (ignore_add(addr, mask, save, con)) {
		case IGN_FULL:
			shell_error(sh, "list full (%u rules): unignore one first", IGNORE_MAX);
			return -ENOMEM;
		case IGN_FLASH_ERR:
			shell_error(sh, "%s ignored, but the flash write failed: until reboot only",
				    str);
			return -EIO;
		case IGN_SAME:
			shell_print(sh, "%s already ignored %s", str,
				    save ? "(saved)" : "until reboot");
			return 0;
		case IGN_CHANGED:
			shell_print(sh, "%s now %s", str,
				    save ? "saved" : "until reboot (removed from flash)");
			return 0;
		default:
			shell_print(sh, "%s ignored %s", str, save ? "(saved)" : "until reboot");
			return 0;
		}
	}
	shell_error(sh, "usage:\n%s", ignore_usage);
	return -EINVAL;
}

static int cmd_unignore(const struct shell *sh, size_t argc, char **argv)
{
	uint8_t addr[ADDR_LEN];
	uint8_t mask[ADDR_LEN];
	char str[48];
	int err;

	if (strcmp(argv[1], "all") == 0) {
		err = ignore_clear(bletracker_IgnoreClear_IGNORE_CLEAR_ALL,
				   bletracker_Event_Source_CONSOLE);
		if (err < 0) {
			shell_error(sh, "flash write failed");
			return err;
		}
		shell_print(sh, "%d rules removed", err);
		return 0;
	}
	if (!ignore_parse(argv[1], addr, mask)) {
		shell_error(sh, "usage: unignore <addr>[/bits|/mask] | all");
		return -EINVAL;
	}
	ignore_fmt(str, sizeof(str), addr, mask);
	err = ignore_del(addr, mask, bletracker_Event_Source_CONSOLE);
	if (err == -ENOENT) {
		shell_error(sh, "%s is not a rule (`ignore` lists them; the mask must match too)",
			    str);
	} else if (err) {
		shell_error(sh, "%s removed, but the flash write failed: back after a reboot", str);
	} else {
		shell_print(sh, "%s no longer ignored", str);
	}
	return err;
}

static int cmd_cmdlog(const struct shell *sh, size_t argc, char **argv)
{
	unsigned int n = MIN(cmd_bad_next, CMD_BAD_LOG);

	if (n == 0) {
		shell_print(sh, "no bad gateway commands since boot");
		return 0;
	}
	shell_print(sh, "last %u of %u bad frames (bytes before the 0x00, first %u kept):", n,
		    cmd_bad_next, CMD_BAD_SHOW);
	for (unsigned int i = cmd_bad_next - n; i < cmd_bad_next; i++) {
		struct cmd_bad e;
		char hex[2 * CMD_BAD_SHOW + 1];
		unsigned int key = irq_lock();

		e = cmd_bad_log[i % CMD_BAD_LOG];
		irq_unlock(key);
		bin2hex(e.b, e.len, hex, sizeof(hex));
		shell_print(sh, "  %7lld.%03lld s  %-15s  %s", e.t / 1000, e.t % 1000,
			    cmd_bad_names[e.reason], e.len ? hex : "(empty)");
	}
	return 0;
}

static int on_off_arg(const struct shell *sh, const char *arg, const char *usage)
{
	if (strcmp(arg, "on") == 0) {
		return 1;
	}
	if (strcmp(arg, "off") == 0) {
		return 0;
	}
	shell_error(sh, "usage: %s", usage);
	return -EINVAL;
}

static int cmd_ant(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		if (strcmp(argv[1], "ext") == 0) {
			antenna_set(true, bletracker_Event_Source_CONSOLE);
		} else if (strcmp(argv[1], "int") == 0) {
			antenna_set(false, bletracker_Event_Source_CONSOLE);
		} else {
			shell_error(sh, "usage: ant [int|ext]");
			return -EINVAL;
		}
	}
	shell_print(sh, "antenna: %s", ant_external ? "ext" : "int");
	return 0;
}

static int cmd_scan(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		int on = on_off_arg(sh, argv[1], "scan [on|off]");

		if (on < 0) {
			return on;
		}
		if (listen_set(on) != 0) {
			shell_error(sh, "scan %s failed", argv[1]);
			return -EIO;
		}
	}
	shell_print(sh, "listening %s", scanning ? "on" : "off");
	return 0;
}

static int cmd_active(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		int on = on_off_arg(sh, argv[1], "active [on|off]");

		if (on < 0) {
			return on;
		}
		if (active_set(on) != 0) {
			shell_error(sh, "scan restart failed");
			return -EIO;
		}
	}
	shell_print(sh, "scanning %s", scan_active ? "active" : "passive");
	return 0;
}

static int cmd_data(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		int on = on_off_arg(sh, argv[1], "data [on|off]");

		if (on < 0) {
			return on;
		}
		payloads_on = on;
	}
	shell_print(sh, "payload records %s", payloads_on ? "on" : "off");
	return 0;
}

static int cmd_budget(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		long v = strtol(argv[1], NULL, 10);

		if (v < 10 || v > 90) {
			shell_error(sh, "usage: budget [10-90]");
			return -EINVAL;
		}
		budget_pct = (uint8_t)v;
	}
	shell_print(sh, "budget %u%% of %u baud per %u ms tick = %u bytes", budget_pct,
		    uart_baud, TICK_MS, uart_baud / 10 * TICK_MS / 1000 * budget_pct / 100);
	return 0;
}

/* Takes effect at the next 1 s boundary (main thread) */
static int cmd_chan(const struct shell *sh, size_t argc, char **argv)
{
	const char *usage = "chan [auto|37|38|39|rot [1-31]]";

	if (argc > 1) {
		long v = strtol(argv[1], NULL, 10);

		if (strcmp(argv[1], "auto") == 0 && argc == 2) {
			chan_mode = CHAN_AUTO;
		} else if (v >= 37 && v <= 39 && argc == 2) {
			chan_fixed = (uint8_t)v;
			chan_mode = CHAN_FIXED;
		} else if (strcmp(argv[1], "rot") == 0) {
			long s = argc > 2 ? strtol(argv[2], NULL, 10) : 1;

			if (s < 1 || s > 31) {
				shell_error(sh, "usage: %s", usage);
				return -EINVAL;
			}
			chan_dwell = (uint8_t)s;
			chan_mode = CHAN_ROTATE;
		} else {
			shell_error(sh, "usage: %s", usage);
			return -EINVAL;
		}
	}
	switch (chan_mode) {
	case CHAN_FIXED:
		shell_print(sh, "channel %u only", chan_fixed);
		break;
	case CHAN_ROTATE:
		shell_print(sh, "channels 37-39, %u s each", chan_dwell);
		break;
	default:
		shell_print(sh, "channels auto (controller rotates 37-39)");
		break;
	}
	return 0;
}

static int cmd_flash(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		int on = on_off_arg(sh, argv[1], "flash [on|off]");

		if (on < 0) {
			return on;
		}
		if (flash_mode_set(on, FLASH_MODE_S, bletracker_Event_Source_CONSOLE, false) != 0) {
			shell_error(sh, "flash mode failed to start");
			return -EIO;
		}
	}
	return cmd_status(sh, 1, NULL);
}

static int cmd_reboot(const struct shell *sh, size_t argc, char **argv)
{
	shell_print(sh, "rebooting");
	k_sleep(K_MSEC(50));
	sys_reboot(SYS_REBOOT_COLD);
	return 0;
}

static int cmd_inject(const struct shell *sh, size_t argc, char **argv)
{
	uint8_t buf[CMD_ENC_MAX + 1];
	size_t n = hex2bin(argv[1], strlen(argv[1]), buf, sizeof(buf));

	if (n == 0) {
		shell_error(sh, "usage: inject <hex>, e.g. from tools/decode_frames.py --cmd");
		return -EINVAL;
	}
	for (size_t i = 0; i < n; i++) {
		cmd_rx_byte(buf[i]);
	}
	shell_print(sh, "%u bytes fed to the command decoder", n);
	return 0;
}

static int cmd_filter(const struct shell *sh, size_t argc, char **argv)
{
	if (strcmp(argv[1], "off") == 0) {
		filter_on = false;
		shell_print(sh, "filter off");
		return 0;
	}
	if (bt_addr_from_str(argv[1], &filter_addr) != 0) {
		shell_error(sh, "usage: filter AA:BB:CC:DD:EE:FF | off");
		return -EINVAL;
	}
	filter_on = true;
	shell_print(sh, "filter %s", argv[1]);
	return 0;
}

static int cmd_print(const struct shell *sh, size_t argc, char **argv)
{
	int on = on_off_arg(sh, argv[1], "print on|off");

	if (on < 0) {
		return on;
	}
	print_raw = on;
	return 0;
}

static int cmd_list(const struct shell *sh, size_t argc, char **argv)
{
	if (strcmp(argv[1], "on") == 0) {
		list_mode = LIST_TABLE;
	} else if (strcmp(argv[1], "csv") == 0) {
		list_mode = LIST_CSV;
	} else if (strcmp(argv[1], "off") == 0) {
		list_mode = LIST_OFF;
	} else {
		shell_error(sh, "usage: list on|csv|off");
		return -EINVAL;
	}
	return 0;
}

static int cmd_minrssi(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		long v = strtol(argv[1], NULL, 10);

		if (v < -127 || v > 20) {
			shell_error(sh, "usage: minrssi <-127..20>");
			return -EINVAL;
		}
		list_min_rssi = (int8_t)v;
	}
	shell_print(sh, "minrssi %d", list_min_rssi);
	return 0;
}

static int cmd_stream(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		if (strcmp(argv[1], "dump") != 0) {
			shell_error(sh, "usage: stream [dump]");
			return -EINVAL;
		}
		frame_dump = true;
	}
	shell_print(sh, "gateway uart21 (D6 TX): %s, buckets sent=%u skipped=%u seq=%u",
		    device_is_ready(gw_uart) ? "ready" : "NOT READY", buckets_sent,
		    buckets_skipped, tick_seq);
	return 0;
}

SHELL_CMD_ARG_REGISTER(status, NULL, "Version, settings, flash mode, stream", cmd_status, 1, 0);
SHELL_CMD_ARG_REGISTER(scan, NULL, "Show or start/stop listening: scan [on|off]", cmd_scan, 1, 1);
SHELL_CMD_ARG_REGISTER(active, NULL, "Active scanning (scan responses): active [on|off]",
		       cmd_active, 1, 1);
SHELL_CMD_ARG_REGISTER(data, NULL, "Payload records to the gateway: data [on|off]", cmd_data,
		       1, 1);
SHELL_CMD_ARG_REGISTER(budget, NULL, "Stream budget, % of the line: budget [10-90]",
		       cmd_budget, 1, 1);
SHELL_CMD_ARG_REGISTER(chan, NULL, "Primary channels scanned: chan [auto|37|38|39|rot [1-31]]",
		       cmd_chan, 1, 2);
SHELL_CMD_ARG_REGISTER(flash, NULL, "BLE update mode: flash [on|off]", cmd_flash, 1, 1);
SHELL_CMD_ARG_REGISTER(reboot, NULL, "Restart", cmd_reboot, 1, 0);
SHELL_CMD_ARG_REGISTER(inject, NULL, "Feed hex bytes to the D7 command decoder: inject <hex>",
		       cmd_inject, 2, 0);
SHELL_CMD_ARG_REGISTER(cmdlog, NULL, "Last rejected D7 command frames", cmd_cmdlog, 1, 0);
SHELL_CMD_ARG_REGISTER(stream, NULL, "Gateway buckets: stream [dump]", cmd_stream, 1, 1);
SHELL_CMD_ARG_REGISTER(list, NULL, "Per-device table each second: list on|csv|off", cmd_list,
		       2, 0);
SHELL_CMD_ARG_REGISTER(minrssi, NULL, "Hide weaker devices in the list: minrssi <dBm>",
		       cmd_minrssi, 1, 1);
SHELL_CMD_ARG_REGISTER(ant, NULL, "Show or set antenna: ant [int|ext]", cmd_ant, 1, 1);
SHELL_CMD_ARG_REGISTER(filter, NULL, "Track one address: filter <addr>|off", cmd_filter, 2, 0);
SHELL_CMD_ARG_REGISTER(print, NULL, "Raw advert lines: print on|off", cmd_print, 2, 0);
SHELL_CMD_ARG_REGISTER(ignore, NULL, ignore_usage, cmd_ignore, 1, 2);
SHELL_CMD_ARG_REGISTER(unignore, NULL, "Remove an ignore rule: unignore <addr>[/bits|/mask]|all",
		       cmd_unignore, 2, 0);

int main(void)
{
	struct adv_evt evt;
	int64_t next_tick;
	int64_t tick_start;
	uint32_t ticks = 0;
	int err;

	printk("\nbletracker scanner %s\n", APP_VERSION_STRING);
	k_msgq_init(&adv_q, adv_q_buf, sizeof(struct adv_evt), ADV_Q_LEN);
	k_msgq_init(&cmd_q, cmd_q_buf, sizeof(struct cmd_msg), 4);
	k_msgq_init(&event_q, event_q_buf, sizeof(bletracker_Event), EVENT_Q_LEN);
	k_work_init(&cmd_work, cmd_work_handler);
	k_work_init(&adv_work, adv_work_handler);

	if (hwinfo_get_device_id(chip_id, sizeof(chip_id)) != sizeof(chip_id)) {
		printk("chip ID: NOT READ, only commands to all will work\n");
	}
	bin2hex(chip_id, sizeof(chip_id), chip_id_str, sizeof(chip_id_str));
	printk("chip ID %s\n", chip_id_str);

	img_confirmed = boot_is_img_confirmed();
	printk("image: %s\n", img_confirmed ? "confirmed" :
	       "TEST, confirms after 60 s of scanning with flash mode working");

	if (led.port && gpio_is_ready_dt(&led)) {
		gpio_pin_configure_dt(&led, GPIO_OUTPUT_INACTIVE);
	}

	err = settings_subsys_init();
	if (err == 0) {
		err = settings_load_subtree("scanner");
	}
	printk("settings: %s\n", err ? "NOT LOADED" : "loaded");
	/* 0.4.x kept a sector claim; the sector is the gateway RX pin now */
	settings_delete("scanner/sector");
	boot_events();

	err = antenna_init();
	printk("rf switch: %s, antenna %s\n", err ? "NOT READY" : "on",
	       ant_external ? "ext" : "int");

	err = gw_uart_init();
	printk("gateway uart: %s, %u baud\n", err ? "NOT READY" : "uart21, D6 TX / D7 RX (commands)",
	       uart_baud);

	err = bt_enable(NULL);
	if (err) {
		printk("bt_enable failed (%d)\n", err);
		return 0;
	}

	err = listen_set(true);
	if (err) {
		printk("scan start failed (%d)\n", err);
		return 0;
	}
	printk("scanning: passive, 100%% duty, duplicates kept; buckets every %u ms, "
	       "payloads off\n", TICK_MS);

	if (img_confirmed) {
		printk("flash mode: off (serial command \"flash on\" opens it)\n");
	} else {
		err = flash_mode_set(true, FLASH_TEST_WINDOW_S,
				     bletracker_Event_Source_TEST_WINDOW, false);
		printk("flash mode: %s\n", err ? "FAILED to start" : "on for 2 min (test image)");
	}

	tick_start = k_uptime_get();
	next_tick = tick_start + TICK_MS;
	for (;;) {
		int64_t now = k_uptime_get();

		if (now >= next_tick) {
			tick_send(now, tick_start);
			tick_start = next_tick;
			next_tick += TICK_MS;
			if (++ticks % TICKS_PER_S == 0) {
				report_second();
				housekeeping(now);
				if (led.port) {
					gpio_pin_toggle_dt(&led);
				}
			}
			continue;
		}
		if (k_msgq_get(&adv_q, &evt, K_MSEC(next_tick - now)) == 0) {
			handle_adv(&evt);
		}
	}
}
