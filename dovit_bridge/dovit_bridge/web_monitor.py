"""Bounded observations, staged configuration edits and optional light commands."""
from collections import OrderedDict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import socket
from pathlib import Path
import threading
import uuid
import time
from .mapping_drafts import validate_draft, save_draft

LOGGER = logging.getLogger(__name__)
TUTORIAL_IMAGE_ROUTES = frozenset(
    f'/manuals/images/{name}-{language}.jpg'
    for name in ('devices-overview', 'setup-dovit', 'setup-mqtt', 'setup-publication',
                 'device-assignment', 'diagnosis', 'json-review', 'recovery')
    for language in ('de', 'fr')
)


BRANDING_IMAGE_ROUTES = frozenset(
    '/branding/' + name for name in (
        'favicon-32.png', 'favicon-64.png', 'apple-touch-icon.png',
        'android-chrome-192.png', 'android-chrome-512.png', 'icon-light.png')
)


class Monitor:
    def __init__(self, secrets=()):
        self.lock = threading.RLock()
        self.secrets = tuple(str(s) for s in secrets if s)
        self.session = uuid.uuid4().hex
        self.sequence = 0
        self.connected = False
        self.devices = []
        self.inventory_configured = False
        self.routes = {}
        self.states = OrderedDict()
        self.events = deque(maxlen=500)
        self.candidates = OrderedDict()
        self.persistence_status = 'disabled'
        self.draft_directory = None
        self.light_control = None
        self.device_control = None
        self.device_editor = None
        self.recovery = None
        self.runtime_status = None
        self.setup_config = None
        self.commands = OrderedDict()

    def safe(self, value):
        text = str(value)
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, '[REDACTED]')
        return text[:160]

    def configure(self, maps, include_system=False):
        devices, routes = [], {}
        for category, entries in maps.items():
            for key, info in entries.items():
                uid = f'{category}:{key}'
                # Same marker convention as publication filtering; not heuristic proof.
                inferred = str(info.get('name') or '').strip().upper().startswith('TODO_')
                endpoints = []
                if category == 'thermostats':
                    for role in ('target', 'current', 'mode'):
                        part = info.get(role, {}) or {}
                        if 'statetype' in part:
                            endpoints.append((int(part.get('id', key)), int(part['statetype']), role))
                elif category == 'alarms':
                    for role in ('state', 'text', 'trigger', 'command'):
                        if role + '_statetype' in info:
                            endpoints.append((int(key), int(info[role + '_statetype']), role))
                elif 'statetype' in info:
                    endpoints.append((int(key), int(info['statetype']), 'state'))
                devices.append(dict(uid=uid, name=self.safe(info.get('name', uid)), category=category,
                                    endpoints=endpoints,
                                    classification='inferred' if inferred else 'confirmed',
                                    provenance='todo_name_marker' if inferred else 'configuration'))
                if category == 'thermostats':
                    devices[-1]['limits'] = {k: info.get(k, default) for k, default in
                                            [('min_temp', 5), ('max_temp', 35), ('temp_step', .5)]}
                for dev_id, statetype, role in endpoints:
                    routes.setdefault(f'{dev_id}:{statetype}', []).append(dict(uid=uid, role=role))
        # Only the live inventory adds system signals, not temporary editor maps.
        if include_system and '39:111' not in routes:
            devices.append(dict(uid='clocks:39', name='Dovit', category='clocks',
                                endpoints=[(39, 111, 'time')], read_only=True,
                                classification='confirmed', provenance='system'))
            routes['39:111'] = [dict(uid='clocks:39', role='time')]
        with self.lock:
            self.devices, self.routes = devices, routes
            self.inventory_configured = True

    def observe(self, dev_id, statetype, value):
        with self.lock:
            key = f'{dev_id}:{statetype}'
            value = self.safe(value)
            previous = self.states.get(key)
            # Equivalent numeric strings are duplicate reports, not changes.
            def equivalent(a, b):
                try:
                    return float(a) == float(b)
                except (ValueError, TypeError):
                    return a == b
            changed = previous is not None and not equivalent(previous['value'], value)
            self.sequence += 1
            event = dict(seq=self.sequence, key=key, device_id=dev_id, statetype=statetype,
                         time=datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                         value=value, previous=previous['value'] if previous else None,
                         provenance='received_signal',
                         kind='first' if previous is None else 'change' if changed else 'repeat',
                         count=previous['count'] + 1 if previous else 1)
            self.states[key] = event
            self.states.move_to_end(key)
            if len(self.states) > 2000:
                self.states.popitem(last=False)
            self.events.append(event)
            for command in self.commands.values():
                if command['status'] not in ('requested', 'transmitted') or time.monotonic()-command['started'] > 12:
                    continue
                if (dev_id, statetype) == (command['id'], command['statetype']) and event['seq'] > command['after']:
                    try:
                        match = (abs(float(value)-command['expected']) < 0.001 if 'expected' in command
                                 else (float(value) >= .5) == (command['action'] == 'ON'))
                    except ValueError:
                        match = False
                    if match:
                        command['matched'] = True
                        if command['status'] == 'transmitted':
                            command['status'] = 'observed'
            if key not in self.routes:
                candidate = self.candidates.get(key)
                values = list(candidate['values']) if candidate else []
                if value not in values:
                    values = (values + [value])[-20:]
                self.candidates[key] = dict(event, seq=0, kind='historical',
                    first_seen=candidate['first_seen'] if candidate else event['time'],
                    count=candidate['count'] + 1 if candidate else 1, values=values)
                self.candidates.move_to_end(key)
                if len(self.candidates) > 2000:
                    self.candidates.popitem(last=False)

    def snapshot(self):
        with self.lock:
            for command in self.commands.values():
                if command['status'] in ('requested', 'transmitted') and time.monotonic()-command['started'] > 12:
                    command['status'] = 'timeout'
            classifications = {device['uid']: device['classification'] for device in self.devices}
            def enrich(event):
                matches = self.routes.get(event['key'], [])
                # Confirmed means configured, not physical identity or execution proof.
                # Re-match retained evidence against current routes on every snapshot.
                kinds = {classifications[match['uid']] for match in matches}
                classification = ('confirmed' if 'confirmed' in kinds else
                                  'inferred' if kinds else 'observed')
                return dict(event, matches=matches, classification=classification)
            historical = [enrich(e) for key, e in self.candidates.items()
                          if key not in self.states and key not in self.routes]
            return dict(session=self.session, sequence=self.sequence, connected=self.connected, devices=self.devices,
                        inventory_configured=self.inventory_configured,
                        setup=self.runtime_status() if self.runtime_status else None,
                        persistence=self.persistence_status,
                        draft_saving=self.draft_directory is not None, draft_token=self.session,
                        light_control='simulation' if self.light_control and self.light_control.simulation else 'live' if self.light_control else 'disabled',
                        device_control='simulation' if self.device_control and self.device_control.simulation else 'live' if self.device_control else 'disabled',
                        commands=[{k:v for k,v in c.items() if k not in ('started', 'after', 'matched')} for c in list(self.commands.values())[-30:]],
                        states=historical + [enrich(e) for e in self.states.values()],
                        events=[enrich(e) for e in self.events], capacity=500)


