import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from error_telemetry import ErrorTelemetry, clean_event
from telemetry_service.server import create_app


class ReceiverSession:
    def __init__(self, client):
        self.client = client
        self.calls = []
    def post(self, url, json, headers=None, **kwargs):
        self.calls.append(url)
        raw = self.client.post('/'+url.split('/',3)[3], json=json, headers=headers or {})
        response = Mock(status_code=raw.status_code)
        response.json.return_value = raw.get_json()
        if raw.status_code >= 400:
            response.raise_for_status.side_effect = ValueError('request failed')
        return response


class ErrorReportsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.telegram = Mock()
        self.telegram.post.return_value.status_code = 200
        self.telegram.post.return_value.json.return_value = {'ok':True}
        self.receiver = create_app(self.root/'db.sqlite', token='FAKE_TEST_TOKEN',
                                  chat_id='TEST_CHAT', session=self.telegram, start_worker=False)
        self.session = ReceiverSession(self.receiver.test_client())
        self.reporter = ErrorTelemetry(self.root/'client', 'https://receiver.example', '0.8.20', 72, self.session)
    def tearDown(self):
        self.temp.cleanup()
    def enabled(self):
        self.reporter.configure(True, 'warning')

    def test_sanitized_durable_delivery_and_grouping(self):
        self.enabled()
        try:
            raise RuntimeError('SECRET PASSWORD /Users/private/account')
        except RuntimeError as error:
            self.reporter.report('runtime_crash','critical',error,'adb-private-account','runtime')
        self.assertTrue(self.reporter.send_once())
        self.reporter._save()
        exported = json.dumps(self.reporter.export())
        self.assertNotIn('SECRET', exported)
        self.assertNotIn('private', exported)
        self.assertTrue(self.receiver.extensions['deliver_once']())
        self.assertFalse(self.receiver.extensions['deliver_once']())
        self.assertNotIn('SECRET', self.telegram.post.call_args.kwargs['json']['text'])
        reloaded = ErrorTelemetry(self.root/'client', 'https://receiver.example', session=self.session)
        self.assertEqual(reloaded.status()['pending'], 0)
        self.assertEqual(len(reloaded.entries), 1)

    def test_opt_out_never_replays_inbox_or_disabled_repeats(self):
        self.enabled()
        self.reporter.report('runtime_crash')
        self.reporter.configure(False,'error')
        self.reporter.report('runtime_crash')
        self.reporter.configure(True,'error')
        self.assertFalse(self.reporter.send_once())
        self.assertEqual(self.session.calls, [])
        self.reporter.report('runtime_crash')
        self.assertTrue(self.reporter.send_once())
        sent = list(self.reporter.entries.values())[-1]
        self.assertEqual(sent['count'],1)

    def test_owner_thread_no_io_and_bounded_inbox(self):
        self.enabled()
        with patch('builtins.open',side_effect=AssertionError('disk on game thread')):
            for _ in range(300):
                self.reporter.report('gas_detector_failed')
        self.assertEqual(self.session.calls,[])
        self.assertEqual(self.reporter.inbox.qsize(),256)
        self.assertEqual(self.reporter.dropped,44)
        self.reporter.drain()
        self.assertEqual(len(self.reporter.entries),1)

    def test_warning_threshold_info_local_and_retry_backoff(self):
        self.enabled()
        self.reporter.report('gpu_fallback','warning')
        self.assertFalse(self.reporter.send_once())
        self.reporter.report('gpu_fallback','warning')
        self.reporter.report('gpu_fallback','warning')
        self.assertTrue(self.reporter.send_once())
        self.reporter.report('manual_report','info')
        self.assertFalse(self.reporter.send_once())
        self.reporter.report('runtime_crash')
        self.reporter.session = Mock()
        self.reporter.session.post.side_effect = OSError('offline')
        self.assertFalse(self.reporter.send_once())
        self.assertFalse(self.reporter.send_once())
        self.assertEqual(self.reporter.session.post.call_count,1)
        self.reporter._save()
        reloaded = ErrorTelemetry(self.root/'client', 'https://receiver.example', session=self.session)
        self.assertEqual(reloaded.status()['pending'],1)

    def test_receiver_auth_idempotency_and_untrusted_fields(self):
        client = self.receiver.test_client()
        self.enabled()
        self.reporter.report('runtime_crash')
        self.reporter.drain()
        item=clean_event(next(iter(self.reporter.entries.values())))
        self.assertEqual(client.post('/v1/events',json=item).status_code,401)
        registration=client.post('/v1/register',json={}).get_json()
        item['installation']=registration['installation']
        item['message']='secret'
        item['fingerprint']='forged'
        headers={'Authorization':'Bearer '+registration['token']}
        self.assertEqual(client.post('/v1/events',json=item,headers=headers).status_code,202)
        self.assertEqual(client.post('/v1/events',json=item,headers=headers).status_code,202)
        self.assertTrue(self.receiver.extensions['deliver_once']())
        text=self.telegram.post.call_args.kwargs['json']['text']
        self.assertIn('Reports: 1',text)
        self.assertNotIn('secret',text)
        item['installation']='0'*32
        self.assertEqual(client.post('/v1/events',json=item,headers=headers).status_code,401)

    def test_disable_during_registration_does_not_send_event(self):
        self.enabled()
        self.reporter.report('runtime_crash')
        original=self.session.post
        def post(*args,**kwargs):
            response=original(*args,**kwargs)
            self.reporter.configure(False,'error')
            return response
        self.session.post=post
        self.assertFalse(self.reporter.send_once())
        self.assertEqual(len(self.session.calls),1)

    def test_new_occurrence_during_delivery_is_not_acknowledged(self):
        self.enabled()
        self.reporter.report('runtime_crash')
        original=self.session.post
        def post(url,**kwargs):
            if url.endswith('/events'):
                self.reporter.report('runtime_crash')
                self.reporter.drain()
            return original(url,**kwargs)
        self.session.post=post
        self.assertTrue(self.reporter.send_once())
        event=next(iter(self.reporter.entries.values()))
        self.assertEqual(event['count'],2)
        self.assertEqual(event['_sent_count'],1)
        self.assertFalse(self.reporter.send_once())
        self.assertEqual(self.reporter.status()['pending'],1)

    def test_opt_out_is_durable_before_ui_acknowledgement(self):
        self.enabled()
        self.reporter.report('runtime_crash')
        self.reporter.drain()
        self.reporter._save()
        self.reporter.configure(False,'error')
        reloaded=ErrorTelemetry(self.root/'client', 'https://receiver.example', session=self.session)
        self.assertFalse(reloaded.enabled)
        self.assertEqual(reloaded.status()['pending'],0)

    def test_redirect_is_not_success_and_no_exception_source_is_loaded(self):
        self.enabled()
        self.reporter.credentials={'installation':'0'*32,'token':'a'*64}
        response=Mock(status_code=302)
        response.json.return_value={'accepted':'anything'}
        self.reporter.session=Mock()
        self.reporter.session.post.return_value=response
        try:
            raise ValueError('secret')
        except ValueError as error:
            with patch('builtins.open',side_effect=AssertionError('source read')):
                self.reporter.report('runtime_crash',error=error)
        self.assertFalse(self.reporter.send_once())
        self.assertEqual(self.reporter.status()['pending'],1)
        self.assertFalse(self.reporter.session.post.call_args.kwargs['allow_redirects'])
