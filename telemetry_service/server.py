"""Single-process HTTPS-proxied receiver with a durable Telegram outbox."""
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

from flask import Flask, jsonify, request
import requests
from error_telemetry import clean_event


def create_app(database=None, token=None, chat_id=None, session=None, start_worker=True):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 32768
    database = str(database or os.environ.get('TELEMETRY_DATABASE', 'telemetry-state/reports.sqlite'))
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    token = token or os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID', '')
    session = session or requests.Session()
    lock = threading.RLock()
    @contextmanager
    def connect():
        conn = sqlite3.connect(database, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()
    with connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS installations(id TEXT PRIMARY KEY, token TEXT UNIQUE, created REAL);
            CREATE TABLE IF NOT EXISTS rate(key TEXT PRIMARY KEY, bucket INTEGER, count INTEGER);
            CREATE TABLE IF NOT EXISTS events(installation TEXT, id TEXT, fingerprint TEXT,
                count INTEGER, level TEXT, code TEXT, version TEXT, revision INTEGER,
                exception TEXT, stage TEXT, trace TEXT, seen REAL, PRIMARY KEY(installation,id));
            CREATE TABLE IF NOT EXISTS groups(fingerprint TEXT PRIMARY KEY, notified INTEGER DEFAULT 0,
                last_sent REAL DEFAULT 0, retry_at REAL DEFAULT 0, failures INTEGER DEFAULT 0);
        ''')
    def rate(db, key, limit, seconds=3600):
        bucket = int(time.time() // seconds)
        db.execute('INSERT INTO rate VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET '
                   'count=CASE WHEN bucket=excluded.bucket THEN count+1 ELSE 1 END,bucket=excluded.bucket', (key,bucket))
        return db.execute('SELECT count FROM rate WHERE key=?', (key,)).fetchone()[0] <= limit

    @app.post('/v1/register')
    def register():
        # No IP addresses are stored. Reverse proxies must supply a trusted remote address.
        ip = hashlib.sha256((request.remote_addr or '').encode()).hexdigest()
        with lock, connect() as db:
            db.execute('DELETE FROM rate WHERE bucket < ?', (int(time.time()//3600)-48,))
            if not rate(db, 'register:'+ip, 20) or not rate(db, 'register:global', 1000):
                return jsonify(error='rate_limited'), 429
            if db.execute('SELECT COUNT(*) FROM installations').fetchone()[0] >= 100000:
                return jsonify(error='capacity'), 503
            installation, credential = uuid.uuid4().hex, secrets.token_hex(32)
            db.execute('INSERT INTO installations VALUES(?,?,?)',
                       (installation, hashlib.sha256(credential.encode()).hexdigest(), time.time()))
        return jsonify(installation=installation, token=credential)

    @app.post('/v1/events')
    def event():
        authorization = request.headers.get('Authorization', '')
        if not authorization.startswith('Bearer ') or len(authorization) != 71:
            return jsonify(error='unauthorized'), 401
        try:
            item = clean_event(request.get_json(silent=True))
        except (ValueError, TypeError, KeyError, OverflowError):
            return jsonify(error='invalid_report'), 400
        if item['level'] == 'info' or (item['level'] == 'warning' and item['count'] < 3):
            return jsonify(error='invalid_level'), 400
        now = time.time()
        if item['last_seen'] < item['first_seen'] or item['last_seen'] > now+86400:
            return jsonify(error='invalid_time'), 400
        credential = hashlib.sha256(authorization[7:].encode()).hexdigest()
        with lock, connect() as db:
            owner = db.execute('SELECT id FROM installations WHERE token=?', (credential,)).fetchone()
            if not owner or owner['id'] != item['installation']:
                return jsonify(error='unauthorized'), 401
            if not rate(db, 'events:'+owner['id'], 120, 60):
                return jsonify(error='rate_limited'), 429
            old = db.execute('SELECT * FROM events WHERE installation=? AND id=?',
                             (owner['id'], item['id'])).fetchone()
            if old and old['fingerprint'] != item['fingerprint']:
                return jsonify(error='conflicting_report'), 409
            # Counts are cumulative, capped server-side to prevent counter inflation.
            count = min(item['count'], 1000000)
            if not old:
                if db.execute('SELECT COUNT(*) FROM events WHERE installation=?', (owner['id'],)).fetchone()[0] >= 1000:
                    return jsonify(error='capacity'), 429
                if db.execute('SELECT COUNT(*) FROM events').fetchone()[0] >= 100000:
                    return jsonify(error='capacity'), 503
                trace = '\n'.join(f"{f['module']}.{f['function']}:{f['line']}" for f in item['trace'])
                db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (owner['id'],item['id'],item['fingerprint'],count,item['level'],item['code'],
                     item['app_version'],item['revision'],item['exception_type'],item['stage'],trace,now))
            else:
                db.execute('UPDATE events SET count=MAX(count,?), seen=? WHERE installation=? AND id=?',
                           (count,now,owner['id'],item['id']))
            db.execute('INSERT OR IGNORE INTO groups(fingerprint) VALUES(?)', (item['fingerprint'],))
        return jsonify(accepted=item['id']), 202

    def deliver_once():
        if not token or not chat_id:
            return False
        now = time.time()
        with lock, connect() as db:
            # Global limit and grouped ten-minute cooldown prevent Telegram floods.
            last = db.execute('SELECT MAX(last_sent) FROM groups').fetchone()[0] or 0
            if now-last < 2:
                return False
            row = db.execute('''SELECT g.*,SUM(e.count) total,COUNT(DISTINCT e.installation) users
                FROM groups g JOIN events e USING(fingerprint)
                WHERE g.retry_at<=? AND (g.last_sent=0 OR g.last_sent<=?)
                GROUP BY g.fingerprint HAVING SUM(e.count)>g.notified
                ORDER BY MAX(CASE e.level WHEN 'critical' THEN 3 WHEN 'error' THEN 2 ELSE 1 END) DESC LIMIT 1''',
                (now,now-600)).fetchone()
            if not row:
                return False
            example = db.execute('SELECT * FROM events WHERE fingerprint=? LIMIT 1', (row['fingerprint'],)).fetchone()
        message = (f"xlamBOT · {example['level'].upper()}\n{example['code']} · {example['stage']}\n"
                   f"Version {example['version']} / r{example['revision']}\n"
                   f"Reports: {row['total']} · installations: {row['users']}\n"
                   f"{example['exception']}\n{example['trace']}")[:4000]
        try:
            response = session.post('https://api.telegram.org/bot'+token+'/sendMessage',
                json={'chat_id':chat_id,'text':message,'link_preview_options':{'is_disabled':True}},
                timeout=(3,10),allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200 or response.json().get('ok') is not True:
                raise ValueError('Telegram refused report')
        except Exception:
            with lock, connect() as db:
                failures = min(row['failures']+1,10)
                db.execute('UPDATE groups SET failures=?,retry_at=? WHERE fingerprint=?',
                           (failures,now+min(3600,5*2**failures),row['fingerprint']))
            return False
        with lock, connect() as db:
            db.execute('UPDATE groups SET notified=?,last_sent=?,failures=0,retry_at=0 WHERE fingerprint=?',
                       (row['total'],now,row['fingerprint']))
        return True

    app.extensions['deliver_once'] = deliver_once
    app.extensions['telemetry_stop'] = threading.Event()
    def work():
        while not app.extensions['telemetry_stop'].wait(2):
            try:
                deliver_once()
            except Exception:
                # No request URLs or Telegram credentials in diagnostic output.
                pass
    if start_worker:
        threading.Thread(target=work,daemon=True,name='telegram-error-outbox').start()
    return app
