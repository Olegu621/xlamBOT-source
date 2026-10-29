"""Vince on an existing installation: selection, identity and ranged combat."""
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import utils
import trophy_reader
from brawler_catalog import BUILT_IN_BRAWLERS
from super_policy import choose

ROOT = Path(__file__).resolve().parents[1]


class VinceTests(unittest.TestCase):
    def test_old_installation_receives_vince_without_changing_saved_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'brawlers_info.json'
            original = b'{"shelly":{"attack_range":490}}'
            path.write_bytes(original)
            with patch.object(utils, 'brawlers_info_file_path', path):
                self.assertIn('vince', utils.get_brawler_list())
                self.assertIn('vince', trophy_reader._known_brawler_names())
                self.assertEqual(utils.load_brawlers_info()['vince']['actual_name'], 'Vince')
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_saved_vince_overrides_survive_and_defaults_do_not_leak(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'brawlers_info.json'
            path.write_text(json.dumps({'vince':{'safe_range':400}}),'utf8')
            with patch.object(utils, 'brawlers_info_file_path', path):
                first = utils.load_brawlers_info()
                self.assertEqual(first['vince']['safe_range'],400)
                self.assertEqual(first['vince']['super_range'],576)
                first['vince']['attack_range']=1
                self.assertEqual(utils.load_brawlers_info()['vince']['attack_range'],533)

    def test_readable_table_matches_signed_catalogue(self):
        table=json.loads((ROOT/'cfg/brawlers_info.json').read_text('utf8'))
        self.assertEqual(table['vince'],BUILT_IN_BRAWLERS['vince'])

    def test_card_name_and_near_miss_are_known_after_catalogue_update(self):
        names=trophy_reader._known_brawler_names()
        for text in ('VINCE','V1NCE'):
            self.assertEqual(trophy_reader._match_brawler_name(text,names),'vince')
        self.assertIsNone(trophy_reader._match_brawler_name('ZZZZZZZZZZZZ',names))

    def test_manual_search_confirms_vince_and_rejects_another_card(self):
        from lobby_automation import LobbyAutomation
        window=Mock()
        bot=SimpleNamespace(window_controller=window,_frame_state=lambda f:f,
            _should_interrupt=lambda *a:False,_sleep_interruptible=lambda *a:False,
            _confirm_brawler_selection=Mock(return_value=True),_last_picked=None)
        reader=SimpleNamespace(read_card=lambda *a,**k:{'brawler':'vince','trophies':12})
        window.screenshot.side_effect=['lobby','brawler_selection','brawler_selection','brawler_selection','lobby']
        with patch.dict('sys.modules',{'trophy_reader':reader}):
            self.assertEqual(LobbyAutomation.select_brawler(bot,'Vince',lambda:'lobby'),'success')
        window.type_text.assert_called_once_with('Vince')
        bot._confirm_brawler_selection.assert_called_once()
        self.assertEqual(bot._last_picked['brawler'],'vince')
        window.screenshot.side_effect=['lobby','brawler_selection','brawler_selection']
        window.click.reset_mock();reader.read_card=lambda *a,**k:{'brawler':'colt'}
        with patch.dict('sys.modules',{'trophy_reader':reader}):
            self.assertEqual(LobbyAutomation.select_brawler(bot,'vince',lambda:'lobby'),'failed')
        self.assertEqual(window.click.call_count,1)

    def test_autopick_adopts_vince_without_reassigning_previous_trophies(self):
        from stage_manager import StageManager
        manager=StageManager.__new__(StageManager)
        manager.Lobby_automation=SimpleNamespace(last_picked={'brawler':'vince','trophies':12})
        manager.brawlers_pick_data=[{'brawler':'shelly','trophies':900,'wins':0}]
        manager.brawler_sort_mode=lambda:'lowest_to_highest'
        manager.Trophy_observer=Mock()
        manager._adopt_picked_brawler('shelly',3)
        self.assertEqual(manager._confirmed_brawler,'vince')
        self.assertEqual(manager.brawlers_pick_data[0]['trophies'],12)
        self.assertEqual(manager.brawlers_pick_data[1]['trophies'],900)

    def test_damage_super_uses_its_own_range_and_does_not_cross_walls(self):
        info=utils.load_brawlers_info()['vince']
        for distance,visible,expected in ((560,True,True),(590,True,False),(300,False,False)):
            self.assertEqual(choose('vince',info,4,(0,0),[[distance-10,-10,distance+10,10]],
                                    533,576,lambda b:visible),expected)

    def strategy(self,style,distance,gas=False):
        info=utils.load_brawlers_info()['vince'];events=[]
        context=dict(brawler='vince',current_brawler='vince',brawlers_info={'vince':info},
            persistent_data={'time_since_holding_attack':None},must_brawler_hold_attack=lambda *a:False,
            get_brawler_range=lambda b:(328,533,576),get_entity_pos=lambda b:(0,0),
            player_data=[-10,-10,10,10],walls=[],JOYSTICK_RADIUS=100,TILE_SIZE=64,
            is_path_blocked=lambda *a:False,get_random_movement=lambda:(0,-100),
            is_there_poison_gas=lambda *a:dict(up=0,down=0,left=int(gas),right=0),
            is_there_enemy=lambda e:bool(e),enemy_data=[[distance-10,-10,distance+10,10]],
            teammate_data=[],find_closest_enemy=lambda *a:((distance,0),distance),
            find_closest_teammate=lambda *a:(None,None),is_enemy_hittable=lambda *a:True,
            is_super_ready=True,is_gadget_ready=False,is_hypercharge_ready=False,
            attack=lambda **k:events.append('attack'),use_super=lambda:events.append('super'),
            use_gadget=Mock(),use_hypercharge=Mock(),seconds_to_hold_attack_after_reaching_max=0)
        _,code=utils.load_playstyle_script(style)
        move,_=utils.interpret_playstyle_code(compile(code,'<vince-test>','exec'),context)
        return move,events

    def test_both_classic_styles_super_before_attack_and_retreat_at_close_range(self):
        for style in ('survivor.xlambot','aggressive.xlambot'):
            move,events=self.strategy(style,100)
            self.assertLess(move[0],0)
            self.assertEqual(events,['super','attack'])

    def test_super_only_between_attack_and_super_range_and_no_out_of_range_fire(self):
        for style in ('survivor.xlambot','aggressive.xlambot'):
            _,events=self.strategy(style,560)
            self.assertEqual(events,['super'])
            _,events=self.strategy(style,600)
            self.assertEqual(events,[])

    def test_gas_escape_keeps_priority_over_retreat(self):
        for style in ('survivor.xlambot','aggressive.xlambot'):
            move,_=self.strategy(style,100,gas=True)
            self.assertGreater(move[0],0)


if __name__=='__main__':
    unittest.main()
