"""Per-user preferences and OS-protected secrets, outside xlamBOT exports."""
from __future__ import annotations

import copy
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time

CATEGORIES = ("lifecycle", "error", "adb", "game", "match", "trophies", "brawler", "queue", "update", "summary")
PRESETS = {
    "errors": {"error", "adb", "game"},
    "important": {"lifecycle", "error", "adb", "game", "queue", "update", "summary"},
    "all": set(CATEGORIES), "off": set(),
}


def defaults():
    return {"configured": False, "enabled": False, "language": "auto", "owner_id": None,
            "chat_id": None, "selected": None, "device_filter": "all", "offset": 0,
            "categories": sorted(PRESETS["important"]), "summary_minutes": 30,
            "quiet_start": "23:00", "quiet_end": "08:00", "quiet_enabled": False,
            "critical_at_night": True, "pair_hash": "", "pair_until": 0, "limits": {}}


def protect(data: bytes, decrypt=False) -> bytes:
    if os.name != "nt":
        return data  # POSIX protection is mode 0700/0600 on the containing files.

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    library = ctypes.WinDLL("crypt32", use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("OS secret protection failed")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def default_directory():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
    return base / "xlamBOT-Telegram"


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else default_directory()
        self.lock = threading.RLock()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data = defaults()
        path = self.directory / "preferences.json"
        if path.exists():
            self.data.update(json.loads(path.read_text("utf-8")))

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def _write(self, name, data):
        path = self.directory / name
        temporary = self.directory / (name + ".tmp")
        fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)

    def update(self, **values):
        with self.lock:
            self.data.update(values)
            self._write("preferences.json", json.dumps(self.data, ensure_ascii=False).encode())

    def put_secret(self, **values):
        with self.lock:
            self._write("secrets.bin", protect(json.dumps(values).encode()))

    def secret(self):
        with self.lock:
            path = self.directory / "secrets.bin"
            return json.loads(protect(path.read_bytes(), decrypt=True)) if path.exists() else {}

    def pairing_code(self, now=None):
        now = time.time() if now is None else now
        code = secrets.token_urlsafe(24)
        self.update(pair_hash=hashlib.sha256(code.encode()).hexdigest(), pair_until=now + 300)
        return code

    def bind(self, code, user_id, chat_id, now=None):
        now = time.time() if now is None else now
        with self.lock:
            digest = hashlib.sha256(str(code).encode()).hexdigest()
            if (self.data["chat_id"] is not None or now >= self.data["pair_until"]
                    or not hmac.compare_digest(digest, self.data["pair_hash"])
                    or self.data["owner_id"] not in (None, user_id) or user_id != chat_id):
                return False
            self.update(owner_id=user_id, chat_id=chat_id, pair_hash="", pair_until=0)
            return True

    def unlink(self):
        self.update(enabled=False, owner_id=None, chat_id=None, pair_hash="", pair_until=0, limits={})
        self.put_secret()


def redact(value):
    import re
    text = str(value)
    text = re.sub(r"\d{5,}:[A-Za-z0-9_-]{20,}", "[REDACTED]", text)
    text = re.sub(r"(?i)((?:token|secret|authorization|pair_hash)[\s\"'=:\]]+)[^\s,;}]+", r"\1[REDACTED]", text)
    return text[:1000]
