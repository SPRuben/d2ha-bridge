import json
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from dovit_bridge.config import Config
from dovit_bridge.setup_config import SetupConfig, apply_setup_overrides
from dovit_bridge.web_monitor import Monitor, make_server


class SetupConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'setup.json'
        self.cfg = Config(mqtt_pass='private-password', alarm_code='private-alarm')
        self.setup = SetupConfig(self.cfg, self.path, simulation=True)

    def request(self):
        status = self.setup.snapshot()
        return dict(revision=status['revision'], settings=status['settings'], confirm=True)

    def test_snapshot_has_no_password_or_alarm(self):
        text = json.dumps(self.setup.snapshot())
        self.assertNotIn('private-password', text)
        self.assertNotIn('private-alarm', text)
        self.assertNotIn('mqtt_pass', text)
        self.assertTrue(self.setup.snapshot()['password_set'])

    def test_next_start_only_and_explicit_supervisor_selection(self):
        request = self.request()
        request['settings']['mqtt_mode'] = 'supervisor'
        self.setup.save(request)
        self.assertEqual(self.cfg.mqtt_mode, 'manual')
        self.assertEqual(apply_setup_overrides(self.cfg, self.path).mqtt_mode, 'supervisor')
        self.assertTrue(self.setup.snapshot()['pending'])
        self.assertFalse(SetupConfig(self.cfg, self.path).snapshot()['pending'])

    def test_no_override_keeps_upgrade_manual(self):
        self.assertEqual(apply_setup_overrides(self.cfg, self.path), self.cfg)

    def test_confirm_and_revision_guards(self):
        request = self.request()
        request['confirm'] = False
        with self.assertRaisesRegex(ValueError, 'setup_confirm'):
            self.setup.save(request)
        request['confirm'] = True
        self.setup.save(request)
        with self.assertRaisesRegex(ValueError, 'setup_stale'):
            self.setup.save(request)

    def test_invalid_fields_never_write(self):
        for key, value in [('dovit_host', 'host/path'), ('mqtt_port', True),
                           ('mqtt_port', 65536), ('mqtt_mode', 'auto'),
                           ('mqtt_tls', 'false'), ('publish_discovery', 1)]:
            with self.subTest(key=key, value=value):
                request = self.request()
                request['settings'][key] = value
                with self.assertRaises(ValueError):
                    self.setup.save(request)
                self.assertFalse(self.path.exists())

    def test_protected_options_cannot_be_set(self):
        request = self.request()
        request['settings']['alarm_code'] = '1234'
        with self.assertRaisesRegex(ValueError, 'setup_invalid'):
            self.setup.save(request)

    def test_automatic_discovery_is_read_only_and_survives_all_publication_choices(self):
        for automatic in (False, True):
            for publishing in (False, True):
                with self.subTest(automatic=automatic, publishing=publishing):
                    cfg = replace(self.cfg, enable_discovery=automatic)
                    path = self.path.parent / f'setup-{automatic}-{publishing}.json'
                    setup = SetupConfig(cfg, path)
                    snapshot = setup.snapshot()
                    self.assertIs(snapshot['automatic_discovery'], automatic)
                    self.assertNotIn('enable_discovery', snapshot['settings'])
                    request = dict(revision=snapshot['revision'], settings=snapshot['settings'], confirm=True)
                    request['settings']['publish_discovery'] = publishing
                    setup.save(request)
                    staged = apply_setup_overrides(cfg, path)
                    self.assertIs(staged.enable_discovery, automatic)
                    self.assertIs(staged.publish_discovery, publishing)
                    self.assertIs(setup.snapshot()['automatic_discovery'], automatic)
                    self.assertNotIn('automatic_discovery', json.loads(path.read_text()))
                    self.assertEqual(cfg, replace(self.cfg, enable_discovery=automatic))

    def test_automatic_discovery_cannot_be_posted_as_an_option(self):
        for key in ('enable_discovery', 'automatic_discovery'):
            with self.subTest(key=key):
                request = self.request()
                request['settings'][key] = True
                with self.assertRaisesRegex(ValueError, 'setup_invalid'):
                    self.setup.save(request)
                self.assertFalse(self.path.exists())
        request = self.request()
        request['automatic_discovery'] = True
        with self.assertRaisesRegex(ValueError, 'setup_invalid'):
            self.setup.save(request)
        self.assertFalse(self.path.exists())

    def test_blank_password_preserves_and_new_password_is_private(self):
        request = self.request()
        request['mqtt_pass'] = ''
        self.setup.save(request)
        self.assertEqual(apply_setup_overrides(self.cfg, self.path).mqtt_pass, 'private-password')
        request = self.request()
        request['mqtt_pass'] = 'replacement-password'
        self.setup.save(request)
        self.assertEqual(apply_setup_overrides(self.cfg, self.path).mqtt_pass, 'replacement-password')
        self.assertNotIn('replacement-password', json.dumps(self.setup.snapshot()))

    def test_corruption_and_duplicate_keys_preserved(self):
        for raw in (b'broken', b'{"settings":{},"settings":{},"mqtt_pass":""}'):
            self.path.write_bytes(raw)
            self.assertTrue(self.setup.snapshot()['damaged'])
            with self.assertRaisesRegex(ValueError, 'setup_recovery_confirm'):
                self.setup.save(self.request())
            with self.assertRaisesRegex(ValueError, 'setup_storage_error'):
                apply_setup_overrides(self.cfg, self.path)
            self.assertEqual(self.path.read_bytes(), raw)

    def test_corrupt_setup_repair_requires_extra_consent_and_preserves_backup(self):
        self.path.write_bytes(b'{broken')
        request = self.request()
        request['confirm_recovery'] = True
        self.setup.save(request)
        self.assertFalse(self.setup.snapshot()['damaged'])
        backup = next((self.path.parent / 'dovit_setup_backups').glob('*.json'))
        self.assertEqual(backup.read_bytes(), b'{broken')

    def test_oversized_setup_has_read_only_base_snapshot_and_cannot_be_replaced(self):
        original = b'x' * (1024 * 1024 + 1)
        self.path.write_bytes(original)
        setup = SetupConfig(self.cfg, self.path)
        snapshot = setup.snapshot()
        self.assertFalse(snapshot['writable'])
        self.assertIsNone(snapshot['revision'])
        self.assertIsNone(snapshot['password_set'])
        self.assertEqual(snapshot['storage_error'], 'setup_storage_error')
        self.assertEqual(snapshot['settings']['dovit_host'], self.cfg.dovit_host)
        self.assertNotIn(self.cfg.mqtt_pass, json.dumps(snapshot))
        with self.assertRaisesRegex(ValueError, 'setup_storage_error'):
            setup.save(dict(revision=None, settings=snapshot['settings'],
                            confirm=True, confirm_recovery=True, mqtt_pass='replacement'))
        with self.assertRaisesRegex(ValueError, 'setup_storage_error'):
            apply_setup_overrides(self.cfg, self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.path.parent / 'dovit_setup_backups').exists())

    def test_unreadable_setup_remains_present_and_save_is_fail_closed(self):
        original = b'{"private":"not displayed"}'
        self.path.write_bytes(original)
        original_open = Path.open

        def inaccessible(path, *args, **kwargs):
            if path == self.path:
                raise PermissionError('private storage details')
            return original_open(path, *args, **kwargs)

        with patch('dovit_bridge.setup_config.Path.open', new=inaccessible):
            setup = SetupConfig(self.cfg, self.path)
            snapshot = setup.snapshot()
            self.assertFalse(snapshot['writable'])
            self.assertTrue(snapshot['damaged'])
            self.assertIsNone(snapshot['revision'])
            self.assertNotIn('private storage details', json.dumps(snapshot))
            with self.assertRaisesRegex(ValueError, 'setup_storage_error'):
                setup.save(dict(revision=None, settings=snapshot['settings'],
                                confirm=True, confirm_recovery=True))
            with self.assertRaisesRegex(ValueError, 'setup_storage_error'):
                apply_setup_overrides(self.cfg, self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.path.parent / 'dovit_setup_backups').exists())

    def test_revision_is_not_a_public_password_verifier(self):
        same_config = SetupConfig(self.cfg, self.path)
        self.assertNotEqual(self.setup.snapshot()['revision'], same_config.snapshot()['revision'])

    def test_replace_failure_preserves_original(self):
        self.setup.save(self.request())
        original = self.path.read_bytes()
        request = self.request()
        request['settings']['dovit_port'] = 6061
        with patch('dovit_bridge.setup_config.os.replace', side_effect=OSError):
            with self.assertRaises(OSError):
                self.setup.save(request)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.path.parent.glob('.dovit_setup_*')))
        self.assertEqual(next((self.path.parent / 'dovit_setup_backups').glob('*.json')).read_bytes(), original)

    def test_http_setup_tokens_and_recovery_isolation(self):
        monitor = Monitor()
        monitor.setup_config = self.setup
        server = make_server(monitor, host='127.0.0.1', port=0, allowed_peer='127.0.0.1')
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            with urlopen(base + '/api/setup', timeout=2) as response:
                snapshot = json.load(response)
            self.assertNotIn('private-password', json.dumps(snapshot))
            payload = json.dumps(self.request()).encode()
            request = Request(base + '/api/setup', data=payload, headers={'Content-Type': 'application/json'})
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=2)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            request.add_header('X-Dovit-Token', monitor.session)
            with urlopen(request, timeout=2) as response:
                self.assertTrue(json.load(response)['pending'])
            monitor.recovery = object()
            with self.assertRaises(HTTPError) as error:
                urlopen(base + '/api/setup', timeout=2)
            self.assertEqual(error.exception.code, 503)
            error.exception.close()
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=2)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
