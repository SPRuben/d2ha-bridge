"""Bounded candidate archive, independent of device maps and live events."""
import asyncio
from collections import OrderedDict
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import tempfile

LOGGER = logging.getLogger(__name__)


class CandidateStore:
    def __init__(self, monitor, path):
        self.monitor = monitor
        self.path = Path(path)
        self.blocked = False
        self.last_saved = None

    def load(self):
        try:
            if not self.path.exists():
                self.monitor.persistence_status = 'ready'
                return
            if self.path.stat().st_size > 64_000_000:
                raise ValueError('archive too large')
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data['version'] != 1 or not isinstance(data['candidates'], list) or len(data['candidates']) > 2000:
                raise ValueError('invalid schema')
            candidates = OrderedDict()
            for item in data['candidates']:
                for field in ('device_id', 'statetype', 'count'):
                    if type(item[field]) is not int:
                        raise ValueError('invalid integer')
                if item['count'] < 1:
                    raise ValueError('invalid count')
                for field in ('time', 'first_seen'):
                    if datetime.fromisoformat(item[field]).tzinfo is None:
                        raise ValueError('missing timezone')
                if not isinstance(item['value'], str) or not isinstance(item['values'], list) or len(item['values']) > 20 or not all(isinstance(v, str) for v in item['values']):
                    raise ValueError('invalid values')
                key = f"{item['device_id']}:{item['statetype']}"
                if key in candidates:
                    raise ValueError('duplicate candidate')
                candidates[key] = dict(key=key, device_id=item['device_id'], statetype=item['statetype'],
                    count=item['count'], time=item['time'], first_seen=item['first_seen'],
                    value=self.monitor.safe(item['value']), values=[self.monitor.safe(v) for v in item['values']],
                    seq=0, kind='historical', previous=None, provenance='candidate_archive')
            with self.monitor.lock:
                self.monitor.candidates = candidates
            self.monitor.persistence_status = 'ready'
            LOGGER.info('Loaded candidate archive count=%s', len(candidates))
        except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError):
            self.blocked = True
            self.monitor.persistence_status = 'blocked'
            LOGGER.error('Candidate archive unreadable/invalid; file preserved, writes disabled')

    def save(self):
        if self.blocked:
            return
        with self.monitor.lock:
            data = json.dumps(dict(version=1, candidates=list(self.monitor.candidates.values())), ensure_ascii=True)
        if data == self.last_saved:
            return
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix=self.path.name + '.', suffix='.tmp', delete=False) as stream:
                temporary = stream.name
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.last_saved = data
            self.monitor.persistence_status = 'saved'
        except OSError:
            self.monitor.persistence_status = 'error'
            LOGGER.error('Candidate archive save failed; retry on next interval')
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    async def run(self):
        while True:
            await asyncio.sleep(5)
            await asyncio.to_thread(self.save)
