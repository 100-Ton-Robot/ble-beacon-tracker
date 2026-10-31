#include "sector_scanner.h"

#include <cctype>
#include <cinttypes>
#include <cstdio>
#include <cstring>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "esphome/components/mqtt/mqtt_client.h"

namespace esphome {
namespace sector_scanner {

static const char *const TAG = "sector_scanner";

/* A scanner sends a frame every second; warn after this long without one */
static const uint32_t STALE_MS = 5000;
/* Resend the sector command at most this often until the frame header shows it */
static const uint32_t SECTOR_CMD_INTERVAL_MS = 5000;

static const char *const ADV_TYPES[] = {"ind", "direct", "scan", "nonconn", "scanrsp", "ext", "6", "7"};

static uint16_t crc16_ccitt_false(const uint8_t *data, size_t len) {
  uint16_t crc = 0xffff;
  for (size_t i = 0; i < len; i++) {
    crc ^= (uint16_t) data[i] << 8;
    for (int b = 0; b < 8; b++)
      crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

/* COBS-encode len bytes into out (room for len + len / 254 + 1); returns the encoded length */
static size_t cobs_encode(const uint8_t *in, size_t len, uint8_t *out) {
  size_t code_at = 0;
  size_t o = 1;
  uint8_t code = 1;

  for (size_t i = 0; i < len; i++) {
    if (in[i] == 0x00) {
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

/* Chip ID as 16 lowercase hex digits, in byte order (as the scanner's console prints it) */
static void chip_hex(const uint8_t *chip, char *out) {
  for (size_t i = 0; i < CHIP_ID_LEN; i++)
    snprintf(out + 2 * i, 3, "%02x", chip[i]);
}

void SectorScanner::setup() {
  this->json_.reserve(64 + FRAME_MAX_DEVS * 48);

  if (mqtt::global_mqtt_client == nullptr)
    return;
  if (!this->command_topic_.empty())
    mqtt::global_mqtt_client->subscribe(
        this->command_topic_, [this](const std::string &, const std::string &payload) { this->on_command_(payload, false); });
  if (!this->broadcast_command_topic_.empty())
    mqtt::global_mqtt_client->subscribe(
        this->broadcast_command_topic_,
        [this](const std::string &, const std::string &payload) { this->on_command_(payload, true); });
}

void SectorScanner::dump_config() {
  ESP_LOGCONFIG(TAG, "Sector scanner %u:", this->sector_);
  ESP_LOGCONFIG(TAG, "  Topic: %s", this->topic_.c_str());
  ESP_LOGCONFIG(TAG, "  Commands: %s", this->command_uart_ != nullptr ? "on" : "off");
  if (!this->command_topic_.empty())
    ESP_LOGCONFIG(TAG, "  Command topic: %s", this->command_topic_.c_str());
  if (!this->broadcast_command_topic_.empty())
    ESP_LOGCONFIG(TAG, "  Broadcast command topic: %s", this->broadcast_command_topic_.c_str());
  LOG_SENSOR("  ", "Devices", this->devices_sensor_);
  LOG_SENSOR("  ", "Lost frames", this->lost_frames_sensor_);
  LOG_SENSOR("  ", "Bad frames", this->bad_frames_sensor_);
  LOG_TEXT_SENSOR("  ", "Chip", this->chip_text_sensor_);
}

void SectorScanner::loop() {
  uint8_t buf[64];
  size_t avail;

  while ((avail = this->available()) > 0) {
    size_t n = std::min(avail, sizeof(buf));
    if (!this->read_array(buf, n))
      break;
    for (size_t i = 0; i < n; i++) {
      uint8_t b = buf[i];
      if (b == 0x00) {
        if (this->overflow_) {
          this->frames_bad_++;
          ESP_LOGW(TAG, "Sector %u: frame longer than %u bytes dropped", this->sector_, (unsigned) FRAME_ENC_MAX);
        } else if (this->enc_len_ > 0) {
          this->handle_frame_();
        }
        this->enc_len_ = 0;
        this->overflow_ = false;
      } else if (this->enc_len_ < FRAME_ENC_MAX) {
        this->enc_[this->enc_len_++] = b;
      } else {
        this->overflow_ = true;
      }
    }
  }

  if (this->last_frame_ms_ != 0 && millis() - this->last_frame_ms_ > STALE_MS) {
    ESP_LOGW(TAG, "Sector %u: no frame for %" PRIu32 " s", this->sector_, STALE_MS / 1000);
    this->last_frame_ms_ = 0; /* warn once until frames return */
    this->have_seq_ = false;
  }
}

/* COBS-decode enc_ into raw_, check version, length and CRC */
bool SectorScanner::decode_() {
  size_t i = 0;
  size_t o = 0;

  while (i < this->enc_len_) {
    uint8_t code = this->enc_[i];
    if (i + code > this->enc_len_)
      return false;
    for (size_t k = 1; k < code; k++) {
      if (o >= FRAME_RAW_MAX)
        return false;
      this->raw_[o++] = this->enc_[i + k];
    }
    i += code;
    if (code < 0xff && i < this->enc_len_) {
      if (o >= FRAME_RAW_MAX)
        return false;
      this->raw_[o++] = 0x00;
    }
  }

  if (o < FRAME_HDR_LEN + 2)
    return false;
  size_t body = o - 2;
  uint16_t crc = this->raw_[body] | (this->raw_[body + 1] << 8);
  if (crc16_ccitt_false(this->raw_, body) != crc)
    return false;
  if (this->raw_[0] != FRAME_VER)
    return false; /* v1 (scanner fw before 0.3.0) or unknown */
  return body == FRAME_HDR_LEN + this->raw_[6] * FRAME_REC_LEN;
}

void SectorScanner::handle_frame_() {
  if (!this->decode_()) {
    /* The first frame after boot or a reconnect is usually partial */
    this->frames_bad_++;
    ESP_LOGW(TAG, "Sector %u: bad frame (%u bytes) dropped", this->sector_, (unsigned) this->enc_len_);
    if (this->bad_frames_sensor_ != nullptr)
      this->bad_frames_sensor_->publish_state(this->frames_bad_);
    return;
  }

  uint8_t seq = this->raw_[2];
  if (this->have_seq_) {
    uint8_t gap = (uint8_t) (seq - this->last_seq_ - 1);
    if (gap != 0) {
      this->frames_lost_ += gap;
      ESP_LOGW(TAG, "Sector %u: %u frame(s) lost", this->sector_, gap);
    }
  }
  if (this->last_frame_ms_ == 0)
    ESP_LOGI(TAG, "Sector %u: receiving frames", this->sector_);
  this->have_seq_ = true;
  this->last_seq_ = seq;
  this->last_frame_ms_ = millis();
  if (this->last_frame_ms_ == 0)
    this->last_frame_ms_ = 1;
  this->frames_ok_++;

  this->learn_chip_();
  this->publish_();

  if (this->devices_sensor_ != nullptr)
    this->devices_sensor_->publish_state(this->raw_[6]);
  if (this->lost_frames_sensor_ != nullptr)
    this->lost_frames_sensor_->publish_state(this->frames_lost_);

  /* The UART is the sector: give a scanner that reports another sector this one */
  if (this->command_uart_ == nullptr)
    return;
  if (this->raw_[1] == this->sector_) {
    this->sector_cmd_sent_ = false;
    return;
  }
  uint32_t now = millis();
  if (this->sector_cmd_sent_ && now - this->last_sector_cmd_ms_ < SECTOR_CMD_INTERVAL_MS)
    return;
  char hex[2 * CHIP_ID_LEN + 1];
  chip_hex(this->chip_, hex);
  ESP_LOGI(TAG, "Sector %u: scanner %s reports sector %u, sending sector %u", this->sector_, hex, this->raw_[1],
           this->sector_);
  this->write_command_(this->chip_, CMD_SECTOR, this->sector_);
  this->sector_cmd_sent_ = true;
  this->last_sector_cmd_ms_ = now;
}

/* Remember the chip ID from this frame (re-learned every frame, so a swapped board is picked up) */
void SectorScanner::learn_chip_() {
  const uint8_t *chip = &this->raw_[FRAME_CHIP_AT];

  if (this->have_chip_ && memcmp(chip, this->chip_, CHIP_ID_LEN) == 0)
    return;
  memcpy(this->chip_, chip, CHIP_ID_LEN);
  this->have_chip_ = true;
  this->sector_cmd_sent_ = false;

  char hex[2 * CHIP_ID_LEN + 1];
  chip_hex(this->chip_, hex);
  ESP_LOGI(TAG, "Sector %u: scanner chip %s", this->sector_, hex);
  if (this->chip_text_sensor_ != nullptr)
    this->chip_text_sensor_->publish_state(hex);
}

/*
 * {"sector":0,"seq":175,"chip":"1a2b3c4d5e6f7081","scanner_sector":0,"ant":"int","adverts":46,
 *  "dropped":0,"full":false,"listening":true,"flash":false,"client":false,"test_image":false,
 *  "lost":0,"devs":[["0971EA5F01FD",1,"nonconn",-53,-53,3,null],...]}
 * "chip" is lowercase hex, as the scanner's console prints it.
 * "scanner_sector" is the sector saved in the scanner; "sector" is this UART's.
 * Each device: [address, random, adv type, rssi_med, rssi_max, count, tx_1m or null],
 * strongest median first.
 */
void SectorScanner::publish_() {
  const uint8_t *h = this->raw_;
  uint8_t f = h[3];
  char hex[2 * CHIP_ID_LEN + 1];
  char tmp[112];

  chip_hex(&h[FRAME_CHIP_AT], hex);
  snprintf(tmp, sizeof(tmp), "{\"sector\":%u,\"seq\":%u,\"chip\":\"%s\",", this->sector_, h[2], hex);
  this->json_ = tmp;
  snprintf(tmp, sizeof(tmp), "\"scanner_sector\":%u,\"ant\":\"%s\",\"adverts\":%u,\"dropped\":%u,", h[1],
           (f & 0x01) ? "ext" : "int", (unsigned) (h[4] | (h[5] << 8)), h[7]);
  this->json_ += tmp;
  snprintf(tmp, sizeof(tmp), "\"full\":%s,\"listening\":%s,\"flash\":%s,\"client\":%s,\"test_image\":%s,",
           (f & 0x02) ? "true" : "false", (f & 0x04) ? "false" : "true", (f & 0x08) ? "true" : "false",
           (f & 0x10) ? "true" : "false", (f & 0x20) ? "true" : "false");
  this->json_ += tmp;
  snprintf(tmp, sizeof(tmp), "\"lost\":%" PRIu32 ",\"devs\":[", this->frames_lost_);
  this->json_ += tmp;

  for (uint8_t k = 0; k < h[6]; k++) {
    const uint8_t *r = &this->raw_[FRAME_HDR_LEN + k * FRAME_REC_LEN];
    uint8_t flags = r[6];
    char tx[8] = "null";

    if (flags & 0x10)
      snprintf(tx, sizeof(tx), "%d", (int8_t) r[10]);
    snprintf(tmp, sizeof(tmp), "%s[\"%02X%02X%02X%02X%02X%02X\",%u,\"%s\",%d,%d,%u,%s]", k ? "," : "", r[0], r[1],
             r[2], r[3], r[4], r[5], flags & 0x01, ADV_TYPES[(flags >> 1) & 0x07], (int8_t) r[7], (int8_t) r[8],
             r[9], tx);
    this->json_ += tmp;
  }
  this->json_ += "]}";

  if (mqtt::global_mqtt_client == nullptr || !mqtt::global_mqtt_client->is_connected())
    return;
  mqtt::global_mqtt_client->publish(this->topic_, this->json_);
}

bool SectorScanner::send_command(uint8_t cmd, uint8_t arg) {
  if (!this->have_chip_) {
    ESP_LOGW(TAG, "Sector %u: no scanner chip seen yet, command %u dropped", this->sector_, cmd);
    return false;
  }
  return this->write_command_(this->chip_, cmd, arg);
}

/*
 * MQTT payloads: "listen on|off", "flash on|off", "ant int|ext", "reboot".
 * Sector is set automatically from the UART, so it can't be sent here.
 */
void SectorScanner::on_command_(const std::string &payload, bool broadcast) {
  std::string p;
  for (char c : payload)
    p += (char) tolower((unsigned char) c);
  while (!p.empty() && isspace((unsigned char) p.back()))
    p.pop_back();
  while (!p.empty() && isspace((unsigned char) p.front()))
    p.erase(0, 1);

  uint8_t cmd;
  uint8_t arg;
  if (p == "listen on") {
    cmd = CMD_LISTEN, arg = 1;
  } else if (p == "listen off") {
    cmd = CMD_LISTEN, arg = 0;
  } else if (p == "flash on") {
    cmd = CMD_FLASH, arg = 1;
  } else if (p == "flash off") {
    cmd = CMD_FLASH, arg = 0;
  } else if (p == "ant ext") {
    cmd = CMD_ANTENNA, arg = 1;
  } else if (p == "ant int") {
    cmd = CMD_ANTENNA, arg = 0;
  } else if (p == "reboot") {
    cmd = CMD_REBOOT, arg = REBOOT_ARG;
  } else {
    ESP_LOGW(TAG, "Sector %u: unknown command '%s'", this->sector_, payload.c_str());
    return;
  }

  if (broadcast) {
    static const uint8_t ALL[CHIP_ID_LEN] = {};
    this->write_command_(ALL, cmd, arg);
  } else {
    this->send_command(cmd, arg);
  }
}

/* [2, target[8], cmd, arg] + CRC-16/CCITT-FALSE (LE), COBS-encoded, then 0x00, on the shared TX */
bool SectorScanner::write_command_(const uint8_t *target, uint8_t cmd, uint8_t arg) {
  if (this->command_uart_ == nullptr) {
    ESP_LOGW(TAG, "Sector %u: no command UART, command %u dropped", this->sector_, cmd);
    return false;
  }

  uint8_t raw[CMD_RAW_LEN];
  raw[0] = 2;
  memcpy(&raw[1], target, CHIP_ID_LEN);
  raw[1 + CHIP_ID_LEN] = cmd;
  raw[2 + CHIP_ID_LEN] = arg;
  uint16_t crc = crc16_ccitt_false(raw, CMD_RAW_LEN - 2);
  raw[CMD_RAW_LEN - 2] = crc & 0xff;
  raw[CMD_RAW_LEN - 1] = crc >> 8;

  uint8_t enc[CMD_RAW_LEN + 2];
  size_t n = cobs_encode(raw, sizeof(raw), enc);
  enc[n++] = 0x00;
  this->command_uart_->write_array(enc, n);

  char hex[2 * sizeof(enc) + 1];
  for (size_t i = 0; i < n; i++)
    snprintf(hex + 2 * i, 3, "%02x", enc[i]);
  ESP_LOGD(TAG, "Sector %u: sent cmd %u arg %u: %s", this->sector_, cmd, arg, hex);
  return true;
}

}  // namespace sector_scanner
}  // namespace esphome
