# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
from pathlib import Path
import os
from .options import load_addon_options, mqtt_config_options

@dataclass(frozen=True)
class Config:
    # Dovit
    dovit_host: str = "127.0.0.1"
    dovit_port: int = 6060
    frame_sep: bytes = b"\x00"

    # MQTT (HA OS Add-on: core-mosquitto)
    mqtt_host: str = "core-mosquitto"
    mqtt_port: int = 1883
    mqtt_user: str = field(default="", repr=False)
    mqtt_pass: str = field(default="", repr=False)
    alarm_code: str = field(default="", repr=False)
    cover_position_mode: str = "legacy"
    web_light_control: bool = False
    web_device_control: bool = False

    # Discovery
    discovery_prefix: str = "homeassistant"
    discovery_node_id: str = "dovit_bridge"
    enable_discovery: bool = False
    publish_discovery: bool = False

    # Devices file (persistent in your case: /share worked for you)
    devices_file: Path = Path("/share/dovit_devices.json")
    cover_position_file: Path = Path("/share/dovit_cover_positions.json")

    # Light/shutter heuristics
    light_statetypes: set[int] = None  # default below
    shutter_values: set[str] = None    # default below
    shutter_confidence_distinct_values: int = 2

    # Publish behavior
    publish_todo_entities: bool = False
    discovery_republish_seconds: int = 300

    # Appended to preserve existing positional Config construction.
    mqtt_mode: str = "manual"
    mqtt_tls: bool = False
    mqtt_protocol: str = "3.1.1"

def load_config() -> Config:
    # Add-on Mode wenn options.json existiert
    addon_mode = os.path.exists("/data/options.json")
    opts = load_addon_options()
    mqtt_fields = mqtt_config_options(opts)

    enable_discovery = bool(opts.get("enable_discovery", False))
    publish_discovery = opts.get("publish_discovery") is True

    if addon_mode:
        # Läuft im HA Add-on Container: core-mosquitto + /share
        cfg = Config(
            **mqtt_fields,
            dovit_host=opts.get("dovit_host", "127.0.0.1"),
            dovit_port=int(opts.get("dovit_port", 6060)),
            enable_discovery=enable_discovery,
            publish_discovery=publish_discovery,
            mqtt_host=opts.get("mqtt_host", "core-mosquitto"),
            mqtt_port=int(opts.get("mqtt_port", 1883)),
            mqtt_user=opts.get("mqtt_user", ""),
            mqtt_pass=opts.get("mqtt_pass", ""),
            alarm_code=str(opts.get("alarm_code", "")),
            devices_file=Path(opts.get("devices_file", "/share/dovit_devices.json")),
            cover_position_mode=str(opts.get("cover_position_mode", "legacy")),
            cover_position_file=Path(opts.get("cover_position_file", "/share/dovit_cover_positions.json")),
        )
    else:
        # Local development: explicit broker options and a local devices file.
        cfg = Config(
            **mqtt_fields,
            dovit_host=opts.get("dovit_host", "127.0.0.1"),
            dovit_port=int(opts.get("dovit_port", 6060)),
            enable_discovery=enable_discovery,
            publish_discovery=publish_discovery,
            mqtt_host=opts.get("mqtt_host", "localhost"),
            mqtt_port=int(opts.get("mqtt_port", 1883)),
            mqtt_user=opts.get("mqtt_user", ""),
            mqtt_pass=opts.get("mqtt_pass", ""),
            alarm_code=str(opts.get("alarm_code", "")),
            devices_file=Path(opts.get("devices_file", "./dovit_devices.json")),
            cover_position_mode=str(opts.get("cover_position_mode", "legacy")),
            cover_position_file=Path(opts.get("cover_position_file", "./dovit_cover_positions.json")),
        )

    object.__setattr__(cfg, "light_statetypes", {0})
    object.__setattr__(cfg, "web_light_control", opts.get("web_light_control") is True)
    object.__setattr__(cfg, "web_device_control", opts.get("web_device_control") is True)
    object.__setattr__(cfg, "shutter_values", {"0.0", "1.0", "2.0"})
    return cfg
