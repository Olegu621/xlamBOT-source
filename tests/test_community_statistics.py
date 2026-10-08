import csv
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock

from community_statistics import CommunityStatistics


class CommunityStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.session = Mock()
        self.sent = []
        def post(url, json, **kwargs):
            self.sent.append((url,json,kwargs))
            value = {'installation':'a'*32,'token':'b'*64} if url.endswith('/register') else {'accepted':[m['id'] for m in json['matches']]}
            return Mock(status_code=200 if url.endswith('/register') else 202, json=lambda:value)
        self.session.post.side_effect = post
        self.provider = Mock(return_value=[{'key':'PRIVATE-ADB-SERIAL','state':'running','is_running':True}])
        self.service = CommunityStatistics(self.root/'stats', self.root, self.provider, revision=76, session=self.session)
    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()
    def history(self, rows):
        path = self.root/'cfg/match_history.csv'
        path.parent.mkdir(exist_ok=True)
        with path.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f, fieldnames=['date_time','result','trophy_delta','trophy_source','account_tag','brawler_name'])
            writer.writeheader();writer.writerows(rows)
    def row(self, **overrides):
        from datetime import datetime
        return dict({'date_time':datetime.now().isoformat(),'result':'victory','trophy_delta':'10','trophy_source':'estimated','account_tag':'PRIVATE-ACCOUNT','brawler_name':'PRIVATE-BRAWLER'}, **overrides)
    def test_disabled_never_reads_profiles_or_uses_network(self):
        self.service.sync()
        self.provider.assert_not_called();self.session.post.assert_not_called()
    def test_payload_privacy_acknowledgement_and_persistence(self):
        self.history([self.row()]);self.service.configure(True);self.service.sync()
        payload=self.sent[-1][1];encoded=json.dumps(payload)
        self.assertNotIn('PRIVATE',encoded)
        self.assertEqual(payload['matches'][0]['source'],'estimated')
        self.assertTrue(payload['devices'][0]['active'])
        self.assertEqual(self.service.status()['sent_matches'],1)
        reloaded=CommunityStatistics(self.root/'stats',self.root,self.provider,session=self.session)
        reloaded.sync();self.assertEqual(self.sent[-1][1]['matches'],[])
        self.assertNotIn('token',self.service.status())
    def test_unacknowledged_batches_are_retried_with_identical_ids(self):
        self.history([self.row()]);self.service.configure(True);self.service.sync()
        self.service.cursors={}
        payload=self.sent[-1][1]['matches']
        self.session.post.return_value=Mock(status_code=503)
        self.session.post.side_effect=lambda *a,**kw:Mock(status_code=503)
        with self.assertRaises(ValueError):self.service.sync()
        self.assertEqual(self.service.cursors,{})
        self.assertEqual(self.service.history_batch()[0],payload)
    def test_batch_limit_corrupt_values_unknown_trophies_and_truncation(self):
        rows=[self.row() for _ in range(51)]
        self.history(rows);batch,cursors=self.service.history_batch();self.assertEqual(len(batch),50)
        self.assertEqual(len({r['id'] for r in batch}),50)
        self.service.cursors=cursors;self.assertEqual(len(self.service.history_batch()[0]),1)
        self.history(rows[:1]);self.service.cursors=self.service.history_batch()[1]
        again,_=self.service.history_batch();self.assertEqual(again[0]['id'],batch[0]['id'])
        self.service.cursors={}
        self.history([self.row(trophy_delta='nan'),self.row(trophy_delta='5',trophy_source='legacy')])
        batch,_=self.service.history_batch();self.assertEqual(len(batch),1);self.assertIsNone(batch[0]['delta'])
    def test_pause_and_opt_out_clear_presence_without_uploading_history(self):
        self.service.configure(True);self.service.sync()
        self.provider.return_value=[{'key':'PRIVATE','is_running':True,'state':'paused'}]
        self.service.sync();self.assertFalse(self.sent[-1][1]['devices'][0]['active'])
        self.service.configure(False);self.service.sync()
        self.assertEqual(self.sent[-1][1],{'devices':[],'matches':[]})
        before=len(self.sent);self.service.sync();self.assertEqual(len(self.sent),before)
    def test_disabling_during_registration_cancels_upload(self):
        def post(url,**kwargs):
            self.service.configure(False)
            return Mock(status_code=200,json=lambda:{'installation':'a'*32,'token':'b'*64})
        self.session.post.side_effect=post;self.service.configure(True);self.service.sync()
        self.assertEqual(self.session.post.call_count,1)

if __name__=='__main__':unittest.main()
