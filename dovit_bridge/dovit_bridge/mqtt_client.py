# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import threading
import ssl
from datetime import datetime, timezone
from functools import wraps
LOGGER = logging.getLogger(__name__)

import paho.mqtt.client as mqtt
from typing import Callable, Optional
from .topics import MQTT_STATUS_TOPIC


def _reason_value(reason):
    """Never stringify broker-supplied reason text (which may contain secrets)."""
    value = reason if type(reason) is int else getattr(reason, 'value', None)
    return value if type(value) is int and 0 <= value <= 255 else None


def _paho_callback(callback):
    @wraps(callback)
    def guarded(self, *args, **kwargs):
        previous = getattr(self._callback_context, 'active', False)
        self._callback_context.active = True
        try:
            return callback(self, *args, **kwargs)
        finally:
            self._callback_context.active = previous
    return guarded

class MqttWrapper:
    def __init__(self, host: str, port: int, user: str, password: str,
                 tls: bool = False, protocol: str = '3.1.1'):
        """Optional TLS verifies CA/hostname; protocol is 3.1, 3.1.1, 5 or 5.0."""
        protocols = {'3.1': mqtt.MQTTv31, '3.1.1': mqtt.MQTTv311,
                     '5': mqtt.MQTTv5, '5.0': mqtt.MQTTv5}
        if not isinstance(protocol, str) or protocol not in protocols:
            raise ValueError('mqtt_invalid_protocol')
        if type(tls) is not bool:
            raise ValueError('mqtt_invalid_tls')
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.connected = False
        self.defer_online = False
        self._online_announced = False
        self._stopping = False
        self._status_lock = threading.Lock()
        self._callback_context = threading.local()
        self._diagnostic_state = 'disconnected'
        self._diagnostic_reason = None
        self._last_change = datetime.now(timezone.utc).isoformat()

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  protocol=protocols[protocol])
        if tls:
            self.client.tls_set_context(ssl.create_default_context())
        self.client.username_pw_set(self.user, self.password)
        self.client.will_set(MQTT_STATUS_TOPIC, 'offline', qos=1, retain=True)

        self.on_connect: Optional[Callable] = None
        self.on_message: Optional[Callable] = None
        self.on_disconnect: Optional[Callable] = None

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.client.on_connect_fail = self._on_connect_fail
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def _set_diagnostics(self, state, reason=None):
        # Caller holds _status_lock, shared with connected/shutdown state.
        if (state, reason) != (self._diagnostic_state, self._diagnostic_reason):
            self._diagnostic_state = state
            self._diagnostic_reason = reason
            self._last_change = datetime.now(timezone.utc).isoformat()

    def diagnostics(self):
        """Atomic safe snapshot: state, numeric reason_code, UTC last_change."""
        with self._status_lock:
            return dict(state=self._diagnostic_state,
                        reason_code=self._diagnostic_reason,
                        last_change=self._last_change)

    def connect_and_loop(self):
        with self._status_lock:
            self._stopping = False
            self.connected = False
            self._set_diagnostics('connecting')
        LOGGER.info('Connecting MQTT')
        # Paho retries even the first connection in its network thread.
        try:
            self.client.connect_async(self.host, self.port, 60)
            result = self.client.loop_start()
            if result != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError('mqtt_loop_start_failed')
        except Exception:
            with self._status_lock:
                if not self._stopping:
                    self._set_diagnostics('unreachable')
            raise RuntimeError('mqtt_connection_start_failed') from None

    @_paho_callback
    def _on_connect_fail(self, client, userdata):
        with self._status_lock:
            self.connected = False
            if not self._stopping:
                self._set_diagnostics('unreachable')
        LOGGER.warning("MQTT connection failed; automatic retry with backoff (1-30s)")

    def publish(self, topic: str, payload: str, retain: bool = True, qos: int = 0):
        result = self.client.publish(topic, payload, retain=retain, qos=qos)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.error("MQTT publish failed topic=%s rc=%s", topic, result.rc)
        return result

    def subscribe(self, topic: str):
        result = self.client.subscribe(topic)
        if result[0] != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.error("MQTT subscribe failed topic=%s rc=%s", topic, result[0])
        return result

    def _publish_status(self, payload):
        try:
            return self.publish(MQTT_STATUS_TOPIC, payload, retain=True, qos=1)
        except Exception as exc:
            LOGGER.error("MQTT status publish failed type=%s", type(exc).__name__)
            return None

    def mark_online(self):
        # Bridge startup/reconnect snapshots must precede its available status.
        with self._status_lock:
            if self._stopping or not self.connected:
                return False
            if self._online_announced:
                return True
            result = self._publish_status('online')
            self._online_announced = bool(result is not None and result.rc == mqtt.MQTT_ERR_SUCCESS)
            return self._online_announced

    def stop(self):
        if getattr(self._callback_context, 'active', False):
            raise RuntimeError('MQTT stop must run outside Paho callbacks')
        confirmed = False
        was_connected = False
        try:
            # Only state changes and status enqueue share the CONNACK lock.
            with self._status_lock:
                self._stopping = True
                self._set_diagnostics('stopped')
                was_connected = self.connected
                self.connected = False
                result = self._publish_status('offline') if was_connected else None
            if was_connected:
                if result is not None and result.rc == mqtt.MQTT_ERR_SUCCESS:
                    try:
                        result.wait_for_publish(timeout=2.0)
                        confirmed = result.is_published()
                        if not confirmed:
                            LOGGER.warning('MQTT offline publication acknowledgement timed out')
                    except Exception as exc:
                        LOGGER.error('MQTT offline publication wait failed type=%s', type(exc).__name__)
        finally:
            if was_connected and not confirmed:
                LOGGER.warning('MQTT offline status unconfirmed; graceful disconnect may leave retained online (LWT not guaranteed)')
            with self._status_lock:
                self.connected = False
            try:
                self.client.disconnect()
            finally:
                self.client.loop_stop()

    @_paho_callback
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        with self._status_lock:
            if self._stopping:
                self.connected = False
                LOGGER.info('Ignoring MQTT CONNACK during shutdown')
                return
            reason = _reason_value(reason_code)
            failure = reason != 0 if reason is not None else bool(getattr(reason_code, 'is_failure', True))
            if failure:
                self.connected = False
                self._set_diagnostics('auth_rejected' if reason in (4, 5, 134, 135) else 'rejected', reason)
                LOGGER.error("MQTT connection rejected reason_code=%s", reason)
                return
            self.connected = True
            self._set_diagnostics('connected', reason)
            self._online_announced = False
            LOGGER.info("MQTT connection established")
            result = self._publish_status('offline' if self.defer_online else 'online')
            if not self.defer_online:
                self._online_announced = bool(result is not None and result.rc == mqtt.MQTT_ERR_SUCCESS)
        if self.on_connect:
            self.on_connect(client, userdata, flags, reason_code, properties)

    @_paho_callback
    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        with self._status_lock:
            self.connected = False
            reason = _reason_value(reason_code)
            if not self._stopping and self._diagnostic_state not in ('auth_rejected', 'rejected'):
                self._set_diagnostics('disconnected', reason)
        LOGGER.warning("MQTT disconnected reason_code=%s; network loop handles reconnection", reason)
        if self.on_disconnect:
            self.on_disconnect(client, userdata, disconnect_flags, reason_code, properties)

    @_paho_callback
    def _on_message(self, client, userdata, msg):
        if self.on_message:
            try:
                self.on_message(client, userdata, msg)
            except Exception as exc:
                LOGGER.error("MQTT command handler failed topic=%s type=%s; command not retried",
                             msg.topic, type(exc).__name__)
