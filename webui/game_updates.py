"""Original Brawl Stars delivery; signed releases, pinned publisher, no data reset."""
from __future__ import annotations
import hashlib
import json
import re
import struct
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from update_client import PUBLIC_KEY, canonical
from .emulator_distribution import REPO, download

PACKAGE = 'com.supercell.brawlstars'
# Supercell publishes this certificate in link.brawlstars.com/.well-known/assetlinks.json.
SUPERCELL_CERT = '731a29e80b7ca89c7e9b39d381821ee8dccd1b0456782f788650945e7d60d8d3'
LATEST = f'https://raw.githubusercontent.com/{REPO}/main/latest-game.json'


def apk_certificate(path):
    """Read the v2/v3 signing certificate; Android verifies the signature on install."""
    def lp(data, offset=0):
        if offset + 4 > len(data): raise ValueError('INVALID_APK_SIGNATURE')
        size = struct.unpack_from('<I', data, offset)[0]
        end = offset + 4 + size
        if end > len(data): raise ValueError('INVALID_APK_SIGNATURE')
        return data[offset+4:end], end
    with Path(path).open('rb') as stream:
        stream.seek(0, 2); size = stream.tell()
        if size < 22: raise ValueError('INVALID_APK_SIGNATURE')
        stream.seek(max(0, size - 65557)); tail = stream.read()
        offset = tail.rfind(b'PK\x05\x06')
        if offset < 0 or offset+22+struct.unpack_from('<H',tail,offset+20)[0] != len(tail):
            raise ValueError('INVALID_APK_SIGNATURE')
        central = struct.unpack_from('<I',tail,offset+16)[0]
        if central < 24 or central > size: raise ValueError('INVALID_APK_SIGNATURE')
        stream.seek(central-24); footer=stream.read(24)
        block_size=struct.unpack_from('<Q',footer)[0]
        if footer[8:] != b'APK Sig Block 42' or not 32 <= block_size <= 16*1024*1024 or block_size+8 > central:
            raise ValueError('INVALID_APK_SIGNATURE')
        stream.seek(central-block_size-8); block=stream.read(block_size+8)
    if struct.unpack_from('<Q',block)[0] != block_size: raise ValueError('INVALID_APK_SIGNATURE')
    pos=8; certs=[]
    while pos < len(block)-24:
        if pos+8 > len(block)-24: raise ValueError('INVALID_APK_SIGNATURE')
        length=struct.unpack_from('<Q',block,pos)[0];pos+=8
        if length < 4 or pos+length > len(block)-24: raise ValueError('INVALID_APK_SIGNATURE')
        identifier=struct.unpack_from('<I',block,pos)[0];value=block[pos+4:pos+length];pos+=length
        if identifier not in (0x7109871a,0xf05368c0):continue
        signers,end=lp(value)
        if end != len(value):raise ValueError('INVALID_APK_SIGNATURE')
        signer,end=lp(signers)
        if end != len(signers):raise ValueError('INVALID_APK_SIGNATURE')
        signed,_=lp(signer);_,after_digests=lp(signed);certificates,_=lp(signed,after_digests);certificate,_=lp(certificates)
        certs.append(hashlib.sha256(certificate).hexdigest())
    if not certs or set(certs) != {SUPERCELL_CERT}:raise ValueError('NOT_ORIGINAL_BRAWL_STARS')
    return SUPERCELL_CERT


def verify(envelope):
    m=envelope['manifest']
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY)).verify(bytes.fromhex(envelope['signature']),canonical(m))
    if m.get('repository') != REPO or m.get('package_name') != PACKAGE or m.get('certificate') != SUPERCELL_CERT:
        raise ValueError('INVALID_GAME_RELEASE')
    if type(m.get('version_code')) is not int or not 1 <= m['version_code'] <= 2**31-1:
        raise ValueError('INVALID_GAME_RELEASE')
    if not isinstance(m.get('files'),dict) or not 1 <= len(m['files']) <= 32 or 'base.apk' not in m['files']:
        raise ValueError('INVALID_GAME_RELEASE')
    for name,value in m['files'].items():
        if not re.fullmatch(r'(base|split_[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\.apk',name) or not re.fullmatch('[0-9a-f]{64}',str(value)):
            raise ValueError('INVALID_GAME_RELEASE')
    a=m['archive']
    if type(a.get('size')) is not int or not 0 < a['size'] <= 1800*1024*1024 or not re.fullmatch('[0-9a-f]{64}',str(a.get('sha256',''))):
        raise ValueError('INVALID_GAME_RELEASE')
    if a.get('url') != f'https://github.com/{REPO}/releases/download/game-{m["version_code"]}/brawlstars.zip':
        raise ValueError('INVALID_GAME_RELEASE')
    return m


