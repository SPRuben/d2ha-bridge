import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dovit_bridge.storage import load_devices, save_devices, save_cover_positions


class StorageSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'devices.json'
        self.original = b'{"lights":{"19":{"name":"Office","statetype":0}},"custom":{"preserve":true}}'
        self.path.write_bytes(self.original)
        self.updated = json.loads(self.original)
        self.updated['lights']['19']['name'] = 'Updated'

    def test_save_backup_and_metadata(self):
        save_devices(self.path, self.updated)
        self.assertEqual(json.loads(self.path.read_bytes()), self.updated)
        self.assertEqual(next((self.path.parent/'dovit_device_backups').glob('*.json')).read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_replace_failure_preserves_file(self):
        with patch('dovit_bridge.storage.os.replace', side_effect=OSError):
            with self.assertRaises(OSError):
                save_devices(self.path, self.updated)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_flush_failure_preserves_file(self):
        with patch('dovit_bridge.storage.os.fsync', side_effect=OSError):
            with self.assertRaises(OSError):
                save_devices(self.path, self.updated)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_atomic_flush_failure_preserves_original_and_verified_backup(self):
        with patch('dovit_bridge.storage.os.fsync', side_effect=[None, OSError('flush failed')]):
            with self.assertRaises(OSError):
                save_devices(self.path, self.updated)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(next((self.path.parent/'dovit_device_backups').glob('*.json')).read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_corrupt_existing_never_replaced(self):
        for broken in (b'', b'{', b'[]', b'{"lights":[]}', b'{"lights":{},"lights":{}}',
                       b'{"extra":NaN}', b'{"extra":Infinity}', b'{"extra":1e999}'):
            self.path.write_bytes(broken)
            with self.assertRaises(ValueError):
                load_devices(self.path)
            with self.assertRaises(ValueError):
                save_devices(self.path, self.updated)
            self.assertEqual(self.path.read_bytes(), broken)

    def test_new_invalid_data_never_replaces_original(self):
        for data in ([], {'lights': []}, {'lights': {'1': None}}, {'extra': float('nan')},
                     {'lights': {19: {}, '19': {}}}):
            with self.assertRaises(ValueError):
                save_devices(self.path, data)
            self.assertEqual(self.path.read_bytes(), self.original)

    def test_first_install_and_cover_replace_failure(self):
        new = self.path.parent/'first.json'
        self.assertEqual(load_devices(new, create_if_missing=True)['alarms'], {})
        positions = self.path.parent/'positions.json'
        positions.write_bytes(b'{"20":25}')
        with patch('dovit_bridge.storage.os.replace', side_effect=OSError):
            with self.assertRaises(OSError):
                save_cover_positions(positions, {20: 50})
        self.assertEqual(positions.read_bytes(), b'{"20":25}')
        self.assertEqual(self.path.read_bytes(), self.original)
