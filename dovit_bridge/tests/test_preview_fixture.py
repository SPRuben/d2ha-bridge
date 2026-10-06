import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch


class PreviewFixtureTests(unittest.TestCase):
    def test_restart_preserves_saved_settings_in_a_disposable_copy(self):
        from preview_monitor import create_preview
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            original, source = create_preview()
            resumed = None
            try:
                settings = original.setup_config.snapshot()
                settings['settings']['dovit_host'] = 'synthetic-dovit.invalid'
                settings['settings']['mqtt_host'] = 'synthetic-mqtt.invalid'
                settings['settings']['publish_discovery'] = True
                original.setup_config.save(dict(revision=settings['revision'],
                                                settings=settings['settings'],
                                                confirm=True, mqtt_pass='synthetic-secret'))
                maps = json.loads(original.device_editor.path.read_bytes())
                maps['lights']['19']['name'] = 'Saved synthetic name'
                original.device_editor.path.write_text(json.dumps(maps), encoding='utf-8')
                before = {file.name: file.read_bytes() for file in Path(source.name).iterdir()}
                monitor, resumed = create_preview(source.name)
                restored = monitor.setup_config.snapshot()
                self.assertEqual(restored['settings'], settings['settings'])
                self.assertFalse(restored['pending'], 'Saved settings are loaded at manual preview restart')
                self.assertTrue(restored['simulation'])
                self.assertEqual(monitor.setup_config.cfg.mqtt_pass, 'synthetic-secret')
                self.assertNotIn('mqtt_pass', restored)
                self.assertFalse(restored['automatic_discovery'])
                self.assertTrue(monitor.snapshot()['inventory_configured'])
                self.assertIsNone(monitor.device_control.bridge)
                self.assertIsNone(monitor.light_control.bridge)
                self.assertNotEqual(monitor.device_editor.path.parent, Path(source.name))
                self.assertEqual(monitor.setup_config.path.read_bytes(), before['setup.json'])
                self.assertEqual(monitor.device_editor.path.read_bytes(), before['devices.json'])
                self.assertEqual(next(device['name'] for device in monitor.snapshot()['devices']
                                      if device['uid'] == 'lights:19'), 'Saved synthetic name')
                monitor.device_control.submit(dict(category='thermostats', id=44,
                                                   action='TEMPERATURE', value=23.0,
                                                   confirm=True, request_id=str(uuid.uuid4())))
                monitor.device_control.submit(dict(category='shutters', id=20,
                                                   action='STOP', confirm=True,
                                                   request_id=str(uuid.uuid4())))
                states = {state['key']: state for state in monitor.snapshot()['states']}
                self.assertEqual(float(states['44:1']['value']), 23.0)
                self.assertEqual(float(states['20:1']['value']), 0.0)
                monitor.setup_config.save(dict(revision=restored['revision'],
                                               settings=restored['settings'], confirm=True,
                                               mqtt_pass='other-synthetic-secret'))
                self.assertEqual({file.name: file.read_bytes() for file in Path(source.name).iterdir()}, before)
            finally:
                if resumed is not None:
                    resumed.cleanup()
                source.cleanup()

    def test_resume_refuses_missing_or_invalid_saved_maps(self):
        from preview_monitor import create_preview
        with tempfile.TemporaryDirectory() as source:
            with self.assertRaises(FileNotFoundError):
                create_preview(source)
            (Path(source) / 'devices.json').write_bytes(b'{ invalid synthetic maps')
            with self.assertRaises(ValueError):
                create_preview(source)

    def test_recovery_preview_never_constructs_device_controls(self):
        from preview_monitor import create_recovery_preview
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            monitor, temporary = create_recovery_preview()
            try:
                status = monitor.recovery.status()
                self.assertEqual(status['current']['state'], 'invalid')
                self.assertEqual({b['state'] for b in status['backups']}, {'valid', 'invalid'})
                self.assertIsNone(monitor.light_control)
                self.assertIsNone(monitor.device_control)
                self.assertIsNone(monitor.device_editor)
                self.assertFalse(monitor.connected)
                self.assertEqual(monitor.recovery.path.parent, Path(temporary.name))
            finally:
                temporary.cleanup()

    def test_import_does_not_start_a_server(self):
        with patch('dovit_bridge.web_monitor.make_server') as server:
            module = (importlib.reload(sys.modules['preview_monitor'])
                      if 'preview_monitor' in sys.modules
                      else importlib.import_module('preview_monitor'))
            server.assert_not_called()
        importlib.reload(module)

    def test_complete_inventory_uses_only_disposable_simulation(self):
        from preview_monitor import create_preview
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            monitor, temporary = create_preview()
            try:
                snapshot = monitor.snapshot()
                self.assertFalse(snapshot['connected'])
                self.assertEqual(snapshot['light_control'], 'simulation')
                self.assertEqual(snapshot['device_control'], 'simulation')
                self.assertEqual({d['category'] for d in snapshot['devices']},
                                 {'lights', 'shutters', 'thermostats', 'motions', 'contacts', 'alarms', 'clocks'})
                document = json.loads(monitor.device_editor.path.read_text())
                self.assertEqual(set(document['lights']), {'19', '22', '23'})
                self.assertEqual(set(document['contacts']), {'124', '125'})
                self.assertEqual(monitor.device_editor.path.parent, Path(temporary.name))
                states = {s['key']: s for s in snapshot['states']}
                self.assertEqual(states['19:0']['classification'], 'confirmed')
                self.assertEqual(states['23:0']['classification'], 'inferred')
                self.assertEqual(states['999:3']['classification'], 'observed')
                self.assertEqual(states['42:1']['value'], '21.8')
                self.assertEqual(states['44:1']['value'], '22.5')
                self.assertEqual(states['46:0']['value'], '1')
                for key in ('999:3', '19:9'):
                    self.assertEqual(states[key]['matches'], [])
            finally:
                path = monitor.device_editor.path
                temporary.cleanup()
            self.assertFalse(path.exists())

    def test_preview_commands_are_simulated_not_physical(self):
        from preview_monitor import create_preview
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            monitor, temporary = create_preview()
            try:
                self.assertIsNone(monitor.light_control.bridge)
                self.assertIsNone(monitor.device_control.bridge)
                monitor.light_control.submit({'id': 19, 'action': 'OFF', 'confirm': True,
                                              'request_id': str(uuid.uuid4())})
                monitor.device_control.submit({'category': 'thermostats', 'id': 44,
                                               'action': 'TEMPERATURE', 'value': 23.0,
                                               'confirm': True, 'request_id': str(uuid.uuid4())})
                states = {s['key']: s for s in monitor.snapshot()['states']}
                self.assertEqual(float(states['19:0']['value']), 0)
                self.assertEqual(float(states['44:1']['value']), 23)
            finally:
                temporary.cleanup()
