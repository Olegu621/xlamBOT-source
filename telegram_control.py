"""Opt-in PC relay. Remote requests use the same protected Flask handlers as local UI."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import struct
import threading
import time
from urllib.parse import unquote, urlsplit

from error_telemetry import DEFAULT_ENDPOINT


def protect(data, decrypt=False):
    """Use Windows user DPAPI; never persist a plaintext remote-control credential."""
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    raw = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError('Protected Telegram connection unavailable')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.WinDLL('kernel32').LocalFree(output.data)


def permitted(method, path, body=None):
    if not isinstance(path, str) or len(path) > 2048 or not isinstance(method, str) or method not in {'GET', 'POST', 'DELETE'}:
        return False
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return False
    value = unquote(parsed.path)
    if not value.startswith('/') or '\\' in value or '\0' in value or any(v in {'.', '..'} for v in value.split('/')):
        return False
    if method == 'GET':
        return bool(re.fullmatch(r'/(panel|training(?:/[^/]+)?|statistics|calibration/[^/]+)', value) or
            re.fullmatch(r'/static/(?:js|css|fonts)/[A-Za-z0-9_./-]+\.(?:js|css|woff2?|ttf)', value) or
            re.fullmatch(r'/api/(?:assets/(?:brawlers|support)/[^/]+|ui/preferences|statistics|history|bootstrap|devices(?:/(?:status|brawlers|modes|[^/]+/(?:settings|queue|brawler|history|logs|telemetry|snapshot|training)))?|brawler-calibration/[^/]+(?:/snapshot)?|training/(?:trash|sessions(?:/[^/]+(?:/(?:images/[^/]+|export\.zip))?)?))', value))
    if method == 'DELETE':
        return bool(re.fullmatch(r'/api/(?:devices/[^/]+/logs|training/sessions/[^/]+)', value))
    if re.fullmatch(r'/api/devices/[^/]+/settings', value):
        if not isinstance(body, dict) or not isinstance(body.get('values'), dict):
            return False
        fields = {'cfg/general_config.toml': {'thinking_mode'}, 'cfg/bot_config.toml':
                  {'work_mode', 'brawler_switch_after_games', 'brawler_pick_mode'}}.get(body.get('section'), set())
        return set(body) <= {'section', 'values'} and bool(body['values']) and set(body['values']) <= fields
    return bool(re.fullmatch(r'/api/(?:devices/(?:connect|disconnect|prepare|reset-display|stop-all|[^/]+/(?:start|pause|resume|stop|queue|brawler|mode(?:/calibrate)?|training/(?:start|stop)))|brawler-calibration/[^/]+(?:/(?:tap|reset))?|training/(?:sessions/[^/]+/labels|trash/[^/]+/restore))', value))


class SecureSocket:
    """Small RFC6455 client using the frozen runtime's standard library only."""
    def __init__(self, token, stopped, endpoint=DEFAULT_ENDPOINT):
        host = urlsplit(endpoint).hostname
        self.stopped, self.buffer = stopped, bytearray()
        self.last_received = time.monotonic()
        self.socket = ssl.create_default_context().wrap_socket(socket.create_connection((host, 443), timeout=10), server_hostname=host)
        self.socket.settimeout(20)
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall(('GET /v1/remote/socket HTTP/1.1\r\nHost: '+host+'\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: '+key+'\r\nAuthorization: Bearer '+token+'\r\n\r\n').encode())
        while b'\r\n\r\n' not in self.buffer:
            data = self.socket.recv(4096)
            if not data or len(self.buffer) > 16384:
                self.close(); raise OSError('Relay handshake failed')
            self.buffer.extend(data)
        header, rest = bytes(self.buffer).split(b'\r\n\r\n', 1)
        self.buffer = bytearray(rest)
        expected = base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        fields = dict(line.split(':', 1) for line in header.decode('ascii').split('\r\n')[1:] if ':' in line)
        fields = {k.lower(): v.strip() for k, v in fields.items()}
        if b' 101 ' not in header.split(b'\r\n')[0] or fields.get('sec-websocket-accept') != expected:
            self.close(); raise OSError('Relay handshake refused')

    def read(self, size):
        while len(self.buffer) < size:
            if self.stopped.is_set(): raise OSError('Stopped')
            try: data = self.socket.recv(max(4096, size-len(self.buffer)))
            except socket.timeout:
                if time.monotonic()-self.last_received > 60: raise OSError('Relay timed out')
                self.send(b'', 9); continue
            if not data: raise OSError('Relay disconnected')
            self.buffer.extend(data); self.last_received = time.monotonic()
        data = bytes(self.buffer[:size]); del self.buffer[:size]; return data

    def receive(self):
        result = bytearray(); started = False
        while True:
            first, second = self.read(2); opcode = first & 15; size = second & 127
            if first & 112 or second & 128: raise OSError('Unsupported relay frame')
            if size == 126: size = struct.unpack('!H', self.read(2))[0]
            elif size == 127: size = struct.unpack('!Q', self.read(8))[0]
            if size > 3*1024*1024 or len(result)+size > 3*1024*1024: raise OSError('Relay frame too large')
            if opcode >= 8 and (size > 125 or not first & 128): raise OSError('Invalid relay control frame')
            payload = self.read(size)
            if opcode == 8: raise OSError('Relay closed')
            if opcode == 9: self.send(payload, 10); continue
            if opcode == 10: continue
            if opcode not in {0, 1} or (opcode == 0 and not started) or (opcode == 1 and started): raise OSError('Invalid relay fragment')
            started = True; result.extend(payload)
            if first & 128: return json.loads(result.decode('utf-8'))

    def send(self, data, opcode=1):
        if isinstance(data, dict): data = json.dumps(data, separators=(',', ':')).encode()
        mask = os.urandom(4); size = len(data)
        header = bytes([128 | opcode, 128 | (size if size < 126 else 126 if size < 65536 else 127)])
        if size >= 126: header += struct.pack('!H' if size < 65536 else '!Q', size)
        self.socket.sendall(header+mask+bytes(v ^ mask[i % 4] for i, v in enumerate(data)))

    def close(self):
        try: self.socket.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        self.socket.close()


