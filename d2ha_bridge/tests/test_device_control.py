import asyncio
import time
import unittest
import uuid
import json
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import Mock, AsyncMock
from dovit_bridge.device_control import DeviceControl, plan
from dovit_bridge.web_monitor import Monitor, make_server


class DeviceControlTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.maps = {'shutters': {20: {'statetype': 1, 'command_statetype': 0}},
                     'thermostats': {44: {'target': {'id': 45, 'statetype': 1},
                        'current': {'id': 42, 'statetype': 1}, 'mode': {'id': 46, 'statetype': 0},
                        'min_temp': 16, 'max_temp': 26, 'temp_step': .5}}}
        self.monitor = Monitor()
        self.monitor.configure(self.maps)
        self.control = DeviceControl(self.monitor, simulation=True, maps=self.maps)

    def raw(self, **changes):
        return dict(dict(id=20, category='shutters', action='OPEN', confirm=True, request_id=str(uuid.uuid4())), **changes)

    def live(self):
        bridge = Mock(shutters=self.maps['shutters'], thermostats=self.maps['thermostats'],
                      cover_runtime={}, send_frame=AsyncMock(return_value=True))
        bridge.dovit.writer.is_closing.return_value = False
        self.monitor.connected = True
        return DeviceControl(self.monitor, asyncio.get_running_loop(), bridge), bridge

    async def test_simulated_commands_and_idempotency(self):
        for action, expected in [('OPEN', 1), ('STOP', 0), ('CLOSE', 2)]:
            raw = self.raw(action=action)
            self.assertEqual(self.control.submit(raw)['expected'], expected)
            before = self.monitor.sequence
            self.control.submit(raw)
            self.assertEqual(self.monitor.sequence, before)
        for action, value, dev in [('TEMPERATURE', 22.5, 45), ('heat', None, 46), ('off', None, 46)]:
            c = self.control.submit(self.raw(category='thermostats', id=44, action=action, value=value))
            self.assertEqual(c['id'], dev)
            self.assertEqual(c['status'], 'observed')

    async def test_reject_unconfirmed_alarm_unknown_and_invalid_values(self):
        for changes in [dict(confirm=False), dict(id=999), dict(id=True), dict(category='alarms'), dict(action='DISARM')]:
            with self.assertRaises(ValueError):
                self.control.submit(self.raw(**changes))
        for value in [None, True, float('nan'), float('inf'), 15, 27, 22.3]:
            with self.assertRaises(ValueError):
                self.control.submit(self.raw(category='thermostats', id=44, action='TEMPERATURE', value=value))
        self.assertEqual(self.monitor.sequence, 0)

    async def test_send_distinct_statetype_and_exact_observation(self):
        control, bridge = self.live()
        c = control.submit(self.raw())
        await asyncio.sleep(.02)
        xml = bridge.send_frame.call_args.args[0]
        self.assertIs(bridge.send_frame.call_args.kwargs['expected_writer'], bridge.dovit.writer)
        self.assertIn('<statetype>0</statetype>', xml)
        self.assertIn('<statevalue>1.0</statevalue>', xml)
        self.assertEqual(self.monitor.commands[c['request_id']]['status'], 'transmitted')
        self.monitor.observe(20, 0, '1')
        self.monitor.observe(20, 1, '2')
        self.assertEqual(self.monitor.commands[c['request_id']]['status'], 'transmitted')
        self.monitor.observe(20, 1, '1')
        self.assertEqual(self.monitor.commands[c['request_id']]['status'], 'observed')

    async def test_reconnect_during_validation_does_not_rebind_command(self):
        control, bridge = self.live()
        original_maps = control.current_maps

        def reconnect():
            bridge.dovit.writer = Mock()
            return original_maps()

        control.current_maps = reconnect
        command = control.submit(self.raw())
        await asyncio.sleep(.03)
        bridge.send_frame.assert_not_awaited()
        self.assertEqual(self.monitor.commands[command['request_id']]['status'], 'failed')

    async def test_stop_supersedes_queued_move_and_bypasses_busy(self):
        control, bridge = self.live()
        first = control.submit(self.raw())
        with self.assertRaisesRegex(ValueError, 'light_busy'):
            control.submit(self.raw(action='CLOSE'))
        control.submit(self.raw(action='STOP'))
        await asyncio.sleep(.02)
        bridge.send_frame.assert_awaited_once()
        self.assertIn('<statevalue>0.0</statevalue>', bridge.send_frame.call_args.args[0])
        self.assertEqual(self.monitor.commands[first['request_id']]['status'], 'failed')

    async def test_reconnect_changed_mapping_and_expiry_rejected(self):
        for mode in ('reconnect', 'mapping', 'expiry'):
            control, bridge = self.live()
            c = control.submit(self.raw())
            record = self.monitor.commands[c['request_id']]
            if mode == 'reconnect':
                bridge.dovit.writer = Mock()
            elif mode == 'mapping':
                bridge.shutters[20] = {'statetype': 9}
            else:
                record['status'] = 'failed'
            await asyncio.sleep(.02)
            bridge.send_frame.assert_not_awaited()
            self.assertEqual(record['status'], 'failed')

    async def test_cover_reversal_guard_and_timer_cancel(self):
        control, bridge = self.live()
        runtime = Mock(direction='closing', pending_direction=None)
        bridge.cover_runtime[20] = runtime
        with self.assertLogs(level='ERROR'):
            control.submit(self.raw())
            await asyncio.sleep(.02)
        bridge.send_frame.assert_not_awaited()
        control.submit(self.raw(action='STOP'))
        await asyncio.sleep(.02)
        bridge.cancel_cover_stop_task.assert_called_once_with(runtime)
        self.assertIsNone(runtime.target_position)
        bridge.send_frame.assert_awaited_once()

    async def test_send_failure_and_disconnected(self):
        with self.assertRaisesRegex(ValueError, 'light_disconnected'):
            DeviceControl(self.monitor).submit(self.raw())
        control, bridge = self.live()
        bridge.send_frame.return_value = False
        c = control.submit(self.raw())
        await asyncio.sleep(.02)
        self.assertEqual(self.monitor.commands[c['request_id']]['status'], 'failed')

    async def test_expired_dispatch_never_sends(self):
        raw = self.raw()
        self.control.submit(raw)
        record = self.monitor.commands[raw['request_id']]
        record['status'] = 'requested'
        control, bridge = self.live()
        await control.send(record, self.maps['shutters'][20], bridge.dovit.writer, time.monotonic()-1)
        bridge.send_frame.assert_not_awaited()
        self.assertEqual(record['status'], 'failed')

    async def test_http_token_disabled_and_confirmation(self):
        server = make_server(self.monitor, '127.0.0.1', 0, '127.0.0.1')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def post(raw, token=None):
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['X-Dovit-Token'] = token
            request = Request(f'http://127.0.0.1:{server.server_port}/api/controls/command',
                              data=json.dumps(raw).encode(), headers=headers)
            try:
                with urlopen(request) as response:
                    return response.status, json.load(response)
            except HTTPError as error:
                with error:
                    return error.code, error.read()
        try:
            self.assertEqual(post(self.raw())[0], 403)
            self.assertEqual(post(self.raw(), self.monitor.session)[0], 400)
            self.monitor.device_control = self.control
            self.assertEqual(post(self.raw(confirm=False), self.monitor.session)[0], 400)
            self.assertEqual(post(self.raw(category='alarms'), self.monitor.session)[0], 400)
            self.assertEqual(len(self.monitor.commands), 0)
            status, response = post(self.raw(), self.monitor.session)
            self.assertEqual(status, 200)
            self.assertEqual(response['command']['status'], 'observed')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
