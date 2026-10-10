import unittest
from unittest.mock import patch

from dovit_bridge.config import Config, load_config
from dovit_bridge.options import load_addon_options


class MqttConfigTests(unittest.TestCase):
    def test_defaults_and_upgrades_remain_manual(self):
        self.assertEqual(Config().mqtt_mode, 'manual')
        for addon in (False, True):
            for opts in ({}, {'mqtt_host': 'custom.local', 'mqtt_pass': 'old-secret'}):
                with patch('dovit_bridge.config.os.path.exists', return_value=addon), \
                        patch('dovit_bridge.config.load_addon_options', return_value=opts), \
                        patch('dovit_bridge.mqtt_service.http.client.HTTPConnection') as http:
                    cfg = load_config()
                self.assertEqual(cfg.mqtt_mode, 'manual')
                self.assertFalse(cfg.mqtt_tls)
                self.assertEqual(cfg.mqtt_protocol, '3.1.1')
                self.assertEqual(cfg.mqtt_pass, opts.get('mqtt_pass', ''))
                http.assert_not_called()

    def test_shared_options_loaded_without_resolving(self):
        opts = dict(mqtt_mode='supervisor', mqtt_tls=True, mqtt_protocol='5.0')
        for addon in (False, True):
            with patch('dovit_bridge.config.os.path.exists', return_value=addon), \
                    patch('dovit_bridge.config.load_addon_options', return_value=opts), \
                    patch('dovit_bridge.mqtt_service.http.client.HTTPConnection') as http:
                cfg = load_config()
            for name, value in opts.items():
                self.assertEqual(getattr(cfg, name), '5' if name == 'mqtt_protocol' else value)
            http.assert_not_called()

    def test_invalid_options_fixed_errors(self):
        for opts, key in (({'mqtt_mode': 'password-secret'}, 'mqtt_invalid_mode'),
                           ({'mqtt_tls': 'false'}, 'mqtt_invalid_tls'),
                           ({'mqtt_protocol': []}, 'mqtt_invalid_protocol')):
            with patch('dovit_bridge.config.load_addon_options', return_value=opts):
                with self.assertRaisesRegex(ValueError, '^' + key + '$'):
                    load_config()

    def test_repr_hides_credentials_and_alarm_code(self):
        text = repr(Config(mqtt_user='username-secret', mqtt_pass='password-secret', alarm_code='code-secret'))
        for secret in ('username-secret', 'password-secret', 'code-secret'):
            self.assertNotIn(secret, text)

    def test_options_parse_errors_do_not_log_exception_or_path(self):
        with patch('dovit_bridge.options.os.path.exists', return_value=True), \
                patch('builtins.open', side_effect=OSError('password-secret')), \
                patch('builtins.print') as output:
            self.assertEqual(load_addon_options('username-secret'), {})
        output.assert_called_once_with('WARNING: Could not read add-on options')

    def test_options_non_object_is_safe(self):
        from unittest.mock import mock_open
        with patch('dovit_bridge.options.os.path.exists', return_value=True), \
                patch('builtins.open', mock_open(read_data='["password-secret"]')), \
                patch('builtins.print'):
            self.assertEqual(load_addon_options(), {})


if __name__ == '__main__':
    unittest.main()
