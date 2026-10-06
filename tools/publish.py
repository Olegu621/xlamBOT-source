"""Build a cumulative, signed script release without packaging user data."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import py_compile
import sys
import tempfile
from cryptography.hazmat.primitives import serialization
from source_sync import synchronize, mark_release, git

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--key', type=Path, required=True)
parser.add_argument('--revision', type=int, required=True)
parser.add_argument('--source-repo', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--output-root', type=Path, default=Path(__file__).resolve().parents[1] / 'dist')
args = parser.parse_args()
if args.revision < 1:
    parser.error('revision must be positive')
if git(args.source_repo, 'tag', '--list', f'bot-revision-{args.revision}'):
    parser.error('revision already published; use a new revision')
source_commit = synchronize(args.source, args.source_repo, args.revision)
source = args.source_repo.resolve()
files = {}
for path in source.glob('*.py'):
    if path.name not in {'update_client.py', 'xlambot_launcher.py', 'setup.py'} and not path.name.startswith(('test_', 'tools_')):
        files[path.name] = path
for directory, extensions in {'webui': {'.py'}, 'api': {'.py'}, 'static': {'.js', '.css'}, 'templates': {'.html'}}.items():
    for path in (source / directory).rglob('*'):
        if path.is_file() and path.suffix in extensions and '__pycache__' not in path.parts:
            files[path.relative_to(source).as_posix()] = path
output = args.output_root.resolve() / str(args.revision)
output.mkdir(parents=True, exist_ok=True)
payloads = {}
with tempfile.TemporaryDirectory() as temporary:
    for name, path in sorted(files.items()):
        if path.suffix == '.py':
            compiled = Path(temporary) / (name + 'c')
            compiled.parent.mkdir(parents=True, exist_ok=True)
            py_compile.compile(str(path), cfile=str(compiled), dfile=name, doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
            payloads[name + 'c'] = compiled.read_bytes()
        else:
            payloads[name] = path.read_bytes()
with zipfile.ZipFile(output / 'scripts.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for name, data in sorted(payloads.items()):
        info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, data)
data = (output / 'scripts.zip').read_bytes()
manifest = {'repository': 'Olegu621/xlamBOT', 'bootstrap': 1, 'revision': args.revision,
    'python': f'{sys.version_info.major}.{sys.version_info.minor}',
    'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
    'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())}}
canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
key = serialization.load_pem_private_key(args.key.read_bytes(), password=None)
(output / 'manifest.json').write_text(json.dumps({'manifest': manifest, 'signature': key.sign(canonical).hex()}, ensure_ascii=False, indent=2), 'utf-8')
mark_release(args.source_repo, args.revision, source_commit, manifest['sha256'])
(output / 'source-provenance.json').write_text(json.dumps({'repository': 'Olegu621/xlamBOT-source', 'commit': source_commit, 'tag': f'bot-revision-{args.revision}', 'revision': args.revision, 'archive_sha256': manifest['sha256']}, indent=2), 'utf-8')
print(f'{len(files)} files, {len(data)} bytes: {output}; sources {source_commit}')
