# -*- coding: utf-8 -*-
import json
from typing import Dict, Any
from .topics import (
    MQTT_STATUS_TOPIC, DOVIT_STATUS_TOPIC, ALARM_HOUSE_AVAILABILITY_TOPIC,
    ALARM_STATE_AVAILABILITY_TOPIC_FMT, ALARM_TEXT_AVAILABILITY_TOPIC_FMT,
)


def availability_fields(*evidence_topics: str) -> Dict[str, Any]:
    # A live broker connection alone does not establish Dovit connectivity.
    return {
        "availability": [
            {"topic": topic, "payload_available": "online", "payload_not_available": "offline"}
            for topic in (MQTT_STATUS_TOPIC, DOVIT_STATUS_TOPIC, *evidence_topics)
        ],
        "availability_mode": "all",
    }

def discovery_device(node_id: str) -> Dict[str, Any]:
    return {
        "identifiers": [node_id],
        "name": "D2HA Bridge",
        "manufacturer": "Independent community project",
        "model": "TCP 6060 XML bridge",
    }

def light_payload(node_id: str, dev_id: int, name: str) -> Dict[str, Any]:
    unique_id = f"dovit_light_{dev_id}"
    return {
        **availability_fields(),
        "name": name,
        "object_id": unique_id,
        "unique_id": unique_id,
        "state_topic": f"dovit/light/{dev_id}/state",
        "command_topic": f"dovit/light/{dev_id}/set",
        "payload_on": "ON",
        "payload_off": "OFF",
        "optimistic": False,
        "retain": False,
        "device": discovery_device(node_id),
    }

def switch_payload(node_id: str, dev_id: int, name: str) -> Dict[str, Any]:
    return {
        **availability_fields(),
        "name": name,
        "default_entity_id": f"switch.dovit_switch_{dev_id}",
        "unique_id": f"dovit_switch_{dev_id}",
        "state_topic": f"dovit/switch/{dev_id}/state",
        "command_topic": f"dovit/switch/{dev_id}/set",
        "payload_on": "ON",
        "payload_off": "OFF",
        "optimistic": False,
        "retain": False,
        "device": discovery_device(node_id),
    }


def cover_payload(
    node_id: str,
    dev_id: int,
    name: str,
    *,
    position_topic: str | None = None,
    set_position_topic: str | None = None,
) -> Dict[str, Any]:
    unique_id = f"dovit_cover_{dev_id}"
    payload = {
        **availability_fields(),
        "name": name,
        "object_id": unique_id,
        "unique_id": unique_id,
        "command_topic": f"dovit/cover/{dev_id}/set",
        "state_topic": f"dovit/cover/{dev_id}/state",
        "payload_open": "OPEN",
        "payload_close": "CLOSE",
        "payload_stop": "STOP",
        "state_opening": "opening",
        "state_closing": "closing",
        "state_stopped": "stopped",
        "optimistic": False,
        "device": discovery_device(node_id),
    }
    if position_topic and set_position_topic:
        payload["position_topic"] = position_topic
        payload["set_position_topic"] = set_position_topic
        payload["position_open"] = 100
        payload["position_closed"] = 0
    return payload

def motion_payload(node_id: str, dev_id: int, name: str) -> Dict[str, Any]:
    unique_id = f"dovit_motion_{dev_id}"
    return {
        **availability_fields(),
        "name": name,
        "object_id": unique_id,
        "unique_id": unique_id,
        "state_topic": f"dovit/motion/{dev_id}/state",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "motion",
        "device": discovery_device(node_id),
    }

def contact_payload(node_id: str, dev_id: int, name: str, device_class: str = "door") -> Dict[str, Any]:
    unique_id = f"dovit_contact_{dev_id}"
    return {
        **availability_fields(),
        "name": name,
        "object_id": unique_id,
        "unique_id": unique_id,
        "state_topic": f"dovit/contact/{dev_id}/state",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": device_class,
        "device": discovery_device(node_id),
    }

def alarm_state_payload(node_id: str, dev_id: int, name: str) -> Dict[str, Any]:
    unique_id = f"dovit_alarm_state_{dev_id}"
    return {
        **availability_fields(ALARM_STATE_AVAILABILITY_TOPIC_FMT.format(id=dev_id)),
        "name": name,
        "object_id": unique_id,
        "unique_id": unique_id,
        "state_topic": f"dovit/alarm/{dev_id}/state",
        "icon": "mdi:shield-home",
        "device": discovery_device(node_id),
    }

def alarm_text_payload(node_id: str, dev_id: int, name: str) -> Dict[str, Any]:
    unique_id = f"dovit_alarm_text_{dev_id}"
    return {
        **availability_fields(ALARM_TEXT_AVAILABILITY_TOPIC_FMT.format(id=dev_id)),
        "name": name,
        "object_id": unique_id,
        "unique_id": unique_id,
        "state_topic": f"dovit/alarm/{dev_id}/text",
        "icon": "mdi:text-box-outline",
        "entity_category": "diagnostic",
        "device": discovery_device(node_id),
    }

def alarm_panel_payload(node_id: str, name: str) -> Dict[str, Any]:
    unique_id = "dovit_alarm_house"
    return {
        **availability_fields(ALARM_HOUSE_AVAILABILITY_TOPIC),
        "name": name,
        "object_id": unique_id,
        "unique_id": unique_id,
        "state_topic": "dovit/alarm/house/state",
        "command_topic": "dovit/alarm/house/set",
        "supported_features": ["arm_home", "arm_away"],
        "payload_disarm": "DISARM",
        "payload_arm_home": "ARM_HOME",
        "payload_arm_away": "ARM_AWAY",
        "code_arm_required": False,
        "code_disarm_required": False,
        "icon": "mdi:shield-lock",
        "device": discovery_device(node_id),
    }

def climate_payload(
    node_id: str,
    target_id: int,
    name: str,
    min_temp: float,
    max_temp: float,
    step: float,
    current_topic: str,
    target_state_topic: str,
    target_cmd_topic: str,
    mode_state_topic: str,
    mode_cmd_topic: str,
):
    unique_id = f"dovit_climate_{target_id}"
    return {
        **availability_fields(),
        "name": name,
        "object_id": unique_id,
        "unique_id": unique_id,

        "current_temperature_topic": current_topic,
        "temperature_state_topic": target_state_topic,
        "temperature_command_topic": target_cmd_topic,

        "mode_state_topic": mode_state_topic,
        "mode_command_topic": mode_cmd_topic,
        "modes": ["off", "heat"],

        "min_temp": min_temp,
        "max_temp": max_temp,
        "temp_step": step,
        "precision": 0.1,
        "temperature_unit": "C",

        "optimistic": False,
        "device": discovery_device(node_id),
    }

def discovery_topic(prefix: str, component: str, unique_id: str) -> str:
    return f"{prefix}/{component}/{unique_id}/config"

def dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
