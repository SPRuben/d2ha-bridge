from datetime import datetime
import ssl
import threading
import unittest
from unittest.mock import Mock, patch

from dovit_bridge.mqtt_client import MqttWrapper, mqtt


class MqttDiagnosticsTests(unittest.TestCase):
    def wrapper(self, **kwargs):
        with patch('dovit_bridge.mqtt_client.mqtt.Client') as factory:
            wrapper = MqttWrapper('host-secret', 1883, 'username-secret', 'password-secret', **kwargs)
        wrapper.client.loop_start.return_value = mqtt.MQTT_ERR_SUCCESS
        wrapper.client.publish.return_value.rc = mqtt.MQTT_ERR_SUCCESS
        wrapper.client.publish.return_value.is_published.return_value = True
        return wrapper, factory

    def test_protocol_mapping_and_verified_tls(self):
        for value, expected in (('3.1', mqtt.MQTTv31), ('3.1.1', mqtt.MQTTv311),
                                ('5', mqtt.MQTTv5), ('5.0', mqtt.MQTTv5)):
            wrapper, factory = self.wrapper(protocol=value, tls=True)
            factory.assert_called_once_with(mqtt.CallbackAPIVersion.VERSION2, protocol=expected)
            context = wrapper.client.tls_set_context.call_args.args[0]
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            wrapper.client.tls_insecure_set.assert_not_called()
        wrapper, _ = self.wrapper()
        wrapper.client.tls_set_context.assert_not_called()

    def test_invalid_tls_protocol_rejected_before_client(self):
        for args in ({'tls': 'false'}, {'protocol': 'password-secret'}, {'protocol': []}):
            with patch('dovit_bridge.mqtt_client.mqtt.Client') as factory:
                with self.assertRaises(ValueError) as caught:
                    MqttWrapper('host', 1883, 'user', 'pass', **args)
                self.assertNotIn('password-secret', str(caught.exception))
                factory.assert_not_called()

    def test_state_lifecycle_and_safe_snapshot(self):
        wrapper, _ = self.wrapper()
        self.assertEqual(wrapper.diagnostics()['state'], 'disconnected')
        with self.assertLogs('dovit_bridge.mqtt_client', level='INFO') as logs:
            wrapper.connect_and_loop()
            self.assertEqual(wrapper.diagnostics()['state'], 'connecting')
            wrapper._on_connect_fail(None, None)
            self.assertEqual(wrapper.diagnostics()['state'], 'unreachable')
            wrapper._on_connect(None, None, {}, 0)
            self.assertEqual(wrapper.diagnostics()['state'], 'connected')
            wrapper._on_disconnect(None, None, {}, 128)
            self.assertEqual(wrapper.diagnostics()['state'], 'disconnected')
            wrapper.stop()
        snapshot = wrapper.diagnostics()
        self.assertEqual(set(snapshot), {'state', 'reason_code', 'last_change'})
        self.assertEqual(snapshot['state'], 'stopped')
        self.assertIsNotNone(datetime.fromisoformat(snapshot['last_change']).tzinfo)
        snapshot['state'] = 'corrupted'
        self.assertEqual(wrapper.diagnostics()['state'], 'stopped')
        for secret in ('host-secret', 'username-secret', 'password-secret'):
            self.assertNotIn(secret, str(logs.output) + str(snapshot))

    def test_numeric_rejections_and_no_arbitrary_reason_text(self):
        wrapper, _ = self.wrapper()
        for number, state in ((4, 'auth_rejected'), (5, 'auth_rejected'),
                              (134, 'auth_rejected'), (135, 'auth_rejected'),
                              (136, 'rejected')):
            reason = Mock(value=number, is_failure=True)
            reason.__str__ = Mock(side_effect=AssertionError('reason stringified'))
            with self.assertLogs('dovit_bridge.mqtt_client', level='ERROR'):
                wrapper._on_connect(None, None, {}, reason)
            self.assertEqual(wrapper.diagnostics()['state'], state)
            self.assertEqual(wrapper.diagnostics()['reason_code'], number)
        with self.assertLogs('dovit_bridge.mqtt_client', level='WARNING') as logs:
            wrapper._on_disconnect(None, None, {}, 'password-secret')
        self.assertEqual(wrapper.diagnostics()['reason_code'], 136)
        self.assertEqual(wrapper.diagnostics()['state'], 'rejected')
        self.assertNotIn('password-secret', str(logs.output))
        wrapper.client.publish.assert_not_called()

    def test_auth_rejection_survives_following_disconnect_until_new_evidence(self):
        wrapper, _ = self.wrapper()
        wrapper._on_connect(None, None, {}, 135)
        wrapper._on_disconnect(None, None, {}, 128)
        self.assertEqual(wrapper.diagnostics()['state'], 'auth_rejected')
        wrapper._on_connect(None, None, {}, 0)
        self.assertEqual(wrapper.diagnostics()['state'], 'connected')

    def test_late_callbacks_cannot_override_stopped_and_restart_connects(self):
        wrapper, _ = self.wrapper()
        wrapper.stop()
        initial = wrapper.diagnostics()
        wrapper._on_connect(None, None, {}, 0)
        wrapper._on_connect_fail(None, None)
        wrapper._on_disconnect(None, None, {}, 0)
        self.assertEqual(initial, wrapper.diagnostics())
        wrapper.connect_and_loop()
        self.assertEqual(wrapper.diagnostics()['state'], 'connecting')

    def test_start_exception_redacted_and_unreachable(self):
        wrapper, _ = self.wrapper()
        wrapper.client.connect_async.side_effect = OSError('password-secret')
        with self.assertRaisesRegex(RuntimeError, '^mqtt_connection_start_failed$'):
            wrapper.connect_and_loop()
        self.assertEqual(wrapper.diagnostics()['state'], 'unreachable')

    def test_snapshot_takes_lock_and_repeated_state_preserves_timestamp(self):
        wrapper, _ = self.wrapper()
        wrapper._on_connect_fail(None, None)
        initial = wrapper.diagnostics()
        wrapper._on_connect_fail(None, None)
        self.assertEqual(initial, wrapper.diagnostics())
        started = threading.Event()
        finished = threading.Event()
        def read():
            started.set()
            wrapper.diagnostics()
            finished.set()
        with wrapper._status_lock:
            thread = threading.Thread(target=read)
            thread.start()
            self.assertTrue(started.wait(1))
            self.assertFalse(finished.wait(0.02))
        thread.join(1)
        self.assertTrue(finished.is_set())


if __name__ == '__main__':
    unittest.main()
