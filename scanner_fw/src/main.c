/*
 * Sector scanner:
 *   1. boots, prints a banner, blinks the LED once a second
 *   2. passive scan at 100% duty, duplicates kept, adverts to the USB console
 *   3. RF switch control so onboard vs external antenna can be compared
 *   4. 1 s aggregation per address: median/max RSSI, count, advertised 1 m power
 *   5. binary frame of that table each second on the header UART (D6 TX, D7 RX)
 *      to the gateway; format below and in the README. Each scanner's D6 has its
 *      own gateway RX pin (that pin is the sector); D7 is shared by all three
 *   6. commands from the gateway on D7 (listen, flash mode, antenna, sector, reboot),
 *      addressed by chip ID since every scanner hears them
 *   7. flash mode: connectable BLE with MCUmgr SMP so MCUboot images can be
 *      uploaded with the box sealed; only on a serial command (and for 2 min
 *      after an update, while the new image is on trial)
 *   8. sector ID and antenna kept in flash
 *
 * Shell commands:
 *   status                 version, chip ID, sector, antenna, listening, flash mode, image
 *   ant [int|ext]          show or switch antenna (saved in flash)
 *   sector [0-254]         show or set the sector ID (saved in flash)
 *   scan [on|off]          show or start/stop listening (always on after boot)
 *   flash [on|off]         show or enter/leave flash mode (on = 10 min)
 *   reboot                 restart
 *   inject <hex>           feed bytes to the D7 command decoder (bench test)
 *   filter <addr>|off      only track one address, print a 1 s summary for it
 *   print on|off           raw line per advert (off by default: floods)
 *   list on|csv|off        per-device table each second (csv = gateway line format)
 *   minrssi <dBm>          hide devices whose median is below this in the list
 *   stream [dump]          gateway frame stats; dump = hex of the next frame
 */

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

struct adv_evt {
	bt_addr_le_t addr;
	int8_t rssi;
	uint8_t type;
	int8_t tx_1m;
};

/* One second of adverts from one address, main thread only */
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
 * Gateway frame, one per second on uart21 (D6 TX, D7 RX), 115200 8N1.
 * Little-endian, COBS-encoded, each frame followed by a 0x00 delimiter.
 *   header (16): ver, sector, seq, flags, adverts (u16), n_devs, dropped,
 *                chip_id[8] (FICR device ID as hwinfo returns it, printed in that order)
 *                flags: bit0 external antenna, bit1 table was full,
 *                       bit2 listening stopped, bit3 flash mode,
 *                       bit4 update client connected, bit5 image not confirmed
 *   record (11): addr[6] (most significant first, as printed), flags,
 *                rssi_med, rssi_max, count, tx_1m
 *                flags: bit0 random address, bits1-3 adv type, bit4 tx_1m valid
 *   crc (2):     CRC-16/CCITT-FALSE (poly 0x1021, init 0xffff) of header + records
 * Counts saturate at their field size. Every device heard is sent (minrssi only
 * affects the console list), strongest median first. Frames keep coming with
 * listening stopped (no devices), so the gateway always sees the state.
 */
#define FRAME_VER 2
#define FRAME_HDR_LEN 16
#define FRAME_REC_LEN 11
#define FRAME_RAW_MAX (FRAME_HDR_LEN + MAX_DEVS * FRAME_REC_LEN + 2)
/* COBS adds one byte per 254, plus the delimiter */
#define FRAME_TX_MAX (FRAME_RAW_MAX + FRAME_RAW_MAX / 254 + 2)

static const struct device *const gw_uart = DEVICE_DT_GET(DT_NODELABEL(uart21));
static uint8_t frame_raw[FRAME_RAW_MAX];
static uint8_t frame_tx[FRAME_TX_MAX];
static volatile size_t frame_tx_len;
static volatile size_t frame_tx_pos;
static uint8_t frame_seq;
static uint32_t frames_sent;
static uint32_t frames_skipped; /* previous frame still going out */
static bool frame_dump;

/*
 * Gateway command, on uart21 RX (D7), same framing (COBS + 0x00, CRC-16). One gateway
 * TX drives all three scanners' D7, so each command names its target:
 *   ver (2), target[8], cmd, arg, crc (2, LE, of everything before it)
 *   target: a chip ID from a frame header, or all zeros for every scanner
 *           (not allowed for sector)
 *   cmd 1 listen   arg 0 stop, 1 start
 *   cmd 2 flash    arg 0 leave, 1 enter (10 min, extended by each enter)
 *   cmd 3 antenna  arg 0 onboard, 1 external (saved in flash)
 *   cmd 4 sector   arg 0-254 (saved in flash)
 *   cmd 5 reboot   arg 0xa5
 * There is no reply; the result shows in the next frame's header.
 */
