from contextlib import contextmanager
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from dovit_bridge.web_monitor import Monitor, make_server


# Complete 1x1 grayscale baseline JPEG; no image library/test dependency needed.
TUTORIAL_JPEG = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    + b'\xff\xdb\x00\x43\x00' + b'\x01' * 64
    + b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
    + b'\xff\xc4\x00\x14\x00\x01' + b'\x00' * 16
    + b'\xff\xc4\x00\x14\x10\x01' + b'\x00' * 16
    + b'\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x3f\xff\xd9'
)


class ManualTests(unittest.TestCase):
    @contextmanager
    def tutorial_server(self, peer='127.0.0.1'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / 'manuals' / 'images'
            images.mkdir(parents=True)
            names = [f'{stem}-{language}.jpg'
                     for stem in ('devices-overview', 'setup-dovit', 'setup-mqtt', 'setup-publication',
                                  'device-assignment', 'diagnosis', 'json-review', 'recovery')
                     for language in ('de', 'fr')]
            for name in names:
                (images / name).write_bytes(TUTORIAL_JPEG)
            # Use disposable fixtures, never replace the real captured tutorial assets.
            with patch('dovit_bridge.web_monitor.__file__', str(root / 'web_monitor.py')):
                server = make_server(Monitor(), '127.0.0.1', 0, peer)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield f'http://127.0.0.1:{server.server_port}', images, names
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())

    def assert_http_error(self, url, status):
        with self.assertRaises(HTTPError) as raised:
            urlopen(url, timeout=2)
        self.assertEqual(raised.exception.code, status)
        raised.exception.close()

    def test_bundled_manuals_match_sources(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('USER_DE.md', 'USER_FR.md', 'DEVELOPER.md'):
            self.assertEqual((root.parent / 'docs' / name).read_bytes(),
                             (root / 'dovit_bridge' / 'manuals' / name).read_bytes(), name)

    def test_real_bundled_tutorial_images_match_sources(self):
        root = Path(__file__).resolve().parents[1]
        source = root.parent / 'docs' / 'images'
        bundled = root / 'dovit_bridge' / 'manuals' / 'images'
        names = {f'{stem}-{language}.jpg'
                 for stem in ('devices-overview', 'setup-dovit', 'setup-mqtt', 'setup-publication',
                              'device-assignment', 'diagnosis', 'json-review', 'recovery')
                 for language in ('de', 'fr')}
        self.assertEqual({path.name for path in source.glob('*.jpg')}, names)
        self.assertEqual({path.name for path in bundled.glob('*.jpg')}, names)
        for name in sorted(names):
            with self.subTest(name=name):
                content = (source / name).read_bytes()
                self.assertTrue(content.startswith(b'\xff\xd8') and content.endswith(b'\xff\xd9'))
                self.assertEqual((bundled / name).read_bytes(), content, name)

    def test_explicit_routes_and_source_ip(self):
        for peer in ('127.0.0.1', '172.30.32.2'):
            server = make_server(Monitor(), '127.0.0.1', 0, peer)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                for name in ('USER_DE.md', 'USER_FR.md', 'DEVELOPER.md'):
                    if peer == '127.0.0.1':
                        with urlopen(base + '/manuals/' + name) as response:
                            self.assertEqual(response.headers.get_content_type(), 'text/plain')
                            self.assertTrue(response.read().startswith(b'# '))
                    else:
                        with self.assertRaises(HTTPError) as raised:
                            urlopen(base + '/manuals/' + name)
                        self.assertEqual(raised.exception.code, 403)
                        raised.exception.close()
                if peer == '127.0.0.1':
                    for route in ('/help.js', '/help.css'):
                        with urlopen(base + route) as response:
                            self.assertEqual(response.status, 200)
                    for route in ('/manuals/../../config.yaml', '/manuals/README.md'):
                        with self.assertRaises(HTTPError) as raised:
                            urlopen(base + route)
                        self.assertEqual(raised.exception.code, 404)
                        raised.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_all_tutorial_images_serve_exact_bytes_with_binary_security_headers(self):
        with self.tutorial_server() as (base, _, names):
            self.assertEqual(len(names), 16)
            for name in names:
                with self.subTest(name=name), urlopen(base + '/manuals/images/' + name, timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers['Content-Type'], 'image/jpeg')
                    self.assertEqual(response.headers['Content-Length'], str(len(TUTORIAL_JPEG)))
                    self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    policy = response.headers['Content-Security-Policy']
                    self.assertIn("default-src 'self'", policy)
                    self.assertNotIn('*', policy)
                    self.assertNotIn('https:', policy)
                    self.assertNotIn('http:', policy)
                    self.assertEqual(response.read(), TUTORIAL_JPEG)

    def test_tutorial_images_require_actual_ingress_peer_before_file_access(self):
        with self.tutorial_server(peer='172.30.32.2') as (base, _, names):
            with patch('pathlib.Path.read_bytes', side_effect=AssertionError('Wrong peer must not read assets')):
                for name in names:
                    with self.subTest(name=name):
                        request = Request(base + '/manuals/images/' + name,
                                          headers={'X-Forwarded-For': '172.30.32.2'})
                        self.assert_http_error(request, 403)

    def test_tutorial_images_refuse_unknown_encoded_and_traversal_paths(self):
        with self.tutorial_server() as (base, images, _):
            # Even an existing file outside the fixed image contract stays unavailable.
            for name in ('unknown-de.jpg', 'devices-overview-es.jpg', 'devices-overview-de.png'):
                (images / name).write_bytes(TUTORIAL_JPEG)
            for path in (
                    '/manuals/images/unknown-de.jpg',
                    '/manuals/images/devices-overview-es.jpg',
                    '/manuals/images/devices-overview-de.png',
                    '/manuals/images/../USER_DE.md',
                    '/manuals/images/../../config.yaml',
                    '/manuals/images/%2e%2e%2fUSER_DE.md',
                    '/manuals/images/%64evices-overview-de.jpg',
                    '/manuals/images/devices-overview-de.jpg/../diagnosis-de.jpg',
                    '/manuals/images/https://example.invalid/devices-overview-de.jpg'):
                with self.subTest(path=path):
                    self.assert_http_error(base + path, 404)

    def test_missing_allowlisted_tutorial_image_is_a_safe_404(self):
        with self.tutorial_server() as (base, images, names):
            missing = images / names[0]
            missing.unlink()
            self.assert_http_error(base + '/manuals/images/' + names[0], 404)
