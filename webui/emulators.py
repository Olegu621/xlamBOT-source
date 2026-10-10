"""Local, serialized LDPlayer management; never owns gameplay input."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from flask import g, jsonify, render_template, request
from adb_connection import canonical_device_serial, AUTO_CONNECTOR
import update_client

CONSOLE_HASH = '1f63e5985d216109ec9f2897ccba01c8d4a13b680197d35fbc0c4ea4d1ec6eef'


def instance_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'\w[\w .()\-]{0,59}', value, re.UNICODE) or not value.strip():
        raise ValueError('INVALID_NAME')
    return value.strip()


def parse_instances(output):
    result = []
    for row in csv.reader(output.splitlines()):
        if not row or not ''.join(row).strip():
            continue
        if len(row) < 10:
            raise ValueError('INVALID_CONSOLE_RESPONSE')
        if len(row) > 10:
            # Native LDPlayer does not quote commas in existing instance titles.
            row = [row[0], ','.join(row[1:-8]), *row[-8:]]
        index, top, bind, started, pid, vm_pid, width, height, dpi = map(int, [row[0], *row[2:]])
        if index < 0 or started not in (0, 1, 2) or any(v < 0 for v in (width, height, dpi)):
            raise ValueError('INVALID_CONSOLE_RESPONSE')
        result.append(dict(index=index, name=row[1], running=bool(started or pid > 0 or vm_pid > 0),
                           ready=started == 1, width=width, height=height, dpi=dpi,
                           serial=f'emulator-{5554 + 2 * index}'))
    if len({item['index'] for item in result}) != len(result):
        raise ValueError('INVALID_CONSOLE_RESPONSE')
    return result


class EmulatorManager:
    def __init__(self, devices, home=None):
        self.devices = devices
        self.home = Path(home) if home else update_client.root().parent / 'emulators'
        self.lock = threading.RLock()
        self.job = None
        self.console_lock = threading.Lock()
        self.last_instances = []
        self.installation = self.discover()

    def discover(self):
        candidates = []
        try:
            candidates.append(json.loads((self.home / 'preferences.json').read_text('utf-8'))['path'])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if os.name == 'nt':
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for key in ('Software\\leidian\\LDPlayer9', 'Software\\leidian\\ldplayer',
                            'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\LDPlayer9'):
                    try:
                        with winreg.OpenKey(hive, key) as handle:
                            for field in ('InstallDir', 'InstallPath', 'InstallLocation'):
                                try:
                                    candidates.append(winreg.QueryValueEx(handle, field)[0])
                                except OSError:
                                    pass
                    except OSError:
                        pass
            for drive in 'CDEFG':
                candidates.extend((f'{drive}:/LDPlayer/LDPlayer9', f'{drive}:/leidian/LDPlayer9'))
        for value in candidates:
            try:
                return self.validate_path(value)
            except (OSError, ValueError, TypeError):
                continue
        return None

    @staticmethod
    def validate_path(value):
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError('INVALID_INSTALLATION')
        folder = Path(value).resolve(strict=True)
        console = folder / 'ldconsole.exe'
        if console.is_symlink() or hashlib.sha256(console.read_bytes()).hexdigest() != CONSOLE_HASH:
            raise ValueError('UNSUPPORTED_LDPLAYER')
        if not (folder / 'dnplayer.exe').is_file():
            raise ValueError('INVALID_INSTALLATION')
        return folder

    def console(self, *args, timeout=20):
        if not self.installation:
            raise ValueError('LDPLAYER_NOT_FOUND')
        # Check the executable on every launch, including after an external update.
        self.validate_path(str(self.installation))
        with self.console_lock:
            proc = subprocess.run([str(self.installation / 'ldconsole.exe'), *map(str, args)],
                                  cwd=self.installation, capture_output=True, timeout=timeout,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        text = proc.stdout.decode('utf-8', errors='replace').strip()
        if '\ufffd' in text:
            text = proc.stdout.decode('mbcs' if os.name == 'nt' else 'utf-8', errors='replace').strip()
        created_index = args and args[0] in ('add', 'copy') and 0 <= proc.returncode <= 9999
        if proc.returncode and not created_index:
            raise RuntimeError('CONSOLE_FAILED')
        return text

    def instances(self):
        rows = parse_instances(self.console('list2')) if self.installation else []
        self.last_instances = rows
        return rows

    def status(self):
        with self.lock:
            job = dict(self.job) if self.job else None
            folder = self.installation
        edition = {}
        if folder:
            try:
                edition = json.loads((folder / 'xlamBOT-edition.json').read_text('utf-8'))
            except (OSError, ValueError):
                pass
        return dict(ok=True, path=str(folder or ''), edition=edition.get('edition_version'),
                    revision=edition.get('mod_revision', 0),
                    instances=list(self.last_instances) if self.console_lock.locked() else self.instances(), job=job)

    def _idle_bot(self, item):
        identity = canonical_device_serial(item['serial'])
        for state in self.devices.all_statuses():
            if canonical_device_serial(state['serial']) == identity and state['is_running']:
                raise ValueError('STOP_BOT_FIRST')

    def _instance(self, index):
        if type(index) is not int or not 0 <= index <= 9999:
            raise ValueError('INVALID_INSTANCE')
        end = time.monotonic() + 3
        while True:
            for item in self.instances():
                if item['index'] == index:
                    return item
            # Native inventory can briefly omit an instance while boot updates
            # its configuration. Never infer deletion or launch a replacement.
            if time.monotonic() >= end:
                break
            time.sleep(0.15)
        raise ValueError('INSTANCE_NOT_FOUND')

    def _wait(self, predicate, timeout=120):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            items = self.instances()
            match = predicate(items)
            if match:
                return match
            time.sleep(1)
        raise TimeoutError('EMULATOR_TIMEOUT')

    def submit(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('INVALID_ACTION')
        action = payload.get('action')
        fields = {'select': {'action', 'path'}, 'add': {'action', 'name'},
                  'clone': {'action', 'index', 'name'}, 'remove': {'action', 'index', 'confirmation'},
                  'rename': {'action', 'index', 'name'}, 'launch': {'action', 'index'},
                  'quit': {'action', 'index'}, 'configure': {'action', 'index'},
                  'customize': {'action', 'index'}, 'update_game': {'action', 'index'},
                  'install': {'action'}, 'update': {'action'}}
        if action not in fields or set(payload) != fields[action]:
            raise ValueError('INVALID_ACTION')
        if 'name' in payload:
            payload = dict(payload, name=instance_name(payload['name']))
        with self.lock:
            if self.job and self.job['state'] == 'running':
                raise ValueError('EMULATOR_BUSY')
            if action == 'select':
                folder = self.validate_path(payload['path'])
                self.home.mkdir(parents=True, exist_ok=True)
                temp = self.home / 'preferences.tmp'
                temp.write_text(json.dumps({'path': str(folder)}), 'utf-8')
                os.replace(temp, self.home / 'preferences.json')
                self.installation = folder
                return dict(ok=True)
            if 'index' in payload:
                item = self._instance(payload['index'])
                self._idle_bot(item)
                if action in ('clone', 'remove', 'configure', 'customize') and item['running']:
                    raise ValueError('CLOSE_EMULATOR_FIRST')
                if action == 'remove' and payload['confirmation'] != item['name']:
                    raise ValueError('CONFIRM_NAME')
            indices = [payload['index']] if 'index' in payload else ([] if action == 'add' else [i['index'] for i in self.instances()])
            self.job = dict(action=action, state='running', phase='starting', error=None, indices=indices)
            threading.Thread(target=self._run, args=(dict(payload),), daemon=True,
                             name='xlambot-emulator-manager').start()
            return dict(ok=True, job=dict(self.job))

    def phase(self, value):
        with self.lock:
            self.job['phase'] = value

    def native_manager(self, close=False):
        if os.name != 'nt' or not self.installation:
            return False
        # Its cached instance list can recreate removed entries and overwrite
        # configuration. Close this UI gracefully before changing the inventory.
        script = r'''
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($env:XLAMBOT_LD_ROOT)
$allowed = @((Join-Path $root 'dnmultiplayer.exe'), (Join-Path (Split-Path $root) 'ldmutiplayer\dnmultiplayerex.exe'))
$items = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('dnmultiplayer.exe','dnmultiplayerex.exe') -and $_.ExecutablePath -in $allowed })
if ($env:XLAMBOT_LD_CLOSE -eq '1') {
  foreach ($item in $items) {
    $p = Get-Process -Id $item.ProcessId -ErrorAction SilentlyContinue
    if ($p -and (-not $p.CloseMainWindow() -or -not $p.WaitForExit(10000))) { exit 4 }
  }
}
Write-Output $items.Count
'''
        env = dict(os.environ, XLAMBOT_LD_ROOT=str(self.installation), XLAMBOT_LD_CLOSE='1' if close else '0')
        powershell = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
                                env=env, capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise ValueError('CLOSE_MANAGER_FIRST')
        return bool(int(result.stdout.strip() or b'0'))

    def update_loop(self):
        while True:
            time.sleep(6 * 60 * 60)
            try:
                if not self.installation:
                    continue
                from .emulator_distribution import latest, stopped
                manifest = latest()['manifest']
                current = json.loads((self.installation / 'xlamBOT-edition.json').read_text('utf-8'))
                if type(current.get('mod_revision')) is not int or current['mod_revision'] >= manifest['revision']:
                    continue
                stopped(self)
                if self.native_manager():
                    continue
                self.submit({'action': 'update'})
            except Exception:
                # A running instance, offline network or an invalid signature defers the update.
                continue

    def game_update_loop(self):
        while True:
            time.sleep(30 * 60)
            try:
                if not self.installation:
                    continue
                from .game_updates import latest, verify, installed_version, game_in_foreground
                manifest = verify(latest())
                for item in self.instances():
                    if not item['ready']:
                        continue
                    try:
                        self._idle_bot(item)
                        current = installed_version(self, item['index'])
                        foreground = game_in_foreground(self, item['index'])
                    except Exception:
                        continue
                    if not current or current >= manifest['version_code'] or foreground:
                        continue
                    with self.lock:
                        if self.job and self.job['state'] == 'running':
                            break
                        self.job = dict(action='update_game', state='running', phase='checking_game', error=None, indices=[item['index']])
                        threading.Thread(target=self._run, args=({'action':'update_game', 'index':item['index'], 'background':True},), daemon=True).start()
                    break
            except Exception:
                # Offline, active gameplay or a stopped Android defers delivery.
                continue

    def _run(self, payload):
        try:
            action = payload['action']
            if action not in ('launch', 'quit', 'update_game'):
                self.phase('closing_manager')
                self.native_manager(close=True)
            if action in ('install', 'update'):
                from .emulator_distribution import install_edition
                install_edition(self, install_base=action == 'install')
            elif action in ('add', 'clone'):
                before = {item['index'] for item in self.instances()}
                self.phase('creating')
                if action == 'clone':
                    item = self._instance(payload['index'])
                    self._idle_bot(item)
                    if item['running']:
                        raise ValueError('CLOSE_EMULATOR_FIRST')
                    self.console('copy', '--name', payload['name'], '--from', item['index'], timeout=300)
                else:
                    self.console('add', '--name', payload['name'], timeout=180)
                created = self._wait(lambda rows: next((i for i in rows if i['index'] not in before and i['name'] == payload['name']), None))
                with self.lock:
                    self.job['indices'].append(created['index'])
                self.phase('configuring')
                self.configure(created)
                if action == 'add':
                    from .emulator_distribution import customize_instance
                    customize_instance(self, created['index'])
                    from .game_updates import update_game
                    update_game(self, created['index'])
                # Creation never starts the bot and leaves the new instance stopped.
            else:
                item = self._instance(payload['index'])
                self._idle_bot(item)
                index = item['index']
                if action == 'launch':
                    self.phase('booting')
                    self.console('launch', '--index', index)
                    self._wait(lambda rows: next((i for i in rows if i['index'] == index and i['ready']), None))
                    AUTO_CONNECTOR.remember(f'127.0.0.1:{5555 + 2 * index}')
                    installed = self.console('adb', '--index', index, '--command', 'shell pm path com.supercell.brawlstars')
                    if 'package:' in installed:
                        self.console('runapp', '--index', index, '--packagename', 'com.supercell.brawlstars')
                elif action == 'quit':
                    self.console('quit', '--index', index)
                    self._wait(lambda rows: any(i['index'] == index and not i['running'] for i in rows))
                elif action == 'rename':
                    self.console('rename', '--index', index, '--title', payload['name'])
                    self._wait(lambda rows: any(i['index'] == index and i['name'] == payload['name'] for i in rows))
                elif action == 'remove':
                    if item['running']:
                        raise ValueError('CLOSE_EMULATOR_FIRST')
                    self.console('remove', '--index', index, timeout=120)
                    self._wait(lambda rows: not any(i['index'] == index for i in rows))
                elif action == 'configure':
                    self.configure(item)
                elif action == 'customize':
                    from .emulator_distribution import customize_instance
                    customize_instance(self, index)
                elif action == 'update_game':
                    from .game_updates import update_game
                    update_game(self, index, allow_close=not payload.get('background', False))
            with self.lock:
                self.job.update(state='done', phase='ready')
        except Exception as error:
            with self.lock:
                # Do not expose command lines, local file contents or credentials.
                code = str(error) if isinstance(error, (ValueError, RuntimeError)) and re.fullmatch('[A-Z_]+', str(error)) else type(error).__name__
                self.job.update(state='error', error=code)

    def configure(self, item):
        self._idle_bot(item)
        if self._instance(item['index'])['running']:
            raise ValueError('CLOSE_EMULATOR_FIRST')
        cpu = 4 if (os.cpu_count() or 2) >= 8 else 2
        self.console('modify', '--index', item['index'], '--resolution', '1280,720,240',
                     '--cpu', cpu, '--memory', 4096, '--root', 0, '--autorotate', 0)
        # New LDPlayer instances disable ADB by default. Enable local debugging
        # before boot; otherwise the bot never sees the freshly created Android.
        config = self.installation / 'vms' / 'config' / f'leidian{item["index"]}.config'
        if config.is_symlink() or not config.resolve().is_relative_to(self.installation):
            raise ValueError('INVALID_INSTALLATION')
        values = json.loads(config.read_text('utf-8'))
        backup = self.home / 'backups' / f'config-{item["index"]}-{time.time_ns()}.json'
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(config.read_bytes())
        values['basicSettings.adbDebug'] = 1
        values['basicSettings.forceLandscape'] = True
        temporary = config.with_suffix('.xlambot-tmp')
        temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), 'utf-8')
        if self._instance(item['index'])['running']:
            temporary.unlink(missing_ok=True)
            raise ValueError('CLOSE_EMULATOR_FIRST')
        os.replace(temporary, config)
        self._wait(lambda rows: any(i['index'] == item['index'] and (i['width'], i['height'], i['dpi']) == (1280, 720, 240) for i in rows))


def register(app, devices):
    manager = EmulatorManager(devices)
    app.extensions['emulator_manager'] = manager
    threading.Thread(target=manager.update_loop, daemon=True, name='xlambot-emulator-updates').start()
    threading.Thread(target=manager.game_update_loop, daemon=True, name='xlambot-game-updates').start()

    @app.before_request
    def emulator_start_gate():
        if request.method != 'POST' or not request.path.endswith('/start'):
            return None
        manager.lock.acquire()
        g.emulator_gate_locked = True
        active = manager.job and manager.job['state'] == 'running'
        indices = list(manager.job.get('indices', [])) if active else []
        if active and request.path == '/api/runtime/start':
            return jsonify(ok=False, code='EMULATOR_BUSY', message='Wait for emulator setup to finish.'), 409
        if not indices:
            return None
        if not request.path.startswith('/api/devices/'):
            return None
        key = request.path.split('/')[3]
        serial = devices.resolve_serial(key)
        if canonical_device_serial(serial) in {canonical_device_serial(f'emulator-{5554+2*i}') for i in indices}:
            return jsonify(ok=False, code='EMULATOR_BUSY', message='Wait for emulator setup to finish.'), 409

    @app.teardown_request
    def release_emulator_gate(error):
        if getattr(g, 'emulator_gate_locked', False):
            g.emulator_gate_locked = False
            manager.lock.release()

    @app.get('/emulators')
    def emulator_page():
        if request.environ.get('xlambot.remote'):
            return '', 403
        return render_template('emulators.html', ui_api_token=app.config['UI_API_TOKEN'])

    @app.get('/api/emulators')
    def emulator_status():
        if request.environ.get('xlambot.remote'):
            return jsonify(ok=False), 403
        try:
            return jsonify(manager.status())
        except Exception:
            return jsonify(ok=False, error='CONSOLE_UNAVAILABLE'), 503

    @app.post('/api/emulators')
    def emulator_action():
        if request.environ.get('xlambot.remote'):
            return jsonify(ok=False), 403
        try:
            return jsonify(manager.submit(request.get_json(silent=True)))
        except (OSError, ValueError) as error:
            return jsonify(ok=False, error=str(error) if isinstance(error, ValueError) else 'INVALID_INSTALLATION'), 400

    # The installer requests this explicitly through its optional checkbox.
    marker = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'xlamBOT' / 'install-emulator.request'
    if marker.is_file():
        try:
            manager.submit({'action': 'install'})
        except Exception:
            manager.job = dict(action='install', state='error', phase='starting', error='LDPLAYER_NOT_FOUND', indices=[])
        marker.unlink(missing_ok=True)
