"""HTTPS client for the separately deployed manager; contains no manager secret."""
import json
import urllib.error
import urllib.parse
import urllib.request

from .transport import NoRedirect


class SessionError(ValueError):
    pass


class ManagerClient:
    def __init__(self, url):
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1"})) or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise SessionError("Manager must use HTTPS (HTTP allowed only on loopback)")
        self.url = url.rstrip("/")
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path, payload):
        request = urllib.request.Request(self.url + path, json.dumps(payload).encode(), {"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=10) as response:
                return json.loads(response.read(65536))
        except (ValueError, OSError, urllib.error.URLError) as error:
            if isinstance(error, urllib.error.HTTPError):
                error.close()
            raise SessionError("Manager unavailable or session expired") from None
