"""ESPHome external component: one sector scanner (XIAO nRF54L15) on one UART.

Decodes the scanner's binary frames (format in scanner_fw/README.md) and publishes
each second's device table to MQTT as one JSON message. Use one entry per UART.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import mqtt, sensor, uart
from esphome.const import CONF_ID, ENTITY_CATEGORY_DIAGNOSTIC, STATE_CLASS_MEASUREMENT, STATE_CLASS_TOTAL_INCREASING

DEPENDENCIES = ["uart", "mqtt"]
AUTO_LOAD = ["sensor"]
MULTI_CONF = True

CONF_SECTOR = "sector"
CONF_TOPIC = "topic"
CONF_DEVICES = "devices"
CONF_LOST_FRAMES = "lost_frames"
CONF_BAD_FRAMES = "bad_frames"

sector_scanner_ns = cg.esphome_ns.namespace("sector_scanner")
SectorScanner = sector_scanner_ns.class_("SectorScanner", cg.Component, uart.UARTDevice)

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(SectorScanner),
            cv.Required(CONF_SECTOR): cv.int_range(min=0, max=255),
            cv.Required(CONF_TOPIC): cv.publish_topic,
            cv.Optional(CONF_DEVICES): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_LOST_FRAMES): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class=STATE_CLASS_TOTAL_INCREASING,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_BAD_FRAMES): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class=STATE_CLASS_TOTAL_INCREASING,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(uart.UART_DEVICE_SCHEMA)
)

FINAL_VALIDATE_SCHEMA = uart.final_validate_device_schema(
    "sector_scanner", baud_rate=115200, require_rx=True
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)
    cg.add(var.set_sector(config[CONF_SECTOR]))
    cg.add(var.set_topic(config[CONF_TOPIC]))
    for key, setter in (
        (CONF_DEVICES, "set_devices_sensor"),
        (CONF_LOST_FRAMES, "set_lost_frames_sensor"),
        (CONF_BAD_FRAMES, "set_bad_frames_sensor"),
    ):
        if key in config:
            sens = await sensor.new_sensor(config[key])
            cg.add(getattr(var, setter)(sens))
