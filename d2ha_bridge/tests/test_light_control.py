import asyncio
import time
import unittest
import uuid
from unittest.mock import Mock, AsyncMock
from dovit_bridge.web_monitor import Monitor
from dovit_bridge.light_control import LightControl, light_frame


class LightTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.monitor = Monitor()
        self.monitor.configure({'lights': {19: {'name': 'Test', 'statetype': 0}}})

    def command(self, **changes):
        return dict(dict(id=19, action='ON', confirm=True, request_id=str(uuid.uuid4())), **changes)

    async def test_simulation_and_idempotency(self):
        c = LightControl(self.monitor, simulation=True)
        raw = self.command()
        c.submit(raw)
        c.submit(raw)
        self.assertEqual(len(self.monitor.events), 1)
        self.assertEqual(self.monitor.snapshot()['commands'][0]['status'], 'observed')

    async def test_invalid_unknown_and_disconnected(self):
        c = LightControl(self.monitor, simulation=True)
        for changes in ({'id': 88}, {'action': 'DISARM'}, {'confirm': False}, {'id': True}):
            with self.assertRaises(ValueError):
                c.submit(self.command(**changes))
        with self.assertRaises(ValueError):
            LightControl(self.monitor).submit(self.command())
        self.assertEqual(len(self.monitor.events), 0)

    async def test_live_path_observation_not_send_ack(self):
        writer = Mock()
        writer.is_closing.return_value = False
        bridge = Mock(lights={19: {'statetype': 0}}, send_light=AsyncMock(return_value=True))
        bridge.dovit.writer = writer
        self.monitor.connected = True
        c = LightControl(self.monitor, asyncio.get_running_loop(), bridge)
        c.submit(self.command())
        await asyncio.sleep(.03)
        self.assertEqual(self.monitor.snapshot()['commands'][0]['status'], 'transmitted')
        self.monitor.observe(19, 0, '0')
        self.assertEqual(self.monitor.snapshot()['commands'][0]['status'], 'transmitted')
        self.monitor.observe(19, 0, '1')
        self.assertEqual(self.monitor.snapshot()['commands'][0]['status'], 'observed')
        bridge.send_light.assert_awaited_once_with(19, 'ON', expected_writer=bridge.dovit.writer)

    async def test_reconnected_writer_rejects_command(self):
        bridge = Mock(lights={19: {'statetype': 0}}, send_light=AsyncMock())
        old = Mock()
        bridge.dovit.writer = old
        self.monitor.connected = True
        c = LightControl(self.monitor, asyncio.get_running_loop(), bridge)
        c.submit(self.command())
        bridge.dovit.writer = Mock()
        await asyncio.sleep(.03)
        bridge.send_light.assert_not_awaited()
        self.assertEqual(self.monitor.snapshot()['commands'][0]['status'], 'failed')

    async def test_reconnect_during_validation_does_not_rebind_command(self):
        bridge = Mock(lights={19: {'statetype': 0}}, send_light=AsyncMock())
        bridge.dovit.writer = Mock()
        self.monitor.connected = True
        devices = self.monitor.devices

        class ReconnectingDevices(list):
            def __iter__(self):
                bridge.dovit.writer = Mock()
                return super().__iter__()

        self.monitor.devices = ReconnectingDevices(devices)
        control = LightControl(self.monitor, asyncio.get_running_loop(), bridge)
        command = control.submit(self.command())
        await asyncio.sleep(.03)
        bridge.send_light.assert_not_awaited()
        self.assertEqual(self.monitor.commands[command['request_id']]['status'], 'failed')

    async def test_busy_timeout_and_frame(self):
        c = LightControl(self.monitor, simulation=True)
        raw = self.command()
        c.submit(raw)
        record = self.monitor.commands[raw['request_id']]
        record['status'] = 'transmitted'
        with self.assertRaises(ValueError):
            c.submit(self.command(action='OFF'))
        record['started'] = time.monotonic()-13
        self.assertEqual(self.monitor.snapshot()['commands'][0]['status'], 'timeout')
        self.assertIn('<statevalue>0.0</statevalue>', light_frame(19, 0, 'OFF'))
        self.assertIn('<device id="19">', light_frame(19, 0, 'ON'))
