"""Bounded, anonymous error reports. Game threads never perform disk/network IO."""
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import queue
import re
import sys
import threading
import time
from urllib.parse import urlsplit
import uuid

# Set the developer's HTTPS receiver when it is deployed. Never put a bot token here.
DEFAULT_ENDPOINT = 'https://xlambot-error-receiver.olegu621.workers.dev'
LEVELS = {'info': 0, 'warning': 1, 'error': 2, 'critical': 3}
CODES = {
    'startup_failed', 'runtime_crash', 'runtime_halted', 'thread_crash',
    'application_exception', 'ui_request_failed', 'gpu_fallback',
    'gas_detector_failed', 'brawler_selection_failed', 'update_failed',
    'manual_report', 'test_report',
}
MODULES = {
    'bot_instance', 'window_controller', 'capture_transport', 'play', 'detect',
    'stage_manager', 'lobby_automation', 'utils', 'trophy_observer', 'trophy_reader',
    'app', 'device_manager', 'runtime', 'services', 'training_capture',
    'brawler_calibration', 'settings_schema', 'update_client', 'main',
    'battle_memory', 'gas_guard', 'combat_behavior', 'ability_buttons',
}
STAGES = {'startup', 'runtime', 'ui', 'model', 'update', 'manual', 'unknown'}
MAX_EVENTS = 200
_service = None
_context = threading.local()
_initialize_lock = threading.Lock()


def endpoint_url(value):
    if not value:
        return ''
    parsed = urlsplit(str(value))
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment):
        raise ValueError('Telemetry receiver must be an HTTPS URL without credentials.')
    return str(value).rstrip('/')


def identifier(value, limit=80):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,'+str(limit)+'}', value) else 'unknown'


def safe_trace(error):
    """No exception message, source lines, locals, absolute paths or model names."""
    frames = []
    if error is not None:
        tb = error.__traceback__
        while tb is not None:
            code = tb.tb_frame.f_code
            module = Path(code.co_filename.replace('\\', '/')).stem
            if module in MODULES:
                frames.append({'module': module, 'function': identifier(code.co_name), 'line': tb.tb_lineno})
            tb = tb.tb_next
    return frames[-8:]


def clean_event(event):
    """Shared strict allowlist; the receiver independently applies it too."""
    if not isinstance(event, dict) or event.get('code') not in CODES or event.get('level') not in LEVELS:
        raise ValueError('Invalid error report')
    clean = {key: event[key] for key in ('code', 'level')}
    clean['stage'] = event.get('stage') if event.get('stage') in STAGES else 'unknown'
    for key in ('id', 'installation'):
        value = event.get(key, '')
        if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
            raise ValueError('Invalid report identifier')
        clean[key] = value
    clean['device'] = event.get('device') if re.fullmatch(r'[a-f0-9]{12}', str(event.get('device', ''))) else ''
    from presentation_preferences import validate_pc_name
    clean['pc_name'] = validate_pc_name(event.get('pc_name', ''))
    clean['app_version'] = identifier(event.get('app_version'))
    revision = event.get('revision', 0)
    clean['revision'] = revision if type(revision) is int and 0 <= revision <= 10000000 else 0
    clean['exception_type'] = identifier(event.get('exception_type'))
    for key in ('first_seen', 'last_seen'):
        value = event.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid report time')
        clean[key] = value
    count = event.get('count', 1)
    if type(count) is not int or not 1 <= count <= 1000000000:
        raise ValueError('Invalid report count')
    clean['count'] = count
    frames = event.get('trace', [])
    if not isinstance(frames, list):
        raise ValueError('Invalid report trace')
    clean['trace'] = []
    for frame in frames[-8:]:
        if (isinstance(frame, dict) and frame.get('module') in MODULES and
                type(frame.get('line')) is int and 0 < frame['line'] <= 10000000):
            clean['trace'].append({'module': frame['module'], 'function': identifier(frame.get('function')), 'line': frame['line']})
    signature = [clean[key] for key in ('app_version', 'revision', 'level', 'code', 'exception_type', 'stage', 'trace')]
    clean['fingerprint'] = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    return clean


