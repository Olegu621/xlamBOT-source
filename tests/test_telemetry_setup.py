import re
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from telemetry_service.windows_host import setup_app, SecretStore


class WindowsSetupTest(unittest.TestCase):
    def test_missing_secret_file_does_not_break_first_run(self):
        # pywin32 exposes errors through pywintypes, not win32crypt.error.
        class CryptoError(Exception):
            pass
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict('sys.modules',{'win32crypt':types.SimpleNamespace(),
                                         'pywintypes':types.SimpleNamespace(error=CryptoError)}):
                self.assertEqual(SecretStore(folder).load(),('', ''))

    def setUp(self):
        self.store=Mock()
        self.store.load.return_value=('', '')
        self.session=Mock()
        self.response=self.session.post.return_value
        self.response.status_code=200
        self.response.json.return_value={'ok':True,'result':{'id':123,'type':'private'}}
        self.app=setup_app(self.store,self.session)
        self.client=self.app.test_client()
        self.base='http://127.0.0.1:8110'
        page=self.client.get('/',base_url=self.base).text
        self.csrf=re.search(r'const csrf="([^"]+)"',page)[1]
        self.headers={'X-Setup-Token':self.csrf}
    def test_local_setup_rejects_rebinding_and_missing_csrf(self):
        self.assertEqual(self.client.get('/',base_url='http://attacker.example:8110').status_code,403)
        self.assertEqual(self.client.post('/configure',base_url=self.base,json={}).status_code,403)
        self.assertEqual(self.client.post('/status',base_url=self.base,json={},headers=self.headers).json,{'configured':False})
        self.session.post.assert_not_called()
    def test_configuration_validates_private_recipient_and_never_echoes_token(self):
        token='123456789:'+('a'*35)
        response=self.client.post('/configure',base_url=self.base,json={'token':token,'chat_id':'123'},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertNotIn(token,response.text)
        self.store.save.assert_called_once_with(token,'123')
        self.assertTrue(all(call.kwargs['allow_redirects'] is False for call in self.session.post.call_args_list))
    def test_test_message_requires_saved_credentials_and_user_action(self):
        self.assertEqual(self.client.post('/test',base_url=self.base,json={},headers=self.headers).status_code,400)
        self.session.post.assert_not_called()
        self.store.load.return_value=('123456789:'+('a'*35),'123')
        self.response.json.return_value={'ok':True,'result':{}}
        self.assertEqual(self.client.post('/test',base_url=self.base,json={},headers=self.headers).status_code,200)
        self.assertTrue(self.session.post.call_args.args[0].endswith('/sendMessage'))
    def test_network_failure_does_not_expose_credential_url(self):
        import requests
        self.session.post.side_effect=requests.RequestException('URL https://secret-token')
        response=self.client.post('/configure',base_url=self.base,json={'token':'123456789:'+('a'*35),'chat_id':'123'},headers=self.headers)
        self.assertEqual(response.status_code,400)
        self.assertNotIn('secret-token',response.text)
