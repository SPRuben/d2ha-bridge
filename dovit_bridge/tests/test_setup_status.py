import json
import unittest
import threading
from types import SimpleNamespace
from urllib.request import urlopen
from dovit_bridge.web_monitor import Monitor, make_server
from dovit_bridge.bridge import DovitBridge


class SetupStatusTests(unittest.TestCase):
    def test_absent_provider_is_unknown(self):
        self.assertIsNone(Monitor().snapshot()['setup'])

    def test_runtime_facts_exclude_credentials_and_ha_claims(self):
        bridge = DovitBridge.__new__(DovitBridge)
        bridge.mqtt = SimpleNamespace(connected=True, password='private-secret')
        bridge.cfg = SimpleNamespace(enable_discovery=False, publish_discovery=True,
                                     mqtt_pass='private-secret')
        monitor = Monitor()
        monitor.runtime_status = bridge.setup_status
        status = monitor.snapshot()['setup']
        self.assertTrue(status['mqtt_connected'])
        self.assertTrue(status['discovery_publishing'])
        self.assertFalse(status['automatic_discovery'])
        self.assertEqual(status['mqtt_mode'], 'manual')
        self.assertEqual(status['mqtt_state'], 'unknown')
        self.assertNotIn('private-secret', json.dumps(status))
        bridge.mqtt.connected = False
        self.assertFalse(monitor.snapshot()['setup']['mqtt_connected'])

    def test_automatic_discovery_includes_publication(self):
        bridge = DovitBridge.__new__(DovitBridge)
        bridge.mqtt = SimpleNamespace(connected=False)
        bridge.cfg = SimpleNamespace(enable_discovery=True, publish_discovery=False)
        status = bridge.setup_status()
        self.assertFalse(status['mqtt_connected'])
        self.assertTrue(status['discovery_publishing'])
        self.assertTrue(status['automatic_discovery'])

    def test_setup_assets_and_snapshot_are_served_with_existing_csp(self):
        monitor = Monitor()
        monitor.runtime_status = lambda: dict(mqtt_connected=False)
        server = make_server(monitor, host='127.0.0.1', port=0, allowed_peer='127.0.0.1')
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        try:
            for asset in ('setup.js', 'change-review.js'):
                with urlopen(base + '/' + asset, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])
                    self.assertNotIn('unsafe-inline', response.headers['Content-Security-Policy'])
            with urlopen(base + '/api/snapshot', timeout=2) as response:
                self.assertEqual(json.load(response)['setup'], dict(mqtt_connected=False))
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
