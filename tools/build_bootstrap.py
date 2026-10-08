"""Rebuild PC bootstrap against an existing runtime without copying user data."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import toml


def prepare(source, runtime, destination):
    source, runtime, destination = map(lambda path: Path(path).resolve(), (source, runtime, destination))
    if destination.is_relative_to(source) or destination == runtime:
        raise ValueError('Build destination must be separate from source and runtime')
    if destination.exists():
        raise ValueError('Choose a new build destination; existing files are preserved')
    internal = runtime / '_internal' if (runtime / '_internal').is_dir() else runtime
    ignored = shutil.ignore_patterns('.git', '__pycache__', '.venv', 'tests', 'dist', 'build',
        'devices', 'training', 'debug_frames', 'logs', 'web_resources', 'models', 'vendor', 'scrcpy',
        '*.pem', '*.key', '.env*', 'match_history*', 'cfg.zip')
    shutil.copytree(source, destination, ignore=ignored)
    for name in ['models', 'vendor', 'scrcpy']:
        origin = internal / name
        if not origin.is_dir():
            raise ValueError('Missing runtime resource: ' + name)
        shutil.copytree(origin, destination / name)
    for name in ['api/assets']:
        origin = internal / name
        if origin.is_dir(): shutil.copytree(origin, destination / name, dirs_exist_ok=True)
    secrets = {'key', 'discord_bot_token', 'telegram_token', 'webhook_url'}
    def scrub(values):
        for key, value in values.items():
            if key in secrets: values[key] = ''
            elif key == 'player_tag': values[key] = '#'
            elif isinstance(value, dict): scrub(value)
    for config in (destination / 'cfg').glob('*.toml'):
        values = toml.loads(config.read_text('utf-8-sig')); scrub(values)
        config.write_text(toml.dumps(values), encoding='utf-8')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    folder = prepare(args.source, args.runtime, args.destination)
    subprocess.run([sys.executable, '-m', 'PyInstaller', 'xlambot.spec', '--noconfirm'], cwd=folder, check=True)
    print(folder / 'dist' / 'xlamBOT' / 'xlamBOT.exe')


if __name__ == '__main__': main()
