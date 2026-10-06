import json
from pathlib import Path
import re
import threading
import unittest
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from dovit_bridge.web_monitor import Monitor, make_server


class MonitorTests(unittest.TestCase):
    def test_empty_inventory_requires_successful_configuration(self):
        monitor = Monitor()
        self.assertFalse(monitor.snapshot()['inventory_configured'])
        monitor.observe(999, 3, '1')
        self.assertFalse(monitor.snapshot()['inventory_configured'])
        with self.assertRaises((ValueError, TypeError)):
            monitor.configure({'lights': {'invalid': {'statetype': 0}}})
        self.assertFalse(monitor.snapshot()['inventory_configured'])
        monitor.configure({}, include_system=True)
        self.assertTrue(monitor.snapshot()['inventory_configured'])
        self.assertEqual([device['category'] for device in monitor.snapshot()['devices']], ['clocks'])

    def test_page_scripts_are_served_complete_and_uncached(self):
        server = make_server(Monitor(), '127.0.0.1', 0, '127.0.0.1')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        assets = Path(__file__).parents[1] / 'dovit_bridge' / 'web'
        try:
            with urlopen(base + '/', timeout=5) as response:
                scripts = re.findall(r'<script src="([^"]+)"', response.read().decode('utf-8'))
            self.assertIn('change-review.js', scripts)
            self.assertLess(scripts.index('change-review.js'), scripts.index('devices.js'))
            for script in scripts:
                with self.subTest(script=script), urlopen(base + '/' + script, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get_content_type(), 'text/javascript')
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                    self.assertEqual(response.read(), (assets / script).read_bytes())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_system_clock_is_read_only_and_exact_endpoint(self):
        m = Monitor()
        m.configure({}, include_system=True)
        m.observe(39, 111, '15;44')
        m.observe(39, 0, '1')
        result = m.snapshot()
        self.assertEqual(result['devices'][0]['category'], 'clocks')
        self.assertTrue(result['devices'][0]['read_only'])
        self.assertEqual(result['states'][0]['matches'], [{'uid': 'clocks:39', 'role': 'time'}])
        self.assertEqual(result['states'][0]['value'], '15;44')
        self.assertEqual(result['states'][1]['matches'], [])
        self.assertNotIn('39:111', m.candidates)
        m.configure({}, include_system=True)
        self.assertEqual(len(m.devices), 1)

    def test_temporary_inventory_has_no_implicit_clock(self):
        m = Monitor()
        m.configure({'lights': {19: {'name': 'Office', 'statetype': 0}}})
        self.assertEqual(list(m.routes), ['19:0'])

    def test_existing_mapping_is_not_overwritten(self):
        m = Monitor()
        m.configure({'lights': {39: {'name': 'Existing', 'statetype': 111}}}, include_system=True)
        self.assertEqual(len(m.devices), 1)
        self.assertEqual(m.devices[0]['name'], 'Existing')

    def test_clock_cannot_be_assigned_as_light_or_command(self):
        from dovit_bridge.mapping_drafts import validate_draft
        for raw in [dict(category='lights', id=39, statetype=111, name='Clock'),
                    dict(category='shutters', id=39, statetype=0, command_statetype=111, name='Clock')]:
            with self.assertRaisesRegex(ValueError, 'clock_read_only'):
                validate_draft(raw, Monitor())

    def test_changes_duplicates_and_unknown(self):
        m = Monitor(('secret',))
        m.configure({'lights': {19: {'name': 'Office', 'statetype': 0}}})
        for value in ('0', '0.0', '1'):
            m.observe(19, 0, value)
        m.observe(999, 1, 'secret')
        result = m.snapshot()
        self.assertEqual([e['kind'] for e in result['events']], ['first', 'repeat', 'change', 'first'])
        self.assertEqual(result['states'][0]['matches'][0]['uid'], 'lights:19')
        self.assertEqual(result['states'][1]['matches'], [])
        self.assertEqual(result['states'][1]['value'], '[REDACTED]')

    def test_separate_thermostat_endpoints(self):
        m = Monitor()
        m.configure({'thermostats': {44: {'target': {'statetype': 1}, 'current': {'id': 42, 'statetype': 1}, 'mode': {'id': 46, 'statetype': 0}}}})
        m.observe(42, 1, '22.3')
        self.assertEqual(m.snapshot()['events'][0]['matches'], [{'uid': 'thermostats:44', 'role': 'current'}])

    def test_bounded_history(self):
        m = Monitor()
        for i in range(2100):
            m.observe(i, 0, '1')
        self.assertEqual(len(m.snapshot()['events']), 500)
        self.assertEqual(len(m.snapshot()['states']), 2000)

    def test_http_read_only_and_peer_restriction(self):
        for peer, expected in [('127.0.0.1', 200), ('172.30.32.2', 403)]:
            server = make_server(Monitor(), '127.0.0.1', 0, peer)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                try:
                    response = urlopen(Request(base + '/api/snapshot', headers={'X-Forwarded-For': '172.30.32.2'}))
                    self.assertEqual(response.status, expected)
                    self.assertIn('session', json.load(response))
                except HTTPError as e:
                    self.assertEqual(e.code, expected)
                    e.close()
                if expected == 200:
                    page = urlopen(base + '/').read()
                    self.assertIn(b'data-i18n="main_title"', page)
                    self.assertIn(b'id="devices"', page)
                    for path, method, code in [('/../config.yaml', 'GET', 404), ('/api/snapshot', 'POST', 403)]:
                        with self.assertRaises(HTTPError) as raised:
                            urlopen(Request(base + path, method=method))
                        self.assertEqual(raised.exception.code, code)
                        raised.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
