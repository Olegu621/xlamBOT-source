"""Bounded HTTP transport. Exceptions never contain a Telegram token or URL."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid


class APIError(RuntimeError):
    def __init__(self, code="network", retry_after=0):
        super().__init__(f"Telegram request failed ({code})")
        self.code, self.retry_after = code, min(max(float(retry_after), 0), 3600)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TelegramAPI:
    def __init__(self, token, opener=None):
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", token):
            raise APIError("invalid_token")
        self._token = token
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def call(self, method, **payload):
        body = json.dumps(payload).encode()
        request = urllib.request.Request(f"https://api.telegram.org/bot{self._token}/{method}",
                                         body, {"Content-Type": "application/json"})
        return self._send(request, timeout=35 if method == "getUpdates" else 10)

    def _send(self, request, timeout):
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as error:
            try:
                result = json.loads(error.read(65536))
            except (ValueError, OSError):
                result = {}
            finally:
                error.close()
            raise APIError(error.code, result.get("parameters", {}).get("retry_after", 0)) from None
        except (OSError, urllib.error.URLError, TimeoutError):
            raise APIError("network") from None
        try:
            result = json.loads(raw)
        except ValueError:
            raise APIError("invalid_response") from None
        if not isinstance(result, dict):
            raise APIError("invalid_response")
        if len(raw) > 8 * 1024 * 1024 or not result.get("ok"):
            raise APIError(result.get("error_code", "invalid_response"),
                           result.get("parameters", {}).get("retry_after", 0))
        return result.get("result")

    def validate(self):
        bot = self.call("getMe")
        if not isinstance(bot, dict) or not bot.get("is_bot") or not bot.get("username"):
            raise APIError("invalid_bot")
        return bot

    def photo(self, chat_id, image, caption):
        boundary = uuid.uuid4().hex
        chunks = []
        for key, value in {"chat_id": chat_id, "caption": caption}.items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="screen.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode())
        chunks.extend([image, f"\r\n--{boundary}--\r\n".encode()])
        request = urllib.request.Request(f"https://api.telegram.org/bot{self._token}/sendPhoto",
                                         b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        return self._send(request, 15)