#define CMD_VER 2
#define CHIP_ID_LEN 8
#define CMD_RAW_LEN (1 + CHIP_ID_LEN + 4)
#define CMD_ENC_MAX 16
#define CMD_REBOOT_MAGIC 0xa5

enum gw_cmd {
	CMD_LISTEN = 1,
	CMD_FLASH = 2,
	CMD_ANT = 3,
	CMD_SECTOR = 4,
	CMD_REBOOT = 5,
};

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
	BAD_VER,
	BAD_CRC,
	BAD_ARG,	/* unknown command or argument, or sector sent to all */
};
static const char *const cmd_bad_names[] = {
	"too long", "queue full", "bad COBS/length", "wrong version", "bad CRC", "bad cmd/arg",
};

struct cmd_bad {
	int64_t t;
	uint8_t reason;
	uint8_t len;
	uint8_t b[CMD_ENC_MAX];
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
	e->len = MIN(len, CMD_ENC_MAX);
	memcpy(e->b, b, e->len);
	irq_unlock(key);
	atomic_inc(&cmds_bad);
}

/*
 * Flash mode: connectable advertising as "bletracker-s<sector>" with the SMP
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
static char flash_name[16];
static bool flash_adv_ok;  /* flash mode advertising has started at least once */
static bool img_confirmed;

static const struct bt_data flash_ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, SMP_BT_SVC_UUID_VAL),
};

/*
 * Scan callback runs in the BT RX thread: queue and get out, print from main.
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
static uint8_t sector_id;
static uint8_t chip_id[CHIP_ID_LEN];
static char chip_id_str[2 * CHIP_ID_LEN + 1];
static bool filter_on;
static bt_addr_t filter_addr;

/* Per-second counters, main thread only */
static uint32_t sec_total;
static uint32_t sec_n;
static int32_t sec_sum;
static int8_t sec_min;
static int8_t sec_max;

/* Settings: "scanner/sector" and "scanner/ant", one byte each */
static int settings_set_cb(const char *key, size_t len, settings_read_cb read_cb, void *cb_arg)
{
	uint8_t v;

	if (len != 1 || read_cb(cb_arg, &v, 1) != 1) {
		return -EINVAL;
	}
	if (strcmp(key, "sector") == 0) {
		sector_id = v;
	} else if (strcmp(key, "ant") == 0) {
		ant_saved_external = v != 0;
	}
	return 0;
}

SETTINGS_STATIC_HANDLER_DEFINE(scanner, "scanner", NULL, settings_set_cb, NULL, NULL);

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