class ErrorTelemetry:
    def __init__(self, root, endpoint='', app_version='unknown', revision=0, session=None):
        self.root = Path(root)
        self.endpoint = endpoint_url(endpoint)
        self.app_version, self.revision = app_version, revision
        self.session = session
        self.lock = threading.RLock()
        self.wake, self.stopped = threading.Event(), threading.Event()
        self.inbox = queue.Queue(maxsize=256)
        self.entries = OrderedDict()
        self.enabled, self.min_level = True, 'error'
        self.consent_epoch = 0
        self.installation = uuid.uuid4().hex
        self.credentials = {}
        self.generation = 0
        self.saved_generation = -1
        self.status_code, self.last_sent, self.dropped = 'disabled', None, 0
        self.retry_at, self.retry_delay = 0., 5.
        self._load()
        self.status_code = 'ready' if self.enabled else 'disabled'
        self.thread = None

    def _load(self):
        try:
            data = json.loads((self.root/'state.json').read_text('utf-8'))
            if not isinstance(data, dict):
                self.enabled = False
                return
            self.installation = data['installation'] if re.fullmatch(r'[a-f0-9]{32}', str(data.get('installation'))) else self.installation
            self.enabled = data.get('enabled') is True
            self.consent_epoch = max(0, int(data.get('consent_epoch', 0)))
            self.min_level = data.get('min_level') if data.get('min_level') in {'warning', 'error', 'critical'} else 'error'
            self.last_sent = data.get('last_sent')
            for raw in data.get('events', [])[-MAX_EVENTS:]:
                event = clean_event(raw)
                event['_sent_count'] = min(event['count'], max(0, int(raw.get('_sent_count', 0))))
                event['_epoch'] = int(raw.get('_epoch', 0))
                event['_last_delivery'] = float(raw.get('_last_delivery', 0))
                self.entries[event['fingerprint']+event['device']+str(event['_epoch'])] = event
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError):
            self.enabled = False
        try:
            data = json.loads((self.root/'credentials.json').read_text('utf-8'))
            if not isinstance(data, dict):
                return
            if data.get('endpoint') == self.endpoint and re.fullmatch(r'[a-f0-9]{64}', str(data.get('token'))) and re.fullmatch(r'[a-f0-9]{32}', str(data.get('installation'))):
                self.credentials = data
        except (OSError, ValueError, TypeError):
            pass

    def start(self):
        with self.lock:
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._loop, daemon=True, name='xlambot-error-reports')
                self.thread.start()

    def configure(self, enabled, min_level):
        if type(enabled) is not bool or min_level not in {'warning', 'error', 'critical'}:
            raise ValueError('Choose a valid error reporting preference.')
        with self.lock:
            if self.enabled != enabled:
                self.consent_epoch += 1
            self.enabled, self.min_level = enabled, min_level
            self.status_code = 'ready' if enabled else 'disabled'
            self.generation += 1
            if not enabled:
                # Off means no later replay of reports queued before withdrawal.
                for event in self.entries.values():
                    event['_sent_count'] = event['count']
            self.retry_at = 0
        self.wake.set()
        # Preferences are changed by the UI thread, not the game owner. Persist
        # withdrawal before acknowledging it so a restart cannot revive consent.
        self._save()
        return self.status()

    def report(self, code, level='error', error=None, device=None, stage='unknown'):
        if code not in CODES or level not in LEVELS:
            return False
        now = time.time()
        event = {'id': uuid.uuid4().hex, 'installation': self.installation,
                 'code': code, 'level': level, 'stage': stage,
                 'app_version': self.app_version, 'revision': self.revision,
                 'exception_type': type(error).__name__ if error is not None else 'none',
                 'trace': safe_trace(error), 'first_seen': now, 'last_seen': now, 'count': 1,
                 'device': hashlib.sha256((self.installation+str(device)).encode()).hexdigest()[:12] if device else ''}
        from presentation_preferences import read
        event['pc_name'] = read()['pc_name']
        try:
            event = clean_event(event)
            event['_epoch'] = self.consent_epoch
            event['_eligible'] = self.enabled and level != 'info'
            self.inbox.put_nowait(event)
            self.wake.set()
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def drain(self):
        with self.lock:
            while True:
                try:
                    event = self.inbox.get_nowait()
                except queue.Empty:
                    break
                # Per-device counts are independent; server groups across devices.
                eligible = event.pop('_eligible', False) and self.enabled and event['_epoch'] == self.consent_epoch
                key = event['fingerprint']+event['device']+str(event['_epoch'])
                old = self.entries.get(key)
                if old:
                    old['count'] = min(1000000000, old['count']+1)
                    old['last_seen'] = event['last_seen']
                    if not eligible:
                        old['_sent_count'] = old['count']
                    self.entries.move_to_end(key)
                else:
                    event['_sent_count'] = 0 if eligible else 1
                    self.entries[key] = event
                while len(self.entries) > MAX_EVENTS:
                    victim = min(self.entries, key=lambda k: (LEVELS[self.entries[k]['level']], self.entries[k]['last_seen']))
                    self.entries.pop(victim)
                self.generation += 1

    def status(self):
        with self.lock:
            pending = sum(event['count'] > event.get('_sent_count', 0) and LEVELS[event['level']] >= LEVELS[self.min_level] for event in self.entries.values())
            state = 'disabled' if not self.enabled else 'not_configured' if not self.endpoint else self.status_code
            return {'enabled': self.enabled, 'min_level': self.min_level, 'configured': bool(self.endpoint),
                    'state': state, 'pending': pending, 'last_sent': self.last_sent, 'dropped': self.dropped}

    def export(self):
        self.drain()
        with self.lock:
            return {'schema': 1, 'events': [clean_event(event) for event in self.entries.values()]}

    def _save(self):
        from utils import atomic_write_text
        with self.lock:
            if self.saved_generation == self.generation:
                return
            data = {'installation': self.installation, 'enabled': self.enabled, 'min_level': self.min_level,
                    'last_sent': self.last_sent, 'consent_epoch': self.consent_epoch, 'events': list(self.entries.values())}
            atomic_write_text(self.root/'state.json', json.dumps(data))
            self.saved_generation = self.generation

    def send_once(self):
        """Worker-only IO. Success acknowledges only the transmitted count."""
        self.drain()
        with self.lock:
            if not self.enabled or not self.endpoint or time.monotonic() < self.retry_at:
                return False
            candidates = [event for event in self.entries.values() if event['count'] > event.get('_sent_count', 0)
                          and LEVELS[event['level']] >= LEVELS[self.min_level]
                          and (not event.get('_sent_count') or time.time()-event.get('_last_delivery',0) >= 60)
                          and (event['level'] != 'warning' or event['count'] >= 3)]
            if not candidates:
                self.status_code = 'ready'
                return False
            candidate = max(candidates, key=lambda event: LEVELS[event['level']])
            snapshot = clean_event(candidate)
        try:
            if self.session is None:
                import requests
                self.session = requests.Session()
            if not self.credentials:
                response = self.session.post(self.endpoint+'/v1/register', json={}, timeout=(3, 5), allow_redirects=False)
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Registration refused')
                credentials = response.json()
                if not re.fullmatch(r'[a-f0-9]{64}', str(credentials.get('token'))) or not re.fullmatch(r'[a-f0-9]{32}', str(credentials.get('installation'))):
                    raise ValueError('Invalid receiver registration')
                self.credentials = {'endpoint': self.endpoint, 'installation': credentials['installation'], 'token': credentials['token']}
                from utils import atomic_write_text
                atomic_write_text(self.root/'credentials.json', json.dumps(self.credentials))
            with self.lock:
                if not self.enabled or candidate['_epoch'] != self.consent_epoch:
                    return False
            snapshot['installation'] = self.credentials['installation']
            response = self.session.post(self.endpoint+'/v1/events', json=snapshot,
                headers={'Authorization': 'Bearer '+self.credentials['token']}, timeout=(3, 5), allow_redirects=False)
            if response.status_code == 401:
                self.credentials = {}
                (self.root/'credentials.json').unlink(missing_ok=True)
            response.raise_for_status()
            if response.status_code not in (200, 202):
                raise ValueError('Report refused')
            if response.json().get('accepted') != snapshot['id']:
                raise ValueError('Receiver did not acknowledge report')
            with self.lock:
                candidate['_sent_count'] = max(candidate.get('_sent_count', 0), snapshot['count'])
                candidate['_last_delivery'] = time.time()
                self.last_sent, self.status_code = time.time(), 'sent'
                self.retry_delay = 5
                self.generation += 1
            return True
        except Exception:
            # Do not record reporter failures recursively or expose credential URLs.
            with self.lock:
                self.status_code = 'retrying'
                self.retry_at = time.monotonic()+self.retry_delay
                self.retry_delay = min(1800, self.retry_delay*2)
            return False

    def close(self):
        self.stopped.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _loop(self):
        while not self.stopped.is_set():
            try:
                self.drain()
                self.send_once()
                self._save()
            except Exception:
                self.status_code = 'storage_unavailable'
            self.wake.wait(1)
            self.wake.clear()


