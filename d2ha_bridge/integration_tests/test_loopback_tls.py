"""Opt-in real MQTT/TLS acceptance, using disposable local certificates only."""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--run-loopback' in sys.argv:
    sys.argv.remove('--run-loopback')
    os.environ['DOVIT_RUN_LOOPBACK_MQTT'] = '1'


@unittest.skipUnless(os.environ.get('DOVIT_RUN_LOOPBACK_MQTT') == '1',
                     'Opt in with --run-loopback')
class LoopbackTlsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from amqtt.broker import Broker
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from dovit_bridge.mqtt_client import MqttWrapper
        self.Wrapper = MqttWrapper
        self.directory = tempfile.TemporaryDirectory()
        self.wrapper = None
        self.broker = None
        self.addAsyncCleanup(self.cleanup)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5))
                .not_valid_after(now + timedelta(days=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(key, hashes.SHA256()))
        self.cert_path = Path(self.directory.name) / 'local-cert.pem'
        key_path = Path(self.directory.name) / 'local-key.pem'
        self.cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            self.port = reservation.getsockname()[1]
        self.broker = Broker({
            'listeners': {'default': {'type': 'tcp', 'bind': f'127.0.0.1:{self.port}',
                                     'ssl': True, 'certfile': str(self.cert_path), 'keyfile': str(key_path)}},
            'plugins': {'amqtt.plugins.authentication.AnonymousAuthPlugin': {'allow_anonymous': True}},
        })
        await asyncio.wait_for(self.broker.start(), 5)

    async def cleanup(self):
        try:
            if self.wrapper is not None:
                try:
                    await asyncio.wait_for(asyncio.to_thread(self.wrapper.stop), 5)
                finally:
                    self.wrapper.client._reset_sockets()
            if self.broker is not None:
                await asyncio.wait_for(self.broker.shutdown(), 5)
        finally:
            self.directory.cleanup()

    def trusted_wrapper(self, host='localhost'):
        context = ssl.create_default_context(cafile=str(self.cert_path))
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        with patch('dovit_bridge.mqtt_client.ssl.create_default_context', return_value=context):
            self.wrapper = self.Wrapper(host, self.port, 'synthetic-user', 'synthetic-secret', tls=True)
        return self.wrapper

    async def test_trusted_certificate_and_hostname_connect_with_real_puback(self):
        wrapper = self.trusted_wrapper()
        connected = asyncio.Event()
        loop = asyncio.get_running_loop()
        wrapper.on_connect = lambda *args: loop.call_soon_threadsafe(connected.set)
        wrapper.connect_and_loop()
        await asyncio.wait_for(connected.wait(), 5)
        self.assertTrue(wrapper.connected)
        publication = wrapper.publish('integration/tls_probe', 'synthetic', qos=1, retain=False)
        await asyncio.wait_for(asyncio.to_thread(publication.wait_for_publish, 2), 3)
        self.assertTrue(publication.is_published())

    async def test_untrusted_certificate_is_rejected_by_production_context(self):
        self.wrapper = self.Wrapper('localhost', self.port, 'synthetic-user', 'synthetic-secret', tls=True)
        await self.assert_certificate_rejected(self.wrapper, 'localhost')
        self.assertFalse(self.wrapper.connected)

    async def test_trusted_certificate_with_wrong_hostname_is_rejected(self):
        wrapper = self.trusted_wrapper('127.0.0.1')
        await self.assert_certificate_rejected(wrapper, '127.0.0.1')
        self.assertFalse(wrapper.connected)

    async def assert_certificate_rejected(self, wrapper, host):
        # Paho hands the TLS socket to Client only after its handshake succeeds.
        # The test must release failed sockets retained in assertion tracebacks.
        context = wrapper.client._ssl_context
        wrap_socket = context.wrap_socket
        opened = []

        def capture_socket(*args, **kwargs):
            secure_socket = wrap_socket(*args, **kwargs)
            opened.append(secure_socket)
            return secure_socket

        try:
            with patch.object(context, 'wrap_socket', side_effect=capture_socket):
                with self.assertRaises(ssl.SSLCertVerificationError):
                    await asyncio.wait_for(asyncio.to_thread(wrapper.client.connect, host, self.port, 10), 5)
        finally:
            for secure_socket in opened:
                secure_socket.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    unittest.main(verbosity=2)
