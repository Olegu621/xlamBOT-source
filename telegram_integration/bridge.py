"""Use xlamBOT's existing loopback API rather than duplicating gameplay controls."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import urllib.error
import urllib.parse
import urllib.request

from .transport import NoRedirect


class BridgeError(RuntimeError):
    pass


class TokenParser(HTMLParser):
    token = None
    language = "ru"

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "html":
            self.language = "en" if values.get("lang") == "en" else "ru"
        if tag == "meta" and values.get("name") == "xlam-ui-token":
            self.token = values.get("content")


class LocalBridge:
    def __init__(self, base="http://127.0.0.1:5195", opener=None):
        parsed = urllib.parse.urlsplit(base)
        if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
                or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise BridgeError("A loopback panel address is required")
        # Resolve localhost to a literal loopback address, bypassing proxies and DNS.
        host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
        self.base = f"{parsed.scheme}://{host}" + (f":{parsed.port}" if parsed.port else "")
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.token = None
        self.language = "ru"

    def renew(self):
        request = urllib.request.Request(self.base + "/panel")
        try:
            with self.opener.open(request, timeout=5) as response:
                page = response.read(2 * 1024 * 1024).decode("utf-8")
        except (OSError, urllib.error.URLError):
            raise BridgeError("Local panel unavailable") from None
        parser = TokenParser()
        parser.feed(page)
        if not parser.token:
            raise BridgeError("Local UI session token unavailable")
        self.token = parser.token
        self.language = parser.language

    def request(self, path, method="GET", payload=None, binary=False):
        if not self.token:
            self.renew()
        for attempt in range(2):
            data = json.dumps(payload or {}).encode() if method != "GET" else None
            request = urllib.request.Request(self.base + path, data,
                        {"X-Xlam-UI-Token": self.token, "Content-Type": "application/json"}, method=method)
            try:
                with self.opener.open(request, timeout=5) as response:
                    raw = response.read(5 * 1024 * 1024 + 1)
                if len(raw) > 5 * 1024 * 1024:
                    raise BridgeError("Local response too large")
                if binary:
                    return raw
                result = json.loads(raw)
                if result.get("ok") is False:
                    raise BridgeError("Local control rejected")
                return result
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 403 and attempt == 0:
                    self.renew()
                    continue
                raise BridgeError(f"Local request rejected ({error.code})") from None
            except (OSError, urllib.error.URLError, ValueError):
                # Never replay a control POST after a timeout: it may have executed.
                raise BridgeError("Local panel unavailable or invalid response") from None
        raise BridgeError("Local UI session expired")

    def devices(self):
        result = self.request("/api/devices")
        devices = {item["key"]: item for item in result.get("devices", []) if item.get("key")}
        for runtime in self.request("/api/devices/status").get("runtimes", []):
            key = runtime["key"]
            device = devices.setdefault(key, {"key": key, "serial": runtime.get("serial"), "state": "offline"})
            device["runtime"] = runtime
        return devices

    def telemetry(self, key):
        return self.request(f"/api/devices/{urllib.parse.quote(key, safe='')}/telemetry").get("telemetry", {})

    def control(self, key, action, serial=None):
        if action not in {"start", "pause", "resume", "stop"}:
            raise BridgeError("Unsupported control")
        return self.request(f"/api/devices/{urllib.parse.quote(key, safe='')}/{action}", "POST", {"serial": serial})

    def stop_all(self):
        return self.request("/api/devices/stop-all", "POST")

    def screenshot(self, key):
        return self.request(f"/api/devices/{urllib.parse.quote(key, safe='')}/snapshot", binary=True)
