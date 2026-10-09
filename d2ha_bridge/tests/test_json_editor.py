from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from dovit_bridge.device_editor import DeviceEditor
from dovit_bridge.json_editor import decode_document, validate_document
from dovit_bridge.web_monitor import Monitor, make_server


class JsonEditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'devices.json'
        self.maps = {'lights': {'19': {'name': 'Office', 'statetype': 0}},
                     'shutters': {'20': {'name': 'Cover', 'statetype': 1, 'command_statetype': 0,
                                        'position_mode': 'timed', 'travel_time_open': 27}},
                     'thermostats': {'44': {'name': 'Room', 'target': {'statetype': 1},
                                           'current': {'id': 42, 'statetype': 1},
                                           'mode': {'id': 46, 'statetype': 0},
                                           'min_temp': 16, 'max_temp': 26, 'temp_step': .5}},
                     'alarms': {'87': {'name': 'Alarm', 'state_statetype': 1}}}
        self.path.write_text(json.dumps(self.maps), encoding='utf-8')
        self.editor = DeviceEditor(self.path)

    def payload(self, maps):
        return dict(operation='replace_json', document=json.dumps(maps), revision=self.editor.snapshot()['revision'], confirm=True)

    def test_read_stage_confirm_backup_apply(self):
        before = self.path.read_bytes()
        snapshot = self.editor.snapshot()
        self.assertEqual(snapshot['document'], before.decode())
        updated = deepcopy(self.maps)
        updated['lights']['19']['name'] = 'Changed'
        payload = self.payload(updated)
        preview = self.editor.request(payload)
        self.assertEqual(preview['draft']['changed'], ['lights:19'])
        self.assertEqual(preview['draft']['changed_entries'], [
            {'uid': 'lights:19', 'category': 'lights', 'device_id': '19', 'name': 'Changed'}])
        self.assertEqual(preview['draft']['removed_entries'], [])
        with self.assertRaisesRegex(ValueError, 'edit_confirm'):
            self.editor.request(dict(payload, confirm=False), True)
        self.editor.request(payload, True)
        self.assertEqual(before, self.path.read_bytes())
        self.editor.apply_pending()
        self.assertEqual(json.loads(self.path.read_bytes()), updated)
        self.assertEqual(next((self.path.parent/'dovit_device_backups').glob('*.json')).read_bytes(), before)

    def test_deletions_need_identity_confirmation_and_cleanup(self):
        updated = deepcopy(self.maps)
        del updated['lights']['19']
        payload = self.payload(updated)
        preview = self.editor.request(payload)
        self.assertEqual(preview['draft']['removed_entries'], [
            {'uid': 'lights:19', 'category': 'lights', 'device_id': '19', 'name': 'Office'}])
        self.assertTrue(preview['identity_changed'])
        with self.assertRaisesRegex(ValueError, 'edit_identity'):
            self.editor.request(payload, True)
        self.editor.request(dict(payload, confirm_identity=True), True)
        self.editor.apply_pending()
        result = json.loads(self.path.read_bytes())
        self.assertIn('lights:19', result['_removed_discovery'])
        self.assertIn('19:0', result['_unassigned_endpoints'])

    def test_summary_lists_only_validated_changed_and_previous_removed_names(self):
        before = deepcopy(self.maps)
        updated = deepcopy(self.maps)
        name = 'New $& {entry} <img src=x>'
        updated['lights']['19']['name'] = '  Changed office  '
        updated['lights']['22'] = {'name': name, 'statetype': 0}
        updated['motions'] = {'33': {'name': 'Hall', 'statetype': 0}}
        del updated['shutters']['20']
        result, summary, identity = validate_document(json.dumps(updated), self.maps)
        self.assertEqual(summary['changed'], ['lights:19', 'lights:22', 'motions:33'])
        self.assertEqual(summary['removed'], ['shutters:20'])
        self.assertEqual(summary['changed_entries'], [
            {'uid': 'lights:19', 'category': 'lights', 'device_id': '19', 'name': 'Changed office'},
            {'uid': 'lights:22', 'category': 'lights', 'device_id': '22', 'name': name},
            {'uid': 'motions:33', 'category': 'motions', 'device_id': '33', 'name': 'Hall'}])
        self.assertEqual(summary['removed_entries'], [
            {'uid': 'shutters:20', 'category': 'shutters', 'device_id': '20', 'name': 'Cover'}])
        self.assertTrue(identity)
        self.assertEqual(self.maps, before, 'The active map remains untouched by review')
        self.assertEqual(result['lights'], updated['lights'], 'Review metadata does not change serialized names')
        self.assertNotIn('changed_entries', result)
        self.assertNotIn('removed_entries', result)
        self.assertIn('20:0', result['_unassigned_endpoints'])
        self.assertIn('20:1', result['_unassigned_endpoints'])

    def test_noop_summary_has_empty_metadata(self):
        result, summary, identity = validate_document(json.dumps(self.maps), self.maps)
        self.assertEqual(result, self.maps)
        self.assertEqual(summary, dict(changed=[], removed=[], changed_entries=[], removed_entries=[],
                                       covers_reset_to_legacy=[]))
        self.assertFalse(identity)

    def test_removed_legacy_entry_without_name_uses_only_its_identity(self):
        current = deepcopy(self.maps)
        del current['lights']['19']['name']
        updated = deepcopy(current)
        del updated['lights']['19']
        _, summary, identity = validate_document(json.dumps(updated), current)
        self.assertEqual(summary['removed_entries'], [
            {'uid': 'lights:19', 'category': 'lights', 'device_id': '19'}])
        self.assertTrue(identity)

    def test_invalid_name_or_injected_summary_never_produces_a_review(self):
        before = self.path.read_bytes()
        for name in ('', True, {'name': 'Not a name'}, 'Bad\nname'):
            updated = deepcopy(self.maps)
            updated['lights']['19']['name'] = name
            with self.assertRaises(ValueError):
                self.editor.request(self.payload(updated))
        for field in ('changed_entries', 'removed_entries'):
            updated = deepcopy(self.maps)
            updated[field] = [{'uid': 'alarms:87', 'name': 'Injected'}]
            with self.assertRaisesRegex(ValueError, 'json_protected'):
                self.editor.request(self.payload(updated))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.editor.pending.exists())

    def test_stale_external_edits_and_pending_graphical_conflict(self):
        payload = self.payload(self.maps)
        self.path.write_text(json.dumps(self.maps, indent=2))
        with self.assertRaisesRegex(ValueError, 'edit_stale'):
            self.editor.request(payload, True)
        self.editor.request(self.payload(self.maps), True)
        with self.assertRaisesRegex(ValueError, 'edit_pending'):
            self.editor.request({'device': {}})
        self.path.write_text(json.dumps(self.maps, indent=3))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'edit_stale'):
            self.editor.apply_pending()
        self.assertEqual(before, self.path.read_bytes())
        self.editor.cancel()

    def test_syntax_duplicates_nonfinite_and_size(self):
        for text in ('{', '[]', '{"lights":{},"lights":{}}', '{"x":NaN}', '{"x":1e999}', ' '*262145):
            with self.assertRaises(ValueError):
                decode_document(text)

    def test_protected_alarm_metadata_calibration(self):
        for mutate in [lambda m: m['alarms'].clear(), lambda m: m['alarms']['87'].update(name='Changed alarm'),
                       lambda m: m.update(_removed_discovery=[]),
                       lambda m: m['shutters']['20'].update(travel_time_open=5),
                       lambda m: m['lights']['19'].update(unrecognized=True)]:
            updated = deepcopy(self.maps)
            mutate(updated)
            with self.assertRaisesRegex(ValueError, 'json_protected'):
                validate_document(json.dumps(updated), self.maps)

    def test_endpoint_types_collisions_and_clock(self):
        for update in [{'statetype': True}, {'statetype': False}, {'statetype': 0.0}, {'statetype': -1}, {'name': ''}]:
            maps = deepcopy(self.maps)
            maps['lights']['19'].update(update)
            with self.assertRaises(ValueError):
                validate_document(json.dumps(maps), self.maps)
        for key, st in [('39', 111), ('20', 0), ('44', 1), ('019', 0)]:
            maps = deepcopy(self.maps)
            maps['lights'][key] = {'name': 'Collision', 'statetype': st}
            with self.assertRaises(ValueError):
                validate_document(json.dumps(maps), self.maps)

    def test_malformed_nested_and_thermostat_step(self):
        for part in ('target', 'current', 'mode'):
            maps = deepcopy(self.maps)
            maps['thermostats']['44'][part] = 'bad'
            with self.assertRaises(ValueError):
                validate_document(json.dumps(maps), self.maps)
        maps = deepcopy(self.maps)
        maps['thermostats']['44']['temp_step'] = 0
        with self.assertRaises(ValueError):
            validate_document(json.dumps(maps), self.maps)
        maps['thermostats']['44']['temp_step'] = .5
        maps['thermostats']['44']['target']['id'] = 45
        with self.assertRaisesRegex(ValueError, 'json_target_id'):
            validate_document(json.dumps(maps), self.maps)

    def test_changed_cover_endpoint_disables_timed_mode(self):
        maps = deepcopy(self.maps)
        maps['shutters']['20']['command_statetype'] = 3
        updated, _, _ = validate_document(json.dumps(maps), self.maps)
        self.assertEqual(updated['shutters']['20']['position_mode'], 'legacy')
        self.assertEqual(updated['shutters']['20']['travel_time_open'], 27)

    def test_empty_public_seed_and_synthetic_map_rename_roundtrip(self):
        seed = json.loads((Path(__file__).parents[1]/'dovit_devices.json').read_bytes())
        self.assertEqual(set(seed), {'lights', 'switches', 'shutters', 'thermostats', 'motions', 'contacts', 'alarms'})
        self.assertTrue(all(value == {} for value in seed.values()))
        maps = deepcopy(self.maps)
        maps.update(switches={'100': {'name': 'Synthetic switch', 'statetype': 0}},
                    motions={'77': {'name': 'Synthetic motion', 'statetype': 0}},
                    contacts={'124': {'name': 'Synthetic contact', 'statetype': 0, 'device_class': 'door'}})
        updated = deepcopy(maps)
        # Alarm edits have a separate protected workflow; preserve this fixture.
        for category in ('lights', 'switches', 'shutters', 'thermostats', 'motions', 'contacts'):
            key = next(iter(updated[category]))
            updated[category][key]['name'] += ' Test'
        result, _, _ = validate_document(json.dumps(updated), maps)
        self.assertEqual(result, updated)

    def test_http_large_document_auth_and_asset(self):
        monitor = Monitor()
        monitor.device_editor = self.editor
        server = make_server(monitor, '127.0.0.1', 0, '127.0.0.1')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/json-editor.js') as response:
                self.assertEqual(response.status, 200)
            with urlopen(base+'/api/devices') as response:
                self.assertEqual(json.load(response)['document'], self.path.read_text())
            payload = self.payload(self.maps)
            payload['document'] += ' '*9000
            request = Request(base+'/api/devices/validate', data=json.dumps(payload).encode(),
                              headers={'Content-Type': 'application/json'})
            with self.assertRaises(HTTPError) as raised:
                urlopen(request)
            self.assertEqual(raised.exception.code, 403)
            raised.exception.close()
            request.add_header('X-Dovit-Token', monitor.session)
            with urlopen(request) as response:
                self.assertFalse(json.load(response)['pending'])
            self.assertFalse(self.editor.pending.exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
