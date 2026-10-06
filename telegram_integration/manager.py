"""Optional bot-manager service. Deploy behind HTTPS; never bundle its token."""
from __future__ import annotations

import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse

from .store import Store, protect
from .transport import APIError, TelegramAPI


class SessionError(ValueError):
    pass


class Sessions:
    def __init__(self, path, manager_username, clock=time.time, allowed_users=None):
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", manager_username):
            raise SessionError("Invalid manager username")
        self.username, self.clock, self.allowed_users = manager_username, clock, allowed_users
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        if str(path) != ":memory:" and os.name != "nt":
            Path(path).chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, claim_hash TEXT, expires REAL, username TEXT, owner INTEGER, bot_id INTEGER, token BLOB)")
        self.db.commit()

    def purge(self):
        self.db.execute("DELETE FROM sessions WHERE expires <= ?", (self.clock(),))
        self.db.commit()

    def create(self):
        with self.lock:
            self.purge()
            if self.db.execute("SELECT count(*) FROM sessions").fetchone()[0] >= 100:
                raise SessionError("Session capacity reached")
            session, secret = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
            username = "xlam_" + secrets.token_hex(8) + "_bot"
            self.db.execute("INSERT INTO sessions (id,claim_hash,expires,username) VALUES (?,?,?,?)",
                            (session, hashlib.sha256(secret.encode()).hexdigest(), self.clock() + 600, username))
            self.db.commit()
            # /start authenticates the Telegram owner before opening the creation dialog.
            return {"session": session, "claim_secret": secret, "expires_in": 600,
                    "url": f"https://t.me/{self.username}?start=connect_{session}"}

    def link(self, session, owner):
        with self.lock:
            self.purge()
            if self.allowed_users is not None and owner not in self.allowed_users:
                raise SessionError("Owner is not allowed")
            row = self.db.execute("SELECT * FROM sessions WHERE id=?", (session,)).fetchone()
            if row is None or row["owner"] not in (None, owner) or row["token"] is not None:
                raise SessionError("Invalid session")
            # One outstanding creation per owner avoids ambiguous edited usernames.
            other = self.db.execute("SELECT id FROM sessions WHERE owner=? AND id<>?", (owner, session)).fetchone()
            if other:
                raise SessionError("Another setup is pending; finish it or wait for expiry")
            self.db.execute("UPDATE sessions SET owner=? WHERE id=?", (owner, session))
            self.db.commit()
            return f"https://t.me/newbot/{self.username}/{row['username']}?" + urllib.parse.urlencode({"name": "xlamBOT"})

    def attach(self, owner, bot_id, token):
        with self.lock:
            self.purge()
            row = self.db.execute("SELECT * FROM sessions WHERE owner=? AND token IS NULL", (owner,)).fetchone()
            if row is None:
                return False
            self.db.execute("UPDATE sessions SET bot_id=?,token=? WHERE id=?", (bot_id, protect(token.encode()), row["id"]))
            self.db.commit()
            return True

    def claim(self, session, secret):
        with self.lock:
            self.purge()
            row = self.db.execute("SELECT * FROM sessions WHERE id=?", (session,)).fetchone()
            if row is None or not hmac.compare_digest(row["claim_hash"], hashlib.sha256(secret.encode()).hexdigest()):
                raise SessionError("Invalid or expired session")
            if row["token"] is None:
                return {"ready": False}
            token = protect(row["token"], decrypt=True).decode()
            result = {"ready": True, "token": token, "owner_id": row["owner"], "bot_id": row["bot_id"]}
            self.db.execute("DELETE FROM sessions WHERE id=?", (session,))
            self.db.commit()
            return result


