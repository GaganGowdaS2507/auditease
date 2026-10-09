import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import setup


class DatabaseSchemaMigrationTests(unittest.TestCase):
    def test_ensure_database_schema_adds_missing_item_date_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "shop_database.db"

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE purchase_items (
                    id INTEGER PRIMARY KEY,
                    purchase_bill_id INTEGER,
                    item_name TEXT,
                    quantity REAL,
                    unit TEXT,
                    purchase_rate REAL,
                    gst_rate REAL,
                    gst_amount REAL,
                    total_amount REAL,
                    remaining_qty REAL
                )
            """)
            cur.execute("""
                CREATE TABLE sales_items (
                    id INTEGER PRIMARY KEY,
                    sales_bill_id INTEGER,
                    item_name TEXT,
                    quantity REAL,
                    unit TEXT,
                    selling_rate REAL,
                    gst_rate REAL,
                    cgst_rate REAL,
                    sgst_rate REAL,
                    cgst_amount REAL,
                    sgst_amount REAL,
                    total_amount REAL,
                    margin_percent REAL
                )
            """)
            conn.commit()
            conn.close()

            setup.ensure_database_schema(str(db_path))

            conn = sqlite3.connect(db_path)
            cols_purchase = [r[1] for r in conn.execute("PRAGMA table_info(purchase_items)").fetchall()]
            cols_sales = [r[1] for r in conn.execute("PRAGMA table_info(sales_items)").fetchall()]
            conn.close()

            self.assertIn("item_date", cols_purchase)
            self.assertIn("item_date", cols_sales)


if __name__ == "__main__":
    unittest.main()
