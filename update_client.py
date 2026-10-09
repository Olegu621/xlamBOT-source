"""Signed script updates; executable/runtime upgrades still use an installer."""
from __future__ import annotations
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import threading
import time
import zipfile
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPOSITORY = 'Olegu621/xlamBOT'
BOOTSTRAP = 1
BUNDLED_REVISION = 86
PUBLIC_KEY = '9a7d7864c03c38ece7f571ca9808aa41a37b0f1d468e3b2c74e1dbe1b4b36b32'
MAX_SIZE = 64 * 1024 * 1024
ACTIVE_OVERLAY = None
_state_lock = threading.RLock()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

def root():
    return Path(os.environ.get('XLAMBOT_UPDATE_HOME') or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'xlamBOT' / 'updates')

def read_state():
    try:
        return json.loads((root() / 'state.json').read_text('utf-8'))
    except (OSError, ValueError):
        return {'enabled': True, 'revision': BUNDLED_REVISION}

def write_state(state):
    with _state_lock:
        root().mkdir(parents=True, exist_ok=True)
        temporary = root() / 'state.tmp'
        temporary.write_bytes(canonical(state))
        os.replace(temporary, root() / 'state.json')

def safe_name(name):
    p = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError('Invalid update path')
    if p.parts[0] in {'cfg', 'devices', 'models', 'training', 'playstyles', 'vendor', 'scrcpy'}:
        raise ValueError('Update cannot modify user data or runtime')
    if name in {'update_client.pyc', 'xlambot_launcher.pyc'} or p.suffix not in {'.pyc', '.js', '.css', '.html'}:
        raise ValueError('Unsupported update file')
    return name

def verify(envelope):
    manifest = envelope['manifest']
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY)).verify(bytes.fromhex(envelope['signature']), canonical(manifest))
    if manifest['repository'] != REPOSITORY or manifest['bootstrap'] != BOOTSTRAP:
        raise ValueError('This update needs a newer installer')
    if manifest.get('python') != f'{sys.version_info.major}.{sys.version_info.minor}':
        raise ValueError('Update uses a different Python runtime')
    if type(manifest['revision']) is not int or manifest['revision'] < 1:
        raise ValueError('Invalid revision')
    if not 0 < manifest['size'] <= MAX_SIZE or not manifest['files']:
        raise ValueError('Invalid update size')
    for name, digest in manifest['files'].items():
        safe_name(name)
        if len(bytes.fromhex(digest)) != 32:
            raise ValueError('Invalid file digest')
    return manifest

def validate_content(folder, manifest):
    for name, expected in manifest['files'].items():
        path = folder / safe_name(name)
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Update file integrity check failed')

class OverlayFinder(importlib.abc.MetaPathFinder):
    def __init__(self, folder):
        self.folder = folder
    def find_spec(self, fullname, path=None, target=None):
        location = self.folder.joinpath(*fullname.split('.'))
        if (location / '__init__.pyc').is_file():
            return importlib.util.spec_from_file_location(fullname, location / '__init__.pyc', submodule_search_locations=[str(location)])
        if location.with_suffix('.pyc').is_file():
            return importlib.util.spec_from_file_location(fullname, location.with_suffix('.pyc'))
        return None

def activate():
    global ACTIVE_OVERLAY
    state = read_state()
    original_state = dict(state)
    # Installing a rebuilt EXE must not reactivate scripts older than its bundle,
    # including when automatic updates are intentionally disabled.
    if state.get('pending', 0) <= BUNDLED_REVISION:
        state.pop('pending', None)
        state.pop('attempted', None)
    if state.get('revision', 0) < BUNDLED_REVISION:
        state['revision'] = BUNDLED_REVISION
    if state != original_state:
        write_state(state)
    if state.get('pending') and state.get('enabled', True):
        if state.get('attempted'):
            state.pop('pending', None)
            state.pop('attempted', None)
            state['last_error'] = 'Previous update did not start; restored previous scripts'
        else:
            state['attempted'] = True
        write_state(state)
    pending = state.get('pending') if state.get('enabled', True) else None
    candidates = list(dict.fromkeys([pending, state.get('revision', 0), state.get('previous', 0)]))
    failures = []
    for revision in candidates:
        if not revision or revision <= BUNDLED_REVISION:
            continue
        folder = root() / 'releases' / str(revision)
        try:
            manifest = verify(json.loads((folder / 'manifest.json').read_text('utf-8')))
            if manifest['revision'] != revision:
                raise ValueError('Revision mismatch')
            validate_content(folder / 'content', manifest)
        except Exception as error:
            failures.append(f'{revision}: {type(error).__name__}')
            continue
        sys.meta_path.insert(0, OverlayFinder(folder / 'content'))
        ACTIVE_OVERLAY = folder / 'content'
        if failures:
            state.pop('pending', None)
            state.pop('attempted', None)
            state['revision'] = revision
            state['last_error'] = 'Damaged update; restored verified scripts (' + '; '.join(failures) + ')'
            write_state(state)
        return ACTIVE_OVERLAY
    if failures:
        state.pop('pending', None)
        state.pop('attempted', None)
        state['revision'] = BUNDLED_REVISION
        state['last_error'] = 'No verified update remains; using bundled scripts (' + '; '.join(failures) + ')'
        write_state(state)
    return None

def mark_healthy():
    state = read_state()
    if state.get('pending') and state.get('attempted'):
        state['previous'] = state.get('revision', 0)
        state['revision'] = state.pop('pending')
        state.pop('attempted', None)
        state.pop('last_error', None)
        write_state(state)

def download(url, limit):
    response = requests.get(url, timeout=(8, 30), stream=True, headers={'User-Agent': 'xlamBOT-updater/1'})
    with response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(64 * 1024):
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError('Download exceeds permitted size')
        return bytes(data)

