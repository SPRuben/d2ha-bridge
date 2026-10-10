"""Confirmed tests for mapped covers and thermostats. No alarm commands/retries."""
import asyncio
from copy import deepcopy
import logging
import math
import time
import uuid

LOGGER = logging.getLogger(__name__)


def plan(raw, maps):
    category, key, action = raw.get('category'), raw.get('id'), raw.get('action')
    if category not in ('shutters', 'thermostats') or type(key) is not int:
        raise ValueError('control_invalid')
    info = maps.get(category, {}).get(key)
    if not info:
        raise ValueError('light_unknown')
    if category == 'shutters':
        if action not in ('OPEN', 'STOP', 'CLOSE'):
            raise ValueError('control_invalid')
        dev_id, state_st = key, int(info['statetype'])
        command_st = int(info.get('command_statetype', state_st))
        value = {'OPEN': 1.0, 'STOP': 0.0, 'CLOSE': 2.0}[action]
    else:
        if action == 'TEMPERATURE':
            value = raw.get('value')
            lo, hi, step = (float(info.get(k, default)) for k, default in
                            [('min_temp', 5), ('max_temp', 35), ('temp_step', .5)])
            if (type(value) not in (int, float) or not all(math.isfinite(v) for v in (value, lo, hi, step))
                    or step <= 0 or not lo <= value <= hi or abs(value/step-round(value/step)) > 1e-6):
                raise ValueError('control_temperature')
            endpoint = info.get('target', {})
        elif action in ('heat', 'off'):
            endpoint = info.get('mode', {})
            value = 1.0 if action == 'heat' else 0.0
        else:
            raise ValueError('control_invalid')
        if 'statetype' not in endpoint or (action != 'TEMPERATURE' and 'id' not in endpoint):
            raise ValueError('control_invalid')
        dev_id, state_st = int(endpoint.get('id', key)), int(endpoint['statetype'])
        command_st = state_st
    if min(dev_id, state_st, command_st) < 0 or (dev_id, command_st) == (39, 111):
        raise ValueError('control_invalid')
    return dict(id=dev_id, statetype=state_st, command_statetype=command_st, expected=value,
                category=category, device_key=key, action=action)


class DeviceControl:
    def __init__(self, monitor, loop=None, bridge=None, simulation=False, maps=None):
        self.monitor, self.loop, self.bridge = monitor, loop, bridge
        self.simulation, self.maps = simulation, maps or {}

    def current_maps(self):
        return self.maps if self.simulation else {k: getattr(self.bridge, k) for k in ('shutters', 'thermostats')}

    def submit(self, raw):
        writer = self.bridge.dovit.writer if not self.simulation and self.bridge else None
        if not isinstance(raw, dict) or raw.get('confirm') is not True:
            raise ValueError('control_invalid')
        token = raw.get('request_id')
        try:
            uuid.UUID(token)
        except (ValueError, TypeError, AttributeError):
            raise ValueError('control_invalid')
        if not self.simulation and (not self.bridge or not self.monitor.connected or not self.loop):
            raise ValueError('light_disconnected')
        with self.monitor.lock:
            if token in self.monitor.commands:
                return dict(self.monitor.commands[token])
            command = plan(raw, self.current_maps())
            now = time.monotonic()
            stop = command['category'] == 'shutters' and command['action'] == 'STOP'
            busy = [c for c in self.monitor.commands.values() if c['status'] in ('requested', 'transmitted') and now-c['started'] < 12]
            if busy and not stop:
                raise ValueError('light_busy')
            if len(self.monitor.commands) >= 1000:
                raise ValueError('light_limit')
            # A STOP supersedes queued tests for this cover and is never blocked by a moving test.
            if stop:
                for c in busy:
                    if c.get('category') == 'shutters' and c.get('device_key') == command['device_key']:
                        c['status'] = 'failed'
            original = deepcopy(self.current_maps()[command['category']][command['device_key']])
            command.update(request_id=token, status='requested', started=now, after=self.monitor.sequence,
                           matched=False, simulation=self.simulation)
            self.monitor.commands[token] = command
        if self.simulation:
            self.finish(command, True)
            self.monitor.observe(command['id'], command['statetype'], str(command['expected']))
        else:
            coroutine = self.send(command, original, writer, now+2)
            try:
                asyncio.run_coroutine_threadsafe(coroutine, self.loop)
            except Exception:
                coroutine.close()
                self.finish(command, False)
                LOGGER.exception('Web device test scheduling failed')
        return dict(command)

    def finish(self, command, sent):
        with self.monitor.lock:
            if command['status'] == 'failed':
                return
            command['status'] = ('observed' if command['matched'] else 'transmitted') if sent else 'failed'

    async def send(self, c, original, writer, deadline):
        try:
            if (c['status'] != 'requested' or time.monotonic() > deadline or writer is None
                    or writer is not self.bridge.dovit.writer or writer.is_closing()
                    or self.current_maps()[c['category']].get(c['device_key']) != original):
                self.finish(c, False)
                return
            if c['category'] == 'shutters':
                runtime = self.bridge.cover_runtime.get(c['device_key'])
                if runtime:
                    direction = {'OPEN': 'opening', 'CLOSE': 'closing'}.get(c['action'])
                    if direction and (runtime.pending_direction or runtime.direction not in (None, direction)):
                        raise ValueError('Stop the cover before reversing a test')
                    self.bridge.cancel_cover_stop_task(runtime)
                    runtime.pending_direction = None
                    runtime.target_position = None
                    runtime.stop_for_target = False
            with self.monitor.lock:
                c['after'], c['matched'] = self.monitor.sequence, False
            xml = (f'<hidv-state><device id="{c["id"]}"><statetype>{c["command_statetype"]}</statetype>'
                   f'<statevalue>{c["expected"]}</statevalue><timefleeting>-32768</timefleeting>'
                   '<endvalue>-32768</endvalue><speed>-32768</speed></device></hidv-state>')
            LOGGER.info('Web test category=%s id=%s action=%s value=%s', c['category'], c['id'], c['action'], c['expected'])
            self.finish(c, await self.bridge.send_frame(xml, expected_writer=writer))
        except Exception:
            LOGGER.exception('Web device test failed')
            self.finish(c, False)
