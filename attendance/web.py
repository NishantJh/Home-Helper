"""Small home-network web page to view the register and correct entries."""
import html
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import register
from .db import open_db


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


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            today = date.today()
            year = int(q.get("year", [today.year])[0])
            month = int(q.get("month", [today.month])[0])
            page = render(db_path, year, month).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            form = parse_qs(self.rfile.read(length).decode())
            try:
                with open_db(db_path) as conn:
                    register.mark(conn, form["maid"][0], form["day"][0], form["status"][0], source="web")
            except (KeyError, ValueError):
                self.send_error(400)
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


def serve(db_path, host="0.0.0.0", port=8080):
    ThreadingHTTPServer((host, port), make_handler(db_path)).serve_forever()
