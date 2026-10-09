"""Restricted recovery service: file operations only, never device transports."""
import hashlib
import heapq
import os
from pathlib import Path
import uuid

from .recovery import CATEGORIES, MAX_BYTES, digest, restore, validate_recovery_document
from .storage import configuration_lock

MAX_ORIGINAL_BYTES = 4 * 1024 * 1024


class RecoveryManager:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = configuration_lock(self.path)
        self.validation = None
        self.completed = None
        self.backup_ids = {}

    def _inspect(self, path, limit):
        try:
            with path.open('rb') as stream:
                content = stream.read(limit + 1)
            if len(content) > limit:
                return {'state': 'oversized', 'revision': None}
        except FileNotFoundError:
            return {'state': 'missing', 'revision': 'missing'}
        except OSError:
            return {'state': 'unreadable', 'revision': None}
        result = {'revision': digest(content), 'bytes': len(content)}
        try:
            maps = validate_recovery_document(content)
            result.update(state='valid', counts={key: len(maps.get(key, {})) for key in CATEGORIES},
                          contains_cleanup=bool(maps.get('_removed_discovery')))
        except (ValueError, TypeError, RecursionError):
            result['state'] = 'invalid'
        return result

    def _current(self):
        return self._inspect(self.path, MAX_ORIGINAL_BYTES)

    def _backups(self):
        directory = self.path.parent / 'dovit_device_backups'
        self.backup_ids = {}
        if not directory.exists() or directory.is_symlink():
            return []
        try:
            with os.scandir(directory) as entries:
                files = heapq.nlargest(100, (entry.name for entry in entries
                    if entry.name.endswith('.json') and entry.is_file(follow_symlinks=False)))
        except OSError:
            return []
        result = []
        for name in files:
            path = directory / name
            identifier = hashlib.sha256(name.encode()).hexdigest()
            self.backup_ids[identifier] = path
            status = self._inspect(path, MAX_BYTES)
            result.append(dict(id=identifier, name=name, **status))
        return result

    def status(self):
        with self.lock:
            return dict(recovery=True, current=self._current(), backups=self._backups(),
                        pending=self.path.with_name(self.path.stem + '.pending.json').exists(),
                        restored=self.completed is not None, restart_required=self.completed is not None)

    def _read_source(self, raw):
        has_document, has_backup, has_bytes = 'document' in raw, 'backup' in raw, 'file_bytes' in raw
        if sum((has_document, has_backup, has_bytes)) != 1:
            raise ValueError('recovery_source')
        if has_document:
            if not isinstance(raw['document'], str):
                raise ValueError('recovery_invalid')
            try:
                content = raw['document'].encode('utf-8')
            except UnicodeError:
                raise ValueError('recovery_invalid') from None
            source = None
        elif has_bytes:
            values = raw['file_bytes']
            if not isinstance(values, list) or len(values) > MAX_BYTES:
                raise ValueError('recovery_size')
            if any(type(value) is not int or not 0 <= value <= 255 for value in values):
                raise ValueError('recovery_invalid')
            content, source = bytes(values), None
        else:
            identifier = raw['backup']
            if not isinstance(identifier, str) or identifier not in self.backup_ids:
                raise ValueError('recovery_source')
            source = self.backup_ids[identifier]
            if source.is_symlink() or source.parent.is_symlink():
                raise ValueError('recovery_source')
            with source.open('rb') as stream:
                content = stream.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError('recovery_size')
        try:
            maps = validate_recovery_document(content)
        except (ValueError, TypeError, RecursionError, UnicodeError):
            raise ValueError('recovery_invalid') from None
        if maps.get('_removed_discovery'):
            raise ValueError('recovery_cleanup')
        return content, maps, source

    def validate(self, raw):
        with self.lock:
            self.validation = None
            if self.completed:
                raise ValueError('recovery_restart')
            if not isinstance(raw, dict):
                raise ValueError('recovery_invalid')
            current = self._current()
            if current['revision'] is None:
                raise ValueError('recovery_unreadable')
            if raw.get('revision') != current['revision']:
                raise ValueError('recovery_stale')
            if self.path.with_name(self.path.stem + '.pending.json').exists():
                raise ValueError('recovery_pending')
            content, maps, source = self._read_source(raw)
            counts = {category: len(maps.get(category, {})) for category in
                      ('lights', 'switches', 'shutters', 'thermostats', 'motions', 'contacts', 'alarms')}
            names = [dict(category=category, name=str(info.get('name', key))[:160])
                     for category in counts for key, info in maps.get(category, {}).items()]
            summary = dict(counts=counts, names=names[:200], names_truncated=len(names) > 200,
                           has_alarms=bool(counts['alarms']), empty=not any(counts.values()))
            self.validation = dict(id=uuid.uuid4().hex, revision=current['revision'], content=content,
                                   source=source, summary=summary)
            return dict(validation_id=self.validation['id'], revision=current['revision'], summary=summary)

    def apply(self, raw):
        with self.lock:
            if not isinstance(raw, dict):
                raise ValueError('recovery_invalid')
            if self.completed:
                if raw.get('validation_id') == self.completed['validation_id']:
                    return dict(restored=True, restart_required=True)
                raise ValueError('recovery_restart')
            checked = self.validation
            if not checked or raw.get('validation_id') != checked['id'] or raw.get('revision') != checked['revision']:
                raise ValueError('recovery_stale')
            if raw.get('confirm') is not True:
                raise ValueError('recovery_confirm')
            if checked['summary']['has_alarms'] and raw.get('confirm_alarm') is not True:
                raise ValueError('recovery_alarm_confirm')
            if checked['summary']['empty'] and raw.get('confirm_empty') is not True:
                raise ValueError('recovery_empty_confirm')
            if self.path.with_name(self.path.stem + '.pending.json').exists():
                raise ValueError('recovery_pending')
            if self._current()['revision'] != checked['revision']:
                self.validation = None
                raise ValueError('recovery_stale')
            source = checked['source']
            if source is not None:
                if source.is_symlink() or source.parent.is_symlink():
                    raise ValueError('recovery_source')
                with source.open('rb') as stream:
                    if stream.read(MAX_BYTES + 1) != checked['content']:
                        self.validation = None
                        raise ValueError('recovery_stale')
            temporary = self.path.with_name(self.path.name + '.upload.' + uuid.uuid4().hex + '.json')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with temporary.open('xb') as stream:
                    stream.write(checked['content'])
                    stream.flush()
                    os.fsync(stream.fileno())
                restore(self.path, temporary, revision=checked['revision'],
                        source_revision=digest(checked['content']), confirm=True, bridge_stopped=True)
                self.completed = {'validation_id': checked['id']}
                self.validation = None
                return dict(restored=True, restart_required=True)
            finally:
                temporary.unlink(missing_ok=True)
