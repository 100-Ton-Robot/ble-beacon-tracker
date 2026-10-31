#include "sector_scanner.h"

#include <cinttypes>
#include <cstdio>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "esphome/components/mqtt/mqtt_client.h"

namespace esphome {
namespace sector_scanner {

static const char *const TAG = "sector_scanner";

/* A scanner sends a frame every second; warn after this long without one */
static const uint32_t STALE_MS = 5000;

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

void SectorScanner::setup() { this->json_.reserve(64 + FRAME_MAX_DEVS * 48); }

void SectorScanner::dump_config() {
  ESP_LOGCONFIG(TAG, "Sector scanner %u:", this->sector_);
  ESP_LOGCONFIG(TAG, "  Topic: %s", this->topic_.c_str());
  LOG_SENSOR("  ", "Devices", this->devices_sensor_);
  LOG_SENSOR("  ", "Lost frames", this->lost_frames_sensor_);
  LOG_SENSOR("  ", "Bad frames", this->bad_frames_sensor_);
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

/* COBS-decode enc_ into raw_, check length and CRC */
bool SectorScanner::decode_(size_t *raw_len) {
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
  if (this->raw_[0] != 1)
    return false; /* unknown frame version */
  if (body != FRAME_HDR_LEN + this->raw_[6] * FRAME_REC_LEN)
    return false;
  *raw_len = body;
  return true;
}

void SectorScanner::handle_frame_() {
  size_t raw_len;

  if (!this->decode_(&raw_len)) {
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

  this->publish_(raw_len);

  if (this->devices_sensor_ != nullptr)
    this->devices_sensor_->publish_state(this->raw_[6]);
  if (this->lost_frames_sensor_ != nullptr)
    this->lost_frames_sensor_->publish_state(this->frames_lost_);
}

/*
 * {"sector":0,"seq":175,"ant":"int","adverts":46,"dropped":0,"full":false,"lost":0,
 *  "devs":[["0971EA5F01FD",1,"nonconn",-53,-53,3,null],...]}
 * Each device: [address, random, adv type, rssi_med, rssi_max, count, tx_1m or null],
 * strongest median first.
 */
void SectorScanner::publish_(size_t raw_len) {
  const uint8_t *h = this->raw_;
  char tmp[96];

  snprintf(tmp, sizeof(tmp), "{\"sector\":%u,\"seq\":%u,\"ant\":\"%s\",\"adverts\":%u,\"dropped\":%u,", this->sector_,
           h[2], (h[3] & 0x01) ? "ext" : "int", (unsigned) (h[4] | (h[5] << 8)), h[7]);
  this->json_ = tmp;
  snprintf(tmp, sizeof(tmp), "\"full\":%s,\"lost\":%" PRIu32 ",\"devs\":[", (h[3] & 0x02) ? "true" : "false",
           this->frames_lost_);
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

}  // namespace sector_scanner
}  // namespace esphome
