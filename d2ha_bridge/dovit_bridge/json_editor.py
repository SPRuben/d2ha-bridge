"""Whole-document edits with the same staged lifecycle as graphical edits."""
from copy import deepcopy
import json
import math

from .mapping_drafts import validate_draft

CATEGORIES = ('lights', 'switches', 'shutters', 'motions', 'contacts', 'thermostats')
MAX_DOCUMENT_BYTES = 256 * 1024


def same_value(left, right):
    # Python considers False == 0; configuration validation must not.
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def decode_document(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_DOCUMENT_BYTES:
        raise ValueError('json_size')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('json_duplicate')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('json_finite')
    try:
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f'JSON: {exc.lineno}:{exc.colno}: {exc.msg}') from None
    except RecursionError:
        raise ValueError('json_invalid') from None
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('json_finite')
        if isinstance(value, dict):
            for item in value.values():
                finite(item)
        elif isinstance(value, list):
            for item in value:
                finite(item)
    try:
        finite(result)
    except RecursionError:
        raise ValueError('json_invalid') from None
    if not isinstance(result, dict):
        raise ValueError('json_invalid')
    return result


def _review_entry(category, key, name=None):
    entry = dict(uid=f'{category}:{key}', category=category, device_id=key)
    if isinstance(name, str) and name.strip() and len(name) <= 80 and not any(ord(c) < 32 for c in name):
        entry['name'] = name.strip()
    return entry


def validate_document(text, current):
    from .web_monitor import Monitor
    result = decode_document(text)
    # Do not offer a bypass around the graphical editor's protected alarm/internal data.
    protected = (set(current) | set(result)) - set(CATEGORIES)
    if any(not same_value(current.get(key), result.get(key)) or (key in current) != (key in result) for key in protected):
        raise ValueError('json_protected')
    for category in CATEGORIES:
        entries = result.get(category, {})
        if not isinstance(entries, dict):
            raise ValueError('json_invalid')
        for key, info in entries.items():
            if not key.isascii() or not key.isdigit() or str(int(key)) != key or int(key) > 2147483647 or not isinstance(info, dict):
                raise ValueError('json_invalid')
    removed, changed, legacy_covers = [], [], []
    removed_entries, changed_entries = [], []
    suppressed = list(current.get('_unassigned_endpoints', []))
    for category in CATEGORIES:
        for key, old in current.get(category, {}).items():
            if key not in result.get(category, {}):
                removed.append(f'{category}:{key}')
                monitor = Monitor()
                monitor.configure({category: {key: old}})
                endpoints = list(monitor.routes)
                if category == 'shutters':
                    endpoints.append(f"{int(key)}:{int(old.get('command_statetype', old['statetype']))}")
                suppressed.extend(e for e in endpoints if e not in suppressed)
                removed_entries.append(_review_entry(category, key, old.get('name')))
        for key, info in result.get(category, {}).items():
            old = current.get(category, {}).get(key)
            if same_value(info, old):
                continue
            changed.append(f'{category}:{key}')
            maps = deepcopy({k: result.get(k, {}) for k in CATEGORIES + ('alarms',)})
            maps[category].pop(key)
            monitor = Monitor()
            try:
                monitor.configure(maps)
                for group in ('shutters', 'alarms'):
                    for other, entry in maps[group].items():
                        st = entry.get('command_statetype', entry.get('statetype', 0))
                        monitor.routes.setdefault(f'{int(other)}:{int(st)}', [])
                raw = dict(info, category=category, id=int(key))
                if category == 'thermostats':
                    for part in ('target', 'current', 'mode'):
                        if not isinstance(info.get(part), dict):
                            raise ValueError('json_invalid')
                    target_id = info['target'].get('id', int(key))
                    if type(target_id) is not int or target_id != int(key):
                        raise ValueError('json_target_id')
                    raw.update(statetype=info['target'].get('statetype'),
                               current_id=info['current'].get('id'), current_statetype=info['current'].get('statetype'),
                               mode_id=info['mode'].get('id'), mode_statetype=info['mode'].get('statetype'))
                validated = validate_draft(raw, monitor)
                # Extra fields (including calibration) remain visible, not freely writable.
                allowed = {'name', 'statetype'}
                if category == 'shutters':
                    allowed.add('command_statetype')
                if category == 'contacts':
                    allowed.add('device_class')
                if category == 'thermostats':
                    allowed = {'name', 'target', 'current', 'mode', 'min_temp', 'max_temp', 'temp_step'}
                    for part in ('target', 'current', 'mode'):
                        extras = set(info[part]) - {'id', 'statetype'}
                        before = (old or {}).get(part, {})
                        if any(not same_value(info[part].get(k), before.get(k)) for k in extras | (set(before)-{'id', 'statetype'})):
                            raise ValueError('json_protected')
                extras = (set(info) | set(old or {})) - allowed
                if any(not same_value(info.get(k), (old or {}).get(k)) for k in extras):
                    raise ValueError('json_protected')
                if category == 'shutters' and old and (
                        info.get('statetype') != old.get('statetype') or
                        info.get('command_statetype', info['statetype']) != old.get('command_statetype', old['statetype'])):
                    info['position_mode'] = 'legacy'
                    legacy_covers.append(f'{category}:{key}')
                changed_entries.append(_review_entry(category, key, validated['configuration']['name']))
            except (TypeError, KeyError, OverflowError, AttributeError):
                raise ValueError('json_invalid') from None
    if removed:
        result['_removed_discovery'] = list(dict.fromkeys(current.get('_removed_discovery', []) + removed))
        result['_unassigned_endpoints'] = suppressed
    return result, dict(changed=changed, removed=removed, changed_entries=changed_entries,
                        removed_entries=removed_entries, covers_reset_to_legacy=legacy_covers), bool(removed)
