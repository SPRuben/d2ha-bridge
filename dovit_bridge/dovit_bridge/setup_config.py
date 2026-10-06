"""Private setup overrides, applied only on the next operator restart."""
from dataclasses import replace
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import threading
import uuid

FIELDS = ('dovit_host', 'dovit_port', 'mqtt_mode', 'mqtt_host', 'mqtt_port',
          'mqtt_user', 'mqtt_tls', 'mqtt_protocol', 'publish_discovery')
_UNREADABLE = object()


def setup_path():
    return Path('/data/dovit_setup.json') if Path('/data/options.json').exists() else Path('dovit_setup.json')


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) != set(FIELDS):
        raise ValueError('setup_invalid')
    result = dict(settings)
    for key in ('dovit_host', 'mqtt_host'):
        value = result[key]
        if not isinstance(value, str) or not value or len(value) > 253 or any(
                c.isspace() or c in '/\\@?#' or ord(c) < 32 for c in value):
            raise ValueError('setup_invalid_host')
    for key in ('dovit_port', 'mqtt_port'):
        if type(result[key]) is not int or not 1 <= result[key] <= 65535:
            raise ValueError('setup_invalid_port')
    if result['mqtt_mode'] not in ('manual', 'supervisor'):
        raise ValueError('setup_invalid')
    if result['mqtt_protocol'] not in ('3.1', '3.1.1', '5'):
        raise ValueError('setup_invalid')
    if not isinstance(result['mqtt_user'], str) or len(result['mqtt_user']) > 256 or any(
            ord(c) < 32 for c in result['mqtt_user']):
        raise ValueError('setup_invalid')
    if type(result['mqtt_tls']) is not bool or type(result['publish_discovery']) is not bool:
        raise ValueError('setup_invalid')
    return result


def _read_bytes(path, limit):
    """Only an absent file is a fresh setup; never suppress a storage error."""
    try:
        with path.open('rb') as source:
            raw = source.read(limit + 1)
    except FileNotFoundError:
        return None
    except OSError:
        raise ValueError('setup_storage_error') from None
    if len(raw) > limit:
        raise ValueError('setup_storage_error')
    return raw


def _read(path):
    try:
        raw = _read_bytes(path, 16384)
        if raw is None:
            return None, None
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        document = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(document, dict) or set(document) != {'settings', 'mqtt_pass'}:
            raise ValueError()
        validate_settings(document['settings'])
        if not isinstance(document['mqtt_pass'], str) or len(document['mqtt_pass']) > 1024:
            raise ValueError()
        return raw, document
    except (ValueError, TypeError, OSError, RecursionError):
        raise ValueError('setup_storage_error') from None


def apply_setup_overrides(cfg, path=None):
    _, document = _read(Path(path) if path is not None else setup_path())
    return replace(cfg, **document['settings'], mqtt_pass=document['mqtt_pass']) if document else cfg


class SetupConfig:
    def __init__(self, cfg, path=None, simulation=False):
        self.cfg = cfg  # Manual base configuration, never resolved service credentials.
        self.path = Path(path) if path is not None else setup_path()
        self.simulation = simulation
        self.lock = threading.RLock()
        self.revision_key = os.urandom(32)
        try:
            self.initial = self._raw()
        except ValueError:
            # Keep the repair server usable without pretending the original is absent.
            self.initial = _UNREADABLE

    def _raw(self):
        return _read_bytes(self.path, 1024 * 1024)

    def _current(self):
        damaged = False
        try:
            raw, document = _read(self.path)
        except ValueError:
            raw, document, damaged = self._raw(), None, True
        settings = document['settings'] if document else {key: getattr(self.cfg, key) for key in FIELDS}
        password = document['mqtt_pass'] if document else self.cfg.mqtt_pass
        fingerprint = json.dumps(dict(settings=settings, mqtt_pass=password), sort_keys=True).encode()
        revision = hmac.new(self.revision_key, (raw or b'') + fingerprint, hashlib.sha256).hexdigest()
        return raw, settings, password, revision, damaged

    def snapshot(self):
        with self.lock:
            try:
                raw, settings, password, revision, damaged = self._current()
            except ValueError:
                # These are explicitly labelled base fields, never recovered secrets.
                # No revision is issued because a safe source backup is impossible.
                return dict(revision=None, settings={key: getattr(self.cfg, key) for key in FIELDS},
                            password_set=None, pending=False, simulation=self.simulation,
                            damaged=True, writable=False, storage_error='setup_storage_error',
                            automatic_discovery=bool(self.cfg.enable_discovery))
            return dict(revision=revision, settings=settings, password_set=bool(password),
                        pending=raw != self.initial, simulation=self.simulation, damaged=damaged,
                        writable=True, storage_error=None,
                        automatic_discovery=bool(self.cfg.enable_discovery))

    def save(self, request):
        with self.lock:
            if not isinstance(request, dict) or set(request) - {'revision', 'settings', 'confirm', 'mqtt_pass', 'confirm_recovery'}:
                raise ValueError('setup_invalid')
            if request.get('confirm') is not True:
                raise ValueError('setup_confirm')
            raw, _, password, revision, damaged = self._current()
            if request.get('revision') != revision:
                raise ValueError('setup_stale')
            if damaged and request.get('confirm_recovery') is not True:
                raise ValueError('setup_recovery_confirm')
            settings = validate_settings(request.get('settings'))
            new_password = request.get('mqtt_pass')
            if new_password is not None:
                if not isinstance(new_password, str) or len(new_password) > 1024:
                    raise ValueError('setup_invalid')
                if new_password:
                    password = new_password
            document = dict(settings=settings, mqtt_pass=password)
            encoded = (json.dumps(document, ensure_ascii=True, indent=2) + '\n').encode()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if raw is not None:
                backup_dir = self.path.parent / 'dovit_setup_backups'
                backup_dir.mkdir(mode=0o700, exist_ok=True)
                backup = backup_dir / (uuid.uuid4().hex + '.json')
                with backup.open('xb') as file:
                    os.chmod(backup, 0o600)
                    file.write(raw)
                    file.flush()
                    os.fsync(file.fileno())
            fd, temporary = tempfile.mkstemp(prefix='.dovit_setup_', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'wb') as file:
                    file.write(encoded)
                    file.flush()
                    os.fsync(file.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return dict(pending=True, revision=self.snapshot()['revision'])
