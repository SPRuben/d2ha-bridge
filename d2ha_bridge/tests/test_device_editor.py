import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from dovit_bridge.device_editor import DeviceEditor
from dovit_bridge.web_monitor import Monitor, make_server


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'devices.json'
        self.maps = {'lights': {'19': {'name': 'Office', 'statetype': 0, 'extra': 'keep'}},
                     'contacts': {'20': {'name': 'Window', 'statetype': 1, 'device_class': 'window'}},
                     'alarms': {'87': {'name': 'Alarm', 'state_statetype': 0}}}
        self.path.write_text(json.dumps(self.maps))
        self.editor = DeviceEditor(self.path)

    def payload(self, **changes):
        raw = dict(source='lights:19', revision=self.editor.snapshot()['revision'],
                   device=dict(category='lights', id=19, statetype=0, name='New name'), confirm=True)
        raw.update(changes)
        return raw

    def test_rename_staged_backup_and_apply(self):
        before = self.path.read_bytes()
        raw = self.payload()
        self.editor.request(raw, save=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.editor.apply_pending())
        after = json.loads(self.path.read_bytes())
        self.assertEqual(after['lights']['19'], dict(name='New name', statetype=0, extra='keep'))
        self.assertEqual(after['alarms'], self.maps['alarms'])
        self.assertEqual(next((self.path.parent / 'dovit_device_backups').iterdir()).read_bytes(), before)
        self.assertFalse(self.editor.snapshot()['pending'])
        self.assertFalse(self.editor.apply_pending())

    def test_identity_change_requires_confirmation(self):
        raw = self.payload(device=dict(category='motions', id=19, statetype=0, name='Motion'))
        self.assertTrue(self.editor.request(raw)['identity_changed'])
        with self.assertRaisesRegex(ValueError, 'edit_identity'):
            self.editor.request(raw, save=True)
        raw['confirm_identity'] = True
        self.editor.request(raw, save=True)
        self.editor.apply_pending()
        result = json.loads(self.path.read_bytes())
        self.assertNotIn('19', result['lights'])
        self.assertEqual(result['_removed_discovery'], ['lights:19'])
        self.assertEqual(result['motions']['19']['name'], 'Motion')

    def test_other_endpoint_conflicts_and_alarm_protection(self):
        for change in [dict(source='alarms:87'),
                       dict(device=dict(category='lights', id=20, statetype=1, name='Taken')),
                       dict(device=dict(category='alarms', id=19, statetype=0, name='Alarm'))]:
            with self.assertRaises(ValueError):
                self.editor.request(self.payload(**change), save=True)
        self.assertFalse(self.editor.pending.exists())

    def test_revision_conflict_does_not_overwrite_external_edits(self):
        raw = self.payload()
        self.editor.request(raw, save=True)
        self.path.write_text(json.dumps(dict(self.maps, changed=True)))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'edit_stale'):
            self.editor.apply_pending()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.editor.pending.exists())

    def test_only_one_pending_and_cancel(self):
        raw = self.payload()
        self.editor.request(raw, save=True)
        with self.assertRaisesRegex(ValueError, 'edit_pending'):
            self.editor.request(raw, save=True)
        self.editor.cancel()
        self.assertFalse(self.editor.pending.exists())
        self.assertEqual(json.loads(self.path.read_bytes()), self.maps)

    def test_atomic_replace_failure_preserves_original(self):
        self.editor.request(self.payload(), save=True)
        before = self.path.read_bytes()
        with patch('dovit_bridge.device_editor.os.replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                self.editor.apply_pending()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.editor.pending.exists())

    def test_new_mapping_and_thermostat_fields(self):
        raw = self.payload(source=None, device=dict(category='thermostats', name='Room', id=44, statetype=1,
            current_id=42, current_statetype=1, mode_id=46, mode_statetype=0,
            min_temp=16, max_temp=26, temp_step=.5))
        self.editor.request(raw, save=True)
        self.editor.apply_pending()
        self.assertEqual(json.loads(self.path.read_bytes())['thermostats']['44']['current']['id'], 42)

    def test_http_requires_token_and_confirmation(self):
        monitor = Monitor()
        monitor.device_editor = self.editor
        server = make_server(monitor, '127.0.0.1', 0, '127.0.0.1')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def request(action, token, payload):
                return urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/devices/{action}',
                    data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'X-Dovit-Token': token}))
            with self.assertRaises(HTTPError) as error:
                request('save', 'wrong', self.payload())
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            with request('save', monitor.session, self.payload()) as response:
                self.assertTrue(json.load(response)['pending'])
            with self.assertRaises(HTTPError) as error:
                request('cancel', monitor.session, {})
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
            with request('cancel', monitor.session, {'confirm': True}) as response:
                self.assertFalse(json.load(response)['pending'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_cover_calibration_and_separate_command_statetype(self):
        self.maps['shutters'] = {'21': dict(name='Cover', statetype=1, command_statetype=0,
                                          travel_time_up=27, position_mode='timed')}
        self.path.write_text(json.dumps(self.maps))
        raw = self.payload(source='shutters:21', device=dict(category='shutters', name='Rename', id=21,
                                                           statetype=1, command_statetype=0))
        result = self.editor.request(raw, save=True)
        self.assertNotIn('covers_reset_to_legacy', result['draft'])
        self.editor.apply_pending()
        info = json.loads(self.path.read_bytes())['shutters']['21']
        self.assertEqual(info['position_mode'], 'timed')
        self.assertEqual(info['travel_time_up'], 27)
        raw = self.payload(source='shutters:21', device=dict(category='shutters', name='Remap', id=21,
                                                           statetype=2, command_statetype=3))
        result = self.editor.request(raw, save=True)
        self.assertEqual(result['draft']['covers_reset_to_legacy'], ['shutters:21'])
        self.editor.apply_pending()
        info = json.loads(self.path.read_bytes())['shutters']['21']
        self.assertEqual(info['position_mode'], 'legacy')
        self.assertEqual(info['command_statetype'], 3)
        raw = self.payload(source='shutters:21', device=dict(category='shutters', name='Already legacy', id=21,
                                                           statetype=2, command_statetype=4))
        result = self.editor.request(raw)
        self.assertNotIn('covers_reset_to_legacy', result['draft'])
        with self.assertRaises(ValueError):
            self.editor.request(self.payload(source=None, device=dict(category='lights', name='Conflict', id=21, statetype=3)))

    def test_corrupt_pending_is_rejected(self):
        self.editor.pending.write_text('[]')
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.editor.apply_pending()
        self.assertEqual(self.path.read_bytes(), before)

    def test_delete_requires_confirmation_and_is_backed_up(self):
        before = self.path.read_bytes()
        raw = self.payload(operation='delete')
        del raw['device']
        self.assertTrue(self.editor.request(raw)['identity_changed'])
        with self.assertRaisesRegex(ValueError, 'edit_identity'):
            self.editor.request(raw, save=True)
        raw['confirm_identity'] = True
        self.editor.request(raw, save=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.editor.apply_pending()
        result = json.loads(self.path.read_bytes())
        self.assertNotIn('19', result['lights'])
        self.assertEqual(result['_removed_discovery'], ['lights:19'])
        self.assertEqual(result['_unassigned_endpoints'], ['19:0'])
        self.assertEqual(result['contacts'], self.maps['contacts'])
        self.assertEqual(next((self.path.parent / 'dovit_device_backups').iterdir()).read_bytes(), before)
        # Manual reassignment remains possible; suppression affects only heuristics.
        self.editor.request(self.payload(source=None), save=True)
        self.editor.apply_pending()
        self.assertIn('19', json.loads(self.path.read_bytes())['lights'])

    def test_delete_protects_alarms_unknown_sources_and_revision(self):
        for source in ('alarms:87', 'lights:999', None):
            with self.assertRaises(ValueError):
                self.editor.request(self.payload(source=source, operation='delete', confirm_identity=True), save=True)
        raw = self.payload(operation='delete', confirm_identity=True)
        self.editor.request(raw, save=True)
        self.path.write_text(json.dumps(dict(self.maps, external=True)))
        with self.assertRaisesRegex(ValueError, 'edit_stale'):
            self.editor.apply_pending()
        self.editor.cancel()
        self.assertIn('19', json.loads(self.path.read_bytes())['lights'])

    def test_retired_discovery_retries_but_preserves_reused_identity(self):
        from dovit_bridge.bridge import DovitBridge
        bridge = DovitBridge.__new__(DovitBridge)
        bridge.cfg = SimpleNamespace(enable_discovery=True, devices_file=self.path,
                                     discovery_prefix='homeassistant', publish_todo_entities=False)
        bridge.mqtt = Mock(connected=True)
        bridge.mqtt.publish.return_value.rc = 0
        bridge.reload_device_maps = Mock()
        bridge.publish_alarm_house_discovery = Mock()
        bridge.publish_combined_alarm_state = Mock()
        bridge.publish_light_discovery = Mock()
        for category in ('lights', 'shutters', 'motions', 'contacts', 'thermostats', 'alarms'):
            setattr(bridge, category, {})
        self.path.write_text(json.dumps(dict(self.maps, _removed_discovery=['lights:19'])))
        bridge.publish_all_discovery_once()
        bridge.publish_all_discovery_once()
        self.assertEqual(bridge.mqtt.publish.call_count, 4)
        for topic in ('homeassistant/light/dovit_light_19/config', 'dovit/light/19/state'):
            matching = [entry for entry in bridge.mqtt.publish.call_args_list if entry.args[0] == topic]
            self.assertEqual(len(matching), 2)
            for entry in matching:
                self.assertEqual(entry.args, (topic, ''))
                self.assertEqual(entry.kwargs, {'retain': True, 'qos': 1})
        self.assertEqual(json.loads(self.path.read_bytes())['_removed_discovery'], ['lights:19'])
        bridge.lights[19] = dict(name='Reused', statetype=0)
        bridge.mqtt.publish.reset_mock()
        bridge.publish_all_discovery_once()
        bridge.mqtt.publish.assert_not_called()
