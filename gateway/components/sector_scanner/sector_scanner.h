#pragma once

#include <string>

#include "esphome/core/component.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/uart/uart.h"

namespace esphome {
namespace sector_scanner {

/*
 * Scanner frame (scanner_fw/README.md): COBS-encoded, 0x00 after each frame.
 *   header (8):  ver, sector, seq, flags, adverts (u16 LE), n_devs, dropped
 *   record (11): addr[6] (as printed), flags, rssi_med, rssi_max, count, tx_1m
 *   crc (2):     CRC-16/CCITT-FALSE of header + records, LE
 */
static const size_t FRAME_HDR_LEN = 8;
static const size_t FRAME_REC_LEN = 11;
static const size_t FRAME_MAX_DEVS = 64;
static const size_t FRAME_RAW_MAX = FRAME_HDR_LEN + FRAME_MAX_DEVS * FRAME_REC_LEN + 2;
static const size_t FRAME_ENC_MAX = FRAME_RAW_MAX + FRAME_RAW_MAX / 254 + 1;

class SectorScanner : public Component, public uart::UARTDevice {
 public:
  void set_sector(uint8_t sector) { this->sector_ = sector; }
  void set_topic(const std::string &topic) { this->topic_ = topic; }
  void set_devices_sensor(sensor::Sensor *s) { this->devices_sensor_ = s; }
  void set_lost_frames_sensor(sensor::Sensor *s) { this->lost_frames_sensor_ = s; }
  void set_bad_frames_sensor(sensor::Sensor *s) { this->bad_frames_sensor_ = s; }

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

 protected:
  void handle_frame_();
  bool decode_(size_t *raw_len);
  void publish_(size_t raw_len);

  uint8_t sector_{0};
  std::string topic_;
  sensor::Sensor *devices_sensor_{nullptr};
  sensor::Sensor *lost_frames_sensor_{nullptr};
  sensor::Sensor *bad_frames_sensor_{nullptr};

  uint8_t enc_[FRAME_ENC_MAX];
  size_t enc_len_{0};
  bool overflow_{false};
  uint8_t raw_[FRAME_RAW_MAX];
  std::string json_;

  bool have_seq_{false};
  uint8_t last_seq_{0};
  uint32_t frames_ok_{0};
  uint32_t frames_lost_{0};
  uint32_t frames_bad_{0};
  uint32_t last_frame_ms_{0};
};

}  // namespace sector_scanner
}  // namespace esphome
