"""Build a signed LDPlayer edition from an explicit account-free inventory."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from cryptography.hazmat.primitives import serialization

HOST = ('dnplayer.exe', 'dnplycore.dll', 'dnresource.rcc', 'xlambot-avatar.ico', 'xlambot-avatar.png')
GUEST = ('Trebuchet-LDPlayer.apk', 'Settings-xlamBOT-system.apk')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', type=Path, required=True)
    parser.add_argument('--guest', type=Path, required=True)
    parser.add_argument('--base-installer', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--revision', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.revision < 1 or args.output.exists():
        raise ValueError('Use a new revision and output folder')
    inventory = {name: args.host / name for name in HOST}
    inventory.update({'guest/' + name: args.guest / name for name in GUEST})
    if any(p.is_symlink() or not p.is_file() for p in inventory.values()):
        raise ValueError('Incomplete edition inventory')
    args.output.mkdir(parents=True)
    archive = args.output / 'edition.zip'
    files = {}
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for name, path in sorted(inventory.items()):
            data = path.read_bytes()
            files[name] = hashlib.sha256(data).hexdigest()
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(info, data)
    repo = 'Olegu621/xlamBOT-LDPlayer'
    prefix = f'https://github.com/{repo}/releases/download/edition-{args.revision}/'
    manifest = {'repository': repo, 'revision': args.revision, 'edition_version': '1.2',
                'base_version': '9.5.37.0', 'files': files,
                'base': {'url': prefix + 'LDPlayer_9.5.37.0.exe', 'size': args.base_installer.stat().st_size, 'sha256': sha(args.base_installer)},
                'package': {'url': prefix + 'edition.zip', 'size': archive.stat().st_size, 'sha256': sha(archive)}}
    key = serialization.load_pem_private_key(args.key.read_bytes(), password=None)
    canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    envelope = {'manifest': manifest, 'signature': key.sign(canonical).hex()}
    (args.output / 'latest.json').write_text(json.dumps(envelope, indent=2), 'utf-8')
    print(f'Edition {args.revision}: {archive.stat().st_size} bytes; {len(files)} explicit files; no Android disks or user data')


if __name__ == '__main__':
    main()
