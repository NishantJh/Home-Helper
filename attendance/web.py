"""Small home-network web page to view the register and correct entries.

Requires a password (`ATTENDANCE_WEB_PASSWORD` or --password): anyone on
the home Wi-Fi, or any site opened in a home browser, could otherwise see
salaries and post corrections. A correction made here is a household
member acting deliberately, so it's recorded as a manual edit (like the
`mark` CLI command) and -- unlike an automatic camera/voice "present" --
it's allowed to turn a leave day back into present.
"""
import hmac
import html
import secrets
import sqlite3
from base64 import b64decode
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import register
from .db import open_db

ALLOWED_STATUS = {"present", "leave"}


def render(db_path, year, month):
    with open_db(db_path) as conn:
        rows = register.month_summary(conn, year, month)
        maids = [m["name"] for m in register.list_maids(conn)]
    e = html.escape
    body = [f"<h1>Attendance {year}-{month:02d}</h1>", "<table border=1 cellpadding=4>",
            "<tr><th>Maid</th><th>Present</th><th>Leave</th><th>Unpaid</th><th>Deduction</th><th>Unconfirmed days</th></tr>"]
    for r in rows:
        body.append(
            f"<tr><td>{e(r['name'])}</td><td>{r['present_days']}</td><td>{r['leave_days']}</td>"
            f"<td>{r['unpaid_leave_days']}</td><td>{r['deduction']:.2f}</td>"
            f"<td>{len(r['unconfirmed_days'])}</td></tr>")
    body.append("</table><h2>Correct an entry</h2><form method=post action=/mark>")
    body.append("<select name=maid>" + "".join(f"<option>{e(n)}</option>" for n in maids) + "</select>")
    body.append(f"<input name=day type=date value={date.today().isoformat()}>")
    body.append("<select name=status><option>present</option><option>leave</option></select>")
    body.append("<button>Save</button></form>")
    return "<!doctype html><meta charset=utf-8><title>Attendance</title>" + "".join(body)


def _authorized(handler, password):
    header = handler.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        _, given_password = b64decode(header[6:]).decode().split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(given_password, password)


def _same_site(handler):
    """Reject a cross-site POST (the actual fix for CSRF here): a form on
    another site can't set a matching Origin header, so this is enough
    without adding a token to track per form load."""
    origin = handler.headers.get("Origin")
    if origin is None:
        return True  # same-origin browser navigation/form posts omit it
    return urlparse(origin).netloc == handler.headers.get("Host", "")


def make_handler(db_path, password):
    class Handler(BaseHTTPRequestHandler):
        def _require_auth(self):
            if _authorized(self, password):
                return True
            body = b"authorization required"
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Attendance"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return False

        def do_GET(self):
            if not self._require_auth():
                return
            q = parse_qs(urlparse(self.path).query)
            today = date.today()
            try:
                year = int(q.get("year", [today.year])[0])
                month = int(q.get("month", [today.month])[0])
                if not 1 <= month <= 12:
                    raise ValueError
            except ValueError:
                self.send_error(400, "bad year/month")
                return
            page = render(db_path, year, month).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self):
            if not self._require_auth():
                return
            if not _same_site(self):
                self.send_error(403, "cross-site request rejected")
                return
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode())
            try:
                maid, day, status = form["maid"][0], form["day"][0], form["status"][0]
                date.fromisoformat(day)
                if status not in ALLOWED_STATUS:
                    raise ValueError(f"bad status {status!r}")
                with open_db(db_path) as conn:
                    # source="manual": a logged-in household member correcting
                    # the register by hand, same as the CLI `mark` command --
                    # allowed to turn a leave back into present, unlike an
                    # automatic camera/voice mark.
                    register.mark(conn, maid, day, status, source="manual")
            except (KeyError, ValueError, sqlite3.IntegrityError) as e:
                self.send_error(400, str(e))
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


def serve(db_path, host="0.0.0.0", port=8080, password=None):
    if not password:
        if host in ("127.0.0.1", "localhost", "::1"):
            password = secrets.token_urlsafe(16)
            print(f"No password set; generated one for this run: {password}")
        else:
            raise SystemExit(
                "refusing to serve on a non-local address with no password set "
                "(ATTENDANCE_WEB_PASSWORD or --password) -- anyone on this "
                "network could otherwise see salaries and edit the register"
            )
    ThreadingHTTPServer((host, port), make_handler(db_path, password)).serve_forever()
