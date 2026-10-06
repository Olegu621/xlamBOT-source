import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import source_sync

class SourceSyncTests(unittest.TestCase):
    def test_dirty_sources_are_rejected(self):
        with patch.object(source_sync, 'git', side_effect=[source_sync.REMOTE, 'main', ' M bot_instance.py']):
            with self.assertRaisesRegex(RuntimeError, 'uncommitted'):
                source_sync.synchronize('.', '.', 25)

    def test_wrong_remote_is_rejected(self):
        with patch.object(source_sync, 'git', return_value='https://github.com/other/repo.git'):
            with self.assertRaisesRegex(RuntimeError, 'remote'):
                source_sync.synchronize('.', '.', 25)

    def test_release_tag_cannot_be_replaced(self):
        with patch.object(source_sync, 'git', return_value='bot-revision-24') as command:
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                source_sync.mark_release('.', 24, 'abc', 'def')
            self.assertEqual(command.call_count, 1)

    def test_snapshot_excludes_credentials_and_recordings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); source=root/'source'; repo=root/'repo'
            source.mkdir(); repo.mkdir()
            for name in ('bot_instance.py', 'cfg/login.toml', 'devices/user.json', 'training/frame.jpg'):
                p=source/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('private' if '/' in name else 'print(1)')
            def fake_git(directory, *args):
                if args[:2]==('remote','get-url'): return source_sync.REMOTE
                if args[0]=='branch': return 'main'
                if args[:2]==('rev-parse','HEAD'): return 'commit'
                return ''
            with patch.object(source_sync, 'git', side_effect=fake_git):
                self.assertEqual(source_sync.synchronize(source, repo, 25), 'commit')
            self.assertTrue((repo/'bot_instance.py').exists())
            self.assertFalse((repo/'cfg').exists())
            self.assertFalse((repo/'devices').exists())
            self.assertFalse((repo/'training').exists())

if __name__=='__main__': unittest.main()
