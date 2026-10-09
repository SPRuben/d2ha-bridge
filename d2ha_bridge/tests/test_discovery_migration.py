import asyncio
import json
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, patch

from dovit_bridge.bridge import DovitBridge
from dovit_bridge.config import Config, load_config


class DiscoveryMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.b = b = DovitBridge.__new__(DovitBridge)
        b.cfg = Config(publish_discovery=True, light_statetypes={0},
                       shutter_values={'0.0', '1.0', '2.0'})
        b.loop = asyncio.get_running_loop()
        b.mqtt = Mock(connected=True)
        b.mqtt.publish.return_value.rc = 0
        b.lights = {19: {'name': 'Kitchen', 'statetype': 0}}
        b.shutters = {20: {'name': 'Window', 'statetype': 3, 'travel_time': 10}}
        b.motions = {30: {'name': 'Hall motion', 'statetype': 4}}
        b.contacts = {31: {'name': 'Door', 'statetype': 5}}
        b.alarms = {87: {'name': 'House motion', 'state_statetype': 1,
                         'text_statetype': 10, 'trigger_statetype': 13}}
        b.thermostats = {44: {'name': 'Heating', 'current': {'id': 42, 'statetype': 6},
                             'target': {'statetype': 1}, 'mode': {'id': 46, 'statetype': 7}}}
        b.reload_device_maps = Mock()
        b.publish_combined_alarm_state = Mock()
        b.republish_session_status = Mock()
        b.monitor = Mock()
        b.seen_unknown = set()
        b.shutter_candidate_values = {}
        b._observed_endpoint_limit_warned = False

    def payloads(self):
        return {entry.args[0]: json.loads(entry.args[1])
                for entry in self.b.mqtt.publish.call_args_list if entry.args[1]}

    async def test_all_eight_categories_keep_legacy_ids_topics_and_payloads(self):
        b = self.b
        with patch('dovit_bridge.bridge.load_devices', side_effect=AssertionError('disk read')):
            b.publish_all_discovery_once('migration')
        migration = self.payloads()
        expected = {
            'light': 'dovit_light_19', 'cover': 'dovit_cover_20',
            'binary_sensor': ('dovit_motion_30', 'dovit_contact_31'),
            'sensor': ('dovit_alarm_state_87', 'dovit_alarm_text_87'),
            'alarm_control_panel': 'dovit_alarm_house', 'climate': 'dovit_climate_44',
        }
        for component, ids in expected.items():
            for uid in (ids if isinstance(ids, tuple) else (ids,)):
                payload = migration[f'homeassistant/{component}/{uid}/config']
                self.assertEqual(payload['unique_id'], uid)
                self.assertEqual(payload['object_id'], uid)
        self.assertEqual(len(migration), 8)
        b.reload_device_maps.assert_not_called()
        b.cfg = replace(b.cfg, enable_discovery=True, publish_discovery=False)
        b.mqtt.reset_mock()
        with patch('dovit_bridge.bridge.load_devices', return_value={}):
            b.publish_all_discovery_once('legacy')
        b.reload_device_maps.assert_called_once()
        self.assertEqual(self.payloads(), migration)

    async def test_publish_only_ignores_todo_names_and_disk_cleanup(self):
        b = self.b
        b.cfg = replace(b.cfg, publish_todo_entities=True)
        b.lights.update({98: {'name': 'TODO_Light_98', 'statetype': 0},
                         99: {'name': '', 'statetype': 0}})
        with patch('dovit_bridge.bridge.load_devices', side_effect=AssertionError('tombstone read')), \
                patch('dovit_bridge.bridge.save_devices') as save, \
                patch('dovit_bridge.bridge.save_cover_positions') as positions:
            b.publish_all_discovery_once()
            save.assert_not_called()
            positions.assert_not_called()
        self.assertEqual(len(self.payloads()), 8)
        self.assertFalse(any(not c.args[1] for c in b.mqtt.publish.call_args_list))
        b.reload_device_maps.assert_not_called()
        b.mqtt.reset_mock()
        b.publish_light_discovery(98, b.lights[98])
        b.publish_light_discovery(99, b.lights[99])
        b.mqtt.publish.assert_not_called()

    async def test_connect_and_tick_publish_with_new_flag_only(self):
        b = self.b
        b.publish_all_discovery_once = Mock()
        b.on_connect(Mock(), None, {}, 0)
        b.publish_all_discovery_once.assert_not_called()
        await asyncio.sleep(0)
        b.publish_all_discovery_once.assert_called_once_with(reason='connect')
        b.publish_all_discovery_once.reset_mock()
        calls = 0
        async def tick(seconds):
            nonlocal calls
            self.assertEqual(seconds, 300)
            calls += 1
            if calls == 2:
                raise asyncio.CancelledError()
        with patch('dovit_bridge.bridge.asyncio.sleep', side_effect=tick):
            with self.assertRaises(asyncio.CancelledError):
                await b.discovery_republish_loop()
        b.publish_all_discovery_once.assert_called_once_with(reason='tick_300s')

    async def test_both_flags_disabled_and_legacy_fixture_fallback(self):
        b = self.b
        b.cfg = replace(b.cfg, publish_discovery=False)
        b.publish_all_discovery_once()
        await b.discovery_republish_loop()
        b.mqtt.publish.assert_not_called()
        from types import SimpleNamespace
        b.cfg = SimpleNamespace(enable_discovery=True, discovery_prefix='homeassistant',
                                discovery_node_id='dovit_bridge')
        b.publish_light_discovery(19, b.lights[19])
        self.assertEqual(b.mqtt.publish.call_args.args[0], 'homeassistant/light/dovit_light_19/config')

    async def test_publish_only_actual_unknown_receive_never_persists_candidates(self):
        b = self.b
        data = b''.join((f'<hidv-state><device id="{dev}"><statetype>{st}</statetype>'
                         f'<statevalue>{value}</statevalue></device></hidv-state>').encode() + b'\0'
                        for dev, st, value in [(999, 0, '1'), (998, 9, '1.0'), (998, 9, '2.0')])
        b.dovit = Mock()
        b.dovit.read = AsyncMock(side_effect=[data, RuntimeError('fixture end')])
        with patch('dovit_bridge.bridge.load_devices', side_effect=AssertionError('candidate read')), \
                patch('dovit_bridge.bridge.save_devices') as save:
            with self.assertRaisesRegex(RuntimeError, 'fixture end'):
                await b.dovit_read_loop()
            save.assert_not_called()
        self.assertNotIn(999, b.lights)
        self.assertNotIn(998, b.shutters)
        self.assertEqual(b.shutter_candidate_values, {})

    async def test_publish_only_does_not_change_normal_startup_initialization(self):
        maps = (self.b.lights, self.b.shutters, self.b.thermostats,
                self.b.motions, self.b.contacts, self.b.alarms)
        cfg = replace(self.b.cfg, cover_position_mode='timed')
        with patch('dovit_bridge.bridge.load_devices', return_value={}), \
                patch('dovit_bridge.bridge.reload_maps', return_value=maps), \
                patch('dovit_bridge.bridge.load_cover_positions', return_value={}), \
                patch('dovit_bridge.bridge.save_cover_positions') as save, \
                patch.object(DovitBridge, 'initialize_cover_positions') as initialize, \
                patch('dovit_bridge.bridge.MqttWrapper'), patch('dovit_bridge.bridge.DovitTcp'), \
                patch('dovit_bridge.bridge.Monitor'):
            DovitBridge(cfg)
            initialize.assert_called_once()
            save.assert_not_called()

    async def test_config_defaults_and_option_independent_in_both_modes(self):
        self.assertFalse(Config().publish_discovery)
        for addon in (False, True):
            for opts, expected in (({}, False), ({'publish_discovery': True}, True),
                                   ({'enable_discovery': True}, False)):
                with patch('dovit_bridge.config.os.path.exists', return_value=addon), \
                        patch('dovit_bridge.config.load_addon_options', return_value=opts):
                    cfg = load_config()
                self.assertEqual(cfg.publish_discovery, expected)
                self.assertEqual(cfg.enable_discovery, opts.get('enable_discovery', False))
