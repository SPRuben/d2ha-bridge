# -*- coding: utf-8 -*-
import re

MQTT_STATUS_TOPIC = "dovit/bridge/mqtt/status"
DOVIT_STATUS_TOPIC = "dovit/bridge/dovit/status"
ALARM_HOUSE_AVAILABILITY_TOPIC = "dovit/bridge/alarm/house/availability"
ALARM_STATE_AVAILABILITY_TOPIC_FMT = "dovit/bridge/alarm/{id}/state/availability"
ALARM_TEXT_AVAILABILITY_TOPIC_FMT = "dovit/bridge/alarm/{id}/text/availability"

SWITCH_CMD_TOPIC_WILDCARD = "dovit/switch/+/set"
SWITCH_STATE_TOPIC_FMT = "dovit/switch/{id}/state"
SWITCH_TOPIC_RE = re.compile(r"^dovit/switch/(\d+)/set$")

LIGHT_CMD_TOPIC_WILDCARD = "dovit/light/+/set"
LIGHT_STATE_TOPIC_FMT = "dovit/light/{id}/state"

COVER_CMD_TOPIC_WILDCARD = "dovit/cover/+/set"
COVER_CMD_TOPIC_FMT = "dovit/cover/{id}/set"
COVER_STATE_TOPIC_FMT = "dovit/cover/{id}/state"
COVER_POSITION_CMD_TOPIC_WILDCARD = "dovit/cover/+/set_position"
COVER_POSITION_CMD_TOPIC_FMT = "dovit/cover/{id}/set_position"
COVER_POSITION_STATE_TOPIC_FMT = "dovit/cover/{id}/position"

MOTION_STATE_TOPIC_FMT = "dovit/motion/{id}/state"
CONTACT_STATE_TOPIC_FMT = "dovit/contact/{id}/state"
ALARM_STATE_TOPIC_FMT = "dovit/alarm/{id}/state"
ALARM_TEXT_TOPIC_FMT = "dovit/alarm/{id}/text"
ALARM_HOUSE_STATE_TOPIC = "dovit/alarm/house/state"
ALARM_HOUSE_CMD_TOPIC = "dovit/alarm/house/set"

THERMO_TEMP_CMD_TOPIC_WILDCARD = "dovit/thermostat/+/set"
THERMO_MODE_CMD_TOPIC_WILDCARD = "dovit/thermostat/+/mode/set"
THERMO_TEMP_CMD_TOPIC_FMT = "dovit/thermostat/{id}/set"
THERMO_MODE_CMD_TOPIC_FMT = "dovit/thermostat/{id}/mode/set"
THERMO_MODE_STATE_TOPIC_FMT = "dovit/thermostat/{id}/mode"

THERMO_TARGET_STATE_TOPIC_FMT = "dovit/thermostat/{id}/target_temperature"
THERMO_CURRENT_STATE_TOPIC_FMT = "dovit/thermostat/{id}/current_temperature"

LIGHT_TOPIC_RE = re.compile(r"^dovit/light/(\d+)/set$")
COVER_TOPIC_RE = re.compile(r"^dovit/cover/(\d+)/set$")
COVER_POSITION_TOPIC_RE = re.compile(r"^dovit/cover/(\d+)/set_position$")
THERMO_TEMP_TOPIC_RE = re.compile(r"^dovit/thermostat/(\d+)/set$")
THERMO_MODE_TOPIC_RE = re.compile(r"^dovit/thermostat/(\d+)/mode/set$")
