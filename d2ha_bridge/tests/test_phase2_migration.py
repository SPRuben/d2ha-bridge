"""Synthetic stopped-snapshot transfer/rollback and hostile-input checks."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from dovit_bridge.config import Config
from dovit_bridge import migration as m


class Phase2MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / 'private-data'
        self.share = self.root / 'shared'
        self.data.mkdir()
        self.share.mkdir()
        cfg = Config(mqtt_pass='synthetic-secret-not-for-logs')
        self.options = {key: getattr(cfg, key) for key in m.OPTIONS}
        self.options.update(devices_file='/share/custom/map.json',
                            cover_position_file='/share/custom/positions.json')
        self.mapping = b'{"lights":{"19":{"name":"Synthetic","statetype":0}},"extra":{"keep":true}}'
        self.put(self.share / 'custom/map.json', self.mapping)
        self.put(self.share / 'custom/positions.json', b'{"20":25.5}')
        self.put(self.share / 'custom/dovit_device_backups/old.json', b'{old-damaged-backup')
        self.put(self.share / 'custom/dovit_mapping_drafts/draft.json', b'{"draft":true}')
        self.put(self.share / 'custom/dovit_observed_candidates.json', b'{"observed":true}')
        self.put(self.share / 'unrelated-other-app.json', b'{"untouched":true}')
        setup = dict(settings={key: self.options[key] for key in m.FIELDS},
                     mqtt_pass=self.options['mqtt_pass'])
        setup['settings']['publish_discovery'] = True
        self.put(self.data / 'dovit_setup.json', m.encode(setup))
        self.put(self.data / 'dovit_setup_backups/old.json', b'{broken-but-preserved')
        self.save_options()
        self.info = dict(slug='local_local_dovit_bridge', version='3.0.0', state='stopped',
                         boot='manual', watchdog=False, auto_update=False, options=self.options)
        self.target_info = dict(slug='local_d2ha_bridge', version='3.1.0', state='stopped',
                                boot='manual', watchdog=False, auto_update=False)
        self.bundle = self.root / 'private.bundle'

    def put(self, path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def save_options(self):
        self.put(self.data / 'options.json', m.encode(self.options))

    def build(self, reviewed=()):
        return m.build_bundle(self.data, self.share, m.encode(self.info), reviewed)

    def export(self):
        manifest, blobs = self.build()
        m.write_bundle(self.bundle, manifest, blobs)
        return manifest, blobs

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for base in (self.data, self.share) for path in base.rglob('*') if path.is_file()}

    def test_full_transfer_and_rollback_originals_without_shared_overwrite(self):
        before = self.snapshot()
        manifest, blobs = self.export()
        restored, actual = m.read_bundle(self.bundle)
        self.assertEqual(manifest, restored)
        self.assertEqual(blobs, actual)
        destination = self.root / 'new-staging'
        m.stage_bundle(self.bundle, destination, m.encode(self.target_info))
        for name, raw in blobs.items():
            self.assertEqual((destination / name).read_bytes(), raw)
        self.assertEqual((destination / 'source/share/custom/map.json').read_bytes(), self.mapping)
        self.assertFalse((destination / 'target/share').exists())
        self.assertNotIn('source/share/unrelated-other-app.json', blobs)
        # The original options/setup provide an exact rollback snapshot. They
        # are not automatically copied over possibly newer live shared files.
        self.assertEqual((destination / 'source/options.json').read_bytes(), before['private-data/options.json'])
        self.assertEqual((destination / 'source/data/dovit_setup.json').read_bytes(), before['private-data/dovit_setup.json'])
        self.assertEqual(before, self.snapshot())

    def test_private_override_and_target_flags_preserve_password_other_settings(self):
        manifest, blobs = self.export()
        self.assertTrue(manifest['original_flags']['publish_discovery'])
        target_options = m.decode(blobs['target/options.json'])
        self.assertTrue(all(target_options[key] is False for key in m.FLAGS))
        for key in set(self.options) - set(m.FLAGS):
            self.assertEqual(target_options[key], self.options[key])
        original = m.decode(blobs['source/data/dovit_setup.json'])
        target = m.decode(blobs['target/data/dovit_setup.json'])
        self.assertTrue(original['settings']['publish_discovery'])
        original['settings']['publish_discovery'] = False
        self.assertEqual(original, target)

    def test_absent_setup_and_positions_are_explicit_not_initialized(self):
        (self.data / 'dovit_setup.json').unlink()
        (self.share / 'custom/positions.json').unlink()
        manifest, _ = self.export()
        self.assertFalse(manifest['private_setup_present'])
        self.assertFalse(manifest['cover_positions_present'])
        self.assertFalse((self.data / 'dovit_setup.json').exists())
        self.assertFalse((self.share / 'custom/positions.json').exists())

    def test_custom_private_mapping_paths_preserved(self):
        self.options['devices_file'] = '/data/custom/map.json'
        self.options['cover_position_file'] = '/data/custom/positions.json'
        self.save_options()
        self.put(self.data / 'custom/map.json', self.mapping)
        self.put(self.data / 'custom/positions.json', b'{"20":60}')
        manifest, blobs = self.export()
        self.assertEqual(manifest['configured_paths']['devices_file'], '/data/custom/map.json')
        self.assertEqual(blobs['target/data/custom/map.json'], self.mapping)
        self.assertEqual(blobs['target/data/custom/positions.json'], b'{"20":60}')

    def test_unknown_private_file_requires_explicit_review(self):
        self.put(self.data / 'extra.json', b'{"keep":true}')
        with self.assertRaisesRegex(m.MigrationError, 'needs_review'):
            self.build()
        manifest, blobs = self.build(['extra.json'])
        self.assertEqual(manifest['reviewed_data'], ['extra.json'])
        self.assertEqual(blobs['target/data/extra.json'], b'{"keep":true}')

    def test_runtime_tokens_never_transferred_even_when_reviewed(self):
        self.put(self.data / 'supervisor_token', b'synthetic-not-a-real-token')
        with self.assertRaisesRegex(m.MigrationError, 'runtime_access_data_forbidden'):
            self.build(['supervisor_token'])

    def test_running_source_is_refused_without_mutation(self):
        before = self.snapshot()
        self.info['state'] = 'started'
        with self.assertRaisesRegex(m.MigrationError, 'app_not_stopped'):
            self.build()
        self.assertEqual(self.snapshot(), before)

    def test_start_protection_and_version_are_required(self):
        for key, value in (('boot', 'auto'), ('watchdog', True), ('auto_update', True), ('version', '2.2')):
            with self.subTest(key=key):
                info = dict(self.info, **{key: value})
                with self.assertRaises(m.MigrationError):
                    m.build_bundle(self.data, self.share, m.encode(info))

    def test_redacted_or_disagreeing_supervisor_options_are_not_exports(self):
        for value in ({}, dict(self.options, mqtt_host='other.example.invalid')):
            with self.subTest(redacted=not bool(value)):
                with self.assertRaises(m.MigrationError):
                    m.build_bundle(self.data, self.share, m.encode(dict(self.info, options=value)))

    def test_pending_custom_mapping_blocks_cutover(self):
        pending = self.share / 'custom/map.pending.json'
        self.put(pending, b'{"pending":true}')
        before = self.snapshot()
        with self.assertRaisesRegex(m.MigrationError, 'pending_mapping'):
            self.build()
        self.assertEqual(self.snapshot(), before)

    def test_pending_private_mapping_blocks_cutover(self):
        self.options['devices_file'] = '/data/custom/map.json'
        self.save_options()
        self.put(self.data / 'custom/map.json', self.mapping)
        self.put(self.data / 'custom/map.pending.json', b'{"pending":true}')
        with self.assertRaises(m.MigrationError):
            self.build()

    def test_broken_private_setup_is_not_treated_as_absence(self):
        for raw in (b'{broken', b'{"settings":{},"settings":{}}', b'x' * 16385):
            with self.subTest(length=len(raw)):
                self.put(self.data / 'dovit_setup.json', raw)
                with self.assertRaisesRegex(m.MigrationError, 'invalid_private_setup'):
                    self.build()
                self.assertEqual((self.data / 'dovit_setup.json').read_bytes(), raw)

    def test_empty_missing_invalid_mapping_and_positions_refused(self):
        for raw in (b'{}', b'{"lights":[]}', b'{"lights":{},"lights":{}}'):
            with self.subTest(raw=raw):
                self.put(self.share / 'custom/map.json', raw)
                with self.assertRaises(m.MigrationError):
                    self.build()
        self.put(self.share / 'custom/map.json', self.mapping)
        self.put(self.share / 'custom/positions.json', b'{"20":101}')
        with self.assertRaisesRegex(m.MigrationError, 'invalid_mapping_or_positions'):
            self.build()
        (self.share / 'custom/map.json').unlink()
        with self.assertRaisesRegex(m.MigrationError, 'active_mapping_missing'):
            self.build()

    def test_options_unknown_keys_redaction_bad_types_or_paths_refused(self):
        for raw in (b'{}', m.encode(dict(self.options, unknown=True)),
                    m.encode(dict(self.options, enable_discovery='false')),
                    m.encode(dict(self.options, devices_file='/share/../other.json')),
                    m.encode(dict(self.options, devices_file='/app/dovit_devices.json'))):
            with self.subTest(length=len(raw)):
                with self.assertRaises(m.MigrationError):
                    m.config_from_options(raw)

    def test_populated_and_empty_existing_staging_both_refused(self):
        self.export()
        destination = self.root / 'existing'
        destination.mkdir()
        for populated in (False, True):
            if populated:
                (destination / 'sentinel').write_bytes(b'keep')
            with self.assertRaisesRegex(m.MigrationError, 'staging_destination_exists'):
                m.stage_bundle(self.bundle, destination, m.encode(self.target_info))
        self.assertEqual((destination / 'sentinel').read_bytes(), b'keep')

    def test_target_version_state_prefix_and_start_protection_refused(self):
        self.export()
        for key, value in (('version', '3.0.0'), ('state', 'started'),
                           ('slug', 'different_d2ha_bridge'), ('boot', 'auto')):
            with self.subTest(key=key):
                with self.assertRaises(m.MigrationError):
                    m.stage_bundle(self.bundle, self.root / 'new', m.encode(dict(self.target_info, **{key: value})))
                self.assertFalse((self.root / 'new').exists())

    def test_checked_patch_target_supported_unknown_target_refused(self):
        self.export()
        before = self.snapshot()
        for version in ('3.1.2', '3.2.0', '4.0.0'):
            with self.subTest(version=version):
                with self.assertRaisesRegex(m.MigrationError, 'unexpected_app_version'):
                    m.stage_bundle(self.bundle, self.root / 'new',
                                   m.encode(dict(self.target_info, version=version)))
                self.assertFalse((self.root / 'new').exists())
        m.stage_bundle(self.bundle, self.root / 'new',
                       m.encode(dict(self.target_info, version='3.1.1')))
        self.assertTrue((self.root / 'new' / 'target' / 'options.json').is_file())
        self.assertEqual(before, self.snapshot())

    def test_partial_staging_failure_leaves_source_and_destination_untouched(self):
        self.export()
        before = self.snapshot()
        write = m.write_private
        calls = 0
        def fail(path, raw):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('synthetic write failure')
            write(path, raw)
        with patch.object(m, 'write_private', side_effect=fail):
            with self.assertRaises(OSError):
                m.stage_bundle(self.bundle, self.root / 'new', m.encode(self.target_info))
        self.assertFalse((self.root / 'new').exists())
        self.assertEqual(list(self.root.glob('.d2ha-phase2-*')), [])
        self.assertEqual(before, self.snapshot())

    def test_bundle_is_exclusive_and_original_preserved(self):
        manifest, blobs = self.export()
        before = self.bundle.read_bytes()
        with self.assertRaises(FileExistsError):
            m.write_bundle(self.bundle, manifest, blobs)
        self.assertEqual(before, self.bundle.read_bytes())

    def test_archive_traversal_absolute_backslash_and_device_paths_refused(self):
        for name in ('../escape', '/absolute', 'source/data/../../escape',
                     'source\\data\\escape', 'source/data/CON.json'):
            with self.subTest(name=name):
                hostile = self.root / 'hostile.bundle'
                with zipfile.ZipFile(hostile, 'w') as archive:
                    archive.writestr('manifest.json', b'{}')
                    entry = zipfile.ZipInfo('placeholder')
                    entry.filename = name
                    archive.writestr(entry, b'test')
                with self.assertRaisesRegex(m.MigrationError, 'unsafe_path'):
                    m.read_bundle(hostile)
                self.assertFalse((self.root / 'escape').exists())

    def test_duplicate_archive_and_symbolic_link_entries_refused(self):
        hostile = self.root / 'hostile.bundle'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(hostile, 'w') as archive:
                archive.writestr('manifest.json', b'{}')
                archive.writestr('manifest.json', b'{}')
        with self.assertRaisesRegex(m.MigrationError, 'duplicate_archive_path'):
            m.read_bundle(hostile)
        link = zipfile.ZipInfo('source/data/link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(hostile, 'w') as archive:
            archive.writestr('manifest.json', b'{}')
            archive.writestr(link, b'../../outside')
        with self.assertRaisesRegex(m.MigrationError, 'unsupported_archive_entry'):
            m.read_bundle(hostile)

    def test_corruption_and_rehashed_target_identity_changes_are_refused(self):
        manifest, blobs = self.export()
        malicious = dict(blobs)
        malicious['target/options.json'] = m.encode(dict(self.options, mqtt_host='changed.example.invalid'))
        hostile = self.root / 'changed.bundle'
        m.write_bundle(hostile, manifest, malicious)
        with self.assertRaisesRegex(m.MigrationError, 'archive_hash_mismatch'):
            m.read_bundle(hostile)
        altered = dict(manifest, files=[dict(path=name, length=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            for name, raw in sorted(malicious.items())])
        hostile.unlink()
        m.write_bundle(hostile, altered, malicious)
        with self.assertRaisesRegex(m.MigrationError, 'unexpected_target_change_or_file'):
            m.read_bundle(hostile)

    def test_archive_decompressed_size_limit_is_enforced(self):
        hostile = self.root / 'large.bundle'
        with zipfile.ZipFile(hostile, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', b'{}')
            archive.writestr('source/data/large.json', b'x' * 4096)
        with patch.object(m, 'MAX_FILE', 1024):
            with self.assertRaisesRegex(m.MigrationError, 'file_too_large'):
                m.read_bundle(hostile)

    def test_symlink_source_is_refused(self):
        link = self.data / 'extra.json'
        try:
            link.symlink_to(self.share / 'custom/map.json')
        except OSError:
            self.skipTest('Host cannot create symlinks; Linux container verifies this case')
        with self.assertRaises(m.MigrationError):
            self.build(['extra.json'])

    def test_cli_output_never_contains_credentials_or_private_data(self):
        self.export()
        output = io.StringIO()
        with patch('sys.argv', ['migration', 'inspect', str(self.bundle)]), contextlib.redirect_stdout(output):
            m.main()
        text = output.getvalue()
        self.assertNotIn(self.options['mqtt_pass'], text)
        self.assertNotIn('Synthetic', text)
        self.assertNotIn('/share/custom', text)
        self.assertFalse(json.loads(text)['ha_actions_performed'])
        self.assertFalse(json.loads(text)['live_app_state_verified'])


if __name__ == '__main__':
    unittest.main()
