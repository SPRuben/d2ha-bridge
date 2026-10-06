import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from dovit_bridge.dovit_tcp import DovitTcp


class TcpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.peers = []
        self.accepted = asyncio.Queue()

        def accept(reader, writer):
            self.peers.append(writer)
            self.accepted.put_nowait((reader, writer))

        self.server = await asyncio.start_server(accept, '127.0.0.1', 0)
        self.client = DovitTcp('127.0.0.1', self.server.sockets[0].getsockname()[1], .01)

    async def asyncTearDown(self):
        await self.client.close()
        for writer in self.peers:
            writer.close()
            await writer.wait_closed()
        self.server.close()
        await self.server.wait_closed()

    async def test_periodic_nul_and_commands_share_connection(self):
        self.assertEqual(DovitTcp('unused', 0).heartbeat_interval, 5)
        await self.client.connect()
        reader, _ = await self.accepted.get()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(3), 1), b'\0\0\0')
        await self.client.send(b'<test/>\0')
        received = await asyncio.wait_for(reader.readuntil(b'<test/>\0'), 1)
        self.assertTrue(received.endswith(b'<test/>\0'))

    async def test_health_log_and_receive_counters(self):
        await self.client.connect()
        reader, writer = await self.accepted.get()
        await asyncio.wait_for(reader.readexactly(1), 1)
        writer.write(b'hello')
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(self.client.read(5), 1), b'hello')
        self.assertEqual(self.client.rx_bytes, 5)
        self.assertIsNotNone(self.client.last_rx_at)
        self.client.heartbeats_sent = 29999

        async def wait_for_completed_heartbeat():
            # The peer can receive a NUL before send/drain completes, or read
            # one already buffered. The health report follows the completion.
            while self.client.heartbeats_sent < 30000:
                await asyncio.sleep(.001)

        with self.assertLogs('dovit_bridge.dovit_tcp', level='INFO') as logs:
            await asyncio.wait_for(reader.readexactly(1), 1)
            await asyncio.wait_for(wait_for_completed_heartbeat(), 1)
        self.assertIn('Dovit health', str(logs.output))
        self.assertIn('rx_bytes=5', str(logs.output))
        self.assertIn('heartbeats_sent=30000', str(logs.output))

    async def test_eof_clears_state_and_reconnect_replaces_heartbeat(self):
        await self.client.connect()
        reader, writer = await self.accepted.get()
        await asyncio.wait_for(reader.readexactly(1), 1)
        task = self.client._heartbeat_task
        writer.close()
        await writer.wait_closed()
        try:
            self.assertEqual(await asyncio.wait_for(self.client.read(), 1), b'')
        except ConnectionResetError:
            pass  # Windows may report a peer close as a reset.
        self.assertIsNone(self.client.writer)
        self.assertTrue(task.done())
        with self.assertLogs('dovit_bridge.dovit_tcp', level='ERROR'):
            with self.assertRaises(ConnectionError):
                await self.client.send(b'not-replayed')
        await self.client.connect()
        reader, _ = await self.accepted.get()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(2), 1), b'\0\0')

    async def test_close_is_idempotent_and_cancels_heartbeat(self):
        await self.client.connect()
        task = self.client._heartbeat_task
        await self.client.close()
        await self.client.close()
        self.assertTrue(task.done())
        self.assertIsNone(self.client.reader)
        self.assertIsNone(self.client.writer)

    async def test_send_failure_logged_without_payload_and_not_retried(self):
        self.client.on_connection_lost = Mock()
        writer = Mock()
        writer.is_closing.return_value = False
        writer.drain = AsyncMock(side_effect=ConnectionResetError('failure'))
        writer.wait_closed = AsyncMock()
        self.client.writer = writer
        with self.assertLogs('dovit_bridge.dovit_tcp', level='ERROR') as logs:
            with self.assertRaises(ConnectionResetError):
                await self.client.send(b'<pw>SECRET</pw>')
        self.assertNotIn('SECRET', ''.join(logs.output))
        writer.write.assert_called_once()
        writer.close.assert_called_once()
        self.client.on_connection_lost.assert_called_once()

    async def test_loss_callback_precedes_close_wait(self):
        writer = Mock()
        events = []
        writer.wait_closed = AsyncMock(side_effect=lambda: events.append('wait'))
        self.client.writer = writer
        self.client.on_connection_lost = lambda: events.append('offline')
        await self.client.close()
        self.assertEqual(events, ['offline', 'wait'])

    async def test_loss_callback_failure_does_not_prevent_cleanup(self):
        writer = Mock()
        writer.wait_closed = AsyncMock()
        self.client.writer = writer
        self.client.on_connection_lost = Mock(side_effect=ValueError('SECRET'))
        with self.assertLogs('dovit_bridge.dovit_tcp', level='ERROR') as logs:
            await self.client.close()
        self.assertNotIn('SECRET', str(logs.output))
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()

    async def test_read_reset_cleans_up_before_raising(self):
        self.client.reader = Mock()
        self.client.reader.read = AsyncMock(side_effect=ConnectionResetError())
        with self.assertRaises(ConnectionResetError):
            await self.client.read()
        self.assertIsNone(self.client.reader)

    async def test_old_send_failure_does_not_invalidate_replacement(self):
        entered, release = asyncio.Event(), asyncio.Event()
        old_writer, replacement = Mock(), Mock()
        old_writer.is_closing.return_value = False

        async def delayed_failure():
            entered.set()
            await release.wait()
            raise ConnectionResetError('old session')

        old_writer.drain = delayed_failure
        self.client.writer = old_writer
        self.client.on_connection_lost = Mock()
        sending = asyncio.create_task(self.client.send(b'fixture'))
        await entered.wait()
        self.client.writer = replacement
        replacement.wait_closed = AsyncMock()
        release.set()
        with self.assertLogs('dovit_bridge.dovit_tcp', level='ERROR'):
            with self.assertRaises(ConnectionResetError):
                await sending
        self.client.on_connection_lost.assert_not_called()
        old_writer.close.assert_called_once()
        replacement.close.assert_not_called()

    async def test_expected_writer_rejects_replacement_without_writing(self):
        old_writer, replacement = Mock(), Mock()
        replacement.is_closing.return_value = False
        replacement.drain = AsyncMock()
        replacement.wait_closed = AsyncMock()
        self.client.writer = replacement
        self.client.on_connection_lost = Mock()
        for expected in (old_writer, None):
            with self.assertLogs('dovit_bridge.dovit_tcp', level='WARNING'):
                with self.assertRaises(ConnectionError):
                    await self.client.send(b'command', expected_writer=expected)
        replacement.write.assert_not_called()
        self.client.on_connection_lost.assert_not_called()
        await self.client.send(b'current-command', expected_writer=replacement)
        replacement.write.assert_called_once_with(b'current-command')

    async def test_cancelled_close_closes_socket_before_heartbeat_wait(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def heartbeat():
            try:
                await asyncio.Event().wait()
            finally:
                entered.set()
                await release.wait()

        task = asyncio.create_task(heartbeat())
        await asyncio.sleep(0)
        writer = Mock()
        writer.wait_closed = AsyncMock()
        self.client.writer = writer
        self.client._heartbeat_task = task
        closing = asyncio.create_task(self.client.close())
        await entered.wait()
        writer.close.assert_called_once()
        closing.cancel()
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await closing
        await asyncio.gather(task, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
