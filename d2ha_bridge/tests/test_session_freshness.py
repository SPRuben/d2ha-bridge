import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

from dovit_bridge.bridge import DovitBridge
from dovit_bridge.topics import DOVIT_STATUS_TOPIC, ALARM_HOUSE_AVAILABILITY_TOPIC
from dovit_bridge.topics import ALARM_STATE_AVAILABILITY_TOPIC_FMT, ALARM_TEXT_AVAILABILITY_TOPIC_FMT


class SessionFreshnessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge = b = DovitBridge.__new__(DovitBridge)
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
        b.alarm_partition_raw_states = {187: 1, 188: 1}
        b.alarm_partition_triggered = {187}
        b.pending_alarm_house_state = 'armed_away'
        b._dovit_connected = False
        b._session_diagnostics_dirty = True
        b._alarm_session_readings = {}
        b._alarm_session_triggers = set()
        for name in ('lights', 'shutters', 'thermostats', 'motions', 'contacts'):
            setattr(b, name, {})
        b.monitor = Mock()
        b.publish_all_cover_positions = Mock()

    async def frame(self, dev_id, statetype, value):
        b = self.bridge
        xml = (f'<hidv-state><device id="{dev_id}"><statetype>{statetype}</statetype>'
               f'<statevalue>{value}</statevalue></device></hidv-state>').encode() + b'\0'
        b.dovit = Mock()
        b.dovit.read = AsyncMock(side_effect=[xml, RuntimeError('fixture end')])
        with self.assertRaisesRegex(RuntimeError, 'fixture end'):
            await b.dovit_read_loop()

    def availability(self):
        return [entry.args[1] for entry in self.bridge.mqtt.publish.call_args_list
                if entry.args[0] == ALARM_HOUSE_AVAILABILITY_TOPIC]

    def transport_snapshot_calls(self):
        return [entry for entry in self.bridge.mqtt.publish.call_args_list
                if entry.args[0] in (DOVIT_STATUS_TOPIC, ALARM_HOUSE_AVAILABILITY_TOPIC)]

    async def test_start_loss_reconnect_reset_and_duplicate_notifications(self):
        b = self.bridge
        b.set_dovit_connected(False)
        self.assertEqual(b.alarm_partition_raw_states, {})
        self.assertEqual(b.alarm_partition_triggered, set())
        self.assertIsNone(b.pending_alarm_house_state)
        self.assertEqual(self.transport_snapshot_calls(), [
            call(DOVIT_STATUS_TOPIC, 'offline', qos=1, retain=True),
            call(ALARM_HOUSE_AVAILABILITY_TOPIC, 'offline', qos=1, retain=True)])
        b.mqtt.reset_mock()
        b.set_dovit_connected(False)
        b.mqtt.publish.assert_not_called()
        b.set_dovit_connected(True)
        await self.frame(187, 1, '1')
        b.set_dovit_connected(True)
        self.assertEqual(b._alarm_session_readings, {187: 1})
        b.pending_alarm_house_state = 'armed_home'
        b.set_dovit_connected(False)
        self.assertFalse(b._alarm_session_fresh())
        self.assertEqual(b.alarm_partition_raw_states, {})
        self.assertIsNone(b.pending_alarm_house_state)
        b.set_dovit_connected(True)
        await self.frame(188, 1, '1')
        self.assertFalse(b._alarm_session_fresh())
        self.assertEqual(self.availability()[-1], 'offline')

    async def test_partial_full_and_nonfinite_readings(self):
        b = self.bridge
        b.set_dovit_connected(True)
        await self.frame(187, 1, '0')
        self.assertEqual(self.availability()[-1], 'offline')
        for invalid in ('nan', 'inf', 'garbage'):
            await self.frame(188, 1, invalid)
            self.assertFalse(b._alarm_session_fresh())
        await self.frame(188, 1, '1')
        self.assertEqual(self.availability()[-1], 'online')
        self.assertEqual(b.alarm_partition_raw_states, {187: 0, 188: 1})

    async def test_current_session_trigger_unlocks_then_loss_invalidates(self):
        b = self.bridge
        b.set_dovit_connected(True)
        await self.frame(187, 2, 'text only')
        self.assertFalse(b._alarm_session_fresh())
        await self.frame(187, 3, 'trigger text')
        self.assertEqual(self.availability()[-1], 'online')
        b.set_dovit_connected(False)
        b.set_dovit_connected(True)
        self.assertEqual(self.availability()[-1], 'offline')
        self.assertEqual(b.alarm_partition_triggered, set())

    async def test_ambiguous_or_missing_roles_do_not_unlock(self):
        b = self.bridge
        b.set_dovit_connected(True)
        b.alarms[188]['partition_role'] = 'motion'
        await self.frame(187, 3, 'trigger')
        self.assertFalse(b._alarm_session_fresh())
        del b.alarms[188]
        self.assertFalse(b._alarm_session_fresh())

    async def test_mqtt_reconnect_schedules_snapshot_without_reset(self):
        b = self.bridge
        b.set_dovit_connected(True)
        await self.frame(187, 1, '0')
        await self.frame(188, 1, '1')
        before = dict(b.alarm_partition_raw_states)
        b.mqtt.reset_mock()
        client = Mock()
        thread = threading.Thread(target=b.on_connect, args=(client, None, {}, 0))
        thread.start()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        b.mqtt.publish.assert_not_called()
        await asyncio.sleep(0)
        self.assertEqual(b.alarm_partition_raw_states, before)
        self.assertEqual(self.transport_snapshot_calls(), [
            call(DOVIT_STATUS_TOPIC, 'online', qos=1, retain=True),
            call(ALARM_HOUSE_AVAILABILITY_TOPIC, 'online', qos=1, retain=True)])

    async def test_disconnected_mqtt_does_not_queue_diagnostics(self):
        b = self.bridge
        b.mqtt.connected = False
        b.set_dovit_connected(True)
        b._record_alarm_session_evidence(187, reading=0)
        b._record_alarm_session_evidence(188, reading=1)
        b.mqtt.publish.assert_not_called()
        b.mqtt.connected = True
        b.republish_session_status()
        self.assertEqual(self.availability(), ['offline'])

    async def test_lifecycle_rejects_non_loop_thread(self):
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.bridge.set_dovit_connected, True)

    async def test_direct_offline_aggregate_fixture_semantics_preserved(self):
        b = self.bridge
        b.publish_combined_alarm_state()
        self.assertEqual(b.mqtt.publish.call_args.args,
                         ('dovit/alarm/house/state', 'triggered'))
        self.assertEqual(self.availability(), [])

    async def test_initialized_offline_suppresses_received_and_aggregate_alarm(self):
        b = self.bridge
        b.set_dovit_connected(False)
        self.assertFalse(b.monitor.connected)
        b.mqtt.reset_mock()
        for statetype in (1, 2, 3):
            await self.frame(187, statetype, '1')
        b.publish_combined_alarm_state()
        b.mqtt.publish.assert_not_called()
        self.assertEqual(b.alarm_partition_raw_states, {})
        self.assertEqual(b.alarm_partition_triggered, set())
        b.set_dovit_connected(True)
        self.assertTrue(b.monitor.connected)

    async def test_diagnostic_exceptions_do_not_interrupt_lifecycle(self):
        b = self.bridge
        b.mqtt.publish.side_effect = RuntimeError('publish failure')
        with self.assertLogs('dovit_bridge.bridge', level='ERROR'):
            b.set_dovit_connected(True)
            b._record_alarm_session_evidence(187, reading=0)
            b._record_alarm_session_evidence(188, reading=1)
            b.set_dovit_connected(False)
        self.assertFalse(b.monitor.connected)
        self.assertEqual(b._alarm_session_readings, {})

    async def test_discovery_reconnect_is_loop_owned_without_estimated_positions(self):
        b = self.bridge
        b.cfg.enable_discovery = True
        b.publish_all_discovery_once = Mock()
        b.on_connect(Mock(), None, {}, 0)
        b.publish_all_discovery_once.assert_not_called()
        b.publish_all_cover_positions.assert_not_called()
        await asyncio.sleep(0)
        b.publish_all_discovery_once.assert_called_once_with(reason='connect')
        b.publish_all_cover_positions.assert_not_called()

    async def test_failed_offline_exception_and_rc_retry_current_snapshot(self):
        b = self.bridge
        for failure in (RuntimeError('fail once'), SimpleNamespace(rc=4)):
            with self.subTest(failure=failure):
                b.mqtt.publish.side_effect = None
                b.set_dovit_connected(True)
                b.mqtt.publish.side_effect = [failure, SimpleNamespace(rc=0)]
                with self.assertLogs('dovit_bridge.bridge', level='ERROR'):
                    b.set_dovit_connected(False)
                self.assertTrue(b._session_diagnostics_dirty)
                b.mqtt.publish.side_effect = None
                b.mqtt.reset_mock()
                sleep_calls = []

                async def tick(seconds):
                    sleep_calls.append(seconds)
                    if len(sleep_calls) == 2:
                        raise asyncio.CancelledError()

                with patch('dovit_bridge.bridge.asyncio.sleep', side_effect=tick):
                    with self.assertRaises(asyncio.CancelledError):
                        await b.session_status_retry_loop()
                self.assertEqual(sleep_calls, [3, 3])
                self.assertEqual(self.transport_snapshot_calls(), [
                    call(DOVIT_STATUS_TOPIC, 'offline', qos=1, retain=True),
                    call(ALARM_HOUSE_AVAILABILITY_TOPIC, 'offline', qos=1, retain=True)])
                self.assertFalse(b._session_diagnostics_dirty)

    async def test_evidence_success_preserves_dirty_and_duplicate_retry_preserves_data(self):
        b = self.bridge
        b.mqtt.publish.side_effect = [SimpleNamespace(rc=4), SimpleNamespace(rc=0)]
        with self.assertLogs('dovit_bridge.bridge', level='ERROR'):
            b.set_dovit_connected(True)
        b.mqtt.publish.side_effect = None
        b._record_alarm_session_evidence(187, reading=0)
        b._record_alarm_session_evidence(188, reading=1)
        self.assertTrue(b._session_diagnostics_dirty)
        b.mqtt.reset_mock()
        b.set_dovit_connected(True)
        self.assertEqual(b._alarm_session_readings, {187: 0, 188: 1})
        self.assertFalse(b._session_diagnostics_dirty)
        self.assertEqual(self.transport_snapshot_calls(), [
            call(DOVIT_STATUS_TOPIC, 'online', qos=1, retain=True),
            call(ALARM_HOUSE_AVAILABILITY_TOPIC, 'offline', qos=1, retain=True)])

    async def test_clean_retry_tick_does_not_publish(self):
        b = self.bridge
        b.set_dovit_connected(False)
        b.mqtt.reset_mock()
        ticks = 0

        async def tick(seconds):
            nonlocal ticks
            ticks += 1
            if ticks == 2:
                raise asyncio.CancelledError()

        with patch('dovit_bridge.bridge.asyncio.sleep', side_effect=tick):
            with self.assertRaises(asyncio.CancelledError):
                await b.session_status_retry_loop()
        b.mqtt.publish.assert_not_called()

    def gate_value(self, dev_id, kind):
        fmt = (ALARM_STATE_AVAILABILITY_TOPIC_FMT if kind == 'state'
               else ALARM_TEXT_AVAILABILITY_TOPIC_FMT)
        values = [entry.args[1] for entry in self.bridge.mqtt.publish.call_args_list
                  if entry.args[0] == fmt.format(id=dev_id)]
        return values[-1]

    async def test_empty_cache_gates_precede_mqtt_online(self):
        b = self.bridge
        b.set_dovit_connected(True)
        self.assertEqual(self.availability(), ['offline'])
        for dev_id in b.alarms:
            self.assertEqual(self.gate_value(dev_id, 'state'), 'offline')
            self.assertEqual(self.gate_value(dev_id, 'text'), 'offline')
        self.assertEqual(b.mqtt.mock_calls[-1], call.mark_online())

    async def test_partition_state_and_text_are_independent_and_ordered(self):
        b = self.bridge
        b.set_dovit_connected(True)
        b.mqtt.reset_mock()
        await self.frame(187, 1, '0')
        self.assertEqual(self.gate_value(187, 'state'), 'online')
        self.assertEqual(self.gate_value(187, 'text'), 'offline')
        self.assertEqual(self.gate_value(188, 'state'), 'offline')
        self.assertEqual(self.availability()[-1], 'offline')
        await self.frame(188, 2, 'actual text')
        self.assertEqual(self.gate_value(188, 'text'), 'online')
        self.assertEqual(self.gate_value(188, 'state'), 'offline')
        calls = b.mqtt.publish.call_args_list
        self.assertLess(calls.index(call('dovit/alarm/188/text', 'actual text', qos=1, retain=True)),
                        calls.index(call(ALARM_TEXT_AVAILABILITY_TOPIC_FMT.format(id=188),
                                         'online', qos=1, retain=True)))

    async def test_partial_trigger_unlocks_house_and_only_triggered_partition(self):
        b = self.bridge
        b.set_dovit_connected(True)
        b.mqtt.reset_mock()
        await self.frame(187, 3, 'trigger text')
        self.assertEqual(self.gate_value(187, 'state'), 'online')
        self.assertEqual(self.gate_value(188, 'state'), 'offline')
        self.assertEqual(self.gate_value(187, 'text'), 'online')
        self.assertEqual(self.availability()[-1], 'online')
        self.assertEqual(b._alarm_last_accepted_house_state, 'triggered')
        calls = b.mqtt.publish.call_args_list
        self.assertLess(calls.index(call('dovit/alarm/187/state', 'triggered', qos=1, retain=True)),
                        calls.index(call(ALARM_STATE_AVAILABILITY_TOPIC_FMT.format(id=187),
                                         'online', qos=1, retain=True)))
        self.assertLess(calls.index(call('dovit/alarm/house/state', 'triggered', qos=1, retain=True)),
                        calls.index(call(ALARM_HOUSE_AVAILABILITY_TOPIC, 'online', qos=1, retain=True)))

    async def test_broker_reconnect_replays_current_alarm_values_before_gates(self):
        b = self.bridge
        b.set_dovit_connected(True)
        await self.frame(187, 1, '0')
        await self.frame(188, 1, '1')
        await self.frame(187, 2, 'current text')
        b.mqtt.reset_mock()
        b.on_connect(Mock(), None, {}, 0)
        await asyncio.sleep(0)
        calls = b.mqtt.publish.call_args_list
        for state_topic, value, gate in (
            ('dovit/alarm/187/state', 'disarmed', ALARM_STATE_AVAILABILITY_TOPIC_FMT.format(id=187)),
            ('dovit/alarm/188/state', 'armed', ALARM_STATE_AVAILABILITY_TOPIC_FMT.format(id=188)),
            ('dovit/alarm/187/text', 'current text', ALARM_TEXT_AVAILABILITY_TOPIC_FMT.format(id=187)),
            ('dovit/alarm/house/state', 'armed_home', ALARM_HOUSE_AVAILABILITY_TOPIC),
        ):
            self.assertLess(calls.index(call(state_topic, value, qos=1, retain=True)),
                            calls.index(call(gate, 'online', qos=1, retain=True)))
        self.assertEqual(b.mqtt.mock_calls[-1], call.mark_online())
        b.set_dovit_connected(False)
        self.assertIsNone(b._alarm_last_accepted_house_state)
        b.mqtt.reset_mock()
        b.set_dovit_connected(True)
        self.assertFalse(any(c.args[0].startswith('dovit/alarm/') for c in b.mqtt.publish.call_args_list))

    async def test_failed_house_or_sensor_state_keeps_gate_offline_then_recovers(self):
        b = self.bridge
        for topic in ('dovit/alarm/house/state', 'dovit/alarm/187/state', 'dovit/alarm/187/text'):
            for failure in ('rc', 'exception'):
                with self.subTest(topic=topic, failure=failure):
                    b.mqtt.publish.side_effect = None
                    b.set_dovit_connected(False)
                    b.set_dovit_connected(True)
                    await self.frame(187, 1, '0')
                    await self.frame(188, 1, '1')
                    await self.frame(187, 2, 'SECRET_TEXT')
                    def publish(current_topic, payload, **kwargs):
                        if current_topic == topic:
                            if failure == 'exception':
                                raise RuntimeError('SECRET_TEXT')
                            return SimpleNamespace(rc=4)
                        return SimpleNamespace(rc=0)
                    b.mqtt.reset_mock()
                    b.mqtt.publish.side_effect = publish
                    with self.assertLogs('dovit_bridge.bridge', level='ERROR') as logs:
                        b.republish_session_status()
                    self.assertNotIn('SECRET_TEXT', '\n'.join(logs.output))
                    self.assertTrue(b._session_diagnostics_dirty)
                    b.mqtt.mark_online.assert_not_called()
                    if topic.endswith('house/state'):
                        self.assertEqual(self.availability()[-1], 'offline')
                    else:
                        self.assertEqual(self.gate_value(187, topic.rsplit('/', 1)[1]), 'offline')
                    b.mqtt.publish.side_effect = None
                    b.republish_session_status()
                    self.assertFalse(b._session_diagnostics_dirty)
                    self.assertEqual(self.availability()[-1], 'online')

    async def test_online_announcement_failure_stays_dirty(self):
        b = self.bridge
        b.mqtt.mark_online.return_value = False
        b.set_dovit_connected(False)
        self.assertTrue(b._session_diagnostics_dirty)
        b.mqtt.mark_online.return_value = True
        b.set_dovit_connected(False)
        self.assertFalse(b._session_diagnostics_dirty)
