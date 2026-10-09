"""Local-only subprocess used to exercise an ungraceful MQTT client exit."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dovit_bridge.mqtt_client import MqttWrapper


if __name__ == '__main__':
    wrapper = MqttWrapper('127.0.0.1', int(sys.argv[1]), 'loopback', 'loopback')
    wrapper.connect_and_loop()
    deadline = time.monotonic() + 8
    while not wrapper.connected and time.monotonic() < deadline:
        time.sleep(0.02)
    if not wrapper.connected:
        raise SystemExit('Loopback MQTT connection timed out')
    print('READY', flush=True)
    # Parent kills this process without MQTT DISCONNECT to provoke its LWT.
    while True:
        time.sleep(1)
