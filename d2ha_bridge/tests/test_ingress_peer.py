"""Supervisor DNS peer authentication without a fixed address or live HA."""
from contextlib import contextmanager
import json
import socket
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dovit_bridge.web_monitor import Monitor, make_server


class IngressPeerTests(unittest.TestCase):
    @contextmanager
    def server(self, peers):
        original = socket.getaddrinfo
        lookups = []

        def resolve(host, port, *args, **kwargs):
            if host != 'supervisor':
                return original(host, port, *args, **kwargs)
            lookups.append((host, port, args))
            if isinstance(peers, Exception):
                raise peers
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (peer, 0))
                    for peer in peers]

        monitor = Monitor()
        server = make_server(monitor, '127.0.0.1', 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        with patch('dovit_bridge.web_monitor.socket.getaddrinfo', side_effect=resolve):
            thread.start()
            try:
                yield f'http://127.0.0.1:{server.server_port}', monitor, lookups
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())

    def refused(self, request):
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_accepts_actual_supervisor_peer_from_multiple_dns_answers(self):
        with self.server(['192.0.2.2', '127.0.0.1']) as (base, _, lookups):
            with urlopen(base + '/api/snapshot', timeout=2) as response:
                self.assertIn('session', json.load(response))
            self.assertEqual(lookups, [('supervisor', None, (socket.AF_INET, socket.SOCK_STREAM))])

    def test_rejects_get_and_post_with_spoofed_headers_before_any_action(self):
        with self.server(['192.0.2.2']) as (base, monitor, _):
            for method in ('GET', 'POST'):
                with self.subTest(method=method):
                    self.refused(Request(base + '/api/setup', method=method,
                        headers={'X-Forwarded-For': '192.0.2.2', 'X-Ingress-Path': '/api/hassio_ingress/fake',
                                 'X-Dovit-Token': monitor.session}))

    def test_dns_failure_or_empty_result_fails_closed(self):
        for peers in (socket.gaierror('Synthetic DNS failure'), []):
            with self.subTest(peers=repr(peers)), self.server(peers) as (base, monitor, _):
                self.refused(base + '/api/snapshot')
                self.refused(Request(base + '/api/setup', method='POST',
                                     headers={'X-Dovit-Token': monitor.session}))

    def test_refreshes_supervisor_address_after_dns_change_and_keeps_post_token(self):
        peers = ['127.0.0.1']
        with self.server(peers) as (base, _, lookups):
            with urlopen(base + '/api/snapshot', timeout=2) as response:
                self.assertEqual(response.status, 200)
            self.refused(Request(base + '/api/setup', method='POST'))
            peers[:] = ['192.0.2.22']
            self.refused(base + '/api/snapshot')
            self.assertEqual(len(lookups), 3)
