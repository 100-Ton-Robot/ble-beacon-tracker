/*
 * Boot self-test (self_test: true): the gateway's own encoder and decoder against data generated
 * independently by gateway/tools/make_selftest.py from the reference protobuf code:
 *   - the contract atom's command test vectors must encode byte for byte the same;
 *   - sample buckets fed to a scratch sector must publish exactly the expected MQTT messages.
 * Nothing goes to MQTT or the scanners while it runs. Result: log + "Self test" text sensor.
 */
#include "sector_scanner.h"
#include "selftest_data.h"

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <memory>

#include "esphome/core/log.h"

namespace esphome {
namespace sector_scanner {

static const char *const TAG = "sector_scanner.selftest";

static std::string hex_of(const std::string &s) {
  static const char H[] = "0123456789abcdef";
  std::string out;
  for (char c : s) {
    out.push_back(H[(uint8_t) c >> 4]);
    out.push_back(H[(uint8_t) c & 15]);
  }
  return out;
}

static std::string unhex(const char *h) {
  std::string out;
  for (size_t i = 0; h[i] && h[i + 1]; i += 2) {
    char b[3] = {h[i], h[i + 1], 0};
    out.push_back((char) strtoul(b, nullptr, 16));
  }
  return out;
}

void SectorScanner::run_self_test_() {
  using namespace selftest;
  this->self_test_done_ = true;

  /* Command vectors */
  size_t cmd_n = 0, cmd_ok = 0;
  for (const auto &v : CMD_VECTORS) {
    cmd_n++;
    Command c;
    std::string err;
    if (!parse_command(v.text, c, err)) {
      ESP_LOGE(TAG, "command '%s': %s", v.text, err.c_str());
      continue;
    }
    c.seq = 1;
    if (v.chip[0]) {
      std::string id = unhex(v.chip);
      c.all = false;
      memcpy(c.target, id.data(), std::min(id.size(), CHIP_ID_LEN));
    }
    std::string got = hex_of(encode_command(c));
    if (got == v.hex) {
      cmd_ok++;
    } else {
      ESP_LOGE(TAG, "command '%s' %s: got %s, want %s", v.text, v.chip, got.c_str(), v.hex);
    }
  }

  /* Sample buckets through a scratch sector (heap: its buffers are too big for the loop stack) */
  std::vector<std::pair<std::string, std::string>> got;
  std::string prefix = this->prefix_, mast = this->mast_;
  this->prefix_ = PREFIX;
  this->mast_ = MAST;
  this->capture_ = &got;
  {
    std::unique_ptr<Sector> s(new Sector(this));
    s->set_sector(PIN);
    s->desired() = this->defaults_;
    for (const char *fh : FRAMES) {
      std::string f = unhex(fh);
      size_t start = 0;
      for (size_t i = 0; i < f.size(); i++) {
        if (f[i] != '\0')
          continue;
        if (i > start)
          s->handle_encoded((const uint8_t *) f.data() + start, i - start);
        start = i + 1;
      }
    }
  }
  this->capture_ = nullptr;
  this->prefix_ = prefix;
  this->mast_ = mast;

  size_t msg_n = sizeof(MESSAGES) / sizeof(MESSAGES[0]), msg_ok = 0;
  for (size_t i = 0; i < msg_n || i < got.size(); i++) {
    if (i < msg_n && i < got.size() && got[i].first == MESSAGES[i].topic && got[i].second == MESSAGES[i].payload) {
      msg_ok++;
      continue;
    }
    ESP_LOGE(TAG, "message %u: want %s %s", (unsigned) i, i < msg_n ? MESSAGES[i].topic : "(none)",
             i < msg_n ? MESSAGES[i].payload : "");
    ESP_LOGE(TAG, "message %u: got  %s %s", (unsigned) i, i < got.size() ? got[i].first.c_str() : "(none)",
             i < got.size() ? got[i].second.c_str() : "");
  }

  bool pass = cmd_ok == cmd_n && msg_ok == msg_n && got.size() == msg_n;
  char result[96];
  snprintf(result, sizeof(result), "%s: commands %u/%u, messages %u/%u%s", pass ? "PASS" : "FAIL", (unsigned) cmd_ok,
           (unsigned) cmd_n, (unsigned) msg_ok, (unsigned) msg_n,
           got.size() != msg_n ? (got.size() > msg_n ? " (extra)" : " (missing)") : "");
  if (pass)
    ESP_LOGI(TAG, "Self test %s", result);
  else
    ESP_LOGE(TAG, "Self test %s", result);
  if (this->self_test_sensor_ != nullptr)
    this->self_test_sensor_->publish_state(result);
}

}  // namespace sector_scanner
}  // namespace esphome