def latest():
    with requests.get(LATEST,stream=True,timeout=(10,20)) as response:
        response.raise_for_status();raw=bytearray()
        for block in response.iter_content(8192):
            raw.extend(block)
            if len(raw)>32768:raise ValueError('INVALID_GAME_RELEASE')
    envelope=json.loads(raw);verify(envelope);return envelope


def installed_version(manager,index):
    text=manager.console('adb','--index',index,'--command',f'shell dumpsys package {PACKAGE}')
    match=re.search(r'\bversionCode=(\d+)\b',text)
    if not match:
        paths=manager.console('adb','--index',index,'--command',f'shell pm path {PACKAGE}')
        if 'package:' in paths:raise ValueError('GAME_VERSION_UNAVAILABLE')
    return int(match[1]) if match else 0


def game_in_foreground(manager,index):
    text=manager.console('adb','--index',index,'--command','shell dumpsys window windows')
    focus=re.search(r'mCurrentFocus=Window\{[^\n]*?\s([^\s/]+)/[^\s}]+',text)
    if not focus:raise ValueError('GAME_FOCUS_UNAVAILABLE')
    return focus[1] == PACKAGE


def update_game(manager,index,allow_close=True,manifest=None):
    item=manager._instance(index);manager._idle_bot(item)
    manager.phase('checking_game')
    m=manifest or verify(latest())
    owned=not item['running']
    try:
        if owned:
            manager.phase('booting');manager.console('launch','--index',index)
            manager._wait(lambda rows:any(i['index']==index and i['ready'] for i in rows),timeout=180)
        manager._wait(lambda rows:manager.console('adb','--index',index,'--command','shell getprop sys.boot_completed').strip()=='1',timeout=180)
        manager._idle_bot(manager._instance(index))
        current=installed_version(manager,index)
        if current>m['version_code']:raise ValueError('GAME_DOWNGRADE_BLOCKED')
        if current==m['version_code']:return
        if not allow_close and game_in_foreground(manager,index):raise ValueError('CLOSE_GAME_FIRST')
        archive=download(m['archive'],manager.home/'game'/str(m['version_code'])/'brawlstars.zip',manager.phase)
        with tempfile.TemporaryDirectory(dir=archive.parent) as staging:
            with zipfile.ZipFile(archive) as zipped:
                if set(zipped.namelist())!=set(m['files']) or len(zipped.namelist())!=len(m['files']) or sum(i.file_size for i in zipped.infolist())>2000*1024*1024:
                    raise ValueError('INVALID_GAME_ARCHIVE')
                paths=[]
                for name,expected in sorted(m['files'].items()):
                    path=Path(staging)/name
                    value=hashlib.sha256()
                    with zipped.open(name) as source,path.open('wb') as dest:
                        for block in iter(lambda:source.read(1024*1024),b''):
                            dest.write(block);value.update(block)
                    if value.hexdigest()!=expected:raise ValueError('GAME_CHECKSUM')
                    apk_certificate(path);paths.append(path)
            manager._idle_bot(manager._instance(index))
            if not allow_close and game_in_foreground(manager,index):raise ValueError('CLOSE_GAME_FIRST')
            manager.phase('installing_game')
            flags=['-r']
            sdk=manager.console('adb','--index',index,'--command','shell getprop ro.build.version.sdk').strip()
            if sdk=='28':
                # LDPlayer's package manager provides SDK compatibility without
                # altering APKs or their Supercell signature.
                help_text=manager.console('adb','--index',index,'--command','shell pm help')
                if '--force-sdk' not in help_text:raise ValueError('INCOMPATIBLE_ANDROID')
                flags.append('--force-sdk')
            if allow_close:
                manager.console('adb','--index',index,'--command',f'shell am force-stop {PACKAGE}')
            # One atomic split-APK session; -r preserves the game's existing data.
            result=subprocess.run([str(manager.installation/'adb.exe'),'-s',item['serial'],'install-multiple',*flags,*map(str,paths)],
                                  capture_output=True,timeout=1200,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode or b'Success' not in result.stdout:
                raise RuntimeError('GAME_INSTALL_FAILED')
            if installed_version(manager,index)!=m['version_code']:raise RuntimeError('GAME_INSTALL_FAILED')
    finally:
        if owned:
            manager._idle_bot(manager._instance(index));manager.console('quit','--index',index)
            manager._wait(lambda rows:any(i['index']==index and not i['running'] for i in rows))