class TelegramControl:
    def __init__(self, app, root, endpoint=DEFAULT_ENDPOINT, session=None):
        self.app, self.root, self.endpoint, self.session = app, Path(root), endpoint, session
        self.lock = threading.RLock(); self.stopped = threading.Event()
        self.enabled, self.credentials, self.state, self.connection = False, {}, 'disabled', None
        self.key, self.expires, self.paired, self.revision = '', 0, False, 0
        try:
            data = json.loads(protect((self.root/'connection.dpapi').read_bytes(), True))
            if data.get('endpoint') == endpoint and re.fullmatch('[a-f0-9]{64}', str(data.get('token'))) and re.fullmatch('[a-f0-9]{32}', str(data.get('installation'))):
                self.credentials = data; self.enabled = data.get('enabled') is True
        except (OSError, ValueError, TypeError, AttributeError): pass
        self.thread = None

    def _save(self):
        # Use an atomic replacement; the local UI owns configuration changes.
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root/'connection.tmp'
        temporary.write_bytes(protect(json.dumps({**self.credentials, 'endpoint': self.endpoint, 'enabled': self.enabled}).encode()))
        os.replace(temporary, self.root/'connection.dpapi')

    def api(self, path, body=None):
        if self.session is None:
            import requests
            self.session = requests.Session()
        headers = {'Authorization': 'Bearer '+self.credentials['token']} if self.credentials else {}
        response = (self.session.get(self.endpoint+path, headers=headers, timeout=(4, 12), allow_redirects=False) if body is None else
                    self.session.post(self.endpoint+path, json=body, headers=headers, timeout=(4, 12), allow_redirects=False))
        if response.status_code not in (200, 202): raise OSError('Telegram relay unavailable')
        return response.json()

    def status(self):
        with self.lock:
            return {'enabled':self.enabled,'state':self.state,'paired':self.paired,'key':self.key if self.expires > time.time() else '',
                    'expires':self.expires,'bot':'https://t.me/xlambottt_bot'}

    def update_pc_name(self):
        """Update an existing pairing without reconnecting or changing its key."""
        with self.lock:
            if not self.enabled or not self.credentials:
                return
            token = self.credentials['token']
        def update():
            try:
                from presentation_preferences import read
                import requests
                requests.post(self.endpoint+'/v1/remote/status',
                    json={'pc_name':read()['pc_name']},
                    headers={'Authorization':'Bearer '+token}, timeout=(4,12), allow_redirects=False)
            except Exception:
                # Statistics heartbeats and reconnects retry the same metadata.
                pass
        threading.Thread(target=update, daemon=True, name='xlambot-pc-name').start()

    def configure(self, action):
        with self.lock:
            if action == 'create_key':
                community = self.app.extensions.get('community_statistics')
                if not self.credentials and community and community.endpoint == self.endpoint:
                    with community.lock:
                        if community.credentials:
                            self.credentials = {k:community.credentials[k] for k in ('installation','token')}
                if not self.credentials:
                    data = self.api('/v1/register', {})
                    if not re.fullmatch('[a-f0-9]{64}', str(data.get('token'))) or not re.fullmatch('[a-f0-9]{32}', str(data.get('installation'))):
                        raise ValueError('Invalid relay registration')
                    self.credentials = data
                data = self.api('/v1/remote/key', {})
                if not re.fullmatch('[a-f0-9]{64}', str(data.get('key'))): raise ValueError('Invalid pairing key')
                self.key, self.expires, self.paired = data['key'], float(data['expires']), False
                self.enabled = True; self._save(); self.start()
            elif action == 'disconnect':
                # Local disconnect is effective even if the cloud is unavailable.
                self.enabled = False; self.key = ''; self.expires = 0; self._save()
                if self.connection: self.connection.close()
                try: self.api('/v1/remote/revoke', {})
                except OSError: pass
                self.paired = False; self.state = 'disabled'
            else: raise ValueError('Choose a valid Telegram action')
            return self.status()

    def start(self):
        with self.lock:
            if self.enabled and (not self.thread or not self.thread.is_alive()):
                self.thread = threading.Thread(target=self._loop, daemon=True, name='xlambot-telegram-control'); self.thread.start()

    def dispatch(self, call):
        method, path, body = call.get('method'), call.get('path'), call.get('body')
        with self.lock:
            if not self.enabled or self.stopped.is_set() or not isinstance(call.get('deadline'), (int, float)) or not time.time() < call['deadline'] <= time.time()+30:
                return 409, b'{"error":"expired_or_disabled"}', 'application/json', ''
            if not permitted(method, path, body): return 403, b'{"error":"forbidden"}', 'application/json', ''
            with self.app.test_client() as client:
                response = client.open(path, method=method, json=body if method != 'GET' else None,
                    headers={'X-Xlam-UI-Token':self.app.config['UI_API_TOKEN']}, environ_overrides={'xlambot.remote':True})
        data = response.get_data()
        if response.mimetype == 'text/html':
            prefix = '/pc/'+self.credentials['installation']
            text = data.decode('utf-8').replace(self.app.config['UI_API_TOKEN'], 'remote')
            boot = '<meta name="xlam-remote-prefix" content="'+prefix+'"><script src="'+prefix+'/static/js/telegram-remote.js"></script>'
            text = text.replace('<head>', '<head>'+boot, 1)
            text = re.sub(r'((?:href|src|action)=[\"\'])/(?!/|pc/)', r'\1'+prefix+'/', text)
            data = text.encode('utf-8')
        elif response.mimetype == 'text/css':
            data = re.sub(rb'url\(([\"\']?)/(?!/)', rb'url(\1/pc/'+self.credentials['installation'].encode()+b'/', data)
        if len(data) > 32*1024*1024: return 413, b'{"error":"download_too_large"}', 'application/json', ''
        return response.status_code, data, response.content_type, response.headers.get('Content-Disposition', '')

    def _loop(self):
        delay = 2
        while not self.stopped.is_set():
            if not self.enabled:
                self.stopped.wait(1); continue
            try:
                from presentation_preferences import read
                self.paired = bool(self.api('/v1/remote/status', {'pc_name': read()['pc_name']}).get('paired'))
                with self.lock:
                    if not self.enabled: continue
                    connection = SecureSocket(self.credentials['token'], self.stopped, self.endpoint)
                    self.connection, self.state = connection, 'connected'
                delay = 2; seen = set()
                while self.enabled and not self.stopped.is_set():
                    call = connection.receive()
                    if not isinstance(call, dict) or not re.fullmatch('[a-f0-9]{64}', str(call.get('id'))): raise OSError('Invalid remote request')
                    if call['id'] in seen: continue
                    if len(seen) >= 4096: seen.clear()
                    seen.add(call['id']); self.paired = True
                    status, data, content_type, disposition = self.dispatch(call)
                    for offset in range(0, len(data), 65536):
                        connection.send({'id':call['id'],'chunk':base64.b64encode(data[offset:offset+65536]).decode()})
                    connection.send({'id':call['id'],'done':True,'status':status,'type':content_type,'disposition':disposition})
            except Exception:
                self.state = 'retrying' if self.enabled else 'disabled'
            finally:
                if self.connection:
                    try: self.connection.close()
                    except OSError: pass
                    self.connection = None
            self.stopped.wait(delay); delay = min(60, delay*2)

    def close(self):
        self.stopped.set()
        if self.connection:
            try: self.connection.close()
            except OSError: pass
        if self.thread: self.thread.join(timeout=2)
