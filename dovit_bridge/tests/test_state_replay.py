import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch

from dovit_bridge.bridge import DovitBridge


class StateReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_estimated_positions_do_not_queue_while_mqtt_disconnected(self):
        b = self.b
        b.cfg.cover_position_mode = 'timed'
        b.mqtt.connected = False
        b.publish_cover_position(20, b.shutters[20], position=50, force=True)
        b.mqtt.publish.assert_not_called()
        self.assertEqual(b.cover_last_published_positions, {})
        self.assertEqual(b._state_cache, {})

    async def test_failed_position_enqueue_does_not_suppress_next_publication(self):
        b = self.b
        b.cfg.cover_position_mode = 'timed'
        b.mqtt.publish.return_value.rc = 4
        b.publish_cover_position(20, b.shutters[20], position=50)
        self.assertEqual(b.cover_last_published_positions, {})
        b.mqtt.publish.return_value.rc = 0
        b.publish_cover_position(20, b.shutters[20], position=50)
        self.assertEqual(b.mqtt.publish.call_count, 2)
        self.assertEqual(b.cover_last_published_positions, {20: 50})
        self.assertEqual(b._state_cache, {})

    async def asyncSetUp(self):
        self.b = b = DovitBridge.__new__(DovitBridge)
        b.loop = asyncio.get_running_loop()
        b.cfg = SimpleNamespace(enable_discovery=False, frame_sep=b'\0',
                                cover_position_mode='legacy')
        b.mqtt = Mock(connected=True)
        b.mqtt.publish.return_value.rc = 0
        b.mqtt.mark_online.return_value = True
        b.monitor = Mock()
        b.lights = {19: {'statetype': 0}}
        b.shutters = {20: {'statetype': 3, 'travel_time': 10}}
        b.motions = {30: {'statetype': 4}}
        b.contacts = {31: {'statetype': 5}}
        b.thermostats = {44: {'target': {'statetype': 1},
                             'current': {'id': 42, 'statetype': 6},
                             'mode': {'id': 46, 'statetype': 7}}}
        b.alarms = {}
        b.alarm_partition_raw_states = {}
        b.alarm_partition_triggered = set()
        b.pending_alarm_house_state = None
        b._state_cache = {}
        b._dovit_connected = False
        b._session_diagnostics_dirty = True
        b.cover_positions = {20: 50}
        b.cover_runtime = {}
        b.cover_last_published_positions = {}
        b.persist_cover_positions = Mock()
        b.publish_all_cover_positions = Mock()
        b.seen_unknown = set()
        b.shutter_candidate_values = {}
        b._observed_endpoint_limit_warned = False
        b.set_dovit_connected(True)
        b.mqtt.reset_mock()

    async def frames(self, readings):
        data = b''.join((
            f'<hidv-state><device id="{dev_id}"><statetype>{statetype}</statetype>'
            f'<statevalue>{value}</statevalue></device></hidv-state>'
        ).encode() + b'\0' for dev_id, statetype, value in readings)
        self.b.dovit = SimpleNamespace(read=AsyncMock(
            side_effect=[data, RuntimeError('fixture receive complete')]))
        with self.assertRaisesRegex(RuntimeError, 'fixture receive complete'):
            await self.b.dovit_read_loop()

    def cached_payloads(self):
        return {topic: entry[1] for topic, entry in self.b._state_cache.items()}

    def replay_calls(self):
        return [entry for entry in self.b.mqtt.publish.call_args_list
                if entry.args[0] in self.b._state_routes()]

    async def test_helper_caches_canonical_provenance_and_latest_value(self):
        b = self.b
        topic = 'dovit/light/19/state'
        b._publish_received_state(topic, 'ON', 19, 0)
        b._publish_received_state(topic, 'OFF', 19, 0)
        self.assertEqual(b._state_cache[topic], (b._state_routes()[topic], 'OFF'))
        self.assertEqual(len(b._state_cache), 1)
        b.mqtt.publish.assert_any_call(topic, 'OFF', qos=1, retain=True)

    async def test_actual_receive_path_all_non_alarm_families_preserves_decimals(self):
        await self.frames([(19, 0, '1'), (20, 3, '2.0'), (30, 4, '1'),
                           (31, 5, '0'), (44, 1, '22.250'), (42, 6, '19.8750'),
                           (46, 7, '1')])
        expected = {
            'dovit/light/19/state': 'ON', 'dovit/cover/20/state': 'closing',
            'dovit/motion/30/state': 'ON', 'dovit/contact/31/state': 'OFF',
            'dovit/thermostat/44/target_temperature': '22.250',
            'dovit/thermostat/44/current_temperature': '19.8750',
            'dovit/thermostat/44/mode': 'heat',
        }
        self.assertEqual(self.cached_payloads(), expected)
        routes = self.b._state_routes()
        for topic, (route, payload) in self.b._state_cache.items():
            self.assertEqual(route, routes[topic])
            self.b.mqtt.publish.assert_any_call(topic, payload, qos=1, retain=True)
        self.assertLessEqual(len(self.b._state_cache), len(routes))

    async def test_mqtt_down_records_latest_without_queue_and_reconnect_orders_replay(self):
        b = self.b
        b.mqtt.connected = False
        await self.frames([(19, 0, '1'), (19, 0, '0'), (42, 6, '20.1250')])
        b.mqtt.publish.assert_not_called()
        self.assertEqual(self.cached_payloads()['dovit/light/19/state'], 'OFF')
        b.mqtt.connected = True
        b.on_connect(Mock(), None, {}, 0)
        b.mqtt.publish.assert_not_called()
        await asyncio.sleep(0)
        b.publish_all_cover_positions.assert_not_called()
        self.assertEqual(set((c.args[0], c.args[1]) for c in self.replay_calls()), {
            ('dovit/light/19/state', 'OFF'),
            ('dovit/thermostat/44/current_temperature', '20.1250')})
        calls = b.mqtt.mock_calls
        online = calls.index(call.mark_online())
        for entry in self.replay_calls():
            self.assertLess(calls.index(call.publish(*entry.args, **entry.kwargs)), online)
        self.assertFalse(any('/set' in c.args[0] or c.args[0].startswith('homeassistant/')
                             for c in b.mqtt.publish.call_args_list))

    async def test_dovit_loss_and_start_clear_session_and_offline_frames_do_not_cache(self):
        b = self.b
        await self.frames([(19, 0, '1')])
        b.set_dovit_connected(False)
        self.assertEqual(b._state_cache, {})
        b.mqtt.reset_mock()
        await self.frames([(19, 0, '0')])
        self.assertEqual(b._state_cache, {})
        self.assertEqual(self.replay_calls(), [])
        b.set_dovit_connected(True)
        self.assertEqual(b._state_cache, {})
        b.mqtt.reset_mock()
        b.republish_session_status()
        self.assertEqual(self.replay_calls(), [])

    async def test_removed_and_remapped_routes_pruned_before_snapshot(self):
        b = self.b
        await self.frames([(19, 0, '1'), (42, 6, '20.500')])
        del b.lights[19]
        b.thermostats[44]['current']['id'] = 43
        b.mqtt.reset_mock()
        b.republish_session_status()
        self.assertEqual(b._state_cache, {})
        self.assertFalse(any(c.args[0] in ('dovit/light/19/state',
                                          'dovit/thermostat/44/current_temperature')
                             for c in b.mqtt.publish.call_args_list))
        await self.frames([(43, 6, '21.750')])
        self.assertEqual(self.cached_payloads(), {
            'dovit/thermostat/44/current_temperature': '21.750'})

    async def test_same_endpoint_changed_statetype_invalidates_old_cache(self):
        b = self.b
        b._publish_received_state('dovit/light/19/state', 'ON', 19, 0)
        b.lights[19]['statetype'] = 9
        b.mqtt.reset_mock()
        b.republish_session_status()
        self.assertEqual(b._state_cache, {})
        self.assertEqual(self.replay_calls(), [])

    async def test_failure_retries_current_value_on_three_second_loop(self):
        b = self.b
        topic = 'dovit/light/19/state'
        for failure in ('rc', 'exception'):
            with self.subTest(failure=failure):
                def failing(current_topic, payload, **kwargs):
                    if current_topic == topic:
                        if failure == 'exception':
                            raise RuntimeError('payload omitted')
                        return SimpleNamespace(rc=4)
                    return SimpleNamespace(rc=0)
                b.mqtt.publish.side_effect = failing
                with self.assertLogs('dovit_bridge.bridge', level='ERROR'):
                    b._publish_received_state(topic, 'ON', 19, 0)
                    b.republish_session_status()
                self.assertTrue(b._session_diagnostics_dirty)
                b.mqtt.connected = False
                b._publish_received_state(topic, 'OFF', 19, 0)
                b.mqtt.publish.side_effect = None
                b.mqtt.connected = True
                b.mqtt.reset_mock()
                ticks = []
                async def tick(seconds):
                    ticks.append(seconds)
                    if len(ticks) == 2:
                        raise asyncio.CancelledError()
                with patch('dovit_bridge.bridge.asyncio.sleep', side_effect=tick):
                    with self.assertRaises(asyncio.CancelledError):
                        await b.session_status_retry_loop()
                self.assertEqual(ticks, [3, 3])
                self.assertEqual(self.replay_calls(), [call(topic, 'OFF', qos=1, retain=True)])
                self.assertFalse(b._session_diagnostics_dirty)

    async def test_unknown_wrong_provenance_and_nonstate_topics_never_cached(self):
        b = self.b
        for topic, dev_id, statetype in (
            ('dovit/light/19/state', 19, 99), ('dovit/light/999/state', 999, 0),
            ('dovit/light/19/set', 19, 0), ('homeassistant/light/x/config', 19, 0),
            ('dovit/alarm/house/state', 19, 0), ('dovit/cover/20/position', 20, 3),
            ('dovit/clock/state', 19, 0),
        ):
            b._publish_received_state(topic, 'untrusted', dev_id, statetype)
        self.assertEqual(b._state_cache, {})

    async def test_estimated_cover_positions_do_not_enter_cache(self):
        b = self.b
        b.cfg.cover_position_mode = 'timed'
        b.publish_cover_position(20, b.shutters[20], position=75, force=True)
        self.assertEqual(b._state_cache, {})
        b.mqtt.publish.assert_called_once_with('dovit/cover/20/position', '75', qos=1, retain=True)
        b.mqtt.reset_mock()
        b.republish_session_status()
        self.assertFalse(any(c.args[0] == 'dovit/cover/20/position'
                             for c in b.mqtt.publish.call_args_list))

    async def test_unknown_cover_value_is_live_only_not_replayed(self):
        b = self.b
        await self.frames([(20, 3, '9.0')])
        b.mqtt.publish.assert_any_call('dovit/cover/20/state', 'VALUE_9.0', qos=1, retain=True)
        self.assertNotIn('dovit/cover/20/state', b._state_cache)
        b.mqtt.reset_mock()
        b.republish_session_status()
        self.assertEqual(self.replay_calls(), [])

    async def test_invalid_numeric_receive_frames_do_not_replace_valid_cache(self):
        b = self.b
        await self.frames([(19, 0, '1'), (42, 6, '19.250')])
        before = dict(b._state_cache)
        await self.frames([(19, 0, 'nan'), (42, 6, 'inf'), (44, 1, 'bad'), (46, 7, 'nan')])
        self.assertEqual(b._state_cache, before)

    async def test_legacy_fixture_keeps_direct_publish_without_session_cache(self):
        b = self.b
        del b._session_initialized
        b.mqtt.connected = False
        b._publish_received_state('dovit/light/19/state', 'ON', 19, 0)
        b.mqtt.publish.assert_called_once_with('dovit/light/19/state', 'ON', qos=1, retain=True)
        self.assertEqual(b._state_cache, {})

    async def test_cache_remains_bounded_to_one_value_per_configured_topic(self):
        b = self.b
        for index in range(100):
            b._publish_received_state('dovit/light/19/state', str(index), 19, 0)
            b._publish_received_state(f'dovit/light/{1000 + index}/state', 'ON', 1000 + index, 0)
        self.assertEqual(len(b._state_cache), 1)
        self.assertLessEqual(len(b._state_cache), len(b._state_routes()))
        self.assertEqual(self.cached_payloads()['dovit/light/19/state'], '99')
