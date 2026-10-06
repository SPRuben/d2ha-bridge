# -*- coding: utf-8 -*-
import logging
LOGGER = logging.getLogger(__name__)

import json
import math
import os
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Dict, Any

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def configuration_lock(path):
    """Serialize supported in-process writers; external writers remain unsupported."""
    key = os.path.normcase(str(Path(path).resolve()))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())

def _atomic_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _check_device_maps(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError('Device configuration must be an object')
    for category in ('lights', 'switches', 'shutters', 'thermostats', 'motions', 'contacts', 'alarms'):
        entries = data.get(category, {})
        if not isinstance(entries, dict) or any(not isinstance(info, dict) for info in entries.values()):
            raise ValueError('Invalid device category structure: ' + category)


def _decode_devices(content: bytes) -> dict:
    def finite_number(raw):
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError('Device configuration numbers must be finite')
        return value

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate device configuration key')
            result[key] = value
        return result
    data = json.loads(content, object_pairs_hook=pairs,
                      parse_constant=finite_number, parse_float=finite_number)
    _check_device_maps(data)
    return data

def ensure_devices_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        data = {"lights": {}, "switches": {}, "shutters": {}, "thermostats": {}, "motions": {}, "contacts": {}, "alarms": {}}
        # Exclusive creation never truncates a file created by another process.
        with path.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(data, indent=2, ensure_ascii=False))

def load_devices(path: Path, *, create_if_missing=False) -> dict:
    with configuration_lock(path):
        if create_if_missing:
            ensure_devices_file(path)
        return _decode_devices(path.read_bytes())

def save_devices(path: Path, data: dict) -> None:
    with configuration_lock(path):
        _save_devices(path, data)


def _save_devices(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _check_device_maps(data)
    content = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8')
    # Serialization can collapse distinct Python keys (e.g. 19 and "19").
    _decode_devices(content)
    before = path.read_bytes() if path.exists() else None
    if before is not None:
        # A damaged existing file must be recovered explicitly, not overwritten.
        _decode_devices(before)
        if before == content:
            return
        directory = path.parent / 'dovit_device_backups'
        directory.mkdir(parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex + '.json'
        backup = directory / name
        with backup.open('xb') as stream:
            stream.write(before)
            stream.flush()
            os.fsync(stream.fileno())
        if backup.read_bytes() != before:
            raise OSError('Device backup verification failed')
        if path.read_bytes() != before:
            raise ValueError('Device configuration changed during backup')
    _atomic_bytes(path, content)

def ensure_cover_positions_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("{}", encoding="utf-8")

def load_cover_positions(path: Path) -> dict[int, int]:
    ensure_cover_positions_file(path)
    try:
        raw = _decode_positions(path.read_bytes())
    except Exception:
        LOGGER.error('Cover position file invalid/unreadable; original preserved, estimates unavailable')
        return {}

    positions: dict[int, int] = {}
    for k, v in (raw or {}).items():
        try:
            pos = int(round(float(v)))
            positions[int(k)] = max(0, min(100, pos))
        except Exception:
            continue
    return positions

def save_cover_positions(path: Path, positions: dict[int, int]) -> None:
    with configuration_lock(path):
        if path.exists():
            _decode_positions(path.read_bytes())
        _save_cover_positions(path, positions)


def _decode_positions(content):
    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValueError('Cover positions must be an object')
    for key, value in raw.items():
        if not key.isdigit() or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError('Invalid cover position estimate')
    return raw


def _save_cover_positions(path: Path, positions: dict[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        str(dev_id): max(0, min(100, int(round(pos))))
        for dev_id, pos in sorted(positions.items(), key=lambda item: item[0])
    }
    _atomic_bytes(path, json.dumps(serializable, indent=2, ensure_ascii=False).encode('utf-8'))

def as_int_keys(d: dict) -> dict:
    out = {}
    for k, v in (d or {}).items():
        try:
            out[int(k)] = v
        except Exception:
            continue
    return out

def reload_maps(path: Path):
    dev = load_devices(path)
    lights = as_int_keys(dev.get("lights", {}))
    shutters = as_int_keys(dev.get("shutters", {}))
    thermostats = as_int_keys(dev.get("thermostats", {}))
    motions = as_int_keys(dev.get("motions", {}))
    contacts = as_int_keys(dev.get("contacts", {}))
    alarms = as_int_keys(dev.get("alarms", {}))
    return lights, shutters, thermostats, motions, contacts, alarms

def is_publishable_name(name: str, publish_todo_entities: bool) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    if not publish_todo_entities and n.upper().startswith("TODO_"):
        return False
    return True

def sanity_check_maps(lights: dict, shutters: dict) -> None:
    overlap = set(lights.keys()) & set(shutters.keys())
    if overlap:
        LOGGER.warning("Device IDs mapped as both light and shutter: %s; check dovit_devices.json", sorted(overlap))
