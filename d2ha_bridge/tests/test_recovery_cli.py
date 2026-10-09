"""Exercise the documented offline entry point on disposable files only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RecoveryCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='dovit_cli_acceptance_')
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'devices.json'
        self.source = self.path.with_name('backup.json')
        self.original = b'{"lights":{"19":{"name":"Synthetic Office","statetype":0}}}'
        self.source.write_bytes(self.original)
        self.root = Path(__file__).resolve().parents[1]

    def run_cli(self, action, *arguments, success=True):
        result = subprocess.run(
            [sys.executable, '-m', 'dovit_bridge.recovery', action, str(self.path), *arguments],
            cwd=self.root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return json.loads(result.stdout) if success else result

    def restore_arguments(self, revision='missing'):
        return ['--source', str(self.source), '--revision', revision,
                '--source-revision', hashlib.sha256(self.original).hexdigest(),
                '--confirm', '--bridge-stopped']

    def test_missing_inspection_then_explicit_restore(self):
        self.assertEqual(self.run_cli('inspect')['state'], 'missing')
        self.assertFalse(self.path.exists())
        self.assertEqual(self.run_cli('restore', *self.restore_arguments())['state'], 'restored')
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(self.run_cli('inspect')['counts']['lights'], 1)

    def test_corrupt_target_preserved_and_outputs_do_not_expose_contents(self):
        corrupt = b'{ private synthetic contents'
        self.path.write_bytes(corrupt)
        inspection = self.run_cli('inspect')
        self.assertEqual(inspection['state'], 'invalid')
        self.assertNotIn('private', json.dumps(inspection))
        result = self.run_cli('restore', *self.restore_arguments(inspection['revision']))
        self.assertEqual(Path(result['preserved']).read_bytes(), corrupt)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_confirmation_revision_and_pending_guards(self):
        refusal = self.run_cli('restore', '--source', str(self.source), '--revision', 'missing',
                               '--source-revision', hashlib.sha256(self.original).hexdigest(), success=False)
        self.assertIn('Recovery refused', refusal.stderr)
        self.assertFalse(self.path.exists())
        self.path.write_bytes(self.original)
        self.run_cli('restore', *self.restore_arguments(), success=False)
        pending = self.path.with_name('devices.pending.json')
        pending.write_bytes(b'{}')
        self.run_cli('restore', *self.restore_arguments(hashlib.sha256(self.original).hexdigest()), success=False)
        self.assertTrue(pending.exists())
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_explicit_initialization_never_overwrites_existing_maps(self):
        self.run_cli('initialize', success=False)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.run_cli('initialize', '--confirm', '--bridge-stopped')['state'], 'valid')
        before = self.path.read_bytes()
        self.run_cli('initialize', '--confirm', '--bridge-stopped', success=False)
        self.assertEqual(self.path.read_bytes(), before)
