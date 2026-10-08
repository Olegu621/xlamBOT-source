"""Persistent free-account connector. Its credential is never written in plaintext."""
import atexit
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

import requests


def ngrok_token(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,512}',value):
        raise ValueError('Вставь Authtoken из своего аккаунта ngrok.')
    return value


class NgrokConnector:
    def __init__(self, home, store):
        self.home=Path(home)
        self.store=store
        self.lock=threading.RLock()
        self.closed=threading.Event()
        self.changed=threading.Event()
        self.state='credentials_required'
        self.url=''
        self.generation=0
        self.process=None
        self.attempts=0
        self.retry_at=0
        self.thread=None
        atexit.register(self.close)
    def status(self):
        with self.lock:
            return {'state':self.state,'public_url':self.url,'configured':self.store.path.is_file(),
                    'temporary':False,'request_limit_monthly':20000}
    def _save_status(self):
        # This file contains only public URL/state, never a credential or log text.
        with self.lock:
            target=self.home/'ngrok-status.json'
            temporary=target.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.status()),encoding='utf-8')
            os.replace(temporary,target)
    def configure(self, token):
        token=ngrok_token(token)
        self.store.save(token,'ngrok')
        return self.retry()
    def retry(self):
        with self.lock:
            self.generation+=1
            self.attempts=0
            self.retry_at=0
            self.state='connecting'
            self.url=''
        self.changed.set()
        return self.status()
    def start(self):
        self.thread=threading.Thread(target=self._loop,daemon=True,name='ngrok-connector')
        self.thread.start()
    def _stop_process(self):
        process=self.process
        self.process=None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
    def _launch(self):
        token,_=self.store.load()
        if not token:
            self.state='credentials_required'
            return
        token=ngrok_token(token)
        # Config file includes no secrets. Disable HTTP payload inspection and
        # remote process management; the agent API is loopback only.
        config=self.home/'ngrok-agent.yml'
        config.write_text('version: "3"\nagent:\n  web_addr: 127.0.0.1:4041\n'
                          '  remote_management: false\n  update_check: false\n',encoding='utf-8')
        environment=dict(os.environ,NGROK_AUTHTOKEN=token)
        self.process=subprocess.Popen([str(self.home/'ngrok.exe'),'http','http://127.0.0.1:8088',
                    '--config',str(config),'--inspect=false','--log=false'],
                    env=environment,creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.attempts+=1
        self.state='connecting'
        self.retry_at=time.monotonic()+45
    def _loop(self):
        applied=-1
        while not self.closed.is_set():
            try:
                with self.lock:
                    if applied!=self.generation:
                        self._stop_process()
                        applied=self.generation
                        self._launch()
                    elif self.process and self.process.poll() is not None:
                        self._stop_process()
                        self.url=''
                        self.state='connection_failed'
                        self.retry_at=time.monotonic()+30*self.attempts
                    elif self.process:
                        try:
                            response=requests.get('http://127.0.0.1:4041/api/tunnels',timeout=1)
                            tunnels=response.json().get('tunnels',[])
                            urls=[t.get('public_url','') for t in tunnels if t.get('proto')=='https']
                            valid=[url for url in urls if re.fullmatch(r'https://[a-z0-9-]+\.ngrok-free\.(app|dev)',url)]
                            if valid:
                                self.url=valid[0]
                                self.state='agent_running'
                        except (requests.RequestException,ValueError,TypeError):
                            pass
                        if self.state=='connecting' and time.monotonic()>self.retry_at:
                            self._stop_process()
                            self.state='connection_failed'
                            self.retry_at=time.monotonic()+30*self.attempts
                    elif self.state=='connection_failed' and self.attempts<3 and time.monotonic()>=self.retry_at:
                        self._launch()
                    self._save_status()
            except Exception:
                with self.lock:
                    self._stop_process()
                    self.state='connection_failed'
                    self.attempts=3
                    self.url=''
                    self._save_status()
            self.changed.wait(3)
            self.changed.clear()
    def close(self):
        self.closed.set()
        self.changed.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=5)
        with self.lock:
            self._stop_process()
