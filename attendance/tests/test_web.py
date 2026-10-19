import base64
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from attendance import register, web
from attendance.db import open_db


class WebTest(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(tempfile.mkdtemp(), "a.db")
        with open_db(self.db_path) as conn:
            register.add_maid(conn, "Sunita", 3000)
        self.password = "correct horse battery staple"
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), web.make_handler(self.db_path, self.password)
        )
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)

    def _get(self, path="/", auth=True, headers=None):
        req = urllib.request.Request(self.base + path, headers=headers or {})
        if auth:
            req.add_header("Authorization", self._auth_header())
        return urllib.request.urlopen(req)

    def _auth_header(self, password=None):
        token = base64.b64encode(f"admin:{password or self.password}".encode()).decode()
        return f"Basic {token}"

    def test_rejects_no_credentials(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._get(auth=False)
        self.assertEqual(cm.exception.code, 401)

    def test_rejects_wrong_password(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._get(auth=False, headers={"Authorization": self._auth_header("wrong")})
        self.assertEqual(cm.exception.code, 401)

    def test_accepts_correct_password(self):
        resp = self._get()
        self.assertEqual(resp.status, 200)
        self.assertIn(b"Sunita", resp.read())

    def test_cross_site_post_is_rejected(self):
        data = b"maid=Sunita&day=2026-10-05&status=present"
        req = urllib.request.Request(self.base + "/mark", data=data, method="POST", headers={
            "Authorization": self._auth_header(),
            "Origin": "http://evil.example",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)

    def test_web_correction_can_turn_leave_into_present(self):
        # C2: a web correction is a deliberate human edit, so unlike an
        # automatic camera/voice mark it IS allowed to override a leave.
        with open_db(self.db_path) as conn:
            register.mark(conn, "Sunita", "2026-10-05", "leave")
        data = b"maid=Sunita&day=2026-10-05&status=present"
        req = urllib.request.Request(self.base + "/mark", data=data, method="POST", headers={
            "Authorization": self._auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        })
        resp = urllib.request.urlopen(req)  # urllib follows the 303 to "/" (200) automatically
        self.assertEqual(resp.status, 200)
        with open_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT status FROM attendance WHERE day = '2026-10-05'"
            ).fetchone()
        self.assertEqual(row["status"], "present")

    def test_bad_status_is_rejected_not_silently_dropped(self):
        data = b"maid=Sunita&day=2026-10-05&status=not-a-status"
        req = urllib.request.Request(self.base + "/mark", data=data, method="POST", headers={
            "Authorization": self._auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        })
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)

    def test_bad_month_in_query_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._get("/?month=13")
        self.assertEqual(cm.exception.code, 400)

    def test_serve_refuses_lan_host_without_password(self):
        with self.assertRaises(SystemExit):
            web.serve(self.db_path, host="0.0.0.0", port=0, password=None)


if __name__ == "__main__":
    unittest.main()
