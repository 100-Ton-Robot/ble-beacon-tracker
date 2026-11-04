"""ESPHome external component: a BLE tracker mast's sector scanners (XIAO nRF54L15, protocol 3).

One hub per mast; one `sectors:` entry per scanner RX pin (the pin is the sector). The hub owns
the shared command TX, command seq/acks, the gateway-side throttle and the mast-wide topics; each
sector decodes its scanner's buckets (scanner_fw/PROTOCOL.md) and publishes MQTT layout v3 under
<topic_prefix>/<sector>/. Settings the scanners forget at boot (payloads, active scanning,
intervals, budget) are kept applied from the options below.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import binary_sensor, mqtt, sensor, text_sensor, uart
from esphome.const import (
    CONF_ID,
    DEVICE_CLASS_PROBLEM,
    ENTITY_CATEGORY_DIAGNOSTIC,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
)

DEPENDENCIES = ["uart", "mqtt"]
AUTO_LOAD = ["sensor", "text_sensor", "binary_sensor"]

CONF_MAST = "mast"
CONF_TOPIC_PREFIX = "topic_prefix"
CONF_COMMAND_UART_ID = "command_uart_id"
CONF_PAYLOADS = "payloads"
CONF_ACTIVE_SCAN = "active_scan"
CONF_BUDGET = "budget"
CONF_INTERVALS = "intervals"
CONF_SELF_TEST = "self_test"
CONF_GATEWAY_LOAD = "gateway_load"
CONF_SELF_TEST_RESULT = "self_test_result"
CONF_SECTORS = "sectors"
CONF_SECTOR = "sector"
CONF_EXPECTED_CHIP = "expected_chip"
CONF_LOAD = "load"
CONF_LOST_BUCKETS = "lost_buckets"
CONF_BAD_FRAMES = "bad_frames"
CONF_DEVICES = "devices"
CONF_MISMATCH = "mismatch"
CONF_CHIP = "chip"

# Scanner limits (PROTOCOL.md "Commands"); defaults = the scanner's own boot defaults
INTERVALS = {
    "rssi": (1, 1, 50),
    "payload": (1, 1, 50),
    "refresh": (50, 1, 3000),
    "status": (5, 1, 50),
    "counters": (50, 1, 3000),
}

sector_scanner_ns = cg.esphome_ns.namespace("sector_scanner")
SectorScanner = sector_scanner_ns.class_("SectorScanner", cg.Component)
Sector = sector_scanner_ns.class_("Sector", uart.UARTDevice)


def _chip_id(value):
    value = cv.string_strict(value).lower()
    if len(value) != 16 or any(c not in "0123456789abcdef" for c in value):
        raise cv.Invalid("chip ID must be 16 hex digits, as the scanner prints it")
    return value


def _unique_sectors(config):
    seen = [s[CONF_SECTOR] for s in config[CONF_SECTORS]]
    if len(seen) != len(set(seen)):
        raise cv.Invalid("each sector number may be used once")
    return config


INTERVALS_SCHEMA = cv.Schema(
    {cv.Optional(k, default=d): cv.int_range(min=lo, max=hi) for k, (d, lo, hi) in INTERVALS.items()}
)

SECTOR_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(Sector),
            # 255 is "not set" on the scanner side
            cv.Required(CONF_SECTOR): cv.int_range(min=0, max=254),
            cv.Optional(CONF_EXPECTED_CHIP): _chip_id,
            cv.Optional(CONF_LOAD): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_LOST_BUCKETS): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class=STATE_CLASS_TOTAL_INCREASING,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_BAD_FRAMES): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class=STATE_CLASS_TOTAL_INCREASING,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_DEVICES): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_MISMATCH): binary_sensor.binary_sensor_schema(
                device_class=DEVICE_CLASS_PROBLEM,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_CHIP): text_sensor.text_sensor_schema(
                icon="mdi:chip",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
        }
    ).extend(uart.UART_DEVICE_SCHEMA)
)

CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(SectorScanner),
            cv.Required(CONF_MAST): cv.string_strict,
            cv.Required(CONF_TOPIC_PREFIX): cv.publish_topic,
            cv.Optional(CONF_COMMAND_UART_ID): cv.use_id(uart.UARTComponent),
            cv.Optional(CONF_PAYLOADS, default=True): cv.boolean,
            cv.Optional(CONF_ACTIVE_SCAN, default=False): cv.boolean,
            cv.Optional(CONF_BUDGET, default=70): cv.int_range(min=10, max=90),
            cv.Optional(CONF_INTERVALS, default={}): INTERVALS_SCHEMA,
            cv.Optional(CONF_SELF_TEST, default=True): cv.boolean,
            cv.Optional(CONF_GATEWAY_LOAD): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class=STATE_CLASS_MEASUREMENT,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Optional(CONF_SELF_TEST_RESULT): text_sensor.text_sensor_schema(
                icon="mdi:check-decagram",
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ),
            cv.Required(CONF_SECTORS): cv.All(cv.ensure_list(SECTOR_SCHEMA), cv.Length(min=1)),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _unique_sectors,
)


async def to_code(config):
    hub = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(hub, config)
    cg.add(hub.set_mast(config[CONF_MAST]))
    cg.add(hub.set_topic_prefix(config[CONF_TOPIC_PREFIX]))
    if CONF_COMMAND_UART_ID in config:
        cg.add(hub.set_command_uart(await cg.get_variable(config[CONF_COMMAND_UART_ID])))
    iv = config[CONF_INTERVALS]
    cg.add(
        hub.set_settings(
            config[CONF_PAYLOADS],
            config[CONF_ACTIVE_SCAN],
            iv["rssi"],
            iv["payload"],
            iv["refresh"],
            iv["status"],
            iv["counters"],
            config[CONF_BUDGET],
        )
    )
    cg.add(hub.set_self_test(config[CONF_SELF_TEST]))
    if CONF_GATEWAY_LOAD in config:
        cg.add(hub.set_gateway_load_sensor(await sensor.new_sensor(config[CONF_GATEWAY_LOAD])))
    if CONF_SELF_TEST_RESULT in config:
        cg.add(hub.set_self_test_sensor(await text_sensor.new_text_sensor(config[CONF_SELF_TEST_RESULT])))

    for conf in config[CONF_SECTORS]:
        sec = cg.new_Pvariable(conf[CONF_ID], hub)
        await uart.register_uart_device(sec, conf)
        cg.add(sec.set_sector(conf[CONF_SECTOR]))
        if CONF_EXPECTED_CHIP in conf:
            cg.add(sec.set_expected_chip(conf[CONF_EXPECTED_CHIP]))
        for key, setter in (
            (CONF_LOAD, "set_load_sensor"),
            (CONF_LOST_BUCKETS, "set_lost_sensor"),
            (CONF_BAD_FRAMES, "set_bad_sensor"),
            (CONF_DEVICES, "set_devices_sensor"),
        ):
            if key in conf:
                cg.add(getattr(sec, setter)(await sensor.new_sensor(conf[key])))
        if CONF_MISMATCH in conf:
            cg.add(sec.set_mismatch_sensor(await binary_sensor.new_binary_sensor(conf[CONF_MISMATCH])))
        if CONF_CHIP in conf:
            cg.add(sec.set_chip_sensor(await text_sensor.new_text_sensor(conf[CONF_CHIP])))
        cg.add(hub.add_sector(sec))
