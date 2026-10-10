"""Real local HTTP framing for the Supervisor resolver; no Supervisor access."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from dovit_bridge.config import Config
from dovit_bridge.mqtt_service import MqttServiceError, resolve_mqtt_config


class MqttServiceHttpTests(unittest.TestCase):
    def resolve(self, status=200, body=None, protocol='HTTP/1.0', chunked=False, extra_length=0):
        if body is None:
            body = json.dumps(dict(result='ok', data=dict(
                host='synthetic-broker.invalid', port='1883', ssl=False,
                username='synthetic-user', password='synthetic-secret',
                protocol='3.1.1'))).encode()
        observed = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = protocol

            def do_GET(self):
                observed.append((self.path, self.headers.get('Authorization')))
                self.send_response(status)
                if chunked:
                    self.send_header('Transfer-Encoding', 'chunked')
                else:
                    self.send_header('Content-Length', str(len(body) + extra_length))
                self.end_headers()
                if chunked:
                    for start in range(0, len(body), 19):
                        chunk = body[start:start + 19]
                        self.wfile.write(f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n')
                    self.wfile.write(b'0\r\n\r\n')
                else:
                    self.wfile.write(body)
                self.wfile.flush()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection

        def local_connection(host, timeout):
            self.assertEqual(host, 'supervisor')
            return connection('127.0.0.1', server.server_port, timeout=timeout)

        try:
            with patch('dovit_bridge.mqtt_service.http.client.HTTPConnection', side_effect=local_connection), \
                    patch.dict('os.environ', {'SUPERVISOR_TOKEN': 'synthetic-token'}):
                result = resolve_mqtt_config(replace(Config(), mqtt_mode='supervisor'))
            self.assertEqual(observed, [('/services/mqtt', 'Bearer synthetic-token')])
            return result
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

    def test_real_http_connection_close_resolves_service(self):
        result = self.resolve()
        self.assertEqual(result.mqtt_host, 'synthetic-broker.invalid')
        self.assertEqual(result.mqtt_pass, 'synthetic-secret')
        self.assertEqual(result.mqtt_mode, 'supervisor')

    def test_real_http_keepalive_resolves_service(self):
        self.assertEqual(self.resolve(protocol='HTTP/1.1').mqtt_port, 1883)

    def test_real_http_chunked_response_resolves_service(self):
        self.assertEqual(self.resolve(protocol='HTTP/1.1', chunked=True).mqtt_protocol, '3.1.1')

    def test_real_http_truncated_body_is_rejected_even_when_json_is_valid(self):
        with self.assertRaisesRegex(MqttServiceError, 'mqtt_service_invalid_response'):
            self.resolve(extra_length=10)

    def test_real_http_errors_never_fallback_or_expose_remote_body(self):
        for status, body, expected in (
                (401, b'synthetic-secret', 'mqtt_supervisor_auth_rejected'),
                (302, b'synthetic-secret', 'mqtt_service_unavailable'),
                (200, b'{synthetic-secret', 'mqtt_service_invalid_response')):
            with self.subTest(status=status), self.assertRaises(MqttServiceError) as error:
                self.resolve(status=status, body=body)
            self.assertEqual(str(error.exception), expected)


if __name__ == '__main__':
    unittest.main()
