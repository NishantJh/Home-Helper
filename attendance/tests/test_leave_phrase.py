import unittest
from datetime import date

from attendance.leave_phrase import parse_leave

TODAY = date(2026, 10, 22)  # Thursday
NAMES = ["Sunita"]


def parse(text, names=NAMES, aliases=None):
    return parse_leave(text, names, TODAY, aliases)


class DateTests(unittest.TestCase):
    def test_named_past_date_stays_this_year(self):  # H2
        i = parse("Sunita was on leave on 14 October")
        self.assertEqual((i.start, i.end), (date(2026, 10, 14),) * 2)
        self.assertEqual(parse("Sunita leave on 25 December").start, date(2026, 12, 25))
        self.assertEqual(parse("Sunita leave on 5 January").start, date(2027, 1, 5))

    def test_to_filler_is_not_a_range(self):  # M1
        for text in ["Sunita wants to take leave on Friday",
                     "Sunita is going to be off on Monday"]:
            i = parse(text)
            self.assertEqual(i.start, i.end, text)
        i = parse("सुनीता ते रजेवर आहे उद्या", aliases={"Sunita": ["सुनीता"]})
        self.assertEqual((i.start, i.end), (date(2026, 10, 23),) * 2)
        self.assertEqual(parse("Sunita on leave to Friday").end, date(2026, 10, 23))
        self.assertEqual(parse("Sunita on leave till Friday").start, TODAY)

    def test_readme_marathi_example(self):  # M2
        i = parse("सुनीता उद्यापासून 3 दिवस रजेवर", aliases={"Sunita": ["सुनीता"]})
        self.assertEqual((i.start, i.end), (date(2026, 10, 23), date(2026, 10, 25)))
        self.assertEqual(parse("Sunita कलसे छुट्टी 2 दिन").start, date(2026, 10, 23))

    def test_past_tense_day_number_stays_this_month(self):  # M3
        self.assertEqual(parse("Sunita was absent on 10th").start, date(2026, 10, 10))
        self.assertEqual(parse("Sunita on leave on 3rd").start, date(2026, 11, 3))

    def test_hindi_kal_past_tense_is_yesterday(self):  # L1
        self.assertEqual(parse("Sunita की छुट्टी कल थी").start, date(2026, 10, 21))


class MaidTests(unittest.TestCase):
    def test_longer_name_wins_over_contained_name(self):  # M4
        names = ["Asha", "Ashalata"]
        self.assertEqual(parse("Ashalata on leave tomorrow", names).maid, "Ashalata")
        self.assertEqual(parse("Asha on leave tomorrow", names).maid, "Asha")

    def test_whole_words_only(self):
        self.assertIsNone(parse("Ashalata on leave tomorrow", ["Asha"]).maid)


if __name__ == "__main__":
    unittest.main()
