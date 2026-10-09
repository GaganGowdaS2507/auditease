# modules/sales_module.py
# ============================================================
# SALES MODULE — CORE OF THE SYSTEM
#
# Features:
# 1. View monthly purchase pool
# 2. Configure split parameters
# 3. Smart splitting algorithm
#    - Distributes items naturally across N bills
#    - Random quantities per bill
#    - Random margin per item (min% to max%)
#    - Random dates spread across month
#    - Auto-assigns unique customer names
#    - GST calculated correctly per item
# 4. Preview all generated bills before saving
# 5. Tally verification
# 6. Save to database + generate PDFs
# 7. Export to CSV
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import json
import csv
import random
import math
from pathlib import Path
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

# ============================================================
# PATHS
# ============================================================
BASE_DIR    = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "settings.json"
DB_PATH     = BASE_DIR / "database" / "shop_database.db"

# ============================================================
# COLORS & FONTS
# ============================================================
COLORS = {
    "primary":        "#1a237e",
    "primary_light":  "#3949ab",
    "accent":         "#ff6f00",
    "success":        "#2e7d32",
    "success_light":  "#e8f5e9",
    "warning":        "#f57f17",
    "warning_light":  "#fff3e0",
    "danger":         "#c62828",
    "danger_light":   "#ffebee",
    "bg_main":        "#f5f5f5",
    "bg_card":        "#ffffff",
    "text_dark":      "#212121",
    "text_light":     "#ffffff",
    "text_muted":     "#757575",
    "border":         "#e0e0e0",
    "row_even":       "#f9f9f9",
    "row_odd":        "#ffffff",
    "header_bg":      "#1a237e",
}

FONTS = {
    "heading":    ("Helvetica", 18, "bold"),
    "subheading": ("Helvetica", 13, "bold"),
    "body":       ("Helvetica", 11),
    "body_bold":  ("Helvetica", 11, "bold"),
    "small":      ("Helvetica", 9),
    "button":     ("Helvetica", 11, "bold"),
    "label":      ("Helvetica", 10),
    "label_bold": ("Helvetica", 10, "bold"),
    "table":      ("Helvetica", 10),
    "table_bold": ("Helvetica", 10, "bold"),
    "number":     ("Helvetica", 16, "bold"),
}

MONTH_NAMES = [
    "", "January", "February", "March",
    "April", "May", "June", "July",
    "August", "September", "October",
    "November", "December"
]


# ============================================================
# HELPERS
# ============================================================
def load_settings() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def round2(value) -> float:
    return float(
        Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
    )


class DBHelper:
    def __init__(self):
        self.db_path = DB_PATH

    def query(self, sql, params=()):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur  = conn.cursor()
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            print(f"[DB] {e}")
            return []

    def query_one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else {}

    def execute(self, sql, params=()):
        try:
            conn = sqlite3.connect(self.db_path)
            cur  = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            last_id = cur.lastrowid
            conn.close()
            return last_id
        except Exception as e:
            print(f"[DB] {e}")
            return None

    def execute_many(self, sql, params_list):
        try:
            conn = sqlite3.connect(self.db_path)
            cur  = conn.cursor()
            cur.executemany(sql, params_list)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[DB] {e}")
            return False


db = DBHelper()


# ============================================================
# BILL NUMBER MANAGER
# ============================================================
class BillNumberManager:
    """
    Manages sequential bill numbers.
    Never skips or repeats a number.

    Format: PREFIX-YEAR-NNNN
    Example: INV-2026-0001
    """

    def __init__(self, settings: dict):
        self.prefix = settings["billing"].get(
            "bill_prefix", "INV"
        )
        self.year   = date.today().year

    def get_next_number(self) -> str:
        """Get next bill number and increment tracker"""
        year = self.year

        # Get or create tracker row
        row = db.query_one("""
            SELECT last_number
            FROM bill_number_tracker
            WHERE prefix=? AND year=?
        """, (self.prefix, year))

        if row:
            last = row["last_number"]
            next_num = last + 1
            db.execute("""
                UPDATE bill_number_tracker
                SET last_number=?
                WHERE prefix=? AND year=?
            """, (next_num, self.prefix, year))
        else:
            # First bill of this year
            settings = load_settings()
            start = settings["billing"].get(
                "bill_start_number", 1
            )
            next_num = start
            db.execute("""
                INSERT INTO bill_number_tracker
                (prefix, year, last_number)
                VALUES (?,?,?)
            """, (self.prefix, year, next_num))

        return f"{self.prefix}-{year}-{next_num:04d}"

    def peek_next_number(self) -> str:
        """See what the next number will be (no increment)"""
        year = self.year
        row  = db.query_one("""
            SELECT last_number
            FROM bill_number_tracker
            WHERE prefix=? AND year=?
        """, (self.prefix, year))

        settings = load_settings()
        start    = settings["billing"].get(
            "bill_start_number", 1
        )

        last     = row["last_number"] if row else start - 1
        next_num = last + 1
        return f"{self.prefix}-{year}-{next_num:04d}"

    def rollback_number(self):
        """Roll back one number (if bill generation fails)"""
        year = self.year
        row  = db.query_one("""
            SELECT last_number
            FROM bill_number_tracker
            WHERE prefix=? AND year=?
        """, (self.prefix, year))

        if row and row["last_number"] > 0:
            db.execute("""
                UPDATE bill_number_tracker
                SET last_number = last_number - 1
                WHERE prefix=? AND year=?
            """, (self.prefix, year))


