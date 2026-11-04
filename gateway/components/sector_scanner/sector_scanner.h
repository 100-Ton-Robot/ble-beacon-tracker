#pragma once

#include <deque>
#include <string>
#include <vector>

#include "esphome/core/component.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/uart/uart.h"

namespace esphome {
namespace sector_scanner {

/*
 * Protocol 3 (scanner fw 0.4.0+): scanner_fw/PROTOCOL.md, schema scanner_fw/proto/bletracker.proto.
 * Both directions: protobuf bytes + CRC-16/CCITT-FALSE of them (LE), COBS-encoded, then 0x00.
 * Scanner -> gateway: one Bucket per 200 ms tick on each sector's own RX pin.
 * Gateway -> scanners: one Command per frame on the shared TX, addressed by chip ID (or all).
 * MQTT layout v3: /config/docs/bletracker_gateway.md "MQTT" and the contract atom.
 */
static const size_t CHIP_ID_LEN = 8;
static const size_t BUCKET_RAW_MAX = 3072;  /* largest bucket ~2.3 KB (PROTOCOL.md "Sizes") */
static const size_t BUCKET_ENC_MAX = BUCKET_RAW_MAX + BUCKET_RAW_MAX / 254 + 1;
static const uint32_t SECTOR_UNSET = 255;
static const uint32_t REBOOT_ARG = 0xA5;

/* Event.Category / Event.Severity numbers, shared by scanner and gateway events */
enum Category : uint8_t { CAT_GENERAL = 0, CAT_SECURITY = 1, CAT_LOAD = 2, CAT_COMMAND = 3 };
enum Severity : uint8_t { SEV_INFO = 0, SEV_WARN = 1, SEV_ERROR = 2 };

/* Command action field numbers (bletracker.proto Command) */
enum Action : uint8_t {
  ACT_LISTEN = 3,
  ACT_FLASH = 4,
  ACT_EXT_ANTENNA = 5,
  ACT_SECTOR = 6,
  ACT_REBOOT = 7,
  ACT_PAYLOADS = 8,
  ACT_ACTIVE_SCAN = 9,
  ACT_INTERVALS = 10,
  ACT_BUDGET = 11,
};

/* Intervals in ticks, field order of bletracker.Intervals; 0 = unchanged in a command */
struct Intervals {
  uint32_t v[5]{};  // rssi, payload, refresh, status, counters
};

/* Settings the scanners forget at boot; the gateway keeps them applied */
struct Settings {
  bool payloads{true};
  bool active_scan{false};
  Intervals intervals{{1, 1, 50, 5, 50}};
  uint32_t budget_pct{70};
};

struct Command {
  bool all{true};
  uint8_t target[CHIP_ID_LEN]{};
  uint8_t action{0};
  uint32_t arg{0};
  Intervals intervals;
  int8_t sector{-1};  // pin sector it came from; -1 = all/cmd or the gateway itself
  uint32_t seq{0};
  std::string text;
};

/* Text command -> Command (no target). Same words as scanner_fw/tools/decode_frames.py --cmd */
bool parse_command(const std::string &text, Command &c, std::string &err);
/* Command -> framed bytes (protobuf + CRC + COBS + 0x00) */
std::string encode_command(const Command &c);

class SectorScanner;

/* One scanner on one RX pin; the pin is the sector */
class Sector : public uart::UARTDevice {
 public:
  explicit Sector(SectorScanner *hub) : hub_(hub) {}
  void set_sector(uint8_t sector) { this->pin_ = sector; }
  void set_expected_chip(const std::string &hex);
  void set_load_sensor(sensor::Sensor *s) { this->load_sensor_ = s; }
  void set_lost_sensor(sensor::Sensor *s) { this->lost_sensor_ = s; }
  void set_bad_sensor(sensor::Sensor *s) { this->bad_sensor_ = s; }
  void set_devices_sensor(sensor::Sensor *s) { this->devices_sensor_ = s; }
  void set_mismatch_sensor(binary_sensor::BinarySensor *s) { this->mismatch_sensor_ = s; }
  void set_chip_sensor(text_sensor::TextSensor *s) { this->chip_sensor_ = s; }

  /* Text command ("flash on") to the chip last seen on this pin; for buttons and lambdas */
  bool command(const std::string &text);

  uint8_t pin() const { return this->pin_; }
  bool have_chip() const { return this->have_chip_; }
  const uint8_t *chip() const { return this->chip_; }
  bool online() const { return this->last_bucket_ms_ != 0; }
  Settings &desired() { return this->desired_; }
  void request_settings() { this->needs_settings_ = true; }

  /* Called by the hub */
  void poll();
  void handle_encoded(const uint8_t *enc, size_t len);
  void clear_retained();
  void on_mqtt_command(const std::string &payload);
  uint32_t take_rx_high() {
    uint32_t n = this->rx_high_window_;
    this->rx_high_window_ = 0;
    return n;
  }
  uint32_t take_bad() {
    uint32_t n = this->bad_window_;
    this->bad_window_ = 0;
    return n;
  }
  void log_config();

 protected:
  bool decode_(const uint8_t *enc, size_t len, size_t &body);
  void bad_frame_(const char *why, size_t len);
  void validate_(uint32_t claim);
  void report_condition_();
  void handle_record_(const uint8_t *p, size_t len, const char *t);
  void handle_status_(const uint8_t *p, size_t len, const char *t);
  void handle_counters_(const uint8_t *p, size_t len, const char *t);
  void handle_event_(const uint8_t *p, size_t len, const char *t);
  void add_rssi_(const uint8_t *p, size_t len);
  void publish_payload_(const uint8_t *p, size_t len, bool scan_rsp, const char *t);
  void set_state_(uint8_t i, const std::string &v);
  void publish_online_(bool online);
  void reconcile_();
  std::string chip_hex_() const;
  std::string topic_(const char *suffix) const;

