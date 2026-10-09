import threading
import unittest
from unittest.mock import Mock, call, patch

from dovit_bridge.mqtt_client import MqttWrapper, mqtt
from dovit_bridge.topics import MQTT_STATUS_TOPIC


class MqttTests(unittest.TestCase):
    def make_mock_wrapper(self):
        with patch('dovit_bridge.mqtt_client.mqtt.Client') as factory:
            wrapper = MqttWrapper('broker.invalid', 1883, 'user', 'secret')
        wrapper.client.publish.return_value.rc = mqtt.MQTT_ERR_SUCCESS
        wrapper.client.publish.return_value.is_published.return_value = True
        wrapper.client.loop_start.return_value = mqtt.MQTT_ERR_SUCCESS
        return wrapper

    def test_will_precedes_connect_and_initial_state_is_disconnected(self):
        wrapper = self.make_mock_wrapper()
        self.assertFalse(wrapper.connected)
        wrapper.connect_and_loop()
        calls = wrapper.client.method_calls
        will = call.will_set(MQTT_STATUS_TOPIC, 'offline', qos=1, retain=True)
        connect = call.connect_async('broker.invalid', 1883, 60)
        self.assertIn(will, calls)
        self.assertLess(calls.index(will), calls.index(connect))
        wrapper.client.publish.assert_not_called()

    def test_rejected_connack_never_publishes_online(self):
        wrapper = self.make_mock_wrapper()
        wrapper.on_connect = Mock()
        with self.assertLogs('dovit_bridge.mqtt_client', level='ERROR'):
            wrapper._on_connect(wrapper.client, None, {}, Mock(is_failure=True))
        self.assertFalse(wrapper.connected)
        wrapper.client.publish.assert_not_called()
        wrapper.on_connect.assert_not_called()

    def test_deferred_online_waits_for_snapshot_and_is_idempotent(self):
        wrapper = self.make_mock_wrapper()
        wrapper.defer_online = True
        wrapper.on_connect = Mock()
        wrapper._on_connect(wrapper.client, None, {}, Mock(is_failure=False))
        self.assertTrue(wrapper.connected)
        wrapper.client.publish.assert_called_once_with(MQTT_STATUS_TOPIC, 'offline', retain=True, qos=1)
        wrapper.client.publish('test/current-snapshot', 'offline', retain=True, qos=1)
        self.assertTrue(wrapper.mark_online())
        self.assertTrue(wrapper.mark_online())
        self.assertEqual(wrapper.client.publish.call_args_list, [
            call(MQTT_STATUS_TOPIC, 'offline', retain=True, qos=1),
            call('test/current-snapshot', 'offline', retain=True, qos=1),
            call(MQTT_STATUS_TOPIC, 'online', retain=True, qos=1)])

    def test_deferred_online_failure_retries_and_shutdown_rejects(self):
        wrapper = self.make_mock_wrapper()
        wrapper.connected = True
        wrapper.client.publish.return_value.rc = mqtt.MQTT_ERR_NO_CONN
        with self.assertLogs('dovit_bridge.mqtt_client', level='ERROR'):
            self.assertFalse(wrapper.mark_online())
        wrapper.client.publish.return_value.rc = mqtt.MQTT_ERR_SUCCESS
        self.assertTrue(wrapper.mark_online())
        wrapper._stopping = True
        self.assertFalse(wrapper.mark_online())

    def test_repeated_connections_publish_transport_online_and_forward(self):
        wrapper = self.make_mock_wrapper()
        wrapper.on_connect = Mock(side_effect=lambda *args: self.assertTrue(wrapper.connected))
        for _ in range(2):
            wrapper._on_connect(wrapper.client, None, {}, Mock(is_failure=False))
        self.assertEqual(wrapper.on_connect.call_count, 2)
        self.assertEqual(wrapper.client.publish.call_args_list, [
            call(MQTT_STATUS_TOPIC, 'online', retain=True, qos=1)] * 2)
        wrapper.client.publish.return_value.wait_for_publish.assert_not_called()

    def test_disconnect_forwards_arguments_after_clearing_state(self):
        wrapper = self.make_mock_wrapper()
        wrapper.connected = True
        wrapper.on_disconnect = Mock(side_effect=lambda *args: self.assertFalse(wrapper.connected))
        args = (wrapper.client, None, {}, Mock(), None)
        wrapper._on_disconnect(*args)
        wrapper.on_disconnect.assert_called_once_with(*args)
        wrapper.client.publish.assert_not_called()
        wrapper.connected = True
        wrapper._on_connect_fail(wrapper.client, None)
        self.assertFalse(wrapper.connected)

    def test_online_publish_failure_still_forwards_accepted_connection(self):
        for failure in ('rc', 'exception'):
            with self.subTest(failure=failure):
                wrapper = self.make_mock_wrapper()
                wrapper.on_connect = Mock()
                if failure == 'rc':
                    wrapper.client.publish.return_value.rc = mqtt.MQTT_ERR_NO_CONN
                else:
                    wrapper.client.publish.side_effect = RuntimeError('failure')
                with self.assertLogs('dovit_bridge.mqtt_client', level='ERROR'):
                    wrapper._on_connect(wrapper.client, None, {}, Mock(is_failure=False))
                self.assertTrue(wrapper.connected)
                wrapper.on_connect.assert_called_once()

    def test_stop_orders_offline_bounded_wait_disconnect_and_loop_stop(self):
        wrapper = self.make_mock_wrapper()
        wrapper.connected = True
        wrapper.client.reset_mock()
        wrapper.stop()
        self.assertEqual(wrapper.client.mock_calls, [
            call.publish(MQTT_STATUS_TOPIC, 'offline', retain=True, qos=1),
            call.publish().wait_for_publish(timeout=2.0),
            call.publish().is_published(), call.disconnect(), call.loop_stop()])
        self.assertFalse(wrapper.connected)

    def test_failed_offline_publication_always_cleans_up(self):
        for failure in ('rc', 'publish', 'wait', 'timeout'):
            with self.subTest(failure=failure):
                wrapper = self.make_mock_wrapper()
                wrapper.connected = True
                result = wrapper.client.publish.return_value
                if failure == 'rc':
                    result.rc = mqtt.MQTT_ERR_NO_CONN
                elif failure == 'publish':
                    wrapper.client.publish.side_effect = RuntimeError('failure')
                elif failure == 'wait':
                    result.wait_for_publish.side_effect = RuntimeError('failure')
                else:
                    result.is_published.return_value = False
                with self.assertLogs('dovit_bridge.mqtt_client', level='WARNING'):
                    wrapper.stop()
                wrapper.client.disconnect.assert_called_once()
                wrapper.client.loop_stop.assert_called_once()
                self.assertFalse(wrapper.connected)
                if failure in ('rc', 'publish'):
                    result.wait_for_publish.assert_not_called()

    def test_connack_during_offline_ack_wait_cannot_publish_online(self):
        wrapper = self.make_mock_wrapper()
        wrapper.connected = True
        wrapper.on_connect = Mock()
        accepted = Mock(is_failure=False)

        def concurrent_connack(timeout):
            self.assertEqual(timeout, 2.0)
            thread = threading.Thread(target=wrapper._on_connect,
                                      args=(wrapper.client, None, {}, accepted))
            thread.start()
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertFalse(wrapper.connected)

        wrapper.client.publish.return_value.wait_for_publish.side_effect = concurrent_connack
        wrapper.stop()
        wrapper._on_connect(wrapper.client, None, {}, accepted)
        wrapper.client.publish.assert_called_once_with(
            MQTT_STATUS_TOPIC, 'offline', retain=True, qos=1)
        wrapper.on_connect.assert_not_called()
        self.assertTrue(wrapper._stopping)
        wrapper.client.publish.return_value.wait_for_publish.side_effect = None
        wrapper.connect_and_loop()
        self.assertFalse(wrapper._stopping)
        self.assertFalse(wrapper.connected)
        wrapper._on_connect(wrapper.client, None, {}, accepted)
        self.assertTrue(wrapper.connected)
        wrapper.on_connect.assert_called_once()
        self.assertEqual(wrapper.client.publish.call_args,
                         call(MQTT_STATUS_TOPIC, 'online', retain=True, qos=1))

    def test_unconfirmed_offline_logs_clean_disconnect_caveat(self):
        wrapper = self.make_mock_wrapper()
        wrapper.connected = True
        wrapper.client.publish.return_value.is_published.return_value = False
        with self.assertLogs('dovit_bridge.mqtt_client', level='WARNING') as logs:
            wrapper.stop()
        self.assertIn('offline status unconfirmed', '\n'.join(logs.output))
        self.assertIn('LWT not guaranteed', '\n'.join(logs.output))

    def test_reentrant_connack_during_ack_wait_and_cleanup_are_unlocked(self):
        wrapper = self.make_mock_wrapper()
        wrapper.connected = True
        wrapper.on_connect = Mock()

        def assert_unlocked():
            acquired = wrapper._status_lock.acquire(blocking=False)
            self.assertTrue(acquired)
            if acquired:
                wrapper._status_lock.release()

        def ack_wait(timeout):
            assert_unlocked()
            wrapper._on_connect(wrapper.client, None, {}, Mock(is_failure=False))

        wrapper.client.publish.return_value.wait_for_publish.side_effect = ack_wait
        wrapper.client.disconnect.side_effect = assert_unlocked
        wrapper.client.loop_stop.side_effect = assert_unlocked
        wrapper.stop()
        wrapper.client.publish.assert_called_once_with(
            MQTT_STATUS_TOPIC, 'offline', retain=True, qos=1)
        wrapper.on_connect.assert_not_called()
        self.assertFalse(wrapper.connected)

    def test_status_enqueues_locked_but_forwarded_callbacks_unlocked(self):
        wrapper = self.make_mock_wrapper()
        result = wrapper.client.publish.return_value

        def publish(*args, **kwargs):
            self.assertTrue(wrapper._status_lock.locked())
            return result

        def forwarded(*args):
            self.assertFalse(wrapper._status_lock.locked())

        wrapper.client.publish.side_effect = publish
        wrapper.on_connect = forwarded
        wrapper.on_disconnect = forwarded
        wrapper._on_connect(wrapper.client, None, {}, Mock(is_failure=False))
        wrapper.stop()
        wrapper._on_disconnect(wrapper.client, None, {}, Mock())
        self.assertEqual(wrapper.client.publish.call_args_list, [
            call(MQTT_STATUS_TOPIC, 'online', retain=True, qos=1),
            call(MQTT_STATUS_TOPIC, 'offline', retain=True, qos=1)])

    def test_disconnected_stop_does_not_publish(self):
        wrapper = self.make_mock_wrapper()
        wrapper.stop()
        wrapper.client.publish.assert_not_called()
        wrapper.client.disconnect.assert_called_once()
        wrapper.client.loop_stop.assert_called_once()

    def test_stop_from_callback_is_rejected_without_blocking(self):
        wrapper = self.make_mock_wrapper()
        wrapper.on_connect = lambda *args: wrapper.stop()
        with self.assertRaisesRegex(RuntimeError, 'outside Paho callbacks'):
            wrapper._on_connect(wrapper.client, None, {}, Mock(is_failure=False))
        wrapper.client.publish.return_value.wait_for_publish.assert_not_called()
        wrapper.client.disconnect.assert_not_called()
        wrapper.stop()

    def test_disconnect_exception_still_stops_loop(self):
        wrapper = self.make_mock_wrapper()
        wrapper.client.disconnect.side_effect = RuntimeError('failure')
        with self.assertRaises(RuntimeError):
            wrapper.stop()
        wrapper.client.loop_stop.assert_called_once()
        self.assertFalse(wrapper.connected)

    def test_start_uses_background_connection_and_bounded_backoff(self):
        with patch('dovit_bridge.mqtt_client.mqtt.Client') as factory:
            client = factory.return_value
            client.loop_start.return_value = mqtt.MQTT_ERR_SUCCESS
            wrapper = MqttWrapper('broker.invalid', 1883, 'user', 'secret')
            wrapper.connect_and_loop()
            client.connect.assert_not_called()
            client.connect_async.assert_called_once_with('broker.invalid', 1883, 60)
            client.reconnect_delay_set.assert_called_once_with(min_delay=1, max_delay=30)
            self.assertEqual(client.on_connect_fail, wrapper._on_connect_fail)

    def test_network_thread_start_error_is_not_hidden(self):
        with patch('dovit_bridge.mqtt_client.mqtt.Client') as factory:
            factory.return_value.loop_start.return_value = mqtt.MQTT_ERR_INVAL
            with self.assertRaises(RuntimeError):
                MqttWrapper('broker.invalid', 1883, 'user', 'secret').connect_and_loop()

    def test_refused_initial_connection_is_retried_without_network(self):
        wrapper = MqttWrapper('broker.invalid', 1883, 'user', 'secret')
        retried = threading.Event()
        attempts = []

        def reconnect():
            attempts.append(1)
            if len(attempts) == 1:
                raise ConnectionRefusedError('test broker unavailable')
            # Stop the actual Paho loop after observing its retry.
            wrapper.client.disconnect()
            retried.set()

        with patch.object(wrapper.client, 'reconnect', side_effect=reconnect), \
                patch.object(wrapper.client, '_reconnect_wait'), \
                self.assertLogs('dovit_bridge.mqtt_client', level='WARNING') as logs:
            try:
                wrapper.connect_and_loop()
                self.assertTrue(retried.wait(3), 'Paho did not retry initial failure')
            finally:
                wrapper.client.disconnect()
                wrapper.client.loop_stop()
        self.assertEqual(len(attempts), 2)
        self.assertIn('automatic retry', '\n'.join(logs.output))
        self.assertNotIn('secret', '\n'.join(logs.output))

    def test_success_and_reconnect_forward_subscription_callback(self):
        wrapper = MqttWrapper('broker.invalid', 1883, 'user', 'secret')
        wrapper.on_connect = Mock()
        accepted = Mock(is_failure=False)
        for _ in range(2):
            wrapper._on_connect(wrapper.client, None, {}, accepted)
        self.assertEqual(wrapper.on_connect.call_count, 2)
        with self.assertLogs('dovit_bridge.mqtt_client', level='ERROR'):
            wrapper._on_connect(wrapper.client, None, {}, Mock(is_failure=True))
        self.assertEqual(wrapper.on_connect.call_count, 2)
