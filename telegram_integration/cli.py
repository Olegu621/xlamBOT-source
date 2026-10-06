"""Console-only onboarding and standalone connection to an existing panel."""
import argparse
import getpass
import os
from pathlib import Path
import sys
import time
import webbrowser

from .bridge import LocalBridge
from .client import ManagerClient, SessionError
from .i18n import tr
from .service import Service
from .store import Store
from .transport import APIError, TelegramAPI


class SingleInstance:
    def __init__(self, path):
        self.path, self.file = path, None

    def acquire(self):
        try:
            self.file = open(self.path, "a+b")
            self.file.seek(0)
            if not self.file.read(1):
                self.file.write(b"1")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.close()
            raise RuntimeError("Telegram is already running / Telegram уже запущен") from None

    def close(self):
        if self.file:
            self.file.close()
            self.file = None


def configure_console(store, force=False, interactive=None, input_fn=input,
                      secret_fn=getpass.getpass, output=print, open_url=webbrowser.open,
                      api_factory=TelegramAPI, manager_url=None, clock=time.time, sleep=time.sleep):
    config = store.snapshot()
    interactive = bool(sys.stdin and sys.stdin.isatty()) if interactive is None else interactive
    if not interactive:
        return config  # Never prompt, validate a token, or visit a manager in headless startup.
    if config["configured"] and not force:
        return config
    language = config["language"]
    if language == "auto":
        try:
            from webui.preferences import read
            language = read()["language"]
        except ImportError:
            language = "ru"
    output(tr("connect", language))
    try:
        choice = input_fn(tr("choose", language)).strip()
        if choice != "1":
            store.update(configured=True, enabled=False)
            return store.snapshot()
        output(tr("setup", language))
        method = input_fn(tr("choose", language)).strip()
        owner = None
        url = manager_url or os.environ.get("XLAMBOT_TELEGRAM_MANAGER_URL")
        if method == "1" and url:
            client = ManagerClient(url)
            session = client.request("/v1/sessions", {})
            link = session["url"]
            if not link.startswith("https://t.me/"):
                raise SessionError("Invalid manager link")
            output(link)
            open_url(link)
            deadline = clock() + min(int(session.get("expires_in", 600)), 600)
            while clock() < deadline:
                claim = client.request("/v1/claim", {"session": session["session"], "claim_secret": session["claim_secret"]})
                if claim.get("ready"):
                    token, owner = claim["token"], claim["owner_id"]
                    break
                sleep(2)
            else:
                raise SessionError("Creation session expired")
        else:
            if method == "1":
                output("Manager is not configured / Менеджер не настроен. BotFather: https://t.me/BotFather")
                open_url("https://t.me/BotFather")
            token = secret_fn(tr("token", language)).strip()
        api = api_factory(token)
        bot = api.validate()
        # A previous bot's queued commands must not execute after changing tokens.
        updates = api.call("getUpdates", offset=-1, timeout=0, allowed_updates=["message", "callback_query"])
        offset = updates[-1]["update_id"] + 1 if updates else 0
        store.put_secret(token=token)
        store.update(configured=True, enabled=True, owner_id=owner, chat_id=None, offset=offset, limits={}, selected=None)
        code = store.pairing_code()
        output(tr("pair", language))
        link = f"https://t.me/{bot['username']}?start={code}"
        output(link)
        open_url(link)
        # /start verifies possession of the local code; it never grants control just by visiting the bot.
    except (APIError, SessionError, EOFError, KeyboardInterrupt):
        output("Telegram setup failed or cancelled / Настройка Telegram не завершена. xlamBOT continues / работа продолжается.")
        store.update(enabled=False)
    return store.snapshot()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telegram-setup", action="store_true")
    parser.add_argument("--panel", default="http://127.0.0.1:5195")
    parser.add_argument("--manager-url")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--quiet-start")
    parser.add_argument("--quiet-end")
    args = parser.parse_args()
    store = Store(args.directory)
    for field in ("quiet_start", "quiet_end"):
        value = getattr(args, field)
        if value:
            import datetime
            datetime.datetime.strptime(value, "%H:%M")
            store.update(**{field: value})
    lease = SingleInstance(store.directory / "client.lock")
    try:
        lease.acquire()
        config = configure_console(store, force=args.telegram_setup, manager_url=args.manager_url)
        if not config["enabled"]:
            return 0
        api = TelegramAPI(store.secret().get("token", ""))
        service = Service(store, api, LocalBridge(args.panel))
        try:
            service.run()
        except KeyboardInterrupt:
            service.stop.set()
        return 0
    except (APIError, RuntimeError, ValueError):
        print("Telegram unavailable / Telegram недоступен")
        return 1
    finally:
        lease.close()
