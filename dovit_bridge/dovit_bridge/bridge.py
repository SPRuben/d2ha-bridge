# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
LOGGER = logging.getLogger(__name__)

import asyncio
import time
import os
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, Tuple, Set

from .config import Config
from .light_control import light_frame
from .web_monitor import Monitor
from .alarm_partitions import partition_ids
from .mqtt_client import MqttWrapper
from .mqtt_discovery import (
    discovery_topic,
    light_payload,
    switch_payload,
    cover_payload,
    motion_payload,
    contact_payload,
    alarm_state_payload,
    alarm_text_payload,
    alarm_panel_payload,
    climate_payload,
    dumps,
)
from .topics import (
    DOVIT_STATUS_TOPIC,
    ALARM_HOUSE_AVAILABILITY_TOPIC,
    ALARM_STATE_AVAILABILITY_TOPIC_FMT,
    ALARM_TEXT_AVAILABILITY_TOPIC_FMT,
    LIGHT_CMD_TOPIC_WILDCARD,
    SWITCH_CMD_TOPIC_WILDCARD,
    SWITCH_STATE_TOPIC_FMT,
    SWITCH_TOPIC_RE,
    COVER_CMD_TOPIC_WILDCARD,
    COVER_POSITION_CMD_TOPIC_WILDCARD,
    THERMO_TEMP_CMD_TOPIC_WILDCARD,
    THERMO_MODE_CMD_TOPIC_WILDCARD,
    LIGHT_TOPIC_RE,
    COVER_TOPIC_RE,
    COVER_POSITION_TOPIC_RE,
    THERMO_TEMP_TOPIC_RE,
    LIGHT_STATE_TOPIC_FMT,
    COVER_STATE_TOPIC_FMT,
    COVER_POSITION_STATE_TOPIC_FMT,
    MOTION_STATE_TOPIC_FMT,
    CONTACT_STATE_TOPIC_FMT,
    ALARM_STATE_TOPIC_FMT,
    ALARM_TEXT_TOPIC_FMT,
    ALARM_HOUSE_STATE_TOPIC,
    ALARM_HOUSE_CMD_TOPIC,
    COVER_CMD_TOPIC_FMT,
    COVER_POSITION_CMD_TOPIC_FMT,
    THERMO_TEMP_CMD_TOPIC_FMT,
    THERMO_TARGET_STATE_TOPIC_FMT,
    THERMO_CURRENT_STATE_TOPIC_FMT,
    THERMO_MODE_CMD_TOPIC_FMT,
    THERMO_MODE_STATE_TOPIC_FMT,
    THERMO_MODE_TOPIC_RE,
)
from .storage import (
    load_devices,
    save_devices,
    reload_maps,
    sanity_check_maps,
    is_publishable_name,
    as_int_keys,
    load_cover_positions,
    save_cover_positions,
)
from .dovit_tcp import DovitTcp
from .dovit_parser import extract_hidv_state


MAX_RECEIVE_FRAME_BYTES = 1024 * 1024
MAX_OBSERVED_ENDPOINTS = 2000
_CAPTURE_WRITER = object()


