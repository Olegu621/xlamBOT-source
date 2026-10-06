"""Save release sources before allowing distribution publication."""
import shutil
import subprocess
from pathlib import Path

REMOTE = 'https://github.com/Olegu621/xlamBOT-source.git'

def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

def synchronize(source, repo, revision):
    source, repo = Path(source).resolve(), Path(repo).resolve()
    if git(repo, 'remote', 'get-url', 'origin').removesuffix('.git') != REMOTE.removesuffix('.git'):
        raise RuntimeError('Unexpected source repository remote')
    if git(repo, 'branch', '--show-current') != 'main':
        raise RuntimeError('Merge source PR into main before publishing')
    if git(repo, 'status', '--porcelain'):
        raise RuntimeError('Source repository has uncommitted changes; review and commit them first')
    git(repo, 'pull', '--ff-only', 'origin', 'main')
    if source != repo:
        # Only program code/resources, never runtime profiles, cfg or recordings.
        paths = [p for p in source.glob('*.py') if not p.name.startswith(('test_', 'tools_'))]
        for directory, extensions in {'api':{'.py'}, 'webui':{'.py'}, 'static':{'.js','.css'}, 'templates':{'.html'}}.items():
            paths.extend(p for p in (source/directory).rglob('*') if p.is_file() and p.suffix in extensions and '__pycache__' not in p.parts)
        selected = {p.relative_to(source).as_posix():p for p in paths}
        tracked = git(repo, 'ls-files').splitlines()
        for name in tracked:
            p = Path(name)
            managed = (len(p.parts)==1 and p.suffix=='.py' and not p.name.startswith(('test_', 'tools_'))) or (p.parts[0] in ('api','webui') and p.suffix=='.py') or (p.parts[0]=='static' and p.suffix in ('.js','.css')) or (p.parts[0]=='templates' and p.suffix=='.html')
            if managed and name not in selected:
                (repo/name).unlink(missing_ok=True)
        for name, path in selected.items():
            destination=repo/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        git(repo, 'add', '--all')
        if git(repo, 'diff', '--cached', '--name-only'):
            git(repo, 'commit', '-m', f'Sources for bot revision {revision}')
    git(repo, 'push', 'origin', 'main')
    return git(repo, 'rev-parse', 'HEAD')

def mark_release(repo, revision, commit, archive_hash):
    tag=f'bot-revision-{revision}'
    if git(repo, 'tag', '--list', tag):
        raise RuntimeError(f'{tag} already exists; increase revision, never replace a published tag')
    git(repo, 'tag', '-a', tag, commit, '-m', f'Bot revision {revision}; scripts.zip SHA256 {archive_hash}')
    git(repo, 'push', 'origin', f'refs/tags/{tag}')
