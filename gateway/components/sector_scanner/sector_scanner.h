#pragma once

#include <string>

#include "esphome/core/component.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/uart/uart.h"

namespace esphome {
namespace sector_scanner {

/*
 * Scanner frame v2 (scanner fw 0.3.0+, scanner_fw/README.md): COBS-encoded, 0x00 after each.
 *   header (16): ver (2), sector, seq, flags, adverts (u16 LE), n_devs, dropped, chip_id[8]
 *   record (11): addr[6] (as printed), flags, rssi_med, rssi_max, count, tx_1m
 *   crc (2):     CRC-16/CCITT-FALSE of header + records, LE
 * Command v2 (gateway -> every scanner's D7, same framing):
 *   ver (2), target chip_id[8] (all zeros = every scanner), cmd, arg, crc (2) of the first 11
 */
static const uint8_t FRAME_VER = 2;
static const size_t FRAME_HDR_LEN = 16;
static const size_t FRAME_CHIP_AT = 8;
static const size_t CHIP_ID_LEN = 8;
static const size_t FRAME_REC_LEN = 11;
static const size_t FRAME_MAX_DEVS = 64;
static const size_t FRAME_RAW_MAX = FRAME_HDR_LEN + FRAME_MAX_DEVS * FRAME_REC_LEN + 2;
static const size_t FRAME_ENC_MAX = FRAME_RAW_MAX + FRAME_RAW_MAX / 254 + 1;
static const size_t CMD_RAW_LEN = 1 + CHIP_ID_LEN + 2 + 2;

static const uint8_t CMD_LISTEN = 1;   // arg 0 stop, 1 start
static const uint8_t CMD_FLASH = 2;    // arg 0 leave, 1 enter (10 min)
static const uint8_t CMD_ANTENNA = 3;  // arg 0 onboard, 1 external
static const uint8_t CMD_SECTOR = 4;   // arg 0-254, addressed only
static const uint8_t CMD_REBOOT = 5;   // arg 0xA5 only
static const uint8_t REBOOT_ARG = 0xA5;

class SectorScanner : public Component, public uart::UARTDevice {
 public:
  void set_sector(uint8_t sector) { this->sector_ = sector; }
  void set_topic(const std::string &topic) { this->topic_ = topic; }
  void set_command_uart(uart::UARTComponent *u) { this->command_uart_ = u; }
  void set_command_topic(const std::string &topic) { this->command_topic_ = topic; }
  void set_broadcast_command_topic(const std::string &topic) { this->broadcast_command_topic_ = topic; }
  void set_devices_sensor(sensor::Sensor *s) { this->devices_sensor_ = s; }
  void set_lost_frames_sensor(sensor::Sensor *s) { this->lost_frames_sensor_ = s; }
  void set_bad_frames_sensor(sensor::Sensor *s) { this->bad_frames_sensor_ = s; }
  void set_chip_text_sensor(text_sensor::TextSensor *s) { this->chip_text_sensor_ = s; }

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  /* Send a command to the chip last seen on this sector's UART (for buttons and lambdas) */
  bool send_command(uint8_t cmd, uint8_t arg);

 protected:
  void handle_frame_();
  bool decode_();
  void publish_();
  void learn_chip_();
  void on_command_(const std::string &payload, bool broadcast);
  bool write_command_(const uint8_t *target, uint8_t cmd, uint8_t arg);

  uint8_t sector_{0};
  std::string topic_;
  uart::UARTComponent *command_uart_{nullptr};
  std::string command_topic_;
  std::string broadcast_command_topic_;
  sensor::Sensor *devices_sensor_{nullptr};
  sensor::Sensor *lost_frames_sensor_{nullptr};
  sensor::Sensor *bad_frames_sensor_{nullptr};
  text_sensor::TextSensor *chip_text_sensor_{nullptr};

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

  bool have_chip_{false};
  uint8_t chip_[CHIP_ID_LEN]{};
  bool sector_cmd_sent_{false};
  uint32_t last_sector_cmd_ms_{0};
};

}  // namespace sector_scanner
}  // namespace esphome