@contextmanager
def device_scope(device):
    previous = getattr(_context, 'device', None)
    _context.device = device
    try:
        yield
    finally:
        _context.device = previous


def report(code, level='error', error=None, device=None, stage='unknown'):
    try:
        if _service:
            return _service.report(code, level, error, device or getattr(_context, 'device', None), stage)
    except Exception:
        pass
    return False


class ErrorLogHandler(logging.Handler):
    def emit(self, record):
        if record.exc_info and not getattr(record, 'telemetry_reported', False):
            report('application_exception', 'error', record.exc_info[1], stage='runtime')


def runtime_revision(update_client):
    """Identify executing code, even before a pending update is marked healthy."""
    overlay = getattr(update_client, 'ACTIVE_OVERLAY', None)
    if overlay is not None:
        try:
            revision = int(Path(overlay).parent.name)
            if 0 < revision <= 10000000:
                return revision
        except (TypeError, ValueError):
            pass
    revision = getattr(update_client, 'BUNDLED_REVISION', 0)
    return revision if type(revision) is int and 0 <= revision <= 10000000 else 0


def initialize():
    global _service
    with _initialize_lock:
        if _service:
            return _service
        import utils
        import update_client
        try:
            endpoint = endpoint_url(os.environ.get('XLAMBOT_TELEMETRY_ENDPOINT', DEFAULT_ENDPOINT))
        except ValueError:
            endpoint = ''
        _service = ErrorTelemetry(update_client.root()/'error_reports', endpoint,
            utils.XLAMBOT_VERSION, runtime_revision(update_client))
        old_sys, old_thread = sys.excepthook, threading.excepthook
        def unhandled(kind, error, tb):
            if kind not in (SystemExit, KeyboardInterrupt):
                report('application_exception', 'critical', error, stage='runtime')
            old_sys(kind, error, tb)
        def thread_error(args):
            if args.exc_type is not SystemExit:
                report('thread_crash', 'critical', args.exc_value, stage='runtime')
            old_thread(args)
        sys.excepthook, threading.excepthook = unhandled, thread_error
        logging.getLogger().addHandler(ErrorLogHandler(level=logging.ERROR))
        _service.start()
        return _service