static void antenna_set(bool external)
{
	uint8_t v = external;

	antenna_select(external);
	settings_save_one("scanner/ant", &v, 1);
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

static int flash_adv_start(void);

static int sector_set(uint8_t id)
{
	sector_id = id;
	/* Re-advertise so the flash-mode name follows the new sector */
	if (flash_mode && smp_conn == NULL) {
		bt_le_adv_stop();
		flash_adv_start();
	}
	return settings_save_one("scanner/sector", &id, 1);
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
	bt_addr_le_copy(&evt.addr, addr);
	bt_data_parse(ad, ad_tx_cb, &evt.tx_1m);
	if (k_msgq_put(&adv_q, &evt, K_NO_WAIT) != 0) {
		atomic_inc(&dropped);
	}
}

static int scan_start(void)
{
	/* Interval == window: radio listens all the time. No duplicate filter. */
	struct bt_le_scan_param param = {
		.type = BT_LE_SCAN_TYPE_PASSIVE,
		.options = BT_LE_SCAN_OPT_NONE,
		.interval = 0x0030, /* 30 ms */
		.window = 0x0030,
	};

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

static int flash_adv_start(void)
{
	const struct bt_le_adv_param *param =
		BT_LE_ADV_PARAM(BT_LE_ADV_OPT_CONN, BT_GAP_ADV_FAST_INT_MIN_2,
				BT_GAP_ADV_FAST_INT_MAX_2, NULL);
	struct bt_data sd[1];
	int err;

	snprintk(flash_name, sizeof(flash_name), "bletracker-s%u", sector_id);
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

static int flash_mode_set(bool on, uint32_t secs)
{
	int err = 0;

	if (!on) {
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
		}
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
	printk("flash mode: %s connected\n", addr_str);
	smp_conn = bt_conn_ref(conn);
	if (!flash_mode) {
		bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
	}
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	printk("flash mode: client disconnected (0x%02x)\n", reason);
	if (smp_conn == conn) {
		bt_conn_unref(smp_conn);
		smp_conn = NULL;
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
	int err;

	if (!device_is_ready(gw_uart)) {
		return -ENODEV;
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

static const char *cmd_apply(uint8_t cmd, uint8_t arg)
{
	switch (cmd) {
	case CMD_LISTEN:
		if (arg > 1) {
			return NULL;
		}
		return listen_set(arg) ? "listen FAILED" : (arg ? "listen on" : "listen off");
	case CMD_FLASH:
		if (arg > 1) {
			return NULL;
		}
		return flash_mode_set(arg, FLASH_MODE_S) ? "flash FAILED" :
		       (arg ? "flash on" : "flash off");
	case CMD_ANT:
		if (arg > 1) {
			return NULL;
		}
		antenna_set(arg);
		return arg ? "ant ext" : "ant int";
	case CMD_SECTOR:
		if (arg == 0xff) {
			return NULL;
		}
		return sector_set(arg) ? "sector NOT SAVED" : "sector set";
	case CMD_REBOOT:
		if (arg != CMD_REBOOT_MAGIC) {
			return NULL;
		}
		printk("gateway command: reboot\n");
		k_sleep(K_MSEC(50));
		sys_reboot(SYS_REBOOT_COLD);
		return NULL;
	default:
		return NULL;
	}
}

/* Decode, check and run queued gateway commands (system workqueue) */
static void cmd_work_handler(struct k_work *work)
{
	struct cmd_msg m;

	ARG_UNUSED(work);

	while (k_msgq_get(&cmd_q, &m, K_NO_WAIT) == 0) {
		uint8_t raw[CMD_ENC_MAX];
		int len = cobs_decode(m.enc, m.len, raw, sizeof(raw));
		static const uint8_t all[CHIP_ID_LEN];
		const uint8_t *target = &raw[1];
		uint8_t cmd = raw[1 + CHIP_ID_LEN];
		uint8_t arg = raw[2 + CHIP_ID_LEN];
		bool to_all;
		const char *result;

		if (len != CMD_RAW_LEN) {
			cmd_bad_note(BAD_FRAME, m.enc, m.len);
			continue;
		}
		if (raw[0] != CMD_VER) {
			cmd_bad_note(BAD_VER, m.enc, m.len);
			continue;
		}
		if (crc16_itu_t(0xffff, raw, CMD_RAW_LEN - 2) !=
		    sys_get_le16(&raw[CMD_RAW_LEN - 2])) {
			cmd_bad_note(BAD_CRC, m.enc, m.len);
			continue;
		}
		to_all = memcmp(target, all, CHIP_ID_LEN) == 0;
		if (!to_all && memcmp(target, chip_id, CHIP_ID_LEN) != 0) {
			atomic_inc(&cmds_other);
			continue;
		}
		/* Every scanner would take the same sector */
		result = (to_all && cmd == CMD_SECTOR) ? NULL : cmd_apply(cmd, arg);
		if (result == NULL) {
			cmd_bad_note(BAD_ARG, m.enc, m.len);
			printk("gateway command %u arg %u%s rejected\n", cmd, arg,
			       to_all ? " (to all)" : "");
			continue;
		}
		atomic_inc(&cmds_ok);
		printk("gateway command: %s (%u)%s\n", result, arg, to_all ? " (to all)" : "");
	}
}

static void frame_send(uint32_t drops)
{
	uint8_t *p = frame_raw;
	size_t raw_len;
	size_t tx_len;

	if (!device_is_ready(gw_uart)) {
		return;
	}
	if (frame_tx_pos < frame_tx_len) {
		frames_skipped++;
		frame_seq++; /* the gateway sees the gap */
		return;
	}

	*p++ = FRAME_VER;
	*p++ = sector_id;
	*p++ = frame_seq++;
	*p++ = (ant_external ? BIT(0) : 0) | (devs_full ? BIT(1) : 0) |
	       (scanning ? 0 : BIT(2)) | (flash_mode ? BIT(3) : 0) |
	       (smp_conn != NULL ? BIT(4) : 0) | (img_confirmed ? 0 : BIT(5));
	sys_put_le16(MIN(sec_total, UINT16_MAX), p);
	p += 2;
	*p++ = n_devs;
	*p++ = MIN(drops, UINT8_MAX);
	memcpy(p, chip_id, CHIP_ID_LEN);
	p += CHIP_ID_LEN;

	for (uint8_t k = 0; k < n_devs; k++) {
		const struct dev_agg *d = &devs[order[k]];
		bool tx_valid = d->tx_1m != TX_UNKNOWN;

		for (int b = 5; b >= 0; b--) {
			*p++ = d->addr.a.val[b];
		}
		*p++ = (d->addr.type & 1) | ((d->adv_type & 0x7) << 1) | (tx_valid ? BIT(4) : 0);
		*p++ = (uint8_t)d->rssi_med;
		*p++ = (uint8_t)d->rssi_max;
		*p++ = MIN(d->count, UINT8_MAX);
		*p++ = tx_valid ? (uint8_t)d->tx_1m : 0;
	}

	raw_len = p - frame_raw;
	sys_put_le16(crc16_itu_t(0xffff, frame_raw, raw_len), p);
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
	frames_sent++;
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
			/* sector_id, address, addr_type, rssi_med, rssi_max, count, tx_1m */
			printk("%u,%s,%s,%d,%d,%u,%s\n", sector_id, addr_str,
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
	agg_add(evt);

	if (print_raw) {
		char addr_str[BT_ADDR_LE_STR_LEN];

		bt_addr_le_to_str(&evt->addr, addr_str, sizeof(addr_str));
		printk("%s rssi=%d type=%u\n", addr_str, evt->rssi, evt->type);
	}

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

/* Once a second: flash mode timeout, and confirming a test image */
static void housekeeping(int64_t now)
{
	if (flash_mode && smp_conn == NULL && now >= flash_until) {
		flash_mode_set(false, 0);
		printk("flash mode: off (timeout)\n");
	}

	if (!img_confirmed && now >= CONFIRM_AFTER_MS && scanning && flash_adv_ok) {
		if (boot_write_img_confirmed() == 0) {
			img_confirmed = true;
			printk("image confirmed\n");
		}
	}
}

static void report_second(void)
{
	uint32_t drops = (uint32_t)atomic_set(&dropped, 0);
	const char *ant = ant_external ? "ext" : "int";

	agg_finish();
	frame_send(drops);

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
		printk("[1s] ant=%s adverts=%u devices=%u dropped=%u%s%s\n", ant, sec_total,
		       n_devs, drops, scanning ? "" : " (listening off)",
		       flash_mode ? " (flash mode)" : "");
	}

	n_devs = 0;
	devs_full = 0;
	sec_total = 0;
	sec_n = 0;
	sec_sum = 0;
}

static int cmd_status(const struct shell *sh, size_t argc, char **argv)
{
	shell_print(sh, "version %s, image %s", APP_VERSION_STRING,
		    img_confirmed ? "confirmed" : "TEST (not confirmed yet)");
	shell_print(sh, "chip ID %s", chip_id_str);
	shell_print(sh, "sector %u, antenna %s, listening %s", sector_id,
		    ant_external ? "ext" : "int", scanning ? "on" : "off");
	if (flash_mode) {
		shell_print(sh, "flash mode on as %s, %s, %lld s left", flash_name,
			    smp_conn ? "client connected" : "advertising",
			    MAX(0, (flash_until - k_uptime_get()) / 1000));
	} else {
		shell_print(sh, "flash mode off");
	}
	shell_print(sh, "gateway commands: %u ok, %u bad (cmdlog shows them), %u for others",
		    (unsigned)atomic_get(&cmds_ok), (unsigned)atomic_get(&cmds_bad),
		    (unsigned)atomic_get(&cmds_other));
	shell_print(sh, "D7 line: %u bytes received, %u UART errors",
		    (unsigned)atomic_get(&cmd_rx_bytes), (unsigned)atomic_get(&cmd_rx_errors));
	return 0;
}

static int cmd_cmdlog(const struct shell *sh, size_t argc, char **argv)
{
	unsigned int n = MIN(cmd_bad_next, CMD_BAD_LOG);

	if (n == 0) {
		shell_print(sh, "no bad gateway commands since boot");
		return 0;
	}
	shell_print(sh, "last %u of %u bad frames (bytes before the 0x00, first %u kept):", n,
		    cmd_bad_next, CMD_ENC_MAX);
	for (unsigned int i = cmd_bad_next - n; i < cmd_bad_next; i++) {
		struct cmd_bad e;
		char hex[2 * CMD_ENC_MAX + 1];
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
			antenna_set(true);
		} else if (strcmp(argv[1], "int") == 0) {
			antenna_set(false);
		} else {
			shell_error(sh, "usage: ant [int|ext]");
			return -EINVAL;
		}
	}
	shell_print(sh, "antenna: %s", ant_external ? "ext" : "int");
	return 0;
}

static int cmd_sector(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		char *end;
		long v = strtol(argv[1], &end, 10);

		if (*end != '\0' || v < 0 || v > 254) {
			shell_error(sh, "usage: sector [0-254]");
			return -EINVAL;
		}
		if (sector_set((uint8_t)v) != 0) {
			shell_error(sh, "sector %ld NOT saved", v);
			return -EIO;
		}
	}
	shell_print(sh, "sector %u", sector_id);
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

static int cmd_flash(const struct shell *sh, size_t argc, char **argv)
{
	if (argc > 1) {
		int on = on_off_arg(sh, argv[1], "flash [on|off]");

		if (on < 0) {
			return on;
		}
		if (flash_mode_set(on, FLASH_MODE_S) != 0) {
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
	uint8_t buf[32];
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
	shell_print(sh, "gateway uart21 (D6 TX): %s, sent=%u skipped=%u seq=%u",
		    device_is_ready(gw_uart) ? "ready" : "NOT READY", frames_sent,
		    frames_skipped, frame_seq);
	return 0;
}

SHELL_CMD_ARG_REGISTER(status, NULL, "Version, settings, flash mode, image state", cmd_status,
		       1, 0);
SHELL_CMD_ARG_REGISTER(sector, NULL, "Show or set the sector ID: sector [0-254]", cmd_sector,
		       1, 1);
SHELL_CMD_ARG_REGISTER(scan, NULL, "Show or start/stop listening: scan [on|off]", cmd_scan, 1, 1);
SHELL_CMD_ARG_REGISTER(flash, NULL, "BLE update mode: flash [on|off]", cmd_flash, 1, 1);
SHELL_CMD_ARG_REGISTER(reboot, NULL, "Restart", cmd_reboot, 1, 0);
SHELL_CMD_ARG_REGISTER(inject, NULL, "Feed hex bytes to the D7 command decoder: inject <hex>",
		       cmd_inject, 2, 0);
SHELL_CMD_ARG_REGISTER(cmdlog, NULL, "Last rejected D7 command frames", cmd_cmdlog, 1, 0);
SHELL_CMD_ARG_REGISTER(stream, NULL, "Gateway frames: stream [dump]", cmd_stream, 1, 1);
SHELL_CMD_ARG_REGISTER(list, NULL, "Per-device table each second: list on|csv|off", cmd_list,
		       2, 0);
SHELL_CMD_ARG_REGISTER(minrssi, NULL, "Hide weaker devices in the list: minrssi <dBm>",
		       cmd_minrssi, 1, 1);
SHELL_CMD_ARG_REGISTER(ant, NULL, "Show or set antenna: ant [int|ext]", cmd_ant, 1, 1);
SHELL_CMD_ARG_REGISTER(filter, NULL, "Track one address: filter <addr>|off", cmd_filter, 2, 0);
SHELL_CMD_ARG_REGISTER(print, NULL, "Raw advert lines: print on|off", cmd_print, 2, 0);

int main(void)
{
	struct adv_evt evt;
	int64_t next;
	int err;

	printk("\nsector scanner %s\n", APP_VERSION_STRING);
	k_msgq_init(&adv_q, adv_q_buf, sizeof(struct adv_evt), ADV_Q_LEN);
	k_msgq_init(&cmd_q, cmd_q_buf, sizeof(struct cmd_msg), 4);
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
	printk("settings: %s, sector %u\n", err ? "NOT LOADED" : "loaded", sector_id);

	err = antenna_init();
	printk("rf switch: %s, antenna %s\n", err ? "NOT READY" : "on",
	       ant_external ? "ext" : "int");

	err = gw_uart_init();
	printk("gateway uart: %s\n", err ? "NOT READY" : "uart21, D6 TX / D7 RX (commands)");

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
	printk("scanning: passive, 100%% duty, duplicates kept\n");

	if (img_confirmed) {
		printk("flash mode: off (serial command \"flash on\" opens it)\n");
	} else {
		err = flash_mode_set(true, FLASH_TEST_WINDOW_S);
		printk("flash mode: %s\n", err ? "FAILED to start" : "on for 2 min (test image)");
	}

	next = k_uptime_get() + 1000;
	for (;;) {
		int64_t now = k_uptime_get();

		if (now >= next) {
			report_second();
			housekeeping(now);
			if (led.port) {
				gpio_pin_toggle_dt(&led);
			}
			next += 1000;
			continue;
		}
		if (k_msgq_get(&adv_q, &evt, K_MSEC(next - now)) == 0) {
			handle_adv(&evt);
		}
	}
}
