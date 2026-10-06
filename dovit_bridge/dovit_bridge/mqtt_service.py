"""Resolve MQTT in memory, separately from load_config and persisted options.

resolve_mqtt_config(cfg) returns dataclasses.replace(cfg, ...). Manual mode
never performs I/O; supervisor mode makes one authenticated GET to the official
service endpoint, with no redirect, proxy, retry or automatic manual fallback.
MqttServiceError.key/str contain only fixed keys, never remote error details.
Startup integration belongs to the caller. Other diagnostic/log exporters must
redact mqtt_user, mqtt_pass, alarm_code and SUPERVISOR_TOKEN locally as well.
"""
from dataclasses import replace
import http.client
import json
import os
import time

from .options import mqtt_config_options

SERVICE_TIMEOUT = 5.0
SERVICE_RESPONSE_LIMIT = 16384
SERVICE_URL = "http://supervisor/services/mqtt"
ERROR_KEYS = frozenset({
    "mqtt_invalid_config", "mqtt_supervisor_token_missing",
    "mqtt_supervisor_token_invalid", "mqtt_supervisor_auth_rejected",
    "mqtt_service_unavailable", "mqtt_service_timeout",
    "mqtt_service_response_too_large", "mqtt_service_invalid_response",
})


class MqttServiceError(RuntimeError):
    """Stable, safe UI/log key. Do not attach upstream exceptions or bodies."""

    def __init__(self, key: str):
        self.key = key if key in ERROR_KEYS else "mqtt_service_invalid_response"
        super().__init__(self.key)


def _service_data(token: str) -> dict:
    connection = None
    deadline = time.monotonic() + SERVICE_TIMEOUT
    try:
        connection = http.client.HTTPConnection("supervisor", timeout=SERVICE_TIMEOUT)
        connection.request("GET", "/services/mqtt", headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
        })
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        transport_socket = connection.sock
        transport_socket.settimeout(remaining)
        with connection.getresponse() as response:
            if response.status in (401, 403):
                raise MqttServiceError("mqtt_supervisor_auth_rejected")
            if response.status != 200:
                raise MqttServiceError("mqtt_service_unavailable")
            body = bytearray()
            while True:
                # Reading the final Content-Length bytes may close the response
                # socket immediately (HTTP/1.0 or Connection: close). Do not set
                # another timeout on that closed socket after a complete body.
                if response.isclosed():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                # The response can own the socket after Connection: close.
                transport_socket.settimeout(remaining)
                chunk = response.read1(min(4096, SERVICE_RESPONSE_LIMIT + 1 - len(body)))
                body.extend(chunk)
                if len(body) > SERVICE_RESPONSE_LIMIT:
                    raise MqttServiceError("mqtt_service_response_too_large")
                if not chunk:
                    break
            if response.length not in (None, 0):
                raise MqttServiceError("mqtt_service_invalid_response")
            envelope = json.loads(body)
        if not isinstance(envelope, dict):
            raise MqttServiceError("mqtt_service_invalid_response")
        if envelope.get("result") != "ok":
            raise MqttServiceError("mqtt_service_unavailable")
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise MqttServiceError("mqtt_service_invalid_response")
        return data
    except MqttServiceError:
        raise
    except TimeoutError:
        raise MqttServiceError("mqtt_service_timeout") from None
    except (ValueError, UnicodeError, TypeError):
        raise MqttServiceError("mqtt_service_invalid_response") from None
    except Exception:
        raise MqttServiceError("mqtt_service_unavailable") from None
    finally:
        try:
            if connection is not None:
                connection.close()
        except Exception:
            pass


def _connection_fields(host, port, user, password, tls, protocol) -> dict:
    if (not isinstance(host, str) or not host.strip()
            or any(ord(c) < 33 for c in host) or len(host) > 253
            or not isinstance(user, str) or not isinstance(password, str)):
        raise MqttServiceError("mqtt_invalid_config")
    if isinstance(port, str) and len(port) <= 10 and port.isascii() and port.isdecimal():
        port = int(port)
    if type(port) is not int or not 1 <= port <= 65535:
        raise MqttServiceError("mqtt_invalid_config")
    try:
        fields = mqtt_config_options({"mqtt_tls": tls, "mqtt_protocol": protocol})
    except ValueError:
        raise MqttServiceError("mqtt_invalid_config") from None
    fields.pop("mqtt_mode")
    return dict(fields, mqtt_host=host, mqtt_port=port, mqtt_user=user, mqtt_pass=password)


def resolve_mqtt_config(cfg):
    """Return a resolved Config copy or raise MqttServiceError; never persist."""
    if cfg.mqtt_mode == "manual":
        return replace(cfg, **_connection_fields(
            cfg.mqtt_host, cfg.mqtt_port, cfg.mqtt_user, cfg.mqtt_pass,
            cfg.mqtt_tls, cfg.mqtt_protocol))
    if cfg.mqtt_mode != "supervisor":
        raise MqttServiceError("mqtt_invalid_config")
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        raise MqttServiceError("mqtt_supervisor_token_missing")
    if len(token) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise MqttServiceError("mqtt_supervisor_token_invalid")
    data = _service_data(token)
    try:
        fields = _connection_fields(data["host"], data["port"],
                                    data["username"], data["password"],
                                    data["ssl"], data["protocol"])
    except (KeyError, MqttServiceError):
        raise MqttServiceError("mqtt_service_invalid_response") from None
    return replace(cfg, **fields)
