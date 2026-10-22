"""Routes OTP requests to the otp_relay server on this Pi."""
import json
import re
import urllib.request

from .pipeline import Reply

_OTP = re.compile(
    r"\bo\.?\s?t\.?\s?p\b|one[- ]time (?:password|code)|delivery (?:code|pin)|"
    r"ओ\s?टी\s?पी|ओटीपी|वन टाइम",
    re.IGNORECASE,
)


def is_otp_request(text: str) -> bool:
    return _OTP.search(text) is not None


def _post_query(url, token, transcript):
    req = urllib.request.Request(
        url, data=json.dumps({"transcript": transcript}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def make_otp_handler(url="http://127.0.0.1:8765/query", token="", post=_post_query):
    def handler(text):
        if not is_otp_request(text):
            return None
        body = post(url, token, text)
        return Reply(speech=body["speech"], language=body["language"])
    return handler
