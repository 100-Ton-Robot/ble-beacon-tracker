#include "sector_scanner.h"
#include "pb_wire.h"

#include <algorithm>
#include <cctype>
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <sys/time.h>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "esphome/components/mqtt/mqtt_client.h"

namespace esphome {
namespace sector_scanner {

static const char *const TAG = "sector_scanner";

static const uint32_t STALE_MS = 3000;            /* buckets come every 200 ms */
static const uint32_t REPORT_MS = 60000;          /* repeat a wrong-chip problem this often */
static const uint32_t FIRMWARE_REPORT_MS = 600000;  /* repeat an outdated-firmware warning this often */
static const uint32_t IGNORE_LOG_MS = 10000;      /* debug log of locally ignored addresses */
static const size_t IGNORE_HITS_MAX = 32;         /* addresses tracked per report; the rest summed */
static const char *const IGNORE_LIST_MIN_FW = "0.7.0";  /* first scanner with ignore list readback */
static const uint32_t RECONCILE_MS = 60000;       /* re-check the scanner's settings this often */
static const uint32_t ACK_TIMEOUT_MS = 2000;      /* warn when a command isn't acked within this */
static const uint32_t WINDOW_MS = 10000;          /* throttle measurement window */
static const size_t QUEUE_MAX = 16;               /* the scanner itself queues only 4 commands */
static const uint32_t BUDGET_FLOOR = 30;          /* the gateway never pushes budget_pct below this */
static const uint32_t BUDGET_STEP = 10;
static const time_t CLOCK_VALID_AFTER = 1700000000;  /* before this SNTP hasn't set the clock */

/* Sector condition bits */
static const uint8_t COND_CHIP = 2;  /* chip isn't the expected one */

/* Retained per-sector state topics, in Sector::state_ order */
enum StateTopic : uint8_t {
  ST_CHIP,
  ST_VERSION,
  ST_LOAD,
  ST_FLASH,
  ST_ANT,
  ST_LISTENING,
  ST_CLIENT,
  ST_TEST_IMAGE,
  ST_ACTIVE,
  ST_PAYLOADS,
  ST_COUNT,
};
static const char *const STATE_NAMES[ST_COUNT] = {"chip",      "version", "load",       "flash",  "ant",
                                                  "listening", "client",  "test_image", "active", "payloads"};
/* Retained topics of earlier layouts (sector claims, gone with scanner 0.5.0); cleared at connect */
static const char *const LEGACY_STATES[] = {"scanner_sector", "claim"};

static const char *const CATEGORY_NAMES[] = {"GENERAL", "SECURITY", "LOAD", "COMMAND"};
static const char *const SEVERITY_NAMES[] = {"INFO", "WARN", "ERROR"};
static const char *const CODE_NAMES[] = {
    "UNKNOWN",         "BOOT",          "VERSION_CHANGED", "TEST_IMAGE",          "IMAGE_CONFIRMED", "FLASH_MODE_ON",
    "FLASH_MODE_OFF",  "CLIENT_CONNECTED", "CLIENT_DISCONNECTED", "SETTING_CHANGED", "CMD_OK",     "CMD_REJECTED",
    "BAD_COMMANDS",    "LOAD_LEVEL",    "14",              "EVENTS_LOST",
};
static const uint32_t CODE_BOOT = 1;
static const uint32_t CODE_CMD_OK = 10;
static const uint32_t CODE_CMD_REJECTED = 11;

static const char *const INTERVAL_NAMES[5] = {"rssi", "payload", "refresh", "status", "counters"};

template<size_t N> static std::string enum_name(const char *const (&names)[N], uint32_t v) {
  return v < N ? names[v] : std::to_string(v);
}

/* ---------------------------------------------------------------- framing */

static uint16_t crc16_ccitt_false(const uint8_t *data, size_t len) {
  uint16_t crc = 0xffff;
  for (size_t i = 0; i < len; i++) {
    crc ^= (uint16_t) data[i] << 8;
    for (int b = 0; b < 8; b++)
      crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

static std::string cobs_encode(const std::string &in) {
  std::string out(1, '\0');
  size_t code_at = 0;
  uint8_t code = 1;
  for (char ch : in) {
    if (ch == '\0') {
      out[code_at] = (char) code;
      code_at = out.size();
      out.push_back('\0');
      code = 1;
      continue;
    }
    out.push_back(ch);
    if (++code == 0xff) {
      out[code_at] = (char) code;
      code_at = out.size();
      out.push_back('\0');
      code = 1;
    }
  }
  out[code_at] = (char) code;
  return out;
}

/* ---------------------------------------------------------------- text helpers */

static const char HEX[] = "0123456789abcdef";

static std::string to_hex(const uint8_t *p, size_t len) {
  std::string s;
  s.reserve(2 * len);
  for (size_t i = 0; i < len; i++) {
    s.push_back(HEX[p[i] >> 4]);
    s.push_back(HEX[p[i] & 15]);
  }
  return s;
}

/* "AA:BB:CC:DD:EE:FF" (sep ':') or "AABBCCDDEEFF" (sep 0) */
static std::string addr_str(const uint8_t *p, size_t len, char sep) {
  static const char UP[] = "0123456789ABCDEF";
  std::string s;
  for (size_t i = 0; i < len; i++) {
    if (sep && i)
      s.push_back(sep);
    s.push_back(UP[p[i] >> 4]);
    s.push_back(UP[p[i] & 15]);
  }
  return s;
}

/* Strict UTF-8 (as Python's decoder): no overlongs, surrogates or > U+10FFFF */
static bool utf8_valid(const uint8_t *p, size_t n) {
  size_t i = 0;
  while (i < n) {
    uint8_t c = p[i];
    if (c < 0x80) {
      i++;
      continue;
    }
    size_t len;
    uint32_t cp;
    if (c >= 0xc2 && c <= 0xdf) {
      len = 2, cp = c & 0x1f;
    } else if (c >= 0xe0 && c <= 0xef) {
      len = 3, cp = c & 0x0f;
    } else if (c >= 0xf0 && c <= 0xf4) {
      len = 4, cp = c & 0x07;
    } else {
      return false;
    }
    if (i + len > n)
      return false;
    for (size_t k = 1; k < len; k++) {
      if ((p[i + k] & 0xc0) != 0x80)
        return false;
      cp = (cp << 6) | (p[i + k] & 0x3f);
    }
    if (len == 3 && (cp < 0x800 || (cp >= 0xd800 && cp <= 0xdfff)))
      return false;
    if (len == 4 && (cp < 0x10000 || cp > 0x10ffff))
      return false;
    i += len;
  }
  return true;
}

/* Small JSON writer: escaping matches Python's json.dumps(ensure_ascii=False) */
class J {
 public:
  std::string s;
  J() { this->s.reserve(256); }
  J &obj() {
    this->item_();
    this->s += '{';
    this->first_[++this->d_] = true;
    return *this;
  }
  J &arr() {
    this->item_();
    this->s += '[';
    this->first_[++this->d_] = true;
    return *this;
  }
  J &end_obj() {
    this->s += '}';
    this->d_--;
    return *this;
  }
  J &end_arr() {
    this->s += ']';
    this->d_--;
    return *this;
  }
  J &k(const char *key) {
    this->comma_();
    this->s += '"';
    this->s += key;
    this->s += "\":";
    this->pending_ = true;
    return *this;
  }
  J &i(int64_t v) {
    char b[24];
    snprintf(b, sizeof(b), "%lld", (long long) v);
    return this->raw(b);
  }
  J &b(bool v) { return this->raw(v ? "true" : "false"); }
  J &null() { return this->raw("null"); }
  J &raw(const char *r) {
    this->item_();
    this->s += r;
    return *this;
  }
  J &raw(const std::string &r) { return this->raw(r.c_str()); }
  J &str(const std::string &v) { return this->str((const uint8_t *) v.data(), v.size()); }
  J &str(const uint8_t *p, size_t len) {
    this->item_();
    this->s += '"';
    for (size_t n = 0; n < len; n++) {
      uint8_t c = p[n];
      switch (c) {
        case '"':
          this->s += "\\\"";
          break;
        case '\\':
          this->s += "\\\\";
          break;
        case '\n':
          this->s += "\\n";
          break;
        case '\r':
          this->s += "\\r";
          break;
        case '\t':
          this->s += "\\t";
          break;
        case '\b':
          this->s += "\\b";
          break;
        case '\f':
          this->s += "\\f";
          break;
        default:
          if (c < 0x20) {
            char u[8];
            snprintf(u, sizeof(u), "\\u%04x", c);
            this->s += u;
          } else {
            this->s += (char) c;
          }
      }
    }
    this->s += '"';
    return *this;
  }
  /* A name from an advert: kept as is if valid UTF-8, else every non-ASCII byte becomes '?' */
  J &name(const uint8_t *p, size_t len) {
    if (utf8_valid(p, len))
      return this->str(p, len);
    std::string t((const char *) p, len);
    for (auto &c : t)
      if ((uint8_t) c >= 0x80)
        c = '?';
    return this->str(t);
  }
  J &hex(const uint8_t *p, size_t len) { return this->str(to_hex(p, len)); }

 protected:
  void comma_() {
    if (!this->first_[this->d_])
      this->s += ',';
    this->first_[this->d_] = false;
  }
  void item_() {
    if (this->pending_) {
      this->pending_ = false;
      return;
    }
    this->comma_();
  }
  bool first_[8]{true, true, true, true, true, true, true, true};
  int d_{0};
  bool pending_{false};
};

/* sum / count to one decimal, half away from zero, in integers (no printf rounding differences) */
static std::string mean1(int32_t sum, uint32_t count) {
  if (count == 0)
    return "null";
  int64_t num = (int64_t) sum * 10;
  bool neg = num < 0;
  uint64_t a = neg ? (uint64_t) -num : (uint64_t) num;
  uint64_t q = (2 * a + count) / (2 * (uint64_t) count);
  char b[32];
  snprintf(b, sizeof(b), "%s%llu.%llu", (neg && q) ? "-" : "", (unsigned long long) (q / 10),
           (unsigned long long) (q % 10));
  return b;
}

static std::string uuid_str(const uint8_t *p, size_t len) {
  char b[40];
  if (len == 2) {
    snprintf(b, sizeof(b), "0x%04x", p[0] | (p[1] << 8));
  } else if (len == 4) {
    snprintf(b, sizeof(b), "0x%08" PRIx32, (uint32_t) (p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t) p[3] << 24)));
  } else {
    uint8_t r[16];
    for (int i = 0; i < 16; i++)
      r[i] = p[15 - i];
    std::string h = to_hex(r, 16);
    snprintf(b, sizeof(b), "%s-%s-%s-%s-%s", h.substr(0, 8).c_str(), h.substr(8, 4).c_str(), h.substr(12, 4).c_str(),
             h.substr(16, 4).c_str(), h.substr(20, 12).c_str());
  }
  return b;
}

/* ---------------------------------------------------------------- commands */

static std::string trim_lower(const std::string &in) {
  std::string p;
  for (char c : in)
    p += (char) tolower((unsigned char) c);
  while (!p.empty() && isspace((unsigned char) p.back()))
    p.pop_back();
  while (!p.empty() && isspace((unsigned char) p.front()))
    p.erase(0, 1);
  return p;
}

static bool parse_uint(const std::string &s, uint32_t &out) {
  if (s.empty() || s.size() > 9)
    return false;
  out = 0;
  for (char c : s) {
    if (!isdigit((unsigned char) c))
      return false;
    out = out * 10 + (c - '0');
  }
  return true;
}

/* MQTT payload: plain text, or JSON {"cmd": "<text>"} */
static std::string command_text(const std::string &payload) {
  std::string p = trim_lower(payload);
  if (p.empty() || p[0] != '{')
    return p;
  size_t k = p.find("\"cmd\"");
  if (k == std::string::npos)
    return "";
  size_t q = p.find('"', p.find(':', k + 5) + 1);
  if (q == std::string::npos)
    return "";
  size_t e = p.find('"', q + 1);
  return e == std::string::npos ? "" : trim_lower(p.substr(q + 1, e - q - 1));
}

/* "aa:bb:cc:dd:ee:ff" with any byte "*" (mask byte 0); end of the parsed text or npos */
static size_t parse_addr6(const std::string &s, size_t i, uint8_t *v, uint8_t *m) {
  for (size_t b = 0; b < ADDR_LEN; b++) {
    if (i < s.size() && s[i] == '*') {
      v[b] = 0, m[b] = 0, i++;
    } else if (i + 1 < s.size() && isxdigit((unsigned char) s[i]) && isxdigit((unsigned char) s[i + 1])) {
      v[b] = (uint8_t) strtoul(s.substr(i, 2).c_str(), nullptr, 16), m[b] = 0xff, i += 2;
    } else {
      return std::string::npos;
    }
    if (b < ADDR_LEN - 1 && (i >= s.size() || s[i++] != ':'))
      return std::string::npos;
  }
  return i;
}

/* Ignore rule, the same forms as the scanner's console: <addr>[/<bits 1-48>|/<mask>], "*" bytes.
 * addr comes back masked; false if malformed or the mask is all zeros. */
static bool parse_rule(const std::string &s, uint8_t *addr, uint8_t *mask) {
  size_t i = parse_addr6(s, 0, addr, mask);
  if (i == std::string::npos || (i < s.size() && s[i] != '/'))
    return false;
  if (i < s.size()) {
    std::string m = s.substr(i + 1);
    uint8_t m2[ADDR_LEN], wild[ADDR_LEN];
    if (m.find(':') != std::string::npos) {
      if (parse_addr6(m, 0, m2, wild) != m.size())
        return false;
      for (uint8_t x : wild)
        if (x == 0)
          return false;
    } else {
      uint32_t bits;
      if (!parse_uint(m, bits) || bits < 1 || bits > 8 * ADDR_LEN)
        return false;
      for (size_t b = 0; b < ADDR_LEN; b++) {
        int n = (int) bits - 8 * (int) b;
        n = n < 0 ? 0 : n > 8 ? 8 : n;
        m2[b] = (uint8_t) (0xff00 >> n);
      }
    }
    for (size_t b = 0; b < ADDR_LEN; b++)
      mask[b] &= m2[b];
  }
  bool any = false;
  for (size_t b = 0; b < ADDR_LEN; b++) {
    addr[b] &= mask[b];
    any |= mask[b] != 0;
  }
  return any;
}

bool parse_ignore_rule(const std::string &text, IgnoreRule &rule) {
  return parse_rule(trim_lower(text), rule.addr, rule.mask);
}

bool parse_command(const std::string &text, Command &c, std::string &err) {
  std::vector<std::string> w;
  std::string cur;
  for (char ch : trim_lower(text)) {
    if (isspace((unsigned char) ch)) {
      if (!cur.empty())
        w.push_back(cur), cur.clear();
    } else {
      cur += ch;
    }
  }
  if (!cur.empty())
    w.push_back(cur);
  if (w.empty()) {
    err = "empty command";
    return false;
  }
  c.text.clear();
  for (size_t i = 0; i < w.size(); i++)
    c.text += (i ? " " : "") + w[i];
  const std::string &name = w[0];
  const std::string arg = w.size() > 1 ? w[1] : "";
  auto on_off = [&](uint8_t action) {
    if (w.size() != 2 || (arg != "on" && arg != "off")) {
      err = name + " needs on or off";
      return false;
    }
    c.action = action;
    c.arg = arg == "on";
    return true;
  };

  if (name == "listen")
    return on_off(ACT_LISTEN);
  if (name == "flash")
    return on_off(ACT_FLASH);
  if (name == "payloads")
    return on_off(ACT_PAYLOADS);
  if (name == "active")
    return on_off(ACT_ACTIVE_SCAN);
  if (name == "ant") {
    if (w.size() != 2 || (arg != "int" && arg != "ext")) {
      err = "ant needs int or ext";
      return false;
    }
    c.action = ACT_EXT_ANTENNA;
    c.arg = arg == "ext";
    return true;
  }
  if (name == "reboot" && w.size() == 1) {
    c.action = ACT_REBOOT;
    c.arg = REBOOT_ARG;
    return true;
  }
  if (name == "budget") {
    uint32_t v;
    if (w.size() != 2 || !parse_uint(arg, v) || v < 10 || v > 90) {
      err = "budget needs 10-90";
      return false;
    }
    c.action = ACT_BUDGET;
    c.arg = v;
    return true;
  }
  if (name == "ignore" && w.size() == 2 && arg == "list") {
    c.action = ACT_IGNORE_LIST;
    c.arg = 1;
    return true;
  }
  if (name == "ignore" && w.size() == 3 && arg == "clear") {
    static const char *const KINDS[] = {"boot", "saved", "all"};
    for (uint32_t k = 0; k < 3; k++)
      if (w[2] == KINDS[k]) {
        c.action = ACT_IGNORE_CLEAR;
        c.arg = k + 1;
        return true;
      }
    err = "ignore clear needs boot, saved or all";
    return false;
  }
  if (name == "ignore" || name == "unignore") {
    bool ignore = name == "ignore";
    if (w.size() < 2 || w.size() > (ignore ? 3u : 2u) || (w.size() == 3 && w[2] != "save") ||
        !parse_rule(arg, c.addr, c.mask)) {
      err = ignore ? "ignore takes <addr>[/bits|/mask] [save] (* for any byte), or clear boot|saved|all"
                   : "unignore takes <addr>[/bits|/mask], as the scanner lists it";
      return false;
    }
    c.action = ignore ? ACT_IGNORE : ACT_UNIGNORE;
    c.arg = w.size() == 3;
    return true;
  }
  if (name == "intervals" && w.size() > 1) {
    c.action = ACT_INTERVALS;
    c.intervals = Intervals{};
    for (size_t i = 1; i < w.size(); i++) {
      size_t eq = w[i].find('=');
      uint32_t v;
      int idx = -1;
      for (int n = 0; n < 5 && eq != std::string::npos; n++)
        if (w[i].compare(0, eq, INTERVAL_NAMES[n]) == 0)
          idx = n;
      if (idx < 0 || !parse_uint(w[i].substr(eq + 1), v)) {
        err = "intervals takes rssi=N payload=N refresh=N status=N counters=N";
        return false;
      }
      uint32_t max = (idx == 2 || idx == 4) ? 3000 : 50;
      if (v < 1 || v > max) {
        err = std::string(INTERVAL_NAMES[idx]) + " interval must be 1-" + std::to_string(max);
        return false;
      }
      c.intervals.v[idx] = v;
    }
    return true;
  }
  err = "unknown command '" + text + "'";
  return false;
}

std::string encode_command(const Command &c) {
  pb::Writer w;
  bool any = false;
  for (uint8_t b : c.target)
    any |= b != 0;
  if (!c.all && any)
    w.bytes(1, c.target, CHIP_ID_LEN);
  if (c.seq)
    w.u32(2, c.seq);
  switch (c.action) {
    case ACT_LISTEN:
    case ACT_FLASH:
    case ACT_EXT_ANTENNA:
    case ACT_PAYLOADS:
    case ACT_ACTIVE_SCAN:
    case ACT_IGNORE_LIST:
      w.boolean(c.action, c.arg != 0); /* a oneof member is sent even when false */
      break;
    case ACT_INTERVALS: {
      pb::Writer sub;
      for (int i = 0; i < 5; i++)
        if (c.intervals.v[i])
          sub.u32(i + 1, c.intervals.v[i]);
      w.message(ACT_INTERVALS, sub);
      break;
    }
    case ACT_IGNORE:
    case ACT_UNIGNORE: {
      pb::Writer sub;
      bool exact = true;
      for (uint8_t m : c.mask)
        exact &= m == 0xff;
      sub.bytes(1, c.addr, ADDR_LEN);
      if (!exact)
        sub.bytes(2, c.mask, ADDR_LEN); /* left out = this address only */
      if (c.action == ACT_IGNORE && c.arg)
        sub.boolean(3, true);
      w.message(c.action, sub);
      break;
    }
    default:
      w.u32(c.action, c.arg);
  }
  uint16_t crc = crc16_ccitt_false((const uint8_t *) w.out.data(), w.out.size());
  w.out.push_back((char) (crc & 0xff));
  w.out.push_back((char) (crc >> 8));
  std::string f = cobs_encode(w.out);
  f.push_back('\0');
  return f;
}

static bool same_command(const Command &a, const Command &b) {
  return a.all == b.all && (a.all || memcmp(a.target, b.target, CHIP_ID_LEN) == 0) && a.action == b.action &&
         a.arg == b.arg && memcmp(a.intervals.v, b.intervals.v, sizeof(a.intervals.v)) == 0 &&
         memcmp(a.addr, b.addr, ADDR_LEN) == 0 && memcmp(a.mask, b.mask, ADDR_LEN) == 0;
}

/* ---------------------------------------------------------------- Sector */

void Sector::set_expected_chip(const std::string &hex) {
  for (size_t i = 0; i < CHIP_ID_LEN && 2 * i + 1 < hex.size(); i++)
    this->expected_[i] = (uint8_t) strtoul(hex.substr(2 * i, 2).c_str(), nullptr, 16);
  this->have_expected_ = true;
}

std::string Sector::chip_hex_() const { return to_hex(this->chip_, CHIP_ID_LEN); }

std::string Sector::topic_(const char *suffix) const {
  return this->hub_->prefix() + "/" + std::to_string(this->pin_) + "/" + suffix;
}

void Sector::log_config() {
  ESP_LOGCONFIG(TAG, "  Sector %u (RX pin), expected chip: %s", this->pin_,
                this->have_expected_ ? to_hex(this->expected_, CHIP_ID_LEN).c_str() : "any");
  LOG_SENSOR("    ", "Load", this->load_sensor_);
  LOG_SENSOR("    ", "Lost buckets", this->lost_sensor_);
  LOG_SENSOR("    ", "Bad frames", this->bad_sensor_);
  LOG_SENSOR("    ", "Devices", this->devices_sensor_);
  LOG_SENSOR("    ", "Ignored", this->ignored_sensor_);
  LOG_BINARY_SENSOR("    ", "Wrong chip", this->wrong_chip_sensor_);
  LOG_BINARY_SENSOR("    ", "Firmware outdated", this->firmware_outdated_sensor_);
  LOG_TEXT_SENSOR("    ", "Chip", this->chip_sensor_);
  LOG_TEXT_SENSOR("    ", "Firmware", this->firmware_sensor_);
}

void Sector::poll() {
  uint8_t buf[128];
  size_t avail = this->available();
  /* The driver doesn't report overruns here; a buffer three quarters full is the warning sign */
  if (avail >= this->parent_->get_rx_buffer_size() * 3 / 4) {
    this->rx_high_++;
    this->rx_high_window_++;
  }
  while ((avail = this->available()) > 0) {
    size_t n = std::min(avail, sizeof(buf));
    if (!this->read_array(buf, n))
      break;
    for (size_t i = 0; i < n; i++) {
      uint8_t b = buf[i];
      if (b == 0x00) {
        if (this->overflow_)
          this->bad_frame_("longer than the buffer", this->enc_len_);
        else if (this->enc_len_ > 0)
          this->handle_encoded(this->enc_, this->enc_len_);
        this->enc_len_ = 0;
        this->overflow_ = false;
      } else if (this->enc_len_ < BUCKET_ENC_MAX) {
        this->enc_[this->enc_len_++] = b;
      } else {
        this->overflow_ = true;
      }
    }
  }

  if (this->last_bucket_ms_ != 0 && millis() - this->last_bucket_ms_ > STALE_MS) {
    ESP_LOGW(TAG, "Sector %u: no bucket for %" PRIu32 " s", this->pin_, STALE_MS / 1000);
    this->last_bucket_ms_ = 0;
    this->have_seq_ = false;
    this->needs_settings_ = true;
    this->publish_online_(false); /* the other retained state stays as last known */
  }
}

/* COBS-decode into raw_ and check the CRC; body = protobuf length */
bool Sector::decode_(const uint8_t *enc, size_t len, size_t &body) {
  size_t i = 0, o = 0;
  while (i < len) {
    uint8_t code = enc[i];
    if (code == 0 || i + code > len)
      return false;
    for (size_t k = 1; k < code; k++) {
      if (o >= BUCKET_RAW_MAX)
        return false;
      this->raw_[o++] = enc[i + k];
    }
    i += code;
    if (code < 0xff && i < len) {
      if (o >= BUCKET_RAW_MAX)
        return false;
      this->raw_[o++] = 0x00;
    }
  }
  if (o < 3)
    return false;
  body = o - 2;
  uint16_t crc = this->raw_[body] | (this->raw_[body + 1] << 8);
  return crc16_ccitt_false(this->raw_, body) == crc;
}

void Sector::bad_frame_(const char *why, size_t len) {
  this->bad_++;
  /* The first frame after a reset is usually partial: not a sign of trouble on its own */
  if (this->online())
    this->bad_window_++;
  if (!this->hub_->capturing())
    ESP_LOGW(TAG, "Sector %u: bad frame (%u bytes, %s) dropped", this->pin_, (unsigned) len, why);
  if (this->bad_sensor_ != nullptr)
    this->bad_sensor_->publish_state(this->bad_);
}

/* A record is usable if it and its known sub-message parse; else the whole bucket is dropped
 * (as a protobuf parser would) */
static bool record_well_formed(const pb::Field &rec) {
  pb::Reader r(rec);
  pb::Field f;
  while (r.next(f))
    if (f.num >= 1 && f.num <= 6 && f.wt == pb::LEN && !pb::well_formed(f.p, f.len))
      return false;
  return r.ok();
}

void Sector::handle_encoded(const uint8_t *enc, size_t len) {
  size_t body;
  if (!this->decode_(enc, len, body)) {
    this->bad_frame_("COBS or CRC", len);
    return;
  }

  /* Pass 1: the bucket header, and check every record parses */
  uint8_t chip[CHIP_ID_LEN] = {};
  uint32_t seq = 0, t_ms = 0, tick_ms = 0, chan = 0, load = 0;
  {
    pb::Reader r(this->raw_, body);
    pb::Field f;
    while (r.next(f)) {
      if (f.num == 1 && f.wt == pb::LEN) {
        memcpy(chip, f.p, std::min(f.len, CHIP_ID_LEN));
      } else if (f.num >= 3 && f.num <= 7 && f.wt == pb::VARINT) {
        /* field 2 was the sector claim (scanner 0.4.x), reserved since 0.5.0 */
        uint32_t *dst[] = {&seq, &t_ms, &tick_ms, &chan, &load};
        *dst[f.num - 3] = f.u32();
      } else if (f.num == 15 && f.wt == pb::LEN && !record_well_formed(f)) {
        this->bad_frame_("protobuf", len);
        return;
      }
    }
    if (!r.ok()) {
      this->bad_frame_("protobuf", len);
      return;
    }
  }

  uint32_t now = millis();
  bool capturing = this->hub_->capturing();
  char t[24];
  this->hub_->now_json(t, sizeof(t));

  /* Chip: re-learned every bucket, so a swapped board shows up */
  if (!this->have_chip_ || memcmp(chip, this->chip_, CHIP_ID_LEN) != 0) {
    std::string old = this->have_chip_ ? this->chip_hex_() : "";
    memcpy(this->chip_, chip, CHIP_ID_LEN);
    this->have_chip_ = true;
    this->have_seq_ = false;
    this->needs_settings_ = true;
    this->have_ignore_ = false;
    if (!old.empty())
      this->hub_->event(this->pin_, this->chip_, false, CAT_SECURITY, SEV_WARN, "CHIP_CHANGED", 0, 0, 0,
                        "chip " + this->chip_hex_() + " replaced " + old, t);
    else if (!capturing)
      ESP_LOGI(TAG, "Sector %u: scanner chip %s", this->pin_, this->chip_hex_().c_str());
    if (this->chip_sensor_ != nullptr)
      this->chip_sensor_->publish_state(this->chip_hex_());
  }

  /* Lost buckets: seq is the tick count since the scanner booted */
  if (this->have_seq_ && seq > this->last_seq_) {
    uint32_t gap = seq - this->last_seq_ - 1;
    if (gap) {
      this->lost_ += gap;
      if (!capturing)
        ESP_LOGW(TAG, "Sector %u: %" PRIu32 " bucket(s) lost", this->pin_, gap);
      if (this->lost_sensor_ != nullptr)
        this->lost_sensor_->publish_state(this->lost_);
    }
  }
  this->have_seq_ = true;
  this->last_seq_ = seq;
  if (this->last_bucket_ms_ == 0) {
    if (!capturing)
      ESP_LOGI(TAG, "Sector %u: receiving buckets", this->pin_);
    this->publish_online_(true);
  }
  this->last_bucket_ms_ = now ? now : 1;
  this->seq_ = seq;
  this->tick_ms_ = tick_ms;

  this->validate_();

  if ((int32_t) load != this->load_) {
    if (!capturing && !(this->load_ < 0 && load == 0)) {
      if (load >= 4)
        ESP_LOGE(TAG, "Sector %u: scanner load level %" PRIu32 " (RSSI trimmed)", this->pin_, load);
      else if (load > 0)
        ESP_LOGW(TAG, "Sector %u: scanner load level %" PRIu32, this->pin_, load);
      else
        ESP_LOGI(TAG, "Sector %u: scanner load back to 0", this->pin_);
    }
    this->load_ = (int32_t) load;
    if (this->load_sensor_ != nullptr)
      this->load_sensor_->publish_state(load);
  }
  this->set_state_(ST_CHIP, this->chip_hex_());
  this->set_state_(ST_LOAD, std::to_string(load));

  /* Pass 2: records in order; RSSI is batched into one message at the end */
  this->rssi_.clear();
  this->any_rssi_ = false;
  {
    pb::Reader r(this->raw_, body);
    pb::Field f;
    while (r.next(f))
      if (f.num == 15 && f.wt == pb::LEN)
        this->handle_record_(f.p, f.len, t);
  }

  uint32_t rssi_interval = this->have_status_ ? this->reported_.intervals.v[0] : 1;
  if (this->any_rssi_ || rssi_interval == 1) {
    J j;
    j.obj().k("t").raw(t).k("seq").i(seq).k("t_ms").i(t_ms).k("tick_ms").i(tick_ms).k("chan").i(chan);
    j.k("load").i(load).k("chip").str(this->chip_hex_()).k("suspect").b(this->suspect_);
    j.k("devs").raw("[" + this->rssi_ + "]").end_obj();
    this->hub_->publish(this->topic_("rssi"), j.s, false);
  }
}

/* Expected chip, on every bucket. The sector is the RX pin: scanners have no claim since 0.5.0 */
void Sector::validate_() {
  uint8_t cond = 0;
  if (this->have_expected_ && memcmp(this->chip_, this->expected_, CHIP_ID_LEN) != 0)
    cond |= COND_CHIP;
  bool suspect = cond & COND_CHIP;

  uint32_t now = millis();
  this->suspect_ = suspect;
  if (cond != this->cond_) {
    bool was = this->cond_ != 0;
    this->cond_ = cond;
    this->cond_ms_ = now;
    if (cond) {
      this->report_condition_();
    } else if (was) {
      char t[24];
      this->hub_->now_json(t, sizeof(t));
      this->hub_->event(this->pin_, this->chip_, false, CAT_SECURITY, SEV_INFO, "CHIP_OK", 0, this->pin_, 0,
                        "expected chip back", t);
    }
    if (this->wrong_chip_sensor_ != nullptr)
      this->wrong_chip_sensor_->publish_state(suspect);
  } else if (cond && now - this->cond_ms_ >= REPORT_MS) {
    this->cond_ms_ = now;
    this->report_condition_();
  }
  if (this->wrong_chip_sensor_ != nullptr && !this->wrong_chip_sensor_->has_state())
    this->wrong_chip_sensor_->publish_state(suspect);
}

void Sector::report_condition_() {
  char t[24];
  this->hub_->now_json(t, sizeof(t));
  if (this->cond_ & COND_CHIP)
    this->hub_->event(this->pin_, this->chip_, false, CAT_SECURITY, SEV_ERROR, "CHIP_MISMATCH", 0, this->pin_, 0,
                      "expected chip " + to_hex(this->expected_, CHIP_ID_LEN), t);
}

/* "0.6.0" style versions, numerically; missing parts are 0, anything after the numbers ignored */
static int compare_versions(const std::string &a, const std::string &b) {
  size_t i = 0, j = 0;
  for (int part = 0; part < 3; part++) {
    uint32_t x = 0, y = 0;
    while (i < a.size() && isdigit((unsigned char) a[i]))
      x = x * 10 + (a[i++] - '0');
    while (j < b.size() && isdigit((unsigned char) b[j]))
      y = y * 10 + (b[j++] - '0');
    if (x != y)
      return x < y ? -1 : 1;
    if (i < a.size() && a[i] == '.')
      i++;
    if (j < b.size() && b[j] == '.')
      j++;
  }
  return 0;
}

/* Scanner firmware against scanner_firmware (the latest this gateway knows), on every status:
 * older = FIRMWARE_OUTDATED warning, repeated every 10 min; newer = one FIRMWARE_NEWER info;
 * back to the latest after being older = FIRMWARE_OK */
void Sector::check_firmware_(const std::string &version, const char *t) {
  bool changed = version != this->version_;
  if (changed) {
    this->version_ = version;
    if (this->firmware_sensor_ != nullptr)
      this->firmware_sensor_->publish_state(version);
  }
  const std::string &latest = this->hub_->scanner_firmware();
  if (latest.empty() || version.empty())
    return;
  int cmp = compare_versions(version, latest);
  uint32_t now = millis();
  if (this->fw_known_ && !changed) {
    if (cmp < 0 && now - this->fw_report_ms_ >= FIRMWARE_REPORT_MS) {
      this->fw_report_ms_ = now;
      this->hub_->event(this->pin_, this->chip_, false, CAT_GENERAL, SEV_WARN, "FIRMWARE_OUTDATED", 0, 0, 0,
                        "firmware " + version + ", latest " + latest, t);
    }
    return;
  }
  bool was_outdated = this->fw_known_ && this->fw_cmp_ < 0;
  this->fw_known_ = true;
  this->fw_cmp_ = cmp;
  this->fw_report_ms_ = now;
  if (this->firmware_outdated_sensor_ != nullptr)
    this->firmware_outdated_sensor_->publish_state(cmp < 0);
  if (cmp < 0)
    this->hub_->event(this->pin_, this->chip_, false, CAT_GENERAL, SEV_WARN, "FIRMWARE_OUTDATED", 0, 0, 0,
                      "firmware " + version + ", latest " + latest, t);
  else if (cmp > 0)
    this->hub_->event(this->pin_, this->chip_, false, CAT_GENERAL, SEV_INFO, "FIRMWARE_NEWER", 0, 0, 0,
                      "firmware " + version + ", newer than " + latest, t);
  else if (was_outdated)
    this->hub_->event(this->pin_, this->chip_, false, CAT_GENERAL, SEV_INFO, "FIRMWARE_OK", 0, 0, 0,
                      "firmware " + version + " is the latest", t);
}

void Sector::handle_record_(const uint8_t *p, size_t len, const char *t) {
  pb::Reader r(p, len);
  pb::Field f;
  while (r.next(f)) {
    if (f.wt != pb::LEN || f.num > 7) {
      /* A record kind this gateway doesn't know (forward compatibility) */
      std::string sub = "raw/" + std::to_string(f.num);
      this->hub_->publish(this->topic_(sub.c_str()), f.wt == pb::VARINT ? std::to_string(f.v) : to_hex(f.p, f.len),
                          false);
      continue;
    }
    switch (f.num) {
      case 1:
        this->handle_status_(f.p, f.len, t);
        break;
      case 2:
        this->add_rssi_(f.p, f.len);
        break;
      case 3:
      case 4:
        this->publish_payload_(f.p, f.len, f.num == 4, t);
        break;
      case 5:
        this->handle_event_(f.p, f.len, t);
        break;
      case 6:
        this->handle_counters_(f.p, f.len, t);
        break;
      case 7:
        this->handle_ignore_list_(f.p, f.len, t);
        break;
    }
  }
}

void Sector::add_rssi_(const uint8_t *p, size_t len) {
  const uint8_t *addr = nullptr;
  size_t addr_len = 0;
  bool random = false, has_tx = false;
  uint32_t adv_type = 0, count = 0;
  int32_t sum = 0, max = 0, tx = 0;
  pb::Reader r(p, len);
  pb::Field f;
  while (r.next(f)) {
    switch (f.num) {
      case 1:
        if (f.wt == pb::LEN)
          addr = f.p, addr_len = f.len;
        break;
      case 2:
        random = f.b();
        break;
      case 3:
        adv_type = f.u32();
        break;
      case 4:
        sum = f.s32();
        break;
      case 5:
        count = f.u32();
        break;
      case 6:
        max = f.s32();
        break;
      case 7:
        tx = f.s32(), has_tx = true;
        break;
    }
  }
  if (this->hub_->ignored(addr, addr_len, count))
    return;
  J j;
  j.arr().str(addr_str(addr, addr_len, ':')).b(random).i(adv_type).raw(mean1(sum, count)).i(max).i(count);
  if (has_tx)
    j.i(tx);
  else
    j.null();
  j.end_arr();
  if (this->any_rssi_)
    this->rssi_ += ',';
  this->rssi_ += j.s;
  this->any_rssi_ = true;
}

/* Theengs-style: the AD fields split out of the raw bytes, no device-specific decoding */
void Sector::publish_payload_(const uint8_t *p, size_t len, bool scan_rsp, const char *t) {
  const uint8_t *addr = nullptr, *data = nullptr;
  size_t addr_len = 0, data_len = 0;
  bool random = false, refresh = false;
  uint32_t adv_type = 0, age = 0;
  int32_t rssi = 0;
  pb::Reader r(p, len);
  pb::Field f;
  while (r.next(f)) {
    switch (f.num) {
      case 1:
        if (f.wt == pb::LEN)
          addr = f.p, addr_len = f.len;
        break;
      case 2:
        random = f.b();
        break;
      case 3:
        adv_type = f.u32();
        break;
      case 4:
        rssi = f.s32();
        break;
      case 5:
        if (f.wt == pb::LEN)
          data = f.p, data_len = f.len;
        break;
      case 6:
        refresh = f.b();
        break;
      case 7:
        age = f.u32();
        break;
    }
  }
  if (this->hub_->ignored(addr, addr_len, 0))
    return;

  /* AD structures: [len][type][value...]; stop at padding (len 0) or a truncated one */
  const uint8_t *name = nullptr, *manu = nullptr, *svc = nullptr;
  size_t name_len = 0, manu_len = 0, svc_len = 0, svc_uuid_len = 0;
  bool name_complete = false, has_txp = false;
  int8_t txp = 0;
  std::vector<std::string> uuids;
  for (size_t i = 0; i < data_len;) {
    uint8_t l = data[i];
    if (l == 0 || i + 1 + l > data_len)
      break;
    uint8_t type = data[i + 1];
    const uint8_t *v = data + i + 2;
    size_t vl = l - 1;
    switch (type) {
      case 0x08:
      case 0x09:
        if (name == nullptr || (type == 0x09 && !name_complete))
          name = v, name_len = vl, name_complete = type == 0x09;
        break;
      case 0xff:
        if (manu == nullptr)
          manu = v, manu_len = vl;
        break;
      case 0x16:
      case 0x20:
      case 0x21: {
        size_t ul = type == 0x16 ? 2 : type == 0x20 ? 4 : 16;
        if (svc == nullptr && vl >= ul)
          svc = v, svc_len = vl, svc_uuid_len = ul;
        break;
      }
      case 0x0a:
        if (!has_txp && vl >= 1)
          txp = (int8_t) v[0], has_txp = true;
        break;
      case 0x02:
      case 0x03:
      case 0x04:
      case 0x05:
      case 0x06:
      case 0x07: {
        size_t ul = type <= 0x03 ? 2 : type <= 0x05 ? 4 : 16;
        for (size_t k = 0; k + ul <= vl; k += ul)
          uuids.push_back(uuid_str(v + k, ul));
        break;
      }
    }
    i += 1 + l;
  }

  J j;
  j.obj().k("id").str(addr_str(addr, addr_len, ':')).k("mast").str(this->hub_->mast()).k("sector").i(this->pin_);
  j.k("chip").str(this->chip_hex_()).k("t").raw(t).k("suspect").b(this->suspect_);
  j.k("kind").str(scan_rsp ? "scan_rsp" : "adv").k("rssi").i(rssi).k("random").b(random).k("adv_type").i(adv_type);
  j.k("refresh").b(refresh).k("age_ms").i((int64_t) age * this->tick_ms_).k("data").hex(data, data_len);
  if (name != nullptr)
    j.k("name").name(name, name_len);
  if (manu != nullptr)
    j.k("manufacturerdata").hex(manu, manu_len);
  if (svc != nullptr) {
    j.k("servicedata").hex(svc + svc_uuid_len, svc_len - svc_uuid_len);
    j.k("servicedatauuid").str(uuid_str(svc, svc_uuid_len));
  }
  if (has_txp)
    j.k("txpower").i(txp);
  if (!uuids.empty()) {
    j.k("uuids").arr();
    for (auto &u : uuids)
      j.str(u);
    j.end_arr();
  }
  j.end_obj();
  std::string sub = "adv/" + addr_str(addr, addr_len, 0);
  this->hub_->publish(this->topic_(sub.c_str()), j.s, false);
}

void Sector::handle_status_(const uint8_t *p, size_t len, const char *t) {
  std::string version;
  bool flags[8] = {};  // ext_antenna, listening, active_scan, payloads, flash_mode, client, test_image (2-8)
  uint32_t nums[6] = {};  // adverts, dropped, devices, load_reasons, line_peak_pct, budget_pct (9-14)
  Intervals iv;
  uint32_t baud = 0;
  uint32_t ign[3] = {};  // ignore_rules, ignore_saved, ignored (17-19, scanner 0.6.0+)
  pb::Reader r(p, len);
  pb::Field f;
  while (r.next(f)) {
    if (f.num == 1 && f.wt == pb::LEN) {
      version.assign((const char *) f.p, f.len);
    } else if (f.num >= 2 && f.num <= 8 && f.wt == pb::VARINT) {
      flags[f.num - 2] = f.b();
    } else if (f.num >= 9 && f.num <= 14 && f.wt == pb::VARINT) {
      nums[f.num - 9] = f.u32();
    } else if (f.num == 15 && f.wt == pb::LEN) {
      pb::Reader ri(f);
      pb::Field g;
      while (ri.next(g))
        if (g.num >= 1 && g.num <= 5 && g.wt == pb::VARINT)
          iv.v[g.num - 1] = g.u32();
    } else if (f.num == 16 && f.wt == pb::VARINT) {
      baud = f.u32();
    } else if (f.num >= 17 && f.num <= 19 && f.wt == pb::VARINT) {
      ign[f.num - 17] = f.u32();
    }
  }

  static const char *const FLAG_NAMES[7] = {"ext_antenna", "listening", "active_scan", "payloads",
                                            "flash_mode",  "client",    "test_image"};
  static const char *const NUM_NAMES[6] = {"adverts", "dropped", "devices", "load_reasons", "line_peak_pct",
                                           "budget_pct"};
  J j;
  j.obj().k("t").raw(t).k("chip").str(this->chip_hex_()).k("seq").i(this->seq_).k("pin_sector").i(this->pin_);
  j.k("suspect").b(this->suspect_).k("lost").i(this->lost_).k("bad").i(this->bad_);
  j.k("rx_overflow").i(this->rx_high_).k("version").str(version);
  for (int i = 0; i < 7; i++)
    j.k(FLAG_NAMES[i]).b(flags[i]);
  for (int i = 0; i < 6; i++)
    j.k(NUM_NAMES[i]).i(nums[i]);
  j.k("intervals").obj();
  for (int i = 0; i < 5; i++)
    j.k(INTERVAL_NAMES[i]).i(iv.v[i]);
  j.end_obj().k("baud").i(baud);
  j.k("ignore_rules").i(ign[0]).k("ignore_saved").i(ign[1]).k("ignored").i(ign[2]).end_obj();
  this->hub_->publish(this->topic_("status"), j.s, false);

  this->check_firmware_(version, t);
  this->set_state_(ST_VERSION, version);

  this->set_state_(ST_FLASH, flags[4] ? "on" : "off");
  this->set_state_(ST_ANT, flags[0] ? "ext" : "int");
  this->set_state_(ST_LISTENING, flags[1] ? "on" : "off");
  this->set_state_(ST_CLIENT, flags[5] ? "on" : "off");
  this->set_state_(ST_TEST_IMAGE, flags[6] ? "on" : "off");
  this->set_state_(ST_ACTIVE, flags[2] ? "on" : "off");
  this->set_state_(ST_PAYLOADS, flags[3] ? "on" : "off");
  if (this->devices_sensor_ != nullptr)
    this->devices_sensor_->publish_state(nums[2]);
  if (this->ignored_sensor_ != nullptr)
    this->ignored_sensor_->publish_state(ign[2]);

  this->reported_.payloads = flags[3];
  this->reported_.active_scan = flags[2];
  this->reported_.intervals = iv;
  this->reported_.budget_pct = nums[5];
  this->have_status_ = true;
  this->reconcile_();
}

void Sector::handle_counters_(const uint8_t *p, size_t len, const char *t) {
  static const int N = 15;
  static const char *const NAMES[N] = {"uptime_s",     "buckets_sent",  "buckets_skipped", "cmds_ok",
                                       "cmds_bad",     "cmds_other",    "rx_errors",       "payloads_sent",
                                       "payloads_held", "rssi_trimmed", "seen_evicted",    "events_lost",
                                       "boots",        "flash_opens",   "ignored"};
  uint32_t v[N] = {};
  pb::Reader r(p, len);
  pb::Field f;
  while (r.next(f))
    if (f.num >= 1 && f.num <= N && f.wt == pb::VARINT)
      v[f.num - 1] = f.u32();
  J j;
  j.obj().k("t").raw(t).k("chip").str(this->chip_hex_()).k("seq").i(this->seq_);
  for (int i = 0; i < N; i++)
    j.k(NAMES[i]).i(v[i]);
  j.end_obj();
  this->hub_->publish(this->topic_("counters"), j.s, false);
}

/* "C1:7D:2B:AC:03:BC", "C1:7D:2B:00:00:00/24" or "<addr>/<mask>", as the scanner's console prints it */
static std::string rule_str(const uint8_t *addr, const uint8_t *mask) {
  int bits = 0;
  bool prefix = true, zeros = false;
  for (size_t i = 0; i < 8 * ADDR_LEN; i++) {
    bool one = mask[i / 8] & (0x80 >> (i % 8));
    if (one && zeros)
      prefix = false;
    else if (one)
      bits++;
    else
      zeros = true;
  }
  std::string r = addr_str(addr, ADDR_LEN, ':');
  if (bits == 8 * (int) ADDR_LEN)
    return r;
  return r + "/" + (prefix ? std::to_string(bits) : addr_str(mask, ADDR_LEN, ':'));
}

/* IgnoreList: the scanner's rules at boot, after a change and on request; retained <sector>/ignore */
void Sector::handle_ignore_list_(const uint8_t *p, size_t len, const char *t) {
  struct Rule {
    std::string rule;
    bool saved;
    uint32_t hits;
  };
  std::vector<Rule> rules;
  bool paused = false;
  pb::Reader r(p, len);
  pb::Field f;
  while (r.next(f)) {
    if (f.num == 2 && f.wt == pb::VARINT) {
      paused = f.b();
    } else if (f.num == 1 && f.wt == pb::LEN) {
      uint8_t addr[ADDR_LEN] = {}, mask[ADDR_LEN];
      memset(mask, 0xff, sizeof(mask));
      Rule e{"", false, 0};
      pb::Reader ri(f);
      pb::Field g;
      while (ri.next(g)) {
        if ((g.num == 1 || g.num == 2) && g.wt == pb::LEN && g.len == ADDR_LEN)
          memcpy(g.num == 1 ? addr : mask, g.p, ADDR_LEN);
        else if (g.num == 3 && g.wt == pb::VARINT)
          e.saved = g.b();
        else if (g.num == 4 && g.wt == pb::VARINT)
          e.hits = g.u32();
      }
      e.rule = rule_str(addr, mask);
      rules.push_back(e);
    }
  }

  std::vector<std::string> sig;
  J j;
  j.obj().k("t").raw(t).k("chip").str(this->chip_hex_()).k("seq").i(this->seq_).k("paused").b(paused);
  j.k("count").i(rules.size()).k("rules").arr();
  for (auto &e : rules) {
    j.obj().k("rule").str(e.rule).k("saved").b(e.saved).k("hits").i(e.hits).end_obj();
    sig.push_back(e.rule + (e.saved ? " saved" : " boot"));
  }
  j.end_arr().end_obj();
  std::sort(sig.begin(), sig.end());
  this->ignore_sig_.clear();
  for (auto &x : sig)
    this->ignore_sig_ += x + ";";
  this->ignore_rules_ = rules.size();
  this->ignore_json_ = j.s;
  this->have_ignore_ = true;
  this->hub_->publish(this->topic_("ignore"), j.s, true);
  this->hub_->check_ignore_lists(t);
}

void Sector::handle_event_(const uint8_t *p, size_t len, const char *t) {
  uint32_t category = 0, severity = 0, code = 0, cmd_seq = 0;
  int32_t value = 0, value2 = 0;
  std::string text;
  pb::Reader r(p, len);
  pb::Field f;
  while (r.next(f)) {
    switch (f.num) {
      case 1:
        category = f.u32();
        break;
      case 2:
        severity = f.u32();
        break;
      case 3:
        code = f.u32();
        break;
      case 4:
        cmd_seq = f.u32();
        break;
      case 5:
        value = f.s32();
        break;
      case 6:
        value2 = f.s32();
        break;
      case 7:
        if (f.wt == pb::LEN)
          text.assign((const char *) f.p, f.len);
        break;
    }
  }
  this->hub_->event(this->pin_, this->chip_, true, category, severity, enum_name(CODE_NAMES, code), value, value2,
                    cmd_seq, text, t);
  if (code == CODE_CMD_OK || code == CODE_CMD_REJECTED)
    this->hub_->on_ack(cmd_seq, code == CODE_CMD_OK, value, text, this->pin_);
  else if (code == CODE_BOOT)
    this->needs_settings_ = true;
}

void Sector::set_state_(uint8_t i, const std::string &v) {
  if (this->state_[i] == v)
    return;
  if (this->hub_->publish(this->topic_(STATE_NAMES[i]), v, true))
    this->state_[i] = v;
}

void Sector::publish_online_(bool online) { this->hub_->publish(this->topic_("online"), online ? "online" : "offline", true); }

void Sector::clear_retained() {
  for (uint8_t i = 0; i < ST_COUNT; i++) {
    this->hub_->publish(this->topic_(STATE_NAMES[i]), "", true);
    this->state_[i].clear();
  }
  for (const char *legacy : LEGACY_STATES)
    this->hub_->publish(this->topic_(legacy), "", true);
  this->hub_->publish(this->topic_("ignore"), this->ignore_json_, true);
  this->publish_online_(this->online());
  ESP_LOGI(TAG, "Sector %u: retained topics cleared", this->pin_);
}

/* Keep the settings the scanner forgets at boot applied: after BOOT / a new chip / a gap, and
 * every minute, compare its status with what it should have and send only the differences */
void Sector::reconcile_() {
  if (this->hub_->capturing() || !this->have_status_ || !this->have_chip_)
    return;
  uint32_t now = millis();
  bool boot = this->needs_settings_;
  if (!boot && now - this->last_reconcile_ms_ < RECONCILE_MS)
    return;
  if (this->hub_->pending_for(this))
    return;
  this->last_reconcile_ms_ = now;
  this->needs_settings_ = false;

  const Settings &d = this->desired_;
  const Settings &s = this->reported_;
  int sent = 0;
  auto send = [&](Command c) {
    c.all = false;
    memcpy(c.target, this->chip_, CHIP_ID_LEN);
    c.sector = this->pin_;
    if (this->hub_->enqueue(c))
      sent++;
  };
  if (s.payloads != d.payloads) {
    Command c;
    c.action = ACT_PAYLOADS, c.arg = d.payloads, c.text = d.payloads ? "payloads on" : "payloads off";
    send(c);
  }
  if (s.active_scan != d.active_scan) {
    Command c;
    c.action = ACT_ACTIVE_SCAN, c.arg = d.active_scan, c.text = d.active_scan ? "active on" : "active off";
    send(c);
  }
  Command iv;
  iv.action = ACT_INTERVALS;
  iv.text = "intervals";
  for (int i = 1; i < 5; i++) {
    if (s.intervals.v[i] != d.intervals.v[i]) {
      iv.intervals.v[i] = d.intervals.v[i];
      iv.text += std::string(" ") + INTERVAL_NAMES[i] + "=" + std::to_string(d.intervals.v[i]);
    }
  }
  if (iv.text != "intervals")
    send(iv);
  uint32_t budget = this->hub_->effective_budget(d.budget_pct);
  if (s.budget_pct != budget) {
    Command c;
    c.action = ACT_BUDGET, c.arg = budget, c.text = "budget " + std::to_string(budget);
    send(c);
  }
  /* Ignore list: scanners send it at boot and on change; after a gateway restart, ask for it.
   * Only 0.7.0+ knows the request (an older scanner would reject it every minute). */
  if (!this->have_ignore_ && compare_versions(this->version_, IGNORE_LIST_MIN_FW) >= 0) {
    Command c;
    c.action = ACT_IGNORE_LIST, c.arg = 1, c.text = "ignore list";
    send(c);
  }
  /* The RSSI interval is mast-wide: it may only go to every scanner at once */
  if (s.intervals.v[0] != this->hub_->rssi_interval()) {
    Command c;
    c.all = true;
    c.action = ACT_INTERVALS;
    c.intervals.v[0] = this->hub_->rssi_interval();
    c.text = "intervals rssi=" + std::to_string(c.intervals.v[0]);
    if (this->hub_->enqueue(c))
      sent++;
  }
  if (sent == 0)
    return;
  if (boot)
    ESP_LOGI(TAG, "Sector %u: sending %d setting(s) to scanner %s", this->pin_, sent, this->chip_hex_().c_str());
  else
    ESP_LOGW(TAG, "Sector %u: scanner settings differ from the gateway's, re-sending %d", this->pin_, sent);
}

/* <sector>/cmd, buttons and lambdas: addressed to the chip last seen on this pin */
void Sector::on_mqtt_command(const std::string &payload) { this->command(command_text(payload)); }

bool Sector::command(const std::string &text) {
  Command c;
  std::string err;
  if (!parse_command(text, c, err)) {
    ESP_LOGW(TAG, "Sector %u: %s", this->pin_, err.c_str());
    return false;
  }
  if (c.action == ACT_INTERVALS && c.intervals.v[0]) {
    ESP_LOGW(TAG, "Sector %u: the rssi interval is mast-wide, send it on all/cmd", this->pin_);
    return false;
  }
  if (c.action == ACT_IGNORE || c.action == ACT_UNIGNORE || c.action == ACT_IGNORE_CLEAR) {
    ESP_LOGW(TAG, "Sector %u: the ignore list is one for the whole mast, send '%s' on all/cmd", this->pin_,
             c.text.c_str());
    return false;
  }
  if (!this->have_chip_) {
    ESP_LOGW(TAG, "Sector %u: no scanner chip seen yet, '%s' dropped", this->pin_, c.text.c_str());
    return false;
  }
  /* Settings sent by hand become what the gateway keeps applied (until it reboots) */
  if (c.action == ACT_PAYLOADS)
    this->desired_.payloads = c.arg;
  else if (c.action == ACT_ACTIVE_SCAN)
    this->desired_.active_scan = c.arg;
  else if (c.action == ACT_BUDGET)
    this->desired_.budget_pct = c.arg;
  else if (c.action == ACT_INTERVALS)
    for (int i = 1; i < 5; i++)
      if (c.intervals.v[i])
        this->desired_.intervals.v[i] = c.intervals.v[i];
  c.all = false;
  memcpy(c.target, this->chip_, CHIP_ID_LEN);
  c.sector = this->pin_;
  return this->hub_->enqueue(c);
}

/* ---------------------------------------------------------------- SectorScanner (hub) */

void SectorScanner::set_settings(bool payloads, bool active, uint32_t rssi, uint32_t payload, uint32_t refresh,
                                 uint32_t status, uint32_t counters, uint32_t budget) {
  this->defaults_.payloads = payloads;
  this->defaults_.active_scan = active;
  this->defaults_.intervals = Intervals{{rssi, payload, refresh, status, counters}};
  this->defaults_.budget_pct = budget;
  this->rssi_interval_ = rssi;
}

void SectorScanner::add_ignore_rule(const std::string &text) {
  IgnoreRule r;
  if (parse_ignore_rule(text, r))
    this->ignore_.push_back(r);
  else
    ESP_LOGE(TAG, "Bad ignore rule '%s' (checked at compile time, so this shouldn't happen)", text.c_str());
}

/* YAML ignore list: records from matching addresses are dropped here, silently. At DEBUG level
 * each address with drops is logged once per 10 s with its counts (ignore_log_tick_). */
bool SectorScanner::ignored(const uint8_t *addr, size_t len, uint32_t adverts) {
  if (this->ignore_.empty() || addr == nullptr || len != ADDR_LEN)
    return false;
  const IgnoreRule *hit = nullptr;
  for (const auto &r : this->ignore_) {
    bool match = true;
    for (size_t b = 0; b < ADDR_LEN && match; b++)
      match = (addr[b] & r.mask[b]) == r.addr[b];
    if (match) {
      hit = &r;
      break;
    }
  }
  if (hit == nullptr)
    return false;
#if ESPHOME_LOG_LEVEL >= ESPHOME_LOG_LEVEL_DEBUG
  if (this->capture_ == nullptr) {
    for (auto &h : this->ignore_hits_) {
      if (memcmp(h.addr, addr, ADDR_LEN) == 0) {
        h.records++;
        h.adverts += adverts;
        return true;
      }
    }
    if (this->ignore_hits_.size() < IGNORE_HITS_MAX) {
      IgnoreHit h;
      memcpy(h.addr, addr, ADDR_LEN);
      h.records = 1;
      h.adverts = adverts;
      this->ignore_hits_.push_back(h);
    } else {
      this->ignore_hits_overflow_++;
    }
  }
#endif
  return true;
}

void SectorScanner::ignore_log_tick_() {
#if ESPHOME_LOG_LEVEL >= ESPHOME_LOG_LEVEL_DEBUG
  uint32_t now = millis();
  if (now - this->ignore_log_ms_ < IGNORE_LOG_MS)
    return;
  this->ignore_log_ms_ = now;
  for (const auto &h : this->ignore_hits_)
    ESP_LOGD(TAG, "Ignored %s: %" PRIu32 " record(s) dropped (%" PRIu32 " adverts) in the last %" PRIu32 " s",
             addr_str(h.addr, ADDR_LEN, ':').c_str(), h.records, h.adverts, IGNORE_LOG_MS / 1000);
  if (this->ignore_hits_overflow_)
    ESP_LOGD(TAG, "Ignored: %" PRIu32 " more record(s) dropped from other addresses", this->ignore_hits_overflow_);
  this->ignore_hits_.clear();
  this->ignore_hits_overflow_ = 0;
#endif
}

void SectorScanner::setup() {
  for (auto *s : this->sectors_)
    s->desired() = this->defaults_;
  if (mqtt::global_mqtt_client == nullptr)
    return;
  for (auto *s : this->sectors_)
    mqtt::global_mqtt_client->subscribe(this->prefix_ + "/" + std::to_string(s->pin()) + "/cmd",
                                        [s](const std::string &, const std::string &payload) { s->on_mqtt_command(payload); });
  mqtt::global_mqtt_client->subscribe(this->prefix_ + "/all/cmd", [this](const std::string &, const std::string &payload) {
    this->on_all_command_(payload);
  });
}

void SectorScanner::dump_config() {
  ESP_LOGCONFIG(TAG, "Sector scanners (protocol 3), mast '%s':", this->mast_.c_str());
  ESP_LOGCONFIG(TAG, "  Topic prefix: %s", this->prefix_.c_str());
  ESP_LOGCONFIG(TAG, "  Commands: %s", this->command_uart_ != nullptr ? "on" : "off");
  const Settings &d = this->defaults_;
  ESP_LOGCONFIG(TAG,
                "  Settings: payloads %s, active %s, budget %" PRIu32 "%%, intervals rssi=%" PRIu32 " payload=%" PRIu32
                " refresh=%" PRIu32 " status=%" PRIu32 " counters=%" PRIu32,
                d.payloads ? "on" : "off", d.active_scan ? "on" : "off", d.budget_pct, d.intervals.v[0],
                d.intervals.v[1], d.intervals.v[2], d.intervals.v[3], d.intervals.v[4]);
  ESP_LOGCONFIG(TAG, "  Scanner firmware (latest): %s",
                this->scanner_firmware_.empty() ? "not checked" : this->scanner_firmware_.c_str());
  ESP_LOGCONFIG(TAG, "  Ignore list: %u rule(s)", (unsigned) this->ignore_.size());
  for (const auto &r : this->ignore_)
    ESP_LOGCONFIG(TAG, "    %s/%s", addr_str(r.addr, ADDR_LEN, ':').c_str(), addr_str(r.mask, ADDR_LEN, ':').c_str());
  LOG_SENSOR("  ", "Gateway load", this->gateway_load_sensor_);
  LOG_TEXT_SENSOR("  ", "Self test", this->self_test_sensor_);
  for (auto *s : this->sectors_)
    s->log_config();
}

void SectorScanner::loop() {
  /* Nothing from a scanner that's gone survives a gateway reboot or a broker reconnect */
  bool connected = mqtt::global_mqtt_client != nullptr && mqtt::global_mqtt_client->is_connected();
  if (connected && !this->mqtt_connected_)
    this->clear_retained();
  this->mqtt_connected_ = connected;

  if (this->self_test_ && !this->self_test_done_)
    this->run_self_test_();

  for (auto *s : this->sectors_)
    s->poll();
  this->pump_commands_();
  this->throttle_tick_();
  this->ignore_log_tick_();
}

void SectorScanner::clear_retained() {
  for (auto *s : this->sectors_)
    s->clear_retained();
}

void SectorScanner::now_json(char *out, size_t size) const {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  if (this->capture_ != nullptr || tv.tv_sec < CLOCK_VALID_AFTER) {
    snprintf(out, size, "null");
    return;
  }
  snprintf(out, size, "%lld", (long long) tv.tv_sec * 1000 + tv.tv_usec / 1000);
}

bool SectorScanner::publish(const std::string &topic, const std::string &payload, bool retain) {
  if (this->capture_ != nullptr) {
    if (!retain)
      this->capture_->emplace_back(topic, payload);
    return true;
  }
  if (mqtt::global_mqtt_client == nullptr || !mqtt::global_mqtt_client->is_connected())
    return false;
  bool ok = mqtt::global_mqtt_client->publish(topic, payload, 0, retain);
  if (!ok)
    this->pub_fail_window_++;
  return ok;
}

/* Scanner and gateway events -> log, <prefix>/events, and SECURITY ones also <prefix>/security */
void SectorScanner::event(int pin, const uint8_t *chip, bool scanner, uint8_t category, uint8_t severity,
                          const std::string &code, int32_t value, int32_t value2, uint32_t cmd_seq,
                          const std::string &text, const char *t) {
  char now[24];
  if (t == nullptr) {
    this->now_json(now, sizeof(now));
    t = now;
  }
  std::string cat = enum_name(CATEGORY_NAMES, category);
  std::string sev = enum_name(SEVERITY_NAMES, severity);
  J j;
  j.obj().k("t").raw(t).k("source").str(scanner ? "scanner" : "gateway").k("sector");
  if (pin < 0)
    j.null();
  else
    j.i(pin);
  j.k("chip");
  if (chip == nullptr)
    j.null();
  else
    j.str(to_hex(chip, CHIP_ID_LEN));
  j.k("category").str(cat).k("severity").str(sev).k("code").str(code).k("value").i(value).k("value2").i(value2);
  j.k("cmd_seq").i(cmd_seq).k("text").str(text).end_obj();
  this->publish(this->prefix_ + "/events", j.s, false);
  if (category == CAT_SECURITY)
    this->publish(this->prefix_ + "/security", j.s, false);

  if (this->capture_ != nullptr)
    return;
  char where[40];
  if (pin < 0)
    snprintf(where, sizeof(where), "gateway");
  else
    snprintf(where, sizeof(where), "sector %d %s", pin, scanner ? "scanner" : "gateway");
  if (severity >= SEV_ERROR)
    ESP_LOGE(TAG, "[%s %s] %s: %s %s", cat.c_str(), sev.c_str(), where, code.c_str(), text.c_str());
  else if (severity == SEV_WARN)
    ESP_LOGW(TAG, "[%s %s] %s: %s %s", cat.c_str(), sev.c_str(), where, code.c_str(), text.c_str());
  else
    ESP_LOGI(TAG, "[%s %s] %s: %s %s", cat.c_str(), sev.c_str(), where, code.c_str(), text.c_str());
}

bool SectorScanner::enqueue(Command c) {
  if (this->capture_ != nullptr)
    return false;
  if (this->command_uart_ == nullptr) {
    ESP_LOGW(TAG, "No command UART, '%s' dropped", c.text.c_str());
    return false;
  }
  if (this->in_flight_ && same_command(this->flight_, c))
    return true;
  for (auto &q : this->queue_)
    if (same_command(q, c))
      return true;
  if (this->queue_.size() >= QUEUE_MAX) {
    ESP_LOGW(TAG, "Command queue full, '%s' dropped", c.text.c_str());
    return false;
  }
  this->queue_.push_back(c);
  return true;
}

bool SectorScanner::pending_for(const Sector *s) const {
  auto mine = [s](const Command &c) { return c.all || memcmp(c.target, s->chip(), CHIP_ID_LEN) == 0; };
  if (this->in_flight_ && mine(this->flight_))
    return true;
  for (auto &c : this->queue_)
    if (mine(c))
      return true;
  return false;
}

/* The ignore list is mast-wide: warn (SECURITY) when the online scanners' lists differ, and say
 * when they match again. Hits don't count, only rules and whether they are saved. */
void SectorScanner::check_ignore_lists(const char *t) {
  std::string first, counts;
  bool differ = false;
  int n = 0;
  for (auto *s : this->sectors_) {
    if (!s->online() || !s->have_ignore())
      continue;
    if (n++ == 0)
      first = s->ignore_sig();
    else
      differ |= s->ignore_sig() != first;
    counts += (counts.empty() ? "" : ", ") + std::string("sector ") + std::to_string(s->pin()) + ": " +
              std::to_string(s->ignore_rules());
  }
  if (differ == this->ignore_mismatch_)
    return;
  this->ignore_mismatch_ = differ;
  if (differ)
    this->event(-1, nullptr, false, CAT_SECURITY, SEV_WARN, "IGNORE_MISMATCH", n, 0, 0,
                "ignore lists differ (" + counts + " rules); send ignore commands on all/cmd", t);
  else
    this->event(-1, nullptr, false, CAT_SECURITY, SEV_INFO, "IGNORE_MATCH", n, 0, 0,
                "ignore lists match (" + counts + " rules)", t);
}

/* One command on the wire at a time: the next goes after the ack (or 2 s without one) */
void SectorScanner::pump_commands_() {
  uint32_t now = millis();
  if (this->in_flight_ && now - this->flight_ms_ >= ACK_TIMEOUT_MS) {
    this->in_flight_ = false;
    char text[96];
    snprintf(text, sizeof(text), "no ack for '%s' within %" PRIu32 " s", this->flight_.text.c_str(),
             ACK_TIMEOUT_MS / 1000);
    this->event(this->flight_.sector, this->flight_.all ? nullptr : this->flight_.target, false, CAT_COMMAND, SEV_WARN,
                "CMD_NO_ACK", 0, 0, this->flight_.seq, text, nullptr);
  }
  if (this->in_flight_ || this->queue_.empty())
    return;
  Command c = this->queue_.front();
  this->queue_.pop_front();
  c.seq = this->next_seq_++;
  if (this->next_seq_ == 0)
    this->next_seq_ = 1;
  std::string frame = encode_command(c);
  this->command_uart_->write_array((const uint8_t *) frame.data(), frame.size());
  ESP_LOGD(TAG, "Sent '%s' (seq %" PRIu32 ") to %s: %s", c.text.c_str(), c.seq,
           c.all ? "all scanners" : to_hex(c.target, CHIP_ID_LEN).c_str(),
           to_hex((const uint8_t *) frame.data(), frame.size()).c_str());
  this->flight_ = c;
  this->in_flight_ = true;
  this->flight_ms_ = now;
}

void SectorScanner::on_ack(uint32_t cmd_seq, bool ok, int32_t action, const std::string &text, int pin) {
  if (this->capture_ != nullptr)
    return;
  if (!this->in_flight_ || cmd_seq != this->flight_.seq) {
    /* e.g. the other scanners answering a command to all */
    ESP_LOGD(TAG, "Sector %d: ack for seq %" PRIu32 " (not the command in flight)", pin, cmd_seq);
    return;
  }
  this->in_flight_ = false;
  if (ok)
    ESP_LOGI(TAG, "Sector %d: '%s' accepted", pin, this->flight_.text.c_str());
  else
    ESP_LOGW(TAG, "Sector %d: '%s' rejected: %s", pin, this->flight_.text.c_str(), text.c_str());
}

void SectorScanner::on_all_command_(const std::string &payload) {
  Command c;
  std::string err;
  if (!parse_command(command_text(payload), c, err)) {
    ESP_LOGW(TAG, "all/cmd: %s", err.c_str());
    return;
  }
  for (auto *s : this->sectors_) {
    Settings &d = s->desired();
    if (c.action == ACT_PAYLOADS)
      d.payloads = c.arg;
    else if (c.action == ACT_ACTIVE_SCAN)
      d.active_scan = c.arg;
    else if (c.action == ACT_BUDGET)
      d.budget_pct = c.arg;
    else if (c.action == ACT_INTERVALS)
      for (int i = 1; i < 5; i++)
        if (c.intervals.v[i])
          d.intervals.v[i] = c.intervals.v[i];
  }
  if (c.action == ACT_INTERVALS && c.intervals.v[0])
    this->rssi_interval_ = c.intervals.v[0];
  c.all = true;
  c.sector = -1;
  this->enqueue(c);
}

/* Every 10 s: if the gateway can't keep up (UART buffers filling, bad frames, MQTT publishes
 * failing) for two windows running, lower the scanners' budget_pct; raise it again after a
 * clean minute. Gateway load: 0 normal, 1 under pressure, 2 budget lowered. */
void SectorScanner::throttle_tick_() {
  uint32_t now = millis();
  if (this->window_ms_ == 0) {
    this->window_ms_ = now ? now : 1;
    return;
  }
  if (now - this->window_ms_ < WINDOW_MS)
    return;
  this->window_ms_ = now ? now : 1;

  uint32_t rx = 0, bad = 0;
  for (auto *s : this->sectors_) {
    rx += s->take_rx_high();
    bad += s->take_bad();
  }
  uint32_t pf = this->pub_fail_window_;
  this->pub_fail_window_ = 0;
  bool pressure = rx > 0 || pf >= 3 || bad >= 3;
  uint32_t max_desired = 0;
  for (auto *s : this->sectors_)
    max_desired = std::max(max_desired, s->desired().budget_pct);
  char text[128];
  snprintf(text, sizeof(text), "rx buffer high %" PRIu32 ", publish failures %" PRIu32 ", bad frames %" PRIu32, rx, pf,
           bad);

  if (pressure) {
    ESP_LOGW(TAG, "Gateway under pressure: %s", text);
    this->clean_windows_ = 0;
    if (++this->pressure_windows_ >= 2) {
      this->pressure_windows_ = 0;
      uint32_t cur = std::min(max_desired, this->budget_cap_);
      if (cur > BUDGET_FLOOR) {
        this->budget_cap_ = std::max(BUDGET_FLOOR, cur - BUDGET_STEP);
        std::string msg = std::string("gateway can't keep up (") + text + "): scanner budget " +
                          std::to_string(this->budget_cap_) + "%";
        this->event(-1, nullptr, false, CAT_LOAD, SEV_WARN, "BUDGET_LOWERED", (int32_t) this->budget_cap_, 0, 0, msg,
                    nullptr);
        for (auto *s : this->sectors_)
          s->request_settings();
      }
    }
  } else {
    this->pressure_windows_ = 0;
    if (this->budget_cap_ < 100 && ++this->clean_windows_ >= 6) {
      this->clean_windows_ = 0;
      this->budget_cap_ += BUDGET_STEP;
      if (this->budget_cap_ >= max_desired)
        this->budget_cap_ = 100;
      uint32_t eff = std::min(max_desired, this->budget_cap_);
      this->event(-1, nullptr, false, CAT_LOAD, SEV_INFO, "BUDGET_RAISED", (int32_t) eff, 0, 0,
                  "gateway keeping up again: scanner budget " + std::to_string(eff) + "%", nullptr);
      for (auto *s : this->sectors_)
        s->request_settings();
    }
  }

  int level = this->budget_cap_ < 100 ? 2 : pressure ? 1 : 0;
  if (level != this->gateway_load_) {
    this->gateway_load_ = level;
    if (this->gateway_load_sensor_ != nullptr)
      this->gateway_load_sensor_->publish_state(level);
  }
}

}  // namespace sector_scanner
}  // namespace esphome
