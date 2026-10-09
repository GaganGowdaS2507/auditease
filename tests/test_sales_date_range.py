import unittest
from datetime import date

from modules.sales_module import BillSplitter


class SalesDateRangeTests(unittest.TestCase):
    def test_date_range_limits_generation(self):
        splitter = BillSplitter({"billing": {"default_margin_type": "range", "default_margin_min": 10, "default_margin_max": 20, "default_margin_global": 15, "tax_scheme": "regular"}})
        dates = splitter._distribute_dates(
            n_bills=5,
            month=10,
            year=2026,
            start_date=date(2026, 10, 5),
            end_date=date(2026, 10, 15),
        )

        self.assertEqual(len(dates), 5)
        for d in dates:
            self.assertGreaterEqual(d, date(2026, 10, 5))
            self.assertLessEqual(d, date(2026, 10, 15))

    def test_reversed_date_range_is_normalized(self):
        splitter = BillSplitter({"billing": {"default_margin_type": "range", "default_margin_min": 10, "default_margin_max": 20, "default_margin_global": 15, "tax_scheme": "regular"}})
        dates = splitter._distribute_dates(
            n_bills=3,
            month=10,
            year=2026,
            start_date=date(2026, 10, 15),
            end_date=date(2026, 10, 5),
        )

        self.assertEqual(len(dates), 3)
        for d in dates:
            self.assertGreaterEqual(d, date(2026, 10, 5))
            self.assertLessEqual(d, date(2026, 10, 15))


if __name__ == "__main__":
    unittest.main()
