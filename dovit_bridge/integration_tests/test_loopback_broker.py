"""Opt-in real MQTT tests. Never contact HA, Dovit, or a non-loopback broker."""
import asyncio
import logging
import os
from pathlib import Path
import socket
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--run-loopback' in sys.argv:
    sys.argv.remove('--run-loopback')
    os.environ['DOVIT_RUN_LOOPBACK_MQTT'] = '1'


@unittest.skipUnless(os.environ.get('DOVIT_RUN_LOOPBACK_MQTT') == '1',
                     'Opt in with --run-loopback or DOVIT_RUN_LOOPBACK_MQTT=1')
class LoopbackBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from amqtt.broker import Broker
        import paho.mqtt.client as mqtt
        from dovit_bridge.mqtt_client import MqttWrapper
        self.Broker, self.mqtt, self.Wrapper = Broker, mqtt, MqttWrapper
        self.loop = asyncio.get_running_loop()
        self.clients = []
        self.wrappers = []
        self.children = []
        self.broker = None
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            self.port = reservation.getsockname()[1]
        self.addAsyncCleanup(self.cleanup)
        await self.start_broker()

    async def start_broker(self):
        self.broker = self.Broker({
            'listeners': {'default': {'type': 'tcp', 'bind': f'127.0.0.1:{self.port}'}},
            'plugins': {'amqtt.plugins.authentication.AnonymousAuthPlugin': {'allow_anonymous': True}},
        })
        await asyncio.wait_for(self.broker.start(), 5)

    async def close_client(self, client):
        def close():
            try:
                client.disconnect()
            finally:
                client.loop_stop()
                client._reset_sockets()
        await asyncio.wait_for(asyncio.to_thread(close), 5)
        if client in self.clients:
            self.clients.remove(client)

    async def stop_wrapper(self, wrapper):
        await asyncio.wait_for(asyncio.to_thread(wrapper.stop), 5)
        wrapper.client._reset_sockets()
        if wrapper in self.wrappers:
            self.wrappers.remove(wrapper)

    async def cleanup(self):
        errors = []
        for child in self.children:
            if child.returncode is None:
                child.kill()
            try:
                await asyncio.wait_for(child.wait(), 5)
            except Exception as exc:
                errors.append(exc)
        for wrapper in list(self.wrappers):
            try:
                await self.stop_wrapper(wrapper)
            except Exception as exc:
                errors.append(exc)
        for client in list(self.clients):
            try:
                await self.close_client(client)
            except Exception as exc:
                errors.append(exc)
        if self.broker is not None:
            try:
                await asyncio.wait_for(self.broker.shutdown(), 5)
            except Exception as exc:
                errors.append(exc)
            self.broker = None
        if errors:
            raise RuntimeError(f'Loopback cleanup failed: {errors!r}')

    async def observer(self, topic='dovit/#'):
        queue = asyncio.Queue()
        connected, subscribed = asyncio.Event(), asyncio.Event()
        client = self.mqtt.Client(self.mqtt.CallbackAPIVersion.VERSION2)
        self.clients.append(client)
        def on_connect(client, userdata, flags, reason, properties):
            if not reason.is_failure:
                self.loop.call_soon_threadsafe(connected.set)
        def on_subscribe(*args):
            self.loop.call_soon_threadsafe(subscribed.set)
        def on_message(client, userdata, msg):
            self.loop.call_soon_threadsafe(queue.put_nowait,
                                          (msg.topic, msg.payload.decode(), msg.retain, msg.qos))
        client.on_connect, client.on_subscribe, client.on_message = on_connect, on_subscribe, on_message
        await asyncio.wait_for(asyncio.to_thread(client.connect, '127.0.0.1', self.port, 10), 5)
        client.loop_start()
        await asyncio.wait_for(connected.wait(), 5)
        self.assertEqual(client.subscribe(topic, qos=1)[0], 0)
        await asyncio.wait_for(subscribed.wait(), 5)
        return client, queue

    async def receive(self, queue, topic, payload, timeout=8):
        async def find():
            while True:
                item = await queue.get()
                if item[:2] == (topic, payload):
                    return item
        return await asyncio.wait_for(find(), timeout)

    def wrapper(self):
        wrapper = self.Wrapper('127.0.0.1', self.port, 'loopback', 'loopback')
        self.wrappers.append(wrapper)
        return wrapper

    async def test_retained_online_and_graceful_offline_real_puback(self):
        wrapper = self.wrapper()
        _, live = await self.observer('dovit/bridge/mqtt/status')
        wrapper.connect_and_loop()
        live_online = await self.receive(live, 'dovit/bridge/mqtt/status', 'online')
        self.assertEqual(live_online[3], 1)
        _, retained = await self.observer('dovit/bridge/mqtt/status')
        msg = await self.receive(retained, 'dovit/bridge/mqtt/status', 'online')
        self.assertTrue(msg[2])
        # aMQTT 0.12 retained snapshot delivery may use QoS 0; publisher uses QoS 1.
        # Capture the real MQTTMessageInfo used by production stop(), not a mock ACK.
        original = wrapper.publish
        infos = []
        def capture(topic, payload, **kwargs):
            info = original(topic, payload, **kwargs)
            if payload == 'offline':
                infos.append(info)
            return info
        wrapper.publish = capture
        await self.stop_wrapper(wrapper)
        self.assertEqual(len(infos), 1)
        self.assertTrue(infos[0].is_published(), 'graceful offline did not receive PUBACK')
        await self.receive(live, 'dovit/bridge/mqtt/status', 'offline')
        _, retained = await self.observer('dovit/bridge/mqtt/status')
        msg = await self.receive(retained, 'dovit/bridge/mqtt/status', 'offline')
        self.assertTrue(msg[2])

    async def test_abrupt_process_exit_publishes_retained_lwt(self):
        _, live = await self.observer('dovit/bridge/mqtt/status')
        child = await asyncio.create_subprocess_exec(
            sys.executable, str(Path(__file__).with_name('will_child.py')), str(self.port),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, cwd=str(ROOT))
        self.children.append(child)
        self.assertEqual(await asyncio.wait_for(child.stdout.readline(), 10), b'READY\r\n' if os.name == 'nt' else b'READY\n')
        await self.receive(live, 'dovit/bridge/mqtt/status', 'online')
        child.kill()
        await asyncio.wait_for(child.wait(), 5)
        await self.receive(live, 'dovit/bridge/mqtt/status', 'offline')
        _, retained = await self.observer('dovit/bridge/mqtt/status')
        self.assertTrue((await self.receive(retained, 'dovit/bridge/mqtt/status', 'offline'))[2])

    async def test_broker_restart_discards_in_memory_retained_cache(self):
        client, queue = await self.observer('integration/cache_probe')
        info = client.publish('integration/cache_probe', 'before_restart', qos=1, retain=True)
        await asyncio.wait_for(asyncio.to_thread(info.wait_for_publish, 2), 3)
        self.assertTrue(info.is_published())
        await self.receive(queue, 'integration/cache_probe', 'before_restart')
        await self.close_client(client)
        await asyncio.wait_for(self.broker.shutdown(), 5)
        self.broker = None
        await self.start_broker()
        _, queue = await self.observer('integration/cache_probe')
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), 0.5)

    async def test_removed_retained_state_cleanup_preserves_owned_and_unrelated_records(self):
        from dovit_bridge.bridge import DovitBridge
        wrapper = self.wrapper()
        _, status = await self.observer('dovit/bridge/mqtt/status')
        wrapper.connect_and_loop()
        await self.receive(status, 'dovit/bridge/mqtt/status', 'online')
        retired = {
            'homeassistant/light/dovit_light_19/config': '{"unique_id":"dovit_light_19"}',
            'dovit/light/19/state': 'ON',
            'homeassistant/climate/dovit_climate_44/config': '{"unique_id":"dovit_climate_44"}',
            'dovit/thermostat/44/current_temperature': '20.1250',
            'dovit/thermostat/44/target_temperature': '22.50',
            'dovit/thermostat/44/mode': 'heat',
        }
        preserved = {
            'homeassistant/light/dovit_light_20/config': '{"unique_id":"dovit_light_20"}',
            'dovit/light/20/state': 'OFF',
            # This is a test-only topic, never an actual bridge command subscription.
            'integration/unrelated/set': 'command_sentinel',
            'integration/unrelated/state': 'unrelated_state',
            'dovit/bridge/dovit/status': 'status_sentinel',
        }
        seeds = dict(retired, **preserved)
        for topic, payload in seeds.items():
            info = wrapper.publish(topic, payload, qos=1, retain=True)
            await asyncio.wait_for(asyncio.to_thread(info.wait_for_publish, 2), 3)
            self.assertTrue(info.is_published())

        async def snapshot(expected):
            client, queue = await self.observer([(topic, 1) for topic in seeds])
            received = {}
            async def gather():
                while not set(expected).issubset(received):
                    topic, payload, retain, qos = await queue.get()
                    if topic not in seeds:
                        continue
                    self.assertTrue(retain)
                    received[topic] = payload
            await asyncio.wait_for(gather(), 5)
            # Allow unexpected retained records to arrive, rather than accepting
            # the first preserved sentinel as evidence that deleted topics are gone.
            deadline = self.loop.time() + 0.5
            while self.loop.time() < deadline:
                try:
                    topic, payload, retain, qos = await asyncio.wait_for(
                        queue.get(), max(0.001, deadline - self.loop.time()))
                    if topic not in seeds:
                        continue
                    self.assertTrue(retain)
                    received[topic] = payload
                except asyncio.TimeoutError:
                    break
            self.assertEqual(received, expected)

        await snapshot(seeds)
        b = DovitBridge.__new__(DovitBridge)
        b.cfg = SimpleNamespace(enable_discovery=False, publish_discovery=True,
                                publish_todo_entities=False, discovery_prefix='homeassistant',
                                devices_file='mock-only.json')
        b.mqtt = wrapper
        b.reload_device_maps = Mock()
        for category in ('lights', 'shutters', 'motions', 'contacts', 'thermostats', 'alarms'):
            setattr(b, category, {})
        b.lights[20] = {'name': 'Reused mapping', 'statetype': 0}
        for method in ('publish_light_discovery', 'publish_cover_discovery',
                       'publish_motion_discovery', 'publish_contact_discovery',
                       'publish_alarm_discovery', 'publish_alarm_house_discovery',
                       'publish_combined_alarm_state'):
            setattr(b, method, Mock())
        self.assertFalse(hasattr(b, 'dovit'))
        with patch('dovit_bridge.bridge.load_devices', side_effect=AssertionError('publish-only disk read')):
            b.publish_all_discovery_once('publication-only guard')
        b.reload_device_maps.assert_not_called()
        await snapshot(seeds)
        b.cfg.enable_discovery = True
        b.cfg.publish_discovery = False
        document = {'_removed_discovery': ['lights:19', 'thermostats:44', 'lights:20']}
        deletion_client, deletion_queue = await self.observer([(topic, 1) for topic in retired])
        original_publish = wrapper.publish
        cleanup_infos = []
        def capture(topic, payload, **kwargs):
            info = original_publish(topic, payload, **kwargs)
            cleanup_infos.append((topic, payload, kwargs, info))
            return info
        wrapper.publish = capture
        with patch('dovit_bridge.bridge.load_devices', return_value=document), \
                patch('dovit_bridge.bridge.save_devices') as save:
            b.publish_all_discovery_once('real loopback cleanup')
            save.assert_not_called()
        self.assertEqual({topic for topic, payload, kwargs, info in cleanup_infos}, set(retired))
        for topic, payload, kwargs, info in cleanup_infos:
            self.assertEqual(payload, '')
            self.assertEqual(kwargs, {'qos': 1, 'retain': True})
            await asyncio.wait_for(asyncio.to_thread(info.wait_for_publish, 2), 3)
            self.assertTrue(info.is_published(), f'cleanup PUBACK missing: {topic}')
        async def wait_for_deletions():
            remaining = set(retired)
            while remaining:
                topic, payload, retain, qos = await deletion_queue.get()
                if payload == '':
                    remaining.discard(topic)
        # aMQTT PUBACK can precede its broker application processing. Observe
        # every real empty publication before testing a fresh retained snapshot.
        await asyncio.wait_for(wait_for_deletions(), 8)
        await snapshot(preserved)
        self.assertEqual(document['_removed_discovery'], ['lights:19', 'thermostats:44', 'lights:20'])

    async def test_bridge_replays_fake_received_state_before_online_after_cache_loss(self):
        from dovit_bridge.bridge import DovitBridge
        b = DovitBridge.__new__(DovitBridge)
        b.loop = self.loop
        b.cfg = SimpleNamespace(enable_discovery=False, publish_discovery=False,
                                frame_sep=b'\0', cover_position_mode='legacy')
        b.monitor = Mock()
        b.mqtt = self.wrapper()
        b.mqtt.client.reconnect_delay_set(min_delay=5, max_delay=5)
        b.mqtt.defer_online = True
        b.mqtt.on_connect = b.on_connect
        b.lights = {19: {'statetype': 0}}
        b.thermostats = {44: {'target': {'statetype': 1}, 'current': {'id': 42, 'statetype': 6}}}
        for name in ('shutters', 'motions', 'contacts', 'alarms'):
            setattr(b, name, {})
        b.alarm_partition_raw_states = {}
        b.alarm_partition_triggered = set()
        b.pending_alarm_house_state = None
        b._state_cache = {}
        b._session_diagnostics_dirty = True
        b._dovit_connected = False
        b.set_dovit_connected(True)
        data = (b'<hidv-state><device id="19"><statetype>0</statetype>'
                b'<statevalue>1</statevalue></device></hidv-state>\0'
                b'<hidv-state><device id="42"><statetype>6</statetype>'
                b'<statevalue>20.1250</statevalue></device></hidv-state>\0')
        b.dovit = SimpleNamespace(read=AsyncMock(side_effect=[data, RuntimeError('fake end')]))
        with self.assertRaisesRegex(RuntimeError, 'fake end'):
            await b.dovit_read_loop()
        self.assertEqual(len(b._state_cache), 2)
        for cycle in range(2):
            _, queue = await self.observer()
            if cycle == 0:
                b.mqtt.connect_and_loop()
            observed = []
            async def until_online():
                while True:
                    item = await queue.get()
                    observed.append(item)
                    if item[:2] == ('dovit/bridge/mqtt/status', 'online'):
                        return
            await asyncio.wait_for(until_online(), 8)
            self.assertEqual(observed[0][:2], ('dovit/bridge/mqtt/status', 'offline'))
            self.assertIn(('dovit/light/19/state', 'ON' if cycle == 0 else 'OFF'),
                          [item[:2] for item in observed[:-1]])
            self.assertIn(('dovit/thermostat/44/current_temperature', '20.1250' if cycle == 0 else '21.25'),
                          [item[:2] for item in observed[:-1]])
            self.assertFalse(any('/set' in item[0] for item in observed))
            for client in list(self.clients):
                await self.close_client(client)
            if cycle == 0:
                await asyncio.wait_for(self.broker.shutdown(), 5)
                self.broker = None
                async def until_disconnected():
                    while b.mqtt.connected:
                        await asyncio.sleep(0.02)
                await asyncio.wait_for(until_disconnected(), 5)
                # The bridge keeps its Dovit session while the real MQTT broker
                # is down. New received values must replace the old snapshot.
                b._publish_received_state('dovit/light/19/state', 'OFF', 19, 0)
                b._publish_received_state('dovit/thermostat/44/current_temperature', '21.25', 42, 6)
                await self.start_broker()
            else:
                await self.stop_wrapper(b.mqtt)


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    unittest.main(verbosity=2)