class Management:
    def __init__(self, sessions, api, store, stop):
        self.sessions, self.api, self.store, self.stop = sessions, api, store, stop

    def handle(self, update):
        managed = update.get("managed_bot")
        if managed:
            owner, bot_id = managed["user"]["id"], managed["bot"]["id"]
            # Do not request tokens for bots unrelated to a pending authenticated setup.
            with self.sessions.lock:
                row = self.sessions.db.execute("SELECT id FROM sessions WHERE owner=? AND token IS NULL AND expires>?",
                                               (owner, self.sessions.clock())).fetchone()
            if row:
                token = self.api.call("getManagedBotToken", user_id=bot_id)
                self.sessions.attach(owner, bot_id, token)
            return
        message = update.get("message", {})
        text = message.get("text", "")
        user, chat = message.get("from", {}).get("id"), message.get("chat", {})
        if chat.get("type") == "private" and chat.get("id") == user and text == "/id":
            self.api.call("sendMessage", chat_id=user, text=f"Telegram ID: {user}")
            return
        if chat.get("type") != "private" or chat.get("id") != user or not text.startswith("/start connect_"):
            return
        try:
            url = self.sessions.link(text.removeprefix("/start connect_"), user)
        except SessionError:
            self.api.call("sendMessage", chat_id=user, text="Setup expired or unavailable / Настройка недоступна или истекла")
            return
        self.api.call("sendMessage", chat_id=user, text="Create your xlamBOT bot / Создайте бота xlamBOT",
                      reply_markup={"inline_keyboard": [[{"text": "🟢 Создать / Create", "style": "success", "url": url}]]})

    def run(self):
        delay = 1
        while not self.stop.is_set():
            try:
                updates = self.api.call("getUpdates", offset=self.store.snapshot()["offset"], timeout=20,
                                        allowed_updates=["message", "managed_bot"])
                for update in updates:
                    self.handle(update)
                    self.store.update(offset=update["update_id"] + 1)
                delay = 1
            except APIError as error:
                if error.code in (401, 409):
                    self.stop.set()
                    return
                delay = min(delay * 2, 60)
                self.stop.wait(max(delay, error.retry_after))
            except (ValueError, KeyError):
                self.stop.wait(2)


def handler_for(sessions):
    class Handler(BaseHTTPRequestHandler):
        buckets = {}
        bucket_lock = threading.Lock()

        def log_message(self, format, *args):
            pass  # No tokens, session capabilities or request bodies in access logs.

        def do_POST(self):
            self.connection.settimeout(5)
            code, result = 200, {}
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 <= size <= 16384:
                    raise SessionError("Invalid request size")
                payload = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(payload, dict):
                    raise SessionError("Invalid request")
                if self.path == "/v1/sessions":
                    with self.bucket_lock:
                        now = sessions.clock()
                        type(self).buckets = {key: values for key, values in self.buckets.items() if values[-1] > now - 60}
                        entries = [at for at in self.buckets.get(self.client_address[0], []) if now - at < 60]
                        if len(entries) >= 10:
                            raise SessionError("Rate limited")
                        entries.append(now)
                        type(self).buckets[self.client_address[0]] = entries
                    result = sessions.create()
                elif self.path == "/v1/claim":
                    result = sessions.claim(str(payload.get("session", "")), str(payload.get("claim_secret", "")))
                else:
                    code, result = 404, {"error": "Not found"}
            except (ValueError, OSError):
                code, result = 400, {"error": "Invalid, expired or rate-limited request"}
            body = json.dumps(result).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8789)
    parser.add_argument("--allowed-user", type=int, action="append")
    args = parser.parse_args()
    token = os.environ.get("XLAMBOT_MANAGER_TOKEN", "")
    api = TelegramAPI(token)
    bot = api.validate()
    store = Store(args.directory)
    sessions = Sessions(args.directory / "sessions.sqlite", bot["username"],
                        allowed_users=set(args.allowed_user) if args.allowed_user else None)
    stop = threading.Event()
    management = Management(sessions, api, store, stop)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(sessions))
    threading.Thread(target=management.run, daemon=True).start()
    # Timed handle_request also stops the HTTP listener after fatal polling errors.
    server.timeout = 1
    try:
        while not stop.is_set():
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