  SectorScanner *hub_;
  uint8_t pin_{0};
  bool have_expected_{false};
  uint8_t expected_[CHIP_ID_LEN]{};
  sensor::Sensor *load_sensor_{nullptr};
  sensor::Sensor *lost_sensor_{nullptr};
  sensor::Sensor *bad_sensor_{nullptr};
  sensor::Sensor *devices_sensor_{nullptr};
  binary_sensor::BinarySensor *mismatch_sensor_{nullptr};
  text_sensor::TextSensor *chip_sensor_{nullptr};

  uint8_t enc_[BUCKET_ENC_MAX];
  size_t enc_len_{0};
  bool overflow_{false};
  uint8_t raw_[BUCKET_RAW_MAX];

  /* Current bucket header (valid while its records are handled) */
  uint32_t claim_{SECTOR_UNSET};
  uint32_t seq_{0};
  uint32_t tick_ms_{0};
  bool suspect_{false};

  /* Link health */
  bool have_seq_{false};
  uint32_t last_seq_{0};
  uint32_t lost_{0};
  uint32_t bad_{0};
  uint32_t bad_window_{0};
  uint32_t rx_high_{0};
  uint32_t rx_high_window_{0};
  uint32_t last_bucket_ms_{0};
  int32_t load_{-1};

  /* Chip and sector claim checks */
  bool have_chip_{false};
  uint8_t chip_[CHIP_ID_LEN]{};
  uint8_t cond_{0};  // COND_* bits
  uint32_t cond_claim_{0};
  uint32_t cond_ms_{0};

  /* Settings the scanner reported in its last status, and what it should have */
  Settings desired_;
  bool have_status_{false};
  Settings reported_;
  bool needs_settings_{true};
  uint32_t last_reconcile_ms_{0};

  /* rssi message of the current bucket */
  std::string rssi_;
  bool any_rssi_{false};

  std::string state_[11];
};

class SectorScanner : public Component {
 public:
  void set_mast(const std::string &m) { this->mast_ = m; }
  void set_topic_prefix(const std::string &p) { this->prefix_ = p; }
  void set_command_uart(uart::UARTComponent *u) { this->command_uart_ = u; }
  void set_settings(bool payloads, bool active, uint32_t rssi, uint32_t payload, uint32_t refresh, uint32_t status,
                    uint32_t counters, uint32_t budget);
  void set_self_test(bool on) { this->self_test_ = on; }
  void set_gateway_load_sensor(sensor::Sensor *s) { this->gateway_load_sensor_ = s; }
  void set_self_test_sensor(text_sensor::TextSensor *s) { this->self_test_sensor_ = s; }
  void add_sector(Sector *s) { this->sectors_.push_back(s); }

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  /* Delete and republish every sector's retained topics (gateway "clear" command) */
  void clear_retained();

  /* Used by the sectors */
  const std::string &prefix() const { return this->prefix_; }
  const std::string &mast() const { return this->mast_; }
  bool capturing() const { return this->capture_ != nullptr; }
  bool publish(const std::string &topic, const std::string &payload, bool retain);
  void event(int pin, const uint8_t *chip, bool scanner, uint8_t category, uint8_t severity, const std::string &code,
             int32_t value, int32_t value2, uint32_t cmd_seq, const std::string &text, const char *t);
  bool enqueue(Command c);
  bool pending_for(const Sector *s) const;
  void on_ack(uint32_t cmd_seq, bool ok, int32_t action, const std::string &text, int pin);
  uint32_t effective_budget(uint32_t desired) const { return desired < this->budget_cap_ ? desired : this->budget_cap_; }
  uint32_t rssi_interval() const { return this->rssi_interval_; }
  void set_rssi_interval(uint32_t n) { this->rssi_interval_ = n; }
  void note_publish_failure() { this->pub_fail_window_++; }
  /* Epoch ms of now as a JSON number, or null before SNTP has set the clock (and in the self-test) */
  void now_json(char *out, size_t size) const;

 protected:
  void pump_commands_();
  void throttle_tick_();
  void on_all_command_(const std::string &payload);
  void run_self_test_();

  std::string mast_;
  std::string prefix_;
  uart::UARTComponent *command_uart_{nullptr};
  std::vector<Sector *> sectors_;
  Settings defaults_;
  uint32_t rssi_interval_{1};
  bool self_test_{false};
  sensor::Sensor *gateway_load_sensor_{nullptr};
  text_sensor::TextSensor *self_test_sensor_{nullptr};

  bool mqtt_connected_{false};

  std::deque<Command> queue_;
  bool in_flight_{false};
  Command flight_;
  uint32_t flight_ms_{0};
  uint32_t next_seq_{1};

  /* Gateway-side throttle */
  uint32_t budget_cap_{100};  // 100 = no cap
  uint32_t window_ms_{0};
  uint32_t pub_fail_window_{0};
  uint8_t pressure_windows_{0};
  uint8_t clean_windows_{0};
  int gateway_load_{-1};

  /* Self-test: publishes go here instead of MQTT, commands and logs are suppressed */
  std::vector<std::pair<std::string, std::string>> *capture_{nullptr};
  bool self_test_done_{false};
};

}  // namespace sector_scanner
}  // namespace esphome
