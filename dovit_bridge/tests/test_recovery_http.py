import asyncio
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dovit_bridge.web_monitor import Monitor, make_server
from dovit_bridge.recovery_service import RecoveryManager


class RecoveryHttpTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'devices.json'
        self.monitor = Monitor()
        self.monitor.recovery = RecoveryManager(self.path)
        self.monitor.device_control = Mock()
        self.server = make_server(self.monitor, '127.0.0.1', 0, '127.0.0.1')
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, path, body=None, token=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            headers = {'Content-Type': 'application/json', 'X-Dovit-Token': token or self.monitor.session}
            client.request('POST' if body is not None else 'GET', path,
                           json.dumps(body) if body is not None else None, headers)
            response = client.getresponse()
            return response.status, response.read()
        finally:
            client.close()

    def test_token_and_normal_operations_are_blocked(self):
        self.assertEqual(self.request('/api/recovery/validate', {}, token='wrong')[0], 403)
        status, body = self.request('/api/controls/command', {'category': 'shutters', 'id': 20, 'action': 'OPEN'})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)['error'], 'recovery_only')
        self.monitor.device_control.submit.assert_not_called()
        self.assertEqual(self.request('/api/snapshot')[0], 503)
        self.assertEqual(self.request('/api/devices')[0], 503)

    def test_pasted_document_review_and_apply_with_no_auto_runtime(self):
        page_status, page = self.request('/')
        self.assertEqual(page_status, 200)
        self.assertIn(b'recovery.js', page)
        self.assertNotIn(b'src="app.js"', page)
        status, body = self.request('/api/recovery')
        state = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(state['token'], self.monitor.session)
        document = '{"lights":{"19":{"name":"Synthetic","statetype":0}}}'
        status, body = self.request('/api/recovery/validate', {'revision': state['current']['revision'], 'document': document})
        checked = json.loads(body)
        self.assertEqual(status, 200)
        self.assertFalse(self.path.exists())
        self.assertEqual(checked['summary']['counts']['lights'], 1)
        status, _ = self.request('/api/recovery/apply', dict(validation_id=checked['validation_id'], revision=checked['revision'], confirm=True))
        self.assertEqual(status, 200)
        self.assertEqual(self.path.read_text(), document)
        status, body = self.request('/api/recovery')
        self.assertTrue(json.loads(body)['restart_required'])
        self.assertFalse(self.monitor.connected)
        self.assertIsNone(self.monitor.light_control)
        self.assertIsNone(self.monitor.device_editor)
        self.monitor.device_control.submit.assert_not_called()

    def test_normal_mode_does_not_offer_restore(self):
        self.monitor.recovery = None
        self.assertEqual(self.request('/api/recovery')[0], 404)
        status, body = self.request('/api/recovery/apply', {})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)['error'], 'recovery_disabled')


class RecoveryStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_restricted_server_closes_on_cancellation(self):
        from dovit_bridge.main import run_recovery
        cfg = SimpleNamespace(mqtt_pass='', alarm_code='', devices_file=Path('synthetic-not-read.json'))
        server = Mock()
        with patch('dovit_bridge.main.start_monitor', return_value=server) as start, \
                patch('dovit_bridge.main.DovitBridge') as bridge:
            task = asyncio.create_task(run_recovery(cfg))
            await asyncio.sleep(0)
            monitor = start.call_args.args[0]
            self.assertIsNotNone(monitor.recovery)
            self.assertIsNone(monitor.light_control)
            self.assertIsNone(monitor.device_control)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            bridge.assert_not_called()
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
