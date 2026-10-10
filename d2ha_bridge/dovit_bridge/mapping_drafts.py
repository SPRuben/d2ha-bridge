"""Validate and save immutable proposals; never modify active device maps."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import uuid


def validate_draft(raw, monitor):
    if not isinstance(raw, dict):
        raise ValueError('Ungueltiger Entwurf')
    category = raw.get('category')
    if category not in ('lights', 'switches', 'shutters', 'motions', 'contacts', 'thermostats'):
        raise ValueError('Kategorie nicht unterstuetzt; Alarm bleibt gesperrt')
    name = raw.get('name', '')
    if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError('Name erforderlich, maximal 80 Zeichen')
    def integer(field):
        value = raw.get(field)
        if type(value) is not int or not 0 <= value <= 2147483647:
            raise ValueError(f'{field}: nichtnegative ganze Zahl erforderlich')
        return value
    dev_id, st = integer('id'), integer('statetype')
    info = dict(name=name.strip(), statetype=st)
    endpoints = [(dev_id, st)]
    if category == 'contacts':
        cls = raw.get('device_class')
        if cls not in ('door', 'window', 'garage_door'):
            raise ValueError('Kontaktart erforderlich')
        info['device_class'] = cls
    if category == 'shutters':
        # Commands share the device ID but can use a separate statetype.
        info['statetype'] = st
        if 'command_statetype' in raw:
            command_st = integer('command_statetype')
            info['command_statetype'] = command_st
            if command_st != st:
                endpoints.append((dev_id, command_st))
    if category == 'thermostats':
        info = dict(name=name.strip(), target=dict(statetype=st),
                    current=dict(id=integer('current_id'), statetype=integer('current_statetype')),
                    mode=dict(id=integer('mode_id'), statetype=integer('mode_statetype')))
        endpoints.extend((part['id'], part['statetype']) for part in (info['current'], info['mode']))
        for field in ('min_temp', 'max_temp', 'temp_step'):
            value = raw.get(field)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f'{field}: endliche Zahl erforderlich')
            info[field] = value
        if not -50 <= info['min_temp'] < info['max_temp'] <= 100 or not 0 < info['temp_step'] <= info['max_temp'] - info['min_temp']:
            raise ValueError('Temperaturgrenzen oder Schrittweite ungueltig')
    if len(set(endpoints)) != len(endpoints):
        raise ValueError('Endpunkte duerfen nicht mehrfach verwendet werden')
    if (39, 111) in endpoints:
        raise ValueError('clock_read_only')
    with monitor.lock:
        for endpoint in endpoints:
            if f'{endpoint[0]}:{endpoint[1]}' in monitor.routes:
                raise ValueError(f'Endpunkt {endpoint} ist bereits zugeordnet')
        if any(d['uid'] == f'{category}:{dev_id}' for d in monitor.devices):
            raise ValueError('Geraete-ID in dieser Kategorie bereits vorhanden')
    return dict(category=category, device_id=str(dev_id), configuration=info)


def save_draft(directory, draft):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Exclusive immutable files: saving never overwrites an earlier proposal.
    filename = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex + '.json'
    with (directory / filename).open('x', encoding='utf-8') as stream:
        json.dump(dict(version=1, active=False, draft=draft), stream, indent=2, ensure_ascii=True)
    return filename
