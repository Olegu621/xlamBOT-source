"""Optional startup hook used by create_app in both source and the regular EXE."""
import atexit
import sys
import threading

from .bridge import BridgeError, LocalBridge
from .service import Service
from .store import Store
from .transport import TelegramAPI


class AppBridge(LocalBridge):
    def __init__(self, app):
        self.app = app

    @property
    def language(self):
        from webui.preferences import read
        return read()["language"]

    def request(self, path, method="GET", payload=None, binary=False):
        # Dispatch through the exact same authenticated handlers used by the panel.
        with self.app.test_client() as client:
            response = client.open(path, method=method, json=payload,
                                   headers={"X-Xlam-UI-Token": self.app.config["UI_API_TOKEN"]})
            if response.status_code >= 400:
                raise BridgeError(f"Local control rejected ({response.status_code})")
            if binary:
                return response.data
            result = response.get_json(silent=True)
            if not isinstance(result, dict) or result.get("ok") is False:
                raise BridgeError("Local control unavailable")
            return result


def start_optional(app, store=None, configure=None, api_factory=TelegramAPI):
    if "--update-self-test" in sys.argv or app.config.get("TESTING"):
        return None
    lease = None
    try:
        from .cli import configure_console, SingleInstance
        store = store or Store()
        configure = configure or configure_console
        config = configure(store, force="--telegram-setup" in sys.argv)
        if not config["enabled"]:
            return None
        lease = SingleInstance(store.directory / "client.lock")
        lease.acquire()
        api = api_factory(store.secret().get("token", ""))
        service = Service(store, api, AppBridge(app))
        app.extensions["telegram"] = service
        thread = threading.Thread(target=service.run, daemon=True, name="telegram-control")
        thread.start()
        def stop():
            service.stop.set()
            lease.close()
        atexit.register(stop)
        app.extensions["telegram_stop"] = stop
        return service
    except Exception:
        if lease:
            lease.close()
        # Integration errors must not abort app creation or leak exception text.
        print("Telegram unavailable / Telegram недоступен; xlamBOT continues / работа продолжается.")
        return None
