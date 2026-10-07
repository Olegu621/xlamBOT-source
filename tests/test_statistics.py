import csv,tempfile,unittest
from pathlib import Path
from datetime import datetime
import importlib.util
_spec=importlib.util.spec_from_file_location('statistics_service',Path(__file__).resolve().parents[1]/'webui/statistics.py')
_service=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_service);build=_service.build

class StatisticsTests(unittest.TestCase):
    NOW=datetime(2026,10,7,12)
    def write(self,root,key,rows):
        path=Path(root)/('cfg' if key=='default' else 'devices/'+key+'/cfg')/'match_history.csv';path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=['date_time','brawler_name','result','trophy_delta','account_tag','trophy_source']);writer.writeheader();writer.writerows(rows)
    def row(self,date='2026-10-07T10:00:00',delta='8',result='victory',account='#AAA',brawler='shelly'):
        return dict(date_time=date,brawler_name=brawler,result=result,trophy_delta=delta,account_tag=account,trophy_source='estimated')
    def test_empty_install_has_no_fabricated_trophies_and_creates_no_files(self):
        with tempfile.TemporaryDirectory() as root:
            p=build(root,now=self.NOW);self.assertEqual(p['summary']['matches'],0);self.assertIsNone(p['summary']['trophy_delta']);self.assertIsNone(p['summary']['win_rate']);self.assertEqual(list(Path(root).iterdir()),[])
    def test_filters_do_not_mix_devices_accounts_and_fighters(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root,'emulator-5554',[self.row(),self.row(delta='-3',result='defeat',account='#BBB')]);self.write(root,'emulator-5556',[self.row(brawler='bo',delta='5')])
            all=build(root,now=self.NOW);self.assertEqual(all['summary']['matches'],3);self.assertEqual(all['summary']['trophy_delta'],10)
            chosen=build(root,device='emulator-5554',account='#AAA',brawler='shelly',now=self.NOW);self.assertEqual(chosen['summary']['matches'],1);self.assertEqual(chosen['summary']['trophy_delta'],8)
    def test_legacy_account_is_not_assigned_to_current_account(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root,'emulator-5554',[self.row(account='')]);p=build(root,now=self.NOW)
            self.assertEqual(p['options']['account'],['unknown:emulator-5554']);self.assertEqual(build(root,account='#AAA',now=self.NOW)['summary']['matches'],0)
    def test_missing_delta_is_a_gap_and_draw_counts_in_outcome_denominator(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root,'default',[self.row(delta=''),self.row(date='2026-10-06T10:00:00',delta='0',result='draw')]);p=build(root,now=self.NOW)
            self.assertEqual(p['summary']['win_rate'],50);self.assertEqual(p['summary']['measured_matches'],1);self.assertIsNone(p['series'][-1]['delta']);self.assertIsNone(p['series'][-1]['cumulative'])
    def test_period_is_inclusive_and_future_or_broken_rows_are_excluded(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root,'default',[self.row(date='2026-10-01T00:00:00'),self.row(date='2026-09-30T23:59:59'),self.row(date='2026-10-08T00:00:00'),self.row(date='bad')]);p=build(root,now=self.NOW)
            self.assertEqual(p['summary']['matches'],1);self.assertEqual(p['skipped_rows'],1)
    def test_long_history_is_bounded_without_losing_totals(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root,'default',[self.row(date='2020-01-01T00:00:00'),self.row()]);p=build(root,period='all',now=self.NOW)
            self.assertLessEqual(len(p['series']),120);self.assertEqual(sum(x['matches'] for x in p['series']),2);self.assertEqual(p['summary']['trophy_delta'],16)
    def test_invalid_period_and_nonfinite_trophies(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):build(root,period='100')
            self.write(root,'default',[self.row(delta='NaN')]);self.assertIsNone(build(root,now=self.NOW)['summary']['trophy_delta'])

    def test_old_csv_loads_without_being_renamed_or_losing_rows(self):
        from trophy_observer import TrophyObserver
        with tempfile.TemporaryDirectory() as root:
            observer=TrophyObserver.__new__(TrophyObserver);observer.history_file=Path(root)/'match_history.csv'
            columns=[c for c in TrophyObserver.HISTORY_COLUMNS if c not in {'account_tag','trophy_source'}]
            with observer.history_file.open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerow(dict(date_time='2026-10-07T10:00:00',brawler_name='shelly',result='victory',trophy_delta=8))
            before=observer.history_file.read_bytes();loaded=observer.load_history()
            self.assertEqual(len(loaded),1);self.assertEqual(loaded[0]['account_tag'],'');self.assertEqual(observer.history_file.read_bytes(),before)
