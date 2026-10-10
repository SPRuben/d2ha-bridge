"""Regressions preserving complete discovery payloads and existing identities."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from dovit_bridge import mqtt_discovery
from dovit_bridge.web_monitor import BRANDING_IMAGE_ROUTES, Monitor, make_server


class IdentityCompatibilityTests(unittest.TestCase):
    def test_complete_discovery_payloads_preserve_all_non_branding_fields(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/phase1_discovery.json').read_text(encoding='utf-8'))
        for case in fixture['cases']:
            with self.subTest(function=case['function'], kwargs=case['kwargs']):
                before = deepcopy(case['payload'])
                after = getattr(mqtt_discovery, case['function'])(*case['args'], **case['kwargs'])
                self.assertEqual(after['device']['name'], 'D2HA Bridge')
                self.assertEqual(after['device']['manufacturer'], 'Independent community project')
                for key in fixture['display_metadata_allowed']:
                    before['device'].pop(key)
                    after['device'].pop(key)
                self.assertEqual(after, before)
                topic = mqtt_discovery.discovery_topic('homeassistant', 'example', after['unique_id'])
                self.assertEqual(topic, f"homeassistant/example/{before['unique_id']}/config")

    def test_arbitrary_existing_device_identifier_is_retained(self):
        for node_id in ('dovit_bridge', 'existing_custom_node'):
            self.assertEqual(mqtt_discovery.discovery_device(node_id)['identifiers'], [node_id])

    def test_branding_assets_work_in_normal_and_recovery_mode(self):
        for recovery in (False, True):
            with self.subTest(recovery=recovery):
                monitor = Monitor()
                if recovery:
                    monitor.recovery = object()
                server = make_server(monitor, '127.0.0.1', 0, '127.0.0.1')
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f'http://127.0.0.1:{server.server_port}'
                try:
                    with urlopen(base + '/', timeout=2) as response:
                        html = response.read().decode()
                        self.assertIn('D2HA Bridge', html)
                        self.assertIn('href="brand.css"', html)
                        self.assertIn('href="branding/favicon-32.png"', html)
                        self.assertNotIn('https://', html)
                    with urlopen(base + '/brand.css', timeout=2) as response:
                        self.assertEqual(response.headers.get_content_type(), 'text/css')
                    for route in BRANDING_IMAGE_ROUTES:
                        with urlopen(base + route, timeout=2) as response:
                            self.assertEqual(response.headers['Content-Type'], 'image/png')
                            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                            self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])
                            actual = response.read()
                            expected = (Path(mqtt_discovery.__file__).parent / 'web' / route[1:]).read_bytes()
                            self.assertEqual(actual, expected)
                    for route in ('/branding/../../config.yaml', '/branding/unknown.png'):
                        with self.assertRaises(HTTPError) as raised:
                            urlopen(base + route, timeout=2)
                        self.assertEqual(raised.exception.code, 404)
                        raised.exception.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())

    def test_branding_does_not_bypass_ingress_peer_guard(self):
        server = make_server(Monitor(), '127.0.0.1', 0, '192.0.2.2')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for route in ('/', '/brand.css', *BRANDING_IMAGE_ROUTES):
                with self.assertRaises(HTTPError) as raised:
                    urlopen(f'http://127.0.0.1:{server.server_port}' + route, timeout=2)
                self.assertEqual(raised.exception.code, 403)
                raised.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
