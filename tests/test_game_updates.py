import copy
import hashlib
import json
from pathlib import Path
import tempfile
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch
import zipfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
package=ModuleType('webui');package.__path__=[str(Path(__file__).resolve().parents[1]/'webui')]
with patch.dict(sys.modules,{'webui':package}):
    from webui import game_updates as game
from update_client import canonical

class GameDeliveryTests(unittest.TestCase):
    def release(self):
        key=Ed25519PrivateKey.generate()
        public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()
        m=dict(repository=game.REPO,package_name=game.PACKAGE,certificate=game.SUPERCELL_CERT,version_code=69414,version_name='69.414',files={'base.apk':'a'*64,'split_config.arm64_v8a.apk':'b'*64},archive=dict(url=f'https://github.com/{game.REPO}/releases/download/game-69414/brawlstars.zip',size=10,sha256='c'*64))
        return key,public,m

    def test_signed_wrong_publisher_paths_and_downgrade_metadata_rejected(self):
        key,public,m=self.release()
        with patch.object(game,'PUBLIC_KEY',public):
            self.assertEqual(game.verify(dict(manifest=m,signature=key.sign(canonical(m)).hex()))['version_code'],69414)
            for change in (dict(package_name='another.game'),dict(certificate='0'*64),dict(version_code=True),dict(files={'../base.apk':'a'*64}),dict(archive=dict(m['archive'],url='https://example.org/game.zip'))):
                broken=dict(m,**change)
                with self.assertRaises(ValueError):game.verify(dict(manifest=broken,signature=key.sign(canonical(broken)).hex()))
            tampered=copy.deepcopy(m);tampered['version_code']=70000
            with self.assertRaises(Exception):game.verify(dict(manifest=tampered,signature=key.sign(canonical(m)).hex()))

    def test_unavailable_version_and_focus_never_treated_as_idle(self):
        m=Mock()
        m.console.side_effect=['', 'package:/data/app/base.apk']
        with self.assertRaisesRegex(ValueError,'GAME_VERSION_UNAVAILABLE'):game.installed_version(m,0)
        m.console.side_effect=None;m.console.return_value=''
        with self.assertRaisesRegex(ValueError,'GAME_FOCUS_UNAVAILABLE'):game.game_in_foreground(m,0)
        m.console.return_value='mCurrentFocus=Window{123 u0 com.supercell.brawlstars/GameApp}'
        self.assertTrue(game.game_in_foreground(m,0))

    def test_background_update_never_stops_foreground_game(self):
        _,_,manifest=self.release();m=Mock();m._instance.return_value=dict(index=0,running=True,serial='emulator-5554')
        with patch.object(game,'installed_version',return_value=69000),patch.object(game,'game_in_foreground',return_value=True),patch.object(game,'download') as download:
            with self.assertRaisesRegex(ValueError,'CLOSE_GAME_FIRST'):game.update_game(m,0,allow_close=False,manifest=manifest)
            download.assert_not_called()
        self.assertFalse(any('force-stop' in str(call) for call in m.console.call_args_list))

    def test_corrupt_game_archive_does_not_stop_or_replace_game(self):
        _,_,manifest=self.release();m=Mock();m._instance.return_value=dict(index=0,running=True,serial='emulator-5554')
        with tempfile.TemporaryDirectory() as folder:
            m.home=Path(folder)
            archive=Path(folder)/'game.zip'
            with zipfile.ZipFile(archive,'w') as zipped:zipped.writestr('../base.apk',b'bad')
            with patch.object(game,'installed_version',return_value=69000),patch.object(game,'download',return_value=archive),patch('subprocess.run') as install:
                with self.assertRaisesRegex(ValueError,'INVALID_GAME_ARCHIVE'):game.update_game(m,0,manifest=manifest)
                install.assert_not_called()
        self.assertFalse(any('force-stop' in str(call) for call in m.console.call_args_list))

    def test_newer_installed_game_preserved(self):
        _,_,manifest=self.release();m=Mock();m._instance.return_value=dict(index=0,running=True,serial='emulator-5554')
        with patch.object(game,'installed_version',return_value=70000),patch.object(game,'download') as download:
            with self.assertRaisesRegex(ValueError,'GAME_DOWNGRADE_BLOCKED'):game.update_game(m,0,manifest=manifest)
            download.assert_not_called()

    def test_boot_failure_closes_only_instance_started_by_updater(self):
        _,_,manifest=self.release();m=Mock();m._instance.return_value=dict(index=2,running=False,serial='emulator-5558');m._wait.side_effect=[TimeoutError(),True]
        with self.assertRaises(TimeoutError):game.update_game(m,2,manifest=manifest)
        m.console.assert_any_call('quit','--index',2)

    def test_invalid_apk_signing_block_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            apk=Path(folder)/'base.apk'
            for content in (b'',b'APK Sig Block 42'*10,b'PK\x05\x06'+b'\0'*18):
                apk.write_bytes(content)
                with self.assertRaises(ValueError):game.apk_certificate(apk)
