import unittest

from dovit_bridge import mqtt_discovery as discovery
from dovit_bridge.topics import (
    MQTT_STATUS_TOPIC, DOVIT_STATUS_TOPIC, ALARM_HOUSE_AVAILABILITY_TOPIC,
    ALARM_STATE_AVAILABILITY_TOPIC_FMT, ALARM_TEXT_AVAILABILITY_TOPIC_FMT,
)


class DiscoveryAvailabilityTests(unittest.TestCase):
    def climate(self):
        return discovery.climate_payload('node', 44, 'Room', 16, 26, .5,
                                         'current', 'target', 'set', 'mode', 'mode/set')

    def assert_availability(self, payload, extra=()):
        self.assertEqual(payload['availability_mode'], 'all')
        self.assertNotIn('availability_topic', payload)
        self.assertEqual(payload['availability'], [
            {'topic': topic, 'payload_available': 'online', 'payload_not_available': 'offline'}
            for topic in (MQTT_STATUS_TOPIC, DOVIT_STATUS_TOPIC, *extra)])

    def test_standard_devices_require_both_transports(self):
        payloads = [discovery.light_payload('node', 19, 'Light'),
                    discovery.cover_payload('node', 20, 'Cover'),
                    discovery.cover_payload('node', 20, 'Cover', position_topic='position',
                                            set_position_topic='set-position'),
                    discovery.motion_payload('node', 7, 'Motion'),
                    discovery.contact_payload('node', 8, 'Contact'), self.climate()]
        for payload in payloads:
            with self.subTest(identity=payload['unique_id']):
                self.assert_availability(payload)

    def test_alarm_sensors_have_separate_configured_id_evidence(self):
        self.assert_availability(discovery.alarm_state_payload('node', 321, 'State'),
                                 (ALARM_STATE_AVAILABILITY_TOPIC_FMT.format(id=321),))
        self.assert_availability(discovery.alarm_text_payload('node', 321, 'Text'),
                                 (ALARM_TEXT_AVAILABILITY_TOPIC_FMT.format(id=321),))
        self.assert_availability(discovery.alarm_panel_payload('node', 'House'),
                                 (ALARM_HOUSE_AVAILABILITY_TOPIC,))

    def test_existing_identity_and_command_contract_remain_stable(self):
        light = discovery.light_payload('node', 19, 'Light')
        self.assertEqual(light['unique_id'], 'dovit_light_19')
        self.assertEqual(light['command_topic'], 'dovit/light/19/set')
        self.assertEqual(light['state_topic'], 'dovit/light/19/state')
        self.assertEqual(light['payload_off'], 'OFF')
        climate = self.climate()
        self.assertEqual(climate['unique_id'], 'dovit_climate_44')
        self.assertEqual(climate['modes'], ['off', 'heat'])
        self.assertEqual(climate['temp_step'], .5)
        self.assertEqual(climate['precision'], .1)
        cover = discovery.cover_payload('node', 20, 'Cover')
        self.assertEqual(cover['state_stopped'], 'stopped')
        self.assertNotIn('position_topic', cover)
        alarm = discovery.alarm_panel_payload('node', 'House')
        self.assertEqual(alarm['unique_id'], 'dovit_alarm_house')
        self.assertEqual(alarm['command_topic'], 'dovit/alarm/house/set')
        self.assertEqual(alarm['supported_features'], ['arm_home', 'arm_away'])

    def test_payloads_do_not_share_mutable_availability_lists(self):
        first = discovery.light_payload('node', 19, 'First')
        second = discovery.light_payload('node', 21, 'Second')
        first['availability'][0]['topic'] = 'changed'
        self.assertEqual(second['availability'][0]['topic'], MQTT_STATUS_TOPIC)

    def test_discovery_topics_and_device_registry_identity_are_unchanged(self):
        self.assertEqual(discovery.discovery_topic('homeassistant', 'climate', 'dovit_climate_44'),
                         'homeassistant/climate/dovit_climate_44/config')
        self.assertEqual(self.climate()['device']['identifiers'], ['node'])
