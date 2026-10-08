import base64
from flask import Flask, request
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from telegram_control import TelegramControl, SecureSocket, permitted, protect


class TelegramControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Flask(__name__)
        self.app.config['UI_API_TOKEN'] = 'LOCAL_PRIVATE_TOKEN'
        self.starts = []
        @self.app.post('/api/devices/<key>/start')
        def start(key):
            self.assertEqual(request.headers['X-Xlam-UI-Token'], 'LOCAL_PRIVATE_TOKEN')
            self.assertTrue(request.environ['xlambot.remote'])
            self.starts.append(key)
            return {'ok':True}
        @self.app.get('/panel')
        def panel():
            return '<html><head></head><body><meta name="xlam-ui-token" content="LOCAL_PRIVATE_TOKEN"><a href="/training">Training</a></body></html>'
        self.control = TelegramControl(self.app, self.temp.name)
        self.control.credentials = {'installation':'a'*32,'token':'b'*64}
    def tearDown(self):
        self.control.close(); self.temp.cleanup()
    def call(self, **values):
        return {'method':'POST','path':'/api/devices/device-one/start','body':{},'deadline':time.time()+15,**values}

    def test_expired_disabled_and_forbidden_requests_never_reach_control_handlers(self):
        self.assertEqual(self.control.dispatch(self.call())[0],409)
        self.control.enabled = True
        for deadline in [time.time()-1, time.time()+90, None, float('nan')]:
            self.assertEqual(self.control.dispatch(self.call(deadline=deadline))[0],409)
        for path in ['/api/shutdown','/api/telegram-control','https://localhost/api/devices/d/start','/api/settings/config','/api/devices/d/%2e%2e/start']:
            self.assertEqual(self.control.dispatch(self.call(path=path))[0],403)
        self.assertEqual(self.starts,[])
        self.assertEqual(self.control.dispatch(self.call())[0],200)
        self.assertEqual(self.starts,['device-one'])

    def test_remote_html_never_exposes_local_token_and_scopes_links_to_its_pc(self):
        self.control.enabled = True
        status, data, content, _ = self.control.dispatch(self.call(method='GET',path='/panel',body=None))
        self.assertEqual(status,200); self.assertIn('text/html',content)
        self.assertNotIn(b'LOCAL_PRIVATE_TOKEN',data)
        self.assertIn(('/pc/'+'a'*32+'/training').encode(),data)
        self.assertIn(b'telegram-remote.js',data)

    def test_dpapi_credentials_and_disabled_preference_survive_reload_without_plaintext(self):
        self.control._save()
        encrypted = (Path(self.temp.name)/'connection.dpapi').read_bytes()
        self.assertNotIn(('b'*64).encode(),encrypted)
        self.assertEqual(json.loads(protect(encrypted,True))['token'],'b'*64)
        reloaded = TelegramControl(self.app,self.temp.name)
        self.assertFalse(reloaded.enabled)
        self.assertEqual(reloaded.credentials['token'],'b'*64)

    def test_remote_settings_allow_only_existing_card_controls(self):
        path = '/api/devices/device-one/settings'
        self.assertTrue(permitted('POST',path,{'section':'cfg/general_config.toml','values':{'thinking_mode':'standard'}}))
        self.assertTrue(permitted('POST',path,{'section':'cfg/bot_config.toml','values':{'work_mode':3}}))
        for body in [{'section':'cfg/general_config.toml','values':{'discord_bot_token':'secret'}},
                     {'section':'cfg/bot_config.toml','values':{'work_mode':3,'avoid_gas':False}},
                     {'section':'../cfg/bot_config.toml','values':{'work_mode':3}},
                     {'section':'cfg/bot_config.toml','values':[]},None]:
            self.assertFalse(permitted('POST',path,body))

    def test_socket_handles_fragmented_json_and_ping_and_masks_client_frames(self):
        client, server = socket.socketpair(); self.addCleanup(client.close); self.addCleanup(server.close)
        connection = SecureSocket.__new__(SecureSocket); connection.socket=client; connection.stopped=threading.Event(); connection.buffer=bytearray()
        server.sendall(b'\x01\x04{"x"'+b'\x89\x01p'+b'\x80\x03:1}')
        self.assertEqual(connection.receive(),{'x':1})
        raw=server.recv(100);self.assertEqual(raw[0],138);self.assertTrue(raw[1]&128)
        self.assertEqual(bytes([raw[6]^raw[2]]),b'p')
        connection.send({'hello':'world'})
        raw=server.recv(100);self.assertEqual(raw[0],129);mask=raw[2:6]
        self.assertEqual(json.loads(bytes(v^mask[i%4] for i,v in enumerate(raw[6:]))),{'hello':'world'})
        server.sendall(b'\x81\x7f'+struct.pack('!Q',4*1024*1024))
        with self.assertRaises(OSError):connection.receive()
