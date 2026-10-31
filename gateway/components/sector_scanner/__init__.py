"""ESPHome external component: one sector scanner (XIAO nRF54L15) on one UART.

Decodes the scanner's binary frames (format in scanner_fw/README.md) and publishes
each second's device table to MQTT as one JSON message. Use one entry per UART.
With command_uart_id set, it also learns the scanner's chip ID, sets the scanner's
sector to this entry's, and sends MQTT commands to it over the shared command TX.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import mqtt, sensor, text_sensor, uart
from esphome.const import CONF_ID, ENTITY_CATEGORY_DIAGNOSTIC, STATE_CLASS_MEASUREMENT, STATE_CLASS_TOTAL_INCREASING

DEPENDENCIES = ["uart", "mqtt"]
AUTO_LOAD = ["sensor", "text_sensor"]
MULTI_CONF = True

CONF_SECTOR = "sector"
CONF_TOPIC = "topic"
CONF_COMMAND_UART_ID = "command_uart_id"
CONF_COMMAND_TOPIC = "command_topic"
CONF_BROADCAST_COMMAND_TOPIC = "broadcast_command_topic"
CONF_DEVICES = "devices"
CONF_LOST_FRAMES = "lost_frames"
CONF_BAD_FRAMES = "bad_frames"
CONF_CHIP = "chip"

sector_scanner_ns = cg.esphome_ns.namespace("sector_scanner")
SectorScanner = sector_scanner_ns.class_("SectorScanner", cg.Component, uart.UARTDevice)


def _commands_need_uart(config):
    for key in (CONF_COMMAND_TOPIC, CONF_BROADCAST_COMMAND_TOPIC):
        if key in config and CONF_COMMAND_UART_ID not in config:
            raise cv.Invalid(f"{key} needs {CONF_COMMAND_UART_ID}")
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(SectorScanner),
            # 255 can't be sent: the scanner's sector command takes 0-254
            cv.Required(CONF_SECTOR): cv.int_range(min=0, max=254),
            cv.Required(CONF_TOPIC): cv.publish_topic,
            cv.Optional(CONF_COMMAND_UART_ID): cv.use_id(uart.UARTComponent),
            cv.Optional(CONF_COMMAND_TOPIC): cv.subscribe_topic,
            cv.Optional(CONF_BROADCAST_COMMAND_TOPIC): cv.subscribe_topic,
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
            cv.Optional(CONF_CHIP): text_sensor.text_sensor_schema(
                icon="mdi:chip",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(uart.UART_DEVICE_SCHEMA),
    _commands_need_uart,
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
    if CONF_COMMAND_UART_ID in config:
        command_uart = await cg.get_variable(config[CONF_COMMAND_UART_ID])
        cg.add(var.set_command_uart(command_uart))
    if CONF_COMMAND_TOPIC in config:
        cg.add(var.set_command_topic(config[CONF_COMMAND_TOPIC]))
    if CONF_BROADCAST_COMMAND_TOPIC in config:
        cg.add(var.set_broadcast_command_topic(config[CONF_BROADCAST_COMMAND_TOPIC]))
    for key, setter in (
        (CONF_DEVICES, "set_devices_sensor"),
        (CONF_LOST_FRAMES, "set_lost_frames_sensor"),
        (CONF_BAD_FRAMES, "set_bad_frames_sensor"),
    ):
        if key in config:
            sens = await sensor.new_sensor(config[key])
            cg.add(getattr(var, setter)(sens))
    if CONF_CHIP in config:
        sens = await text_sensor.new_text_sensor(config[CONF_CHIP])
        cg.add(var.set_chip_text_sensor(sens))