def make_server(monitor, host='0.0.0.0', port=8099, allowed_peer=None):
    assets = Path(__file__).with_name('web')

    def peer_allowed(address):
        # An explicit peer is used only by local previews/tests. Production
        # resolves the Supervisor on every request, including after DNS changes.
        if allowed_peer is not None:
            return address == allowed_peer
        try:
            peers = socket.getaddrinfo('supervisor', None, socket.AF_INET,
                                       socket.SOCK_STREAM)
        except OSError:
            return False  # DNS failure must never open access to other peers.
        return address in {peer[4][0] for peer in peers}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if not peer_allowed(self.client_address[0]) or self.headers.get('X-Dovit-Token') != monitor.session:
                self.send_error(403)
                return
            if self.path not in ('/api/drafts/validate', '/api/drafts/save', '/api/lights/command', '/api/controls/command',
                                 '/api/devices/validate', '/api/devices/save', '/api/devices/cancel',
                                 '/api/recovery/validate', '/api/recovery/apply', '/api/setup'):
                self.send_error(404)
                return
            try:
                recovery_request = self.path.startswith('/api/recovery/')
                if monitor.recovery is not None and not recovery_request:
                    raise ValueError('recovery_only')
                if recovery_request and monitor.recovery is None:
                    raise ValueError('recovery_disabled')
                length = int(self.headers.get('Content-Length', '0'))
                limit = 2 * 1024 * 1024 if self.path in ('/api/devices/validate', '/api/devices/save', '/api/recovery/validate') else 8192
                if not 0 < length <= limit or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('Ungueltige Anfrage')
                raw = json.loads(self.rfile.read(length))
                if self.path == '/api/setup':
                    if monitor.setup_config is None:
                        raise ValueError('setup_disabled')
                    result = monitor.setup_config.save(raw)
                elif recovery_request:
                    result = (monitor.recovery.validate(raw) if self.path.endswith('/validate')
                              else monitor.recovery.apply(raw))
                elif self.path.startswith('/api/devices/'):
                    if monitor.device_editor is None:
                        raise ValueError('edit_disabled')
                    if self.path.endswith('/cancel'):
                        if not isinstance(raw, dict) or raw.get('confirm') is not True:
                            raise ValueError('edit_confirm')
                        result = monitor.device_editor.cancel()
                    else:
                        result = monitor.device_editor.request(raw, self.path.endswith('/save'))
                elif self.path == '/api/controls/command':
                    if monitor.device_control is None:
                        raise ValueError('control_disabled')
                    result = dict(command=monitor.device_control.submit(raw))
                elif self.path == '/api/lights/command':
                    if monitor.light_control is None:
                        raise ValueError('light_disabled')
                    result = dict(command=monitor.light_control.submit(raw))
                else:
                    draft = validate_draft(raw, monitor)
                    result = dict(draft=draft, active=False)
                if self.path == '/api/drafts/save':
                    if monitor.draft_directory is None:
                        raise ValueError('Vorschau: Speichern deaktiviert')
                    result['filename'] = save_draft(monitor.draft_directory, draft)
                status = 200
            except (ValueError, TypeError, RecursionError) as exc:
                status, result = 400, dict(error=str(exc))
            except OSError:
                LOGGER.error('Configuration request failed; file operation unsuccessful')
                status, result = 500, dict(error='recovery_storage' if self.path.startswith('/api/recovery/') else
                                         'setup_storage_error' if self.path == '/api/setup' else 'edit_storage_error')
            body = json.dumps(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_GET(self):
            # Trust the TCP peer, never a spoofable forwarded header.
            if not peer_allowed(self.client_address[0]):
                self.send_error(403)
                return
            path = self.path.split('?', 1)[0]
            if monitor.recovery is not None and path in ('/api/snapshot', '/api/devices', '/api/setup'):
                self.send_error(503)
                return
            if path == '/api/recovery':
                if monitor.recovery is None:
                    self.send_error(404)
                    return
                result = monitor.recovery.status()
                result['token'] = monitor.session
                data = json.dumps(result, ensure_ascii=True).encode()
                mime = 'application/json'
            elif path == '/api/setup':
                try:
                    result = monitor.setup_config.snapshot() if monitor.setup_config else dict(disabled=True)
                    data = json.dumps(result, ensure_ascii=True).encode()
                except (OSError, ValueError):
                    self.send_error(503)
                    return
                mime = 'application/json'
            elif path == '/api/snapshot':
                data = json.dumps(monitor.snapshot(), ensure_ascii=True).encode()
                mime = 'application/json'
            elif path == '/api/devices':
                try:
                    result = monitor.device_editor.snapshot() if monitor.device_editor else dict(disabled=True)
                    data = json.dumps(result, ensure_ascii=True).encode()
                except (OSError, ValueError):
                    self.send_error(503)
                    return
                mime = 'application/json'
            elif path in ('/manuals/USER_DE.md', '/manuals/USER_FR.md', '/manuals/DEVELOPER.md'):
                data = (assets.parent / 'manuals' / path.rsplit('/', 1)[1]).read_bytes()
                mime = 'text/plain'
            elif path in TUTORIAL_IMAGE_ROUTES:
                try:
                    data = (assets.parent / 'manuals' / 'images' / path.rsplit('/', 1)[1]).read_bytes()
                except OSError:
                    self.send_error(404)
                    return
                mime = 'image/jpeg'
            elif path in BRANDING_IMAGE_ROUTES:
                data = (assets / 'branding' / path.rsplit('/', 1)[1]).read_bytes()
                mime = 'image/png'
            elif path in ('/brand.css', '/help.js', '/help.css', '/devices.js', '/json-editor.js', '/recovery.js', '/recovery.css', '/setup.js', '/change-review.js', '/onboarding.js', '/onboarding.css'):
                data = (assets / path[1:]).read_bytes()
                mime = 'text/javascript' if path.endswith('.js') else 'text/css'
            elif path in ('/', '/index.html', '/app.js', '/i18n.js', '/style.css', '/mapping.css'):
                name = 'index.html' if path == '/' else path[1:]
                if monitor.recovery is not None and name == 'index.html':
                    name = 'recovery.html'
                data = (assets / name).read_bytes()
                mime = {'index.html': 'text/html', 'recovery.html': 'text/html', 'app.js': 'text/javascript', 'i18n.js': 'text/javascript', 'style.css': 'text/css', 'mapping.css': 'text/css'}[name]
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime if mime.startswith('image/') else mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass  # Ingress paths and session tokens must not enter logs.

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def start_monitor(monitor):
    server = make_server(monitor)
    threading.Thread(target=server.serve_forever, name='dovit-monitor', daemon=True).start()
    LOGGER.info('Web monitor started port=8099 ingress-only')
    return server
