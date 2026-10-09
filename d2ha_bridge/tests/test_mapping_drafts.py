import json
from pathlib import Path
import tempfile
import unittest
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from dovit_bridge.mapping_drafts import validate_draft, save_draft
from dovit_bridge.web_monitor import Monitor, make_server


class DraftTests(unittest.TestCase):
    def test_http_token_validation_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor = Monitor()
            monitor.draft_directory = Path(tmp)
            server = make_server(monitor, '127.0.0.1', 0, '127.0.0.1')
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            payload = json.dumps(dict(category='lights', name='Test', id=99, statetype=0)).encode()
            def request(action, token):
                return urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/drafts/{action}',
                    data=payload, headers={'Content-Type': 'application/json', 'X-Dovit-Token': token}))
            try:
                with self.assertRaises(HTTPError) as raised:
                    request('save', 'invalid')
                self.assertEqual(raised.exception.code, 403)
                raised.exception.close()
                self.assertEqual(list(Path(tmp).iterdir()), [])
                with request('validate', monitor.session) as response:
                    self.assertFalse(json.load(response)['active'])
                self.assertEqual(list(Path(tmp).iterdir()), [])
                with request('save', monitor.session) as response:
                    saved = json.load(response)
                self.assertTrue((Path(tmp) / saved['filename']).exists())
                self.assertEqual(monitor.devices, [])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_categories_and_schema(self):
        for category in ('lights', 'motions', 'contacts', 'shutters'):
            result = validate_draft(dict(category=category, name='Office', id=99, statetype=0, device_class='window'), Monitor())
            self.assertEqual(result['configuration']['statetype'], 0)
            self.assertEqual(result['device_id'], '99')

    def test_conflict_and_alarm_rejected(self):
        m = Monitor()
        m.configure({'lights': {99: {'statetype': 0}}})
        for category in ('motions', 'alarms'):
            with self.assertRaises(ValueError):
                validate_draft(dict(category=category, name='Office', id=99, statetype=0), m)

    def test_thermostat_validation(self):
        raw = dict(category='thermostats', name='Office', id=44, statetype=1,
                   current_id=42, current_statetype=1, mode_id=46, mode_statetype=0,
                   min_temp=16, max_temp=26, temp_step=.5)
        self.assertEqual(validate_draft(raw, Monitor())['configuration']['current']['id'], 42)
        for change in (dict(temp_step=0), dict(min_temp=float('nan')), dict(id=True), dict(current_id=44)):
            with self.assertRaises(ValueError):
                validate_draft(dict(raw, **change), Monitor())

    def test_immutable_drafts_do_not_touch_maps(self):
        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / 'dovit_devices.json'
            active.write_text('{"lights": {}}')
            directory = Path(tmp) / 'drafts'
            draft = validate_draft(dict(category='lights', name='Office', id=99, statetype=0), Monitor())
            a, b = save_draft(directory, draft), save_draft(directory, draft)
            self.assertNotEqual(a, b)
            self.assertFalse(json.loads((directory / a).read_text())['active'])
            self.assertEqual(active.read_text(), '{"lights": {}}')
