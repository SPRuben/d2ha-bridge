# -*- coding: utf-8 -*-
import json
import os

MQTT_PROTOCOLS = ("3.1", "3.1.1", "5", "5.0")


def mqtt_config_options(opts: dict) -> dict:
    """Shared MQTT fields; missing mode stays manual, and 5.0 becomes 5."""
    mode = opts.get("mqtt_mode", "manual")
    tls = opts.get("mqtt_tls", False)
    protocol = opts.get("mqtt_protocol", "3.1.1")
    if mode not in ("manual", "supervisor"):
        raise ValueError("mqtt_invalid_mode")
    if type(tls) is not bool:
        raise ValueError("mqtt_invalid_tls")
    if not isinstance(protocol, str) or protocol not in MQTT_PROTOCOLS:
        raise ValueError("mqtt_invalid_protocol")
    if protocol == "5.0":
        protocol = "5"
    return dict(mqtt_mode=mode, mqtt_tls=tls, mqtt_protocol=protocol)

def load_addon_options(path: str = "/data/options.json") -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            result = json.load(f)
            if not isinstance(result, dict):
                raise ValueError("options_not_object")
            return result
    except Exception:
        # Parsing errors may include credential-bearing source text.
        print("WARNING: Could not read add-on options")
        return {}
