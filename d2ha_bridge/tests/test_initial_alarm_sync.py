import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from dovit_bridge.bridge import DovitBridge
from dovit_bridge.dovit_tcp import DovitTcp
from dovit_bridge.topics import ALARM_HOUSE_AVAILABILITY_TOPIC, ALARM_HOUSE_STATE_TOPIC


QUERY = (b'<hisynch-ask><username>user</username><pw></pw>'
         b'<clientid>-1</clientid></hisynch-ask>\0')


class InitialAlarmSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        b = self.bridge = DovitBridge.__new__(DovitBridge)
        b.loop = asyncio.get_running_loop()
        b.cfg = SimpleNamespace(enable_discovery=False, frame_sep=b'\0')
        b.mqtt = Mock(connected=True)
        b.mqtt.publish.return_value.rc = 0
        b.mqtt.mark_online.return_value = True
        b.alarms = {
            187: {'partition_role': 'motion', 'state_statetype': 1,
                  'text_statetype': 2, 'trigger_statetype': 3},
            188: {'partition_role': 'contact', 'state_statetype': 1,
                  'text_statetype': 2, 'trigger_statetype': 3},
        }
        b.alarm_partition_raw_states = {}
        b.alarm_partition_triggered = set()
        b.pending_alarm_house_state = None
        b._dovit_connected = False
        b._session_diagnostics_dirty = True
        b._alarm_session_readings = {}
        b._alarm_session_triggers = set()
        for name in ('lights', 'switches', 'shutters', 'thermostats', 'motions', 'contacts'):
            setattr(b, name, {})
        b.monitor = Mock()
        b.publish_all_cover_positions = Mock()
        b.dovit = Mock(writer=object(), connect=AsyncMock(), send=AsyncMock())

    async def test_no_alarm_mapping_preserves_heartbeat_only_connection(self):
        b = self.bridge
        b.alarms = {}
        await b.connect_dovit()
        b.dovit.connect.assert_awaited_once_with()
        b.dovit.send.assert_not_awaited()

    async def test_sync_is_read_only_and_bound_to_new_writer(self):
        b = self.bridge
        await b.connect_dovit()
        b.dovit.send.assert_awaited_once_with(QUERY, expected_writer=b.dovit.writer)
        self.assertFalse(b._dovit_connected)
        self.assertFalse(b._alarm_session_fresh())
        b.mqtt.publish.assert_not_called()

    async def test_send_failure_propagates_without_fabricating_availability(self):
        b = self.bridge
        b.dovit.send.side_effect = ConnectionError('fixture connection lost')
        with self.assertRaises(ConnectionError):
            await b.connect_dovit()
        self.assertFalse(b._alarm_session_fresh())
        self.assertEqual(b.alarm_partition_raw_states, {})
        b.mqtt.publish.assert_not_called()

    async def test_real_tcp_start_and_reconnect_receive_current_partition_states(self):
        b = self.bridge
        requests = []
        deliveries = [(0, 0), (1, 1)]
        response_done = asyncio.Queue()

        async def server_client(reader, writer):
            try:
                while True:
                    frame = await reader.readuntil(b'\0')
                    if frame == b'\0':
                        continue
                    requests.append(frame)
                    if frame != QUERY:
                        return
                    values = deliveries[len(requests) - 1]
                    response = b''.join(
                        (f'<hidv-state><device id="{dev_id}"><statetype>1</statetype>'
                         f'<statevalue>{value}</statevalue></device></hidv-state>').encode() + b'\0'
                        for dev_id, value in zip((187, 188), values))
                    # Exercise fragmented/coalesced frames as on a real TCP stream.
                    writer.write(response[:31])
                    await writer.drain()
                    writer.write(response[31:])
                    await writer.drain()
                    await response_done.put(True)
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(server_client, '127.0.0.1', 0)
        b.dovit = DovitTcp('127.0.0.1', server.sockets[0].getsockname()[1])
        b.dovit.on_connection_lost = lambda: b.set_dovit_connected(False)
        try:
            for expected_state in ('disarmed', 'armed_away'):
                await b.connect_dovit()
                b.set_dovit_connected(True)
                self.assertFalse(b._alarm_session_fresh())
                task = asyncio.create_task(b.dovit_read_loop())
                try:
                    await asyncio.wait_for(response_done.get(), 2)
                    async with asyncio.timeout(2):
                        while not b._alarm_session_fresh():
                            await asyncio.sleep(0.001)
                    self.assertEqual(b._alarm_last_accepted_house_state, expected_state)
                    calls = [(c.args[0], c.args[1]) for c in b.mqtt.publish.call_args_list]
                    self.assertIn((ALARM_HOUSE_STATE_TOPIC, expected_state), calls)
                    self.assertEqual([v for t, v in calls if t == ALARM_HOUSE_AVAILABILITY_TOPIC][-1], 'online')
                    self.assertEqual(set(b._alarm_session_readings), {187, 188})
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    await b.dovit.close()
                self.assertFalse(b._alarm_session_fresh())
                self.assertEqual(b.alarm_partition_raw_states, {})
                b.mqtt.reset_mock()
            self.assertEqual(requests, [QUERY, QUERY])
        finally:
            await b.dovit.close()
            server.close()
            await server.wait_closed()
