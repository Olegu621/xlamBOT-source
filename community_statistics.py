"""Voluntary anonymous aggregates. No gameplay thread performs network IO."""
import csv
from collections import deque
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid

from error_telemetry import DEFAULT_ENDPOINT, endpoint_url


class CommunityStatistics:
    def __init__(self, root, data_root, status_provider, revision=0, session=None, endpoint=DEFAULT_ENDPOINT):
        self.root, self.data_root = Path(root), Path(data_root)
        self.provider, self.revision = status_provider, revision
        self.session, self.endpoint = session, endpoint_url(endpoint)
        self.lock = threading.RLock()
        self.wake, self.stopped = threading.Event(), threading.Event()
        self.enabled, self.clear_presence = True, False
        self.salt, self.credentials, self.cursors = uuid.uuid4().hex, {}, {}
        self.recent_ids = []
        self.last_sent, self.sent_matches, self.state, self.epoch = None, 0, 'ready', 0
        self.thread = None
        try:
            saved = json.loads((self.root/'state.json').read_text('utf-8'))
            if isinstance(saved, dict):
                self.enabled = saved.get('enabled') is True
                if re.fullmatch('[a-f0-9]{32}', str(saved.get('salt'))): self.salt = saved['salt']
                c = saved.get('credentials', {})
                if (isinstance(c, dict) and c.get('endpoint') == self.endpoint and
                        re.fullmatch('[a-f0-9]{64}', str(c.get('token'))) and
                        re.fullmatch('[a-f0-9]{32}', str(c.get('installation')))):
                    self.credentials = c
                self.cursors = {k:v for k,v in saved.get('cursors', {}).items() if isinstance(k,str) and type(v) is int and v>=0}
                ids = saved.get('recent_ids', [])
                if isinstance(ids, list):
                    self.recent_ids = [v for v in ids[-2048:] if isinstance(v,str) and re.fullmatch('[a-f0-9]{32}',v)]
                self.last_sent = saved.get('last_sent')
                self.sent_matches = max(0, int(saved.get('sent_matches', 0)))
                self.state = 'ready' if self.enabled else 'disabled'
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError):
            self.enabled = False

    def _save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root/'state.tmp'
        temporary.write_text(json.dumps({key:getattr(self,key) for key in
            ('enabled','salt','credentials','cursors','recent_ids','last_sent','sent_matches')}), 'utf-8')
        os.replace(temporary, self.root/'state.json')

    def configure(self, enabled):
        if type(enabled) is not bool: raise ValueError('Choose a valid statistics preference.')
        with self.lock:
            previous = (self.enabled, self.clear_presence, self.epoch, self.state)
            if self.enabled != enabled:
                self.epoch += 1
                self.clear_presence = not enabled
            self.enabled = enabled
            self.state = 'ready' if enabled else 'disabled'
            try:
                self._save()
            except OSError:
                self.enabled, self.clear_presence, self.epoch, self.state = previous
                raise
        self.wake.set()
        return self.status()

    def status(self):
        with self.lock:
            return {'enabled':self.enabled, 'state':self.state, 'last_sent':self.last_sent, 'sent_matches':self.sent_matches}

    def anonymous(self, value):
        return hashlib.sha256((self.salt+'\0'+value).encode()).hexdigest()[:32]

    def history_batch(self):
        """Prioritize recent results and fairly backfill every device after acknowledgement."""
        paths = [self.data_root/'cfg/match_history.csv']
        paths += sorted((self.data_root/'devices').glob('*/cfg/match_history.csv'))[:128]
        cursors, recent, backlog = dict(self.cursors), [], []
        now = time.time()
        for path in paths:
            if not path.is_file() or not path.resolve().is_relative_to(self.data_root.resolve()): continue
            key = path.relative_to(self.data_root).as_posix()
            start, count, duplicates = cursors.get(key, 0), 0, {}
            tail, older = deque(maxlen=20), deque()
            try:
                with path.open('r', encoding='utf-8-sig', newline='') as file:
                    for index, row in enumerate(csv.DictReader(file)):
                        count = index+1
                        identity = json.dumps([key]+[row.get(k,'') for k in ('date_time','account_tag','brawler_name','result')], ensure_ascii=False)
                        identity_key = hashlib.sha256(identity.encode()).digest()
                        occurrence = duplicates.get(identity_key, 0)
                        duplicates[identity_key] = occurrence+1
                        try:
                            played = datetime.fromisoformat(row['date_time']).timestamp()
                            if not 1262304000<=played<=now+300 or row.get('result') not in {'victory','defeat','draw'}: continue
                            raw = row.get('trophy_delta','')
                            delta = float(raw) if raw.strip() else None
                            if delta is not None and (not math.isfinite(delta) or not delta.is_integer() or abs(delta)>1000): continue
                            source = row.get('trophy_source','unknown')
                            source = source if source in {'observed','estimated'} else 'unknown'
                            match = {'id':self.anonymous(identity+'\0'+str(occurrence)), 'played':played,
                                'result':row['result'], 'delta':int(delta) if delta is not None and source!='unknown' else None, 'source':source}
                            tail.append(match)
                            if index>=start and len(older)<50: older.append((count,match))
                        except (ValueError, TypeError, KeyError, OverflowError, OSError): continue
                if count<start: cursors[key] = 0  # Stable IDs prevent duplicates after truncation/rebuild.
                elif not older: cursors[key] = count
                recent.extend(tail)
                backlog.append((key,older))
            except (OSError, UnicodeError, csv.Error): continue
        acknowledged = set(self.recent_ids)
        matches, selected = [], set()
        for match in sorted(recent, key=lambda m:m['played'], reverse=True):
            if match['id'] not in acknowledged and match['id'] not in selected:
                matches.append(match);selected.add(match['id'])
            if len(matches)==20: break
        while len(matches)<50 and any(rows for _,rows in backlog):
            for key, rows in backlog:
                if not rows: continue
                position, match = rows.popleft()
                cursors[key] = position
                if match['id'] not in selected and match['id'] not in acknowledged:
                    matches.append(match);selected.add(match['id'])
                if len(matches)==50: break
        return matches, cursors

    def _post(self, route, body, token=None):
        if self.session is None:
            import requests
            self.session = requests.Session()
        headers = {'Authorization':'Bearer '+token} if token else {}
        response = self.session.post(self.endpoint+route, json=body, headers=headers, timeout=(3,10), allow_redirects=False)
        if response.status_code not in (200,202): raise ValueError('Statistics upload unavailable')
        return response.json()

    def sync(self):
        with self.lock:
            enabled, clear, epoch = self.enabled, self.clear_presence, self.epoch
            if not enabled and not clear: return
            credentials = dict(self.credentials)
        if not credentials:
            if not enabled: return
            data = self._post('/v1/register', {})
            if not re.fullmatch('[a-f0-9]{64}', str(data.get('token'))) or not re.fullmatch('[a-f0-9]{32}', str(data.get('installation'))):
                raise ValueError('Invalid statistics registration')
            with self.lock:
                self.credentials = credentials = dict(data, endpoint=self.endpoint)
                self._save()
        devices, matches, cursors = [], [], {}
        if enabled:
            for status in self.provider()[:32]:
                key = status.get('key')
                if not key: continue
                paused = status.get('state') in {'paused','pausing'}
                devices.append({'id':self.anonymous(str(key)), 'active':status.get('is_running') is True and not paused,
                    'paused':paused, 'revision':self.revision})
            matches, cursors = self.history_batch()
        with self.lock:
            if epoch!=self.epoch: return
        payload = {'devices':devices,'matches':matches}
        if enabled:
            payload['revision'] = self.revision
        ack = self._post('/v1/statistics', payload, credentials['token'])
        if ack.get('accepted') != [m['id'] for m in matches]: raise ValueError('Invalid statistics acknowledgement')
        with self.lock:
            if enabled:
                self.cursors = cursors
                self.recent_ids = list(dict.fromkeys(self.recent_ids+[m['id'] for m in matches]))[-2048:]
                self.sent_matches += len(matches)
                self.last_sent = time.time()
            if epoch==self.epoch:
                self.clear_presence = False
                self.state = 'sent' if enabled else 'disabled'
            self._save()

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive(): return
            self.thread = threading.Thread(target=self._loop, name='xlambot-community-statistics', daemon=True)
            self.thread.start()

    def _loop(self):
        while not self.stopped.is_set():
            self.wake.clear()
            try: self.sync()
            except Exception:
                with self.lock:
                    if self.enabled: self.state = 'retrying'
            self.wake.wait(60)

    def close(self):
        self.stopped.set()
        self.wake.set()
