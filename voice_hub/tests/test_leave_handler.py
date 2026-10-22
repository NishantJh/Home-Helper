import os
import tempfile
import unittest
from datetime import date

from attendance import register
from attendance.db import open_db
from voice_hub.leave_handler import make_leave_handler
from voice_hub.pipeline import Hub

TODAY = date(2026, 10, 22)


class LeaveTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.dir.name, "a.db")
        with open_db(self.db) as c:
            register.add_maid(c, "Sunita", 6000)
        self.handler = make_leave_handler(self.db, aliases={"Sunita": ["सुनीता"]},
                                          today=lambda: TODAY)

    def tearDown(self):
        self.dir.cleanup()

    def days(self, status="leave"):
        with open_db(self.db) as c:
            return [r["day"] for r in c.execute(
                "SELECT day FROM attendance WHERE status = ? ORDER BY day", (status,))]

    def test_nothing_logged_before_confirmation(self):
        reply = self.handler("Sunita is on leave from 25 October to 27 October")
        self.assertIn("25 October to 27 October, 3 days", reply.speech)
        self.assertEqual(self.days(), [])

    def test_yes_logs_range_and_reports_paid_leaves(self):
        reply = self.handler("Sunita is on leave from 25 October to 27 October")
        done = reply.then("yes")
        self.assertEqual(self.days(), ["2026-10-25", "2026-10-26", "2026-10-27"])
        self.assertIn("used 3 of 2 paid leaves", done.speech)
        self.assertIn("1 unpaid", done.speech)

    def test_no_and_unclear_log_nothing(self):
        reply = self.handler("Sunita on leave tomorrow")
        self.assertEqual(reply.then("no").speech, "Okay, not logged.")
        self.assertIn("nothing was logged", reply.then("hmm maybe").speech)
        self.assertEqual(self.days(), [])

    def test_hindi_with_alias(self):
        reply = self.handler("सुनीता की छुट्टी कल से शुक्रवार तक")
        self.assertEqual(reply.language, "hi")
        self.assertIn("सुनीता".replace("सुनीता", "Sunita"), reply.speech)
        reply.then("हाँ")
        self.assertEqual(self.days(), ["2026-10-23"])

    def test_marathi_confirmation_language(self):
        reply = self.handler("सुनीता २५ ते २७ रजेवर")
        self.assertEqual(reply.language, "mr")
        self.assertIn("नोंद झाली", reply.then("होय").speech)

    def test_not_a_leave_request(self):
        self.assertIsNone(self.handler("what's the amazon otp"))
        self.assertIsNone(self.handler("leave the parcel at the door"))

    def test_unknown_maid_and_missing_date(self):
        self.assertIn("Which maid", self.handler("Rekha is on leave tomorrow").speech)
        self.assertIn("dates", self.handler("Sunita is on leave").speech)

    def test_voice_present_cannot_overwrite_logged_leave(self):
        self.handler("Sunita on leave tomorrow").then("yes")
        with open_db(self.db) as c:
            self.assertFalse(register.mark(c, "Sunita", date(2026, 10, 23), "present", "camera"))
        self.assertEqual(self.days(), ["2026-10-23"])

    def test_hub_listens_again_without_wake_word(self):
        spoken, wakes, heard = [], [], iter(["Sunita on leave tomorrow", "yes"])
        hub = Hub(wait_for_wake=lambda: wakes.append(1), listen=lambda: "a",
                  transcribe=lambda a: next(heard), speak=lambda t, l: spoken.append(t),
                  handlers=[self.handler])
        hub.run_once()
        self.assertEqual(len(wakes), 1)
        self.assertEqual(len(spoken), 2)
        self.assertEqual(self.days(), ["2026-10-23"])
