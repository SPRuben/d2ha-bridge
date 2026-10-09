import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dovit_bridge.recovery import digest
from dovit_bridge.recovery_service import RecoveryManager


class RecoveryServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'devices.json'
        self.original = b'{ broken original'
        self.path.write_bytes(self.original)
        self.document = '{"lights":{"19":{"name":"Office","statetype":0}}}'
        self.manager = RecoveryManager(self.path)

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def validate(self, **changes):
        raw = dict(revision=self.manager.status()['current']['revision'], document=self.document)
        raw.update(changes)
        return self.manager.validate(raw)

    def request(self, checked, **changes):
        raw = dict(revision=checked['revision'], validation_id=checked['validation_id'], confirm=True)
        raw.update(changes)
        return raw

    def backup(self, name='known.json', document=None):
        directory = self.root / 'dovit_device_backups'
        directory.mkdir(exist_ok=True)
        path = directory / name
        path.write_text(self.document if document is None else document, encoding='utf-8')
        listing = self.manager.status()['backups']
        return path, next(item['id'] for item in listing if item['name'] == name)

    def test_status_and_validation_are_file_mutation_free(self):
        before = self.files()
        status = self.manager.status()
        self.assertEqual(status['current']['state'], 'invalid')
        self.assertEqual(status['current']['revision'], digest(self.original))
        checked = self.validate()
        self.assertEqual(checked['revision'], digest(self.original))
        self.assertEqual(checked['summary']['counts']['lights'], 1)
        self.assertEqual(checked['summary']['names'], [{'category': 'lights', 'name': 'Office'}])
        self.assertFalse(checked['summary']['has_alarms'])
        self.assertFalse(checked['summary']['empty'])
        self.assertEqual(self.files(), before)

    def test_uploaded_text_and_pasted_text_have_identical_document_api(self):
        upload = self.root / 'uploaded.json'
        upload.write_text(self.document, encoding='utf-8')
        first = self.validate(document=upload.read_text(encoding='utf-8'))
        second = self.validate(document=self.document)
        self.assertEqual(first['summary'], second['summary'])
        self.assertEqual(first['revision'], second['revision'])
        self.assertNotEqual(first['validation_id'], second['validation_id'])

    def test_backup_opaque_id_list_counts_and_restore_exact_bytes(self):
        source, identifier = self.backup()
        listed = self.manager.status()['backups'][0]
        self.assertEqual(listed['counts']['lights'], 1)
        self.assertNotIn(str(self.root), json.dumps(listed))
        self.assertNotEqual(identifier, source.name)
        before = self.files()
        checked = self.manager.validate({'revision': digest(self.original), 'backup': identifier})
        self.assertEqual(self.files(), before)
        result = self.manager.apply(self.request(checked))
        self.assertEqual(result, {'restored': True, 'restart_required': True})
        self.assertEqual(self.path.read_bytes(), source.read_bytes())

    def test_paths_traversal_unknown_ids_and_ambiguous_sources_refused(self):
        source, identifier = self.backup()
        for value in ['../known.json', str(source), source.name, 'missing', 1, None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.manager.validate({'revision': digest(self.original), 'backup': value})
        for raw in [dict(revision=digest(self.original)),
                    dict(revision=digest(self.original), backup=identifier, document=self.document),
                    dict(revision=digest(self.original), document={}), None, []]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.manager.validate(raw)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_invalid_json_nonfinite_duplicates_and_protocol_schema_refused(self):
        documents = ['{', '{"lights":{},"lights":{}}',
                     '{"extra":NaN}', '{"extra":Infinity}',
                     '{"lights":{"19":{"statetype":true}}}',
                     '{"lights":{"19":{"statetype":-1}}}',
                     '{"lights":{"019":{"statetype":0}}}',
                     '{"lights":{"19":{"statetype":2147483648}}}',
                     '{"lights":{"19":{"name":3,"statetype":0}}}',
                     '{"thermostats":{"19":{"target":{},"current":{}}}}',
                     '{"_removed_discovery":["lights:19"]}']
        before = self.files()
        for document in documents:
            with self.subTest(document=document), self.assertRaises(ValueError):
                self.validate(document=document)
        self.assertEqual(self.files(), before)

    def test_alarm_confirmation_requires_literal_true(self):
        checked = self.validate(document='{"alarms":{"1":{"name":"House","state_statetype":1}}}')
        self.assertTrue(checked['summary']['has_alarms'])
        for confirmation in [None, False, 1, 'true']:
            with self.subTest(confirmation=confirmation), self.assertRaises(ValueError):
                self.manager.apply(self.request(checked, confirm_alarm=confirmation))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(self.manager.apply(self.request(checked, confirm_alarm=True))['restored'])

    def test_empty_and_general_confirmations_require_literal_true(self):
        checked = self.validate(document='{}')
        self.assertTrue(checked['summary']['empty'])
        for changes in [dict(confirm=False, confirm_empty=True), dict(confirm=1, confirm_empty=True),
                        dict(confirm_empty=False), dict(confirm_empty=1)]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.apply(self.request(checked, **changes))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(self.manager.apply(self.request(checked, confirm_empty=True))['restored'])

    def test_stale_target_during_validate_and_apply_refused(self):
        with self.assertRaises(ValueError):
            self.validate(revision='wrong')
        checked = self.validate()
        self.path.write_bytes(b'{ changed original')
        with self.assertRaises(ValueError):
            self.manager.apply(self.request(checked))
        self.assertEqual(self.path.read_bytes(), b'{ changed original')
        self.assertIsNone(self.manager.validation)

    def test_changed_or_deleted_backup_refused(self):
        for deleted in [False, True]:
            with self.subTest(deleted=deleted):
                source, identifier = self.backup()
                checked = self.manager.validate({'revision': digest(self.original), 'backup': identifier})
                if deleted:
                    source.unlink()
                else:
                    source.write_text('{}')
                with self.assertRaises((ValueError, OSError)):
                    self.manager.apply(self.request(checked))
                self.assertEqual(self.path.read_bytes(), self.original)

    def test_pending_blocks_validation_and_apply(self):
        pending = self.path.with_name('devices.pending.json')
        pending.write_bytes(b'pending')
        with self.assertRaises(ValueError):
            self.validate()
        pending.unlink()
        checked = self.validate()
        pending.write_bytes(b'pending')
        with self.assertRaises(ValueError):
            self.manager.apply(self.request(checked))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(pending.read_bytes(), b'pending')

    def test_latest_validation_only_and_invalid_attempt_invalidates(self):
        first = self.validate()
        second = self.validate()
        with self.assertRaises(ValueError):
            self.manager.apply(self.request(first))
        self.assertEqual(self.manager.validation['id'], second['validation_id'])
        with self.assertRaises(ValueError):
            self.validate(document='{')
        with self.assertRaises(ValueError):
            self.manager.apply(self.request(second))
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_success_preserves_original_and_allows_only_idempotent_result(self):
        checked = self.validate()
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            result = self.manager.apply(self.request(checked))
            self.assertEqual(result, {'restored': True, 'restart_required': True})
        backups = list((self.root / 'dovit_device_backups').glob('*_recovery_*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.original)
        self.assertEqual(self.path.read_bytes(), self.document.encode())
        before = self.files()
        self.assertEqual(self.manager.apply(self.request(checked)), result)
        with self.assertRaises(ValueError):
            self.validate()
        with self.assertRaises(ValueError):
            self.manager.apply(self.request(checked, validation_id='other'))
        self.assertEqual(self.files(), before)
        self.assertTrue(self.manager.status()['restart_required'])

    def test_replace_failure_preserves_original_and_cleans_upload(self):
        checked = self.validate()
        with patch('dovit_bridge.storage.os.replace', side_effect=OSError('replace failed')):
            with self.assertRaises(OSError):
                self.manager.apply(self.request(checked))
        self.assertEqual(self.path.read_bytes(), self.original)
        backups = list((self.root / 'dovit_device_backups').glob('*_recovery_*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.original)
        self.assertFalse(list(self.root.glob('*.upload.*')))
        self.assertFalse(list(self.root.glob('*.tmp')))
        self.assertFalse(self.manager.status()['restored'])

    def test_missing_target_and_bounded_backup_list_and_summary(self):
        self.path.unlink()
        self.assertEqual(self.manager.status()['current']['revision'], 'missing')
        directory = self.root / 'dovit_device_backups'
        directory.mkdir()
        for index in range(105):
            (directory / f'{index:03}.json').write_text('{}')
        self.assertEqual(len(self.manager.status()['backups']), 100)
        document = json.dumps({'lights': {str(index): {'name': 'x' * 170, 'statetype': 0}
                                         for index in range(205)}})
        checked = self.validate(document=document)
        self.assertEqual(checked['summary']['counts']['lights'], 205)
        self.assertEqual(len(checked['summary']['names']), 200)
        self.assertTrue(checked['summary']['names_truncated'])
        self.assertEqual(len(checked['summary']['names'][0]['name']), 160)
        self.assertFalse(self.path.exists())
        self.assertTrue(self.manager.apply(self.request(checked))['restored'])

    def test_document_size_cap(self):
        with self.assertRaises(ValueError):
            self.validate(document=' ' * (256 * 1024 + 1))
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_raw_upload_preserves_bom_crlf_and_exact_bytes_on_apply(self):
        content = (b'\xef\xbb\xbf{\r\n  "lights": {"19": {"name": "Caf\xc3\xa9", '
                   b'"statetype": 0}}\r\n}\r\n')
        before = self.files()
        checked = self.manager.validate({'revision': digest(self.original), 'file_bytes': list(content)})
        self.assertEqual(checked['summary']['counts']['lights'], 1)
        self.assertEqual(checked['summary']['names'][0]['name'], 'Caf\u00e9')
        self.assertEqual(self.files(), before)
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            self.assertTrue(self.manager.apply(self.request(checked))['restored'])
        self.assertEqual(self.path.read_bytes(), content)
        backups = list((self.root / 'dovit_device_backups').glob('*_recovery_*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.original)

    def test_raw_upload_malformed_utf8_inside_name_refused(self):
        before = self.files()
        for name in [b'\xff', b'\xc3(', b'\xed\xa0\x80', b'\xe2\x82']:
            content = b'{"lights":{"19":{"name":"' + name + b'","statetype":0}}}'
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.manager.validate({'revision': digest(self.original), 'file_bytes': list(content)})
                self.assertIsNone(self.manager.validation)
        self.assertEqual(self.files(), before)

    def test_raw_upload_byte_values_and_container_strict(self):
        before = self.files()
        for value in [True, False, -1, 256, 1.0, '123', None]:
            values = list(self.document.encode())
            values[0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.manager.validate({'revision': digest(self.original), 'file_bytes': values})
        for values in [self.document, bytes(self.document, 'utf-8'), {}, None, []]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.manager.validate({'revision': digest(self.original), 'file_bytes': values})
        self.assertEqual(self.files(), before)

    def test_raw_upload_mixed_sources_refused(self):
        _, identifier = self.backup()
        before = self.files()
        for extra in [dict(document=self.document), dict(backup=identifier),
                      dict(document=self.document, backup=identifier)]:
            raw = dict(revision=digest(self.original), file_bytes=list(self.document.encode()), **extra)
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.manager.validate(raw)
        self.assertEqual(self.files(), before)

    def test_raw_upload_256_kib_boundary(self):
        limit = 256 * 1024
        content = self.document.encode()
        content += b' ' * (limit - len(content))
        before = self.files()
        checked = self.manager.validate({'revision': digest(self.original), 'file_bytes': list(content)})
        self.assertEqual(checked['summary']['counts']['lights'], 1)
        self.assertEqual(self.files(), before)
        with self.assertRaises(ValueError):
            self.manager.validate({'revision': digest(self.original), 'file_bytes': list(content + b' ')})
        self.assertIsNone(self.manager.validation)
        self.assertEqual(self.files(), before)


if __name__ == '__main__':
    unittest.main()
