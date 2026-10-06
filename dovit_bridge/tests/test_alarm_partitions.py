import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock
from dovit_bridge.alarm_partitions import partition_ids
from dovit_bridge.device_editor import DeviceEditor
from dovit_bridge.bridge import DovitBridge
from dovit_bridge.topics import ALARM_HOUSE_CMD_TOPIC


class AlarmPartitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'devices.json'
        self.path.write_text(json.dumps({'alarms': {'87': {'name': 'Motion', 'state_statetype': 1,
                                                           'text_statetype': 10, 'trigger_statetype': 13}}}))
        self.editor = DeviceEditor(self.path)

    def request(self, **changes):
        device = dict(category='alarm_contact', id=188, name='Contacts', state_statetype=1,
                      text_statetype=10, trigger_statetype=13, command_statetype=0)
        device.update(changes)
        return dict(device=device, revision=self.editor.snapshot()['revision'], confirm=True)

    def test_legacy_occupancy_and_unique_role(self):
        self.assertEqual(self.editor.snapshot()['alarm_roles'], {'motion': 87})
        with self.assertRaisesRegex(ValueError, 'alarm_role_used'):
            self.editor.request(self.request(category='alarm_motion'), True)
        self.assertFalse(self.editor.pending.exists())

    def test_stage_apply_and_backup_new_partition(self):
        before = self.path.read_bytes()
        self.editor.request(self.request(), True)
        self.assertEqual(self.path.read_bytes(), before)
        self.editor.apply_pending()
        maps = json.loads(self.path.read_bytes())
        self.assertEqual(partition_ids(maps['alarms']), {'motion': 87, 'contact': 188})
        self.assertEqual(maps['alarms']['188']['command_statetype'], 0)
        self.assertEqual(next((self.path.parent/'dovit_device_backups').glob('*.json')).read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'alarm_role_used'):
            self.editor.request(self.request(id=189), True)

    def test_collisions_missing_fields_and_existing_partition_protection(self):
        for changes in [dict(id=87), dict(command_statetype=1), dict(text_statetype=None), dict(id=39, command_statetype=111)]:
            with self.assertRaises(ValueError):
                self.editor.request(self.request(**changes), True)
        raw = self.request()
        raw['source'] = 'alarms:87'
        with self.assertRaises(ValueError):
            self.editor.validate(raw)
        with self.assertRaises(ValueError):
            partition_ids({87: {}, 90: {'partition_role': 'motion'}})

    def test_bridge_uses_configured_ids_for_commands(self):
        b = DovitBridge.__new__(DovitBridge)
        b.alarms = {187: {'partition_role': 'motion', 'command_statetype': 2},
                    188: {'partition_role': 'contact', 'command_statetype': 3}}
        b.loop = Mock()
        writer = Mock()
        writer.is_closing.return_value = False
        b.dovit = SimpleNamespace(writer=writer)
        b.loop.call_soon_threadsafe.side_effect = lambda callback: callback()
        b.loop.create_task.side_effect = asyncio.run
        b.send_frame = AsyncMock(return_value=True)
        b.on_message(None, None, SimpleNamespace(topic=ALARM_HOUSE_CMD_TOPIC, payload=b'ARM_HOME'))
        frames = [call.args[0] for call in b.send_frame.call_args_list]
        self.assertIn('<device id="187"><statetype>2</statetype><statevalue>0</statevalue>', frames[0])
        self.assertIn('<device id="188"><statetype>3</statetype><statevalue>1</statevalue>', frames[1])

    def test_bridge_aggregates_configured_roles(self):
        b = DovitBridge.__new__(DovitBridge)
        b.alarms = {187: {'partition_role': 'motion'}, 188: {'partition_role': 'contact'}}
        b.alarm_partition_triggered = set()
        b.alarm_partition_raw_states = {187: 0, 188: 1}
        b.pending_alarm_house_state = None
        b.mqtt = Mock()
        b.publish_combined_alarm_state()
        self.assertEqual(b.mqtt.publish.call_args.args[1], 'armed_home')

    def test_legacy_commands_and_missing_role_guard(self):
        b = DovitBridge.__new__(DovitBridge)
        b.alarms = {87: {}, 88: {}}
        b.loop = Mock()
        writer = Mock()
        writer.is_closing.return_value = False
        b.dovit = SimpleNamespace(writer=writer)
        b.loop.call_soon_threadsafe.side_effect = lambda callback: callback()
        b.loop.create_task.side_effect = asyncio.run
        b.send_frame = AsyncMock(return_value=True)
        b.on_message(None, None, SimpleNamespace(topic=ALARM_HOUSE_CMD_TOPIC, payload=b'ARM_AWAY'))
        self.assertEqual(b.send_frame.await_count, 2)
        self.assertIn('<device id="87"><statetype>0</statetype><statevalue>1</statevalue>', b.send_frame.call_args_list[0].args[0])
        b.alarms = {87: {}}
        with patch('dovit_bridge.bridge.asyncio.run_coroutine_threadsafe') as send, self.assertLogs(level='ERROR'):
            b.on_message(None, None, SimpleNamespace(topic=ALARM_HOUSE_CMD_TOPIC, payload=b'ARM_AWAY'))
        send.assert_not_called()
