import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dovit_bridge.bridge import DovitBridge


class Covers(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.b = DovitBridge.__new__(DovitBridge)
        self.b.cfg = SimpleNamespace(cover_position_mode="timed")
        self.b.loop = asyncio.get_running_loop()
        writer = Mock()
        writer.is_closing.return_value = False
        self.b.dovit = SimpleNamespace(writer=writer)
        self.info = dict(statetype=1, command_statetype=0, travel_time_up=27,
                         travel_time_down=24)
        self.b.shutters = {20: self.info}
        self.b.cover_positions = {20: 100}
        self.b.cover_runtime = {}
        self.b.cover_last_published_positions = {}
        self.b.mqtt = Mock()
        self.b.persist_cover_positions = Mock()
        self.b.send_cover_frame = Mock()
        self.clock = patch('dovit_bridge.bridge.time')
        self.now = self.clock.start().monotonic
        self.now.return_value = 100

    async def asyncTearDown(self):
        for runtime in self.b.cover_runtime.values():
            self.b.cancel_cover_stop_task(runtime)
            self.b.cancel_cover_ticker_task(runtime)
        await asyncio.sleep(0)
        self.clock.stop()

    async def test_timer_waits_for_motion_and_duplicate_does_not_restart(self):
        self.b.handle_cover_target_position(20, 50)
        r = self.b.get_cover_runtime(20)
        self.assertIsNone(r.stop_task)
        self.now.return_value = 103
        self.b.start_cover_motion(20, self.info, 'closing')
        timer = r.stop_task
        self.assertIsNotNone(timer)
        self.now.return_value = 104
        self.b.start_cover_motion(20, self.info, 'closing')
        self.assertIs(r.stop_task, timer)
        self.assertEqual(r.started_at, 103)

    async def test_early_stop_freezes_actual_estimate_and_cancels_timer(self):
        self.b.handle_cover_target_position(20, 50)
        self.b.start_cover_motion(20, self.info, 'closing')
        r = self.b.get_cover_runtime(20)
        self.now.return_value = 106
        self.assertEqual(self.b.finish_cover_motion(20, self.info), 75)
        self.assertIsNone(r.stop_task)
        self.assertIsNone(r.direction)

    async def test_late_dovit_stop_clamps_endpoint(self):
        self.b.handle_cover_target_position(20, 0)
        self.b.start_cover_motion(20, self.info, 'closing')
        self.assertIsNone(self.b.get_cover_runtime(20).stop_task)
        self.now.return_value = 160
        self.assertEqual(self.b.finish_cover_motion(20, self.info), 0)

    async def test_reverse_stops_without_sending_opposite_direction(self):
        self.b.start_cover_motion(20, self.info, 'closing')
        self.now.return_value = 112
        self.b.handle_cover_target_position(20, 80)
        self.assertEqual(self.b.send_cover_frame.call_args.args[2], '0.0')
        self.assertEqual(self.b.finish_cover_motion(20, self.info), 50)
        self.b.handle_cover_target_position(20, 80)
        self.assertEqual(self.b.send_cover_frame.call_args.args[2], '1.0')
        self.assertEqual(self.b.send_cover_frame.call_args.args[1], 0)

    async def test_same_direction_retarget_preserves_current_position(self):
        self.b.handle_cover_target_position(20, 50)
        self.b.start_cover_motion(20, self.info, 'closing')
        self.now.return_value = 106
        self.b.handle_cover_target_position(20, 25)
        self.assertEqual(self.b.estimate_cover_position(20, self.info), 75)
        self.assertEqual(self.b.send_cover_frame.call_count, 1)

    async def test_estimate_does_not_claim_target_if_stop_delayed(self):
        self.b.handle_cover_target_position(20, 50)
        self.b.start_cover_motion(20, self.info, 'closing')
        self.now.return_value = 118
        self.assertEqual(self.b.finish_cover_motion(20, self.info), 25)

    async def test_endpoint_can_recalibrate_even_if_estimate_already_there(self):
        self.b.handle_cover_target_position(20, 100)
        self.assertEqual(self.b.send_cover_frame.call_args.args[2], '1.0')

    async def test_legacy_and_invalid_times(self):
        self.b.cfg.cover_position_mode = 'legacy'
        self.b.handle_cover_target_position(20, 50)
        self.b.send_cover_frame.assert_not_called()
        self.b.cfg.cover_position_mode = 'timed'
        for invalid in ('bad', float('nan'), float('inf'), 0, -2):
            self.info['travel_time_up'] = invalid
            self.assertFalse(self.b.cover_supports_position(20))

    async def test_timer_sends_stop_without_fabricating_confirmation(self):
        self.b.handle_cover_target_position(20, 50)
        self.b.start_cover_motion(20, self.info, 'closing')
        r = self.b.get_cover_runtime(20)
        self.b.cancel_cover_stop_task(r)
        await self.b.delayed_cover_stop(20, 0, 0, expected_writer=self.b.dovit.writer)
        self.assertEqual(self.b.send_cover_frame.call_args.args[2], '0.0')
        self.assertEqual(r.direction, 'closing')

    async def test_disconnect_cancels_scheduled_commands(self):
        self.b.handle_cover_target_position(20, 50)
        self.b.start_cover_motion(20, self.info, 'closing')
        r = self.b.get_cover_runtime(20)
        self.b.reset_cover_motion()
        self.assertIsNone(r.stop_task)
        self.assertIsNone(r.direction)


if __name__ == '__main__':
    unittest.main()
