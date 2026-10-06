import asyncio
import unittest
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from dovit_bridge.bridge import DovitBridge, CoverRuntime


class CommandSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.b = b = DovitBridge.__new__(DovitBridge)
        b.loop = asyncio.get_running_loop()
        b.cfg = SimpleNamespace(frame_sep=b'\0', cover_position_mode='timed')
        self.writer = Mock()
        self.writer.is_closing.return_value = False
        b.dovit = SimpleNamespace(writer=self.writer, send=AsyncMock())
        b.lights = {19: {'statetype': 0}}
        b.shutters = {20: {'statetype': 3, 'travel_time': 10}}
        b.thermostats = {44: {'target': {'statetype': 1}, 'mode': {'id': 46, 'statetype': 0}}}
        b.alarms = {87: {}, 88: {}}
        b.pending_alarm_house_state = None
        b.cover_positions = {20: 100}
        b.cover_runtime = {}
        b.cover_last_published_positions = {}
        b.mqtt = Mock()
        b.persist_cover_positions = Mock()

    async def asyncTearDown(self):
        for runtime in self.b.cover_runtime.values():
            self.b.cancel_cover_stop_task(runtime)
            self.b.cancel_cover_ticker_task(runtime)
        await asyncio.sleep(0)

    def replace(self):
        writer = Mock()
        writer.is_closing.return_value = False
        self.b.dovit.writer = writer

    async def flush(self):
        for _ in range(3):
            await asyncio.sleep(0)

    def message(self, topic, payload):
        self.b.on_message(None, None, SimpleNamespace(topic=topic, payload=payload, retain=False))

    async def test_every_mqtt_path_rejects_replacement_before_dispatch(self):
        for topic, payload in (
            ('dovit/light/19/set', b'ON'), ('dovit/cover/20/set', b'OPEN'),
            ('dovit/cover/20/set_position', b'50'), ('dovit/thermostat/44/set', b'22'),
            ('dovit/thermostat/44/mode/set', b'heat'), ('dovit/alarm/house/set', b'ARM_HOME'),
        ):
            with self.subTest(topic=topic):
                self.b.dovit.writer = self.writer
                self.message(topic, payload)
                self.replace()
                await self.flush()
                self.b.dovit.send.assert_not_called()
                self.assertIsNone(self.b.pending_alarm_house_state)
                self.assertEqual(self.b.cover_runtime, {})

    async def test_valid_commands_send_using_same_writer(self):
        for topic, payload in (
            ('dovit/light/19/set', b'ON'), ('dovit/cover/20/set', b'STOP'),
            ('dovit/cover/20/set_position', b'50'), ('dovit/thermostat/44/set', b'22'),
            ('dovit/thermostat/44/mode/set', b'heat'), ('dovit/alarm/house/set', b'ARM_HOME'),
        ):
            self.message(topic, payload)
            await self.flush()
        self.assertEqual(self.b.dovit.send.await_count, 7)
        for entry in self.b.dovit.send.call_args_list:
            self.assertIs(entry.kwargs['expected_writer'], self.writer)
        self.assertEqual(self.b.pending_alarm_house_state, 'armed_home')

    def last_sent_device(self):
        data = self.b.dovit.send.call_args.args[0]
        self.assertTrue(data.endswith(self.b.cfg.frame_sep))
        self.assertIs(self.b.dovit.send.call_args.kwargs['expected_writer'], self.writer)
        return ET.fromstring(data[:-len(self.b.cfg.frame_sep)]).find('device')

    async def test_legacy_cover_open_stop_close_use_command_endpoint(self):
        for global_mode, device_mode in (('legacy', 'timed'), ('timed', 'legacy')):
            self.b.cfg.cover_position_mode = global_mode
            self.b.shutters[20] = dict(statetype=1, command_statetype=0,
                                       travel_time=10, position_mode=device_mode)
            for action, expected in ((b'OPEN', '1.0'), (b'STOP', '0.0'), (b'CLOSE', '2.0')):
                with self.subTest(global_mode=global_mode, device_mode=device_mode, action=action):
                    self.b.dovit.send.reset_mock()
                    self.message('dovit/cover/20/set', action)
                    await self.flush()
                    self.b.dovit.send.assert_awaited_once()
                    device = self.last_sent_device()
                    self.assertEqual(device.get('id'), '20')
                    self.assertEqual(device.findtext('statetype'), '0')
                    self.assertEqual(device.findtext('statevalue'), expected)
                    self.assertEqual(self.b.cover_runtime, {})

    async def test_legacy_cover_without_command_endpoint_keeps_fallback(self):
        self.b.cfg.cover_position_mode = 'legacy'
        for action, expected in ((b'OPEN', '1.0'), (b'STOP', '0.0'), (b'CLOSE', '2.0')):
            with self.subTest(action=action):
                self.message('dovit/cover/20/set', action)
                await self.flush()
                device = self.last_sent_device()
                self.assertEqual(device.findtext('statetype'), '3')
                self.assertEqual(device.findtext('statevalue'), expected)

    async def test_legacy_cover_and_bounded_temperature_keep_captured_writer(self):
        self.b.cfg.cover_position_mode = 'legacy'
        self.b.shutters[20] = dict(statetype=1, command_statetype=0)
        self.b.thermostats[44].update(min_temp=16, max_temp=26, temp_step=3)
        for topic, action in (
                ('dovit/cover/20/set', b'OPEN'), ('dovit/cover/20/set', b'STOP'),
                ('dovit/cover/20/set', b'CLOSE'), ('dovit/thermostat/44/set', b'26')):
            with self.subTest(topic=topic, action=action):
                self.b.dovit.writer = self.writer
                self.message(topic, action)
                self.replace()
                await self.flush()
                self.b.dovit.send.assert_not_called()

    async def test_thermostat_step_rounding_respects_both_bounds(self):
        self.b.thermostats[44].update(min_temp=16, max_temp=26, temp_step=3)
        for requested, expected in ((b'26', '26.0'), (b'999', '26.0'),
                                    (b'16', '16.0'), (b'-999', '16.0')):
            with self.subTest(requested=requested):
                self.message('dovit/thermostat/44/set', requested)
                await self.flush()
                device = self.last_sent_device()
                self.assertEqual(device.get('id'), '44')
                self.assertEqual(device.findtext('statetype'), '1')
                self.assertEqual(device.findtext('statevalue'), expected)

    async def test_thermostat_normal_half_degree_rounding_is_preserved(self):
        self.b.thermostats[44].update(min_temp=16, max_temp=26, temp_step=.5)
        for requested, expected in ((b'22.2', '22.0'), (b'22.8', '23.0'),
                                    (b'16', '16.0'), (b'26', '26.0')):
            with self.subTest(requested=requested):
                self.message('dovit/thermostat/44/set', requested)
                await self.flush()
                self.assertEqual(self.last_sent_device().findtext('statevalue'), expected)

    async def test_thermostat_serialized_value_respects_non_grid_bounds(self):
        for minimum, maximum, requested, expected in (
                (16.04, 26.04, b'16.04', '16.1'),
                (16.05, 26.05, b'26.05', '26.0'),
                (-26.05, -16.05, b'-26.05', '-26.0'),
                (-26.04, -16.04, b'-16.04', '-16.1')):
            with self.subTest(minimum=minimum, maximum=maximum, requested=requested):
                self.b.thermostats[44].update(min_temp=minimum, max_temp=maximum, temp_step=3)
                self.message('dovit/thermostat/44/set', requested)
                await self.flush()
                value = self.last_sent_device().findtext('statevalue')
                self.assertEqual(value, expected)
                self.assertGreaterEqual(float(value), minimum)
                self.assertLessEqual(float(value), maximum)

    async def test_thermostat_unrepresentable_or_invalid_limits_do_not_send(self):
        for limits in (
                dict(min_temp=16.01, max_temp=16.09, temp_step=.5),
                dict(min_temp=16, max_temp=26, temp_step=1e-320),
                dict(min_temp=16, max_temp=26, temp_step=0),
                dict(min_temp=16, max_temp=26, temp_step=float('nan')),
                dict(min_temp=16, max_temp=float('inf'), temp_step=.5),
                dict(min_temp=26, max_temp=16, temp_step=.5)):
            with self.subTest(limits=limits):
                self.b.thermostats[44].update(limits)
                with self.assertLogs('dovit_bridge.bridge', level='WARNING'):
                    self.message('dovit/thermostat/44/set', b'16')
                await self.flush()
                self.b.dovit.send.assert_not_called()

    async def test_callback_entry_capture_survives_validation_reconnect(self):
        payload = Mock()
        payload.__len__ = Mock(return_value=2)
        payload.decode.side_effect = lambda *args, **kwargs: (self.replace() or 'ON')
        self.message('dovit/light/19/set', payload)
        await self.flush()
        self.b.dovit.send.assert_not_called()

    async def test_send_coroutine_creation_binds_writer_before_execution(self):
        frame = self.b.send_frame('<test/>')
        light = self.b.send_light(19, 'ON')
        self.replace()
        self.assertFalse(await frame)
        self.assertFalse(await light)
        self.b.dovit.send.assert_not_called()

    async def test_missing_and_closing_writer_never_rebind(self):
        for writer in (None, self.writer):
            self.b.dovit.writer = writer
            self.writer.is_closing.return_value = True
            self.message('dovit/light/19/set', b'ON')
            self.replace()
            await self.flush()
        self.b.dovit.send.assert_not_called()

    async def test_timer_replacement_during_delay_precedes_runtime_mutation(self):
        runtime = CoverRuntime(command_writer=self.writer)
        self.b.cover_runtime[20] = runtime
        async def delay(seconds):
            self.replace()
        with patch('dovit_bridge.bridge.asyncio.sleep', side_effect=delay):
            await self.b.delayed_cover_stop(20, 3, 1, expected_writer=self.writer)
        self.assertFalse(runtime.stop_for_target)
        self.b.dovit.send.assert_not_called()

    async def test_timer_child_keeps_original_writer_after_cancellation_gap(self):
        runtime = CoverRuntime(command_writer=self.writer)
        self.b.cover_runtime[20] = runtime
        children = []
        with patch('dovit_bridge.bridge.asyncio.create_task', side_effect=lambda coro: children.append(coro)):
            await self.b.delayed_cover_stop(20, 3, 0, expected_writer=self.writer)
        self.assertTrue(runtime.stop_for_target)
        self.assertEqual(len(children), 1)
        self.replace()
        self.assertFalse(await children[0])
        self.b.dovit.send.assert_not_called()

    async def test_pending_cover_direction_preserves_writer_into_timer(self):
        self.b.handle_cover_target_position(20, 50, expected_writer=self.writer)
        await self.flush()
        self.replace()
        self.b.start_cover_motion(20, self.b.shutters[20], 'closing')
        runtime = self.b.cover_runtime[20]
        self.assertIs(runtime.command_writer, self.writer)
        self.b.cancel_cover_stop_task(runtime)
        await self.b.delayed_cover_stop(20, 3, 0, expected_writer=runtime.command_writer)
        self.assertFalse(runtime.stop_for_target)
        self.assertEqual(self.b.dovit.send.await_count, 1)

    async def test_alarm_group_cannot_continue_on_replacement_after_await(self):
        async def first_send(data, *, expected_writer):
            self.replace()
        self.b.dovit.send.side_effect = first_send
        self.message('dovit/alarm/house/set', b'ARM_AWAY')
        self.assertIsNone(self.b.pending_alarm_house_state)
        await self.flush()
        self.assertEqual(self.b.dovit.send.await_count, 1)
