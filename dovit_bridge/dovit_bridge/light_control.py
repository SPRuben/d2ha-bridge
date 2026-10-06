"""Known-light commands only; no persistence, retries or reconnect queue."""
import asyncio
import time
import uuid


def light_frame(dev_id, statetype, action):
    if action not in ('ON', 'OFF'):
        raise ValueError('light_invalid')
    return (f'<hidv-state><device id="{int(dev_id)}"><statetype>{int(statetype)}</statetype>'
            f'<statevalue>{"1.0" if action == "ON" else "0.0"}</statevalue>'
            '<timefleeting>-32768</timefleeting><endvalue>-32768</endvalue>'
            '<speed>-32768</speed></device></hidv-state>')


class LightControl:
    def __init__(self, monitor, loop=None, bridge=None, simulation=False):
        self.monitor, self.loop, self.bridge = monitor, loop, bridge
        self.simulation = simulation

    def submit(self, raw):
        writer = self.bridge.dovit.writer if not self.simulation and self.bridge else None
        if not isinstance(raw, dict) or type(raw.get('id')) is not int or raw.get('action') not in ('ON', 'OFF') or raw.get('confirm') is not True:
            raise ValueError('light_invalid')
        token = raw.get('request_id')
        try:
            uuid.UUID(token)
        except (ValueError, TypeError, AttributeError):
            raise ValueError('light_invalid')
        dev_id, action = raw['id'], raw['action']
        with self.monitor.lock:
            if token in self.monitor.commands:
                return dict(self.monitor.commands[token])
            device = next((d for d in self.monitor.devices if d['uid'] == f'lights:{dev_id}'), None)
            if not device or not device['endpoints']:
                raise ValueError('light_unknown')
            now = time.monotonic()
            if any(c['status'] in ('requested', 'transmitted') and now-c['started'] < 12 for c in self.monitor.commands.values()):
                raise ValueError('light_busy')
            if len(self.monitor.commands) >= 1000:
                raise ValueError('light_limit')
            if not self.simulation and (not self.bridge or not self.monitor.connected):
                raise ValueError('light_disconnected')
            st = device['endpoints'][0][1]
            command = dict(request_id=token, id=dev_id, statetype=st, action=action,
                           status='requested', started=now, after=self.monitor.sequence,
                           simulation=self.simulation, matched=False)
            self.monitor.commands[token] = command
        if self.simulation:
            self._finish(token, True)
            self.monitor.observe(dev_id, st, '1.0' if action == 'ON' else '0.0')
        else:
            asyncio.run_coroutine_threadsafe(self._send(token, writer, now + 2), self.loop)
        return dict(command)

    async def _send(self, token, writer, deadline):
        command = self.monitor.commands[token]
        try:
            if time.monotonic() > deadline or writer is None or writer is not self.bridge.dovit.writer or writer.is_closing():
                self._finish(token, False)
                return
            info = self.bridge.lights.get(command['id'])
            if not info or int(info['statetype']) != command['statetype']:
                self._finish(token, False)
                return
            with self.monitor.lock:
                command['after'] = self.monitor.sequence
                command['matched'] = False
            result = await self.bridge.send_light(command['id'], command['action'], expected_writer=writer)
            self._finish(token, result)
        except Exception:
            self._finish(token, False)

    def _finish(self, token, sent):
        with self.monitor.lock:
            c = self.monitor.commands[token]
            c['status'] = ('observed' if c['matched'] else 'transmitted') if sent else 'failed'