# ============================================================
# SMART BILL SPLITTING ALGORITHM
# ============================================================
class BillSplitter:
    """
    Core algorithm: splits purchase items into N sales bills.

    Algorithm:
    1. Pool all items from purchase bills
    2. For each of N bills:
       a. Randomly pick 1-5 items
       b. Assign random quantity (not exceeding remaining)
       c. Apply random margin within range
       d. Calculate selling price + GST
    3. After distributing, handle remaining quantities
       in last few bills
    4. Verify total sales = total purchases + margin
    5. Return list of bill dicts
    """

    def __init__(self, settings: dict):
        self.settings     = settings
        self.margin_type  = settings["billing"].get(
            "default_margin_type", "range"
        )
        self.margin_min   = settings["billing"].get(
            "default_margin_min", 10.0
        )
        self.margin_max   = settings["billing"].get(
            "default_margin_max", 20.0
        )
        self.margin_global = settings["billing"].get(
            "default_margin_global", 15.0
        )
        self.tax_scheme   = settings["billing"].get(
            "tax_scheme", "regular"
        )

    def get_purchase_pool(
        self, month: int, year: int
    ) -> list:
        """
        Get all purchase items for the month.
        Only items with remaining_qty > 0.
        """
        items = db.query("""
            SELECT
                pi.id           AS purchase_item_id,
                pi.item_name,
                pi.hsn_code,
                pi.unit,
                pi.purchase_rate,
                pi.gst_rate,
                pi.quantity     AS original_qty,
                pi.remaining_qty,
                pb.bill_month,
                pb.bill_year,
                pb.dealer_name
            FROM purchase_items pi
            JOIN purchase_bills pb
                ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_month = ?
            AND   pb.bill_year  = ?
            AND   pi.remaining_qty > 0
            ORDER BY pi.item_name
        """, (month, year))

        return items

    def get_margin_for_item(self) -> float:
        """Get margin % for one item based on settings"""
        if self.margin_type == "global":
            return self.margin_global
        elif self.margin_type == "range":
            # Random within range, rounded to 1 decimal
            margin = random.uniform(
                self.margin_min,
                self.margin_max
            )
            return round(margin, 1)
        else:
            # itemwise — use range as default
            return round(
                random.uniform(
                    self.margin_min,
                    self.margin_max
                ), 1
            )

    def calculate_selling_rate(
        self,
        purchase_rate: float,
        gst_rate: float,
        margin_pct: float
    ) -> tuple:
        """
        Calculate selling rate for COMPOSITION SCHEME.

        Formula (Composition / No-GST):
            selling_rate = purchase_rate + flat_markup
            (No GST is added on top — shop is on composition scheme)

        The flat_markup is stored in settings as
        billing.flat_markup_amount (default: 5).

        Returns:
            (selling_rate, gst_rate, cgst_rate, sgst_rate)
        """
        flat_markup = self.settings["billing"].get(
            "flat_markup_amount", 5.0
        )
        selling_rate = round2(purchase_rate + flat_markup)
        # Composition scheme — no GST charged to customer
        cgst_rate = 0.0
        sgst_rate = 0.0

        return selling_rate, 0.0, cgst_rate, sgst_rate

    def _get_working_days(
        self, month: int, year: int
    ) -> list:
        """
        Get list of working days in the month.
        Excludes Sundays (hardware shops usually open Sat).
        """
        import calendar

        _, days_in_month = calendar.monthrange(year, month)
        working_days = []

        for day in range(1, days_in_month + 1):
            d = date(year, month, day)
            # Exclude Sundays (weekday 6)
            if d.weekday() != 6:
                working_days.append(d)

        return working_days

    def _distribute_dates(
        self,
        n_bills: int,
        month: int,
        year: int
    ) -> list:
        """
        Distribute N bill dates across the month naturally.

        Strategy:
        - More bills mid-month and weekends
          (busy periods for hardware shops)
        - At least 1 day gap between consecutive dates
          for same volume
        - Random spread overall
        """
        working_days = self._get_working_days(month, year)

        if not working_days:
            # Fallback: first day of month
            return [date(year, month, 1)] * n_bills

        if n_bills <= len(working_days):
            # Sample without replacement for natural spread
            chosen = sorted(
                random.sample(working_days, n_bills)
            )
        else:
            # More bills than working days
            # Allow some days to have multiple bills
            chosen = sorted(
                random.choices(working_days, k=n_bills)
            )

        return chosen

    def split(
        self,
        month: int,
        year: int,
        n_bills: int,
        min_items_per_bill: int = 1,
        max_items_per_bill: int = 5,
        override_margin_type: str = None,
        override_margin_min:  float = None,
        override_margin_max:  float = None,
        override_margin_global: float = None,
    ) -> list:
        """
        Main splitting function.

        Args:
            month: Purchase month
            year:  Purchase year
            n_bills: Number of sales bills to generate
            min_items_per_bill: Min items per bill
            max_items_per_bill: Max items per bill
            override_*: Override margin settings

        Returns:
            List of bill dicts ready for preview/saving
            [
                {
                    "bill_date": date,
                    "customer": {...},
                    "items": [
                        {
                            "purchase_item_id": int,
                            "item_name": str,
                            "hsn_code": str,
                            "quantity": float,
                            "unit": str,
                            "purchase_rate": float,
                            "selling_rate": float,
                            "gst_rate": float,
                            "cgst_rate": float,
                            "sgst_rate": float,
                            "cgst_amount": float,
                            "sgst_amount": float,
                            "taxable_amount": float,
                            "total_amount": float,
                            "margin_pct": float,
                        }
                    ],
                    "subtotal": float,
                    "total_cgst": float,
                    "total_sgst": float,
                    "grand_total": float,
                    "bill_type": str,
                    "margin_avg": float,
                }
            ]
        """
        # Apply overrides
        if override_margin_type:
            self.margin_type = override_margin_type
        if override_margin_min is not None:
            self.margin_min = override_margin_min
        if override_margin_max is not None:
            self.margin_max = override_margin_max
        if override_margin_global is not None:
            self.margin_global = override_margin_global

        # Step 1: Get purchase pool
        pool = self.get_purchase_pool(month, year)
        if not pool:
            raise ValueError(
                "No purchase items found for this month.\n"
                "Add purchase bills first."
            )

        # Step 2: Create working copy of pool
        # (to track remaining quantities)
        working_pool = []
        for item in pool:
            working_pool.append({
                **item,
                "remaining": float(item["remaining_qty"])
            })

        # Step 3: Generate bill dates
        bill_dates = self._distribute_dates(
            n_bills, month, year
        )

        # Step 4: Get customer names
        from modules.customer_module import (
            KarnatakaNameGenerator
        )
        name_gen   = KarnatakaNameGenerator()
        name_gen.refresh_cache(month, year)
        customers  = name_gen.generate_batch(
            n_bills, month, year
        )

        # Step 5: Split items across bills
        bills = []

        for bill_idx in range(n_bills):
            # Available items (still have stock)
            available = [
                item for item in working_pool
                if item["remaining"] > 0
            ]

            if not available:
                break

            # Determine items for this bill
            is_last_bill = (
                bill_idx == n_bills - 1 or
                bill_idx == len(bills)
            )

            bill_items = self._pick_items_for_bill(
                available=available,
                working_pool=working_pool,
                bill_idx=bill_idx,
                n_bills=n_bills,
                min_items=min_items_per_bill,
                max_items=max_items_per_bill,
                is_last_bill=is_last_bill,
            )

            if not bill_items:
                continue

            # Calculate totals for this bill
            subtotal    = 0.0
            total_cgst  = 0.0
            total_sgst  = 0.0
            margins_used = []

            for bi in bill_items:
                subtotal   += bi["taxable_amount"]
                total_cgst += bi["cgst_amount"]
                total_sgst += bi["sgst_amount"]
                margins_used.append(bi["margin_pct"])

            grand_total = round2(
                subtotal + total_cgst + total_sgst
            )
            avg_margin  = (
                round(
                    sum(margins_used) / len(margins_used),
                    1
                )
                if margins_used else 0
            )

            # Get customer
            customer_name = (
                customers[bill_idx]
                if bill_idx < len(customers)
                else name_gen.generate_name(month, year)
            )
            city = name_gen.get_city()

            bills.append({
                "bill_date":   bill_dates[bill_idx]
                               if bill_idx < len(bill_dates)
                               else date(year, month, 1),
                "customer": {
                    "name":    customer_name,
                    "city":    city,
                    "phone":   "",
                    "address": "",
                },
                "items":       bill_items,
                "subtotal":    round2(subtotal),
                "total_cgst":  round2(total_cgst),
                "total_sgst":  round2(total_sgst),
                "grand_total": grand_total,
                "bill_type":   self.tax_scheme,
                "margin_avg":  avg_margin,
            })

        # Step 6: Handle any remaining stock
        # Add to last bill as balancing
        remaining_items = [
            item for item in working_pool
            if item["remaining"] > 0.001
        ]

        if remaining_items and bills:
            last_bill = bills[-1]
            for rem_item in remaining_items:
                if rem_item["remaining"] > 0.001:
                    margin = self.get_margin_for_item()
                    sell_rate, gst_r, cgst_r, sgst_r = \
                        self.calculate_selling_rate(
                            rem_item["purchase_rate"],
                            rem_item["gst_rate"],
                            margin
                        )
                    qty     = round(
                        rem_item["remaining"], 3
                    )
                    taxable = round2(qty * sell_rate)
                    cgst    = round2(taxable * cgst_r / 100)
                    sgst    = round2(taxable * sgst_r / 100)
                    total   = round2(taxable + cgst + sgst)

                    last_bill["items"].append({
                        "purchase_item_id":
                            rem_item["purchase_item_id"],
                        "item_name":
                            rem_item["item_name"],
                        "hsn_code":
                            rem_item["hsn_code"],
                        "quantity":    qty,
                        "unit":        rem_item["unit"],
                        "purchase_rate":
                            rem_item["purchase_rate"],
                        "selling_rate": sell_rate,
                        "gst_rate":    gst_r,
                        "cgst_rate":   cgst_r,
                        "sgst_rate":   sgst_r,
                        "cgst_amount": cgst,
                        "sgst_amount": sgst,
                        "taxable_amount": taxable,
                        "total_amount": total,
                        "margin_pct":  margin,
                    })
                    rem_item["remaining"] = 0

            # Recalculate last bill totals
            last_bill["subtotal"]    = round2(sum(
                i["taxable_amount"]
                for i in last_bill["items"]
            ))
            last_bill["total_cgst"]  = round2(sum(
                i["cgst_amount"]
                for i in last_bill["items"]
            ))
            last_bill["total_sgst"]  = round2(sum(
                i["sgst_amount"]
                for i in last_bill["items"]
            ))
            last_bill["grand_total"] = round2(
                last_bill["subtotal"] +
                last_bill["total_cgst"] +
                last_bill["total_sgst"]
            )

        return bills

    def _pick_items_for_bill(
        self,
        available:   list,
        working_pool: list,
        bill_idx:    int,
        n_bills:     int,
        min_items:   int,
        max_items:   int,
        is_last_bill: bool,
    ) -> list:
        """
        Pick items and quantities for one sales bill.

        Strategy:
        - Random number of items (min to max)
        - For each item: random portion of remaining qty
        - Last bill gets all remaining quantities
        - Quantities are realistic
          (not too small, not all at once)
        """
        bill_items = []

        if is_last_bill:
            # Last bill — take ALL remaining
            for item in working_pool:
                if item["remaining"] > 0.001:
                    margin    = self.get_margin_for_item()
                    sell_rate, gst_r, cgst_r, sgst_r = \
                        self.calculate_selling_rate(
                            item["purchase_rate"],
                            item["gst_rate"],
                            margin
                        )
                    qty     = round(item["remaining"], 3)
                    taxable = round2(qty * sell_rate)
                    cgst    = round2(
                        taxable * cgst_r / 100
                    )
                    sgst    = round2(
                        taxable * sgst_r / 100
                    )

                    bill_items.append({
                        "purchase_item_id":
                            item["purchase_item_id"],
                        "item_name":  item["item_name"],
                        "hsn_code":   item["hsn_code"],
                        "quantity":   qty,
                        "unit":       item["unit"],
                        "purchase_rate":
                            item["purchase_rate"],
                        "selling_rate": sell_rate,
                        "gst_rate":   gst_r,
                        "cgst_rate":  cgst_r,
                        "sgst_rate":  sgst_r,
                        "cgst_amount": cgst,
                        "sgst_amount": sgst,
                        "taxable_amount":
                            round2(qty * sell_rate),
                        "total_amount":
                            round2(taxable + cgst + sgst),
                        "margin_pct": margin,
                    })
                    item["remaining"] = 0

            return bill_items

        # Normal bill — pick random items and quantities
        # How many items for this bill?
        n_items = random.randint(
            min(min_items, len(available)),
            min(max_items, len(available))
        )

        # Shuffle and pick n_items
        shuffled = available.copy()
        random.shuffle(shuffled)
        chosen_items = shuffled[:n_items]

        # Bills remaining after this one
        bills_left = n_bills - bill_idx

        for item in chosen_items:
            if item["remaining"] < 0.001:
                continue

            # What fraction of remaining to use?
            # Strategy: if many bills left, use smaller portion
            # If few bills left, use more
            if bills_left <= 1:
                fraction = 1.0
            elif bills_left <= 3:
                # Use 30-70% of remaining
                fraction = random.uniform(0.3, 0.7)
            else:
                # Use 10-40% of remaining
                fraction = random.uniform(0.1, 0.4)

            raw_qty = item["remaining"] * fraction

            # Round quantity to realistic values
            qty = self._round_quantity(
                raw_qty, item["unit"]
            )

            # Ensure at least minimum meaningful quantity
            qty = max(qty, self._min_qty(item["unit"]))

            # Ensure not exceeding remaining
            qty = min(qty, item["remaining"])

            if qty < 0.001:
                continue

            # Calculate prices
            margin    = self.get_margin_for_item()
            sell_rate, gst_r, cgst_r, sgst_r = \
                self.calculate_selling_rate(
                    item["purchase_rate"],
                    item["gst_rate"],
                    margin
                )

            taxable = round2(qty * sell_rate)
            cgst    = round2(taxable * cgst_r / 100)
            sgst    = round2(taxable * sgst_r / 100)
            total   = round2(taxable + cgst + sgst)

            bill_items.append({
                "purchase_item_id":
                    item["purchase_item_id"],
                "item_name":  item["item_name"],
                "hsn_code":   item["hsn_code"],
                "quantity":   qty,
                "unit":       item["unit"],
                "purchase_rate":
                    item["purchase_rate"],
                "selling_rate": sell_rate,
                "gst_rate":   gst_r,
                "cgst_rate":  cgst_r,
                "sgst_rate":  sgst_r,
                "cgst_amount": cgst,
                "sgst_amount": sgst,
                "taxable_amount": taxable,
                "total_amount":   total,
                "margin_pct":    margin,
            })

            # Deduct from pool
            item["remaining"] -= qty

        return bill_items

    def _round_quantity(
        self, qty: float, unit: str
    ) -> float:
        """
        Round quantity to realistic values per unit type.
        """
        unit_lower = unit.lower()

        if unit_lower in ("piece", "pcs", "nos"):
            # Round to whole numbers
            return max(1, round(qty))

        elif unit_lower in ("kg", "kilogram"):
            if qty >= 10:
                return round(qty / 5) * 5  # nearest 5kg
            elif qty >= 1:
                return round(qty, 1)  # 1 decimal
            else:
                return round(qty, 2)

        elif unit_lower in ("meter", "metre", "mtr"):
            if qty >= 10:
                return round(qty / 2) * 2  # nearest 2m
            elif qty >= 1:
                return round(qty, 1)
            else:
                return round(qty, 2)

        elif unit_lower in ("liter", "litre", "ltr"):
            if qty >= 5:
                return round(qty / 5) * 5  # nearest 5L
            elif qty >= 1:
                return round(qty, 1)
            else:
                return round(qty, 2)

        elif unit_lower in ("bag", "bags"):
            return max(1, round(qty))

        else:
            # Default: 2 decimal places
            return round(qty, 2)

    def _min_qty(self, unit: str) -> float:
        """Minimum meaningful quantity per unit"""
        unit_lower = unit.lower()
        mins = {
            "piece": 1.0, "pcs": 1.0, "nos": 1.0,
            "kg": 0.5,    "kilogram": 0.5,
            "meter": 0.5, "metre": 0.5,  "mtr": 0.5,
            "liter": 0.5, "litre": 0.5,  "ltr": 0.5,
            "bag":   1.0, "bags": 1.0,
        }
        return mins.get(unit_lower, 1.0)

    def verify_tally(
        self,
        month: int,
        year: int,
        generated_bills: list
    ) -> dict:
        """
        Verify that generated bills account for
        all purchased items.

        Returns tally report dict.
        """
        # Purchase totals
        p = db.query_one("""
            SELECT
                COALESCE(SUM(subtotal),    0) AS p_taxable,
                COALESCE(SUM(total_gst),   0) AS p_gst,
                COALESCE(SUM(grand_total), 0) AS p_total
            FROM purchase_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        # Generated bills totals
        s_taxable  = sum(
            b["subtotal"] for b in generated_bills
        )
        s_cgst     = sum(
            b["total_cgst"] for b in generated_bills
        )
        s_sgst     = sum(
            b["total_sgst"] for b in generated_bills
        )
        s_total    = sum(
            b["grand_total"] for b in generated_bills
        )
        s_gst      = s_cgst + s_sgst

        # Item tally
        purchase_items = db.query("""
            SELECT
                pi.item_name,
                pi.unit,
                SUM(pi.quantity) AS total_purchased
            FROM purchase_items pi
            JOIN purchase_bills pb
                ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_month=? AND pb.bill_year=?
            GROUP BY pi.item_name, pi.unit
        """, (month, year))

        # Count items in generated bills
        item_totals = defaultdict(float)
        for bill in generated_bills:
            for item in bill["items"]:
                key = item["item_name"].lower()
                item_totals[key] += item["quantity"]

        # Compare
        item_tally = []
        all_tallied = True

        for pi in purchase_items:
            key       = pi["item_name"].lower()
            purchased = pi["total_purchased"]
            sold      = item_totals.get(key, 0)
            diff      = round(purchased - sold, 3)
            ok        = abs(diff) < 0.01

            if not ok:
                all_tallied = False

            item_tally.append({
                "item_name": pi["item_name"],
                "unit":      pi["unit"],
                "purchased": purchased,
                "sold":      round(sold, 3),
                "diff":      diff,
                "ok":        ok,
            })

        profit     = round2(
            s_taxable - p["p_taxable"]
        )
        gst_payable = round2(
            max(0, s_gst - p["p_gst"])
        )

        return {
            "purchase_taxable": p["p_taxable"],
            "purchase_gst":     p["p_gst"],
            "purchase_total":   p["p_total"],
            "sales_taxable":    round2(s_taxable),
            "sales_gst":        round2(s_gst),
            "sales_cgst":       round2(s_cgst),
            "sales_sgst":       round2(s_sgst),
            "sales_total":      round2(s_total),
            "profit":           profit,
            "gst_payable":      gst_payable,
            "all_items_tallied": all_tallied,
            "item_tally":       item_tally,
            "bills_count":      len(generated_bills),
        }


# ============================================================
# BILL PREVIEW DIALOG
# ============================================================
class BillPreviewDialog(tk.Toplevel):
    """
    Shows all generated bills for review before saving.

    Layout:
    ┌─────────────────────────────────────────────┐
    │  Title + Tally Summary                      │
    ├────────────────┬────────────────────────────┤
    │  Bill List     │  Selected Bill Detail      │
    │  (left panel)  │  (right panel)             │
    │                │                            │
    │  Bill #1  ₹XXX │  Customer: Ramesh Gowda    │
    │  Bill #2  ₹XXX │  Date: 15/06/2026          │
    │  ...           │  Items table               │
    │                │  Totals                    │
    ├────────────────┴────────────────────────────┤
    │  [Regenerate]  [Cancel]  [✅ Save All Bills] │
    └─────────────────────────────────────────────┘
    """

    def __init__(
        self,
        parent,
        bills: list,
        tally: dict,
        month: int,
        year: int,
        on_confirm_callback,
        on_regenerate_callback,
    ):
        super().__init__(parent)
        self.bills       = bills
        self.tally       = tally
        self.month       = month
        self.year        = year
        self.on_confirm  = on_confirm_callback
        self.on_regen    = on_regenerate_callback

        self.title(
            f"Preview — {len(bills)} Sales Bills — "
            f"{MONTH_NAMES[month]} {year}"
        )
        self.geometry("1200x780")
        self.resizable(True, True)
        self.configure(bg=COLORS["bg_main"])
        self.grab_set()

        self.selected_bill_idx = tk.IntVar(value=0)

        self._build_ui()
        self._show_bill(0)

    # ----------------------------------------------------------
    # BUILD UI
    # ----------------------------------------------------------
    def _build_ui(self):
        # Header with tally summary
        self._build_header()

        # Main content
        content = tk.Frame(self, bg=COLORS["bg_main"])
        content.pack(
            fill="both", expand=True,
            padx=10, pady=5
        )

        # Left — bill list
        left = tk.Frame(
            content,
            bg=COLORS["bg_card"],
            width=280
        )
        left.pack(
            side="left", fill="y",
            padx=(0, 5)
        )
        left.pack_propagate(False)
        self._build_bill_list(left)

        # Right — bill detail
        right = tk.Frame(
            content,
            bg=COLORS["bg_main"]
        )
        right.pack(
            side="left",
            fill="both",
            expand=True
        )
        self._build_bill_detail(right)

        # Footer buttons
        self._build_footer()

    def _build_header(self):
        """Tally summary header"""
        t = self.tally

        hdr = tk.Frame(self, bg=COLORS["primary"], pady=10)
        hdr.pack(fill="x")

        tk.Label(
            hdr,
            text=f"📋 Bill Preview — "
                 f"{MONTH_NAMES[self.month]} {self.year}",
            font=FONTS["subheading"],
            bg=COLORS["primary"],
            fg="white"
        ).pack(side="left", padx=15)

        # Tally numbers
        nums_frame = tk.Frame(
            hdr, bg=COLORS["primary"]
        )
        nums_frame.pack(side="right", padx=15)

        tally_ok = t.get("all_items_tallied", False)
        tally_color = "#a5d6a7" if tally_ok else "#ffcc80"
        tally_text  = "✅ TALLIED" if tally_ok else "⚠️ CHECK"

        for label, value, color in [
            ("Purchase Total",
             f"₹{t['purchase_total']:,.2f}",
             "#90caf9"),
            ("Sales Total",
             f"₹{t['sales_total']:,.2f}",
             "#a5d6a7"),
            ("Profit",
             f"₹{t['profit']:,.2f}",
             "#ffcc80"),
            ("GST Payable",
             f"₹{t['gst_payable']:,.2f}",
             "#ce93d8"),
            ("Tally",
             tally_text,
             tally_color),
        ]:
            box = tk.Frame(
                nums_frame,
                bg=COLORS["primary_light"],
                padx=12, pady=5
            )
            box.pack(side="left", padx=4)

            tk.Label(
                box,
                text=label,
                font=FONTS["small"],
                bg=COLORS["primary_light"],
                fg="#e0e0e0"
            ).pack()

            tk.Label(
                box,
                text=value,
                font=FONTS["label_bold"],
                bg=COLORS["primary_light"],
                fg=color
            ).pack()

    def _build_bill_list(self, parent):
        """Left panel: list of all generated bills"""
        tk.Label(
            parent,
            text=f"📄 {len(self.bills)} Bills",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            pady=8
        ).pack(fill="x", padx=10)

        tk.Frame(
            parent, bg=COLORS["border"], height=1
        ).pack(fill="x")

        # Scrollable list
        canvas = tk.Canvas(
            parent,
            bg=COLORS["bg_card"],
            highlightthickness=0
        )
        sb = ttk.Scrollbar(
            parent,
            orient="vertical",
            command=canvas.yview
        )
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        list_frame = tk.Frame(
            canvas, bg=COLORS["bg_card"]
        )
        cw = canvas.create_window(
            (0, 0),
            window=list_frame,
            anchor="nw"
        )

        list_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(
                cw, width=e.width
            )
        )

        # Render bill items
        self.list_buttons = []
        for i, bill in enumerate(self.bills):
            self._render_list_item(
                list_frame, i, bill
            )

    def _render_list_item(
        self, parent, idx: int, bill: dict
    ):
        """Render one bill in the left list"""
        frame = tk.Frame(
            parent,
            bg=COLORS["bg_card"],
            cursor="hand2"
        )
        frame.pack(fill="x", pady=1)

        # Click to select
        def on_click(e, i=idx):
            self._show_bill(i)
            self._highlight_list_item(i)

        date_str = bill["bill_date"].strftime(
            "%d/%m"
        ) if isinstance(
            bill["bill_date"], date
        ) else str(bill["bill_date"])

        # Bill row content
        inner = tk.Frame(
            frame,
            bg=COLORS["bg_card"],
            padx=10, pady=6
        )
        inner.pack(fill="x")

        top_row = tk.Frame(inner, bg=COLORS["bg_card"])
        top_row.pack(fill="x")

        tk.Label(
            top_row,
            text=f"Bill #{idx + 1}",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["primary"]
        ).pack(side="left")

        tk.Label(
            top_row,
            text=date_str,
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        ).pack(side="right")

        bot_row = tk.Frame(inner, bg=COLORS["bg_card"])
        bot_row.pack(fill="x")

        cust_name = bill["customer"]["name"]
        # Truncate long names
        if len(cust_name) > 20:
            cust_name = cust_name[:18] + "..."

        tk.Label(
            bot_row,
            text=cust_name,
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Label(
            bot_row,
            text=f"₹{bill['grand_total']:,.0f}",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["success"]
        ).pack(side="right")

        # Separator
        tk.Frame(
            frame, bg=COLORS["border"], height=1
        ).pack(fill="x")

        # Bind clicks
        for widget in [frame, inner, top_row, bot_row]:
            widget.bind("<Button-1>", on_click)
            for child in widget.winfo_children():
                child.bind("<Button-1>", on_click)

        self.list_buttons.append(
            (frame, inner)
        )

    def _highlight_list_item(self, idx: int):
        """Highlight selected bill in list"""
        for i, (frame, inner) in enumerate(
            self.list_buttons
        ):
            if i == idx:
                for w in [frame, inner]:
                    w.configure(
                        bg=COLORS["primary_light"]
                    )
                for widget in inner.winfo_children():
                    try:
                        widget.configure(
                            bg=COLORS["primary_light"],
                            fg="white"
                        )
                    except Exception:
                        pass
            else:
                for w in [frame, inner]:
                    w.configure(bg=COLORS["bg_card"])
                for widget in inner.winfo_children():
                    try:
                        widget.configure(
                            bg=COLORS["bg_card"]
                        )
                    except Exception:
                        pass

    def _build_bill_detail(self, parent):
        """Right panel: selected bill details"""
        # Title
        self.detail_title = tk.Label(
            parent,
            text="Select a bill from the left",
            font=FONTS["subheading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        )
        self.detail_title.pack(
            anchor="w", padx=10, pady=(5, 0)
        )

        # Customer + date row
        self.detail_meta = tk.Frame(
            parent, bg=COLORS["bg_card"],
            padx=15, pady=8
        )
        self.detail_meta.pack(
            fill="x", padx=10, pady=5
        )

        # Items table
        table_frame = tk.Frame(
            parent, bg=COLORS["bg_main"]
        )
        table_frame.pack(
            fill="both", expand=True,
            padx=10, pady=5
        )

        # Items table header
        hdr = tk.Frame(
            table_frame, bg=COLORS["header_bg"]
        )
        hdr.pack(fill="x")

        for col, width in [
            ("Item Name",   25), ("HSN",     8),
            ("Qty",          8), ("Unit",     7),
            ("Buy Rate",    10), ("Sell Rate",10),
            ("Margin%",      8), ("CGST",     8),
            ("SGST",         8), ("Total",   12),
        ]:
            tk.Label(
                hdr,
                text=col,
                font=FONTS["table_bold"],
                bg=COLORS["header_bg"],
                fg="white",
                width=width,
                anchor="w",
                padx=4, pady=6
            ).pack(side="left")

        # Scrollable items body
        body_outer = tk.Frame(
            table_frame,
            bg=COLORS["bg_card"],
            relief="solid", bd=1
        )
        body_outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            body_outer,
            bg=COLORS["bg_card"],
            highlightthickness=0
        )
        sb = ttk.Scrollbar(
            body_outer,
            orient="vertical",
            command=canvas.yview
        )
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(
            side="left", fill="both", expand=True
        )

        self.detail_body = tk.Frame(
            canvas, bg=COLORS["bg_card"]
        )
        cw = canvas.create_window(
            (0, 0),
            window=self.detail_body,
            anchor="nw"
        )

        self.detail_body.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(
                cw, width=e.width
            )
        )

        # Totals footer
        self.detail_totals = tk.Frame(
            parent,
            bg=COLORS["bg_card"],
            padx=15, pady=8
        )
        self.detail_totals.pack(
            fill="x", padx=10, pady=(0, 5)
        )

    def _show_bill(self, idx: int):
        """Display selected bill details"""
        if idx < 0 or idx >= len(self.bills):
            return

        bill = self.bills[idx]
        self.selected_bill_idx.set(idx)

        # Update title
        self.detail_title.configure(
            text=f"Bill #{idx + 1} — "
                 f"{bill['customer']['name']}"
        )

        # Clear and update meta
        for w in self.detail_meta.winfo_children():
            w.destroy()

        date_str = bill["bill_date"].strftime(
            "%d %B %Y"
        ) if isinstance(
            bill["bill_date"], date
        ) else str(bill["bill_date"])

        meta_items = [
            ("👤 Customer",
             bill["customer"]["name"],
             COLORS["primary"]),
            ("📅 Date", date_str,
             COLORS["text_dark"]),
            ("🏙️ City",
             bill["customer"].get("city", ""),
             COLORS["text_muted"]),
            ("📊 Margin Avg",
             f"{bill['margin_avg']:.1f}%",
             COLORS["success"]),
            ("🧾 Type",
             bill["bill_type"].title(),
             COLORS["accent"]),
        ]

        for label, value, color in meta_items:
            box = tk.Frame(
                self.detail_meta,
                bg=COLORS["bg_card"]
            )
            box.pack(side="left", padx=(0, 20))

            tk.Label(
                box,
                text=label,
                font=FONTS["small"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(anchor="w")

            tk.Label(
                box,
                text=value,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=color
            ).pack(anchor="w")

        # Clear and populate items
        for w in self.detail_body.winfo_children():
            w.destroy()

        for i, item in enumerate(bill["items"]):
            bg = (COLORS["row_even"]
                  if i % 2 == 0
                  else COLORS["row_odd"])
            row = tk.Frame(self.detail_body, bg=bg)
            row.pack(fill="x")

            for text, width in [
                (item["item_name"],             25),
                (item["hsn_code"] or "-",        8),
                (f"{item['quantity']:.2f}",       8),
                (item["unit"],                    7),
                (f"₹{item['purchase_rate']:.2f}",10),
                (f"₹{item['selling_rate']:.2f}", 10),
                (f"{item['margin_pct']:.1f}%",    8),
                (f"₹{item['cgst_amount']:.2f}",   8),
                (f"₹{item['sgst_amount']:.2f}",   8),
                (f"₹{item['total_amount']:.2f}", 12),
            ]:
                tk.Label(
                    row,
                    text=text,
                    font=FONTS["table"],
                    bg=bg,
                    fg=COLORS["text_dark"],
                    width=width,
                    anchor="w",
                    padx=4, pady=5
                ).pack(side="left")

        # Update totals
        for w in self.detail_totals.winfo_children():
            w.destroy()

        for label, value, color in [
            ("Taxable Amount",
             f"₹{bill['subtotal']:,.2f}",
             COLORS["text_dark"]),
            ("CGST",
             f"₹{bill['total_cgst']:,.2f}",
             COLORS["warning"]),
            ("SGST",
             f"₹{bill['total_sgst']:,.2f}",
             COLORS["warning"]),
            ("Grand Total",
             f"₹{bill['grand_total']:,.2f}",
             COLORS["success"]),
        ]:
            col = tk.Frame(
                self.detail_totals,
                bg=COLORS["bg_card"]
            )
            col.pack(side="right", padx=15)

            tk.Label(
                col,
                text=label,
                font=FONTS["small"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(anchor="e")

            tk.Label(
                col,
                text=value,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=color
            ).pack(anchor="e")

        # Highlight in list
        self._highlight_list_item(idx)

    def _build_footer(self):
        """Action buttons footer"""
        footer = tk.Frame(
            self, bg=COLORS["bg_card"], pady=12
        )
        footer.pack(fill="x", padx=10)

        # Left — info
        tk.Label(
            footer,
            text=f"✅ {len(self.bills)} bills generated  |  "
                 f"Review each bill before saving.",
            font=FONTS["label"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        ).pack(side="left", padx=15)

        # Right — buttons
        btn_row = tk.Frame(footer, bg=COLORS["bg_card"])
        btn_row.pack(side="right", padx=10)

        tk.Button(
            btn_row,
            text="🔄 Regenerate",
            font=FONTS["button"],
            bg=COLORS["warning"],
            fg="white",
            relief="flat",
            padx=15, pady=8,
            cursor="hand2",
            command=self._regenerate
        ).pack(side="left", padx=5)

        tk.Button(
            btn_row,
            text="✕ Cancel",
            font=FONTS["button"],
            bg=COLORS["text_muted"],
            fg="white",
            relief="flat",
            padx=15, pady=8,
            cursor="hand2",
            command=self.destroy
        ).pack(side="left", padx=5)

        tk.Button(
            btn_row,
            text="💾 Save All Bills",
            font=FONTS["button"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=20, pady=8,
            cursor="hand2",
            command=self._confirm_save
        ).pack(side="left", padx=5)

    def _regenerate(self):
        """Close and trigger regeneration"""
        self.destroy()
        if self.on_regen:
            self.on_regen()

    def _confirm_save(self):
        """Confirm and save all bills"""
        if not messagebox.askyesno(
            "Confirm Save",
            f"Save {len(self.bills)} sales bills?\n\n"
            f"Month: {MONTH_NAMES[self.month]} "
            f"{self.year}\n"
            f"Total: ₹{self.tally['sales_total']:,.2f}\n"
            f"Profit: ₹{self.tally['profit']:,.2f}\n\n"
            "This will deduct quantities from\n"
            "purchase pool. Continue?"
        ):
            return

        self.destroy()
        if self.on_confirm:
            self.on_confirm(self.bills)


# ============================================================
# SALES FRAME — MAIN VIEW
# ============================================================
class SalesFrame(tk.Frame):
    """
    Sales bills main view.

    Layout:
    ┌──────────────────────────────────────────┐
    │  Title            Month/Year filter      │
    ├──────────────────────────────────────────┤
    │  LEFT: Generate Panel                    │
    │  - Purchase pool summary                 │
    │  - Split configuration                   │
    │  - [Generate Bills] button               │
    ├──────────────────────────────────────────┤
    │  RIGHT: Existing sales bills this month  │
    └──────────────────────────────────────────┘
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS["bg_main"])
        self.app      = app
        self.settings = load_settings()

        today = date.today()
        self.filter_month = tk.IntVar(value=today.month)
        self.filter_year  = tk.IntVar(value=today.year)

        # Split configuration vars
        self.var_n_bills      = tk.IntVar(value=10)
        self.var_min_items    = tk.IntVar(value=1)
        self.var_max_items    = tk.IntVar(value=5)
        self.var_margin_type  = tk.StringVar(
            value=self.settings["billing"].get(
                "default_margin_type", "range"
            )
        )
        self.var_margin_min   = tk.DoubleVar(
            value=self.settings["billing"].get(
                "default_margin_min", 10.0
            )
        )
        self.var_margin_max   = tk.DoubleVar(
            value=self.settings["billing"].get(
                "default_margin_max", 20.0
            )
        )
        self.var_margin_global = tk.DoubleVar(
            value=self.settings["billing"].get(
                "default_margin_global", 15.0
            )
        )
        self.var_bill_type = tk.StringVar(
            value=self.settings["billing"].get(
                "tax_scheme", "regular"
            )
        )

        # Pending generated bills (not yet saved)
        self.pending_bills = []

        self._build_ui()
        self._load_data()

    # ----------------------------------------------------------
    # BUILD UI
    # ----------------------------------------------------------
    def _build_ui(self):
        self._build_top_bar()

        # Main content — scrollable
        outer = tk.Frame(self, bg=COLORS["bg_main"])
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            outer,
            bg=COLORS["bg_main"],
            highlightthickness=0
        )
        sb = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=canvas.yview
        )
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(
            side="left", fill="both", expand=True
        )

        self.scroll_frame = tk.Frame(
            canvas, bg=COLORS["bg_main"]
        )
        cw = canvas.create_window(
            (0, 0),
            window=self.scroll_frame,
            anchor="nw"
        )

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(
                cw, width=e.width
            )
        )
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"
            )
        )

        # Two column layout
        cols = tk.Frame(
            self.scroll_frame, bg=COLORS["bg_main"]
        )
        cols.pack(
            fill="both", expand=True,
            padx=20, pady=10
        )

        # Left — generate panel
        left = tk.Frame(
            cols, bg=COLORS["bg_main"],
            width=420
        )
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)
        self._build_generate_panel(left)

        # Right — existing bills
        right = tk.Frame(cols, bg=COLORS["bg_main"])
        right.pack(
            side="left", fill="both", expand=True
        )
        self._build_existing_bills(right)

    def _build_top_bar(self):
        top = tk.Frame(self, bg=COLORS["bg_main"])
        top.pack(fill="x", padx=25, pady=(20, 5))

        tk.Label(
            top,
            text="📤  Sales Bills",
            font=FONTS["heading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        # Right — filter
        right = tk.Frame(top, bg=COLORS["bg_main"])
        right.pack(side="right")

        tk.Label(
            right,
            text="Month:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(0, 5))

        month_cb = ttk.Combobox(
            right,
            values=MONTH_NAMES[1:],
            width=11,
            font=FONTS["body"],
            state="readonly"
        )
        month_cb.set(
            MONTH_NAMES[self.filter_month.get()]
        )
        month_cb.pack(side="left", padx=3)
        month_cb.bind(
            "<<ComboboxSelected>>",
            lambda e: self._on_filter_change(
                month_cb.get(), None
            )
        )

        current_year = date.today().year
        year_cb = ttk.Combobox(
            right,
            values=[str(y) for y in range(
                current_year - 3,
                current_year + 2
            )],
            width=7,
            font=FONTS["body"],
            state="readonly"
        )
        year_cb.set(str(self.filter_year.get()))
        year_cb.pack(side="left", padx=3)
        year_cb.bind(
            "<<ComboboxSelected>>",
            lambda e: self._on_filter_change(
                None, year_cb.get()
            )
        )

        self.month_cb = month_cb
        self.year_cb  = year_cb

    def _on_filter_change(self, month_name, year_str):
        if month_name:
            self.filter_month.set(
                MONTH_NAMES.index(month_name)
            )
        if year_str:
            self.filter_year.set(int(year_str))
        self._load_data()

    # ----------------------------------------------------------
    # GENERATE PANEL
    # ----------------------------------------------------------
    def _build_generate_panel(self, parent):
        """Left panel: purchase pool + split config"""

        # ---- Purchase Pool Summary ----
        pool_card = tk.Frame(
            parent,
            bg=COLORS["bg_card"],
            padx=15, pady=12
        )
        pool_card.pack(fill="x", pady=(0, 8))

        tk.Label(
            pool_card,
            text="📦 Purchase Pool (This Month)",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 5))

        self.pool_info_frame = tk.Frame(
            pool_card, bg=COLORS["bg_card"]
        )
        self.pool_info_frame.pack(fill="x")

        # ---- Split Configuration ----
        config_card = tk.Frame(
            parent,
            bg=COLORS["bg_card"],
            padx=15, pady=12
        )
        config_card.pack(fill="x", pady=(0, 8))

        tk.Label(
            config_card,
            text="⚙️ Split Configuration",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 10))

        # Number of bills
        row1 = tk.Frame(
            config_card, bg=COLORS["bg_card"]
        )
        row1.pack(fill="x", pady=4)

        tk.Label(
            row1,
            text="Number of Sales Bills:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            width=25,
            anchor="w"
        ).pack(side="left")

        tk.Spinbox(
            row1,
            from_=1, to=100,
            textvariable=self.var_n_bills,
            font=FONTS["body"],
            width=6,
            relief="solid", bd=1
        ).pack(side="left")

        # Items per bill range
        row2 = tk.Frame(
            config_card, bg=COLORS["bg_card"]
        )
        row2.pack(fill="x", pady=4)

        tk.Label(
            row2,
            text="Items per Bill (Min):",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            width=25, anchor="w"
        ).pack(side="left")

        tk.Spinbox(
            row2,
            from_=1, to=10,
            textvariable=self.var_min_items,
            font=FONTS["body"],
            width=4,
            relief="solid", bd=1
        ).pack(side="left")

        tk.Label(
            row2,
            text="Max:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(10, 5))

        tk.Spinbox(
            row2,
            from_=1, to=20,
            textvariable=self.var_max_items,
            font=FONTS["body"],
            width=4,
            relief="solid", bd=1
        ).pack(side="left")

        # Bill type (GST scheme)
        row3 = tk.Frame(
            config_card, bg=COLORS["bg_card"]
        )
        row3.pack(fill="x", pady=4)

        tk.Label(
            row3,
            text="Bill Type:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            width=25, anchor="w"
        ).pack(side="left")

        for val, lbl in [
            ("regular",     "Regular GST"),
            ("composition", "Composition"),
        ]:
            tk.Radiobutton(
                row3,
                text=lbl,
                variable=self.var_bill_type,
                value=val,
                font=FONTS["label"],
                bg=COLORS["bg_card"],
                activebackground=COLORS["bg_card"]
            ).pack(side="left", padx=(0, 10))

        # Margin settings
        margin_frame = tk.Frame(
            config_card,
            bg="#f0f4ff",
            padx=10, pady=8
        )
        margin_frame.pack(fill="x", pady=8)

        tk.Label(
            margin_frame,
            text="💰 Profit Margin Settings",
            font=FONTS["label_bold"],
            bg="#f0f4ff",
            fg=COLORS["primary"]
        ).pack(anchor="w", pady=(0, 6))

        # Margin type
        for val, lbl in [
            ("range",    "Random Range (Recommended)"),
            ("global",   "Fixed Global %"),
            ("itemwise", "Item-wise (uses range)"),
        ]:
            tk.Radiobutton(
                margin_frame,
                text=lbl,
                variable=self.var_margin_type,
                value=val,
                font=FONTS["small"],
                bg="#f0f4ff",
                activebackground="#f0f4ff",
                command=self._on_margin_type_change
            ).pack(anchor="w", pady=1)

        # Range inputs
        self.range_inputs = tk.Frame(
            margin_frame, bg="#f0f4ff"
        )
        self.range_inputs.pack(fill="x", pady=4)

        tk.Label(
            self.range_inputs,
            text="Min %:",
            font=FONTS["small"],
            bg="#f0f4ff",
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Entry(
            self.range_inputs,
            textvariable=self.var_margin_min,
            font=FONTS["body"],
            width=6,
            relief="solid", bd=1
        ).pack(side="left", padx=3)

        tk.Label(
            self.range_inputs,
            text="Max %:",
            font=FONTS["small"],
            bg="#f0f4ff",
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(8, 0))

        tk.Entry(
            self.range_inputs,
            textvariable=self.var_margin_max,
            font=FONTS["body"],
            width=6,
            relief="solid", bd=1
        ).pack(side="left", padx=3)

        # Global input
        self.global_input = tk.Frame(
            margin_frame, bg="#f0f4ff"
        )
        self.global_input.pack(fill="x", pady=4)

        tk.Label(
            self.global_input,
            text="Global Margin %:",
            font=FONTS["small"],
            bg="#f0f4ff",
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Entry(
            self.global_input,
            textvariable=self.var_margin_global,
            font=FONTS["body"],
            width=6,
            relief="solid", bd=1
        ).pack(side="left", padx=3)

        self._on_margin_type_change()

        # ---- Generate Button ----
        tk.Button(
            parent,
            text="⚡ Generate Sales Bills",
            font=FONTS["button"],
            bg=COLORS["accent"],
            fg="white",
            relief="flat",
            padx=20, pady=12,
            cursor="hand2",
            command=self._generate_bills
        ).pack(fill="x", pady=5)

        # Tally check button
        tk.Button(
            parent,
            text="📊 Check Tally",
            font=FONTS["label_bold"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=15, pady=8,
            cursor="hand2",
            command=self._check_tally
        ).pack(fill="x", pady=3)

        # Export CSV button
        tk.Button(
            parent,
            text="📊 Export Bills to CSV",
            font=FONTS["label_bold"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=15, pady=8,
            cursor="hand2",
            command=self._export_csv
        ).pack(fill="x", pady=3)

    def _on_margin_type_change(self):
        """Show/hide margin input fields"""
        mtype = self.var_margin_type.get()

        # Range inputs
        for child in self.range_inputs.winfo_children():
            try:
                child.configure(
                    state="normal"
                    if mtype in ("range", "itemwise")
                    else "disabled"
                )
            except Exception:
                pass

        # Global input
        for child in self.global_input.winfo_children():
            try:
                child.configure(
                    state="normal"
                    if mtype == "global"
                    else "disabled"
                )
            except Exception:
                pass

    # ----------------------------------------------------------
    # EXISTING BILLS
    # ----------------------------------------------------------
    def _build_existing_bills(self, parent):
        """Right panel: existing sales bills this month"""

        tk.Label(
            parent,
            text="Existing Sales Bills",
            font=FONTS["subheading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 5))

        # Summary bar
        self.existing_summary = tk.Label(
            parent,
            text="",
            font=FONTS["label"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            anchor="w",
            padx=10, pady=6
        )
        self.existing_summary.pack(fill="x")

        # Table header
        hdr = tk.Frame(parent, bg=COLORS["header_bg"])
        hdr.pack(fill="x")

        for col, width in [
            ("Bill No",     14), ("Customer",  20),
            ("Date",        12), ("Items",      6),
            ("Total",       13), ("Actions",   16),
        ]:
            tk.Label(
                hdr,
                text=col,
                font=FONTS["table_bold"],
                bg=COLORS["header_bg"],
                fg="white",
                width=width,
                anchor="w",
                padx=5, pady=7
            ).pack(side="left")

        # Scrollable body
        body_outer = tk.Frame(
            parent,
            bg=COLORS["bg_card"],
            relief="solid", bd=1
        )
        body_outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            body_outer,
            bg=COLORS["bg_card"],
            highlightthickness=0
        )
        sb = ttk.Scrollbar(
            body_outer,
            orient="vertical",
            command=canvas.yview
        )
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(
            side="left", fill="both", expand=True
        )

        self.bills_body = tk.Frame(
            canvas, bg=COLORS["bg_card"]
        )
        cw = canvas.create_window(
            (0, 0),
            window=self.bills_body,
            anchor="nw"
        )

        self.bills_body.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(
                cw, width=e.width
            )
        )

    # ----------------------------------------------------------
    # LOAD DATA
    # ----------------------------------------------------------
    def _load_data(self):
        """Load purchase pool and existing sales bills"""
        month = self.filter_month.get()
        year  = self.filter_year.get()

        self._load_pool_summary(month, year)
        self._load_existing_bills(month, year)

    def _load_pool_summary(self, month: int, year: int):
        """Show purchase pool summary"""
        for w in self.pool_info_frame.winfo_children():
            w.destroy()

        # Get pool totals
        totals = db.query_one("""
            SELECT
                COUNT(DISTINCT pb.id) AS bill_count,
                COUNT(pi.id)          AS item_count,
                COALESCE(SUM(pi.quantity), 0)
                    AS total_qty,
                COALESCE(SUM(pi.remaining_qty), 0)
                    AS remaining_qty,
                COALESCE(SUM(pb.grand_total), 0)
                    AS purchase_total
            FROM purchase_bills pb
            JOIN purchase_items pi
                ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_month=? AND pb.bill_year=?
        """, (month, year))

        if not totals or totals.get(
            "bill_count", 0
        ) == 0:
            tk.Label(
                self.pool_info_frame,
                text="⚠️  No purchase bills found.\n"
                     "Add purchase bills first.",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["warning"]
            ).pack(pady=10)
            return

        month_name = MONTH_NAMES[month]
        remaining  = totals.get("remaining_qty", 0)
        total_qty  = totals.get("total_qty", 0)
        pct_done   = (
            round(
                (total_qty - remaining) /
                total_qty * 100
            )
            if total_qty > 0 else 0
        )

        stats = [
            ("Purchase Bills", str(totals["bill_count"])),
            ("Unique Items",   str(totals["item_count"])),
            ("Total Stock",    f"{total_qty:.1f} units"),
            ("Remaining",      f"{remaining:.1f} units"),
            ("Purchase Total",
             f"₹{totals['purchase_total']:,.2f}"),
            ("Distributed",    f"{pct_done}%"),
        ]

        for i, (label, value) in enumerate(stats):
            row = tk.Frame(
                self.pool_info_frame,
                bg=COLORS["bg_card"]
            )
            row.pack(fill="x", pady=2)

            tk.Label(
                row,
                text=label + ":",
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"],
                width=18, anchor="w"
            ).pack(side="left")

            tk.Label(
                row,
                text=value,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=COLORS["primary"]
            ).pack(side="left")

        # Progress bar
        if total_qty > 0:
            prog_frame = tk.Frame(
                self.pool_info_frame,
                bg=COLORS["border"],
                height=8
            )
            prog_frame.pack(fill="x", pady=(5, 0))

            prog_done = tk.Frame(
                prog_frame,
                bg=COLORS["success"],
                height=8
            )
            prog_done.place(
                relx=0, rely=0,
                relwidth=pct_done / 100,
                relheight=1
            )

    def _load_existing_bills(
        self, month: int, year: int
    ):
        """Load and display existing sales bills"""
        for w in self.bills_body.winfo_children():
            w.destroy()

        bills = db.query("""
            SELECT
                sb.*,
                (SELECT COUNT(*) FROM sales_items si
                 WHERE si.sales_bill_id = sb.id
                ) AS item_count
            FROM sales_bills sb
            WHERE sb.bill_month=? AND sb.bill_year=?
            ORDER BY sb.bill_date, sb.bill_number
        """, (month, year))

        # Summary
        if bills:
            total = sum(
                b["grand_total"] for b in bills
            )
            self.existing_summary.configure(
                text=f"  {len(bills)} bills  |  "
                     f"Total: ₹{total:,.2f}",
                bg=COLORS["success_light"],
                fg=COLORS["success"]
            )
        else:
            self.existing_summary.configure(
                text="  No sales bills generated yet "
                     "for this month.",
                bg=COLORS["warning_light"],
                fg=COLORS["warning"]
            )

        if not bills:
            tk.Label(
                self.bills_body,
                text="No sales bills for this month.\n"
                     "Use the Generate panel on the left.",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"],
                justify="center"
            ).pack(pady=30)
            return

        for i, bill in enumerate(bills):
            self._render_bill_row(bill, i)

    def _render_bill_row(
        self, bill: dict, idx: int
    ):
        """Render one sales bill row"""
        bg = (COLORS["row_even"]
              if idx % 2 == 0
              else COLORS["row_odd"])

        row = tk.Frame(self.bills_body, bg=bg)
        row.pack(fill="x")

        try:
            d = datetime.strptime(
                bill["bill_date"], "%Y-%m-%d"
            )
            date_str = d.strftime("%d/%m/%Y")
        except Exception:
            date_str = bill["bill_date"]

        for text, width in [
            (bill["bill_number"],          14),
            (bill["customer_name"],        20),
            (date_str,                     12),
            (str(bill.get("item_count",0)), 6),
            (f"₹{bill['grand_total']:,.0f}",13),
        ]:
            tk.Label(
                row,
                text=text,
                font=FONTS["table"],
                bg=bg,
                fg=COLORS["text_dark"],
                width=width,
                anchor="w",
                padx=5, pady=6
            ).pack(side="left")

        # Actions
        act = tk.Frame(row, bg=bg)
        act.pack(side="left", padx=5)

        bill_id = bill["id"]

        tk.Button(
            act,
            text="🖨️",
            font=FONTS["small"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=5, pady=3,
            cursor="hand2",
            command=lambda bid=bill_id:
                self._print_bill(bid)
        ).pack(side="left", padx=2)

        tk.Button(
            act,
            text="📄",
            font=FONTS["small"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=5, pady=3,
            cursor="hand2",
            command=lambda bid=bill_id:
                self._export_bill_pdf(bid)
        ).pack(side="left", padx=2)

        tk.Button(
            act,
            text="🗑️",
            font=FONTS["small"],
            bg=COLORS["danger"],
            fg="white",
            relief="flat",
            padx=5, pady=3,
            cursor="hand2",
            command=lambda bid=bill_id:
                self._delete_bill(bid)
        ).pack(side="left", padx=2)

    # ----------------------------------------------------------
    # GENERATE BILLS
    # ----------------------------------------------------------
    def _generate_bills(self):
        """Run splitting algorithm and show preview"""
        month = self.filter_month.get()
        year  = self.filter_year.get()

        # Validate inputs
        n_bills = self.var_n_bills.get()
        if n_bills < 1:
            messagebox.showerror(
                "Error",
                "Number of bills must be at least 1."
            )
            return

        min_items = self.var_min_items.get()
        max_items = self.var_max_items.get()
        if min_items > max_items:
            messagebox.showerror(
                "Error",
                "Min items cannot be more than max items."
            )
            return

        margin_min = self.var_margin_min.get()
        margin_max = self.var_margin_max.get()
        if margin_min >= margin_max and \
                self.var_margin_type.get() == "range":
            messagebox.showerror(
                "Error",
                "Margin minimum must be less than maximum."
            )
            return

        # Check for existing bills
        existing = db.query_one("""
            SELECT COUNT(*) AS cnt
            FROM sales_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        if existing.get("cnt", 0) > 0:
            if not messagebox.askyesno(
                "Bills Exist",
                f"Sales bills already exist for "
                f"{MONTH_NAMES[month]} {year}.\n\n"
                "Generating new bills will be IN ADDITION\n"
                "to existing ones.\n\n"
                "Continue?"
            ):
                return

        # Run splitter
        try:
            splitter = BillSplitter(self.settings)

            # Apply tax scheme from UI
            splitter.tax_scheme = self.var_bill_type.get()

            self.app.set_status(
                "Generating bills...", "info"
            )

            bills = splitter.split(
                month=month,
                year=year,
                n_bills=n_bills,
                min_items_per_bill=min_items,
                max_items_per_bill=max_items,
                override_margin_type=
                    self.var_margin_type.get(),
                override_margin_min=margin_min,
                override_margin_max=margin_max,
                override_margin_global=
                    self.var_margin_global.get(),
            )

            if not bills:
                messagebox.showwarning(
                    "No Bills Generated",
                    "Could not generate bills.\n"
                    "All purchase stock may be\n"
                    "already distributed."
                )
                return

            # Verify tally
            tally = splitter.verify_tally(
                month, year, bills
            )

            # Store for later use
            self.pending_bills = bills
            self._current_splitter = splitter

            # Show preview
            BillPreviewDialog(
                self,
                bills=bills,
                tally=tally,
                month=month,
                year=year,
                on_confirm_callback=self._save_bills,
                on_regenerate_callback=
                    self._generate_bills,
            )

        except ValueError as e:
            messagebox.showerror(
                "Cannot Generate",
                str(e)
            )
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Bill generation failed.\n\n{e}"
            )

    # ----------------------------------------------------------
    # SAVE BILLS TO DATABASE
    # ----------------------------------------------------------
    def _save_bills(self, bills: list):
        """Save confirmed bills to database"""
        month    = self.filter_month.get()
        year     = self.filter_year.get()
        settings = load_settings()

        bill_num_mgr = BillNumberManager(settings)

        saved_count = 0
        errors      = []

        for bill in bills:
            try:
                # Get bill number
                bill_number = bill_num_mgr.get_next_number()

                bill_date = bill["bill_date"]
                if isinstance(bill_date, date):
                    bill_date_str = \
                        bill_date.strftime("%Y-%m-%d")
                else:
                    bill_date_str = str(bill_date)

                # Save or get customer
                customer_name = bill["customer"]["name"]
                city          = bill["customer"].get(
                    "city", ""
                )

                # Check if customer exists
                cust = db.query_one("""
                    SELECT id FROM customers
                    WHERE LOWER(name)=?
                """, (customer_name.lower(),))

                if cust:
                    customer_id = cust["id"]
                else:
                    # Save auto-generated customer
                    customer_id = db.execute("""
                        INSERT INTO customers
                        (name, city, is_auto_generated)
                        VALUES (?,?,1)
                    """, (customer_name, city))

                # Save sales bill
                sales_bill_id = db.execute("""
                    INSERT INTO sales_bills
                    (bill_number, customer_id,
                     customer_name, bill_date,
                     bill_month, bill_year,
                     subtotal, total_cgst, total_sgst,
                     grand_total, bill_type,
                     margin_applied, linked_month,
                     linked_year)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    bill_number,
                    customer_id,
                    customer_name,
                    bill_date_str,
                    month, year,
                    bill["subtotal"],
                    bill["total_cgst"],
                    bill["total_sgst"],
                    bill["grand_total"],
                    bill["bill_type"],
                    bill["margin_avg"],
                    month, year
                ))

                # Save items
                for item in bill["items"]:
                    db.execute("""
                        INSERT INTO sales_items
                        (sales_bill_id,
                         purchase_item_id,
                         item_name, hsn_code,
                         quantity, unit,
                         selling_rate, gst_rate,
                         cgst_rate, sgst_rate,
                         cgst_amount, sgst_amount,
                         total_amount, margin_percent)
                        VALUES
                        (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        sales_bill_id,
                        item["purchase_item_id"],
                        item["item_name"],
                        item["hsn_code"],
                        item["quantity"],
                        item["unit"],
                        item["selling_rate"],
                        item["gst_rate"],
                        item["cgst_rate"],
                        item["sgst_rate"],
                        item["cgst_amount"],
                        item["sgst_amount"],
                        item["total_amount"],
                        item["margin_pct"],
                    ))

                    # Update remaining_qty in purchase_items
                    db.execute("""
                        UPDATE purchase_items
                        SET remaining_qty =
                            remaining_qty - ?
                        WHERE id = ?
                    """, (
                        item["quantity"],
                        item["purchase_item_id"]
                    ))

                # Generate PDF
                self._generate_bill_pdf(
                    sales_bill_id,
                    bill_number,
                    bill,
                    month, year,
                    settings
                )

                saved_count += 1

            except Exception as e:
                errors.append(str(e))
                bill_num_mgr.rollback_number()

        # Update monthly summary
        self._update_monthly_summary(month, year)

        # Reload UI
        self._load_data()
        self.app.set_status(
            f"Saved {saved_count} sales bills",
            "success"
        )

        if errors:
            messagebox.showwarning(
                "Partial Save",
                f"Saved: {saved_count} bills\n"
                f"Errors: {len(errors)}\n\n"
                + "\n".join(errors[:3])
            )
        else:
            messagebox.showinfo(
                "Bills Saved ✅",
                f"Successfully saved "
                f"{saved_count} sales bills!\n\n"
                f"Month: {MONTH_NAMES[month]} {year}\n"
                f"Bills: {saved_count}\n\n"
                "PDFs generated in bills folder."
            )

    def _generate_bill_pdf(
        self,
        bill_id:    int,
        bill_number: str,
        bill_data:  dict,
        month:      int,
        year:       int,
        settings:   dict
    ):
        """Generate PDF for a single bill"""
        try:
            from modules.pdf_generator import PDFGenerator
            gen = PDFGenerator(settings)

            folder = self._get_sales_folder(
                month, year, settings
            )
            pdf_path = folder / f"{bill_number}.pdf"

            gen.generate_sales_bill(
                bill_data=bill_data,
                bill_number=bill_number,
                output_path=str(pdf_path)
            )

            # Update file_path in DB
            db.execute("""
                UPDATE sales_bills
                SET file_path=?
                WHERE id=?
            """, (str(pdf_path), bill_id))

        except Exception as e:
            print(f"[PDF] Generation error: {e}")

    def _get_sales_folder(
        self,
        month: int,
        year: int,
        settings: dict
    ) -> Path:
        """Get/create sales bills folder"""
        root = Path(
            settings["storage"]["bills_root_folder"]
        )
        folder = (
            root / str(year) /
            f"{month:02d}_{MONTH_NAMES[month]}" /
            "Sales"
        )
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _update_monthly_summary(
        self, month: int, year: int
    ):
        """Refresh monthly summary table"""
        p = db.query_one("""
            SELECT
                COUNT(*) AS cnt,
                COALESCE(SUM(subtotal), 0) AS taxable,
                COALESCE(SUM(total_gst), 0) AS gst
            FROM purchase_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        s = db.query_one("""
            SELECT
                COUNT(*) AS cnt,
                COALESCE(SUM(subtotal), 0) AS taxable,
                COALESCE(SUM(total_cgst), 0) AS cgst,
                COALESCE(SUM(total_sgst), 0) AS sgst,
                COALESCE(SUM(grand_total), 0) AS total
            FROM sales_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        profit  = (
            s.get("taxable", 0) -
            p.get("taxable", 0)
        )
        out_gst = (
            s.get("cgst", 0) +
            s.get("sgst", 0)
        )
        payable = max(
            0, out_gst - p.get("gst", 0)
        )

        db.execute("""
            INSERT INTO monthly_summary
            (month, year, total_purchase,
             total_purchase_gst, total_sales,
             total_cgst, total_sgst,
             total_profit, gst_payable,
             bills_count_purchase,
             bills_count_sales,
             updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,
                    CURRENT_TIMESTAMP)
            ON CONFLICT(month,year) DO UPDATE SET
                total_purchase=excluded.total_purchase,
                total_purchase_gst=
                    excluded.total_purchase_gst,
                total_sales=excluded.total_sales,
                total_cgst=excluded.total_cgst,
                total_sgst=excluded.total_sgst,
                total_profit=excluded.total_profit,
                gst_payable=excluded.gst_payable,
                bills_count_purchase=
                    excluded.bills_count_purchase,
                bills_count_sales=
                    excluded.bills_count_sales,
                updated_at=CURRENT_TIMESTAMP
        """, (
            month, year,
            p.get("taxable", 0),
            p.get("gst", 0),
            s.get("taxable", 0),
            s.get("cgst", 0),
            s.get("sgst", 0),
            profit, payable,
            p.get("cnt", 0),
            s.get("cnt", 0)
        ))

    # ----------------------------------------------------------
    # TALLY CHECK
    # ----------------------------------------------------------
    def _check_tally(self):
        """Show tally verification popup"""
        month = self.filter_month.get()
        year  = self.filter_year.get()

        splitter = BillSplitter(self.settings)
        pool     = splitter.get_purchase_pool(
            month, year
        )

        if not pool:
            messagebox.showinfo(
                "Tally Check",
                "No purchase data found for "
                f"{MONTH_NAMES[month]} {year}."
            )
            return

        # Get existing sales
        sales_items = db.query("""
            SELECT
                si.item_name,
                si.unit,
                SUM(si.quantity) AS total_sold
            FROM sales_items si
            JOIN sales_bills sb
                ON si.sales_bill_id = sb.id
            WHERE sb.bill_month=? AND sb.bill_year=?
            GROUP BY si.item_name, si.unit
        """, (month, year))

        sold_map = {
            r["item_name"].lower(): r["total_sold"]
            for r in sales_items
        }

        # Pool totals
        pool_totals = db.query("""
            SELECT
                pi.item_name,
                pi.unit,
                SUM(pi.quantity) AS purchased,
                SUM(pi.remaining_qty) AS remaining
            FROM purchase_items pi
            JOIN purchase_bills pb
                ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_month=? AND pb.bill_year=?
            GROUP BY pi.item_name, pi.unit
        """, (month, year))

        # Build tally popup
        popup = tk.Toplevel(self)
        popup.title(
            f"Tally Check — "
            f"{MONTH_NAMES[month]} {year}"
        )
        popup.geometry("700x500")
        popup.configure(bg=COLORS["bg_main"])

        tk.Label(
            popup,
            text=f"📊 Tally Check — "
                 f"{MONTH_NAMES[month]} {year}",
            font=FONTS["heading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", padx=20, pady=15)

        # Header
        hdr = tk.Frame(popup, bg=COLORS["header_bg"])
        hdr.pack(fill="x", padx=20)

        for col, width in [
            ("Item",        20), ("Unit",   7),
            ("Purchased",    9), ("Sold",   9),
            ("Remaining",    9), ("Status", 8),
        ]:
            tk.Label(
                hdr,
                text=col,
                font=FONTS["table_bold"],
                bg=COLORS["header_bg"],
                fg="white",
                width=width,
                anchor="w",
                padx=5, pady=6
            ).pack(side="left")

        # Rows
        body = tk.Frame(popup, bg=COLORS["bg_card"])
        body.pack(
            fill="both", expand=True,
            padx=20, pady=5
        )

        all_ok = True
        for i, pt in enumerate(pool_totals):
            bg = (COLORS["row_even"]
                  if i % 2 == 0
                  else COLORS["row_odd"])
            row = tk.Frame(body, bg=bg)
            row.pack(fill="x")

            purchased = pt["purchased"]
            remaining = pt.get("remaining", 0) or 0
            sold      = round(purchased - remaining, 3)
            diff      = round(remaining, 3)
            ok        = abs(diff) < 0.01

            if not ok:
                all_ok = False

            status       = "✅" if ok else f"⚠️ {diff:.1f}"
            status_color = (COLORS["success"]
                           if ok else COLORS["warning"])

            for text, width in [
                (pt["item_name"], 20),
                (pt["unit"],       7),
                (f"{purchased:.1f}", 9),
                (f"{sold:.1f}",      9),
                (f"{remaining:.1f}", 9),
            ]:
                tk.Label(
                    row,
                    text=text,
                    font=FONTS["table"],
                    bg=bg,
                    fg=COLORS["text_dark"],
                    width=width,
                    anchor="w",
                    padx=5, pady=5
                ).pack(side="left")

            tk.Label(
                row,
                text=status,
                font=FONTS["table_bold"],
                bg=bg,
                fg=status_color,
                width=8,
                anchor="w",
                padx=5
            ).pack(side="left")

        # Overall status
        status_msg = (
            "✅ All items tallied perfectly!"
            if all_ok
            else "⚠️ Some items have remaining stock"
        )
        status_color = (
            COLORS["success"]
            if all_ok
            else COLORS["warning"]
        )

        tk.Label(
            popup,
            text=status_msg,
            font=FONTS["subheading"],
            bg=COLORS["bg_main"],
            fg=status_color
        ).pack(pady=10)

    # ----------------------------------------------------------
    # ACTIONS
    # ----------------------------------------------------------
    def _print_bill(self, bill_id: int):
        """Print a sales bill"""
        bill = db.query_one("""
            SELECT file_path FROM sales_bills
            WHERE id=?
        """, (bill_id,))

        pdf_path = bill.get("file_path", "")

        if pdf_path and Path(pdf_path).exists():
            try:
                import os
                os.startfile(pdf_path, "print")
                db.execute("""
                    UPDATE sales_bills
                    SET is_printed=1
                    WHERE id=?
                """, (bill_id,))
                self._load_data()
            except Exception as e:
                messagebox.showerror(
                    "Print Error", str(e)
                )
        else:
            messagebox.showwarning(
                "PDF Not Found",
                "PDF not found. Regenerating..."
            )

    def _export_bill_pdf(self, bill_id: int):
        """Export/open PDF for a bill"""
        bill = db.query_one("""
            SELECT * FROM sales_bills WHERE id=?
        """, (bill_id,))

        pdf_path = bill.get("file_path", "")

        if pdf_path and Path(pdf_path).exists():
            import os
            os.startfile(pdf_path)
        else:
            messagebox.showwarning(
                "PDF Not Found",
                "PDF file not found for this bill."
            )

    def _delete_bill(self, bill_id: int):
        """Delete a sales bill and restore quantities"""
        bill = db.query_one("""
            SELECT * FROM sales_bills WHERE id=?
        """, (bill_id,))

        if not bill:
            return

        if not messagebox.askyesno(
            "Delete Bill",
            f"Delete bill {bill['bill_number']}?\n"
            f"Customer: {bill['customer_name']}\n"
            f"Total: ₹{bill['grand_total']:,.2f}\n\n"
            "Stock quantities will be restored.\n"
            "This cannot be undone."
        ):
            return

        # Restore quantities
        items = db.query("""
            SELECT purchase_item_id, quantity
            FROM sales_items
            WHERE sales_bill_id=?
        """, (bill_id,))

        for item in items:
            db.execute("""
                UPDATE purchase_items
                SET remaining_qty =
                    remaining_qty + ?
                WHERE id=?
            """, (
                item["quantity"],
                item["purchase_item_id"]
            ))

        # Delete sales items
        db.execute("""
            DELETE FROM sales_items
            WHERE sales_bill_id=?
        """, (bill_id,))

        # Delete sales bill
        db.execute("""
            DELETE FROM sales_bills WHERE id=?
        """, (bill_id,))

        # Update summary
        self._update_monthly_summary(
            bill["bill_month"],
            bill["bill_year"]
        )

        self.app.set_status(
            "Sales bill deleted — stock restored",
            "warning"
        )
        self._load_data()

    def _export_csv(self):
        """Export all sales bills to CSV"""
        month = self.filter_month.get()
        year  = self.filter_year.get()

        bills = db.query("""
            SELECT
                sb.bill_number,
                sb.customer_name,
                sb.bill_date,
                sb.subtotal,
                sb.total_cgst,
                sb.total_sgst,
                sb.grand_total,
                sb.bill_type,
                sb.margin_applied
            FROM sales_bills sb
            WHERE sb.bill_month=? AND sb.bill_year=?
            ORDER BY sb.bill_date, sb.bill_number
        """, (month, year))

        if not bills:
            messagebox.showwarning(
                "No Bills",
                "No sales bills to export."
            )
            return

        path = filedialog.asksaveasfilename(
            title="Export Sales Bills",
            defaultextension=".csv",
            initialfile=(
                f"sales_{year}_{month:02d}.csv"
            ),
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        try:
            with open(
                path, "w", newline="",
                encoding="utf-8-sig"
            ) as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "bill_number",
                        "customer_name",
                        "bill_date",
                        "taxable_amount",
                        "cgst",
                        "sgst",
                        "grand_total",
                        "bill_type",
                        "margin_pct"
                    ]
                )
                writer.writeheader()

                for b in bills:
                    writer.writerow({
                        "bill_number":
                            b["bill_number"],
                        "customer_name":
                            b["customer_name"],
                        "bill_date":
                            b["bill_date"],
                        "taxable_amount":
                            b["subtotal"],
                        "cgst": b["total_cgst"],
                        "sgst": b["total_sgst"],
                        "grand_total":
                            b["grand_total"],
                        "bill_type":
                            b["bill_type"],
                        "margin_pct":
                            b["margin_applied"]
                    })

            messagebox.showinfo(
                "Export Complete ✅",
                f"Exported {len(bills)} bills to:\n"
                f"{path}"
            )

            import os
            os.startfile(
                str(Path(path).parent)
            )

        except Exception as e:
            messagebox.showerror(
                "Export Error",
                f"Could not export.\n\n{e}"
            )