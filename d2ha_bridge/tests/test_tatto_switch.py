import asyncio
from dataclasses import replace
import json
from fnmatch import fnmatchcase
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
import xml.etree.ElementTree as ET

from dovit_bridge.bridge import DovitBridge
from dovit_bridge.config import Config
from dovit_bridge.device_editor import DeviceEditor
from dovit_bridge.mapping_drafts import validate_draft
from dovit_bridge.mqtt_discovery import switch_payload
from dovit_bridge.recovery import validate_recovery_document
from dovit_bridge.web_monitor import Monitor


# Synthetic endpoint fixture; IDs and names are not a recommended house mapping.
INFO = {'name': 'Example night mode', 'statetype': 0}


class TattoSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.b = b = DovitBridge.__new__(DovitBridge)
        b.cfg = Config(publish_discovery=True, frame_sep=b'\0')
        b.loop = asyncio.get_running_loop()
        b.switches = {100: dict(INFO)}
        for category in ('lights', 'shutters', 'thermostats', 'motions', 'contacts', 'alarms'):
            setattr(b, category, {})
        b.monitor = Monitor()
        b.monitor.configure({'switches': {'100': INFO}})
        b.mqtt = Mock(connected=True)
        b.mqtt.publish.return_value.rc = 0
        self.writer = Mock()
        self.writer.is_closing.return_value = False
        b.dovit = SimpleNamespace(writer=self.writer, send=AsyncMock())
        b.reload_device_maps = Mock()
        b.publish_combined_alarm_state = Mock()
        b.publish_alarm_house_discovery = Mock()
        b.seen_unknown = set()
        b.shutter_candidate_values = {}

    async def flush(self):
        for _ in range(3):
            await asyncio.sleep(0)

    def command(self, payload=b'ON', topic='dovit/switch/100/set', retain=False):
        self.b.on_message(None, None, SimpleNamespace(topic=topic, payload=payload, retain=retain))

    async def test_mqtt_commands_send_only_id_100_and_no_optimistic_state(self):
        for action, value in ((b'ON', '1.0'), (b'OFF', '0.0')):
            self.command(action)
            await self.flush()
            raw = self.b.dovit.send.call_args.args[0]
            device = ET.fromstring(raw[:-1]).find('device')
            self.assertEqual(device.attrib['id'], '100')
            self.assertEqual(device.findtext('statetype'), '0')
            self.assertEqual(device.findtext('statevalue'), value)
            self.assertIs(self.b.dovit.send.call_args.kwargs['expected_writer'], self.writer)
        self.assertEqual(self.b.dovit.send.await_count, 2)
        self.b.mqtt.publish.assert_not_called()

    async def test_retained_unknown_invalid_commands_do_not_send(self):
        self.command(retain=True)
        for payload in (b'TOGGLE', b'1', b'', b'ON\xff'):
            self.command(payload)
        self.command(topic='dovit/switch/99/set')
        self.command(topic='dovit/light/100/set')
        await self.flush()
        self.b.dovit.send.assert_not_called()

    async def test_command_does_not_cross_tcp_sessions(self):
        self.command()
        self.b.dovit.writer = Mock()
        await self.flush()
        self.b.dovit.send.assert_not_called()

    async def test_disconnected_command_is_not_replayed(self):
        self.b.dovit.writer = None
        self.command()
        self.b.dovit.writer = self.writer
        await self.flush()
        self.b.dovit.send.assert_not_called()

    async def receive(self, readings):
        frames = b''.join((f'<hidv-state><device id="{key}"><statetype>{st}</statetype>'
                           f'<statevalue>{value}</statevalue></device></hidv-state>').encode() + b'\0'
                          for key, st, value in readings)
        self.b.dovit.read = AsyncMock(side_effect=[frames, b''])
        with self.assertRaisesRegex(RuntimeError, 'closed by server'):
            await self.b.dovit_read_loop()

    async def test_received_binary_states_are_published_without_wall_light(self):
        await self.receive([(100, 0, '1.0'), (100, 0, '0.0'), (99, 0, '1.0')])
        self.assertEqual([c.args for c in self.b.mqtt.publish.call_args_list],
                         [('dovit/switch/100/state', 'ON'), ('dovit/switch/100/state', 'OFF')])
        self.assertTrue(all(c.kwargs == {'qos': 1, 'retain': True}
                            for c in self.b.mqtt.publish.call_args_list))
        self.b.dovit.send.assert_not_called()

    async def test_invalid_or_different_statetype_does_not_establish_state(self):
        await self.receive([(100, 1, '1'), (100, 0, 'NaN'), (100, 0, '.5'), (100, 0, '2')])
        self.b.mqtt.publish.assert_not_called()

    async def test_explicit_switch_is_not_automatically_reclassified_as_light(self):
        self.b.cfg = Config(enable_discovery=True, light_statetypes={0}, shutter_values={'0.0', '1.0'})
        self.b.unassigned_endpoints = set()
        with patch('dovit_bridge.bridge.save_devices') as save:
            await self.receive([(100, 0, '1')])
        save.assert_not_called()
        self.assertEqual(self.b.lights, {})

    def test_discovery_is_a_switch_with_nonoptimistic_state_and_availability(self):
        payload = switch_payload('node', 100, INFO['name'])
        self.assertEqual(payload['unique_id'], 'dovit_switch_100')
        self.assertFalse(payload['optimistic'])
        self.assertFalse(payload['retain'])
        self.assertEqual(payload['availability_mode'], 'all')
        self.b.publish_all_discovery_once()
        self.b.mqtt.publish.assert_called_once_with(
            'homeassistant/switch/dovit_switch_100/config',
            unittest.mock.ANY, retain=True)
        published = json.loads(self.b.mqtt.publish.call_args.args[1])
        self.assertEqual(published['command_topic'], 'dovit/switch/100/set')
        self.assertEqual(published['state_topic'], 'dovit/switch/100/state')

    def test_discovery_disabled_and_todo_names_are_respected(self):
        self.b.cfg = Config()
        self.b.publish_switch_discovery(100, INFO)
        self.b.cfg = Config(publish_discovery=True)
        self.b.publish_switch_discovery(100, dict(INFO, name='TODO_Night'))
        self.b.mqtt.publish.assert_not_called()

    def test_new_switch_ids_match_homekit_glob_independently_of_display_name(self):
        # Regression for HA's room/device/name generation excluding a new Tatto from HomeKit.
        for dev_id, name in ((100, 'Example switch'), (102, 'Example night mode'),
                             (106, 'Mode nuit — chambre')):
            with self.subTest(dev_id=dev_id, name=name):
                self.b.mqtt.reset_mock()
                self.b.publish_switch_discovery(dev_id, dict(INFO, name=name))
                topic, raw = self.b.mqtt.publish.call_args.args
                payload = json.loads(raw)
                entity_id = payload['default_entity_id']
                self.assertTrue(fnmatchcase(entity_id, 'switch.dovit_switch_*'))
                self.assertEqual(entity_id.split('.', 1)[1], payload['unique_id'])
                self.assertEqual(topic, 'homeassistant/switch/' + payload['unique_id'] + '/config')
                self.assertEqual(payload['name'], name)
                self.assertNotIn('object_id', payload)
                # A rename changes presentation, not MQTT identity or command/state routing.
                renamed = switch_payload(self.b.cfg.discovery_node_id, dev_id, 'Renamed')
                for field in ('default_entity_id', 'unique_id', 'command_topic', 'state_topic', 'device'):
                    self.assertEqual(payload[field], renamed[field])

    def test_switch_state_is_owned_and_eligible_for_session_replay(self):
        self.assertEqual(self.b._state_routes()['dovit/switch/100/state'],
                         ('switches', 100, 'state', 100, 0))
        self.assertEqual(self.b._removed_mapping_state_topics('switches', 100),
                         {'dovit/switch/100/state'})
        self.assertIn('dovit/switch/100/state', self.b._owned_mapping_state_topics())

    async def test_mqtt_reconnect_replays_only_evidence_from_current_dovit_session(self):
        b = self.b
        b.alarm_partition_raw_states = {}
        b.alarm_partition_triggered = set()
        b.set_dovit_connected(True)
        b.mqtt.connected = False
        b.mqtt.reset_mock()
        await self.receive([(100, 0, '1.0')])
        b.mqtt.publish.assert_not_called()
        b.mqtt.connected = True
        b.republish_session_status()
        self.assertIn(('dovit/switch/100/state', 'ON'),
                      [c.args for c in b.mqtt.publish.call_args_list])
        b.set_dovit_connected(False)
        b.mqtt.reset_mock()
        b.set_dovit_connected(True)
        self.assertNotIn(('dovit/switch/100/state', 'ON'),
                         [c.args for c in b.mqtt.publish.call_args_list])
        self.assertEqual(b._state_cache, {})

    def test_startup_loads_explicit_switch_and_monitor_route(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'devices.json'
            path.write_text(json.dumps({'switches': {'100': INFO}}))
            self.b.cfg = replace(self.b.cfg, devices_file=path)
            self.b.initialize_cover_positions = Mock()
            self.b.cover_positions = {}
            DovitBridge.reload_device_maps(self.b)
            self.assertEqual(self.b.switches, {100: INFO})
            self.assertEqual(self.b.monitor.routes['100:0'],
                             [{'uid': 'switches:100', 'role': 'state'}])
            self.assertNotIn('99:0', self.b.monitor.routes)

    def test_assignment_rejects_endpoint_collision(self):
        with self.assertRaises(ValueError):
            validate_draft(dict(category='lights', id=100, statetype=0, name='Collision'), self.b.monitor)

    def test_graphical_and_json_editor_preserve_switch_with_verified_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'devices.json'
            path.write_text('{}')
            editor = DeviceEditor(path)
            raw = dict(revision=editor.snapshot()['revision'], confirm=True,
                       device=dict(category='switches', id=100, statetype=0, name=INFO['name']))
            editor.request(raw, save=True)
            self.assertEqual(path.read_text(), '{}')
            self.assertTrue(editor.apply_pending())
            maps = validate_recovery_document(path.read_bytes())
            self.assertEqual(maps['switches']['100'], INFO)
            self.assertNotIn('99', maps['switches'])
            self.assertEqual(next((path.parent / 'dovit_device_backups').iterdir()).read_bytes(), b'{}')
            maps['switches']['100']['name'] = 'Renamed'
            editor.request(dict(operation='replace_json', revision=editor.snapshot()['revision'],
                                document=json.dumps(maps), confirm=True), save=True)
            editor.apply_pending()
            self.assertEqual(editor.snapshot()['maps']['switches']['100']['name'], 'Renamed')

    def test_delete_cleans_only_switch_discovery_and_state(self):
        self.b.cfg = Config(enable_discovery=True)
        self.b.switches = {}
        with patch('dovit_bridge.bridge.load_devices', return_value={'_removed_discovery': ['switches:100']}):
            self.b.publish_all_discovery_once()
        self.assertEqual({c.args for c in self.b.mqtt.publish.call_args_list},
                         {('homeassistant/switch/dovit_switch_100/config', ''),
                          ('dovit/switch/100/state', '')})


if __name__ == '__main__':
    unittest.main()