def finite_telemetry_value(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Telemetry must be finite")
    return number


def thermostat_command_value(temperature: float, info: dict) -> str:
    """Keep the final one-decimal wire value inside the configured range."""
    try:
        minimum = float(info.get('min_temp', 5.0))
        maximum = float(info.get('max_temp', 35.0))
        step = float(info.get('temp_step', 0.5))
        if (not all(math.isfinite(number) for number in (temperature, minimum, maximum, step))
                or minimum >= maximum or step <= 0):
            raise ValueError()
        temperature = max(minimum, min(maximum, temperature))
        steps = temperature / step
        if not math.isfinite(steps):
            raise ValueError()
        temperature = max(minimum, min(maximum, round(steps) * step))
        value = f'{temperature:.1f}'
        # Bounds need not align with either the step or the wire precision.
        if float(value) < minimum:
            value = f'{math.ceil(minimum * 10) / 10:.1f}'
        elif float(value) > maximum:
            value = f'{math.floor(maximum * 10) / 10:.1f}'
        if not minimum <= float(value) <= maximum:
            raise ValueError()
        return value
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Invalid thermostat command range or precision') from None


@dataclass
class CoverRuntime:
    direction: str | None = None
    started_at: float = 0.0
    start_position: int = 100
    target_position: int | None = None
    expected_completion_at: float = 0.0
    stop_for_target: bool = False
    stop_task: asyncio.Task | None = None
    ticker_task: asyncio.Task | None = None
    pending_direction: str | None = None
    command_writer: object = None

class DovitBridge:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.monitor = Monitor((cfg.mqtt_pass, cfg.alarm_code))
        self.loop: asyncio.AbstractEventLoop | None = None

        # device maps (int -> dict)
        self.switches: Dict[int, dict] = {}
        self.lights: Dict[int, dict] = {}
        self.shutters: Dict[int, dict] = {}
        self.thermostats: Dict[int, dict] = {}
        self.motions: Dict[int, dict] = {}
        self.contacts: Dict[int, dict] = {}
        self.alarms: Dict[int, dict] = {}
        self.cover_positions: Dict[int, int] = load_cover_positions(self.cfg.cover_position_file)
        self.cover_runtime: Dict[int, CoverRuntime] = {}
        self.cover_last_published_positions: Dict[int, int] = {}
        self.reload_device_maps()
        self.alarm_partition_raw_states: Dict[int, float] = {}
        self.alarm_partition_triggered: Set[int] = set()
        self.pending_alarm_house_state: str | None = None
        self._dovit_connected = False
        self._session_diagnostics_dirty = True
        self._state_cache = {}
        self._alarm_session_readings: Dict[int, float] = {}
        self._alarm_session_triggers: Set[int] = set()
        self._alarm_session_states = {}
        self._alarm_session_texts = {}
        self._alarm_session_house_state = None
        self._alarm_last_accepted_house_state = None

        # observer / shutter candidates
        self.seen_unknown: Set[Tuple[int, int]] = set()
        self.shutter_candidate_values: Dict[Tuple[int, int], Set[str]] = {}
        self._observed_endpoint_limit_warned = False

        # MQTT
        self.mqtt = MqttWrapper(cfg.mqtt_host, cfg.mqtt_port, cfg.mqtt_user, cfg.mqtt_pass,
                                tls=cfg.mqtt_tls, protocol=cfg.mqtt_protocol)
        self.monitor.secrets = tuple(value for value in
            (cfg.mqtt_user, cfg.mqtt_pass, cfg.alarm_code, os.environ.get('SUPERVISOR_TOKEN', '')) if value)
        self.mqtt.defer_online = True
        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_message = self.on_message
        self.monitor.runtime_status = self.setup_status

        # Dovit TCP
        self.dovit = DovitTcp(cfg.dovit_host, cfg.dovit_port)

    def setup_status(self):
        """Read-only facts; broker connection is not HA/HomeKit acceptance."""
        diagnostic = self.mqtt.diagnostics() if hasattr(self.mqtt, 'diagnostics') else {}
        return dict(mqtt_connected=bool(self.mqtt.connected),
                    discovery_publishing=bool(self.cfg.enable_discovery or self.cfg.publish_discovery),
                    automatic_discovery=bool(self.cfg.enable_discovery),
                    mqtt_mode=getattr(self.cfg, 'mqtt_mode', 'manual'),
                    mqtt_state=diagnostic.get('state', 'unknown'),
                    mqtt_changed_at=diagnostic.get('last_change'),
                    configuration_error=None,
                    dovit_state='connected' if getattr(getattr(self, 'monitor', None), 'connected', False) else 'disconnected')

    def reload_device_maps(self):
        self.unassigned_endpoints = set(load_devices(self.cfg.devices_file).get('_unassigned_endpoints', []))
        self.lights, self.shutters, self.thermostats, self.motions, self.contacts, self.alarms = reload_maps(self.cfg.devices_file)
        self.switches = as_int_keys(load_devices(self.cfg.devices_file).get("switches", {}))
        sanity_check_maps(self.lights, self.shutters)
        self.refresh_monitor_routes()
        LOGGER.info('%s', f"DEBUG: Devices file path = {self.cfg.devices_file}")
        LOGGER.info('%s', f"DEBUG: Devices file exists = {self.cfg.devices_file.exists()}")
        LOGGER.info('%s', f"DEBUG: Loaded lights = {list(self.lights.keys())}")
        LOGGER.info('%s', f"DEBUG: Loaded shutters = {list(self.shutters.keys())}")
        LOGGER.info('%s', f"DEBUG: Loaded thermostats = {list(self.thermostats.keys())}")
        LOGGER.info('%s', f"DEBUG: Loaded motions = {list(self.motions.keys())}")
        LOGGER.info('%s', f"DEBUG: Loaded contacts = {list(self.contacts.keys())}")
        LOGGER.info('%s', f"DEBUG: Loaded alarms = {list(self.alarms.keys())}")
        self.initialize_cover_positions()
        LOGGER.info('%s', f"DEBUG: Loaded cover positions = {self.cover_positions}")

    def refresh_monitor_routes(self):
        """Reflect active maps only; pending editor drafts are never live routes."""
        self.monitor.configure({name: getattr(self, name, {}) for name in
                                ("lights", "switches", "shutters", "thermostats", "motions", "contacts", "alarms")}, include_system=True)

    # -------------------
    # Covers
    # -------------------
    def normalize_cover_position(self, value: float | int) -> int:
        return max(0, min(100, int(round(float(value)))))

    def cover_travel_time(self, info: dict, direction: str) -> float:
        fallback = float(info.get("travel_time", 0.0) or 0.0)
        if direction == "opening":
            return float(info.get("travel_time_up", fallback) or 0.0)
        return float(info.get("travel_time_down", fallback) or 0.0)

    def cover_supports_position(self, dev_id: int, info: dict | None = None) -> bool:
        if self.cfg.cover_position_mode.strip().lower() != "timed":
            return False

        info = info or self.shutters.get(dev_id) or {}
        if str(info.get("position_mode", "timed")).strip().lower() == "legacy":
            return False

        try:
            times = [self.cover_travel_time(info, d) for d in ("opening", "closing")]
            return all(math.isfinite(t) and t > 0 for t in times)
        except (TypeError, ValueError):
            return False

    def cover_open_position(self, info: dict) -> int:
        return self.normalize_cover_position(info.get("open_position", 100))

    def cover_close_position(self, info: dict) -> int:
        return self.normalize_cover_position(info.get("close_position", 0))

    def cover_default_position(self, info: dict) -> int:
        return self.normalize_cover_position(info.get("initial_position", 100))

    def initialize_cover_positions(self) -> None:
        changed = False
        for dev_id, info in self.shutters.items():
            if not self.cover_supports_position(dev_id, info):
                continue
            if dev_id not in self.cover_positions:
                self.cover_positions[dev_id] = self.cover_default_position(info)
                changed = True
        if changed:
            self.persist_cover_positions()

    def persist_cover_positions(self) -> None:
        save_cover_positions(self.cfg.cover_position_file, self.cover_positions)

    def get_cover_runtime(self, dev_id: int, info: dict | None = None) -> CoverRuntime:
        runtime = self.cover_runtime.get(dev_id)
        if runtime is None:
            runtime = CoverRuntime(start_position=self.cover_positions.get(dev_id, self.cover_default_position(info or {})))
            self.cover_runtime[dev_id] = runtime
        return runtime

    def cancel_cover_stop_task(self, runtime: CoverRuntime) -> None:
        if runtime.stop_task and not runtime.stop_task.done():
            runtime.stop_task.cancel()
        runtime.stop_task = None
        runtime.expected_completion_at = 0.0
        runtime.stop_for_target = False

    def cancel_cover_ticker_task(self, runtime: CoverRuntime) -> None:
        if runtime.ticker_task and not runtime.ticker_task.done():
            runtime.ticker_task.cancel()
        runtime.ticker_task = None

    def estimate_cover_position(self, dev_id: int, info: dict, now: float | None = None) -> int:
        runtime = self.get_cover_runtime(dev_id, info)
        base_position = self.cover_positions.get(dev_id, runtime.start_position)

        if runtime.direction not in ("opening", "closing"):
            return self.normalize_cover_position(base_position)

        timestamp = time.monotonic() if now is None else now
        elapsed = max(0.0, timestamp - runtime.started_at)
        travel_time = self.cover_travel_time(info, runtime.direction)
        if travel_time <= 0:
            return self.normalize_cover_position(base_position)

        delta = (elapsed / travel_time) * 100.0
        if runtime.direction == "opening":
            position = runtime.start_position + delta
            position = min(position, 100)
        else:
            position = runtime.start_position - delta
            position = max(position, 0)

        return self.normalize_cover_position(position)

    def publish_cover_position(self, dev_id: int, info: dict, position: int | None = None, force: bool = False) -> None:
        if not self.cover_supports_position(dev_id, info):
            return
        if not self.mqtt.connected:
            return

        current = self.normalize_cover_position(
            self.estimate_cover_position(dev_id, info) if position is None else position
        )
        if not force and self.cover_last_published_positions.get(dev_id) == current:
            return

        topic = COVER_POSITION_STATE_TOPIC_FMT.format(id=dev_id)
        result = self.mqtt.publish(topic, str(current), qos=1, retain=True)
        if result.rc != 0:
            return
        self.cover_last_published_positions[dev_id] = current
        LOGGER.info('%s', f"Dovit -> MQTT (cover position): id={dev_id} position={current}")

    async def cover_position_ticker(self, dev_id: int) -> None:
        try:
            while True:
                await asyncio.sleep(0.5)
                info = self.shutters.get(dev_id)
                runtime = self.cover_runtime.get(dev_id)
                if not info or not runtime or runtime.direction not in ("opening", "closing"):
                    return
                self.publish_cover_position(dev_id, info)
        except asyncio.CancelledError:
            return

    def ensure_cover_ticker(self, dev_id: int, runtime: CoverRuntime) -> None:
        if not self.loop:
            return
        if runtime.ticker_task and not runtime.ticker_task.done():
            return
        runtime.ticker_task = self.loop.create_task(self.cover_position_ticker(dev_id))

    def start_cover_motion(self, dev_id: int, info: dict, direction: str) -> None:
        runtime = self.get_cover_runtime(dev_id, info)

        if runtime.direction == direction:
            self.publish_cover_position(dev_id, info)
            return

        current_position = self.estimate_cover_position(dev_id, info)

        if runtime.direction and runtime.direction != direction:
            self.cancel_cover_stop_task(runtime)
            runtime.target_position = None

        runtime.direction = direction
        runtime.started_at = time.monotonic()
        runtime.start_position = current_position

        if runtime.pending_direction == direction:
            runtime.pending_direction = None
            self.schedule_cover_target_stop(dev_id, info)
        else:
            runtime.pending_direction = None
            runtime.target_position = None

        if runtime.target_position is not None:
            if direction == "opening" and runtime.target_position < current_position:
                runtime.target_position = None
            elif direction == "closing" and runtime.target_position > current_position:
                runtime.target_position = None

        self.ensure_cover_ticker(dev_id, runtime)
        self.publish_cover_position(dev_id, info, current_position, force=True)

    def finish_cover_motion(self, dev_id: int, info: dict) -> int:
        runtime = self.get_cover_runtime(dev_id, info)

        if runtime.direction in ("opening", "closing"):
            final_position = self.estimate_cover_position(dev_id, info)
        else:
            final_position = self.cover_positions.get(dev_id, self.cover_default_position(info))

        runtime.direction = None
        runtime.started_at = 0.0
        runtime.start_position = final_position
        runtime.target_position = None
        runtime.pending_direction = None
        runtime.expected_completion_at = 0.0
        runtime.stop_for_target = False

        self.cancel_cover_stop_task(runtime)
        self.cancel_cover_ticker_task(runtime)

        self.cover_positions[dev_id] = final_position
        self.persist_cover_positions()
        self.publish_cover_position(dev_id, info, final_position, force=True)
        return final_position

    def send_cover_frame(self, dev_id: int, statetype: int, value: str, reason: str,
                         *, expected_writer=_CAPTURE_WRITER) -> None:
        xml = (
            f"<hidv-state>"
            f"<device id=\"{dev_id}\">"
            f"<statetype>{statetype}</statetype>"
            f"<statevalue>{value}</statevalue>"
            f"<timefleeting>-32768</timefleeting>"
            f"<endvalue>-32768</endvalue>"
            f"<speed>-32768</speed>"
            f"</device>"
            f"</hidv-state>"
        )

        LOGGER.info('%s', f"MQTT cmd -> Dovit (cover): id={dev_id} {reason} value={value}")
        asyncio.create_task(self.send_frame(xml, expected_writer=expected_writer))

    async def delayed_cover_stop(self, dev_id: int, statetype: int, delay: float,
                                 *, expected_writer) -> None:
        try:
            await asyncio.sleep(max(0.0, delay))
            if not self._command_writer_valid(expected_writer):
                return
            runtime = self.cover_runtime.get(dev_id)
            if not runtime:
                return
            runtime.stop_for_target = True
            self.send_cover_frame(dev_id, statetype, "0.0", "timed stop",
                                  expected_writer=expected_writer)
        except asyncio.CancelledError:
            return
        finally:
            runtime = self.cover_runtime.get(dev_id)
            current = asyncio.current_task()
            if runtime and runtime.stop_task is current:
                runtime.stop_task = None

    def schedule_cover_target_stop(self, dev_id: int, info: dict) -> None:
        runtime = self.get_cover_runtime(dev_id, info)
        self.cancel_cover_stop_task(runtime)
        if runtime.target_position is None or runtime.direction is None:
            return
        # Endpoints use Dovit's full run so an estimated position can resynchronise.
        if runtime.target_position in (0, 100):
            return
        current = self.estimate_cover_position(dev_id, info)
        delay = self.cover_travel_time(info, runtime.direction) * abs(runtime.target_position - current) / 100
        statetype = int(info.get("command_statetype", info["statetype"]))
        runtime.stop_task = self.loop.create_task(self.delayed_cover_stop(
            dev_id, statetype, delay, expected_writer=runtime.command_writer))

    def handle_cover_target_position(self, dev_id: int, target_position: int, source: str = "position",
                                     *, expected_writer=_CAPTURE_WRITER) -> None:
        expected_writer = self._capture_command_writer(expected_writer)
        if not self._command_writer_valid(expected_writer):
            return
        info = self.shutters.get(dev_id)
        if not info or not self.cover_supports_position(dev_id, info):
            LOGGER.warning('%s', f"Ignoring {source} command for non-timed cover id={dev_id}")
            return

        statetype = int(info.get("command_statetype", info["statetype"]))
        runtime = self.get_cover_runtime(dev_id, info)
        runtime.command_writer = expected_writer
        current_position = self.estimate_cover_position(dev_id, info)
        target_position = self.normalize_cover_position(target_position)

        if runtime.pending_direction:
            runtime.pending_direction = None
            runtime.target_position = None
            self.cancel_cover_stop_task(runtime)
            self.send_cover_frame(dev_id, statetype, "0.0", "cancel pending move; resend target after stop", expected_writer=expected_writer)
            return

        if abs(target_position - current_position) < 1 and target_position not in (0, 100):
            LOGGER.info('%s', f"Cover target already reached: id={dev_id} target={target_position}")
            if runtime.direction in ("opening", "closing"):
                runtime.target_position = None
                self.cancel_cover_stop_task(runtime)
                self.send_cover_frame(dev_id, statetype, "0.0", f"{source} hold", expected_writer=expected_writer)
            self.cover_positions[dev_id] = current_position
            self.persist_cover_positions()
            self.publish_cover_position(dev_id, info, current_position, force=True)
            return

        direction = "opening" if target_position == 100 or target_position > current_position else "closing"
        if runtime.direction and runtime.direction != direction:
            runtime.target_position = None
            self.cancel_cover_stop_task(runtime)
            self.send_cover_frame(dev_id, statetype, "0.0", "reverse requested; resend target after stop", expected_writer=expected_writer)
            return
        travel_time = self.cover_travel_time(info, direction)
        if travel_time <= 0:
            LOGGER.warning('%s', f"Ignoring {source} command for cover id={dev_id}: missing travel time.")
            return

        value = "1.0" if direction == "opening" else "2.0"

        self.cancel_cover_stop_task(runtime)
        runtime.target_position = target_position
        if runtime.direction == direction:
            self.schedule_cover_target_stop(dev_id, info)
            return
        runtime.pending_direction = direction

        self.send_cover_frame(dev_id, statetype, value, f"{source} -> {target_position}%", expected_writer=expected_writer)

    def handle_cover_command(self, dev_id: int, payload: str,
                             *, expected_writer=_CAPTURE_WRITER) -> None:
        expected_writer = self._capture_command_writer(expected_writer)
        if not self._command_writer_valid(expected_writer):
            return
        info = self.shutters.get(dev_id)
        if not info:
            LOGGER.warning('%s', f"Ignoring command for unknown shutter id={dev_id}")
            return

        statetype = int(info.get("command_statetype", info["statetype"]))
        runtime = self.get_cover_runtime(dev_id, info)

        if self.cover_supports_position(dev_id, info):
            if payload == "OPEN":
                self.handle_cover_target_position(dev_id, self.cover_open_position(info), source="open", expected_writer=expected_writer)
                return
            if payload in ("CLOSE", "CLOSED"):
                self.handle_cover_target_position(dev_id, self.cover_close_position(info), source="close", expected_writer=expected_writer)
                return
            if payload == "STOP":
                runtime.pending_direction = None
                runtime.target_position = None
                runtime.stop_for_target = False
                self.cancel_cover_stop_task(runtime)
                self.send_cover_frame(dev_id, statetype, "0.0", "stop", expected_writer=expected_writer)
                return
        else:
            if payload == "OPEN":
                value = "1.0"
            elif payload == "STOP":
                value = "0.0"
            else:
                value = "2.0"
            self.send_cover_frame(dev_id, statetype, value, payload.lower(), expected_writer=expected_writer)

    def publish_all_cover_positions(self) -> None:
        for dev_id, info in sorted(self.shutters.items(), key=lambda item: item[0]):
            if self.cover_supports_position(dev_id, info):
                self.publish_cover_position(dev_id, info, force=True)

    def reset_cover_motion(self) -> None:
        # Never replay an old scheduled STOP into a new TCP session.
        for runtime in self.cover_runtime.values():
            self.cancel_cover_stop_task(runtime)
            self.cancel_cover_ticker_task(runtime)
            runtime.direction = None
            runtime.pending_direction = None
            runtime.target_position = None
            runtime.command_writer = None

    # -------------------
    # MQTT callbacks
    # -------------------
    def _require_bridge_loop(self):
        if self.loop is None or asyncio.get_running_loop() is not self.loop:
            raise RuntimeError('Dovit session lifecycle must run on the bridge loop')

    def set_dovit_connected(self, connected: bool):
        self._require_bridge_loop()
        self.monitor.connected = bool(connected)
        if (getattr(self, '_session_initialized', False)
                and self._dovit_connected == bool(connected)):
            if getattr(self, '_session_diagnostics_dirty', False):
                self.republish_session_status()
            return
        self._session_initialized = True
        self._dovit_connected = bool(connected)
        self.alarm_partition_raw_states.clear()
        self.alarm_partition_triggered.clear()
        self.pending_alarm_house_state = None
        self._alarm_session_readings = {}
        self._alarm_session_triggers = set()
        self._alarm_session_states = {}
        self._alarm_session_texts = {}
        self._alarm_session_house_state = None
        self._alarm_last_accepted_house_state = None
        self._state_cache = {}
        self.republish_session_status()

    def _state_routes(self):
        routes = {}
        for category, topic_fmt in (
            ('lights', LIGHT_STATE_TOPIC_FMT), ('switches', SWITCH_STATE_TOPIC_FMT), ('shutters', COVER_STATE_TOPIC_FMT),
            ('motions', MOTION_STATE_TOPIC_FMT), ('contacts', CONTACT_STATE_TOPIC_FMT),
        ):
            for key, info in getattr(self, category, {}).items():
                try:
                    routes[topic_fmt.format(id=key)] = (category, key, 'state', key, int(info['statetype']))
                except (KeyError, TypeError, ValueError):
                    continue
        for key, info in getattr(self, 'thermostats', {}).items():
            for role, topic_fmt in (
                ('target', THERMO_TARGET_STATE_TOPIC_FMT),
                ('current', THERMO_CURRENT_STATE_TOPIC_FMT), ('mode', THERMO_MODE_STATE_TOPIC_FMT),
            ):
                try:
                    endpoint = info.get(role, {}) or {}
                    # Mirror the existing receive path: target telemetry uses the map key.
                    dev_id = key if role == 'target' else int(endpoint.get('id', -1))
                    statetype = int(endpoint.get('statetype', -1))
                except (AttributeError, TypeError, ValueError):
                    continue
                if dev_id >= 0 and statetype >= 0:
                    routes[topic_fmt.format(id=key)] = ('thermostats', key, role, dev_id, statetype)
        return routes

    def _prune_state_cache(self):
        routes = self._state_routes()
        cache = getattr(self, '_state_cache', {})
        self._state_cache = {topic: entry for topic, entry in cache.items()
                             if routes.get(topic) == entry[0]}
        return routes

    def _publish_received_state(self, topic, payload, dev_id, statetype):
        if not getattr(self, '_session_initialized', False):
            self.mqtt.publish(topic, payload, qos=1, retain=True)
            return
        self._require_bridge_loop()
        if not self._dovit_connected:
            return
        route = self._prune_state_cache().get(topic)
        if route is None or route[-2:] != (dev_id, statetype):
            return
        if route[0] == 'shutters' and payload not in ('opening', 'closing', 'stopped'):
            self._state_cache.pop(topic, None)
        else:
            self._state_cache[topic] = (route, payload)
        self._publish_session_diagnostic(topic, payload)

    def _alarm_session_fresh(self):
        if not getattr(self, '_dovit_connected', False):
            return False
        try:
            roles = partition_ids(self.alarms)
        except ValueError:
            return False
        if set(roles) != {'motion', 'contact'}:
            return False
        ids = set(roles.values())
        readings = self._alarm_session_readings
        return bool(ids & self._alarm_session_triggers) or all(
            dev_id in readings and math.isfinite(readings[dev_id]) for dev_id in ids)

    def republish_session_status(self):
        self._require_bridge_loop()
        dovit_ok = self._publish_session_diagnostic(DOVIT_STATUS_TOPIC,
                                         'online' if getattr(self, '_dovit_connected', False) else 'offline')
        results = [dovit_ok]
        active = getattr(self, '_dovit_connected', False)
        self._prune_state_cache()
        if active:
            for topic, (_, payload) in self._state_cache.items():
                results.append(self._publish_session_diagnostic(topic, payload))
        for dev_id in self.alarms:
            for cache_name, state_fmt, availability_fmt, eligible in (
                ('_alarm_session_states', ALARM_STATE_TOPIC_FMT, ALARM_STATE_AVAILABILITY_TOPIC_FMT,
                 (dev_id in self._alarm_session_readings
                  or dev_id in self._alarm_session_triggers) if active else False),
                ('_alarm_session_texts', ALARM_TEXT_TOPIC_FMT, ALARM_TEXT_AVAILABILITY_TOPIC_FMT, active),
            ):
                value = getattr(self, cache_name, {}).get(dev_id)
                ready = False
                if active and value is not None:
                    accepted = self._publish_session_diagnostic(state_fmt.format(id=dev_id), value)
                    results.append(accepted)
                    ready = accepted and eligible
                results.append(self._publish_session_diagnostic(
                    availability_fmt.format(id=dev_id), 'online' if ready else 'offline'))
        house = getattr(self, '_alarm_session_house_state', None)
        house_ready = False
        if active and house is not None and self._alarm_session_fresh():
            house_ready = self._publish_session_diagnostic(ALARM_HOUSE_STATE_TOPIC, house)
            results.append(house_ready)
            if house_ready:
                self._alarm_last_accepted_house_state = house
        alarm_ok = self._publish_session_diagnostic(ALARM_HOUSE_AVAILABILITY_TOPIC,
                                         'online' if house_ready else 'offline')
        results.append(alarm_ok)
        self._session_diagnostics_dirty = not all(results)
        if not self._session_diagnostics_dirty:
            try:
                self._session_diagnostics_dirty = not self.mqtt.mark_online()
            except Exception as exc:
                self._session_diagnostics_dirty = True
                LOGGER.error('MQTT online announcement failed type=%s', type(exc).__name__)

    async def session_status_retry_loop(self):
        self._require_bridge_loop()
        while True:
            await asyncio.sleep(3)
            if getattr(self, '_session_diagnostics_dirty', False):
                self.republish_session_status()

    def _publish_session_diagnostic(self, topic, payload):
        if not self.mqtt.connected:
            self._session_diagnostics_dirty = True
            return False
        try:
            result = self.mqtt.publish(topic, payload, qos=1, retain=True)
            if result.rc == 0:
                return True
            LOGGER.error('Session diagnostic publish failed topic=%s rc=%s', topic, result.rc)
        except Exception as exc:
            LOGGER.error('Session diagnostic publish failed topic=%s type=%s',
                         topic, type(exc).__name__)
        self._session_diagnostics_dirty = True
        return False

    def _record_alarm_session_evidence(self, dev_id, *, reading=None, triggered=False):
        # Separate diagnostics from legacy aggregation and direct offline fixtures.
        if not getattr(self, '_dovit_connected', False):
            return
        self._require_bridge_loop()
        if reading is not None and math.isfinite(reading):
            self._alarm_session_readings[dev_id] = reading
            if reading < 0.5:
                self._alarm_session_triggers.discard(dev_id)
        if triggered:
            self._alarm_session_triggers.add(dev_id)

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        LOGGER.info('%s %s', "MQTT connected:", reason_code)
        if self.loop is not None and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._republish_after_mqtt_connect)

        client.subscribe(SWITCH_CMD_TOPIC_WILDCARD)
        LOGGER.info("Subscribed: %s", SWITCH_CMD_TOPIC_WILDCARD)
        client.subscribe(LIGHT_CMD_TOPIC_WILDCARD)
        LOGGER.info('%s %s', "Subscribed:", LIGHT_CMD_TOPIC_WILDCARD)

        client.subscribe(COVER_CMD_TOPIC_WILDCARD)
        LOGGER.info('%s %s', "Subscribed:", COVER_CMD_TOPIC_WILDCARD)

        client.subscribe(COVER_POSITION_CMD_TOPIC_WILDCARD)
        LOGGER.info('%s %s', "Subscribed:", COVER_POSITION_CMD_TOPIC_WILDCARD)

        client.subscribe(THERMO_TEMP_CMD_TOPIC_WILDCARD)
        LOGGER.info('%s %s', "Subscribed:", THERMO_TEMP_CMD_TOPIC_WILDCARD)

        client.subscribe(THERMO_MODE_CMD_TOPIC_WILDCARD)
        LOGGER.info('%s %s', "Subscribed:", THERMO_MODE_CMD_TOPIC_WILDCARD)

        client.subscribe(ALARM_HOUSE_CMD_TOPIC)
        LOGGER.info('%s %s', "Subscribed:", ALARM_HOUSE_CMD_TOPIC)

    def _republish_after_mqtt_connect(self):
        self._require_bridge_loop()
        if not self.mqtt.connected:
            return
        if self._discovery_publication_enabled():
            self.publish_all_discovery_once(reason="connect")
        else:
            LOGGER.info('%s', "[DISCOVERY] Publication disabled. Skipping publish on connect.")
        self.republish_session_status()

    def _capture_command_writer(self, expected_writer=_CAPTURE_WRITER):
        if expected_writer is _CAPTURE_WRITER:
            return getattr(getattr(self, 'dovit', None), 'writer', None)
        return expected_writer

    def _command_writer_valid(self, writer):
        valid = (writer is not None
                 and writer is getattr(getattr(self, 'dovit', None), 'writer', None)
                 and not writer.is_closing())
        if not valid:
            LOGGER.warning('Dovit command rejected: accepted transport no longer attached; no replay')
        return valid

    def _schedule_session_command(self, factory, *, expected_writer=_CAPTURE_WRITER):
        writer = self._capture_command_writer(expected_writer)
        if not self.loop:
            return

        def dispatch():
            if not self._command_writer_valid(writer):
                return
            result = factory(writer)
            if result is not None:
                self.loop.create_task(result)

        self.loop.call_soon_threadsafe(dispatch)

    async def _send_alarm_group(self, frames, pending_state, expected_writer):
        if not self._command_writer_valid(expected_writer):
            return
        self.pending_alarm_house_state = pending_state
        for xml in frames:
            if not await self.send_frame(xml, expected_writer=expected_writer):
                return

    def on_message(self, client, userdata, msg):
        accepted_writer = self._capture_command_writer()
        LOGGER.info("MQTT RX topic=%s payload_bytes=%s retained=%s", msg.topic, len(msg.payload), getattr(msg, "retain", False))
        # Commands describe present intent; retained broker history must not operate devices.
        if getattr(msg, 'retain', False):
            LOGGER.warning('Ignoring retained MQTT command topic=%s', msg.topic)
            return

        if msg.topic == ALARM_HOUSE_CMD_TOPIC:
            try:
                roles = partition_ids(self.alarms)
            except ValueError:
                LOGGER.error('Alarm partition roles are ambiguous; command rejected')
                return
            payload = msg.payload.decode("utf-8", errors="ignore").strip().upper()
            if payload != 'DISARM' and set(roles) != {'motion', 'contact'}:
                LOGGER.error('Both alarm partition roles are required for arming')
                return
            if payload == "DISARM":
                actions = [(dev_id, 0) for dev_id in roles.values()]
                pending_state = "disarmed"
            elif payload == "ARM_HOME":
                actions = [(roles['motion'], 0), (roles['contact'], 1)]
                pending_state = "armed_home"
            elif payload == "ARM_AWAY":
                actions = [(roles['motion'], 1), (roles['contact'], 1)]
                pending_state = "armed_away"
            else:
                LOGGER.warning("Ignoring unknown alarm command; payload omitted")
                return

            if not self.loop:
                LOGGER.error('%s', "ERROR: asyncio loop not set, cannot send to Dovit.")
                return

            frames = []
            for dev_id, value in actions:
                command_statetype = int(self.alarms[dev_id].get('command_statetype', 0))
                xml = (
                    f"<hidv-state>"
                    f"<device id=\"{dev_id}\">"
                    f"<statetype>{command_statetype}</statetype>"
                    f"<statevalue>{value}</statevalue>"
                    f"<timefleeting>-32768</timefleeting>"
                    f"<endvalue>-32768</endvalue>"
                    f"<speed>-32768</speed>"
                    f"</device>"
                    f"</hidv-state>"
                )
                LOGGER.info('%s', f"MQTT cmd -> Dovit (alarm): dev_id={dev_id} action={payload} value={value}")
                frames.append(xml)
            self._schedule_session_command(lambda writer: self._send_alarm_group(frames, pending_state, writer), expected_writer=accepted_writer)
            return

        mp = COVER_POSITION_TOPIC_RE.match(msg.topic)
        if mp:
            if getattr(msg, "retain", False):
                LOGGER.warning('%s', "Ignoring retained cover position command")
                return
            dev_id = int(mp.group(1))
            if dev_id not in self.shutters:
                LOGGER.warning('%s', f"Ignoring position command for unknown shutter id={dev_id} topic={msg.topic}")
                return

            payload_raw = msg.payload.decode("utf-8", errors="ignore").strip()
            try:
                target_position = self.normalize_cover_position(float(payload_raw))
            except Exception:
                LOGGER.warning("Ignoring invalid cover position command id=%s", dev_id)
                return

            if not self.loop:
                LOGGER.error('%s', "ERROR: asyncio loop not set, cannot schedule cover position command.")
                return

            self._schedule_session_command(lambda writer: self.handle_cover_target_position(
                dev_id, target_position, 'set_position', expected_writer=writer), expected_writer=accepted_writer)
            return

        # COVER COMMANDS
        mc = COVER_TOPIC_RE.match(msg.topic)
        if mc:
            dev_id = int(mc.group(1))
            if dev_id not in self.shutters:
                LOGGER.warning('%s', f"Ignoring command for unknown shutter id={dev_id} topic={msg.topic}")
                return

            payload = msg.payload.decode("utf-8", errors="ignore").strip().upper()
            if payload == "OPEN":
                value = "1.0"
            elif payload == "STOP":
                value = "0.0"
            elif payload in ("CLOSE", "CLOSED"):
                value = "2.0"
            else:
                LOGGER.warning("Ignoring invalid cover command id=%s", dev_id)
                return

            if not self.loop:
                LOGGER.error('%s', "ERROR: asyncio loop not set, cannot schedule cover command.")
                return

            if self.cover_supports_position(dev_id, self.shutters[dev_id]):
                self._schedule_session_command(lambda writer: self.handle_cover_command(
                    dev_id, payload, expected_writer=writer), expected_writer=accepted_writer)
            else:
                info = self.shutters[dev_id]
                statetype = int(info.get("command_statetype", info["statetype"]))
                xml = (
                    f"<hidv-state>"
                    f"<device id=\"{dev_id}\">"
                    f"<statetype>{statetype}</statetype>"
                    f"<statevalue>{value}</statevalue>"
                    f"<timefleeting>-32768</timefleeting>"
                    f"<endvalue>-32768</endvalue>"
                    f"<speed>-32768</speed>"
                    f"</device>"
                    f"</hidv-state>"
                )

                LOGGER.info('%s', f"MQTT cmd -> Dovit (cover): id={dev_id} payload={payload} value={value}")
                self._schedule_session_command(lambda writer: self.send_frame(xml, expected_writer=writer), expected_writer=accepted_writer)
            return
        
        # THERMOSTATS COMMANDS
        mt = THERMO_TEMP_TOPIC_RE.match(msg.topic)
        if mt:
            target_id = int(mt.group(1))
            if target_id not in self.thermostats:
                LOGGER.warning('%s', f"Ignoring command for unknown thermostat target id={target_id}")
                return

            payload_raw = msg.payload.decode("utf-8", errors="ignore").strip()
            try:
                # HA schickt z.B. "22.0"
                temp = float(payload_raw)
                if not math.isfinite(temp):
                    raise ValueError('Temperature must be finite')
            except Exception:
                LOGGER.warning("Ignoring invalid thermostat command id=%s", target_id)
                return

            info = self.thermostats[target_id]
            statetype = int(info.get("target", {}).get("statetype", 1))

            try:
                value = thermostat_command_value(temp, info)
            except ValueError:
                LOGGER.warning("Ignoring thermostat command with invalid range or precision id=%s", target_id)
                return

            xml = (
                f"<hidv-state>"
                f"<device id=\"{target_id}\">"
                f"<statetype>{statetype}</statetype>"
                f"<statevalue>{value}</statevalue>"
                f"<timefleeting>-32768</timefleeting>"
                f"<endvalue>-32768</endvalue>"
                f"<speed>-32768</speed>"
                f"</device>"
                f"</hidv-state>"
            )

            LOGGER.info('%s', f"MQTT cmd -> Dovit (thermostat target): id={target_id} set={value}")
            if not self.loop:
                LOGGER.error('%s', "ERROR: asyncio loop not set, cannot send to Dovit.")
                return
            self._schedule_session_command(lambda writer: self.send_frame(xml, expected_writer=writer), expected_writer=accepted_writer)
            return
        
        mm = THERMO_MODE_TOPIC_RE.match(msg.topic)
        if mm:
            target_id = int(mm.group(1))
            if target_id not in self.thermostats:
                LOGGER.warning('%s', f"Ignoring mode command for unknown thermostat id={target_id}")
                return

            payload = msg.payload.decode("utf-8", errors="ignore").strip().lower()

            # HIER dein Dovit-Mapping anpassen:
            if payload == "heat":
                value = "1.0"
            elif payload == "off":
                value = "0.0"
            else:
                LOGGER.warning("Ignoring invalid thermostat mode command id=%s", target_id)
                return

            info = self.thermostats[target_id]
            mode = info.get("mode", {}) or {}
            mode_id = int(mode.get("id", -1))
            mode_statetype = int(mode.get("statetype", -1))

            if mode_id < 0 or mode_statetype < 0:
                LOGGER.warning('%s', f"Ignoring mode command: thermostat {target_id} has no mode mapping")
                return

            xml = (
                f"<hidv-state>"
                f"<device id=\"{mode_id}\">"
                f"<statetype>{mode_statetype}</statetype>"
                f"<statevalue>{value}</statevalue>"
                f"<timefleeting>-32768</timefleeting>"
                f"<endvalue>-32768</endvalue>"
                f"<speed>-32768</speed>"
                f"</device>"
                f"</hidv-state>"
            )

            LOGGER.info('%s', f"MQTT cmd -> Dovit (thermostat mode): target={target_id} mode_id={mode_id} mode={payload} value={value}")
            if not self.loop:
                LOGGER.error('%s', "ERROR: asyncio loop not set, cannot send to Dovit.")
                return
            self._schedule_session_command(lambda writer: self.send_frame(xml, expected_writer=writer), expected_writer=accepted_writer)
            return

        # Only explicitly mapped switches accept current ON/OFF intent.
        ms = SWITCH_TOPIC_RE.match(msg.topic)
        if ms:
            dev_id = int(ms.group(1))
            if dev_id not in getattr(self, 'switches', {}):
                return
            try:
                payload = msg.payload.decode('utf-8').strip().upper()
            except UnicodeDecodeError:
                return
            if payload not in ('ON', 'OFF'):
                return
            self._schedule_session_command(
                lambda writer: self.send_switch(dev_id, payload, expected_writer=writer),
                expected_writer=accepted_writer)
            return

        # LIGHT COMMANDS
        ml = LIGHT_TOPIC_RE.match(msg.topic)
        if not ml:
            return

        dev_id = int(ml.group(1))
        if dev_id not in self.lights:
            LOGGER.warning('%s', f"Ignoring command for unknown light id={dev_id} topic={msg.topic}")
            return

        payload = msg.payload.decode("utf-8", errors="ignore").strip().upper()
        if payload not in ("ON", "OFF"):
            LOGGER.warning("Ignoring invalid light command id=%s", dev_id)
            return

        LOGGER.info('%s', f"MQTT cmd -> Dovit (light): id={dev_id} payload={payload}")
        self._schedule_session_command(lambda writer: self.send_light(dev_id, payload, expected_writer=writer), expected_writer=accepted_writer)

    def send_switch(self, dev_id, action, *, expected_writer=_CAPTURE_WRITER):
        return self._send_switch(dev_id, action, self._capture_command_writer(expected_writer))

    async def _send_switch(self, dev_id, action, expected_writer):
        info = getattr(self, 'switches', {}).get(dev_id)
        if info is None or action not in ('ON', 'OFF'):
            return False
        return await self.send_frame(light_frame(dev_id, info['statetype'], action),
                                     expected_writer=expected_writer)

    def send_light(self, dev_id, action, *, expected_writer=_CAPTURE_WRITER):
        return self._send_light(dev_id, action, self._capture_command_writer(expected_writer))

    async def _send_light(self, dev_id, action, expected_writer):
        if dev_id not in self.lights:
            return False
        return await self.send_frame(light_frame(dev_id, self.lights[dev_id]['statetype'], action), expected_writer=expected_writer)

    # -------------------
    # Discovery
    # -------------------
    def _discovery_publication_enabled(self):
        return (getattr(self.cfg, 'enable_discovery', False)
                or getattr(self.cfg, 'publish_discovery', False))

    def _discovery_publish_only(self):
        return (getattr(self.cfg, 'publish_discovery', False)
                and not getattr(self.cfg, 'enable_discovery', False))

    def _discovery_name_allowed(self, info):
        return (not self._discovery_publish_only()
                or is_publishable_name(info.get('name', ''), False))

    def publish_light_discovery(self, dev_id: int, info: dict):
        if not self._discovery_publication_enabled() or not self._discovery_name_allowed(info):
            return
        name = info.get("name", f"Dovit Light {dev_id}")
        unique_id = f"dovit_light_{dev_id}"
        topic = discovery_topic(self.cfg.discovery_prefix, "light", unique_id)
        payload = light_payload(self.cfg.discovery_node_id, dev_id, name)
        self.mqtt.publish(topic, dumps(payload), retain=True)
        LOGGER.info('%s %s %s', "Published discovery:", topic, name)

    def publish_switch_discovery(self, dev_id: int, info: dict):
        if not self._discovery_publication_enabled() or not self._discovery_name_allowed(info):
            return
        name = info.get('name', f'Dovit Switch {dev_id}')
        topic = discovery_topic(self.cfg.discovery_prefix, 'switch', f'dovit_switch_{dev_id}')
        self.mqtt.publish(topic, dumps(switch_payload(self.cfg.discovery_node_id, dev_id, name)), retain=True)

    def publish_cover_discovery(self, dev_id: int, info: dict):
        if not self._discovery_publication_enabled() or not self._discovery_name_allowed(info):
            return
        name = info.get("name", f"Dovit Shutter {dev_id}")
        unique_id = f"dovit_cover_{dev_id}"
        topic = discovery_topic(self.cfg.discovery_prefix, "cover", unique_id)
        if self.cover_supports_position(dev_id, info):
            payload = cover_payload(
                self.cfg.discovery_node_id,
                dev_id,
                name,
                position_topic=COVER_POSITION_STATE_TOPIC_FMT.format(id=dev_id),
                set_position_topic=COVER_POSITION_CMD_TOPIC_FMT.format(id=dev_id),
            )
        else:
            payload = cover_payload(self.cfg.discovery_node_id, dev_id, name)
        self.mqtt.publish(topic, dumps(payload), retain=True)
        LOGGER.info('%s %s %s', "Published cover discovery:", topic, name)

    def publish_motion_discovery(self, dev_id: int, info: dict):
        if not self._discovery_publication_enabled() or not self._discovery_name_allowed(info):
            return
        name = info.get("name", f"Dovit Motion {dev_id}")
        unique_id = f"dovit_motion_{dev_id}"
        topic = discovery_topic(self.cfg.discovery_prefix, "binary_sensor", unique_id)
        payload = motion_payload(self.cfg.discovery_node_id, dev_id, name)
        self.mqtt.publish(topic, dumps(payload), retain=True)
        LOGGER.info('%s %s %s', "Published motion discovery:", topic, name)

    def publish_contact_discovery(self, dev_id: int, info: dict):
        if not self._discovery_publication_enabled() or not self._discovery_name_allowed(info):
            return
        name = info.get("name", f"Dovit Contact {dev_id}")
        unique_id = f"dovit_contact_{dev_id}"
        topic = discovery_topic(self.cfg.discovery_prefix, "binary_sensor", unique_id)
        payload = contact_payload(
            self.cfg.discovery_node_id,
            dev_id,
            name,
            device_class=str(info.get("device_class", "door")),
        )
        self.mqtt.publish(topic, dumps(payload), retain=True)
        LOGGER.info('%s %s %s', "Published contact discovery:", topic, name)

    def publish_alarm_discovery(self, dev_id: int, info: dict):
        if not self._discovery_publication_enabled() or not self._discovery_name_allowed(info):
            return
        name = info.get("name", f"Dovit Alarm {dev_id}")

        state_unique_id = f"dovit_alarm_state_{dev_id}"
        state_topic = discovery_topic(self.cfg.discovery_prefix, "sensor", state_unique_id)
        state_payload = alarm_state_payload(self.cfg.discovery_node_id, dev_id, name)
        self.mqtt.publish(state_topic, dumps(state_payload), retain=True)
        LOGGER.info('%s %s %s', "Published alarm state discovery:", state_topic, name)

        text_unique_id = f"dovit_alarm_text_{dev_id}"
        text_topic = discovery_topic(self.cfg.discovery_prefix, "sensor", text_unique_id)
        text_payload = alarm_text_payload(self.cfg.discovery_node_id, dev_id, f"{name} Text")
        self.mqtt.publish(text_topic, dumps(text_payload), retain=True)
        LOGGER.info('%s %s %s', "Published alarm text discovery:", text_topic, name)

    def publish_alarm_house_discovery(self):
        if not self._discovery_publication_enabled():
            return
        if self._discovery_publish_only() and not any(
                self._discovery_name_allowed(info) for info in self.alarms.values()):
            return
        unique_id = "dovit_alarm_house"
        topic = discovery_topic(self.cfg.discovery_prefix, "alarm_control_panel", unique_id)
        payload = alarm_panel_payload(self.cfg.discovery_node_id, "Dovit Alarm")
        self.mqtt.publish(topic, dumps(payload), retain=True)
        LOGGER.info('%s %s', "Published combined alarm discovery:", topic)

    def publish_combined_alarm_state(self):
        if (getattr(self, '_session_initialized', False)
                and not self._dovit_connected):
            return
        if not self.alarms:
            return
        try:
            roles = partition_ids(self.alarms)
        except ValueError:
            LOGGER.error('Alarm partition roles are ambiguous; state not published')
            return

        if self.alarm_partition_triggered:
            state = "triggered"
        else:
            if set(roles) != {'motion', 'contact'} or any(
                    dev_id not in self.alarm_partition_raw_states for dev_id in roles.values()):
                LOGGER.debug('Combined alarm state waiting for both partition readings')
                return
            motion_raw = float(self.alarm_partition_raw_states[roles['motion']])
            contact_raw = float(self.alarm_partition_raw_states[roles['contact']])
            if not all(math.isfinite(value) for value in (motion_raw, contact_raw)):
                LOGGER.warning('Combined alarm state contains non-finite readings; not published')
                return

            motion_armed = motion_raw >= 0.5
            contact_armed = contact_raw >= 0.5
            both_partial = motion_raw >= 1.5 and contact_raw >= 1.5
            disarm_reached = not motion_armed and not contact_armed
            arm_home_reached = (not motion_armed and contact_armed) or both_partial
            arm_away_reached = motion_armed and contact_armed and not both_partial

            if self.pending_alarm_house_state == "disarmed" and not disarm_reached:
                state = "disarming"
            elif self.pending_alarm_house_state == "armed_home" and not arm_home_reached:
                state = "arming"
            elif self.pending_alarm_house_state == "armed_away" and not arm_away_reached:
                state = "arming"
            else:
                self.pending_alarm_house_state = None
                if disarm_reached:
                    state = "disarmed"
                elif arm_home_reached:
                    state = "armed_home"
                else:
                    state = "armed_away"

        LOGGER.info('%s', f"Dovit -> MQTT (alarm house): state={state} raw={self.alarm_partition_raw_states} triggered={sorted(self.alarm_partition_triggered)}")
        if getattr(self, '_session_initialized', False):
            self._alarm_session_house_state = state
            self.republish_session_status()
            return True
        self.mqtt.publish(ALARM_HOUSE_STATE_TOPIC, state, qos=1, retain=True)

    def _removed_mapping_state_topics(self, category, dev_id):
        formats = {
            'lights': (LIGHT_STATE_TOPIC_FMT,),
            'switches': (SWITCH_STATE_TOPIC_FMT,),
            'shutters': (COVER_STATE_TOPIC_FMT, COVER_POSITION_STATE_TOPIC_FMT),
            'motions': (MOTION_STATE_TOPIC_FMT,),
            'contacts': (CONTACT_STATE_TOPIC_FMT,),
            'thermostats': (THERMO_CURRENT_STATE_TOPIC_FMT, THERMO_TARGET_STATE_TOPIC_FMT,
                            THERMO_MODE_STATE_TOPIC_FMT),
        }
        return {fmt.format(id=dev_id) for fmt in formats.get(category, ())}

    def _owned_mapping_state_topics(self):
        # Ownership is independent of names, telemetry validity, and position mode.
        topics = set()
        for category in ('lights', 'switches', 'shutters', 'motions', 'contacts', 'thermostats'):
            for dev_id in getattr(self, category, {}):
                topics.update(self._removed_mapping_state_topics(category, dev_id))
        return topics

    def publish_all_discovery_once(self, reason: str = ""):
        if not self._discovery_publication_enabled():
            return

        publish_only = self._discovery_publish_only()
        if not publish_only:
            self.reload_device_maps()
        publish_todo = False if publish_only else self.cfg.publish_todo_entities
        # Keep tombstones on disk so removal is retried after MQTT reconnects.
        # Never remove an identity that was subsequently assigned again.
        components = {'lights': ('light', 'light'), 'switches': ('switch', 'switch'), 'shutters': ('cover', 'cover'),
                      'motions': ('binary_sensor', 'motion'), 'contacts': ('binary_sensor', 'contact'),
                      'thermostats': ('climate', 'climate')}
        owned_states = self._owned_mapping_state_topics()
        for identity in ([] if publish_only else load_devices(self.cfg.devices_file).get('_removed_discovery', [])):
            if not isinstance(identity, str) or ':' not in identity:
                continue
            category, key = identity.split(':', 1)
            if category not in components or not key.isascii() or not key.isdigit():
                continue
            dev_id = int(key)
            if dev_id in getattr(self, category, {}):
                continue
            component, stem = components[category]
            self._publish_session_diagnostic(
                discovery_topic(self.cfg.discovery_prefix, component, f'dovit_{stem}_{key}'), '')
            for topic in sorted(self._removed_mapping_state_topics(category, dev_id) - owned_states):
                self._publish_session_diagnostic(topic, '')

        if reason:
            LOGGER.info('[DISCOVERY] Publishing reason=%s known_only=%s publish_todo=%s',
                        reason, publish_only, publish_todo)

        for dev_id, info in sorted(getattr(self, 'switches', {}).items()):
            if is_publishable_name(info.get('name', ''), publish_todo):
                self.publish_switch_discovery(dev_id, info)

        for dev_id, info in sorted(self.lights.items(), key=lambda x: x[0]):
            if is_publishable_name(info.get("name", ""), publish_todo):
                self.publish_light_discovery(dev_id, info)

        for dev_id, info in sorted(self.shutters.items(), key=lambda x: x[0]):
            if is_publishable_name(info.get("name", ""), publish_todo):
                self.publish_cover_discovery(dev_id, info)

        for dev_id, info in sorted(self.motions.items(), key=lambda x: x[0]):
            if is_publishable_name(info.get("name", ""), publish_todo):
                self.publish_motion_discovery(dev_id, info)

        for dev_id, info in sorted(self.contacts.items(), key=lambda x: x[0]):
            if is_publishable_name(info.get("name", ""), publish_todo):
                self.publish_contact_discovery(dev_id, info)

        for dev_id, info in sorted(self.alarms.items(), key=lambda x: x[0]):
            if is_publishable_name(info.get("name", ""), publish_todo):
                self.publish_alarm_discovery(dev_id, info)
        self.publish_alarm_house_discovery()
        self.publish_combined_alarm_state()

        for target_id, info in sorted(self.thermostats.items(), key=lambda x: x[0]):
            name = info.get("name", f"Dovit Thermostat {target_id}")
            if not is_publishable_name(info.get('name', '') if publish_only else name, publish_todo):
                continue

            current = info.get("current", {}) or {}
            current_id = int(current.get("id", target_id))
            current_st_topic = THERMO_CURRENT_STATE_TOPIC_FMT.format(id=target_id)

            # Wir publishen current temp immer auf topic, das zum target gehört (damit 1 climate entity)
            # -> wir senden später in der read_loop auf genau dieses Topic.

            target_state_topic = THERMO_TARGET_STATE_TOPIC_FMT.format(id=target_id)
            target_cmd_topic = THERMO_TEMP_CMD_TOPIC_FMT.format(id=target_id)
            mode_state_topic = THERMO_MODE_STATE_TOPIC_FMT.format(id=target_id)
            mode_cmd_topic = THERMO_MODE_CMD_TOPIC_FMT.format(id=target_id)

            min_temp = float(info.get("min_temp", 16.0))
            max_temp = float(info.get("max_temp", 26.0))
            step = float(info.get("temp_step", 0.5))

            unique_id = f"dovit_climate_{target_id}"
            topic = discovery_topic(self.cfg.discovery_prefix, "climate", unique_id)
            payload = climate_payload(
                self.cfg.discovery_node_id,
                target_id,
                name,
                min_temp,
                max_temp,
                step,
                current_topic=current_st_topic,
                target_state_topic=target_state_topic,
                target_cmd_topic=target_cmd_topic,
                mode_state_topic=mode_state_topic,
                mode_cmd_topic=mode_cmd_topic,
            )
            self.mqtt.publish(topic, dumps(payload), retain=True)
            LOGGER.info('%s %s %s', "Published climate discovery:", topic, name)

    async def discovery_republish_loop(self):
        if not self._discovery_publication_enabled():
            LOGGER.info('%s', "[DISCOVERY] Disabled: republish loop will not run.")
            return
        while True:
            await asyncio.sleep(self.cfg.discovery_republish_seconds)
            self.publish_all_discovery_once(reason=f"tick_{self.cfg.discovery_republish_seconds}s")

    # -------------------
    # Dovit I/O
    # -------------------
    async def connect_dovit(self):
        await self.dovit.connect()

    def send_frame(self, xml_str: str, *, expected_writer=_CAPTURE_WRITER):
        return self._send_frame(xml_str, self._capture_command_writer(expected_writer))

    async def _send_frame(self, xml_str: str, expected_writer):
        if not self._command_writer_valid(expected_writer):
            return False
        data = xml_str.encode("utf-8") + self.cfg.frame_sep
        try:
            await self.dovit.send(data, expected_writer=expected_writer)
        except (OSError, RuntimeError, asyncio.TimeoutError):
            # DovitTcp logs the failure without exposing the frame or credentials.
            return False
        return True

    async def send_alarm_password(self):
        code = (self.cfg.alarm_code or "").strip()
        if not code:
            LOGGER.warning('%s', "WARNING: Received <pw-ask /> but no alarm_code is configured.")
            return

        repeated = ";".join([code] * 18)
        LOGGER.info('%s', "Dovit <- Bridge (alarm password): responding to <pw-ask />")
        await self.send_frame(f"<pw>{repeated}</pw>")

    def can_record_observed_endpoint(self, entries, key):
        if key in entries or len(entries) < MAX_OBSERVED_ENDPOINTS:
            return True
        if not getattr(self, '_observed_endpoint_limit_warned', False):
            LOGGER.warning("Legacy endpoint observation limit reached (%s); new keys skipped",
                           MAX_OBSERVED_ENDPOINTS)
            self._observed_endpoint_limit_warned = True
        return False

    async def dovit_read_loop(self):
        buffer = b""
        while True:
            chunk = await self.dovit.read(4096)
            if not chunk:
                raise RuntimeError("Dovit connection closed by server.")
            buffer += chunk

            sep = self.cfg.frame_sep
            while sep in buffer:
                frame, buffer = buffer.split(sep, 1)
                if len(frame) > MAX_RECEIVE_FRAME_BYTES:
                    raise RuntimeError("Dovit receive frame exceeds byte limit.")
                frame = frame.strip()
                if not frame:
                    continue

                start = frame.find(b"<")
                if start == -1:
                    continue

                xml_bytes = frame[start:]
                try:
                    text = xml_bytes.decode("utf-8", errors="ignore").strip()
                    if "<pw-ask" in text:
                        await self.send_alarm_password()
                        continue

                    if "<hidv-state" not in text:
                        continue

                    root = ET.fromstring(text)
                    if root.tag != "hidv-state":
                        continue

                    dev = root.find("device")
                    if dev is None:
                        continue

                    dev_id_str = dev.get("id")
                    st = dev.findtext("statetype")
                    sv = dev.findtext("statevalue")

                    if dev_id_str is None or st is None or sv is None:
                        continue

                    dev_id = int(dev_id_str)
                    statetype = int(st)
                    sv_s = str(sv).strip()
                    self.monitor.observe(dev_id, statetype, sv_s)

                    # --------------------------
                    # DISCOVERY PERSISTENCE (only when enabled)
                    # --------------------------
                    if (self.cfg.enable_discovery and f'{dev_id}:{statetype}' not in self.monitor.routes
                            and f'{dev_id}:{statetype}' not in self.unassigned_endpoints):
                        # Light candidates
                        if statetype in self.cfg.light_statetypes:
                            if dev_id not in self.lights:
                                devices = load_devices(self.cfg.devices_file)
                                lights = devices.setdefault("lights", {})
                                k = str(dev_id)
                                if k not in lights:
                                    lights[k] = {"name": f"TODO_Light_{dev_id}", "statetype": statetype}
                                    save_devices(self.cfg.devices_file, devices)
                                    LOGGER.info('%s', f"[DISCOVERY] Added light to {self.cfg.devices_file.name}: id={dev_id} statetype={statetype}")
                                    self.lights = as_int_keys(load_devices(self.cfg.devices_file).get("lights", {}))
                                    self.refresh_monitor_routes()

                        # Shutter candidates
                        if (sv_s in self.cfg.shutter_values) and (statetype not in self.cfg.light_statetypes) and (dev_id not in self.lights):
                            key = (dev_id, statetype)
                            vals = set()
                            if self.can_record_observed_endpoint(self.shutter_candidate_values, key):
                                vals = self.shutter_candidate_values.setdefault(key, set())
                                vals.add(sv_s)

                            if ("2.0" in vals) and (len(vals) >= self.cfg.shutter_confidence_distinct_values):
                                already_known = dev_id in self.shutters and int(self.shutters[dev_id]["statetype"]) == statetype
                                if not already_known:
                                    devices = load_devices(self.cfg.devices_file)
                                    shutters = devices.setdefault("shutters", {})
                                    k = str(dev_id)
                                    if k not in shutters:
                                        shutters[k] = {"name": f"TODO_Shutter_{dev_id}", "statetype": statetype}
                                        save_devices(self.cfg.devices_file, devices)
                                        LOGGER.info('%s', f"[DISCOVERY] Added shutter to {self.cfg.devices_file.name}: id={dev_id} statetype={statetype}")
                                        self.shutters = as_int_keys(load_devices(self.cfg.devices_file).get("shutters", {}))
                                        self.refresh_monitor_routes()
                        pass

                    # ---------------------------------------------------
                    # THERMOSTATS
                    # ---------------------------------------------------

                    # 1) TARGET publish: dev_id ist die Target-ID (z.B. 44)
                    if dev_id in self.thermostats:
                        target_info = self.thermostats[dev_id]
                        target_statetype = int((target_info.get("target", {}) or {}).get("statetype", -1))

                        if statetype == target_statetype:
                            finite_telemetry_value(sv_s)
                            topic = THERMO_TARGET_STATE_TOPIC_FMT.format(id=dev_id)
                            LOGGER.info('%s', f"Dovit -> MQTT (thermostat target): id={dev_id} value={sv_s}")
                            self._publish_received_state(topic, sv_s, dev_id, statetype)
                            continue

                    # 2) CURRENT publish: dev_id ist Sensor-ID (z.B. 42), publish aber auf Target-ID Topic (44)
                    handled_current = False
                    for target_id, info in self.thermostats.items():
                        current = info.get("current", {}) or {}
                        cur_id = int(current.get("id", -1))
                        cur_statetype = int(current.get("statetype", -1))

                        if dev_id == cur_id and statetype == cur_statetype:
                            finite_telemetry_value(sv_s)
                            topic = THERMO_CURRENT_STATE_TOPIC_FMT.format(id=target_id)
                            LOGGER.info('%s', f"Dovit -> MQTT (thermostat current): target={target_id} sensor={dev_id} value={sv_s}")
                            self._publish_received_state(topic, sv_s, dev_id, statetype)
                            handled_current = True
                            break

                    if handled_current:
                        continue

                    handled_mode = False
                    for target_id, info in self.thermostats.items():
                        mode = info.get("mode", {}) or {}
                        mode_id = int(mode.get("id", -1))
                        mode_statetype = int(mode.get("statetype", -1))

                        if dev_id == mode_id and statetype == mode_statetype:
                            v = finite_telemetry_value(sv_s)

                            hvac_mode = "heat" if v >= 0.5 else "off"
                            topic = THERMO_MODE_STATE_TOPIC_FMT.format(id=target_id)
                            LOGGER.info('%s', f"Dovit -> MQTT (thermostat mode): target={target_id} mode_id={dev_id} mode={hvac_mode} raw={sv_s}")
                            self._publish_received_state(topic, hvac_mode, dev_id, statetype)
                            handled_mode = True
                            break

                    if handled_mode:
                        continue

                    # ---------------------------------------------------
                    # LIGHTS (PRIORITY)
                    # ---------------------------------------------------
                    switch = getattr(self, 'switches', {}).get(dev_id)
                    if switch is not None and statetype == int(switch['statetype']):
                        # Only binary evidence establishes a switch state; never guess from other values.
                        try:
                            value = finite_telemetry_value(sv_s)
                        except ValueError:
                            continue
                        if value not in (0.0, 1.0):
                            continue
                        self._publish_received_state(SWITCH_STATE_TOPIC_FMT.format(id=dev_id),
                                                     'ON' if value == 1.0 else 'OFF', dev_id, statetype)
                        continue

                    if dev_id in self.lights and statetype == int(self.lights[dev_id]["statetype"]):
                        try:
                            v = finite_telemetry_value(sv_s)
                        except Exception:
                            LOGGER.warning("Invalid light state id=%s statetype=%s; check device mapping", dev_id, statetype)
                            continue

                        state = "ON" if v >= 0.5 else "OFF"
                        topic = LIGHT_STATE_TOPIC_FMT.format(id=dev_id)
                        LOGGER.info('%s', f"Dovit -> MQTT (light): id={dev_id} state={state}")
                        self._publish_received_state(topic, state, dev_id, statetype)
                        continue

                    # ---------------------------------------------------
                    # SHUTTERS
                    # ---------------------------------------------------
                    if dev_id in self.shutters and statetype == int(self.shutters[dev_id]["statetype"]):
                        shutter_info = self.shutters[dev_id]
                        if sv_s in ("1", "1.0"):
                            cover_state = "opening"
                        elif sv_s in ("2", "2.0"):
                            cover_state = "closing"
                        elif sv_s in ("0", "0.0"):
                            cover_state = "stopped"
                        else:
                            cover_state = f"VALUE_{sv_s}"

                        topic = COVER_STATE_TOPIC_FMT.format(id=dev_id)
                        LOGGER.info('%s', f"Dovit -> MQTT (cover): id={dev_id} state={cover_state} raw={sv_s}")
                        self._publish_received_state(topic, cover_state, dev_id, statetype)

                        if self.cover_supports_position(dev_id, shutter_info):
                            if cover_state == "opening":
                                self.start_cover_motion(dev_id, shutter_info, "opening")
                            elif cover_state == "closing":
                                self.start_cover_motion(dev_id, shutter_info, "closing")
                            elif cover_state == "stopped":
                                self.finish_cover_motion(dev_id, shutter_info)
                        continue

                    # ---------------------------------------------------
                    # MOTION SENSORS
                    # ---------------------------------------------------
                    if dev_id in self.motions and statetype == int(self.motions[dev_id]["statetype"]):
                        try:
                            v = finite_telemetry_value(sv_s)
                        except Exception:
                            LOGGER.warning('%s', f"Ignoring invalid motion statevalue: id={dev_id} raw={sv_s!r}")
                            continue

                        state = "ON" if v >= 0.5 else "OFF"
                        topic = MOTION_STATE_TOPIC_FMT.format(id=dev_id)
                        LOGGER.info('%s', f"Dovit -> MQTT (motion): id={dev_id} state={state} raw={sv_s}")
                        self._publish_received_state(topic, state, dev_id, statetype)
                        continue

                    # ---------------------------------------------------
                    # CONTACT SENSORS
                    # ---------------------------------------------------
                    if dev_id in self.contacts and statetype == int(self.contacts[dev_id]["statetype"]):
                        try:
                            v = finite_telemetry_value(sv_s)
                        except Exception:
                            LOGGER.warning('%s', f"Ignoring invalid contact statevalue: id={dev_id} raw={sv_s!r}")
                            continue

                        state = "ON" if v >= 0.5 else "OFF"
                        topic = CONTACT_STATE_TOPIC_FMT.format(id=dev_id)
                        LOGGER.info('%s', f"Dovit -> MQTT (contact): id={dev_id} state={state} raw={sv_s}")
                        self._publish_received_state(topic, state, dev_id, statetype)
                        continue

                    # ---------------------------------------------------
                    # ALARM PARTITIONS (read-only)
                    # ---------------------------------------------------
                    if dev_id in self.alarms:
                        if (getattr(self, '_session_initialized', False)
                                and not self._dovit_connected):
                            continue
                        info = self.alarms[dev_id]
                        state_statetype = int(info.get("state_statetype", -1))
                        text_statetype = int(info.get("text_statetype", -1))
                        trigger_statetype = int(info.get("trigger_statetype", -1))

                        if statetype == state_statetype:
                            try:
                                v = float(sv_s)
                                if not math.isfinite(v):
                                    raise ValueError('Alarm reading must be finite')
                            except Exception:
                                LOGGER.warning('%s', f"Ignoring invalid alarm statevalue: id={dev_id} raw={sv_s!r}")
                                continue

                            self.alarm_partition_raw_states[dev_id] = v
                            if v < 0.5:
                                self.alarm_partition_triggered.discard(dev_id)

                            state = "armed" if v >= 0.5 else "disarmed"
                            topic = ALARM_STATE_TOPIC_FMT.format(id=dev_id)
                            LOGGER.info('%s', f"Dovit -> MQTT (alarm state): id={dev_id} state={state} raw={sv_s}")
                            self._record_alarm_session_evidence(dev_id, reading=v)
                            if getattr(self, '_session_initialized', False):
                                self._alarm_session_states[dev_id] = state
                            else:
                                self.mqtt.publish(topic, state, qos=1, retain=True)
                            published = self.publish_combined_alarm_state()
                            if getattr(self, '_session_initialized', False) and not published:
                                self.republish_session_status()
                            continue

                        if statetype == text_statetype:
                            topic = ALARM_TEXT_TOPIC_FMT.format(id=dev_id)
                            LOGGER.info('%s', f"Dovit -> MQTT (alarm text): id={dev_id} text={sv_s}")
                            if getattr(self, '_session_initialized', False):
                                self._alarm_session_texts[dev_id] = sv_s
                                self.republish_session_status()
                            else:
                                self.mqtt.publish(topic, sv_s, qos=1, retain=True)
                            continue

                        if statetype == trigger_statetype:
                            self.alarm_partition_triggered.add(dev_id)
                            self.pending_alarm_house_state = None
                            state_topic = ALARM_STATE_TOPIC_FMT.format(id=dev_id)
                            text_topic = ALARM_TEXT_TOPIC_FMT.format(id=dev_id)
                            LOGGER.info('%s', f"Dovit -> MQTT (alarm trigger): id={dev_id} text={sv_s}")
                            self._record_alarm_session_evidence(dev_id, triggered=True)
                            if getattr(self, '_session_initialized', False):
                                self._alarm_session_states[dev_id] = 'triggered'
                                self._alarm_session_texts[dev_id] = sv_s
                            else:
                                self.mqtt.publish(state_topic, 'triggered', qos=1, retain=True)
                                self.mqtt.publish(text_topic, sv_s, qos=1, retain=True)
                            published = self.publish_combined_alarm_state()
                            if getattr(self, '_session_initialized', False) and not published:
                                self.republish_session_status()
                            continue

                    # ---------------------------------------------------
                    # OBSERVER (nur wenn wirklich nichts gematcht hat)
                    # ---------------------------------------------------
                    key = (dev_id, statetype)
                    if key not in self.seen_unknown and self.can_record_observed_endpoint(self.seen_unknown, key):
                        self.seen_unknown.add(key)
                        LOGGER.info("Unmapped Dovit state id=%s statetype=%s value=%r (first observation)", dev_id, statetype, sv[:120])

                except Exception as e:
                    LOGGER.error("Dovit frame processing failed type=%s frame_bytes=%s; frame omitted", type(e).__name__, len(xml_bytes))

            if len(buffer) > MAX_RECEIVE_FRAME_BYTES:
                # A fragmented separator is not part of the frame payload.
                partial_sep = next((size for size in range(min(len(sep) - 1, len(buffer)), 0, -1)
                                    if buffer.endswith(sep[:size])), 0)
                if len(buffer) - partial_sep > MAX_RECEIVE_FRAME_BYTES:
                    raise RuntimeError("Dovit receive frame exceeds byte limit.")

    # -------------------
    # Start
    # -------------------
    def start_mqtt(self):
        self.mqtt.connect_and_loop()
