import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from dovit_bridge.bridge import DovitBridge


class RemovedStateCleanupTests(unittest.TestCase):
    def setUp(self):
        self.b = b = DovitBridge.__new__(DovitBridge)
        b.cfg = SimpleNamespace(enable_discovery=True, publish_discovery=False,
                                publish_todo_entities=False, discovery_prefix='homeassistant',
                                devices_file='unused.json')
        b.mqtt = Mock(connected=True)
        b.mqtt.publish.return_value.rc = 0
        b.reload_device_maps = Mock()
        for category in ('lights', 'shutters', 'motions', 'contacts', 'thermostats', 'alarms'):
            setattr(b, category, {})
        for method in ('publish_light_discovery', 'publish_cover_discovery',
                       'publish_motion_discovery', 'publish_contact_discovery',
                       'publish_alarm_discovery', 'publish_alarm_house_discovery',
                       'publish_combined_alarm_state'):
            setattr(b, method, Mock())
        self.document = {'_removed_discovery': []}

    def publish(self, identities):
        self.document['_removed_discovery'] = identities
        with patch('dovit_bridge.bridge.load_devices', return_value=self.document), \
                patch('dovit_bridge.bridge.save_devices') as save:
            self.b.publish_all_discovery_once('cleanup test')
            save.assert_not_called()
        self.assertEqual(self.document['_removed_discovery'], identities)

    def cleared(self):
        return {c.args[0] for c in self.b.mqtt.publish.call_args_list if c.args[1] == ''}

    def test_all_supported_categories_clear_only_canonical_states_and_discovery(self):
        self.publish(['lights:19', 'shutters:20', 'motions:30', 'contacts:31', 'thermostats:44'])
        expected = {
            'homeassistant/light/dovit_light_19/config', 'dovit/light/19/state',
            'homeassistant/cover/dovit_cover_20/config', 'dovit/cover/20/state', 'dovit/cover/20/position',
            'homeassistant/binary_sensor/dovit_motion_30/config', 'dovit/motion/30/state',
            'homeassistant/binary_sensor/dovit_contact_31/config', 'dovit/contact/31/state',
            'homeassistant/climate/dovit_climate_44/config',
            'dovit/thermostat/44/current_temperature', 'dovit/thermostat/44/target_temperature',
            'dovit/thermostat/44/mode',
        }
        self.assertEqual(self.cleared(), expected)
        for entry in self.b.mqtt.publish.call_args_list:
            self.assertEqual(entry.kwargs, {'qos': 1, 'retain': True})
            self.assertNotIn('/set', entry.args[0])
            self.assertNotIn('/bridge/', entry.args[0])

    def test_reused_identity_preserved_even_unpublishable_or_invalid_mapping(self):
        self.b.lights[19] = {'name': 'TODO_Light', 'statetype': 'invalid'}
        self.b.shutters[20] = {'name': '', 'position_mode': 'legacy'}
        self.publish(['lights:19', 'shutters:20'])
        self.b.mqtt.publish.assert_not_called()

    def test_reclassification_clears_old_namespace_not_new_owner(self):
        self.b.contacts[19] = {'name': 'Door', 'statetype': 5}
        self.publish(['lights:19', 'contacts:19'])
        self.assertEqual(self.cleared(), {'homeassistant/light/dovit_light_19/config', 'dovit/light/19/state'})
        self.assertNotIn('dovit/contact/19/state', self.cleared())

    def test_shared_thermostat_endpoint_does_not_clear_current_owner_topic(self):
        self.b.thermostats[45] = {'name': '', 'current': {'id': 44, 'statetype': 6}}
        self.publish(['thermostats:44'])
        self.assertIn('dovit/thermostat/44/current_temperature', self.cleared())
        self.assertFalse(any('/45/' in topic for topic in self.cleared()))

    def test_owned_topic_is_protected_independently_of_old_category(self):
        # Exercise topic ownership protection directly, including future reclassifications.
        self.b.contacts[99] = {'name': 'Contact'}
        original = self.b._removed_mapping_state_topics
        self.b._removed_mapping_state_topics = lambda category, dev_id: (
            {'dovit/light/19/state'} if category == 'contacts' else original(category, dev_id))
        self.publish(['lights:19'])
        self.assertEqual(self.cleared(), {'homeassistant/light/dovit_light_19/config'})

    def test_publication_only_never_reads_or_processes_tombstones(self):
        self.b.cfg.enable_discovery = False
        self.b.cfg.publish_discovery = True
        with patch('dovit_bridge.bridge.load_devices', side_effect=AssertionError('tombstone read')):
            self.b.publish_all_discovery_once()
        self.b.mqtt.publish.assert_not_called()
        self.b.reload_device_maps.assert_not_called()

    def test_invalid_unrelated_and_alarm_tombstones_are_ignored(self):
        self.publish([None, {}, 'lights', 'lights:-1', 'lights:abc', 'lights:2:extra',
                      'lights:\u00b2', 'alarms:87', 'status:19', 'commands:19', 'unknown:19'])
        self.b.mqtt.publish.assert_not_called()

    def test_disconnected_mqtt_never_queues_cleanup_and_reconnect_retries(self):
        self.b.mqtt.connected = False
        self.publish(['lights:19'])
        self.b.mqtt.publish.assert_not_called()
        self.b.mqtt.connected = True
        self.publish(['lights:19'])
        self.assertIn('dovit/light/19/state', self.cleared())

    def test_rc_or_exception_failure_keeps_tombstone_retryable(self):
        for failure in ('rc', 'exception'):
            with self.subTest(failure=failure):
                self.b.mqtt.reset_mock()
                def publish(topic, payload, **kwargs):
                    if topic == 'dovit/light/19/state':
                        if failure == 'exception':
                            raise RuntimeError('private payload must not be logged')
                        return SimpleNamespace(rc=4)
                    return SimpleNamespace(rc=0)
                self.b.mqtt.publish.side_effect = publish
                with self.assertLogs('dovit_bridge.bridge', level='ERROR') as logs:
                    self.publish(['lights:19'])
                self.assertNotIn('private payload', '\n'.join(logs.output))
                self.b.mqtt.publish.side_effect = None
                self.b.mqtt.reset_mock()
                self.publish(['lights:19'])
                self.b.mqtt.publish.assert_any_call('dovit/light/19/state', '', qos=1, retain=True)

    def test_reassignment_between_retries_protects_new_mapping(self):
        self.publish(['lights:19'])
        self.b.mqtt.reset_mock()
        self.b.lights[19] = {'name': 'Reused'}
        self.publish(['lights:19'])
        self.b.mqtt.publish.assert_not_called()
