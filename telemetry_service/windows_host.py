"""Windows receiver and separate loopback-only setup UI. Secrets use user DPAPI."""
import argparse
import base64
import json
import logging
import os
from pathlib import Path
import re
import secrets
import threading

from flask import Flask, jsonify, request, render_template_string
import requests
from telemetry_service.server import create_app


class SecretStore:
    def __init__(self, home, filename='telegram.private.json'):
        self.path = Path(home)/filename
        self.lock = threading.RLock()
    def load(self):
        import win32crypt
        import pywintypes
        with self.lock:
            try:
                data = json.loads(self.path.read_text('utf-8'))
                token = win32crypt.CryptUnprotectData(base64.b64decode(data['protected_token']),None,None,None,0)[1].decode()
                return token, str(data['chat_id'])
            except (OSError, ValueError, KeyError, TypeError, pywintypes.error):
                return '', ''
    def save(self, token, chat_id):
        import win32crypt
        protected = win32crypt.CryptProtectData(token.encode(),'xlamBOT Telegram receiver',None,None,None,0)
        with self.lock:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({'protected_token':base64.b64encode(protected).decode(),
                                        'chat_id':chat_id}),encoding='utf-8')
            os.replace(temp,self.path)


PAGE = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>xlamBOT — сервер ошибок</title><style>
body{margin:0;background:#11101a;color:#eee;font:16px system-ui;display:grid;place-items:center;min-height:100vh}
main{max-width:580px;padding:32px;background:#1c192b;border:1px solid #494064;border-radius:24px;margin:20px}
input,select,button{box-sizing:border-box;width:100%;font:inherit;border-radius:12px;padding:13px;margin:8px 0;border:1px solid #494064;background:#28233b;color:#fff}
button{background:#9e7cf0;color:#171121;font-weight:700;cursor:pointer}p{line-height:1.6;color:#c4bdd8}#status{white-space:pre-wrap}label{display:block;margin-top:18px}small{color:#c4bdd8}
</style><main><h1>Сервер ошибок xlamBOT</h1><p>Приёмник запущен на этом ПК. Подключи отдельного Telegram-бота, чтобы получать ошибки пользователей.</p>
<p>Перевыпусти раскрытый токен через <b>@BotFather</b>. Новый токен введи здесь: он сохраняется зашифрованным средствами Windows и не попадёт в GitHub. Эта страница доступна только на твоём ПК.</p>
<label for="token">Новый токен Telegram-бота</label><input id="token" type="password" autocomplete="off" spellcheck="false">
<button id="discover">Найти мой Telegram</button><small>Сначала открой своего бота в Telegram и отправь /start. При нескольких чатах выбери свой.</small>
<label for="chat">Получатель уведомлений</label><select id="chat"><option value="">Сначала найди свой Telegram</option></select>
<button id="save">Сохранить подключение</button><button id="test">Отправить проверочное сообщение</button>
<p id="status" role="status">Проверяем подключение…</p>
<h2>Бесплатный постоянный адрес</h2><p>Войди в бесплатный аккаунт <a href="https://dashboard.ngrok.com/get-started/your-authtoken" target="_blank" rel="noreferrer">ngrok</a> и скопируй свой Authtoken. Это отдельный ключ, не токен Telegram.</p>
<label for="ngrokToken">ngrok Authtoken</label><input id="ngrokToken" type="password" autocomplete="off" spellcheck="false"><button id="connectNgrok">Подключить постоянный адрес</button><button id="retryNgrok">Повторить подключение</button>
<p id="ngrokStatus" role="status"></p><p>Адрес сохраняется после перезапуска. Лимиты бесплатного тарифа: 20 000 запросов и 1 ГБ в месяц. Сервер доступен, пока ПК включён, не спит и есть интернет.</p></main>
<script>
const csrf={{ csrf|tojson }};
async function call(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Setup-Token':csrf},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.message);return data;}
const token=document.getElementById('token'),chat=document.getElementById('chat'),status=document.getElementById('status');
async function action(button,callback){button.disabled=true;try{await callback();}catch(e){status.textContent=e.message;}finally{button.disabled=false;}}
document.getElementById('discover').onclick=function(){action(this,async()=>{const d=await call('/discover',{token:token.value});chat.replaceChildren();for(const c of d.chats){const o=document.createElement('option');o.value=c.id;o.textContent=c.label;chat.append(o);}status.textContent=d.chats.length?'Выбери свой чат и сохрани подключение.':'Отправь /start своему боту и нажми «Найти мой Telegram» ещё раз.';});};
document.getElementById('save').onclick=function(){action(this,async()=>{await call('/configure',{token:token.value,chat_id:chat.value});token.value='';status.textContent='Подключение сохранено. Можно отправить проверочное сообщение.';});};
document.getElementById('test').onclick=function(){action(this,async()=>{await call('/test',{});status.textContent='Проверочное сообщение отправлено в твой Telegram.';});};
call('/status',{}).then(d=>status.textContent=d.configured?'Telegram подключён. Приёмник работает.':'Приёмник работает. Осталось подключить Telegram.').catch(e=>status.textContent=e.message);
async function ngrokStatus(){try{const d=await call('/ngrok/status',{});const labels={credentials_required:'Сначала сохрани ngrok Authtoken.',connecting:'Подключаем постоянный адрес…',agent_running:'Туннель запущен.',connection_failed:'Не удалось подключиться. Проверь Authtoken и доступ к сети.'};document.getElementById('ngrokStatus').textContent=(labels[d.state]||'Туннель недоступен.')+(d.public_url?' Адрес: '+d.public_url:'');}catch(e){document.getElementById('ngrokStatus').textContent=e.message;}}
document.getElementById('connectNgrok').onclick=function(){action(this,async()=>{await call('/ngrok/configure',{token:document.getElementById('ngrokToken').value});document.getElementById('ngrokToken').value='';await ngrokStatus();});};
document.getElementById('retryNgrok').onclick=function(){action(this,async()=>{await call('/ngrok/retry',{});await ngrokStatus();});};
ngrokStatus();setInterval(ngrokStatus,5000);
</script></html>'''


def setup_app(store, session=None, connector=None):
    app = Flask('xlambot-local-setup')
    app.config['MAX_CONTENT_LENGTH'] = 4096
    csrf = secrets.token_urlsafe(32)
    session = session or requests.Session()
    def telegram(token, method, body):
        if not isinstance(token,str) or not re.fullmatch(r'[0-9]{5,16}:[A-Za-z0-9_-]{20,100}',token):
            raise ValueError('Введи новый токен из BotFather.')
        try:
            response = session.post('https://api.telegram.org/bot'+token+'/'+method,
                                    json=body,timeout=(3,10),allow_redirects=False)
            if response.status_code != 200 or response.json().get('ok') is not True:
                raise ValueError('Telegram не подтвердил подключение. Проверь токен и отправь боту /start.')
            return response.json()['result']
        except requests.RequestException:
            raise ValueError('Нет связи с Telegram. Попробуй позже.') from None
    @app.before_request
    def local_only():
        if request.remote_addr != '127.0.0.1' or request.host != '127.0.0.1:8110':
            return jsonify(message='Только локальный доступ'),403
        if request.method != 'GET' and not secrets.compare_digest(request.headers.get('X-Setup-Token',''),csrf):
            return jsonify(message='Перезагрузи страницу настройки'),403
    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        return response
    @app.get('/')
    def page():
        return render_template_string(PAGE,csrf=csrf)
    @app.post('/status')
    def status():
        token,chat=store.load()
        return jsonify(configured=bool(token and chat))
    @app.post('/ngrok/status')
    def ngrok_status():
        return jsonify(connector.status() if connector else {'state':'credentials_required'})
    @app.post('/ngrok/configure')
    def ngrok_configure():
        if connector is None:
            raise ValueError('Подключение ngrok пока недоступно.')
        payload=request.get_json(silent=True) or {}
        if not isinstance(payload,dict):
            raise ValueError('Неверные настройки')
        return jsonify(connector.configure(payload.get('token','')))
    @app.post('/ngrok/retry')
    def ngrok_retry():
        if connector is None:
            raise ValueError('Подключение ngrok пока недоступно.')
        return jsonify(connector.retry())
    @app.post('/discover')
    def discover():
        payload=request.get_json(silent=True) or {}
        if not isinstance(payload,dict):
            raise ValueError('Неверные настройки')
        token=payload.get('token','')
        telegram(token,'getMe',{})
        updates=telegram(token,'getUpdates',{'timeout':0,'limit':100,'allowed_updates':['message']})
        chats={}
        for update in updates:
            chat=update.get('message',{}).get('chat',{})
            if chat.get('type')=='private':
                chats[str(chat['id'])]=str(chat.get('first_name') or chat.get('username') or chat['id'])
        return jsonify(chats=[{'id':key,'label':value} for key,value in chats.items()])
    @app.post('/configure')
    def configure():
        payload=request.get_json(silent=True) or {}
        if not isinstance(payload,dict):
            raise ValueError('Неверные настройки')
        token,chat=payload.get('token',''),str(payload.get('chat_id',''))
        if not re.fullmatch(r'[1-9][0-9]{0,19}',chat):
            raise ValueError('Выбери свой Telegram из списка.')
        telegram(token,'getMe',{})
        result=telegram(token,'getChat',{'chat_id':chat})
        if result.get('type')!='private':
            raise ValueError('Выбери личный чат.')
        store.save(token,chat)
        return jsonify(ok=True)
    @app.post('/test')
    def test():
        token,chat=store.load()
        if not token or not chat:
            raise ValueError('Сначала сохрани подключение.')
        telegram(token,'sendMessage',{'chat_id':chat,'text':'xlamBOT: сервер ошибок на твоём ПК подключён. Проверочное сообщение.'})
        return jsonify(ok=True)
    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(message=str(error)),400
    @app.errorhandler(Exception)
    def failed(error):
        # Never print request bodies or request exception URLs with tokens.
        return jsonify(message='Не удалось выполнить действие. Проверь подключение и настройки.'),500
    return app


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',type=Path,required=True)
    args=parser.parse_args()
    args.home.mkdir(parents=True,exist_ok=True)
    from waitress import create_server
    from werkzeug.middleware.proxy_fix import ProxyFix
    store=SecretStore(args.home)
    from telemetry_service.windows_ngrok import NgrokConnector
    connector=NgrokConnector(args.home,SecretStore(args.home,'ngrok.private.json'))
    connector.start()
    app=create_app(database=args.home/'reports.sqlite',credentials_provider=store.load)
    # Only this loopback listener is exposed through the Cloudflare connector.
    app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1)
    @app.get('/health')
    def health():
        return jsonify(ok=True,service='xlambot-error-receiver')
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    receiver=create_server(app,host='127.0.0.1',port=8088,threads=4)
    setup=create_server(setup_app(store,connector=connector),host='127.0.0.1',port=8110,threads=2)
    threading.Thread(target=receiver.run,daemon=True,name='error-receiver').start()
    setup.run()


if __name__=='__main__':
    main()
