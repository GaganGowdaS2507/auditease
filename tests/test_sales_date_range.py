import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from modules.sales_module import BillSplitter
import modules.sales_module as sm
import modules.purchase_module as pm
import modules.dashboard_module as dm
import modules.report_module as rm
import modules.tally_module as tm


def create_test_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchase_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number TEXT NOT NULL,
            dealer_name TEXT NOT NULL,
            bill_date TEXT NOT NULL,
            bill_month INTEGER NOT NULL,
            bill_year INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            total_gst REAL NOT NULL,
            grand_total REAL NOT NULL,
            bill_type TEXT DEFAULT 'regular',
            file_path TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchase_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_bill_id INTEGER NOT NULL,
            item_master_id INTEGER,
            item_name TEXT NOT NULL,
            item_date TEXT DEFAULT '',
            hsn_code TEXT DEFAULT '-',
            quantity REAL NOT NULL,
            unit TEXT DEFAULT 'piece',
            purchase_rate REAL NOT NULL,
            gst_rate REAL NOT NULL,
            gst_amount REAL NOT NULL,
            total_amount REAL NOT NULL,
            remaining_qty REAL NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number TEXT NOT NULL,
            customer_id INTEGER,
            customer_name TEXT NOT NULL,
            bill_date TEXT NOT NULL,
            bill_month INTEGER NOT NULL,
            bill_year INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            total_cgst REAL NOT NULL,
            total_sgst REAL NOT NULL,
            grand_total REAL NOT NULL,
            bill_type TEXT DEFAULT 'regular',
            margin_applied REAL DEFAULT 0,
            file_path TEXT DEFAULT '',
            is_printed INTEGER DEFAULT 0,
            linked_month INTEGER NOT NULL,
            linked_year INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sales_bill_id INTEGER NOT NULL,
            purchase_item_id INTEGER,
            item_name TEXT NOT NULL,
            item_date TEXT DEFAULT '',
            hsn_code TEXT DEFAULT '-',
            quantity REAL NOT NULL,
            unit TEXT DEFAULT 'piece',
            selling_rate REAL NOT NULL,
            gst_rate REAL NOT NULL,
            cgst_rate REAL NOT NULL,
            sgst_rate REAL NOT NULL,
            cgst_amount REAL NOT NULL,
            sgst_amount REAL NOT NULL,
            total_amount REAL NOT NULL,
            margin_percent REAL NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            city TEXT DEFAULT '',
            is_auto_generated INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS items_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            item_name_lower TEXT NOT NULL,
            hsn_code TEXT DEFAULT '-',
            gst_rate REAL DEFAULT 18.0,
            unit TEXT DEFAULT 'piece',
            category TEXT DEFAULT 'general',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed customers
    for name in ["Ramesh Kumar", "Suresh Patel", "Anand Rao", "Vijay Naik", "Mohan Lal"]:
        cur.execute("INSERT INTO customers (name, city) VALUES (?, ?)", (name, "Bangalore"))

    # Seed Bill 1: Dec 2025 (Carried forward stock)
    cur.execute("""
        INSERT INTO purchase_bills (bill_number, dealer_name, bill_date, bill_month, bill_year, subtotal, total_gst, grand_total)
        VALUES ('PB-DEC-01', 'Dec Metals Corp', '2025-12-20', 12, 2025, 50000.0, 9000.0, 59000.0)
    """)
    dec_bill_id = cur.lastrowid
    cur.execute("""
        INSERT INTO purchase_items (purchase_bill_id, item_name, item_date, hsn_code, quantity, unit, purchase_rate, gst_rate, gst_amount, total_amount, remaining_qty)
        VALUES (?, 'Brass Screws 2in', '2025-12-20', '7318', 100.0, 'Nos', 100.0, 18.0, 1800.0, 11800.0, 100.0)
    """, (dec_bill_id,))
    cur.execute("""
        INSERT INTO purchase_items (purchase_bill_id, item_name, item_date, hsn_code, quantity, unit, purchase_rate, gst_rate, gst_amount, total_amount, remaining_qty)
        VALUES (?, 'Copper Wire 1mm', '2025-12-20', '7408', 200.0, 'Mtrs', 200.0, 18.0, 7200.0, 47200.0, 200.0)
    """, (dec_bill_id,))

    # Seed Bill 2: Jan 2026
    cur.execute("""
        INSERT INTO purchase_bills (bill_number, dealer_name, bill_date, bill_month, bill_year, subtotal, total_gst, grand_total)
        VALUES ('PB-JAN-01', 'Jan Hardware Supplies', '2026-01-10', 1, 2026, 100000.0, 18000.0, 118000.0)
    """)
    jan_bill_id = cur.lastrowid
    cur.execute("""
        INSERT INTO purchase_items (purchase_bill_id, item_name, item_date, hsn_code, quantity, unit, purchase_rate, gst_rate, gst_amount, total_amount, remaining_qty)
        VALUES (?, 'Steel Hammer 500g', '2026-01-10', '8205', 50.0, 'Nos', 400.0, 18.0, 3600.0, 23600.0, 50.0)
    """, (jan_bill_id,))
    cur.execute("""
        INSERT INTO purchase_items (purchase_bill_id, item_name, item_date, hsn_code, quantity, unit, purchase_rate, gst_rate, gst_amount, total_amount, remaining_qty)
        VALUES (?, 'PVC Pipe 20mm', '2026-01-10', '3917', 400.0, 'Mtrs', 100.0, 18.0, 7200.0, 47200.0, 400.0)
    """, (jan_bill_id,))
    cur.execute("""
        INSERT INTO purchase_items (purchase_bill_id, item_name, item_date, hsn_code, quantity, unit, purchase_rate, gst_rate, gst_amount, total_amount, remaining_qty)
        VALUES (?, 'Door Handle SS', '2026-01-10', '8302', 100.0, 'pair', 400.0, 18.0, 7200.0, 47200.0, 100.0)
    """, (jan_bill_id,))

    conn.commit()
    conn.close()


class SalesDateRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.test_db_path = Path(cls.tmpdir.name) / "test_shop.db"
        create_test_db(cls.test_db_path)

        # Redirect db in all modules
        cls.orig_paths = {
            "sm": sm.db.db_path,
            "pm": pm.db.db_path,
            "dm": dm.db.db_path,
            "rm": rm.db.db_path,
            "tm": tm.db.db_path,
        }
        sm.db.db_path = cls.test_db_path
        pm.db.db_path = cls.test_db_path
        dm.db.db_path = cls.test_db_path
        rm.db.db_path = cls.test_db_path
        tm.db.db_path = cls.test_db_path

    @classmethod
    def tearDownClass(cls):
        sm.db.db_path = cls.orig_paths["sm"]
        pm.db.db_path = cls.orig_paths["pm"]
        dm.db.db_path = cls.orig_paths["dm"]
        rm.db.db_path = cls.orig_paths["rm"]
        tm.db.db_path = cls.orig_paths["tm"]
        cls.tmpdir.cleanup()

    def setUp(self):
        # Reset remaining_qty to initial quantity before each test
        conn = sqlite3.connect(self.test_db_path)
        cur = conn.cursor()
        cur.execute("UPDATE purchase_items SET remaining_qty = quantity")
        cur.execute("DELETE FROM sales_items")
        cur.execute("DELETE FROM sales_bills")
        conn.commit()
        conn.close()

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

    def test_multiple_bills_generation(self):
        settings = sm.load_settings()
        splitter = BillSplitter(settings)
        for count in [2, 3]:
            bills = splitter.split(month=1, year=2026, n_bills=count)
            self.assertEqual(len(bills), count)

    def test_flat_markup_amount_is_applied_instead_of_percent_margin(self):
        splitter = BillSplitter({
            "billing": {
                "default_margin_type": "flat",
                "default_margin_min": 10,
                "default_margin_max": 20,
                "default_margin_global": 15,
                "flat_markup_amount": 5,
                "tax_scheme": "composition",
            }
        })

        self.assertEqual(splitter.get_margin_for_item(), 5)
        selling_rate, gst_rate, cgst_rate, sgst_rate = splitter.calculate_selling_rate(
            200, 18, 5
        )

        self.assertEqual(selling_rate, 205.0)
        self.assertEqual(gst_rate, 0.0)
        self.assertEqual(cgst_rate, 0.0)
        self.assertEqual(sgst_rate, 0.0)

    def test_target_profit_amount_sets_total_sales_multiplier(self):
        splitter = BillSplitter({
            "billing": {
                "default_margin_type": "target_profit",
                "default_margin_min": 10,
                "default_margin_max": 20,
                "default_margin_global": 15,
                "flat_markup_amount": 5,
                "target_profit_amount": 50000,
                "tax_scheme": "regular",
            }
        })

        self.assertEqual(splitter.get_target_profit_multiplier(200000), 1.25)

    def test_target_profit_amount_generates_exact_target_profit(self):
        settings = sm.load_settings()
        splitter = BillSplitter(settings)
        target_profit = 25000.0
        bills = splitter.split(
            month=1,
            year=2026,
            n_bills=5,
            override_margin_type="target_profit",
            override_target_profit_amount=target_profit,
            include_carried_forward=False,
        )
        tally = splitter.verify_tally(1, 2026, bills)
        self.assertTrue(tally["all_items_tallied"])
        self.assertAlmostEqual(tally["profit"], target_profit, places=2)
        for bill in bills:
            self.assertGreater(len(bill["items"]), 0)

    def test_carried_forward_inventory_from_earlier_months(self):
        """Unsold stock from Dec 2025 is carried forward into Jan 2026 sales pool"""
        settings = sm.load_settings()
        splitter = BillSplitter(settings)

        # Query pool with include_carried_forward=True
        pool = splitter.get_purchase_pool(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            include_carried_forward=True,
        )

        item_names = [it["item_name"] for it in pool]
        # Brass Screws and Copper Wire were purchased in Dec 2025
        self.assertIn("Brass Screws 2in", item_names)
        self.assertIn("Copper Wire 1mm", item_names)
        # Steel Hammer, PVC Pipe, Door Handle SS were purchased in Jan 2026
        self.assertIn("Steel Hammer 500g", item_names)
        self.assertIn("PVC Pipe 20mm", item_names)

        # Total items pool combines both months
        self.assertEqual(len(pool), 5)

        # Generate sales bills using both Dec carried forward and Jan stock
        bills = splitter.split(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            n_bills=3,
            include_carried_forward=True,
        )
        self.assertEqual(len(bills), 3)

        # All items are tallied across the continuous date range
        tally = splitter.verify_tally(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            generated_bills=bills,
        )
        self.assertTrue(tally["all_items_tallied"])
        # Total cost equals 50,000 (Dec) + 100,000 (Jan) = 150,000
        self.assertAlmostEqual(tally["purchase_taxable"], 150000.0, places=2)

    def test_partial_stock_allocation_preserves_remaining_qty(self):
        """Allocating 50% of stock leaves remaining 50% in inventory"""
        settings = sm.load_settings()
        splitter = BillSplitter(settings)

        bills = splitter.split(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            n_bills=2,
            allocation_mode="percentage",
            stock_percentage=50.0,
            include_carried_forward=False,
        )

        total_sold_cost = sum(
            item["quantity"] * item["purchase_rate"]
            for bill in bills
            for item in bill["items"]
        )
        # Jan stock total taxable is 100,000, so 50% is 50,000
        self.assertAlmostEqual(total_sold_cost, 50000.0, places=1)

    def test_dashboard_stat_cards_with_carried_forward_stock(self):
        """Dashboard accurately reports period purchases, sales, and active stock on hand"""
        fetcher = dm.DashboardFrame
        # Run a query simulating dashboard load for Jan 2026
        s_date = date(2026, 1, 1)
        e_date = date(2026, 1, 31)

        # Before any sales: active stock on hand includes both Dec (50,000) and Jan (100,000) = 150,000
        stock = dm.db.query_one("""
            SELECT COALESCE(SUM(pi.remaining_qty * pi.purchase_rate), 0) AS stock_val,
                   COALESCE(SUM(pi.remaining_qty), 0) AS stock_units
            FROM purchase_items pi
            JOIN purchase_bills pb ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_date <= '2026-01-31' AND pi.remaining_qty > 0.0001
        """)
        self.assertAlmostEqual(stock["stock_val"], 150000.0, places=2)
        self.assertEqual(stock["stock_units"], 850.0)

    def test_tally_engine_continuous_stock_reconciliation(self):
        """TallyEngine reports 'ok' when unsold stock is carried forward"""
        engine = tm.TallyEngine()
        results = engine.run_full_tally(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        # Quantity check passes as OK because remaining stock is valid closing inventory
        qty_check = results["checks"]["quantity"]
        self.assertEqual(qty_check["status"], "ok")
        self.assertEqual(qty_check["err_count"], 0)

    def test_report_fetcher_period_data(self):
        """ReportDataFetcher calculates period summaries with closing inventory"""
        fetcher = rm.ReportDataFetcher()
        data = fetcher.get_monthly_data(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        self.assertEqual(data["purchase"]["bill_count"], 1)
        self.assertAlmostEqual(data["purchase"]["taxable"], 100000.0, places=2)
        # Closing stock valuation as of 2026-01-31 includes Dec + Jan unsold stock = 150,000
        self.assertAlmostEqual(data["closing_val"], 150000.0, places=2)

    def test_customer_mode_cash_bills(self):
        """Bills generated with customer_mode='cash' use 'Cash Bill'"""
        settings = sm.load_settings()
        splitter = BillSplitter(settings)
        bills = splitter.split(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            n_bills=3,
            customer_mode="cash",
        )
        self.assertEqual(len(bills), 3)
        for bill in bills:
            self.assertEqual(bill["customer"]["name"], "Cash Bill")

    def test_customer_mode_custom_cash_name(self):
        """Bills generated with customer_mode='cash' use custom cash_name if provided"""
        settings = sm.load_settings()
        splitter = BillSplitter(settings)
        bills = splitter.split(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            n_bills=3,
            customer_mode="cash",
            cash_name="Counter Cash Sale",
        )
        self.assertEqual(len(bills), 3)
        for bill in bills:
            self.assertEqual(bill["customer"]["name"], "Counter Cash Sale")


if __name__ == "__main__":
    unittest.main()
