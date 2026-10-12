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
import calendar
from pathlib import Path
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from modules.date_utils import (
    DATE_PRESETS,
    get_date_range_for_preset,
    parse_flexible_date,
    format_date_display,
    format_date_iso,
    get_month_dates,
)

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
        self.flat_markup_amount = settings["billing"].get(
            "flat_markup_amount", 5.0
        )
        self.target_profit_amount = settings["billing"].get(
            "target_profit_amount", 0.0
        )
        self.tax_scheme   = settings["billing"].get(
            "tax_scheme", "regular"
        )

    def get_purchase_pool(
        self,
        month: int = None,
        year: int = None,
        start_date: date = None,
        end_date: date = None,
        include_carried_forward: bool = True,
    ) -> list:
        """
        Get all purchase items for the date range.
        If include_carried_forward is True (default), loads all unsold items
        purchased on or before end_date (FIFO continuous inventory flow).
        """
        if start_date is None or end_date is None:
            if month is not None and year is not None:
                start_date, end_date = get_month_dates(year, month)
            else:
                today = date.today()
                start_date, end_date = get_month_dates(today.year, today.month)
        else:
            if start_date > end_date:
                start_date, end_date = end_date, start_date

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        if include_carried_forward:
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
                    pb.bill_date,
                    pb.bill_month,
                    pb.bill_year,
                    pb.dealer_name,
                    CASE WHEN pb.bill_date < ? THEN 1 ELSE 0 END AS is_carried_forward
                FROM purchase_items pi
                JOIN purchase_bills pb
                    ON pi.purchase_bill_id = pb.id
                WHERE pb.bill_date <= ?
                AND   pi.remaining_qty > 0.0001
                ORDER BY pb.bill_date ASC, pi.id ASC
            """, (start_str, end_str))
        else:
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
                    pb.bill_date,
                    pb.bill_month,
                    pb.bill_year,
                    pb.dealer_name,
                    0 AS is_carried_forward
                FROM purchase_items pi
                JOIN purchase_bills pb
                    ON pi.purchase_bill_id = pb.id
                WHERE pb.bill_date >= ?
                AND   pb.bill_date <= ?
                AND   pi.remaining_qty > 0.0001
                ORDER BY pb.bill_date ASC, pi.id ASC
            """, (start_str, end_str))

        return items

    def get_margin_for_item(self) -> float:
        """Get margin value for one item based on settings."""
        if self.margin_type == "global":
            return self.margin_global
        elif self.margin_type == "range":
            # Random within range, rounded to 1 decimal
            margin = random.uniform(
                self.margin_min,
                self.margin_max
            )
            return round(margin, 1)
        elif self.margin_type == "flat":
            return max(0.0, float(self.flat_markup_amount or 0.0))
        elif self.margin_type == "target_profit":
            if hasattr(self, "_target_margin_pct") and self._target_margin_pct is not None:
                return self._target_margin_pct
            if hasattr(self, "_target_multiplier") and self._target_multiplier is not None:
                return round((self._target_multiplier - 1.0) * 100.0, 1)
            return 0.0
        else:
            # itemwise — use range as default
            return round(
                random.uniform(
                    self.margin_min,
                    self.margin_max
                ), 1
            )

    def get_target_profit_multiplier(self, purchase_total: float) -> float:
        """Return the sales multiplier required to hit the target profit."""
        purchase_total = max(0.0, float(purchase_total or 0.0))
        target_profit = max(0.0, float(self.target_profit_amount or 0.0))
        if purchase_total <= 0:
            return 1.0
        if target_profit <= 0:
            return 1.0
        return (purchase_total + target_profit) / purchase_total

    def calculate_selling_rate(
        self,
        purchase_rate: float,
        gst_rate: float,
        margin_pct: float
    ) -> tuple:
        """
        Calculate selling rate and GST breakdown.

        For Regular GST:
            selling_rate = purchase_rate * (1 + margin_pct / 100)
            cgst_rate    = gst_rate / 2
            sgst_rate    = gst_rate / 2

        For Composition (No customer GST charged):
            selling_rate = purchase_rate * (1 + margin_pct / 100)
            gst_rate = cgst_rate = sgst_rate = 0.0

        For Flat Markup:
            selling_rate = purchase_rate + flat_markup_amount
            GST follows the same scheme logic, but the margin is a rupee amount.

        Returns:
            (selling_rate, gst_rate, cgst_rate, sgst_rate)
        """
        if self.margin_type == "flat":
            flat_markup = max(
                0.0,
                float(margin_pct if margin_pct is not None else self.flat_markup_amount or 0.0)
            )
            selling_rate = round2(purchase_rate + flat_markup)
        else:
            margin = max(0.0, float(margin_pct or 0.0)) / 100.0
            selling_rate = round2(purchase_rate * (1.0 + margin))

        if self.tax_scheme == "composition":
            return selling_rate, 0.0, 0.0, 0.0

        gst_rate = float(gst_rate or 0.0)
        cgst_rate = round2(gst_rate / 2.0)
        sgst_rate = round2(gst_rate / 2.0)
        return selling_rate, gst_rate, cgst_rate, sgst_rate

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
        month: int = None,
        year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> list:
        """
        Distribute N bill dates across the target date range naturally.
        Prefers working days (Mon-Sat, skipping Sundays).
        """
        if start_date is None or end_date is None:
            if month is not None and year is not None:
                start_date, end_date = get_month_dates(year, month)
            else:
                today = date.today()
                start_date, end_date = get_month_dates(today.year, today.month)

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        candidate_dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() != 6:  # Skip Sundays
                candidate_dates.append(current)
            current += timedelta(days=1)

        if not candidate_dates:
            current = start_date
            while current <= end_date:
                candidate_dates.append(current)
                current += timedelta(days=1)

        if not candidate_dates:
            return [start_date] * n_bills

        if n_bills <= len(candidate_dates):
            chosen = sorted(random.sample(candidate_dates, n_bills))
        else:
            chosen = sorted(random.choices(candidate_dates, k=n_bills))

        return chosen

    def split(
        self,
        month: int = None,
        year: int = None,
        n_bills: int = 5,
        min_items_per_bill: int = 1,
        max_items_per_bill: int = 5,
        override_margin_type: str = None,
        override_margin_min:  float = None,
        override_margin_max:  float = None,
        override_margin_global: float = None,
        override_flat_markup_amount: float = None,
        override_target_profit_amount: float = None,
        start_date: date = None,
        end_date: date = None,
        include_carried_forward: bool = True,
        allocation_mode: str = "all",
        target_sales_amount: float = None,
        stock_percentage: float = 100.0,
        customer_mode: str = "random",
        cash_name: str = "Cash Bill",
    ) -> list:
        """
        Main splitting function.

        Args:
            month: Purchase month (optional if start_date/end_date provided)
            year:  Purchase year (optional if start_date/end_date provided)
            n_bills: Number of sales bills to generate
            min_items_per_bill: Min items per bill
            max_items_per_bill: Max items per bill
            override_*: Override margin settings
            start_date: Custom range start
            end_date: Custom range end
            include_carried_forward: If True, draws from unsold stock before start_date
            allocation_mode: 'all', 'target_amount', or 'percentage'
            target_sales_amount: Rupee amount of sales to generate (when allocation_mode='target_amount')
            stock_percentage: % of stock to sell (when allocation_mode='percentage')

        Returns:
            List of bill dicts ready for preview/saving
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
        if override_flat_markup_amount is not None:
            self.flat_markup_amount = override_flat_markup_amount
        if override_target_profit_amount is not None:
            self.target_profit_amount = override_target_profit_amount

        if start_date is None or end_date is None:
            if month is not None and year is not None:
                start_date, end_date = get_month_dates(year, month)
            else:
                today = date.today()
                start_date, end_date = get_month_dates(today.year, today.month)

        if start_date > end_date:
            start_date, end_date = end_date, start_date

        if month is None:
            month = start_date.month
        if year is None:
            year = start_date.year

        # Step 1: Get purchase pool (including carried forward unsold inventory)
        pool = self.get_purchase_pool(
            month=month,
            year=year,
            start_date=start_date,
            end_date=end_date,
            include_carried_forward=include_carried_forward,
        )
        if not pool:
            raise ValueError(
                "No purchase items found for this period.\n"
                "Add purchase bills first."
            )

        # Step 1b: Determine allocated quantities
        working_pool = []
        if allocation_mode == "percentage" and stock_percentage < 99.9:
            pct = max(1.0, min(100.0, float(stock_percentage))) / 100.0
            for it in pool:
                it_copy = dict(it)
                q_rem = float(it["remaining_qty"])
                u = it["unit"]
                alloc_q = self._round_quantity(q_rem * pct, u)
                alloc_q = max(self._min_qty(u), min(alloc_q, q_rem))
                it_copy["allocated_qty"] = alloc_q
                working_pool.append(it_copy)

        elif allocation_mode == "target_amount" and target_sales_amount and target_sales_amount > 0:
            target_s = float(target_sales_amount)
            if self.margin_type == "target_profit" and self.target_profit_amount > 0:
                est_cost = max(500.0, target_s - self.target_profit_amount)
            else:
                est_m = self.margin_global if self.margin_type == "global" else (self.margin_min + self.margin_max) / 2.0
                est_cost = target_s / (1.0 + max(0.0, est_m) / 100.0)

            accum_cost = 0.0
            for it in pool:
                it_copy = dict(it)
                p_rate = float(it["purchase_rate"])
                q_rem = float(it["remaining_qty"])
                it_cost = p_rate * q_rem
                needed_cost = est_cost - accum_cost
                if needed_cost <= 0:
                    break
                if it_cost <= needed_cost:
                    it_copy["allocated_qty"] = q_rem
                    accum_cost += it_cost
                    working_pool.append(it_copy)
                else:
                    needed_q = self._round_quantity(needed_cost / max(p_rate, 0.01), it["unit"])
                    needed_q = max(self._min_qty(it["unit"]), min(needed_q, q_rem))
                    it_copy["allocated_qty"] = needed_q
                    accum_cost += p_rate * needed_q
                    working_pool.append(it_copy)
                    break
            if not working_pool and pool:
                it_copy = dict(pool[0])
                it_copy["allocated_qty"] = min(float(pool[0]["remaining_qty"]), self._min_qty(pool[0]["unit"]))
                working_pool.append(it_copy)

        else:  # allocation_mode == "all"
            for it in pool:
                it_copy = dict(it)
                it_copy["allocated_qty"] = float(it["remaining_qty"])
                working_pool.append(it_copy)

        total_p_taxable = round2(sum(
            float(item["purchase_rate"]) * float(item["allocated_qty"])
            for item in working_pool
        ))

        # Target profit multiplier and margin %
        if self.margin_type == "target_profit":
            self._target_multiplier = self.get_target_profit_multiplier(
                total_p_taxable
            )
            self._target_margin_pct = round(
                (self.target_profit_amount / total_p_taxable * 100.0)
                if total_p_taxable > 0 else 0.0,
                1
            )
        else:
            self._target_multiplier = None
            self._target_margin_pct = None

        # Step 2: Generate bill dates across target date range
        bill_dates = self._distribute_dates(
            n_bills,
            month,
            year,
            start_date=start_date,
            end_date=end_date,
        )

        # Step 3: Get customer names
        if customer_mode == "cash":
            resolved_cash_name = (cash_name or "Cash Bill").strip() or "Cash Bill"
            customers = [resolved_cash_name] * n_bills
            name_gen = None
        else:
            from modules.customer_module import (
                KarnatakaNameGenerator
            )
            name_gen   = KarnatakaNameGenerator()
            name_gen.refresh_cache(month, year)
            customers  = name_gen.generate_batch(
                n_bills, month, year
            )

        # Step 4: Distribute pool items across N bills
        K = len(working_pool)
        eff_min = max(1, min_items_per_bill)
        eff_max = max(eff_min, max_items_per_bill, math.ceil(K / max(1, n_bills)) + 3)

        # Determine realistic portions for each item based on volume, rate, and bill count
        portions = {}
        for i, item in enumerate(working_pool):
            q = float(item["allocated_qty"])
            rate = float(item["purchase_rate"])
            u = item["unit"].lower()
            if q <= self._min_qty(item["unit"]) * 1.5 or n_bills <= 1:
                p = 1
            elif rate >= 3000:
                p = max(2, round(q / 5.0))
            elif "pipe" in item["item_name"].lower() or "cable" in item["item_name"].lower() or u in ("mtr", "mtrs", "meter", "meters"):
                p = max(2, round(q / 120.0))
            elif q >= 800:
                p = max(3, round(q / 200.0))
            elif q >= 400:
                p = max(2, round(q / 120.0))
            elif q >= 150:
                p = max(2, round(q / 80.0))
            elif q >= 40:
                p = max(2, round(q / 35.0))
            else:
                p = max(1, round(q / 15.0))
            portions[i] = max(1, min(n_bills, p))

        # Respect eff_max total slot capacity across all bills if specified
        max_total_slots = n_bills * eff_max
        while sum(portions.values()) > max_total_slots:
            max_p = max(portions.values())
            if max_p <= 1:
                break
            for i in range(K):
                if portions[i] == max_p:
                    portions[i] -= 1
                    if sum(portions.values()) <= max_total_slots:
                        break

        # Generate sub-quantities for each item
        item_portions = []
        unit_one_created = False

        for i, item in enumerate(working_pool):
            p_count = portions[i]
            q_total = round(float(item["allocated_qty"]), 3)
            u = item["unit"]
            u_lower = u.lower()

            is_count_item = u_lower in ("piece", "pieces", "nos", "no", "bottle", "bottles", "set", "sets")
            make_one = False
            if not unit_one_created and is_count_item and q_total >= 2.0:
                make_one = True
                unit_one_created = True

            if p_count == 1:
                if make_one and q_total > 1.0 and n_bills > 1:
                    item_portions.append({"item": item, "quantity": 1.0})
                    item_portions.append({"item": item, "quantity": round(q_total - 1.0, 3)})
                else:
                    item_portions.append({"item": item, "quantity": q_total})
            else:
                weights = [random.uniform(0.65, 1.35) for _ in range(p_count)]
                w_sum = sum(weights)
                m_q = self._min_qty(u)
                sub_qtys = []
                rem = q_total

                if make_one and p_count >= 2:
                    sub_qtys.append(1.0)
                    rem = round(rem - 1.0, 3)
                    weights = weights[1:]
                    w_sum = sum(weights)

                for w in weights[:-1]:
                    raw_q = rem * (w / w_sum)
                    q = self._round_quantity(raw_q, u)
                    max_allowed = rem - m_q * (p_count - len(sub_qtys) - 1)
                    if max_allowed >= m_q:
                        q = max(m_q, min(q, max_allowed))
                    else:
                        q = m_q
                    q = self._round_quantity(q, u)
                    sub_qtys.append(q)
                    rem = round(rem - q, 3)
                sub_qtys.append(round(rem, 3))
                if sub_qtys[-1] < m_q:
                    need = m_q - sub_qtys[-1]
                    max_idx = sub_qtys[:-1].index(max(sub_qtys[:-1]))
                    sub_qtys[max_idx] = round(sub_qtys[max_idx] - need, 3)
                    sub_qtys[-1] = m_q
                for q in sub_qtys:
                    if q > 0.0001:
                        item_portions.append({"item": item, "quantity": q})

        # Target budgets for natural ticket sizes (small, medium, large tickets)
        scales = []
        for i in range(n_bills):
            r = i / max(1, n_bills - 1) if n_bills > 1 else 0.5
            if r < 0.25:
                scales.append(random.uniform(0.4, 0.65))
            elif r < 0.7:
                scales.append(random.uniform(0.85, 1.25))
            else:
                scales.append(random.uniform(1.35, 1.8))
        random.shuffle(scales)
        s_sum = sum(scales)
        target_budgets = [(sc / s_sum) * total_p_taxable for sc in scales]

        # Sort portions descending by value
        item_portions.sort(
            key=lambda ip: float(ip["item"]["purchase_rate"]) * ip["quantity"],
            reverse=True
        )

        bills_raw = [[] for _ in range(n_bills)]
        bills_ptax = [0.0 for _ in range(n_bills)]

        for ip in item_portions:
            item_id = ip["item"]["purchase_item_id"]
            eligible = [
                b_idx for b_idx in range(n_bills)
                if all(it["item"]["purchase_item_id"] != item_id for it in bills_raw[b_idx])
            ]
            if not eligible:
                eligible = list(range(n_bills))
            eligible.sort(
                key=lambda b_idx: (
                    len(bills_raw[b_idx]) >= eff_max,
                    bills_ptax[b_idx] / max(target_budgets[b_idx], 1.0),
                    len(bills_raw[b_idx]),
                )
            )
            chosen_b = eligible[0]
            bills_raw[chosen_b].append(ip)
            bills_ptax[chosen_b] += float(ip["item"]["purchase_rate"]) * ip["quantity"]

        # Ensure no bill is empty
        for b_idx in range(n_bills):
            if not bills_raw[b_idx]:
                rich_b = max(range(n_bills), key=lambda b: len(bills_raw[b]))
                if len(bills_raw[rich_b]) > 1:
                    moved = bills_raw[rich_b].pop()
                    bills_raw[b_idx].append(moved)

        # Assign selling prices according to margin mode
        all_lines = []
        for b_idx in range(n_bills):
            for ip in bills_raw[b_idx]:
                p_rate = float(ip["item"]["purchase_rate"])
                qty = ip["quantity"]
                ip["purchase_rate"] = p_rate
                ip["bill_idx"] = b_idx

                if self.margin_type == "target_profit":
                    target_m = self._target_margin_pct or 0.0
                    jitter = random.uniform(-0.25, 0.25)
                    m = max(0.5, target_m + jitter)
                    sell_rate = round2(p_rate * (1.0 + m / 100.0))
                elif self.margin_type == "global":
                    m = self.margin_global
                    sell_rate = round2(p_rate * (1.0 + m / 100.0))
                elif self.margin_type == "flat":
                    margin_val = max(0.0, float(self.flat_markup_amount or 0.0))
                    sell_rate = round2(p_rate + margin_val)
                else:  # range and itemwise
                    m = round(random.uniform(self.margin_min, self.margin_max), 1)
                    sell_rate = round2(p_rate * (1.0 + m / 100.0))
                    eff_m = round(((sell_rate - p_rate) / max(p_rate, 0.01)) * 100.0, 1)
                    while eff_m < self.margin_min:
                        sell_rate = round2(sell_rate + 0.01)
                        eff_m = round(((sell_rate - p_rate) / max(p_rate, 0.01)) * 100.0, 1)
                    while eff_m > self.margin_max:
                        sell_rate = round2(sell_rate - 0.01)
                        eff_m = round(((sell_rate - p_rate) / max(p_rate, 0.01)) * 100.0, 1)

                taxable = round2(qty * sell_rate)
                ip["selling_rate"] = sell_rate
                ip["taxable_amount"] = taxable
                all_lines.append(ip)

        # In Target Profit mode: exact balancing down to 0.00 paisa
        if self.margin_type == "target_profit" and self.target_profit_amount > 0 and all_lines:
            target_s_taxable = round2(total_p_taxable + self.target_profit_amount)
            actual_s_taxable = round2(sum(it["taxable_amount"] for it in all_lines))
            diff = round2(target_s_taxable - actual_s_taxable)

            # Sort lines with smaller quantities first for fine-tuning
            lines_sorted = sorted(all_lines, key=lambda ip: ip["quantity"])

            for _ in range(5000):
                if abs(diff) < 0.001:
                    break
                step = 0.01 if diff > 0 else -0.01
                best_cand = None
                best_rem = abs(diff)
                for ip in lines_sorted:
                    new_rate = round2(ip["selling_rate"] + step)
                    if new_rate <= ip["purchase_rate"]:
                        continue
                    new_tax = round2(ip["quantity"] * new_rate)
                    delta = round2(new_tax - ip["taxable_amount"])
                    new_diff = round2(diff - delta)
                    if abs(new_diff) < best_rem:
                        best_rem = abs(new_diff)
                        best_cand = (ip, new_rate, new_tax, new_diff)
                        if abs(new_diff) < 0.001:
                            break
                if best_cand:
                    ip, new_rate, new_tax, new_diff = best_cand
                    ip["selling_rate"] = new_rate
                    ip["taxable_amount"] = new_tax
                    diff = new_diff
                else:
                    break

            # If any tiny residual paisa remains (e.g. 0.01), absorb on any unit quantity or single item
            if abs(diff) > 0.0001:
                one_items = [ip for ip in all_lines if abs(ip["quantity"] - 1.0) < 0.001]
                target_ip = one_items[0] if one_items else min(all_lines, key=lambda ip: ip["quantity"])
                target_ip["selling_rate"] = round2(target_ip["selling_rate"] + diff / target_ip["quantity"])
                target_ip["taxable_amount"] = round2(target_ip["quantity"] * target_ip["selling_rate"])
                diff = 0.0

        bills = []
        for bill_idx in range(n_bills):
            assigned = bills_raw[bill_idx]
            if not assigned:
                continue

            bill_items = []
            subtotal = 0.0
            total_cgst = 0.0
            total_sgst = 0.0
            p_bill_total = 0.0

            for ip in assigned:
                p_rate = ip["purchase_rate"]
                qty = ip["quantity"]
                sell_rate = ip["selling_rate"]
                taxable = ip["taxable_amount"]
                p_bill_total += p_rate * qty

                if self.tax_scheme == "composition":
                    gst_r = 0.0
                    cgst_r = 0.0
                    sgst_r = 0.0
                else:
                    gst_r = float(ip["item"]["gst_rate"] or 0.0)
                    cgst_r = round2(gst_r / 2.0)
                    sgst_r = round2(gst_r / 2.0)

                cgst = round2(taxable * cgst_r / 100.0)
                sgst = round2(taxable * sgst_r / 100.0)
                total = round2(taxable + cgst + sgst)

                subtotal += taxable
                total_cgst += cgst
                total_sgst += sgst

                margin = round(((sell_rate - p_rate) / max(p_rate, 0.01)) * 100.0, 1)

                bill_items.append({
                    "purchase_item_id": ip["item"]["purchase_item_id"],
                    "item_name": ip["item"]["item_name"],
                    "hsn_code": ip["item"]["hsn_code"],
                    "quantity": qty,
                    "unit": ip["item"]["unit"],
                    "purchase_rate": p_rate,
                    "selling_rate": sell_rate,
                    "gst_rate": gst_r,
                    "cgst_rate": cgst_r,
                    "sgst_rate": sgst_r,
                    "cgst_amount": cgst,
                    "sgst_amount": sgst,
                    "taxable_amount": taxable,
                    "total_amount": total,
                    "margin_pct": margin,
                })

            grand_total = round2(subtotal + total_cgst + total_sgst)
            avg_margin = round((subtotal - p_bill_total) / p_bill_total * 100.0, 1) if p_bill_total > 0 else 0.0

            if customer_mode == "cash":
                customer_name = (cash_name or "Cash Bill").strip() or "Cash Bill"
                city = ""
            else:
                customer_name = (
                    customers[bill_idx]
                    if bill_idx < len(customers)
                    else name_gen.generate_name(month, year)
                )
                city = name_gen.get_city() if name_gen else ""

            bills.append({
                "bill_date": bill_dates[bill_idx] if bill_idx < len(bill_dates) else date(year, month, 1),
                "customer": {
                    "name": customer_name,
                    "city": city,
                    "phone": "",
                    "address": "",
                },
                "items": bill_items,
                "subtotal": round2(subtotal),
                "total_cgst": round2(total_cgst),
                "total_sgst": round2(total_sgst),
                "grand_total": grand_total,
                "bill_type": self.tax_scheme,
                "margin_avg": avg_margin,
            })

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
        sell_multiplier: float = None,
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
                    if self.margin_type == "target_profit":
                        multiplier = sell_multiplier or getattr(self, "_target_multiplier", None) or 1.0
                        sell_rate = round2(item["purchase_rate"] * multiplier)
                        margin = round(
                            ((sell_rate - item["purchase_rate"]) /
                             max(item["purchase_rate"], 0.01)) * 100,
                            1,
                        )
                        gst_r = float(item["gst_rate"] or 0.0)
                        cgst_r = round2(gst_r / 2.0)
                        sgst_r = round2(gst_r / 2.0)
                    else:
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
        candidate_count = min(len(available), max(n_items * 2, 6))
        candidates = available[:candidate_count]
        chosen_items = random.sample(candidates, min(n_items, len(candidates)))

        # Bills remaining after this one
        bills_left = n_bills - bill_idx

        for item in chosen_items:
            if item["remaining"] < 0.001:
                continue

            min_q = self._min_qty(item["unit"])

            # If remaining stock is small or few bills left, finish the item
            if bills_left <= 2 or item["remaining"] <= min_q * 2 or (
                item["remaining"] <= item["original_qty"] * 0.35 and random.random() < 0.4
            ):
                qty = round(item["remaining"], 3)
            else:
                fraction = random.uniform(0.25, 0.60)
                raw_qty = item["remaining"] * fraction
                qty = self._round_quantity(
                    raw_qty, item["unit"]
                )
                qty = max(qty, min_q)
                qty = min(qty, item["remaining"])
                if item["remaining"] - qty < min_q:
                    qty = round(item["remaining"], 3)

            if qty < 0.001:
                continue

            # Calculate prices
            if self.margin_type == "target_profit" and sell_multiplier is not None:
                sell_rate = round2(item["purchase_rate"] * sell_multiplier)
                margin = round(
                    ((sell_rate - item["purchase_rate"]) /
                     max(item["purchase_rate"], 0.01)) * 100,
                    1,
                )
                gst_r = float(item["gst_rate"] or 0.0)
                cgst_r = round2(gst_r / 2.0)
                sgst_r = round2(gst_r / 2.0)
            else:
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

        if unit_lower in (
            "piece", "pieces", "pcs", "pc", "nos", "no",
            "bottle", "bottles", "can", "cans", "box", "boxes",
            "bag", "bags", "set", "sets", "pkt", "packet", "packets",
            "roll", "rolls", "drum", "drums", "bundle", "bundles"
        ):
            # Whole units for count items
            return float(max(1, round(qty)))

        elif unit_lower in ("meter", "meters", "metre", "metres", "mtr", "mtrs"):
            # Whole integer meters for pipes and cables >= 10m
            if qty >= 10:
                return float(round(qty))
            elif qty >= 1:
                return float(round(qty, 1))
            else:
                return float(round(qty, 2))

        elif unit_lower in ("kg", "kilogram", "kgs", "kilograms"):
            if qty >= 20:
                return float(round(qty))
            elif qty >= 1:
                return float(round(qty, 1))
            else:
                return float(round(qty, 2))

        elif unit_lower in ("liter", "litre", "ltr", "liters", "litres", "ltrs"):
            if qty >= 10:
                return float(round(qty))
            elif qty >= 1:
                return float(round(qty, 1))
            else:
                return float(round(qty, 2))

        else:
            return float(round(qty, 2))

    def _min_qty(self, unit: str) -> float:
        """Minimum meaningful quantity per unit"""
        unit_lower = unit.lower()
        if unit_lower in (
            "piece", "pieces", "pcs", "pc", "nos", "no",
            "bottle", "bottles", "can", "cans", "box", "boxes",
            "bag", "bags", "set", "sets", "pkt", "packet", "packets",
            "roll", "rolls", "drum", "drums", "bundle", "bundles"
        ):
            return 1.0
        elif unit_lower in ("meter", "meters", "metre", "metres", "mtr", "mtrs"):
            return 1.0
        elif unit_lower in ("kg", "kilogram", "kgs", "kilograms"):
            return 0.5
        elif unit_lower in ("liter", "litre", "ltr", "liters", "litres", "ltrs"):
            return 0.5
        return 1.0

    def verify_tally(
        self,
        month: int = None,
        year: int = None,
        generated_bills: list = None,
        start_date: date = None,
        end_date: date = None,
        pool: list = None,
    ) -> dict:
        """
        Verify that generated bills account for purchased items.
        Supports continuous inventory carry-forward and custom date ranges.
        """
        generated_bills = generated_bills or []
        if start_date is None or end_date is None:
            if month is not None and year is not None:
                start_date, end_date = get_month_dates(year, month)
            else:
                today = date.today()
                start_date, end_date = get_month_dates(today.year, today.month)

        # Generated bills totals
        s_taxable = round2(sum(b["subtotal"] for b in generated_bills))
        s_cgst    = round2(sum(b["total_cgst"] for b in generated_bills))
        s_sgst    = round2(sum(b["total_sgst"] for b in generated_bills))
        s_total   = round2(sum(b["grand_total"] for b in generated_bills))
        s_gst     = round2(s_cgst + s_sgst)

        batch_p_taxable = round2(sum(
            float(it["purchase_rate"]) * float(it["quantity"])
            for bill in generated_bills
            for it in bill["items"]
        ))
        batch_p_gst = round2(sum(
            float(it["purchase_rate"]) * float(it["quantity"]) * float(it.get("gst_rate", 0)) / 100.0
            for bill in generated_bills
            for it in bill["items"]
        ))

        # Item tally
        item_totals = defaultdict(float)
        for bill in generated_bills:
            for item in bill["items"]:
                key = item["item_name"].lower()
                item_totals[key] += float(item["quantity"])

        if pool is None:
            pool = self.get_purchase_pool(
                month=month,
                year=year,
                start_date=start_date,
                end_date=end_date,
                include_carried_forward=True,
            )

        item_tally = []
        all_tallied = True

        for pi in pool:
            key       = pi["item_name"].lower()
            available = float(pi["remaining_qty"])
            sold      = round(item_totals.get(key, 0.0), 3)
            diff      = round(available - sold, 3)
            ok        = (sold <= available + 0.01) and (diff >= -0.01)

            if not ok:
                all_tallied = False

            item_tally.append({
                "item_name": pi["item_name"],
                "unit":      pi["unit"],
                "purchased": available,
                "sold":      sold,
                "diff":      diff,
                "ok":        ok,
            })

        profit = round2(s_taxable - batch_p_taxable)
        gst_payable = round2(max(0.0, s_gst - batch_p_gst))

        return {
            "purchase_taxable": batch_p_taxable,
            "purchase_gst":     batch_p_gst,
            "purchase_total":   round2(batch_p_taxable + batch_p_gst),
            "sales_taxable":    s_taxable,
            "sales_gst":        s_gst,
            "sales_cgst":       s_cgst,
            "sales_sgst":       s_sgst,
            "sales_total":      s_total,
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
        self.var_date_preset = tk.StringVar(value="This Month")
        first_d, last_d = get_date_range_for_preset("This Month")
        self.var_filter_from = tk.StringVar(value=format_date_display(first_d))
        self.var_filter_to = tk.StringVar(value=format_date_display(last_d))

        self.filter_month = tk.IntVar(value=today.month)
        self.filter_year  = tk.IntVar(value=today.year)
        self.var_start_date = tk.StringVar(value=format_date_display(first_d))
        self.var_end_date = tk.StringVar(value=format_date_display(last_d))

        # Carry-forward & stock allocation controls
        self.var_include_carried_forward = tk.BooleanVar(value=True)
        self.var_allocation_mode = tk.StringVar(value="all")  # "all", "target_amount", "percentage"
        self.var_target_sales_amount = tk.DoubleVar(value=100000.0)
        self.var_stock_percentage = tk.DoubleVar(value=50.0)

        # Split configuration vars
        self.var_n_bills      = tk.IntVar(value=10)
        self.var_min_items    = tk.IntVar(value=2)
        self.var_max_items    = tk.IntVar(value=8)
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
        self.var_flat_markup_amount = tk.DoubleVar(
            value=self.settings["billing"].get(
                "flat_markup_amount", 5.0
            )
        )
        self.var_target_profit_amount = tk.DoubleVar(
            value=self.settings["billing"].get(
                "target_profit_amount", 0.0
            )
        )
        self.var_bill_type = tk.StringVar(
            value=self.settings["billing"].get(
                "tax_scheme", "regular"
            )
        )
        self.var_customer_mode = tk.StringVar(value="random")  # "random" or "cash"
        self.var_cash_name     = tk.StringVar(value="Cash Bill")

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
        canvas.bind_all(
            "<Button-4>",
            lambda e: canvas.yview_scroll(-1, "units")
        )
        canvas.bind_all(
            "<Button-5>",
            lambda e: canvas.yview_scroll(1, "units")
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

        # Right — Date filter controls
        right = tk.Frame(top, bg=COLORS["bg_main"])
        right.pack(side="right")

        tk.Label(
            right,
            text="Preset:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(0, 4))

        preset_cb = ttk.Combobox(
            right,
            values=DATE_PRESETS,
            textvariable=self.var_date_preset,
            width=17,
            font=FONTS["body"],
            state="readonly"
        )
        preset_cb.pack(side="left", padx=3)
        preset_cb.bind("<<ComboboxSelected>>", lambda e: self._on_preset_change())

        tk.Label(
            right,
            text="From:",
            font=FONTS["small"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(8, 2))

        tk.Entry(
            right,
            textvariable=self.var_filter_from,
            font=FONTS["body"],
            width=11,
            relief="solid", bd=1
        ).pack(side="left", padx=2)

        tk.Label(
            right,
            text="To:",
            font=FONTS["small"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(6, 2))

        tk.Entry(
            right,
            textvariable=self.var_filter_to,
            font=FONTS["body"],
            width=11,
            relief="solid", bd=1
        ).pack(side="left", padx=2)

        tk.Button(
            right,
            text="🔍 Apply",
            font=FONTS["small"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=10, pady=3,
            cursor="hand2",
            command=self._apply_custom_filter
        ).pack(side="left", padx=(8, 0))

    def _on_preset_change(self):
        preset = self.var_date_preset.get()
        if preset != "Custom Range":
            s_date, e_date = get_date_range_for_preset(preset)
            self.var_filter_from.set(format_date_display(s_date))
            self.var_filter_to.set(format_date_display(e_date))
            self.var_start_date.set(format_date_display(s_date))
            self.var_end_date.set(format_date_display(e_date))
            self.filter_month.set(s_date.month)
            self.filter_year.set(s_date.year)
        self._load_data()

    def _apply_custom_filter(self):
        s_date = parse_flexible_date(self.var_filter_from.get())
        e_date = parse_flexible_date(self.var_filter_to.get())
        if s_date and e_date:
            if s_date > e_date:
                s_date, e_date = e_date, s_date
                self.var_filter_from.set(format_date_display(s_date))
                self.var_filter_to.set(format_date_display(e_date))
            self.var_start_date.set(format_date_display(s_date))
            self.var_end_date.set(format_date_display(e_date))
            self.filter_month.set(s_date.month)
            self.filter_year.set(s_date.year)
        self._load_data()

    def _on_filter_change(self, month_name, year_str):
        if month_name:
            self.filter_month.set(
                MONTH_NAMES.index(month_name)
            )
        if year_str:
            self.filter_year.set(int(year_str))
        self._refresh_date_range_defaults()
        self._load_data()

    def _refresh_date_range_defaults(self):
        """Reset the generated-sales date range to the current preset or month."""
        s_date, e_date = get_date_range_for_preset(self.var_date_preset.get())
        self.var_start_date.set(format_date_display(s_date))
        self.var_end_date.set(format_date_display(e_date))

    # ----------------------------------------------------------
    # GENERATE PANEL
    # ----------------------------------------------------------
    def _build_generate_panel(self, parent):
        """Left panel: purchase pool + split config"""

        # ---- Purchase Pool Summary ----
        pool_card = tk.Frame(
            parent,
            bg=COLORS["bg_card"],
            padx=12, pady=8
        )
        pool_card.pack(fill="x", pady=(0, 6))

        self.pool_title_lbl = tk.Label(
            pool_card,
            text="📦 Stock Inventory Pool",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        )
        self.pool_title_lbl.pack(anchor="w", pady=(0, 4))

        self.pool_info_frame = tk.Frame(
            pool_card, bg=COLORS["bg_card"]
        )
        self.pool_info_frame.pack(fill="x")

        # ---- Split Configuration ----
        config_card = tk.Frame(
            parent,
            bg=COLORS["bg_card"],
            padx=12, pady=8
        )
        config_card.pack(fill="x", pady=(0, 6))

        tk.Label(
            config_card,
            text="⚙️ Split Configuration",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 6))

        # Number of bills
        row1 = tk.Frame(
            config_card, bg=COLORS["bg_card"]
        )
        row1.pack(fill="x", pady=2)

        tk.Label(
            row1,
            text="Number of Sales Bills:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            width=24,
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
        row2.pack(fill="x", pady=2)

        tk.Label(
            row2,
            text="Items per Bill (Min):",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            width=24, anchor="w"
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
        row3.pack(fill="x", pady=2)

        tk.Label(
            row3,
            text="Bill Type:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            width=24, anchor="w"
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

        # Customer Naming (Random Names vs Cash Bills)
        cust_frame = tk.Frame(
            config_card,
            bg="#fdf8f0",
            padx=8, pady=5
        )
        cust_frame.pack(fill="x", pady=(0, 5))

        tk.Label(
            cust_frame,
            text="👤 Customer Naming",
            font=FONTS["label_bold"],
            bg="#fdf8f0",
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 2))

        cust_row = tk.Frame(cust_frame, bg="#fdf8f0")
        cust_row.pack(fill="x", pady=1)

        tk.Radiobutton(
            cust_row,
            text="Random Names",
            variable=self.var_customer_mode,
            value="random",
            font=FONTS["small"],
            bg="#fdf8f0",
            activebackground="#fdf8f0",
            command=self._on_customer_mode_change
        ).pack(side="left", padx=(0, 8))

        tk.Radiobutton(
            cust_row,
            text="Cash Bills",
            variable=self.var_customer_mode,
            value="cash",
            font=FONTS["small"],
            bg="#fdf8f0",
            activebackground="#fdf8f0",
            command=self._on_customer_mode_change
        ).pack(side="left", padx=(0, 6))

        self.cash_name_label = tk.Label(
            cust_row,
            text="Name:",
            font=FONTS["small"],
            bg="#fdf8f0",
            fg=COLORS["text_muted"]
        )
        self.cash_name_label.pack(side="left", padx=(6, 2))

        self.cash_name_ent = tk.Entry(
            cust_row,
            textvariable=self.var_cash_name,
            font=FONTS["body"],
            width=11,
            relief="solid", bd=1,
            state="disabled"
        )
        self.cash_name_ent.pack(side="left")

        # Date range for generated sales bills
        date_range_frame = tk.Frame(
            config_card,
            bg="#eef8ff",
            padx=8, pady=5
        )
        date_range_frame.pack(fill="x", pady=(0, 5))

        tk.Label(
            date_range_frame,
            text="📅 Sales Date Range",
            font=FONTS["label_bold"],
            bg="#eef8ff",
            fg=COLORS["primary"]
        ).pack(anchor="w", pady=(0, 3))

        date_row = tk.Frame(date_range_frame, bg="#eef8ff")
        date_row.pack(fill="x", pady=1)

        tk.Label(
            date_row,
            text="From:",
            font=FONTS["small"],
            bg="#eef8ff",
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Entry(
            date_row,
            textvariable=self.var_start_date,
            font=FONTS["body"],
            width=11,
            relief="solid", bd=1
        ).pack(side="left", padx=(5, 10))

        tk.Label(
            date_row,
            text="To:",
            font=FONTS["small"],
            bg="#eef8ff",
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Entry(
            date_row,
            textvariable=self.var_end_date,
            font=FONTS["body"],
            width=11,
            relief="solid", bd=1
        ).pack(side="left", padx=(5, 0))

        # Stock Allocation & Carry Forward
        alloc_frame = tk.Frame(
            config_card,
            bg="#f0fff4",
            padx=8, pady=5
        )
        alloc_frame.pack(fill="x", pady=(0, 5))

        tk.Label(
            alloc_frame,
            text="📦 Stock Allocation",
            font=FONTS["label_bold"],
            bg="#f0fff4",
            fg=COLORS["success"]
        ).pack(anchor="w", pady=(0, 2))

        tk.Checkbutton(
            alloc_frame,
            text="Include Unsold Stock from earlier purchases",
            variable=self.var_include_carried_forward,
            font=FONTS["small"],
            bg="#f0fff4",
            activebackground="#f0fff4",
        ).pack(anchor="w", pady=(0, 2))

        alloc_row = tk.Frame(alloc_frame, bg="#f0fff4")
        alloc_row.pack(fill="x", pady=1)

        for val, lbl in [
            ("all", "All Stock"),
            ("target_amount", "Target Rupee ₹"),
            ("percentage", "Stock %"),
        ]:
            tk.Radiobutton(
                alloc_row,
                text=lbl,
                variable=self.var_allocation_mode,
                value=val,
                font=FONTS["small"],
                bg="#f0fff4",
                activebackground="#f0fff4",
                command=self._on_allocation_mode_change
            ).pack(side="left", padx=(0, 6))

        self.alloc_target_frame = tk.Frame(alloc_frame, bg="#f0fff4")
        tk.Label(
            self.alloc_target_frame,
            text="Target Sales Amount ₹:",
            font=FONTS["small"],
            bg="#f0fff4",
            fg=COLORS["text_dark"]
        ).pack(side="left")
        tk.Entry(
            self.alloc_target_frame,
            textvariable=self.var_target_sales_amount,
            font=FONTS["body"],
            width=10,
            relief="solid", bd=1
        ).pack(side="left", padx=5)

        self.alloc_pct_frame = tk.Frame(alloc_frame, bg="#f0fff4")
        tk.Label(
            self.alloc_pct_frame,
            text="Sell Stock %:",
            font=FONTS["small"],
            bg="#f0fff4",
            fg=COLORS["text_dark"]
        ).pack(side="left")
        tk.Entry(
            self.alloc_pct_frame,
            textvariable=self.var_stock_percentage,
            font=FONTS["body"],
            width=5,
            relief="solid", bd=1
        ).pack(side="left", padx=5)

        self._on_allocation_mode_change()

        # Margin settings
        margin_frame = tk.Frame(
            config_card,
            bg="#f0f4ff",
            padx=8, pady=5
        )
        margin_frame.pack(fill="x", pady=4)

        tk.Label(
            margin_frame,
            text="💰 Profit Margin Settings",
            font=FONTS["label_bold"],
            bg="#f0f4ff",
            fg=COLORS["primary"]
        ).pack(anchor="w", pady=(0, 3))

        # Margin type
        m_row = tk.Frame(margin_frame, bg="#f0f4ff")
        m_row.pack(fill="x", pady=1)

        for val, lbl in [
            ("range",    "Random Range"),
            ("global",   "Fixed Global %"),
            ("flat",     "Fixed Rupee Markup"),
            ("target_profit", "Target Profit ₹"),
            ("itemwise", "Item-wise"),
        ]:
            tk.Radiobutton(
                m_row,
                text=lbl,
                variable=self.var_margin_type,
                value=val,
                font=FONTS["small"],
                bg="#f0f4ff",
                activebackground="#f0f4ff",
                command=self._on_margin_type_change
            ).pack(side="left", padx=(0, 8))

        # Range inputs
        self.range_inputs = tk.Frame(
            margin_frame, bg="#f0f4ff"
        )
        self.range_inputs.pack(fill="x", pady=2)

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
            width=5,
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
            width=5,
            relief="solid", bd=1
        ).pack(side="left", padx=3)

        # Global input
        self.global_input = tk.Frame(
            margin_frame, bg="#f0f4ff"
        )
        self.global_input.pack(fill="x", pady=2)

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
            width=5,
            relief="solid", bd=1
        ).pack(side="left", padx=3)

        # Flat markup input
        self.flat_input = tk.Frame(
            margin_frame, bg="#f0f4ff"
        )
        self.flat_input.pack(fill="x", pady=2)

        tk.Label(
            self.flat_input,
            text="Flat Markup ₹:",
            font=FONTS["small"],
            bg="#f0f4ff",
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Entry(
            self.flat_input,
            textvariable=self.var_flat_markup_amount,
            font=FONTS["body"],
            width=6,
            relief="solid", bd=1
        ).pack(side="left", padx=3)

        # Target profit input
        self.target_profit_input = tk.Frame(
            margin_frame, bg="#f0f4ff"
        )
        self.target_profit_input.pack(fill="x", pady=2)

        tk.Label(
            self.target_profit_input,
            text="Target Profit ₹:",
            font=FONTS["small"],
            bg="#f0f4ff",
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Entry(
            self.target_profit_input,
            textvariable=self.var_target_profit_amount,
            font=FONTS["body"],
            width=8,
            relief="solid", bd=1
        ).pack(side="left", padx=3)

        self._on_margin_type_change()

        # ---- Generate Button ----
        self.generate_button = tk.Button(
            parent,
            text="⚡ Generate Sales Bills",
            font=FONTS["button"],
            bg=COLORS["accent"],
            fg="white",
            relief="flat",
            padx=15, pady=10,
            cursor="hand2",
            command=self._generate_bills
        )
        self.generate_button.pack(fill="x", pady=(3, 2))
        self._set_generate_enabled(True)

        # Action buttons row (Check Tally & Export CSV side-by-side)
        btn_row = tk.Frame(parent, bg=COLORS["bg_main"])
        btn_row.pack(fill="x", pady=2)

        tk.Button(
            btn_row,
            text="📊 Check Tally",
            font=FONTS["label_bold"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=10, pady=7,
            cursor="hand2",
            command=self._check_tally
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))

        tk.Button(
            btn_row,
            text="📁 Export Bills CSV",
            font=FONTS["label_bold"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=10, pady=7,
            cursor="hand2",
            command=self._export_csv
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))

    def _parse_date_input(self, value: str, label: str) -> date:
        """Parse DD-MM-YYYY, DD/MM/YYYY, or YYYY-MM-DD strings from the UI."""
        parsed = parse_flexible_date(value)
        if not parsed:
            raise ValueError(f"{label} is required and must be a valid date.")
        return parsed

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

        # Flat input
        for child in self.flat_input.winfo_children():
            try:
                child.configure(
                    state="normal"
                    if mtype == "flat"
                    else "disabled"
                )
            except Exception:
                pass

        # Target profit input
        for child in self.target_profit_input.winfo_children():
            try:
                child.configure(
                    state="normal"
                    if mtype == "target_profit"
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
    def _on_allocation_mode_change(self):
        """Show/hide target amount and percentage entries based on allocation mode."""
        mode = self.var_allocation_mode.get()
        if hasattr(self, "alloc_target_frame") and hasattr(self, "alloc_pct_frame"):
            if mode == "target_amount":
                self.alloc_target_frame.pack(fill="x", pady=2)
                self.alloc_pct_frame.pack_forget()
            elif mode == "percentage":
                self.alloc_pct_frame.pack(fill="x", pady=2)
                self.alloc_target_frame.pack_forget()
            else:
                self.alloc_target_frame.pack_forget()
                self.alloc_pct_frame.pack_forget()

    def _on_customer_mode_change(self):
        """Enable/disable custom cash name entry based on customer mode."""
        is_cash = (self.var_customer_mode.get() == "cash")
        state = "normal" if is_cash else "disabled"
        if hasattr(self, "cash_name_ent"):
            self.cash_name_ent.configure(state=state)
        if hasattr(self, "cash_name_label"):
            fg = COLORS["text_dark"] if is_cash else COLORS["text_muted"]
            self.cash_name_label.configure(fg=fg)

    def _load_data(self):
        """Load purchase pool and existing sales bills"""
        month = self.filter_month.get()
        year  = self.filter_year.get()

        self._load_pool_summary(month, year)
        self._load_existing_bills(month, year)

    def _set_generate_enabled(self, enabled: bool):
        """Keep the action visible and usable even if the selected month is empty."""
        if hasattr(self, "generate_button"):
            self.generate_button.configure(
                state="normal",
                bg=COLORS["accent"],
                fg="white"
            )

    def _load_pool_summary(self, month: int = None, year: int = None):
        """Show purchase pool summary with carried-forward stock details"""
        for w in self.pool_info_frame.winfo_children():
            w.destroy()

        s_date = parse_flexible_date(self.var_filter_from.get())
        e_date = parse_flexible_date(self.var_filter_to.get())
        if not s_date or not e_date:
            s_date, e_date = get_date_range_for_preset("This Month")

        s_str = s_date.strftime("%Y-%m-%d")
        e_str = e_date.strftime("%Y-%m-%d")

        preset = self.var_date_preset.get() if hasattr(self, "var_date_preset") else "Current Period"
        if hasattr(self, "pool_title_lbl") and self.pool_title_lbl:
            self.pool_title_lbl.config(text=f"📦 Stock Inventory Pool ({preset})")

        # 1. Carried-forward unsold purchases (before s_date)
        carried = db.query_one("""
            SELECT
                COUNT(DISTINCT pb.id) AS bill_count,
                COUNT(pi.id) AS item_count,
                COALESCE(SUM(pi.remaining_qty), 0) AS remaining_qty,
                COALESCE(SUM(pi.remaining_qty * pi.purchase_rate), 0) AS valuation
            FROM purchase_items pi
            JOIN purchase_bills pb ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_date < ? AND pi.remaining_qty > 0.0001
        """, (s_str,))

        # 2. Purchases in selected date range (queried directly from purchase_bills)
        period_bills = db.query_one("""
            SELECT
                COUNT(*) AS bill_count,
                COALESCE(SUM(subtotal), 0) AS purchase_taxable,
                COALESCE(SUM(grand_total), 0) AS purchase_total
            FROM purchase_bills
            WHERE bill_date >= ? AND bill_date <= ?
        """, (s_str, e_str))

        # Items in selected date range
        period_items = db.query_one("""
            SELECT
                COUNT(pi.id) AS item_count,
                COALESCE(SUM(pi.quantity), 0) AS total_qty,
                COALESCE(SUM(pi.remaining_qty), 0) AS remaining_qty,
                COALESCE(SUM(pi.remaining_qty * pi.purchase_rate), 0) AS valuation
            FROM purchase_items pi
            JOIN purchase_bills pb ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_date >= ? AND pb.bill_date <= ?
        """, (s_str, e_str))

        # 3. Total active stock available (carried forward + period)
        total_active_val = (carried.get("valuation", 0) or 0) + (period_items.get("valuation", 0) or 0)
        total_active_qty = (carried.get("remaining_qty", 0) or 0) + (period_items.get("remaining_qty", 0) or 0)
        total_active_items = (carried.get("item_count", 0) or 0) + (period_items.get("item_count", 0) or 0)

        if total_active_items == 0:
            tk.Label(
                self.pool_info_frame,
                text="⚠️  No active stock available.\n"
                     "Add purchase bills first or expand date range.",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["warning"]
            ).pack(pady=10)
            self._set_generate_enabled(True)
            return

        self._set_generate_enabled(True)

        items = [
            ("Carried Forward:", f"₹{carried.get('valuation', 0):,.2f}",
             "Stock:", f"{carried.get('remaining_qty', 0):.1f} units"),
            ("New Purchases:",   f"₹{period_bills.get('purchase_taxable', 0):,.2f}",
             "Bills:", f"{period_bills.get('bill_count', 0)} bills"),
            ("Total Stock Value:", f"₹{total_active_val:,.2f}",
             "Available:", f"{total_active_qty:.1f} units"),
        ]

        for l1, v1, l2, v2 in items:
            row = tk.Frame(self.pool_info_frame, bg=COLORS["bg_card"])
            row.pack(fill="x", pady=1)

            tk.Label(
                row, text=l1,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"],
                width=16, anchor="w"
            ).pack(side="left")

            tk.Label(
                row, text=v1,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=COLORS["primary"],
                width=13, anchor="w"
            ).pack(side="left")

            tk.Label(
                row, text=l2,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"],
                width=10, anchor="w"
            ).pack(side="left")

            tk.Label(
                row, text=v2,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=COLORS["primary"],
                anchor="w"
            ).pack(side="left")

    def _load_existing_bills(self, month: int = None, year: int = None):
        """Load and display existing sales bills within the selected date range"""
        for w in self.bills_body.winfo_children():
            w.destroy()

        preset = self.var_date_preset.get()
        if preset == "All Time":
            bills = db.query("""
                SELECT
                    sb.*,
                    (SELECT COUNT(*) FROM sales_items si
                     WHERE si.sales_bill_id = sb.id
                    ) AS item_count
                FROM sales_bills sb
                ORDER BY sb.bill_date DESC, sb.bill_number DESC
            """)
        else:
            s_date = parse_flexible_date(self.var_filter_from.get())
            e_date = parse_flexible_date(self.var_filter_to.get())
            if not s_date or not e_date:
                s_date, e_date = get_date_range_for_preset("This Month")
            s_str = s_date.strftime("%Y-%m-%d")
            e_str = e_date.strftime("%Y-%m-%d")

            bills = db.query("""
                SELECT
                    sb.*,
                    (SELECT COUNT(*) FROM sales_items si
                     WHERE si.sales_bill_id = sb.id
                    ) AS item_count
                FROM sales_bills sb
                WHERE sb.bill_date >= ? AND sb.bill_date <= ?
                ORDER BY sb.bill_date DESC, sb.bill_number DESC
            """, (s_str, e_str))

        if bills:
            total = sum(b["grand_total"] for b in bills)
            self.existing_summary.configure(
                text=f"  {len(bills)} bills  |  Total: ₹{total:,.2f}",
                bg=COLORS["success_light"],
                fg=COLORS["success"]
            )
        else:
            self.existing_summary.configure(
                text="  No sales bills generated yet for this period.",
                bg=COLORS["warning_light"],
                fg=COLORS["warning"]
            )

        if not bills:
            tk.Label(
                self.bills_body,
                text="No sales bills for this period.\nUse the Generate panel on the left.",
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

        try:
            start_date = self._parse_date_input(
                self.var_start_date.get(), "Start date"
            )
            end_date = self._parse_date_input(
                self.var_end_date.get(), "End date"
            )
            if start_date > end_date:
                start_date, end_date = end_date, start_date
                self.var_start_date.set(format_date_display(start_date))
                self.var_end_date.set(format_date_display(end_date))
        except ValueError as exc:
            messagebox.showerror("Date Error", str(exc))
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

        # Check for existing bills within this date range
        s_str = start_date.strftime("%Y-%m-%d")
        e_str = end_date.strftime("%Y-%m-%d")
        existing = db.query_one("""
            SELECT COUNT(*) AS cnt
            FROM sales_bills
            WHERE bill_date >= ? AND bill_date <= ?
        """, (s_str, e_str))

        if existing.get("cnt", 0) > 0:
            if not messagebox.askyesno(
                "Bills Exist",
                f"{existing['cnt']} sales bills already exist between "
                f"{format_date_display(start_date)} and {format_date_display(end_date)}.\n\n"
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
                month=start_date.month,
                year=start_date.year,
                n_bills=n_bills,
                min_items_per_bill=min_items,
                max_items_per_bill=max_items,
                override_margin_type=
                    self.var_margin_type.get(),
                override_margin_min=margin_min,
                override_margin_max=margin_max,
                override_margin_global=
                    self.var_margin_global.get(),
                override_flat_markup_amount=
                    self.var_flat_markup_amount.get(),
                override_target_profit_amount=
                    self.var_target_profit_amount.get(),
                start_date=start_date,
                end_date=end_date,
                include_carried_forward=
                    self.var_include_carried_forward.get(),
                allocation_mode=
                    self.var_allocation_mode.get(),
                target_sales_amount=
                    self.var_target_sales_amount.get(),
                stock_percentage=
                    self.var_stock_percentage.get(),
                customer_mode=
                    self.var_customer_mode.get(),
                cash_name=
                    self.var_cash_name.get().strip(),
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
                start_date=start_date,
                end_date=end_date,
                generated_bills=bills,
            )

            # Store for later use
            self.pending_bills = bills
            self._current_splitter = splitter

            # Show preview
            BillPreviewDialog(
                self,
                bills=bills,
                tally=tally,
                month=start_date.month,
                year=start_date.year,
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
                    bill_date_str = bill_date.strftime("%Y-%m-%d")
                    b_month = bill_date.month
                    b_year = bill_date.year
                else:
                    bd = parse_flexible_date(str(bill_date))
                    bill_date_str = bd.strftime("%Y-%m-%d") if bd else str(bill_date)
                    b_month = bd.month if bd else self.filter_month.get()
                    b_year = bd.year if bd else self.filter_year.get()

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
                    b_month, b_year,
                    bill["subtotal"],
                    bill["total_cgst"],
                    bill["total_sgst"],
                    bill["grand_total"],
                    bill["bill_type"],
                    bill["margin_avg"],
                    b_month, b_year
                ))

                # Save items
                for item in bill["items"]:
                    db.execute("""
                        INSERT INTO sales_items
                        (sales_bill_id,
                         purchase_item_id,
                         item_name, item_date,
                         hsn_code, quantity, unit,
                         selling_rate, gst_rate,
                         cgst_rate, sgst_rate,
                         cgst_amount, sgst_amount,
                         total_amount, margin_percent)
                        VALUES
                        (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        sales_bill_id,
                        item["purchase_item_id"],
                        item["item_name"],
                        bill_date_str,
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
                    b_month, b_year,
                    settings
                )

                saved_count += 1

            except Exception as e:
                errors.append(str(e))
                bill_num_mgr.rollback_number()

        # Update monthly summary for all affected months
        affected_months = set()
        for b in bills:
            bd = parse_flexible_date(b["bill_date"])
            if bd:
                affected_months.add((bd.month, bd.year))
        for m, y in affected_months:
            self._update_monthly_summary(m, y)

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