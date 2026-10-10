"""Signed, account-free LDPlayer edition delivery, independent of bot updates."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import zipfile

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from update_client import PUBLIC_KEY, canonical

REPO = 'Olegu621/xlamBOT-LDPlayer'
LATEST = f'https://raw.githubusercontent.com/{REPO}/main/latest.json'
HOST_FILES = {'dnplayer.exe', 'dnplycore.dll', 'dnresource.rcc', 'xlambot-avatar.ico', 'xlambot-avatar.png'}
GUEST_FILES = {'guest/Trebuchet-LDPlayer.apk', 'guest/Settings-xlamBOT-system.apk'}
FILES = HOST_FILES | GUEST_FILES


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def verify_manifest(envelope):
    manifest = envelope['manifest']
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY)).verify(
        bytes.fromhex(envelope['signature']), canonical(manifest))
    if manifest.get('repository') != REPO or manifest.get('base_version') != '9.5.37.0':
        raise ValueError('INVALID_EDITION')
    if type(manifest.get('revision')) is not int or manifest['revision'] < 1:
        raise ValueError('INVALID_EDITION')
    if set(manifest.get('files', {})) != FILES:
        raise ValueError('INVALID_EDITION')
    for value in manifest['files'].values():
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
            raise ValueError('INVALID_EDITION')
    for name, limit in [('base', 1500 * 1024 * 1024), ('package', 120 * 1024 * 1024)]:
        item = manifest[name]
        if not isinstance(item, dict) or type(item.get('size')) is not int or not 0 < item['size'] <= limit:
            raise ValueError('INVALID_EDITION')
        if not re.fullmatch('[0-9a-f]{64}', str(item.get('sha256', ''))):
            raise ValueError('INVALID_EDITION')
        expected = f'https://github.com/{REPO}/releases/download/edition-{manifest["revision"]}/'
        filename = 'LDPlayer_9.5.37.0.exe' if name == 'base' else 'edition.zip'
        if item.get('url') != expected + filename:
            raise ValueError('INVALID_EDITION')
    return manifest


def latest():
    with requests.get(LATEST, timeout=(10, 20), stream=True) as response:
        response.raise_for_status()
        data = bytearray()
        for block in response.iter_content(8192):
            data.extend(block)
            if len(data) > 32 * 1024:
                raise ValueError('INVALID_EDITION')
    envelope = json.loads(data)
    verify_manifest(envelope)
    return envelope


def download(item, destination, progress=None):
    destination = Path(destination)
    if destination.is_file() and destination.stat().st_size == item['size'] and digest(destination) == item['sha256']:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix('.download')
    try:
        end = time.monotonic() + 1200
        total = 0
        with requests.get(item['url'], stream=True, timeout=(15, 30)) as response, part.open('wb') as output:
            response.raise_for_status()
            for block in response.iter_content(1024 * 1024):
                total += len(block)
                if total > item['size'] or time.monotonic() > end:
                    raise ValueError('DOWNLOAD_LIMIT')
                output.write(block)
                if progress:
                    progress(f'download:{total}:{item["size"]}')
        if total != item['size'] or digest(part) != item['sha256']:
            raise ValueError('EDITION_CHECKSUM')
        os.replace(part, destination)
    finally:
        part.unlink(missing_ok=True)
    return destination


def extract_package(archive, manifest, target):
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        if set(names) != FILES or len(names) != len(FILES) or sum(i.file_size for i in zipped.infolist()) > 160 * 1024 * 1024:
            raise ValueError('INVALID_EDITION_ARCHIVE')
        for name in names:
            data = zipped.read(name)
            if hashlib.sha256(data).hexdigest() != manifest['files'][name]:
                raise ValueError('EDITION_CHECKSUM')
            destination = Path(target) / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)


def stopped(manager):
    items = manager.instances()
    for item in items:
        manager._idle_bot(item)
    if any(item['running'] for item in items):
        raise ValueError('CLOSE_EMULATOR_FIRST')


def record_package(manager, staged, manifest):
    cache = manager.home / 'packages' / str(manifest['revision'])
    cache.mkdir(parents=True, exist_ok=True)
    for name in GUEST_FILES:
        shutil.copy2(Path(staged) / name, cache / Path(name).name)


def record_edition(manager, manifest):
    folder = manager.installation
    edition = {'name': 'LDPlayer - Special for xlamBOT', 'base_version': manifest['base_version'],
               'edition_version': manifest['edition_version'], 'mod_revision': manifest['revision'],
               'multi_instance_manager': True, 'native_system_settings': True}
    marker = folder / 'xlamBOT-edition.json'
    if marker.is_symlink():
        raise ValueError('INVALID_INSTALLATION')
    temp = folder / 'xlamBOT-edition.tmp'
    temp.write_bytes(canonical(edition))
    os.replace(temp, marker)


def apply_host(manager, staged, manifest):
    stopped(manager)
    folder = manager.installation
    try:
        old = json.loads((folder / 'xlamBOT-edition.json').read_text('utf-8'))
    except (OSError, ValueError):
        old = {}
    if old.get('mod_revision', 0) > manifest['revision']:
        raise ValueError('EDITION_ROLLBACK_BLOCKED')
    backup = manager.home / 'backups' / f'{time.time_ns()}'
    backup.mkdir(parents=True)
    replaced = []
    try:
        for name in sorted(HOST_FILES):
            stopped(manager)
            target = folder / name
            if target.is_symlink() or target.resolve().parent != folder:
                raise ValueError('INVALID_INSTALLATION')
            if target.exists():
                shutil.copy2(target, backup / name)
            temp = folder / (name + '.xlambot-new')
            shutil.copy2(Path(staged) / name, temp)
            os.replace(temp, target)
            replaced.append(name)
        # Guest assets live outside Android disks; apply only to a explicitly chosen stopped instance.
        record_package(manager, staged, manifest)
        record_edition(manager, manifest)
    except Exception:
        for name in reversed(replaced):
            original = backup / name
            if original.exists():
                os.replace(original, folder / name)
            else:
                (folder / name).unlink(missing_ok=True)
        raise


def install_edition(manager, install_base=False):
    fresh = not manager.installation
    manager.phase('checking')
    envelope = latest()
    manifest = verify_manifest(envelope)
    cache = manager.home / 'downloads' / str(manifest['revision'])
    package = download(manifest['package'], cache / 'edition.zip', manager.phase)
    if not manager.installation:
        if not install_base:
            raise ValueError('LDPLAYER_NOT_FOUND')
        installer = download(manifest['base'], cache / 'LDPlayer_9.5.37.0.exe', manager.phase)
        manager.phase('vendor_setup')
        # The official signed engine installer handles drivers and Windows permissions.
        process = subprocess.Popen([str(installer)], cwd=cache)
        process.wait(timeout=1200)
        manager.installation = manager.discover()
        if not manager.installation:
            raise ValueError('FINISH_LDPLAYER_SETUP')
        items = manager.instances()
        with manager.lock:
            manager.job['indices'] = [i['index'] for i in items]
        for item in items:
            manager._idle_bot(item)
            if item['running']:
                manager.console('quit', '--index', item['index'])
        manager._wait(lambda rows: all(not i['running'] for i in rows))
        manager.native_manager(close=True)
    manager.phase('applying')
    try:
        current = json.loads((manager.installation / 'xlamBOT-edition.json').read_text('utf-8'))
    except (OSError, ValueError):
        current = {}
    if current.get('mod_revision', 0) > manifest['revision']:
        raise ValueError('EDITION_ROLLBACK_BLOCKED')
    with tempfile.TemporaryDirectory(dir=cache) as staging:
        extract_package(package, manifest, staging)
        same = all((manager.installation / name).is_file() and not (manager.installation / name).is_symlink()
                   and digest(manager.installation / name) == manifest['files'][name] for name in HOST_FILES)
        if same:
            # Adopt an already installed, byte-identical signed edition without restarting it.
            record_package(manager, staging, manifest)
            record_edition(manager, manifest)
        else:
            apply_host(manager, staging, manifest)
    (cache / 'signed-manifest.json').write_bytes(canonical(envelope))
    if fresh:
        for item in manager.instances():
            manager.configure(item)
            customize_instance(manager, item['index'])
            from .game_updates import update_game
            update_game(manager, item['index'])


def customize_instance(manager, index):
    item = manager._instance(index)
    manager._idle_bot(item)
    if item['running']:
        raise ValueError('CLOSE_EMULATOR_FIRST')
    edition = json.loads((manager.installation / 'xlamBOT-edition.json').read_text('utf-8'))
    revision = edition.get('mod_revision')
    if type(revision) is not int:
        raise ValueError('UPDATE_EDITION_FIRST')
    cache = manager.home / 'packages' / str(revision)
    envelope_path = manager.home / 'downloads' / str(revision) / 'signed-manifest.json'
    manifest = verify_manifest(json.loads(envelope_path.read_text('utf-8')))
    for name in GUEST_FILES:
        if digest(cache / Path(name).name) != manifest['files'][name]:
            raise ValueError('EDITION_CHECKSUM')
    manager.phase('booting')
    manager.console('launch', '--index', index)
    try:
        manager._wait(lambda rows: any(i['index'] == index and i['ready'] for i in rows))
        def adb(command):
            manager._idle_bot(manager._instance(index))
            return manager.console('adb', '--index', index, '--command', command, timeout=60)
        manager._wait(lambda rows: adb('shell getprop sys.boot_completed').strip() == '1', timeout=180)
        manager.phase('guest_setup')
        for filename, package in [('Trebuchet-LDPlayer.apk', 'com.android.launcher3'),
                                  ('Settings-xlamBOT-system.apk', 'com.android.settings')]:
            manager._idle_bot(manager._instance(index))
            manager.console('installapp', '--index', index, '--filename', cache / filename, timeout=120)
            def installed(rows):
                paths = adb(f'shell pm path {package}').splitlines()
                path = next((p[8:].strip() for p in paths if p.startswith('package:') and '/data/app/' in p), '')
                return bool(re.fullmatch(r'/data/app/[A-Za-z0-9_./=+\-]+', path) and
                            manifest['files']['guest/' + filename] in adb('shell sha256sum ' + path))
            # installapp is asynchronous, and the original system package may
            # already exist. Wait for the exact installed update, not any path.
            manager._wait(installed, timeout=150)
        adb('shell cmd package set-home-activity com.android.launcher3/.lineage.LineageLauncher')
        if 'com.android.launcher3/.lineage.LineageLauncher' not in adb('shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME'):
            raise RuntimeError('GUEST_HOME_FAILED')
        # Only the two vendor ad applications are disabled; no game, accounts or files are cleared.
        for package in ('com.android.ld.appstore', 'com.ldmnq.launcher3'):
            adb('shell pm disable-user --user 0 ' + package)
        for command in ('settings put global window_animation_scale 0',
                        'settings put global transition_animation_scale 0',
                        'settings put global animator_duration_scale 0',
                        'settings put system accelerometer_rotation 0',
                        'settings put global stay_on_while_plugged_in 3'):
            adb('shell ' + command)
        (manager.home / f'instance-{index}.json').write_bytes(canonical({'revision': revision}))
    finally:
        manager._idle_bot(manager._instance(index))
        manager.console('quit', '--index', index)
        manager._wait(lambda rows: any(i['index'] == index and not i['running'] for i in rows))
