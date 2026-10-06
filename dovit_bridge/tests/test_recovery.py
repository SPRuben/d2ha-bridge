import json
import asyncio
from unittest.mock import AsyncMock
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from dovit_bridge.recovery import inspect, restore, initialize, digest, validate_recovery_document
from dovit_bridge.storage import load_devices, load_cover_positions, save_cover_positions, configuration_lock
from dovit_bridge.device_editor import DeviceEditor


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'devices.json'
        self.source = self.path.with_name('backup.json')
        self.raw = b'{"lights":{"19":{"name":"Office","statetype":0}},"extra":{"preserved":true}}'
        self.source.write_bytes(self.raw)

    def recover(self, **changes):
        options = dict(revision=inspect(self.path)['revision'], source_revision=digest(self.raw),
                       confirm=True, bridge_stopped=True)
        options.update(changes)
        return restore(self.path, self.source, **options)

    def test_missing_inspection_and_strict_load_do_not_create(self):
        self.assertEqual(inspect(self.path), {'state': 'missing', 'revision': 'missing'})
        with self.assertRaises(FileNotFoundError):
            load_devices(self.path, create_if_missing=False)
        with self.assertRaises(FileNotFoundError):
            load_devices(self.path)
        self.assertFalse(self.path.exists())

    def test_restore_missing_preserves_exact_backup(self):
        result = self.recover()
        self.assertEqual(result['state'], 'restored')
        self.assertEqual(self.path.read_bytes(), self.raw)
        self.assertEqual(inspect(self.path)['counts']['lights'], 1)

    def test_restore_corrupt_preserves_verified_original(self):
        original = b'{ broken file'
        self.path.write_bytes(original)
        self.assertEqual(inspect(self.path)['state'], 'invalid')
        result = self.recover()
        self.assertEqual(Path(result['preserved']).read_bytes(), original)
        self.assertEqual(self.path.read_bytes(), self.raw)

    def test_refuse_without_confirmation_or_stopped_bridge(self):
        for option in ('confirm', 'bridge_stopped'):
            with self.assertRaises(ValueError):
                self.recover(**{option: False})
        self.assertFalse(self.path.exists())

    def test_revision_conflicts_and_pending_edits(self):
        self.path.write_bytes(self.raw)
        with self.assertRaises(ValueError):
            self.recover(revision='missing')
        with self.assertRaises(ValueError):
            self.recover(source_revision='changed')
        DeviceEditor(self.path).pending.write_text('{}')
        with self.assertRaises(ValueError):
            self.recover()
        self.assertEqual(self.path.read_bytes(), self.raw)

    def test_invalid_backup_and_cleanup_actions_refused(self):
        for raw in (b'{', b'{"lights":{"19":{"name":"x","statetype":false}}}',
                    b'{"lights":{},"_removed_discovery":["lights:19"]}'):
            self.source.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.recover(source_revision=digest(raw))
            self.assertFalse(self.path.exists())

    def test_failed_replace_and_backup_flush_preserve_original(self):
        original = b'corrupt'
        self.path.write_bytes(original)
        with patch('dovit_bridge.storage.os.replace', side_effect=OSError):
            with self.assertRaises(OSError):
                self.recover()
        self.assertEqual(self.path.read_bytes(), original)
        with patch('dovit_bridge.recovery.os.fsync', side_effect=OSError):
            with self.assertRaises(OSError):
                self.recover()
        self.assertEqual(self.path.read_bytes(), original)

    def test_external_change_during_preservation_is_not_overwritten(self):
        self.path.write_bytes(b'original')
        def changed(_):
            self.path.write_bytes(b'external edit')
        with patch('dovit_bridge.recovery.os.fsync', side_effect=changed):
            with self.assertRaises(ValueError):
                self.recover()
        self.assertEqual(self.path.read_bytes(), b'external edit')

    def test_initialize_is_explicit_and_never_replaces_existing(self):
        with self.assertRaises(ValueError):
            initialize(self.path)
        initialize(self.path, confirm=True, bridge_stopped=True)
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            initialize(self.path, confirm=True, bridge_stopped=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_supported_writers_share_lock(self):
        self.assertIs(DeviceEditor(self.path).lock, configuration_lock(self.path))
        self.assertIs(configuration_lock(self.path), configuration_lock(self.path.parent / '.' / self.path.name))

    def test_initialize_flush_failure_leaves_no_target(self):
        with patch('dovit_bridge.recovery.os.fsync', side_effect=OSError):
            with self.assertRaises(OSError):
                initialize(self.path, confirm=True, bridge_stopped=True)
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_pending_final_bytes_checked_before_replacement(self):
        document = json.loads(self.raw)
        document['extra']['padding'] = '\u00e9' * 90000
        original = json.dumps(document, ensure_ascii=False).encode()
        self.path.write_bytes(original)
        self.assertEqual(inspect(self.path)['state'], 'valid')
        editor = DeviceEditor(self.path)
        request = dict(revision=digest(original), source='lights:19',
                       device=dict(category='lights', id=19, name='Updated', statetype=0),
                       confirm=True)
        with self.assertRaises(ValueError):
            editor.request(request, save=True)
        self.assertFalse(editor.pending.exists())
        # An older release may already have staged an oversized serialized result.
        editor.pending.write_text(json.dumps(request))
        with self.assertRaises(ValueError):
            editor.apply_pending()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(editor.pending.exists())

    def test_corrupt_positions_remain_recoverable_and_not_silently_overwritten(self):
        self.path.write_bytes(b'{broken')
        with self.assertLogs('dovit_bridge.storage', level='ERROR'):
            self.assertEqual(load_cover_positions(self.path), {})
        with self.assertRaises(ValueError):
            save_cover_positions(self.path, {20: 50})
        self.assertEqual(self.path.read_bytes(), b'{broken')

    def test_shipped_maps_pass_compatible_recovery_validation(self):
        raw = (Path(__file__).resolve().parents[1] / 'dovit_devices.json').read_bytes()
        self.assertEqual(validate_recovery_document(raw), json.loads(raw))

    def test_bom_restored_map_can_be_shown_in_normal_json_editor(self):
        original = b'\xef\xbb\xbf' + self.raw
        self.path.write_bytes(original)
        shown = DeviceEditor(self.path).snapshot()
        self.assertEqual(json.loads(shown['document']), json.loads(self.raw))
        self.assertEqual(shown['revision'], digest(original))
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_or_missing_startup_never_constructs_transports(self):
        from dovit_bridge.main import main
        from dovit_bridge.config import Config
        cfg = Config(mqtt_pass='', alarm_code='', enable_discovery=False,
                              devices_file=self.path, cover_position_mode='legacy',
                              cover_position_file=self.path.with_name('positions.json'))
        for missing in (True, False):
            if not missing:
                self.path.write_bytes(b'{broken')
            with patch('dovit_bridge.main.load_config', return_value=cfg), \
                    patch('dovit_bridge.main.setup_logging'), \
                    patch('dovit_bridge.main.run_recovery', new_callable=AsyncMock) as recovery, \
                    patch('dovit_bridge.main.DovitBridge') as bridge:
                with self.assertLogs('dovit_bridge.main', level='CRITICAL'):
                    asyncio.run(main())
                bridge.assert_not_called()
                recovery.assert_awaited_once_with(cfg)
            if missing:
                self.assertFalse(self.path.exists())
            else:
                self.assertEqual(self.path.read_bytes(), b'{broken')
