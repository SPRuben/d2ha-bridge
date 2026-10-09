"""Validated configuration edits, staged for the next bridge start."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid

from .mapping_drafts import validate_draft
from .alarm_partitions import partition_ids
from .json_editor import validate_document
from .storage import configuration_lock

CATEGORIES = ('lights', 'switches', 'shutters', 'motions', 'contacts', 'thermostats')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_maps(content):
    maps = json.loads(content)
    if not isinstance(maps, dict):
        raise ValueError('edit_invalid')
    for category in CATEGORIES + ('alarms',):
        entries = maps.get(category, {})
        if not isinstance(entries, dict) or any(not isinstance(v, dict) for v in entries.values()):
            raise ValueError('edit_invalid')
    if not isinstance(maps.get('_removed_discovery', []), list):
        raise ValueError('edit_invalid')
    if not isinstance(maps.get('_unassigned_endpoints', []), list) or any(
            not isinstance(key, str) for key in maps.get('_unassigned_endpoints', [])):
        raise ValueError('edit_invalid')
    return maps


def atomic_write(path, data):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class DeviceEditor:
    def __init__(self, path):
        self.path = Path(path)
        self.pending = self.path.with_name(self.path.stem + '.pending.json')
        self.lock = configuration_lock(self.path)

    def snapshot(self):
        with self.lock:
            raw = self.path.read_bytes()
            maps = parse_maps(raw)
            return dict(revision=digest(raw), document=raw.decode('utf-8-sig'), maps={k: maps.get(k, {}) for k in CATEGORIES},
                        alarm_roles=partition_ids(maps.get('alarms', {})),
                        pending=self.pending.exists())

    def validate(self, raw):
        # Work from disk, not the potentially older observation snapshot.
        from .web_monitor import Monitor
        if not isinstance(raw, dict):
            raise ValueError('edit_invalid')
        content = self.path.read_bytes()
        if raw.get('revision') != digest(content):
            raise ValueError('edit_stale')
        maps = parse_maps(content)
        operation = raw.get('operation', 'upsert')
        if operation == 'replace_json':
            updated, summary, identity = validate_document(raw.get('document'), maps)
            return dict(maps=updated, before=content, draft=summary, identity_changed=identity)
        if operation not in ('upsert', 'delete'):
            raise ValueError('edit_invalid')
        previous = None
        source = raw.get('source')
        if source is not None:
            if not isinstance(source, str) or ':' not in source:
                raise ValueError('edit_invalid')
            category, key = source.split(':', 1)
            if category not in CATEGORIES or key not in maps.get(category, {}):
                raise ValueError('edit_stale')
            previous = maps[category].pop(key)
        if operation == 'delete':
            if previous is None:
                raise ValueError('edit_invalid')
            removed = maps.setdefault('_removed_discovery', [])
            if source not in removed:
                removed.append(source)
            deleted = Monitor()
            deleted.configure({category: {key: previous}})
            endpoints = maps.setdefault('_unassigned_endpoints', [])
            if not isinstance(endpoints, list):
                raise ValueError('edit_invalid')
            keys = list(deleted.routes)
            if category == 'shutters':
                keys.append(f"{int(key)}:{int(previous.get('command_statetype', previous['statetype']))}")
            for endpoint in keys:
                if endpoint not in endpoints:
                    endpoints.append(endpoint)
            return dict(maps=maps, before=content, draft=dict(operation='delete', source=source,
                        configuration=previous), identity_changed=True)
        monitor = Monitor()
        monitor.configure({k: v for k, v in maps.items() if k in CATEGORIES + ('alarms',)})
        for key, info in maps.get('alarms', {}).items():
            monitor.routes.setdefault(f"{int(key)}:{int(info.get('command_statetype', 0))}", [])
        for key, info in maps.get('shutters', {}).items():
            command_st = info.get('command_statetype', info.get('statetype'))
            if command_st is not None:
                monitor.routes.setdefault(f'{int(key)}:{int(command_st)}', [])
        device = raw.get('device')
        if isinstance(device, dict) and device.get('category') in ('alarm_motion', 'alarm_contact'):
            role = device['category'].removeprefix('alarm_')
            if role in partition_ids(maps.get('alarms', {})):
                raise ValueError('alarm_role_used')
            # Reuse endpoint/name validation, then build the explicit partition schema.
            probe = dict(device, category='lights', statetype=device.get('state_statetype'))
            validated = validate_draft(probe, monitor)
            key = validated['device_id']
            if key in maps.get('alarms', {}):
                raise ValueError('alarm_role_used')
            info = dict(name=validated['configuration']['name'], partition_role=role)
            endpoints = []
            for field in ('state_statetype', 'text_statetype', 'trigger_statetype', 'command_statetype'):
                value = device.get(field)
                if type(value) is not int or not 0 <= value <= 2147483647:
                    raise ValueError('edit_invalid')
                endpoint = f'{int(key)}:{value}'
                if endpoint in monitor.routes or endpoint == '39:111':
                    raise ValueError('alarm_endpoint_used')
                endpoints.append(value)
                info[field] = value
            if len(set(endpoints)) != len(endpoints):
                raise ValueError('alarm_endpoint_used')
            draft = dict(category='alarms', device_id=key, configuration=info)
        else:
            draft = validate_draft(device, monitor)
        category, key = draft['category'], draft['device_id']
        changed_identity = source is not None and source != f'{category}:{key}'
        info = draft['configuration']
        if previous is not None and source.split(':', 1)[0] == category:
            # Preserve calibration and other fields not represented in the form.
            merged = deepcopy(previous)
            for field, value in info.items():
                if isinstance(value, dict):
                    merged[field] = dict(merged.get(field) or {}, **value)
                else:
                    merged[field] = value
            info = merged
            if category == 'thermostats':
                info['target']['id'] = int(key)
            if category == 'shutters' and (changed_identity or info['statetype'] != previous.get('statetype')
                    or info.get('command_statetype') != previous.get('command_statetype', previous.get('statetype'))):
                if previous.get('position_mode') != 'legacy':
                    draft['covers_reset_to_legacy'] = [f'{category}:{key}']
                info['position_mode'] = 'legacy'
        maps.setdefault(category, {})[key] = info
        draft['configuration'] = info
        if changed_identity:
            removed = maps.setdefault('_removed_discovery', [])
            if source not in removed:
                removed.append(source)
        return dict(maps=maps, before=content, draft=draft, identity_changed=changed_identity)

    def request(self, raw, save=False):
        with self.lock:
            if self.pending.exists():
                raise ValueError('edit_pending')
            result = self.validate(raw)
            from .recovery import validate_recovery_document
            validate_recovery_document(json.dumps(result['maps'], indent=2, ensure_ascii=True).encode())
            if save:
                if raw.get('confirm') is not True:
                    raise ValueError('edit_confirm')
                if result['identity_changed'] and raw.get('confirm_identity') is not True:
                    raise ValueError('edit_identity')
                # The validated request is revalidated against the active file at startup.
                with self.pending.open('x', encoding='utf-8') as stream:
                    json.dump(raw, stream, ensure_ascii=True, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
            return dict(draft=result['draft'], identity_changed=result['identity_changed'], pending=save)

    def cancel(self):
        with self.lock:
            self.pending.unlink(missing_ok=True)
            return dict(pending=False)

    def apply_pending(self):
        with self.lock:
            if not self.pending.exists():
                return False
            raw = json.loads(self.pending.read_bytes())
            if not isinstance(raw, dict) or raw.get('confirm') is not True:
                raise ValueError('edit_confirm')
            result = self.validate(raw)
            if result['identity_changed'] and raw.get('confirm_identity') is not True:
                raise ValueError('edit_identity')
            from .recovery import validate_recovery_document
            content = json.dumps(result['maps'], indent=2, ensure_ascii=True).encode()
            validate_recovery_document(content)
            directory = self.path.parent / 'dovit_device_backups'
            directory.mkdir(parents=True, exist_ok=True)
            name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex + '.json'
            backup = directory / name
            with backup.open('xb') as stream:
                stream.write(result['before'])
                stream.flush()
                os.fsync(stream.fileno())
            if backup.read_bytes() != result['before']:
                raise OSError('Backup verification failed')
            # Refuse to overwrite external edits made while creating the backup.
            if self.path.read_bytes() != result['before']:
                raise ValueError('edit_stale')
            atomic_write(self.path, content)
            self.pending.unlink()
            return True
