import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from dovit_bridge.main import run_bridge


class ShutdownTests(unittest.IsolatedAsyncioTestCase):
    def bridge(self):
        bridge = SimpleNamespace(
            monitor=SimpleNamespace(connected=False), start_mqtt=Mock(),
            discovery_republish_loop=AsyncMock(), connect_dovit=AsyncMock(),
            session_status_retry_loop=AsyncMock(),
            dovit_read_loop=AsyncMock(side_effect=asyncio.CancelledError),
            reset_cover_motion=Mock(), dovit=SimpleNamespace(close=AsyncMock()),
            mqtt=SimpleNamespace(stop=Mock()))
        bridge.set_dovit_connected = Mock(
            side_effect=lambda connected: setattr(bridge.monitor, 'connected', connected))
        return bridge

    async def test_cancellation_closes_transports_and_preserves_cancellation(self):
        bridge = self.bridge()
        with self.assertRaises(asyncio.CancelledError):
            await run_bridge(bridge, SimpleNamespace(dovit_host='test.invalid', dovit_port=6060))
        self.assertFalse(bridge.monitor.connected)
        bridge.reset_cover_motion.assert_called_once()
        self.assertGreaterEqual(bridge.dovit.close.await_count, 1)
        bridge.mqtt.stop.assert_called_once()
        self.assertIn(True, [call.args[0] for call in bridge.set_dovit_connected.call_args_list])
        self.assertFalse(bridge.set_dovit_connected.call_args.args[0])

    async def test_mqtt_start_failure_still_cleans_up(self):
        bridge = self.bridge()
        bridge.start_mqtt.side_effect = RuntimeError('offline fixture')
        with self.assertRaisesRegex(RuntimeError, 'offline fixture'):
            await run_bridge(bridge, SimpleNamespace())
        bridge.connect_dovit.assert_not_awaited()
        bridge.mqtt.stop.assert_called_once()
        bridge.dovit.close.assert_awaited_once()

    async def test_discovery_is_cancelled_before_mqtt_shutdown(self):
        bridge = self.bridge()
        started, stopped = asyncio.Event(), asyncio.Event()

        async def discovery():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async def read():
            await started.wait()
            raise asyncio.CancelledError()

        bridge.discovery_republish_loop = discovery
        bridge.dovit_read_loop.side_effect = read
        bridge.mqtt.stop.side_effect = lambda: self.assertTrue(stopped.is_set())
        with self.assertRaises(asyncio.CancelledError):
            await run_bridge(bridge, SimpleNamespace(dovit_host='test.invalid', dovit_port=6060))
        self.assertTrue(stopped.is_set())
        bridge.mqtt.stop.assert_called_once()

    async def test_close_failure_still_stops_mqtt(self):
        bridge = self.bridge()
        bridge.start_mqtt.side_effect = RuntimeError('startup failed')
        bridge.dovit.close.side_effect = OSError('close failed')
        with self.assertRaisesRegex(OSError, 'close failed'):
            await run_bridge(bridge, SimpleNamespace())
        bridge.mqtt.stop.assert_called_once()

    async def test_read_failure_marks_offline_before_retry(self):
        bridge = self.bridge()
        bridge.dovit_read_loop.side_effect = ConnectionResetError('fixture')

        async def stop_retry(delay):
            self.assertEqual(delay, 3)
            self.assertFalse(bridge.monitor.connected)
            bridge.dovit.close.assert_awaited()
            raise asyncio.CancelledError()

        with patch('dovit_bridge.main.asyncio.sleep', side_effect=stop_retry):
            with self.assertLogs('dovit_bridge.main', level='ERROR'):
                with self.assertRaises(asyncio.CancelledError):
                    await run_bridge(bridge, SimpleNamespace(dovit_host='test.invalid', dovit_port=6060))
        bridge.mqtt.stop.assert_called_once()

    async def test_tcp_loss_callback_immediately_marks_offline(self):
        bridge = self.bridge()

        async def read():
            self.assertTrue(bridge.monitor.connected)
            bridge.dovit.on_connection_lost()
            self.assertFalse(bridge.monitor.connected)
            raise asyncio.CancelledError()

        bridge.dovit_read_loop.side_effect = read
        with self.assertRaises(asyncio.CancelledError):
            await run_bridge(bridge, SimpleNamespace(dovit_host='test.invalid', dovit_port=6060))

    async def test_status_retry_task_stops_before_mqtt(self):
        bridge = self.bridge()
        started, stopped = asyncio.Event(), asyncio.Event()

        async def retry():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async def read():
            await started.wait()
            raise asyncio.CancelledError()

        bridge.session_status_retry_loop = retry
        bridge.dovit_read_loop.side_effect = read
        bridge.mqtt.stop.side_effect = lambda: self.assertTrue(stopped.is_set())
        with self.assertRaises(asyncio.CancelledError):
            await run_bridge(bridge, SimpleNamespace(dovit_host='test.invalid', dovit_port=6060))
