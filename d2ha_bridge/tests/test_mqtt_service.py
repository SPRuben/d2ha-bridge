import json
import traceback
import unittest
from dataclasses import replace
from unittest.mock import patch

from dovit_bridge.config import Config, load_config
from dovit_bridge.options import mqtt_config_options
from dovit_bridge.mqtt_service import (
    ERROR_KEYS, SERVICE_RESPONSE_LIMIT, SERVICE_TIMEOUT,
    MqttServiceError, resolve_mqtt_config,
)


class MqttServiceTests(unittest.TestCase):
    def setUp(self):
        self.cfg = replace(Config(), mqtt_mode='supervisor')
        self.data = dict(host='broker.local', port='8883', ssl=True,
                         username='service-user-secret', password='password-secret',
                         protocol='3.1.1')
        self.http = patch('dovit_bridge.mqtt_service.http.client.HTTPConnection')
        self.factory = self.http.start()
        self.addCleanup(self.http.stop)
        self.env = patch.dict('os.environ', {'SUPERVISOR_TOKEN': 'token-secret'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.connection = self.factory.return_value
        self.response = self.connection.getresponse.return_value.__enter__.return_value
        self.response.status = 200
        self.response.isclosed.return_value = False
        self.response.length = None
        self.body(dict(result='ok', data=self.data))

    def body(self, value):
        self.response.read1.side_effect = [json.dumps(value).encode(), b'']

    def error(self, key):
        with self.assertRaises(MqttServiceError) as caught:
            resolve_mqtt_config(self.cfg)
        self.assertEqual(caught.exception.key, key)
        self.assertEqual(str(caught.exception), key)
        self.assertIn(key, ERROR_KEYS)
        rendered = ''.join(traceback.format_exception(caught.exception))
        for secret in ('token-secret', 'password-secret', 'service-user-secret'):
            self.assertNotIn(secret, rendered)
        return caught.exception

    def test_supervisor_official_request_and_in_memory_copy(self):
        resolved = resolve_mqtt_config(self.cfg)
        self.factory.assert_called_once_with('supervisor', timeout=SERVICE_TIMEOUT)
        self.connection.request.assert_called_once_with('GET', '/services/mqtt', headers={
            'Authorization': 'Bearer token-secret', 'Accept': 'application/json'})
        self.connection.close.assert_called_once()
        self.assertIsNot(resolved, self.cfg)
        self.assertEqual(resolved.mqtt_host, 'broker.local')
        self.assertEqual(resolved.mqtt_port, 8883)
        self.assertTrue(resolved.mqtt_tls)
        self.assertEqual(resolved.mqtt_protocol, '3.1.1')
        self.assertEqual(resolved.mqtt_user, self.data['username'])
        self.assertEqual(resolved.mqtt_pass, self.data['password'])
        self.assertEqual(self.cfg.mqtt_host, Config().mqtt_host)
        self.assertEqual(resolved.devices_file, self.cfg.devices_file)
        self.assertEqual(resolved.mqtt_mode, 'supervisor')
        for secret in (self.data['username'], self.data['password']):
            self.assertNotIn(secret, repr(resolved))

    def test_manual_never_contacts_supervisor(self):
        cfg = Config(mqtt_host='manual.local', mqtt_user='', mqtt_pass='')
        result = resolve_mqtt_config(cfg)
        self.assertEqual(result, cfg)
        self.assertIsNot(result, cfg)
        self.factory.assert_not_called()

    def test_missing_invalid_token_and_mode_do_not_connect(self):
        for token, key in (('', 'mqtt_supervisor_token_missing'),
                           ('token-secret\r\n', 'mqtt_supervisor_token_invalid')):
            with patch.dict('os.environ', {'SUPERVISOR_TOKEN': token}, clear=True):
                self.error(key)
        self.cfg = replace(self.cfg, mqtt_mode='invalid-secret')
        self.error('mqtt_invalid_config')
        self.factory.assert_not_called()

    def test_http_failures_do_not_read_body_or_follow_redirect(self):
        for status in (301, 302, 401, 403, 404, 503):
            with self.subTest(status=status):
                self.response.status = status
                key = 'mqtt_supervisor_auth_rejected' if status in (401, 403) else 'mqtt_service_unavailable'
                self.error(key)
        self.response.read1.assert_not_called()

    def test_timeout_and_transport_failure_are_safe(self):
        for exc, key in ((TimeoutError('password-secret'), 'mqtt_service_timeout'),
                         (OSError('token-secret'), 'mqtt_service_unavailable')):
            self.connection.request.side_effect = exc
            self.error(key)
        self.assertEqual(self.connection.close.call_count, 2)

    def test_connection_construction_failure_is_safe(self):
        self.factory.side_effect = OSError('token-secret')
        self.error('mqtt_service_unavailable')

    def test_deadline_enforced_without_retry(self):
        with patch('dovit_bridge.mqtt_service.time.monotonic', side_effect=[0, 1, 6]):
            self.error('mqtt_service_timeout')
        self.connection.request.assert_called_once()
        self.response.read1.assert_not_called()

    def test_oversize_and_malformed_json(self):
        self.response.read1.side_effect = [b'x' * 4096] * 4 + [b'x']
        self.error('mqtt_service_response_too_large')
        self.assertEqual(self.response.read1.call_args.args[0], 1)
        self.assertEqual(sum(c.args[0] for c in self.response.read1.call_args_list),
                         SERVICE_RESPONSE_LIMIT + 1)
        self.response.read1.side_effect = [b'{password-secret', b'']
        self.error('mqtt_service_invalid_response')

    def test_invalid_envelopes_and_unavailable_service(self):
        for value, key in (([], 'mqtt_service_invalid_response'),
                           ({'result': 'ok', 'data': []}, 'mqtt_service_invalid_response'),
                           ({'result': 'error', 'message': 'password-secret'}, 'mqtt_service_unavailable')):
            self.body(value)
            self.error(key)

    def test_service_schema_strict_and_no_manual_fallback(self):
        invalid = {'host': ['', None, 'broker\nsecret'],
                   'port': ['', 'abc', '0', '65536', True, 1.5, '1' * 5000],
                   'ssl': ['true', 1, None], 'username': [None, {}],
                   'password': [None, []], 'protocol': ['bad-secret', None, 4]}
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=type(value)):
                    self.body(dict(result='ok', data=dict(self.data, **{field: value})))
                    self.error('mqtt_service_invalid_response')
            data = dict(self.data)
            del data[field]
            self.body(dict(result='ok', data=data))
            self.error('mqtt_service_invalid_response')

    def test_all_protocols_and_integer_port(self):
        for protocol in ('3.1', '3.1.1', '5', '5.0'):
            self.body(dict(result='ok', data=dict(self.data, protocol=protocol, port=1883, ssl=False)))
            cfg = resolve_mqtt_config(self.cfg)
            self.assertEqual(cfg.mqtt_protocol, '5' if protocol == '5.0' else protocol)
            self.assertEqual(cfg.mqtt_port, 1883)
            self.assertFalse(cfg.mqtt_tls)

    def test_manual_protocol_alias_resolves_without_mutation_or_network(self):
        cfg = Config(mqtt_protocol='5.0')
        resolved = resolve_mqtt_config(cfg)
        self.assertEqual(resolved.mqtt_protocol, '5')
        self.assertEqual(cfg.mqtt_protocol, '5.0')
        self.factory.assert_not_called()

    def test_shared_options_protocols_are_canonical_without_mutation(self):
        for protocol in ('3.1', '3.1.1', '5', '5.0'):
            opts = {'mqtt_protocol': protocol}
            fields = mqtt_config_options(opts)
            self.assertEqual(fields['mqtt_protocol'], '5' if protocol == '5.0' else protocol)
            self.assertEqual(fields['mqtt_mode'], 'manual')
            self.assertEqual(opts, {'mqtt_protocol': protocol})

    def test_load_config_normalizes_alias_in_both_environments_without_network(self):
        for addon in (False, True):
            opts = {'mqtt_protocol': '5.0'}
            with patch('dovit_bridge.config.os.path.exists', return_value=addon), \
                    patch('dovit_bridge.config.load_addon_options', return_value=opts):
                cfg = load_config()
            self.assertEqual(cfg.mqtt_protocol, '5')
            self.assertEqual(cfg.mqtt_mode, 'manual')
            self.assertEqual(opts['mqtt_protocol'], '5.0')
        self.factory.assert_not_called()

    def test_invalid_manual_config_never_contacts_supervisor(self):
        for fields in ({'mqtt_tls': 'false'}, {'mqtt_protocol': 'secret'},
                       {'mqtt_port': True}, {'mqtt_host': ''}):
            self.cfg = replace(Config(), **fields)
            self.error('mqtt_invalid_config')
        self.factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
