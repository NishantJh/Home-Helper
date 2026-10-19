"""Ingest server on the Pi. Bind it to the Tailscale/LAN address only.

POST /ingest  {"company", "item", "order_tail", "code"}  -> {"status": "accepted"|"rejected"}
POST /query   {"transcript": "..."}             -> {"language": "...", "speech": "..."}
GET  /health  -> {"ok": true, "rejected": N}

The phone sends only those four fields, never message text. They are validated
(default deny) and kept in memory for 30 minutes. Request bodies are never logged.
"""
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .classify import validate
from .notify import forward
from .store import OtpStore
from .voice import answer

MAX_BODY = 4096
MIN_TOKEN_LEN = 16


def require_token(token):
    """An empty or short token would let anyone in ("Bearer " matches an empty one)."""
    if not isinstance(token, str) or len(token) < MIN_TOKEN_LEN:
        raise SystemExit(f"OTP_RELAY_TOKEN must be set and at least {MIN_TOKEN_LEN} characters long")
    return token


def make_handler(store, token, config, secrets, send=forward):
    require_token(token)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # no access log: it could carry content
            pass

        def _json(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorised(self):
            given = self.headers.get("Authorization", "")
            return hmac.compare_digest(given, f"Bearer {token}")

        def _body(self):
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None
            if n <= 0 or n > MAX_BODY:
                return None
            try:
                data = json.loads(self.rfile.read(n))
            except ValueError:
                return None
            return data if isinstance(data, dict) else None

        def do_GET(self):
            if self.path == "/health" and self._authorised():
                return self._json(200, {"ok": True, "rejected": store.rejected})
            self._json(404, {})

        def do_POST(self):
            if not self._authorised():
                return self._json(401, {})
            data = self._body()
            if data is None:
                return self._json(400, {})
            if self.path == "/ingest":
                otp = validate(data)
                if otp is None:
                    store.reject()
                    return self._json(200, {"status": "rejected"})
                entry = store.add(otp)
                send(entry, config, secrets)
                return self._json(200, {"status": "accepted"})
            if self.path == "/query":
                lang, speech = answer(store, str(data.get("transcript", "")))
                return self._json(200, {"language": lang, "speech": speech})
            self._json(404, {})

    return Handler


def main(argv=None):
    config_path = os.environ.get("OTP_RELAY_CONFIG", "otp_relay.config.json")
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    token = require_token(os.environ.get("OTP_RELAY_TOKEN"))
    secrets = {k: os.environ[k] for k in ("TELEGRAM_BOT_TOKEN", "WHATSAPP_TOKEN") if k in os.environ}
    host = config.get("bind", "127.0.0.1")
    port = int(config.get("port", 8765))
    server = ThreadingHTTPServer((host, port), make_handler(OtpStore(), token, config, secrets))
    print(f"otp_relay listening on {host}:{port}", file=sys.stderr)
    server.serve_forever()


if __name__ == "__main__":
    main()
