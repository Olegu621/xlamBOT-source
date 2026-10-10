import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace,ModuleType
import sys
package=ModuleType('webui')
package.__path__=[str(Path(__file__).resolve().parents[1]/'webui')]
with patch.dict(sys.modules,{'webui':package}):
    from webui import emulator_language as language
host_english,prepare_english=language.host_english,language.prepare_english

class EmulatorLanguageTests(unittest.TestCase):
    def test_host_locale_preserves_instance_independent_settings_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'vms/config/leidians.config';path.parent.mkdir(parents=True)
            original={'languageId':'ru_RU','productLanguageId':'ru_RU','custom':'keep'}
            path.write_text(json.dumps(original),encoding='utf8')
            m=SimpleNamespace(installation=root,home=root/'manager',instances=lambda:[],native_manager=Mock())
            self.assertTrue(host_english(m))
            self.assertEqual(json.loads(path.read_text())['custom'],'keep')
            self.assertEqual(json.loads(path.read_text())['languageId'],'en_US')
            self.assertEqual(json.loads(next((m.home/'backups').glob('*.json')).read_text()),original)

    def test_active_emulator_defers_host_change(self):
        m=SimpleNamespace(instances=lambda:[{'running':True}],native_manager=Mock())
        self.assertFalse(host_english(m));m.native_manager.assert_not_called()

    def test_guest_verification_failure_still_closes_owned_instance(self):
        item={'running':False,'index':1};m=Mock()
        m._instance.return_value=item
        m.console.return_value='ru-RU'
        with patch.object(language,'host_english'),self.assertRaisesRegex(RuntimeError,'GUEST_LANGUAGE_FAILED'):
            prepare_english(m,1)
        self.assertIn(('quit','--index',1),[c.args for c in m.console.call_args_list])

    def test_already_running_guest_is_not_reconfigured(self):
        m=Mock();m._instance.return_value={'running':True,'index':1}
        with self.assertRaisesRegex(ValueError,'CLOSE_EMULATOR_FIRST'):prepare_english(m,1)
        m.console.assert_not_called()
