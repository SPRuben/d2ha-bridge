import copy
import json
from pathlib import Path
import tempfile
import unittest

from dovit_bridge.candidate_store import CandidateStore
from dovit_bridge.web_monitor import Monitor


class CandidateClassificationTests(unittest.TestCase):
    def test_todo_marker_matches_existing_publication_convention(self):
        monitor = Monitor()
        monitor.configure({'lights': {2: {'name': '  todo_Light_2 ', 'statetype': 0}}})
        self.assertEqual(monitor.snapshot()['devices'][0]['classification'], 'inferred')
        self.assertEqual(monitor.snapshot()['devices'][0]['name'], '  todo_Light_2 ')

    def test_current_routes_classify_without_mutating_maps_or_match_ids(self):
        maps = {'lights': {1: {'name': 'Office', 'statetype': 0},
                           2: {'name': 'TODO_Light_2', 'statetype': 0}}}
        original = copy.deepcopy(maps)
        monitor = Monitor()
        monitor.configure(maps, include_system=True)
        for device_id, statetype in [(1, 0), (2, 0), (3, 0), (39, 111)]:
            monitor.observe(device_id, statetype, '1')
        snapshot = monitor.snapshot()
        states = {event['key']: event for event in snapshot['states']}
        self.assertEqual(states['1:0']['classification'], 'confirmed')
        self.assertEqual(states['2:0']['classification'], 'inferred')
        self.assertEqual(states['3:0']['classification'], 'observed')
        self.assertEqual(states['39:111']['classification'], 'confirmed')
        self.assertEqual(states['2:0']['matches'], [{'uid': 'lights:2', 'role': 'state'}])
        self.assertTrue(all(event['provenance'] == 'received_signal' for event in snapshot['events']))
        self.assertEqual(snapshot['devices'][1]['provenance'], 'todo_name_marker')
        self.assertEqual(maps, original)
        self.assertEqual(list(monitor.candidates), ['3:0'])

    def test_reconfigure_reclassifies_existing_evidence(self):
        monitor = Monitor()
        monitor.observe(2, 0, '1')
        for name, classification in [('TODO_Light_2', 'inferred'),
                                     ('Office', 'confirmed')]:
            monitor.configure({'lights': {2: {'name': name, 'statetype': 0}}})
            snapshot = monitor.snapshot()
            self.assertEqual(snapshot['states'][0]['classification'], classification)
            self.assertEqual(snapshot['events'][0]['classification'], classification)
            self.assertEqual(snapshot['states'][0]['matches'], [{'uid': 'lights:2', 'role': 'state'}])
            self.assertEqual(snapshot['events'][0]['matches'], [{'uid': 'lights:2', 'role': 'state'}])
        monitor.configure({})
        snapshot = monitor.snapshot()
        self.assertEqual(snapshot['states'][0]['classification'], 'observed')
        self.assertEqual(snapshot['events'][0]['classification'], 'observed')
        self.assertEqual(snapshot['states'][0]['matches'], [])
        self.assertEqual(snapshot['events'][0]['matches'], [])

    def test_archive_cannot_claim_configuration_or_live_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'candidates.json'
            monitor = Monitor()
            monitor.observe(2, 0, '1')
            CandidateStore(monitor, path).save()
            data = json.loads(path.read_text())
            data['candidates'][0].update(classification='confirmed',
                                         provenance='received_signal', matches=[{'uid': 'lights:2'}])
            path.write_text(json.dumps(data))
            restored = Monitor()
            CandidateStore(restored, path).load()
            state = restored.snapshot()['states'][0]
            self.assertEqual(state['classification'], 'observed')
            self.assertEqual(state['provenance'], 'candidate_archive')
            self.assertEqual(state['matches'], [])
            self.assertEqual(restored.sequence, 0)
            restored.observe(2, 0, '0')
            self.assertEqual(restored.snapshot()['states'][0]['provenance'], 'received_signal')

    def test_caps_and_redaction_unchanged(self):
        monitor = Monitor(secrets=('secret',))
        for value in range(25):
            monitor.observe(0, 0, str(value))
        self.assertEqual(len(monitor.candidates['0:0']['values']), 20)
        for device_id in range(1, 2002):
            monitor.observe(device_id, 0, 'secret' + 'x' * 200)
        snapshot = monitor.snapshot()
        self.assertEqual(len(monitor.candidates), 2000)
        self.assertEqual(len(monitor.states), 2000)
        self.assertEqual(len(snapshot['events']), 500)
        self.assertEqual(snapshot['capacity'], 500)
        self.assertNotIn('secret', snapshot['states'][-1]['value'])
        self.assertEqual(len(snapshot['states'][-1]['value']), 160)


if __name__ == '__main__':
    unittest.main()
