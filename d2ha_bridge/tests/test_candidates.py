import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from dovit_bridge.candidate_store import CandidateStore
from dovit_bridge.web_monitor import Monitor


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'candidates.json'

    def test_restart_is_historical_not_live(self):
        m = Monitor(('secret',))
        m.configure({'lights': {1: {'statetype': 0}}})
        m.observe(1, 0, '1')
        m.observe(99, 0, 'secret')
        m.observe(99, 0, '1')
        CandidateStore(m, self.path).save()
        self.assertNotIn('secret', self.path.read_text())
        restored = Monitor()
        CandidateStore(restored, self.path).load()
        result = restored.snapshot()
        self.assertEqual(result['events'], [])
        self.assertEqual(len(result['states']), 1)
        self.assertEqual(result['states'][0]['kind'], 'historical')
        self.assertEqual(result['states'][0]['seq'], 0)
        restored.observe(99, 0, '0')
        self.assertEqual(restored.snapshot()['events'][0]['kind'], 'first')
        self.assertEqual(restored.candidates['99:0']['count'], 3)

    def test_corrupt_file_preserved(self):
        self.path.write_text('{broken')
        m = Monitor()
        store = CandidateStore(m, self.path)
        with self.assertLogs(level='ERROR'):
            store.load()
        m.observe(2, 0, '1')
        store.save()
        self.assertEqual(self.path.read_text(), '{broken')
        self.assertEqual(m.persistence_status, 'blocked')

    def test_failed_replace_keeps_previous_archive_and_retries(self):
        m = Monitor()
        store = CandidateStore(m, self.path)
        m.observe(2, 0, '0')
        store.save()
        old = self.path.read_bytes()
        m.observe(2, 0, '1')
        with patch('dovit_bridge.candidate_store.os.replace', side_effect=OSError), self.assertLogs(level='ERROR'):
            store.save()
        self.assertEqual(self.path.read_bytes(), old)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])
        store.save()
        self.assertNotEqual(self.path.read_bytes(), old)

    def test_deeply_nested_archive_preserved_without_startup_failure(self):
        original = '[' * 5000 + '0' + ']' * 5000
        self.path.write_text(original)
        monitor = Monitor()
        store = CandidateStore(monitor, self.path)
        with self.assertLogs(level='ERROR'):
            store.load()
        self.assertTrue(store.blocked)
        self.assertEqual(monitor.persistence_status, 'blocked')
        store.save()
        self.assertEqual(self.path.read_text(), original)

    def test_mapped_candidate_hidden_after_restart(self):
        m = Monitor()
        m.observe(2, 0, '1')
        CandidateStore(m, self.path).save()
        restored = Monitor()
        CandidateStore(restored, self.path).load()
        restored.configure({'lights': {2: {'statetype': 0}}})
        self.assertEqual(restored.snapshot()['states'], [])

    def test_values_bounded_and_missing_file_ready(self):
        m = Monitor()
        store = CandidateStore(m, self.path)
        store.load()
        self.assertEqual(m.persistence_status, 'ready')
        for i in range(30):
            m.observe(2, 0, str(i))
        self.assertEqual(len(m.candidates['2:0']['values']), 20)
        store.save()
        with patch('dovit_bridge.candidate_store.os.replace') as replace:
            store.save()
        replace.assert_not_called()
