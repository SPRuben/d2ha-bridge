"""Explicit offline recovery. Never connects to MQTT or operates Dovit devices."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid
from datetime import datetime, timezone

from .storage import _decode_devices, _atomic_bytes, configuration_lock
from .alarm_partitions import partition_ids

CATEGORIES = ('lights', 'switches', 'shutters', 'thermostats', 'motions', 'contacts', 'alarms')
MAX_BYTES = 256 * 1024


def digest(content):
    return hashlib.sha256(content).hexdigest()


def validate_recovery_document(content):
    """Compatible endpoint checks, not a claim of verified physical semantics."""
    if len(content) > MAX_BYTES:
        raise ValueError('Configuration exceeds recovery size limit')
    content.decode('utf-8', errors='strict')
    maps = _decode_devices(content)
    # JSON escape sequences can otherwise introduce unpaired Unicode surrogates.
    json.dumps(maps, ensure_ascii=False).encode('utf-8', errors='strict')
    def endpoint(value):
        if type(value) is not int or not 0 <= value <= 2147483647:
            raise ValueError('Invalid endpoint number')
    for category in CATEGORIES:
        for key, info in maps.get(category, {}).items():
            if not key.isascii() or not key.isdigit() or str(int(key)) != key:
                raise ValueError('Invalid device ID')
            endpoint(int(key))
            if 'name' in info and not isinstance(info['name'], str):
                raise ValueError('Device name must be text')
            if category == 'thermostats':
                for role in ('target', 'current', 'mode'):
                    part = info.get(role)
                    if part is None and role == 'mode':
                        continue
                    if not isinstance(part, dict):
                        raise ValueError('Invalid thermostat endpoint')
                    endpoint(part.get('id', int(key)))
                    endpoint(part.get('statetype'))
                for field, default in (('min_temp', 5), ('max_temp', 35), ('temp_step', .5)):
                    value = info.get(field, default)
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise ValueError('Invalid thermostat limit')
                if info.get('min_temp', 5) >= info.get('max_temp', 35) or info.get('temp_step', .5) <= 0:
                    raise ValueError('Invalid thermostat range')
            elif category == 'alarms':
                for field in ('state_statetype', 'text_statetype', 'trigger_statetype', 'command_statetype'):
                    if field in info:
                        endpoint(info[field])
            else:
                endpoint(info.get('statetype'))
                if 'command_statetype' in info:
                    endpoint(info['command_statetype'])
    partition_ids(maps.get('alarms', {}))
    for field in ('_removed_discovery', '_unassigned_endpoints'):
        if not isinstance(maps.get(field, []), list) or any(not isinstance(v, str) for v in maps.get(field, [])):
            raise ValueError('Invalid internal metadata')
    return maps


def inspect(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {'state': 'missing', 'revision': 'missing'}
    except OSError:
        return {'state': 'unreadable', 'revision': None}
    result = {'revision': digest(raw), 'bytes': len(raw)}
    try:
        maps = validate_recovery_document(raw)
        result.update(state='valid', counts={key: len(maps.get(key, {})) for key in CATEGORIES},
                      contains_cleanup=bool(maps.get('_removed_discovery')))
    except (ValueError, TypeError, RecursionError):
        result['state'] = 'invalid'
    return result


def _current(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def restore(path, source, *, revision, source_revision, confirm=False, bridge_stopped=False):
    """Require reviewed hashes, explicit consent and a stopped external bridge."""
    path, source = Path(path), Path(source)
    if not confirm or not bridge_stopped:
        raise ValueError('Explicit confirmation and stopped bridge required')
    if path.resolve() == source.resolve():
        raise ValueError('Backup must be a separate file')
    with configuration_lock(path):
        if path.with_name(path.stem + '.pending.json').exists():
            raise ValueError('Pending edit must be resolved before recovery')
        before = _current(path)
        if ('missing' if before is None else digest(before)) != revision:
            raise ValueError('Active file changed; inspect again')
        raw = source.read_bytes()
        if digest(raw) != source_revision:
            raise ValueError('Backup changed; inspect again')
        maps = validate_recovery_document(raw)
        if maps.get('_removed_discovery'):
            raise ValueError('Backup contains cleanup actions; review on a copy first')
        path.parent.mkdir(parents=True, exist_ok=True)
        preserved = None
        if before is not None:
            directory = path.parent / 'dovit_device_backups'
            directory.mkdir(parents=True, exist_ok=True)
            preserved = directory / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_recovery_' + uuid.uuid4().hex + '.json')
            with preserved.open('xb') as stream:
                stream.write(before)
                stream.flush()
                os.fsync(stream.fileno())
            if preserved.read_bytes() != before:
                raise OSError('Preserved file verification failed')
        if _current(path) != before:
            raise ValueError('Active file changed during preservation')
        _atomic_bytes(path, raw)
        if path.read_bytes() != raw:
            raise OSError('Restored file verification failed')
        return {'state': 'restored', 'revision': digest(raw), 'preserved': str(preserved) if preserved else None}


def initialize(path, *, confirm=False, bridge_stopped=False):
    path = Path(path)
    if not confirm or not bridge_stopped:
        raise ValueError('Explicit confirmation and stopped bridge required')
    with configuration_lock(path):
        if path.with_name(path.stem + '.pending.json').exists():
            raise ValueError('Pending edit exists')
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps({key: {} for key in CATEGORIES}, indent=2).encode()
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # Same-filesystem hard-link install is atomic and refuses an existing target.
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return inspect(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'restore', 'initialize'))
    parser.add_argument('path', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--source-revision')
    parser.add_argument('--confirm', action='store_true')
    parser.add_argument('--bridge-stopped', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'inspect':
            result = inspect(args.path)
        elif args.action == 'initialize':
            result = initialize(args.path, confirm=args.confirm, bridge_stopped=args.bridge_stopped)
        else:
            if args.source is None or args.revision is None or args.source_revision is None:
                parser.error('restore requires --source, --revision and --source-revision')
            result = restore(args.path, args.source, revision=args.revision,
                             source_revision=args.source_revision, confirm=args.confirm,
                             bridge_stopped=args.bridge_stopped)
        print(json.dumps(result))
    except (ValueError, OSError, TypeError, RecursionError) as exc:
        parser.exit(1, 'Recovery refused: ' + type(exc).__name__ + '; inspect files and arguments.\n')


if __name__ == '__main__':
    main()
