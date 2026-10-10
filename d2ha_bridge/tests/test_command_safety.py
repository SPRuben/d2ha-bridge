from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from dovit_bridge.bridge import DovitBridge


class CommandSafetyTests(unittest.TestCase):
    def test_nonretained_commands_keep_existing_dispatch(self):
        bridge = DovitBridge.__new__(DovitBridge)
        bridge.loop = Mock()
        bridge.loop.call_soon_threadsafe.side_effect = lambda callback: callback()
        writer = Mock()
        writer.is_closing.return_value = False
        bridge.dovit = SimpleNamespace(writer=writer)
        bridge.lights = {19: {'statetype': 0}}
        bridge.shutters = {20: {'statetype': 3}}
        bridge.thermostats = {44: {'target': {'statetype': 1},
                                 'mode': {'id': 46, 'statetype': 0}}}
        bridge.cover_supports_position = Mock(return_value=False)
        bridge.send_frame = Mock(return_value=object())
        bridge.send_light = Mock(return_value=object())
        with patch('dovit_bridge.bridge.asyncio.run_coroutine_threadsafe') as schedule:
            for topic, payload, endpoint, value in (
                    ('dovit/cover/20/set', b'CLOSE', 20, '2.0'),
                    ('dovit/thermostat/44/set', b'22.2', 44, '22.0'),
                    ('dovit/thermostat/44/mode/set', b'heat', 46, '1.0')):
                bridge.on_message(None, None, SimpleNamespace(topic=topic, payload=payload, retain=False))
                frame = bridge.send_frame.call_args.args[0]
                self.assertIn(f'<device id="{endpoint}">', frame)
                self.assertIn(f'<statevalue>{value}</statevalue>', frame)
            bridge.on_message(None, None, SimpleNamespace(topic='dovit/light/19/set', payload=b'ON', retain=False))
            bridge.send_light.assert_called_once_with(19, 'ON', expected_writer=writer)
            self.assertEqual(bridge.loop.create_task.call_count, 4)
            schedule.assert_not_called()

    def test_all_retained_commands_rejected_before_resolution(self):
        bridge = DovitBridge.__new__(DovitBridge)
        with patch('dovit_bridge.bridge.asyncio.run_coroutine_threadsafe') as send:
            for topic, payload in [('dovit/light/19/set', b'ON'), ('dovit/cover/20/set', b'OPEN'),
                                   ('dovit/cover/20/set_position', b'50'), ('dovit/thermostat/44/set', b'22'),
                                   ('dovit/thermostat/44/mode/set', b'heat'), ('dovit/alarm/house/set', b'DISARM'),
                                   ('dovit/alarm/house/set', b'ARM_AWAY')]:
                with self.assertLogs(level='WARNING'):
                    bridge.on_message(None, None, SimpleNamespace(topic=topic, payload=payload, retain=True))
            send.assert_not_called()

    def test_nonfinite_temperatures_rejected(self):
        bridge = DovitBridge.__new__(DovitBridge)
        bridge.shutters = {}
        bridge.thermostats = {44: {}}
        with patch('dovit_bridge.bridge.asyncio.run_coroutine_threadsafe') as send:
            for value in (b'nan', b'inf', b'-inf', b'1e999'):
                with self.assertLogs(level='WARNING'):
                    bridge.on_message(None, None, SimpleNamespace(topic='dovit/thermostat/44/set', payload=value))
            send.assert_not_called()

    def test_alarm_needs_both_finite_readings_but_trigger_is_immediate(self):
        bridge = DovitBridge.__new__(DovitBridge)
        bridge.alarms = {87: {}, 88: {}}
        bridge.alarm_partition_triggered = set()
        bridge.pending_alarm_house_state = None
        bridge.mqtt = Mock()
        for raw in ({}, {87: 0}, {88: 1}, {87: float('nan'), 88: 0}):
            bridge.alarm_partition_raw_states = raw
            bridge.publish_combined_alarm_state()
            bridge.mqtt.publish.assert_not_called()
        bridge.alarm_partition_raw_states = {87: 0, 88: 0}
        bridge.publish_combined_alarm_state()
        self.assertEqual(bridge.mqtt.publish.call_args.args[1], 'disarmed')
        bridge.alarm_partition_raw_states = {}
        bridge.alarm_partition_triggered.add(88)
        bridge.publish_combined_alarm_state()
        self.assertEqual(bridge.mqtt.publish.call_args.args[1], 'triggered')
