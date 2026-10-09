import os
import tempfile
import unittest

from modules.purchase_module import parse_csv_bill, extract_bill_date_from_csv


class PurchaseCsvDateSupportTests(unittest.TestCase):
    def test_csv_with_bill_date_is_parsed_and_normalized(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as handle:
            handle.write(
                "bill_date,item_name,hsn_code,quantity,unit,purchase_rate,gst_rate\n"
                "15-01-2026,GI Pipe 1 inch 6mtr,7306,10,piece,250.00,18\n"
            )
            temp_path = handle.name

        try:
            bill_date = extract_bill_date_from_csv(temp_path)
            items = parse_csv_bill(temp_path)

            self.assertEqual(bill_date, "2026-01-15")
            self.assertEqual(items[0]["item_name"], "GI Pipe 1 inch 6mtr")
            self.assertEqual(items[0]["quantity"], 10)
        finally:
            os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
