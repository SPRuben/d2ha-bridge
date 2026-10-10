import logging
import unittest
from unittest.mock import Mock, patch

from dovit_bridge.logging_setup import SafeFormatter
from dovit_bridge.mqtt_client import MqttWrapper


class LoggingTests(unittest.TestCase):
    def test_utc_timestamp_level_module_and_single_line(self):
        record = logging.LogRecord("bridge", logging.WARNING, "", 0, "bad\nvalue\rtest", (), None)
        record.created = 0
        record.msecs = 123
        text = SafeFormatter().format(record)
        self.assertEqual(text, "1970-01-01T00:00:00.123Z WARNING [bridge] bad\\nvalue\\rtest")

    def test_secrets_redacted_after_interpolation(self):
        record = logging.LogRecord("bridge", logging.ERROR, "", 0, "password=%s code=%s", ("secret", "1234"), None)
        text = SafeFormatter(("secret", "1234", "")).format(record)
        self.assertNotIn("secret", text)
        self.assertNotIn("1234", text)
        self.assertEqual(text.count("[REDACTED]"), 2)

    def wrapper(self):
        with patch("dovit_bridge.mqtt_client.mqtt.Client"):
            wrapper = MqttWrapper("broker.invalid", 1883, "test", "secret")
        wrapper.on_connect = Mock()
        wrapper.on_message = Mock()
        return wrapper

    def test_publish_failure_logged_without_payload(self):
        wrapper = self.wrapper()
        wrapper.client.publish.return_value.rc = 4
        with self.assertLogs("dovit_bridge.mqtt_client", level="ERROR") as logs:
            wrapper.publish("dovit/test", "secret")
        self.assertNotIn("secret", str(logs.output))
        self.assertIn("rc=4", str(logs.output))

    def test_rejected_connection_does_not_run_subscriptions(self):
        wrapper = self.wrapper()
        with self.assertLogs("dovit_bridge.mqtt_client", level="ERROR"):
            wrapper._on_connect(None, None, None, Mock(is_failure=True))
        wrapper.on_connect.assert_not_called()

    def test_callback_exception_is_logged_without_secret(self):
        wrapper = self.wrapper()
        wrapper.on_message.side_effect = ValueError("secret")
        with self.assertLogs("dovit_bridge.mqtt_client", level="ERROR") as logs:
            wrapper._on_message(None, None, Mock(topic="dovit/test"))
        self.assertIn("ValueError", str(logs.output))
        self.assertNotIn("secret", str(logs.output))

    def test_disconnect_reported(self):
        with self.assertLogs("dovit_bridge.mqtt_client", level="WARNING") as logs:
            self.wrapper()._on_disconnect(None, None, None, "Lost connection")
        self.assertIn("reason_code=None", str(logs.output))
        self.assertNotIn("Lost connection", str(logs.output))
