import unittest
from datetime import date

from attendance import register
from attendance.db import connect


class RegisterTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        register.add_maid(self.conn, "Sunita", 3000, paid_leaves_per_month=2)

    def test_paid_leaves_then_deduction(self):
        register.mark_leave_range(self.conn, "Sunita", date(2026, 9, 1), date(2026, 9, 4))
        row = register.month_summary(self.conn, 2026, 9, today=date(2026, 10, 1))[0]
        self.assertEqual((row["paid_leave_days"], row["unpaid_leave_days"]), (2, 2))
        self.assertEqual(row["deduction"], 200.0)  # 3000 / 30 * 2
        self.assertEqual(row["net_salary"], 2800.0)

    def test_no_record_is_flagged_not_deducted(self):
        row = register.month_summary(self.conn, 2026, 9, today=date(2026, 10, 1))[0]
        self.assertEqual(len(row["unconfirmed_days"]), 30)
        self.assertEqual(row["deduction"], 0)

    def test_current_month_only_counts_days_so_far(self):
        row = register.month_summary(self.conn, 2026, 10, today=date(2026, 10, 5))[0]
        self.assertEqual(len(row["unconfirmed_days"]), 5)

    def test_auto_present_does_not_override_leave(self):
        register.mark(self.conn, "Sunita", "2026-09-01", "leave")
        self.assertFalse(register.mark(self.conn, "Sunita", "2026-09-01", "present", source="camera"))
        self.assertTrue(register.mark(self.conn, "Sunita", "2026-09-01", "present", source="manual"))

    def test_unknown_maid(self):
        with self.assertRaises(KeyError):
            register.mark(self.conn, "Nobody", "2026-09-01", "present")


if __name__ == "__main__":
    unittest.main()
