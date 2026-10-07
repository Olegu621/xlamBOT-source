import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
from work_modes import resolve, style, movement, danger_weight
from settings_schema import validate


def box(x,y=0):return [x-5,y-5,x+5,y+5]


class WorkModeTests(unittest.TestCase):
    def choose(self,level,enemies,allies=()):
        return movement(level,(0.,100.),(0.,0.),enemies,allies,200,100,40,100)

    def test_five_modes_have_distinct_combat_intents(self):
        enemies=[box(180)]
        self.assertLess(self.choose(1,enemies)[0],0)
        self.assertEqual(self.choose(2,enemies),(0.,100.))
        self.assertGreater(self.choose(3,enemies)[0],0)
        self.assertEqual(style(4),'aggressive.xlambot')
        self.assertGreater(self.choose(5,[box(80)])[0],0)

    def test_balanced_mode_retreats_from_a_group_but_engages_with_support(self):
        enemies=[box(180),box(190)]
        self.assertLess(self.choose(3,enemies)[0],0)
        self.assertGreater(self.choose(3,enemies,[box(70)])[0],0)
        self.assertEqual(sorted([danger_weight(n) for n in range(1,6)],reverse=True),
                         [danger_weight(n) for n in range(1,6)])

    def test_old_styles_migrate_without_changing_existing_behavior(self):
        self.assertEqual(resolve({'current_playstyle':'showdown_survivor.xlambot'}),2)
        self.assertEqual(resolve({'current_playstyle':'aggressive.xlambot'}),4)
        self.assertEqual(resolve({'work_mode':3,'current_playstyle':'aggressive.xlambot'}),3)
        for bad in [0,6,True,'5',None]:
            self.assertEqual(resolve({'work_mode':bad}),2)
            with self.assertRaises(ValueError):validate('work_mode',bad,2)

    def test_new_setting_is_saved_per_device_and_does_not_change_think(self):
        import utils,device_profiles
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder);shutil.copytree(root/'cfg',data/'cfg')
            with patch.object(utils,'PROJECT_ROOT',data),patch.object(utils,'DATA_ROOT',data):
                original_a=device_profiles.read_settings('mode-A')
                original_b=device_profiles.read_settings('mode-B')
                device_profiles.update_settings('mode-A','cfg/bot_config.toml',{'work_mode':5})
                saved=device_profiles.read_settings('mode-A')
                self.assertEqual(saved['bot_config']['work_mode'],5)
                self.assertEqual(saved['general_config'],original_a['general_config'])
                self.assertEqual(device_profiles.read_settings('mode-B'),original_b)
                with self.assertRaises(ValueError):
                    device_profiles.update_settings('mode-A','cfg/bot_config.toml',{'work_mode':7})


if __name__=='__main__':unittest.main()