class UpdateManager:
    def __init__(self, busy, restart):
        self.busy, self.restart = busy, restart
        self.lock = threading.RLock()
        self.check_lock = threading.Lock()
        self.status = {'state': 'idle', 'message': 'Проверка обновлений', 'repository': REPOSITORY}
        self.installing = False
    def snapshot(self):
        with self.lock:
            return {**self.status, 'enabled': read_state().get('enabled', True), 'revision': read_state().get('revision', 0)}
    def enabled(self, enabled):
        with self.lock:
            if type(enabled) is not bool:
                raise ValueError('enabled must be boolean')
            state = read_state(); state['enabled'] = enabled; write_state(state)
        return self.snapshot()
    def check(self):
        if not self.check_lock.acquire(blocking=False):
            return
        try:
            self.status.update(state='checking', message='Проверяю GitHub')
            # Pin both files to one commit, so a concurrent publication cannot mix revisions.
            commit = json.loads(download(f'https://api.github.com/repos/{REPOSITORY}/commits/main', 2 * 1024 * 1024))['sha']
            if not isinstance(commit, str) or len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
                raise ValueError('Invalid repository commit')
            base = f'https://raw.githubusercontent.com/{REPOSITORY}/{commit}'
            envelope = json.loads(download(f'{base}/manifest.json', 1024 * 1024))
            manifest = verify(envelope)
            state = read_state()
            if manifest['revision'] <= max(state.get('revision', 0), state.get('pending', 0)):
                self.status.update(state='current', message='Установлена актуальная версия')
                return
            archive = download(f'{base}/scripts.zip', MAX_SIZE)
            if len(archive) != manifest['size'] or hashlib.sha256(archive).hexdigest() != manifest['sha256']:
                raise ValueError('Archive integrity check failed')
            folder = root() / 'releases' / str(manifest['revision'])
            content = folder / 'content'; content.mkdir(parents=True, exist_ok=True)
            import io
            with zipfile.ZipFile(io.BytesIO(archive)) as z:
                names = z.namelist()
                if len(names) != len(set(names)) or set(names) != set(manifest['files']):
                    raise ValueError('Unexpected archive contents')
                if sum(i.file_size for i in z.infolist()) > MAX_SIZE:
                    raise ValueError('Unpacked update too large')
                for name in names:
                    path = content / safe_name(name); path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(z.read(name))
            validate_content(content, manifest)
            (folder / 'manifest.json').write_bytes(canonical(envelope))
            # A disabled updater may check manually, but never arms installation.
            if read_state().get('enabled', True):
                state = read_state(); state['pending'] = manifest['revision']; write_state(state)
            self.status.update(state='ready', message='Обновление скачано; установится после остановки ботов', available=manifest['revision'])
        except Exception as error:
            self.status.update(state='error', message=f'Не удалось обновить: {type(error).__name__}')
        finally:
            self.check_lock.release()
    def request_check(self):
        threading.Thread(target=self.check, daemon=True).start()
    def loop(self):
        next_check = 0
        while True:
            if read_state().get('enabled', True):
                if time.monotonic() >= next_check:
                    self.check(); next_check = time.monotonic() + 3600
                with self.lock:
                    if read_state().get('pending') and not self.busy() and not self.installing:
                        self.installing = True
                        self.status.update(state='restarting', message='Применяю обновление; панель перезапустится')
                        try:
                            self.restart()
                        except Exception:
                            self.installing = False
                            self.status.update(state='error', message='Не удалось перезапустить бот')
            time.sleep(10)

def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def start_restart_helper(exe, pid, arguments=()):
    import uuid
    folder = root()
    folder.mkdir(parents=True, exist_ok=True)
    ready = folder / ('restart-ready-' + uuid.uuid4().hex)
    helper = folder / ('restart-' + str(pid) + '.ps1')
    args = (" -ArgumentList " + _ps_quote(subprocess.list2cmdline(list(arguments)))) if arguments else ''
    helper.write_text(
        "$ErrorActionPreference = 'Stop'\ntry {\n"
        + "  [IO.File]::WriteAllText(" + _ps_quote(ready) + ", 'ready')\n"
        + f"  $p = Get-Process -Id {pid} -ErrorAction SilentlyContinue\n"
        + "  if ($p -and -not $p.WaitForExit(60000)) { throw 'Previous process did not exit' }\n"
        + "  Start-Sleep -Seconds 1\n"
        + "  Start-Process -FilePath " + _ps_quote(exe) + args
        + " -WorkingDirectory " + _ps_quote(Path(exe).parent) + " -WindowStyle Hidden\n"
        + "} catch { [Console]::Error.WriteLine($_); exit 1 }\n",
        encoding='utf-8-sig')
    # A windowed EXE can have invalid inherited standard handles. Give the
    # helper real handles and keep diagnostics rather than detaching blindly.
    with (folder / 'restart.log').open('ab') as output:
        process = subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(helper)],
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
    deadline = time.monotonic() + 8
    try:
        while time.monotonic() < deadline:
            if ready.exists():
                return process
            if process.poll() is not None:
                raise RuntimeError('Restart helper failed; see restart.log')
            time.sleep(.05)
        process.terminate()
        raise RuntimeError('Restart helper did not become ready; current bot preserved')
    finally:
        ready.unlink(missing_ok=True)


def restart_application(arguments=()):
    if not getattr(sys, 'frozen', False) or os.name != 'nt':
        raise RuntimeError('Automatic restart requires the Windows installer')
    start_restart_helper(str(Path(sys.executable).resolve()), os.getpid(), arguments)
    os._exit(0)
