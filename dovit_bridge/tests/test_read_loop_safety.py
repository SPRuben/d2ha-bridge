import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dovit_bridge.bridge import DovitBridge, MAX_RECEIVE_FRAME_BYTES, MAX_OBSERVED_ENDPOINTS
from dovit_bridge.topics import (
    THERMO_TARGET_STATE_TOPIC_FMT, THERMO_CURRENT_STATE_TOPIC_FMT,
    THERMO_MODE_STATE_TOPIC_FMT, LIGHT_STATE_TOPIC_FMT,
    MOTION_STATE_TOPIC_FMT, CONTACT_STATE_TOPIC_FMT,
)


def frame(device, value):
    return (f'<hidv-state><device id="{device}"><statetype>1</statetype>'
            f'<statevalue>{value}</statevalue></device></hidv-state>').encode()


class FakeRead:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    async def read(self, size):
        return next(self.chunks, b'')


class ReadLoopSafetyTests(unittest.IsolatedAsyncioTestCase):
    def make_bridge(self, chunks, sep=b'\0'):
        bridge = DovitBridge.__new__(DovitBridge)
        bridge.cfg = SimpleNamespace(frame_sep=sep, enable_discovery=False)
        bridge.dovit = FakeRead(chunks)
        bridge.monitor = Mock()
        bridge.mqtt = Mock()
        bridge.thermostats = {1: {'target': {'statetype': 1},
                                  'current': {'id': 2, 'statetype': 1},
                                  'mode': {'id': 3, 'statetype': 1}}}
        bridge.lights = {4: {'statetype': 1}}
        bridge.motions = {5: {'statetype': 1}}
        bridge.contacts = {6: {'statetype': 1}}
        bridge.shutters = {}
        bridge.alarms = {}
        bridge.seen_unknown = set()
        bridge.shutter_candidate_values = {}
        return bridge

    async def run_to_eof(self, bridge):
        with self.assertRaisesRegex(RuntimeError, 'closed by server'):
            await bridge.dovit_read_loop()

    async def test_fragmentation_coalescing_and_raw_precision(self):
        first = frame(1, '21.1234500')
        second = frame(2, '-2.50000')
        bridge = self.make_bridge([first[:7], first[7:] + b'\r',
                                   b'\n' + second + b'\r\n'], b'\r\n')
        await self.run_to_eof(bridge)
        self.assertEqual([call.args for call in bridge.mqtt.publish.call_args_list], [
            (THERMO_TARGET_STATE_TOPIC_FMT.format(id=1), '21.1234500'),
            (THERMO_CURRENT_STATE_TOPIC_FMT.format(id=1), '-2.50000')])

    async def test_invalid_telemetry_is_dropped_and_next_frame_processed(self):
        for device in range(1, 7):
            for invalid in ('NaN', 'inf', '-Infinity', '1e999', 'bad', ''):
                with self.subTest(device=device, invalid=invalid):
                    bridge = self.make_bridge([frame(device, invalid) + b'\0' +
                                               frame(device, '0.5') + b'\0'])
                    await self.run_to_eof(bridge)
                    self.assertEqual(bridge.mqtt.publish.call_count, 1)
                    self.assertEqual(bridge.mqtt.publish.call_args.kwargs,
                                     {'qos': 1, 'retain': True})

    async def test_threshold_semantics(self):
        routes = ((3, THERMO_MODE_STATE_TOPIC_FMT, 1, 'off', 'heat'),
                  (4, LIGHT_STATE_TOPIC_FMT, 4, 'OFF', 'ON'),
                  (5, MOTION_STATE_TOPIC_FMT, 5, 'OFF', 'ON'),
                  (6, CONTACT_STATE_TOPIC_FMT, 6, 'OFF', 'ON'))
        for device, topic, target, low, high in routes:
            for value, expected in (('-1', low), ('0.499999', low),
                                    ('0.5', high), ('2', high)):
                with self.subTest(device=device, value=value):
                    bridge = self.make_bridge([frame(device, value) + b'\0'])
                    await self.run_to_eof(bridge)
                    bridge.mqtt.publish.assert_called_once_with(
                        topic.format(id=target), expected, qos=1, retain=True)

    async def test_malformed_xml_does_not_block_following_valid_frame(self):
        bridge = self.make_bridge([b'<hidv-state><device\0' + frame(4, '1') + b'\0'])
        with self.assertLogs(level='ERROR'):
            await self.run_to_eof(bridge)
        bridge.mqtt.publish.assert_called_once_with(
            LIGHT_STATE_TOPIC_FMT.format(id=4), 'ON', qos=1, retain=True)

    async def test_invalid_alarm_reading_does_not_clear_previous_trigger(self):
        bridge = self.make_bridge([frame(87, 'NaN') + b'\0'])
        bridge.alarms = {87: {'state_statetype': 1}, 88: {'state_statetype': 1}}
        bridge.alarm_partition_raw_states = {87: 1.0, 88: 1.0}
        bridge.alarm_partition_triggered = {87}
        with self.assertLogs(level='WARNING'):
            await self.run_to_eof(bridge)
        self.assertEqual(bridge.alarm_partition_raw_states, {87: 1.0, 88: 1.0})
        self.assertEqual(bridge.alarm_partition_triggered, {87})
        bridge.mqtt.publish.assert_not_called()

    async def test_completed_frame_limit_before_stripping(self):
        raw = frame(4, '1')
        for extra in (0, 1):
            with self.subTest(extra=extra):
                bridge = self.make_bridge([raw + b' ' * extra + b'\0'])
                with patch('dovit_bridge.bridge.MAX_RECEIVE_FRAME_BYTES', len(raw)):
                    if extra:
                        with self.assertRaisesRegex(RuntimeError, 'byte limit'):
                            await bridge.dovit_read_loop()
                        bridge.mqtt.publish.assert_not_called()
                    else:
                        await self.run_to_eof(bridge)
                        bridge.mqtt.publish.assert_called_once()

    async def test_incomplete_tail_limit_after_completed_frame(self):
        raw = frame(4, '1')
        bridge = self.make_bridge([raw + b'\0' + b'x' * len(raw), b'x'])
        with patch('dovit_bridge.bridge.MAX_RECEIVE_FRAME_BYTES', len(raw)):
            with self.assertRaisesRegex(RuntimeError, 'byte limit'):
                await bridge.dovit_read_loop()
        bridge.mqtt.publish.assert_called_once()

    async def test_oversize_frame_does_not_resync_to_following_command(self):
        bridge = self.make_bridge([b'x' * 129 + b'\0' + frame(4, '1') + b'\0'])
        with patch('dovit_bridge.bridge.MAX_RECEIVE_FRAME_BYTES', 128):
            with self.assertRaisesRegex(RuntimeError, 'byte limit'):
                await bridge.dovit_read_loop()
        bridge.mqtt.publish.assert_not_called()

    async def test_exact_limit_with_fragmented_multibyte_separator(self):
        raw = frame(4, '1')
        bridge = self.make_bridge([raw + b'\r', b'\n'], b'\r\n')
        with patch('dovit_bridge.bridge.MAX_RECEIVE_FRAME_BYTES', len(raw)):
            await self.run_to_eof(bridge)
        bridge.mqtt.publish.assert_called_once()

    async def test_coalesced_frames_are_limited_individually(self):
        raw = frame(4, '1')
        bridge = self.make_bridge([(raw + b'\0') * 3])
        with patch('dovit_bridge.bridge.MAX_RECEIVE_FRAME_BYTES', len(raw)):
            await self.run_to_eof(bridge)
        self.assertEqual(bridge.mqtt.publish.call_count, 3)

    async def test_separator_prefix_becoming_payload_exceeds_limit(self):
        raw = frame(4, '1')
        bridge = self.make_bridge([raw + b'\r', b'x'], b'\r\n')
        with patch('dovit_bridge.bridge.MAX_RECEIVE_FRAME_BYTES', len(raw)):
            with self.assertRaisesRegex(RuntimeError, 'byte limit'):
                await bridge.dovit_read_loop()
        bridge.mqtt.publish.assert_not_called()

    async def test_unknown_endpoint_cap_keeps_known_telemetry_and_warns_once(self):
        self.assertEqual(MAX_OBSERVED_ENDPOINTS, 2000)
        ids = list(range(100, 100 + MAX_OBSERVED_ENDPOINTS + 2))
        bridge = self.make_bridge([frame(device, '1') + b'\0' for device in ids])
        with patch('dovit_bridge.bridge.LOGGER.warning') as warning:
            await self.run_to_eof(bridge)
            self.assertEqual(bridge.seen_unknown, {(device, 1) for device in ids[:2000]})
            # The warning stays bounded across read-loop restarts as well.
            bridge.dovit = FakeRead([frame(ids[-1], '1') + b'\0',
                                    frame(ids[0], '1') + b'\0', frame(4, '1') + b'\0'])
            await self.run_to_eof(bridge)
            warning.assert_called_once()
        bridge.mqtt.publish.assert_called_once_with(
            LIGHT_STATE_TOPIC_FMT.format(id=4), 'ON', qos=1, retain=True)

    async def test_candidate_cap_preserves_existing_candidate_promotion(self):
        ids = list(range(100, 100 + MAX_OBSERVED_ENDPOINTS + 2))
        bridge = self.make_bridge([frame(device, '1.0') + b'\0' for device in ids])
        bridge.cfg.enable_discovery = True
        bridge.cfg.light_statetypes = set()
        bridge.cfg.shutter_values = {'0.0', '1.0', '2.0'}
        bridge.cfg.shutter_confidence_distinct_values = 2
        bridge.cfg.devices_file = SimpleNamespace(name='synthetic.json')
        bridge.monitor.routes = {}
        bridge.unassigned_endpoints = set()
        bridge.cover_supports_position = Mock(return_value=False)
        devices = {'shutters': {}}
        with patch('dovit_bridge.bridge.load_devices', return_value=devices), \
                patch('dovit_bridge.bridge.save_devices') as save, \
                patch('dovit_bridge.bridge.LOGGER.warning') as warning:
            await self.run_to_eof(bridge)
            self.assertEqual(set(bridge.shutter_candidate_values),
                             {(device, 1) for device in ids[:2000]})
            save.assert_not_called()
            bridge.dovit = FakeRead([frame(ids[-1], '2.0') + b'\0',
                                    frame(ids[0], '2.0') + b'\0'])
            await self.run_to_eof(bridge)
            save.assert_called_once_with(bridge.cfg.devices_file, devices)
            self.assertEqual(set(devices['shutters']), {str(ids[0])})
            self.assertEqual(bridge.shutter_candidate_values[(ids[0], 1)], {'1.0', '2.0'})
            self.assertEqual(len(bridge.shutter_candidate_values), MAX_OBSERVED_ENDPOINTS)
            self.assertEqual(len(bridge.seen_unknown), MAX_OBSERVED_ENDPOINTS)
            warning.assert_called_once()
        self.assertIn(ids[0], bridge.shutters)
        self.assertEqual(bridge.mqtt.publish.call_args.args[1], 'closing')

    async def test_legacy_candidate_refreshes_active_monitor_routes_immediately(self):
        from dovit_bridge.web_monitor import Monitor
        bridge = self.make_bridge([frame(99, '1.0') + b'\0'])
        bridge.monitor = Monitor()
        bridge.cfg.enable_discovery = True
        bridge.cfg.light_statetypes = {1}
        bridge.cfg.shutter_values = set()
        bridge.cfg.devices_file = SimpleNamespace(name='synthetic.json')
        bridge.unassigned_endpoints = set()
        document = {'lights': {}}
        with patch('dovit_bridge.bridge.load_devices', return_value=document), \
                patch('dovit_bridge.bridge.save_devices'):
            await self.run_to_eof(bridge)
        state = bridge.monitor.snapshot()['states'][0]
        self.assertEqual(state['matches'], [{'uid': 'lights:99', 'role': 'state'}])
        self.assertEqual(state['classification'], 'inferred')
        self.assertEqual(bridge.monitor.snapshot()['devices'][0]['uid'], 'lights:99')

    async def test_default_limit_is_one_mib_and_bounds_unterminated_input(self):
        self.assertEqual(MAX_RECEIVE_FRAME_BYTES, 1024 * 1024)
        bridge = self.make_bridge([b'x' * 4096] * 256 + [b'x'])
        with self.assertRaisesRegex(RuntimeError, 'byte limit'):
            await bridge.dovit_read_loop()
        bridge.mqtt.publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
