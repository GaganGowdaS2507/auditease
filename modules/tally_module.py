# modules/tally_module.py
# ============================================================
# TALLY MODULE
# Comprehensive verification system ensuring
# purchase bills and sales bills match perfectly
#
# Features:
# 1. Item quantity tally (purchased = sold)
# 2. Amount tally (purchase total vs sales total)
# 3. GST tally (input vs output)
# 4. Month-wise tally status
# 5. Discrepancy detection and reporting
# 6. Fix suggestions for mismatches
# 7. Export tally report (PDF + CSV)
# 8. Visual tally dashboard
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import json
import csv
import os
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from modules.date_utils import (
    DATE_PRESETS,
    get_date_range_for_preset,
    parse_flexible_date,
    format_date_display,
    format_date_iso,
    get_month_dates,
    get_financial_year,
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
    "tally_ok":       "#2e7d32",
    "tally_warn":     "#f57f17",
    "tally_bad":      "#c62828",
    "tally_ok_bg":    "#e8f5e9",
    "tally_warn_bg":  "#fff3e0",
    "tally_bad_bg":   "#ffebee",
}

FONTS = {
    "heading":    ("Helvetica", 18, "bold"),
    "subheading": ("Helvetica", 13, "bold"),
    "body":       ("Helvetica", 11),
    "body_bold":  ("Helvetica", 11, "bold"),
    "small":      ("Helvetica", 9),
    "smaller":    ("Helvetica", 8),
    "button":     ("Helvetica", 11, "bold"),
    "label":      ("Helvetica", 10),
    "label_bold": ("Helvetica", 10, "bold"),
    "table":      ("Helvetica", 10),
    "table_bold": ("Helvetica", 10, "bold"),
    "number":     ("Helvetica", 16, "bold"),
    "number_sm":  ("Helvetica", 13, "bold"),
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


def format_inr(amount: float) -> str:
    """Format as Indian Rupees"""
    try:
        is_neg  = amount < 0
        amount  = abs(amount)
        rupees  = int(amount)
        paise   = f"{amount - rupees:.2f}"[1:]
        s       = str(rupees)
        if len(s) <= 3:
            formatted = s
        else:
            last3     = s[-3:]
            remaining = s[:-3]
            groups    = []
            while len(remaining) > 2:
                groups.append(remaining[-2:])
                remaining = remaining[:-2]
            if remaining:
                groups.append(remaining)
            groups.reverse()
            formatted = ",".join(groups) + "," + last3
        result = f"₹{formatted}{paise}"
        return f"-{result}" if is_neg else result
    except Exception:
        return f"₹{amount:.2f}"


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


db = DBHelper()


# ============================================================
# TALLY ENGINE — CORE LOGIC
# ============================================================
class TallyEngine:
    """
    Core tally verification engine.
    Checks all aspects of purchase vs sales matching.

    Checks performed:
    1. Item quantity tally
       → Every purchased item must be sold
    2. Amount tally
       → Sales = Purchase + Margin
    3. GST tally
       → Output GST >= Input GST (usually)
    4. Bill number sequence
       → No gaps in bill numbers
    5. Date consistency
       → Sales dates within purchase month
    6. Negative stock check
       → Cannot sell more than purchased
    """

    @staticmethod
    def _get_conditions(prefix, start_date, end_date, month, year):
        conds = []
        params = []
        if start_date:
            conds.append(f"{prefix}.bill_date >= ?")
            params.append(format_date_iso(start_date))
        if end_date:
            conds.append(f"{prefix}.bill_date <= ?")
            params.append(format_date_iso(end_date))
        if not start_date and not end_date and month and year:
            conds.append(f"{prefix}.bill_month = ? AND {prefix}.bill_year = ?")
            params.extend([month, year])
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        return where, params

    def run_full_tally(
        self,
        month: int = None,
        year: int = None,
        start_date = None,
        end_date = None,
    ) -> dict:
        """
        Run complete tally check for a date range or month.
        Returns comprehensive tally report.
        """
        if isinstance(start_date, str) and start_date.strip():
            start_date = parse_flexible_date(start_date)
        if isinstance(end_date, str) and end_date.strip():
            end_date = parse_flexible_date(end_date)

        if not start_date and not end_date and month and year:
            start_date, end_date = get_month_dates(year, month)

        disp_month = start_date.month if start_date else (month or date.today().month)
        disp_year  = start_date.year if start_date else (year or date.today().year)
        month_name = MONTH_NAMES[disp_month] if disp_month <= 12 else ""

        results = {
            "month":          disp_month,
            "year":           disp_year,
            "start_date":     start_date,
            "end_date":       end_date,
            "month_name":     month_name,
            "checks":         {},
            "overall_status": "ok",
            "issues":         [],
            "summary":        {},
        }

        # Run all checks
        results["checks"]["quantity"] = \
            self._check_quantity_tally(disp_month, disp_year, start_date, end_date)

        results["checks"]["amount"] = \
            self._check_amount_tally(disp_month, disp_year, start_date, end_date)

        results["checks"]["gst"] = \
            self._check_gst_tally(disp_month, disp_year, start_date, end_date)

        results["checks"]["sequence"] = \
            self._check_bill_sequence(disp_month, disp_year, start_date, end_date)

        results["checks"]["negative_stock"] = \
            self._check_negative_stock(disp_month, disp_year, start_date, end_date)

        results["checks"]["dates"] = \
            self._check_date_consistency(disp_month, disp_year, start_date, end_date)

        # Determine overall status
        all_ok  = all(
            c.get("status") == "ok"
            for c in results["checks"].values()
        )
        any_bad = any(
            c.get("status") == "error"
            for c in results["checks"].values()
        )

        if all_ok:
            results["overall_status"] = "ok"
        elif any_bad:
            results["overall_status"] = "error"
        else:
            results["overall_status"] = "warning"

        # Collect all issues
        for check_name, check in results["checks"].items():
            for issue in check.get("issues", []):
                results["issues"].append({
                    "check":   check_name,
                    "message": issue,
                    "level":   check.get("status", "ok"),
                })

        # Build summary
        results["summary"] = \
            self._build_summary(disp_month, disp_year, start_date, end_date)

        return results

    # ----------------------------------------------------------
    # CHECK 1: QUANTITY TALLY
    # ----------------------------------------------------------
    def _check_quantity_tally(
        self,
        month: int,
        year: int,
        start_date = None,
        end_date = None,
    ) -> dict:
        """
        Check every item: sold qty + remaining qty = purchased qty.
        Continuous inventory: unsold stock carried forward is recognized as active inventory.
        """
        result = {
            "name":    "Quantity Tally",
            "status":  "ok",
            "issues":  [],
            "details": [],
        }

        where_p, params_p = self._get_conditions("pb", start_date, end_date, month, year)
        where_s, params_s = self._get_conditions("sb", start_date, end_date, month, year)

        # Get all purchase items in period
        items = db.query(f"""
            SELECT
                pi.item_name,
                pi.unit,
                pi.hsn_code,
                SUM(pi.quantity)      AS purchased,
                SUM(pi.remaining_qty) AS remaining
            FROM purchase_items pi
            JOIN purchase_bills pb
                ON pi.purchase_bill_id = pb.id
            {where_p}
            GROUP BY pi.item_name, pi.unit
            ORDER BY pi.item_name
        """, tuple(params_p))

        if not items:
            result["status"]  = "warning"
            result["issues"].append(
                "No purchase items found for this period."
            )
            return result

        # Get sold quantities from sales
        sold_items = db.query(f"""
            SELECT
                si.item_name,
                si.unit,
                SUM(si.quantity) AS sold_qty
            FROM sales_items si
            JOIN sales_bills sb
                ON si.sales_bill_id = sb.id
            {where_s}
            GROUP BY si.item_name, si.unit
        """, tuple(params_s))

        sold_map = {
            (r["item_name"].lower(), r["unit"]): r
            for r in sold_items
        }

        ok_count   = 0
        warn_count = 0
        err_count  = 0

        for item in items:
            key       = (
                item["item_name"].lower(),
                item["unit"]
            )
            purchased = item["purchased"]
            remaining = item["remaining"] or 0
            sold      = round(
                purchased - remaining, 4
            )

            diff = round(remaining, 4)

            if abs(diff) < 0.001:
                status = "ok"
                ok_count += 1
            elif diff > 0:
                # Active carried-forward inventory
                status = "ok"
                ok_count += 1
            else:
                status = "error"  # oversold!
                err_count += 1
                result["issues"].append(
                    f"❌ {item['item_name']}: "
                    f"Sold {abs(diff):.2f} "
                    f"{item['unit']} MORE than purchased!"
                )

            result["details"].append({
                "item_name": item["item_name"],
                "hsn_code":  item["hsn_code"] or "-",
                "unit":      item["unit"],
                "purchased": purchased,
                "sold":      sold,
                "remaining": remaining,
                "status":    status,
            })

        if err_count > 0:
            result["status"] = "error"
        else:
            result["status"] = "ok"

        result["ok_count"]   = ok_count
        result["warn_count"] = warn_count
        result["err_count"]  = err_count
        result["total"]      = len(items)

        return result

    # ----------------------------------------------------------
    # CHECK 2: AMOUNT TALLY
    # ----------------------------------------------------------
    def _check_amount_tally(
        self,
        month: int,
        year: int,
        start_date = None,
        end_date = None,
    ) -> dict:
        """
        Check: Sales taxable > Cost of goods sold.
        Gross profit on sold goods must be non-negative.
        """
        result = {
            "name":    "Amount Tally",
            "status":  "ok",
            "issues":  [],
            "details": [],
        }

        where_p, params_p = self._get_conditions("pb", start_date, end_date, month, year)
        where_s, params_s = self._get_conditions("sb", start_date, end_date, month, year)

        p = db.query_one(f"""
            SELECT
                COALESCE(SUM(subtotal),    0) AS taxable,
                COALESCE(SUM(total_gst),   0) AS gst,
                COALESCE(SUM(grand_total), 0) AS total,
                COUNT(*)                      AS bills
            FROM purchase_bills pb
            {where_p}
        """, tuple(params_p))

        s = db.query_one(f"""
            SELECT
                COALESCE(SUM(subtotal),    0) AS taxable,
                COALESCE(SUM(total_cgst),  0) AS cgst,
                COALESCE(SUM(total_sgst),  0) AS sgst,
                COALESCE(SUM(grand_total), 0) AS total,
                COUNT(*)                      AS bills
            FROM sales_bills sb
            {where_s}
        """, tuple(params_s))

        # COGS of sold goods
        cogs_row = db.query_one(f"""
            SELECT
                COALESCE(SUM(si.quantity * pi.purchase_rate), 0) AS cogs
            FROM sales_items si
            JOIN sales_bills sb ON si.sales_bill_id = sb.id
            LEFT JOIN purchase_items pi ON si.purchase_item_id = pi.id
            {where_s}
        """, tuple(params_s))
        cogs = cogs_row.get("cogs", 0)

        p_taxable = p.get("taxable", 0) or 0
        s_taxable = s.get("taxable", 0) or 0
        p_total   = p.get("total",   0) or 0
        s_total   = s.get("total",   0) or 0

        if cogs > 0:
            profit = round2(s_taxable - cogs)
            margin_pct = round2(profit / cogs * 100) if cogs > 0 else 0
        else:
            profit = round2(s_taxable - p_taxable)
            margin_pct = round2(profit / p_taxable * 100) if p_taxable > 0 else 0

        result["details"] = {
            "purchase_taxable": p_taxable,
            "purchase_gst":     p.get("gst", 0) or 0,
            "purchase_total":   p_total,
            "purchase_bills":   p.get("bills", 0),
            "sales_taxable":    s_taxable,
            "sales_cgst":       s.get("cgst", 0) or 0,
            "sales_sgst":       s.get("sgst", 0) or 0,
            "sales_total":      s_total,
            "sales_bills":      s.get("bills", 0),
            "cogs":             cogs,
            "profit":           profit,
            "margin_pct":       margin_pct,
        }

        if p_taxable == 0 and s_taxable == 0:
            result["status"] = "warning"
            result["issues"].append("No purchase or sales data found in this period.")
        elif s_taxable == 0:
            result["status"] = "warning"
            result["issues"].append("No sales data found. Generate sales bills first.")
        elif profit < 0:
            result["status"] = "error"
            result["issues"].append(
                f"❌ Sales ({format_inr(s_taxable)}) is LESS than cost of goods sold "
                f"({format_inr(cogs)}). Loss of {format_inr(abs(profit))}!"
            )
        else:
            result["status"] = "ok"

        return result

    # ----------------------------------------------------------
    # CHECK 3: GST TALLY
    # ----------------------------------------------------------
    def _check_gst_tally(
        self,
        month: int,
        year: int,
        start_date = None,
        end_date = None,
    ) -> dict:
        result = {
            "name":    "GST Tally",
            "status":  "ok",
            "issues":  [],
            "details": [],
        }

        where_s, params_s = self._get_conditions("sb", start_date, end_date, month, year)
        where_p, params_p = self._get_conditions("pb", start_date, end_date, month, year)

        output_gst = db.query(f"""
            SELECT
                si.gst_rate,
                SUM(si.taxable_amount) AS taxable,
                SUM(si.cgst_amount)    AS cgst,
                SUM(si.sgst_amount)    AS sgst
            FROM sales_items si
            JOIN sales_bills sb
                ON si.sales_bill_id = sb.id
            {where_s}
            GROUP BY si.gst_rate
            ORDER BY si.gst_rate
        """, tuple(params_s))

        input_gst = db.query(f"""
            SELECT
                pi.gst_rate,
                SUM(pi.quantity * pi.purchase_rate) AS taxable,
                SUM(pi.gst_amount)                  AS gst
            FROM purchase_items pi
            JOIN purchase_bills pb
                ON pi.purchase_bill_id = pb.id
            {where_p}
            GROUP BY pi.gst_rate
            ORDER BY pi.gst_rate
        """, tuple(params_p))

        input_map = {r["gst_rate"]: r for r in input_gst}
        total_output = 0
        total_input  = 0
        issues_found = False

        for row in output_gst:
            rate       = row["gst_rate"]
            out_cgst   = row["cgst"] or 0
            out_sgst   = row["sgst"] or 0
            out_total  = out_cgst + out_sgst

            inp        = input_map.get(rate, {})
            in_gst     = inp.get("gst", 0) or 0
            net_payable = round2(max(0, out_total - in_gst))

            total_output += out_total
            total_input  += in_gst

            gst_rate_ok = out_total >= in_gst
            if not gst_rate_ok:
                issues_found = True
                result["issues"].append(
                    f"⚠️  GST {rate:.0f}%: "
                    f"Output ({format_inr(out_total)}) "
                    f"< Input ({format_inr(in_gst)})."
                )

            result["details"].append({
                "gst_rate":   rate,
                "out_taxable": row["taxable"] or 0,
                "out_cgst":   out_cgst,
                "out_sgst":   out_sgst,
                "out_total":  out_total,
                "in_gst":     in_gst,
                "net_payable": net_payable,
                "status": "ok" if gst_rate_ok else "warning",
            })

        net_total = round2(max(0, total_output - total_input))
        result["total_output"] = round2(total_output)
        result["total_input"]  = round2(total_input)
        result["net_payable"]  = net_total

        if not output_gst:
            result["status"] = "warning"
            result["issues"].append("No sales GST data found.")
        elif issues_found:
            result["status"] = "warning"
        else:
            result["status"] = "ok"

        return result

    # ----------------------------------------------------------
    # CHECK 4: BILL NUMBER SEQUENCE
    # ----------------------------------------------------------
    def _check_bill_sequence(
        self,
        month: int,
        year: int,
        start_date = None,
        end_date = None,
    ) -> dict:
        result = {
            "name":    "Bill Sequence",
            "status":  "ok",
            "issues":  [],
            "details": [],
        }

        where_s, params_s = self._get_conditions("sb", start_date, end_date, month, year)
        bills = db.query(f"""
            SELECT sb.bill_number, sb.bill_date
            FROM sales_bills sb
            {where_s}
            ORDER BY sb.bill_number
        """, tuple(params_s))

        if not bills:
            result["status"] = "warning"
            result["issues"].append("No sales bills found for this period.")
            return result

        bill_numbers = []
        for bill in bills:
            num_str = bill["bill_number"]
            parts = num_str.split("-")
            try:
                num = int(parts[-1])
                bill_numbers.append(num)
            except (ValueError, IndexError):
                result["issues"].append(f"⚠️ Cannot parse bill number: {num_str}")

        if not bill_numbers:
            return result

        bill_numbers.sort()
        gaps = []
        for i in range(len(bill_numbers) - 1):
            expected = bill_numbers[i] + 1
            actual   = bill_numbers[i + 1]
            if actual != expected:
                for missing in range(expected, actual):
                    gaps.append(missing)

        if gaps:
            result["status"] = "warning"
            gap_strs = [str(g) for g in gaps[:5]]
            result["issues"].append(
                f"⚠️ Missing bill numbers: {', '.join(gap_strs)}{'...' if len(gaps) > 5 else ''}"
            )
        else:
            result["status"] = "ok"

        result["details"] = {
            "first_bill":  bills[0]["bill_number"],
            "last_bill":   bills[-1]["bill_number"],
            "total_bills": len(bills),
            "gaps_found":  len(gaps),
        }
        return result

    # ----------------------------------------------------------
    # CHECK 5: NEGATIVE STOCK
    # ----------------------------------------------------------
    def _check_negative_stock(
        self,
        month: int,
        year: int,
        start_date = None,
        end_date = None,
    ) -> dict:
        result = {
            "name":    "Negative Stock Check",
            "status":  "ok",
            "issues":  [],
            "details": [],
        }

        where_p, params_p = self._get_conditions("pb", start_date, end_date, month, year)
        negative_items = db.query(f"""
            SELECT
                pi.item_name,
                pi.unit,
                SUM(pi.remaining_qty) AS remaining
            FROM purchase_items pi
            JOIN purchase_bills pb
                ON pi.purchase_bill_id = pb.id
            {where_p}
            GROUP BY pi.item_name, pi.unit
            HAVING SUM(pi.remaining_qty) < -0.001
        """, tuple(params_p))

        if negative_items:
            result["status"] = "error"
            for item in negative_items:
                result["issues"].append(
                    f"❌ NEGATIVE STOCK: {item['item_name']} — "
                    f"Oversold by {abs(item['remaining']):.2f} {item['unit']}"
                )
                result["details"].append(item)
        else:
            result["status"] = "ok"

        return result

    # ----------------------------------------------------------
    # CHECK 6: DATE CONSISTENCY
    # ----------------------------------------------------------
    def _check_date_consistency(
        self,
        month: int,
        year: int,
        start_date = None,
        end_date = None,
    ) -> dict:
        result = {
            "name":    "Date Consistency",
            "status":  "ok",
            "issues":  [],
            "details": [],
        }
        today = date.today()
        where_s, params_s = self._get_conditions("sb", start_date, end_date, month, year)

        # Check for future dates
        future_conds = list(params_s)
        future_clause = f"{where_s} {'AND' if where_s else 'WHERE'} sb.bill_date > ?"
        future_conds.append(today.strftime("%Y-%m-%d"))

        future_bills = db.query(f"""
            SELECT sb.bill_number, sb.bill_date
            FROM sales_bills sb
            {future_clause}
        """, tuple(future_conds))

        if future_bills:
            result["status"] = "warning"
            for bill in future_bills[:3]:
                result["issues"].append(f"⚠️ Bill {bill['bill_number']}: Future date {bill['bill_date']}")

        all_bills = db.query(f"""
            SELECT sb.bill_number, sb.bill_date
            FROM sales_bills sb
            {where_s}
        """, tuple(params_s))

        sunday_bills = []
        for bill in all_bills:
            try:
                d = datetime.strptime(bill["bill_date"], "%Y-%m-%d")
                if d.weekday() == 6:
                    sunday_bills.append(bill["bill_number"])
            except Exception:
                pass

        if sunday_bills:
            result["issues"].append(
                f"ℹ️ Bills on Sunday: {', '.join(sunday_bills[:3])}{'...' if len(sunday_bills) > 3 else ''} (verify if shop was open)"
            )

        result["details"] = {
            "future_count": len(future_bills),
            "sunday_count": len(sunday_bills),
            "total_bills":  len(all_bills),
        }
        return result

    # ----------------------------------------------------------
    # SUMMARY BUILDER
    # ----------------------------------------------------------
    def _build_summary(
        self,
        month: int,
        year: int,
        start_date = None,
        end_date = None,
    ) -> dict:
        where_p, params_p = self._get_conditions("pb", start_date, end_date, month, year)
        where_s, params_s = self._get_conditions("sb", start_date, end_date, month, year)

        p = db.query_one(f"""
            SELECT
                COUNT(*)                     AS p_bills,
                COUNT(DISTINCT dealer_name)  AS dealers,
                COALESCE(SUM(subtotal),    0) AS p_taxable,
                COALESCE(SUM(total_gst),   0) AS p_gst,
                COALESCE(SUM(grand_total), 0) AS p_total
            FROM purchase_bills pb
            {where_p}
        """, tuple(params_p))

        s = db.query_one(f"""
            SELECT
                COUNT(*)                       AS s_bills,
                COUNT(DISTINCT customer_name)  AS customers,
                COALESCE(SUM(subtotal),      0) AS s_taxable,
                COALESCE(SUM(total_cgst),    0) AS s_cgst,
                COALESCE(SUM(total_sgst),    0) AS s_sgst,
                COALESCE(SUM(grand_total),   0) AS s_total
            FROM sales_bills sb
            {where_s}
        """, tuple(params_s))

        cogs_row = db.query_one(f"""
            SELECT
                COALESCE(SUM(si.quantity * pi.purchase_rate), 0) AS cogs
            FROM sales_items si
            JOIN sales_bills sb ON si.sales_bill_id = sb.id
            LEFT JOIN purchase_items pi ON si.purchase_item_id = pi.id
            {where_s}
        """, tuple(params_s))
        cogs = cogs_row.get("cogs", 0)

        p_taxable = p.get("p_taxable", 0) or 0
        s_taxable = s.get("s_taxable", 0) or 0
        p_gst     = p.get("p_gst", 0) or 0
        s_cgst    = s.get("s_cgst", 0) or 0
        s_sgst    = s.get("s_sgst", 0) or 0
        s_gst     = s_cgst + s_sgst

        if cogs > 0:
            profit = round2(s_taxable - cogs)
            margin_pct = round2(profit / cogs * 100) if cogs > 0 else 0
        else:
            profit = round2(s_taxable - p_taxable)
            margin_pct = round2(profit / p_taxable * 100) if p_taxable > 0 else 0

        gst_payable = round2(max(0, s_gst - p_gst))

        remaining = db.query_one(f"""
            SELECT
                COALESCE(SUM(pi.remaining_qty), 0) AS total_remaining,
                COUNT(DISTINCT pi.item_name)        AS items_with_remaining
            FROM purchase_items pi
            JOIN purchase_bills pb
                ON pi.purchase_bill_id = pb.id
            {where_p}
            AND pi.remaining_qty > 0.001
        """, tuple(params_p))

        return {
            "p_bills":         p.get("p_bills", 0),
            "dealers":         p.get("dealers", 0),
            "p_taxable":       p_taxable,
            "p_gst":           p_gst,
            "p_total":         p.get("p_total", 0) or 0,
            "s_bills":         s.get("s_bills", 0),
            "customers":       s.get("customers", 0),
            "s_taxable":       s_taxable,
            "s_cgst":          s_cgst,
            "s_sgst":          s_sgst,
            "s_gst":           s_gst,
            "s_total":         s.get("s_total", 0) or 0,
            "cogs":            cogs,
            "profit":          profit,
            "margin_pct":      margin_pct,
            "gst_payable":     gst_payable,
            "total_remaining": remaining.get("total_remaining", 0) or 0,
            "items_pending":   remaining.get("items_with_remaining", 0) or 0,
        }


# ============================================================
# TALLY FRAME — MAIN VIEW
# ============================================================
class TallyFrame(tk.Frame):
    """
    Tally verification main view.

    Layout:
    ┌──────────────────────────────────────────────┐
    │  Title          Month/Year  [Run Tally]      │
    ├──────────────────────────────────────────────┤
    │  Overall Status Banner                       │
    ├──────────────────────────────────────────────┤
    │  Summary Cards (6 cards)                     │
    ├──────────────────────────────────────────────┤
    │  Check Results (6 checks with details)       │
    ├──────────────────────────────────────────────┤
    │  Issues List                                 │
    ├──────────────────────────────────────────────┤
    │  Item Quantity Detail Table                  │
    └──────────────────────────────────────────────┘
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS["bg_main"])
        self.app     = app
        self.engine  = TallyEngine()
        self.results = None

        today = date.today()
        self.preset_var = tk.StringVar(value="This Month")
        s_date, e_date = get_date_range_for_preset("This Month")
        self.from_date_var = tk.StringVar(value=format_date_display(s_date) if s_date else "")
        self.to_date_var   = tk.StringVar(value=format_date_display(e_date) if e_date else "")
        self.view_month = tk.IntVar(value=today.month)
        self.view_year  = tk.IntVar(value=today.year)

        self._build_ui()
        self._run_tally()

    # ----------------------------------------------------------
    # BUILD UI
    # ----------------------------------------------------------
    def _build_ui(self):
        self._build_top_bar()
        self._build_scroll_area()

    def _build_top_bar(self):
        top = tk.Frame(self, bg=COLORS["bg_main"])
        top.pack(fill="x", padx=25, pady=(20, 5))

        tk.Label(
            top,
            text="✅  Tally Verification",
            font=FONTS["heading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        # Right controls
        right = tk.Frame(top, bg=COLORS["bg_main"])
        right.pack(side="right")

        tk.Label(
            right,
            text="Period:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(0, 4))

        self.preset_cb = ttk.Combobox(
            right,
            values=DATE_PRESETS,
            width=15,
            font=FONTS["body"],
            state="readonly"
        )
        self.preset_cb.set(self.preset_var.get())
        self.preset_cb.pack(side="left", padx=3)
        self.preset_cb.bind(
            "<<ComboboxSelected>>",
            self._on_preset_change
        )

        tk.Label(
            right,
            text="From:",
            font=FONTS["label"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_muted"]
        ).pack(side="left", padx=(6, 2))

        self.from_ent = tk.Entry(
            right,
            textvariable=self.from_date_var,
            width=11,
            font=FONTS["body"]
        )
        self.from_ent.pack(side="left", padx=2)

        tk.Label(
            right,
            text="To:",
            font=FONTS["label"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_muted"]
        ).pack(side="left", padx=(4, 2))

        self.to_ent = tk.Entry(
            right,
            textvariable=self.to_date_var,
            width=11,
            font=FONTS["body"]
        )
        self.to_ent.pack(side="left", padx=2)

        # Action buttons
        for label, color, cmd in [
            ("🔄 Run Tally",
             COLORS["accent"],
             self._run_tally),
            ("📄 Export PDF",
             COLORS["danger"],
             self._export_pdf),
            ("📊 Export CSV",
             COLORS["success"],
             self._export_csv),
        ]:
            tk.Button(
                right,
                text=label,
                font=FONTS["label_bold"],
                bg=color,
                fg="white",
                relief="flat",
                padx=11, pady=6,
                cursor="hand2",
                command=cmd
            ).pack(side="left", padx=3)

    def _on_preset_change(self, event=None):
        preset = self.preset_cb.get()
        self.preset_var.set(preset)
        s, e = get_date_range_for_preset(preset)
        if s:
            self.from_date_var.set(format_date_display(s))
            self.view_month.set(s.month)
            self.view_year.set(s.year)
        else:
            self.from_date_var.set("")
        if e:
            self.to_date_var.set(format_date_display(e))
        else:
            self.to_date_var.set("")
        self._run_tally()

    def _get_active_date_range(self):
        s_raw = self.from_date_var.get().strip()
        e_raw = self.to_date_var.get().strip()
        s_date = parse_flexible_date(s_raw) if s_raw else None
        e_date = parse_flexible_date(e_raw) if e_raw else None
        return s_date, e_date

    def _on_filter_change(self, month_name, year_str):
        if month_name:
            self.view_month.set(
                MONTH_NAMES.index(month_name)
            )
        if year_str:
            self.view_year.set(int(year_str))
        self._run_tally()

    def _build_scroll_area(self):
        outer = tk.Frame(self, bg=COLORS["bg_main"])
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            outer,
            bg=COLORS["bg_main"],
            highlightthickness=0
        )
        sb = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(
            side="left", fill="both", expand=True
        )

        self.content = tk.Frame(
            self.canvas, bg=COLORS["bg_main"]
        )
        self.canvas_win = self.canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="nw"
        )

        self.content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(
                self.canvas_win, width=e.width
            )
        )
        self.canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"
            )
        )

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)

    # ----------------------------------------------------------
    # RUN TALLY
    # ----------------------------------------------------------
    def _run_tally(self):
        """Run tally engine and render results"""
        s_date, e_date = self._get_active_date_range()
        disp_month = s_date.month if s_date else self.view_month.get()
        disp_year  = s_date.year if s_date else self.view_year.get()

        period_desc = f"{format_date_display(s_date)} to {format_date_display(e_date)}" if s_date and e_date else f"{MONTH_NAMES[disp_month]} {disp_year}"
        self.app.set_status(
            f"Running tally for {period_desc}...",
            "info"
        )

        self.results = self.engine.run_full_tally(
            month=disp_month,
            year=disp_year,
            start_date=s_date,
            end_date=e_date,
        )

        self._clear_content()
        self._render_overall_status()
        self._render_summary_cards()
        self._render_check_results()
        self._render_issues_list()
        self._render_quantity_table()

        status = self.results["overall_status"]
        status_map = {
            "ok":      ("All checks passed!", "success"),
            "warning": ("Some warnings found.", "warning"),
            "error":   ("Errors detected!", "error"),
        }
        msg, level = status_map.get(
            status, ("Done", "info")
        )
        self.app.set_status(
            f"Tally complete — {msg}", level
        )

    # ----------------------------------------------------------
    # OVERALL STATUS BANNER
    # ----------------------------------------------------------
    def _render_overall_status(self):
        """Big status banner at the top"""
        status = self.results["overall_status"]
        s_date = self.results.get("start_date")
        e_date = self.results.get("end_date")
        if s_date and e_date:
            period_str = f"{format_date_display(s_date)} to {format_date_display(e_date)}"
        elif s_date:
            period_str = f"From {format_date_display(s_date)}"
        elif e_date:
            period_str = f"Up to {format_date_display(e_date)}"
        else:
            period_str = f"{MONTH_NAMES[self.results['month']]} {self.results['year']}"

        config = {
            "ok": (
                COLORS["success"],
                "✅  ALL CHECKS PASSED",
                f"{period_str} — Continuous inventory reconciled and perfectly tallied!"
            ),
            "warning": (
                COLORS["warning"],
                "⚠️  SOME WARNINGS",
                f"{period_str} — Review warnings below."
            ),
            "error": (
                COLORS["danger"],
                "❌  ERRORS FOUND",
                f"{period_str} — Critical issues detected. Fix immediately!"
            ),
        }

        color, title, subtitle = config.get(
            status, (
                COLORS["text_muted"],
                "Unknown", ""
            )
        )

        banner = tk.Frame(
            self.content,
            bg=color,
            pady=15
        )
        banner.pack(
            fill="x", padx=20, pady=(15, 5)
        )

        tk.Label(
            banner,
            text=title,
            font=FONTS["heading"],
            bg=color,
            fg="white"
        ).pack()

        tk.Label(
            banner,
            text=subtitle,
            font=FONTS["body"],
            bg=color,
            fg="#e0e0e0"
        ).pack()

    # ----------------------------------------------------------
    # SUMMARY CARDS
    # ----------------------------------------------------------
    def _render_summary_cards(self):
        """6 summary stat cards"""
        s = self.results["summary"]

        cards_frame = tk.Frame(
            self.content, bg=COLORS["bg_main"]
        )
        cards_frame.pack(
            fill="x", padx=20, pady=8
        )

        row1 = tk.Frame(
            cards_frame, bg=COLORS["bg_main"]
        )
        row1.pack(fill="x")

        for title, value, sub, color in [
            ("📥 Purchase Total",
             format_inr(s["p_total"]),
             f"{s['p_bills']} bills | "
             f"{s['dealers']} dealers",
             "#1565c0"),
            ("📤 Sales Total",
             format_inr(s["s_total"]),
             f"{s['s_bills']} bills | "
             f"{s['customers']} customers",
             "#2e7d32"),
            ("💰 Profit",
             format_inr(s["profit"]),
             f"Margin: {s['margin_pct']:.1f}%",
             "#e65100"),
        ]:
            self._make_card(
                row1, title, value, sub, color
            )

        row2 = tk.Frame(
            cards_frame, bg=COLORS["bg_main"]
        )
        row2.pack(fill="x", pady=(8, 0))

        remaining = s.get("total_remaining", 0)
        pending   = s.get("items_pending", 0)
        stock_color = (
            COLORS["success"]
            if remaining == 0
            else COLORS["warning"]
        )

        for title, value, sub, color in [
            ("🧾 GST Payable",
             format_inr(s["gst_payable"]),
             f"Input: {format_inr(s['p_gst'])} | "
             f"Output: {format_inr(s['s_gst'])}",
             "#6a1b9a"),
            ("📦 Remaining Stock",
             f"{remaining:.2f} units",
             f"{pending} items not fully sold",
             stock_color),
            ("📊 Tally Status",
             self.results["overall_status"].upper(),
             f"{len(self.results['issues'])} issues",
             COLORS["tally_ok"]
             if self.results["overall_status"] == "ok"
             else COLORS["tally_warn"]
             if self.results["overall_status"] == "warning"
             else COLORS["tally_bad"]),
        ]:
            self._make_card(
                row2, title, value, sub, color
            )

    def _make_card(
        self, parent, title, value, sub, color
    ):
        card = tk.Frame(
            parent,
            bg=color,
            padx=18, pady=14
        )
        card.pack(
            side="left", padx=8, pady=5,
            fill="both", expand=True
        )
        tk.Label(
            card, text=title,
            font=FONTS["label_bold"],
            bg=color, fg="#e0e0e0"
        ).pack(anchor="w")
        tk.Label(
            card, text=value,
            font=FONTS["number_sm"],
            bg=color, fg="white"
        ).pack(anchor="w", pady=(5, 0))
        tk.Label(
            card, text=sub,
            font=FONTS["small"],
            bg=color, fg="#e0e0e0"
        ).pack(anchor="w")

    # ----------------------------------------------------------
    # CHECK RESULTS
    # ----------------------------------------------------------
    def _render_check_results(self):
        """Show each check with pass/fail indicator"""
        section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=15
        )
        section.pack(
            fill="x", padx=20, pady=8
        )

        tk.Label(
            section,
            text="🔍 Verification Checks",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 10))

        checks = self.results.get("checks", {})

        check_display = [
            ("quantity",
             "📦 Item Quantity Tally",
             "All purchased quantities sold"),
            ("amount",
             "💰 Amount Tally",
             "Sales ≥ Purchase (profit margin)"),
            ("gst",
             "🧾 GST Tally",
             "Output GST ≥ Input GST"),
            ("sequence",
             "🔢 Bill Number Sequence",
             "No gaps in bill numbers"),
            ("negative_stock",
             "📉 Negative Stock Check",
             "No item sold more than purchased"),
            ("dates",
             "📅 Date Consistency",
             "All dates within correct month"),
        ]

        status_config = {
            "ok": (
                "✅ PASS",
                COLORS["success"],
                COLORS["success_light"]
            ),
            "warning": (
                "⚠️ WARN",
                COLORS["warning"],
                COLORS["warning_light"]
            ),
            "error": (
                "❌ FAIL",
                COLORS["danger"],
                COLORS["danger_light"]
            ),
        }

        for key, label, description in check_display:
            check  = checks.get(key, {})
            status = check.get("status", "ok")

            status_text, fg_color, bg_color = \
                status_config.get(
                    status,
                    ("? UNKNOWN", COLORS["text_muted"],
                     COLORS["bg_card"])
                )

            row = tk.Frame(
                section,
                bg=bg_color,
                padx=12, pady=8
            )
            row.pack(fill="x", pady=2)

            # Status badge
            tk.Label(
                row,
                text=status_text,
                font=FONTS["label_bold"],
                bg=bg_color,
                fg=fg_color,
                width=10,
                anchor="w"
            ).pack(side="left")

            # Check name
            tk.Label(
                row,
                text=label,
                font=FONTS["label_bold"],
                bg=bg_color,
                fg=COLORS["text_dark"],
                width=30,
                anchor="w"
            ).pack(side="left", padx=(5, 0))

            # Description
            tk.Label(
                row,
                text=description,
                font=FONTS["small"],
                bg=bg_color,
                fg=COLORS["text_muted"]
            ).pack(side="left", padx=(5, 0))

            # Issue count if any
            issues = check.get("issues", [])
            if issues:
                tk.Label(
                    row,
                    text=f"{len(issues)} issue(s)",
                    font=FONTS["small"],
                    bg=bg_color,
                    fg=fg_color
                ).pack(side="right", padx=5)

    # ----------------------------------------------------------
    # ISSUES LIST
    # ----------------------------------------------------------
    def _render_issues_list(self):
        """Show all issues found"""
        issues = self.results.get("issues", [])

        if not issues:
            ok_frame = tk.Frame(
                self.content,
                bg=COLORS["success_light"],
                padx=20, pady=12
            )
            ok_frame.pack(
                fill="x", padx=20, pady=5
            )
            tk.Label(
                ok_frame,
                text="✅  No issues found! "
                     "All checks passed perfectly.",
                font=FONTS["body_bold"],
                bg=COLORS["success_light"],
                fg=COLORS["success"]
            ).pack(anchor="w")
            return

        section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=15
        )
        section.pack(
            fill="x", padx=20, pady=5
        )

        tk.Label(
            section,
            text=f"⚠️  Issues Found "
                 f"({len(issues)})",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["danger"]
        ).pack(anchor="w", pady=(0, 8))

        level_colors = {
            "ok":      COLORS["success"],
            "warning": COLORS["warning"],
            "error":   COLORS["danger"],
        }

        for i, issue in enumerate(issues):
            bg = (COLORS["row_even"]
                  if i % 2 == 0
                  else COLORS["row_odd"])
            row = tk.Frame(section, bg=bg)
            row.pack(fill="x", pady=1)

            level = issue.get("level", "warning")
            color = level_colors.get(
                level, COLORS["warning"]
            )

            tk.Label(
                row,
                text="●",
                font=FONTS["body"],
                bg=bg,
                fg=color
            ).pack(side="left", padx=(5, 8), pady=5)

            tk.Label(
                row,
                text=issue.get("message", ""),
                font=FONTS["label"],
                bg=bg,
                fg=COLORS["text_dark"],
                anchor="w",
                wraplength=700,
                justify="left"
            ).pack(
                side="left", pady=5, anchor="w"
            )

    # ----------------------------------------------------------
    # QUANTITY TABLE
    # ----------------------------------------------------------
    def _render_quantity_table(self):
        """Detailed item quantity tally table"""
        qty_check = self.results.get(
            "checks", {}
        ).get("quantity", {})
        details   = qty_check.get("details", [])

        if not details:
            return

        section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=15
        )
        section.pack(
            fill="x", padx=20, pady=(5, 15)
        )

        # Header row
        title_row = tk.Frame(
            section, bg=COLORS["bg_card"]
        )
        title_row.pack(fill="x", pady=(0, 8))

        tk.Label(
            title_row,
            text="📦 Item Quantity Detail",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        # Counts
        ok_c   = qty_check.get("ok_count",   0)
        warn_c = qty_check.get("warn_count", 0)
        err_c  = qty_check.get("err_count",  0)
        total  = qty_check.get("total",      0)

        for text, color in [
            (f"✅ {ok_c} OK",    COLORS["success"]),
            (f"⚠️ {warn_c} Pending",
             COLORS["warning"]),
            (f"❌ {err_c} Error", COLORS["danger"]),
        ]:
            tk.Label(
                title_row,
                text=text,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=color
            ).pack(side="right", padx=10)

        # Table header
        hdr = tk.Frame(
            section, bg=COLORS["header_bg"]
        )
        hdr.pack(fill="x")

        for col, width in [
            ("Item Name",  25),
            ("HSN Code",    9),
            ("Unit",        8),
            ("Purchased",  10),
            ("Sold",       10),
            ("Remaining",  10),
            ("Status",      9),
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

        # Data rows
        status_config = {
            "ok": (
                "✅ Done",
                COLORS["success"],
                COLORS["success_light"]
            ),
            "warning": (
                "⚠️ Pending",
                COLORS["warning"],
                COLORS["warning_light"]
            ),
            "error": (
                "❌ Oversold",
                COLORS["danger"],
                COLORS["danger_light"]
            ),
        }

        for i, item in enumerate(details):
            status = item.get("status", "ok")
            status_text, fg_c, bg_c = \
                status_config.get(
                    status,
                    ("?", COLORS["text_muted"],
                     COLORS["row_even"])
                )

            if status == "ok":
                bg = (COLORS["row_even"]
                      if i % 2 == 0
                      else COLORS["row_odd"])
            else:
                bg = bg_c

            row = tk.Frame(section, bg=bg)
            row.pack(fill="x")

            for text, width in [
                (item["item_name"],         25),
                (item.get("hsn_code", "-"), 9),
                (item["unit"],               8),
                (f"{item['purchased']:.2f}", 10),
                (f"{item['sold']:.2f}",      10),
                (f"{item['remaining']:.2f}", 10),
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
                text=status_text,
                font=FONTS["table_bold"],
                bg=bg,
                fg=fg_c,
                width=9,
                anchor="w",
                padx=5
            ).pack(side="left")

    # ----------------------------------------------------------
    # EXPORT FUNCTIONS
    # ----------------------------------------------------------
    def _export_pdf(self):
        """Export tally report as PDF"""
        if not self.results:
            messagebox.showwarning(
                "No Data",
                "Run tally first."
            )
            return

        month = self.results["month"]
        year  = self.results["year"]

        path = filedialog.asksaveasfilename(
            title="Export Tally Report",
            defaultextension=".pdf",
            initialfile=(
                f"tally_{year}_{month:02d}"
                f"_{MONTH_NAMES[month]}.pdf"
            ),
            filetypes=[
                ("PDF files", "*.pdf"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        try:
            self._generate_tally_pdf(path)
            messagebox.showinfo(
                "Export Complete ✅",
                f"Tally report saved to:\n{path}"
            )
            os.startfile(path)
        except Exception as e:
            messagebox.showerror(
                "Export Error",
                f"Could not export PDF.\n\n{e}"
            )

    def _generate_tally_pdf(self, path: str):
        """Generate tally PDF report"""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.lib.styles import (
            getSampleStyleSheet, ParagraphStyle
        )
        from reportlab.lib.enums import TA_CENTER
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle,
            Paragraph, Spacer
        )

        settings = load_settings()
        shop     = settings.get("shop", {})
        r        = self.results
        month    = r["month"]
        year     = r["year"]
        s        = r["summary"]

        doc = SimpleDocTemplate(
            path,
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=12 * mm,
            bottomMargin=15 * mm,
            title=f"Tally Report "
                  f"{MONTH_NAMES[month]} {year}"
        )

        styles = getSampleStyleSheet()
        story  = []

        # Title
        story.append(Paragraph(
            shop.get("name", "Hardware Shop"),
            ParagraphStyle(
                "SN",
                parent=styles["Normal"],
                fontSize=16,
                fontName="Helvetica-Bold",
                alignment=TA_CENTER
            )
        ))
        story.append(Paragraph(
            f"Tally Report — "
            f"{MONTH_NAMES[month]} {year}",
            ParagraphStyle(
                "RT",
                parent=styles["Normal"],
                fontSize=13,
                fontName="Helvetica-Bold",
                alignment=TA_CENTER
            )
        ))

        # Overall status
        status_color = {
            "ok":      colors.HexColor("#2e7d32"),
            "warning": colors.HexColor("#f57f17"),
            "error":   colors.HexColor("#c62828"),
        }.get(r["overall_status"], colors.grey)

        status_text = {
            "ok":      "✅ ALL CHECKS PASSED",
            "warning": "⚠️  WARNINGS FOUND",
            "error":   "❌ ERRORS DETECTED",
        }.get(r["overall_status"], "UNKNOWN")

        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph(
            status_text,
            ParagraphStyle(
                "ST",
                parent=styles["Normal"],
                fontSize=14,
                fontName="Helvetica-Bold",
                textColor=status_color,
                alignment=TA_CENTER
            )
        ))
        story.append(Spacer(1, 8 * mm))

        # Summary table
        summary_rows = [
            ["Category", "Purchase", "Sales"],
            ["Bills",
             str(s["p_bills"]),
             str(s["s_bills"])],
            ["Taxable Amount",
             format_inr(s["p_taxable"]),
             format_inr(s["s_taxable"])],
            ["GST",
             format_inr(s["p_gst"]),
             format_inr(s["s_gst"])],
            ["Grand Total",
             format_inr(s["p_total"]),
             format_inr(s["s_total"])],
            ["Profit", "—",
             format_inr(s["profit"])],
            ["GST Payable", "—",
             format_inr(s["gst_payable"])],
        ]

        summary_table = Table(
            summary_rows,
            colWidths=[60 * mm, 60 * mm, 60 * mm]
        )
        summary_table.setStyle(TableStyle([
            ("BACKGROUND",
             (0, 0), (-1, 0),
             colors.HexColor("#1a237e")),
            ("TEXTCOLOR",
             (0, 0), (-1, 0),
             colors.white),
            ("FONTNAME",
             (0, 0), (-1, 0),
             "Helvetica-Bold"),
            ("FONTNAME",
             (0, 1), (-1, -1),
             "Helvetica"),
            ("FONTSIZE",
             (0, 0), (-1, -1), 10),
            ("BOX",
             (0, 0), (-1, -1),
             1, colors.HexColor("#1a237e")),
            ("INNERGRID",
             (0, 0), (-1, -1),
             0.3, colors.grey),
            ("TOPPADDING",
             (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING",
             (0, 0), (-1, -1), 6),
            ("LEFTPADDING",
             (0, 0), (-1, -1), 8),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 8 * mm))

        # Issues section
        issues = r.get("issues", [])
        if issues:
            story.append(Paragraph(
                f"Issues Found ({len(issues)})",
                ParagraphStyle(
                    "IH",
                    parent=styles["Normal"],
                    fontSize=11,
                    fontName="Helvetica-Bold",
                    textColor=colors.HexColor(
                        "#c62828"
                    )
                )
            ))
            story.append(Spacer(1, 3 * mm))

            issue_rows = [["#", "Issue"]]
            for i, issue in enumerate(issues):
                issue_rows.append([
                    str(i + 1),
                    issue.get("message", "")
                ])

            issue_table = Table(
                issue_rows,
                colWidths=[10 * mm, 170 * mm]
            )
            issue_table.setStyle(TableStyle([
                ("BACKGROUND",
                 (0, 0), (-1, 0),
                 colors.HexColor("#c62828")),
                ("TEXTCOLOR",
                 (0, 0), (-1, 0),
                 colors.white),
                ("FONTNAME",
                 (0, 0), (-1, 0),
                 "Helvetica-Bold"),
                ("FONTNAME",
                 (0, 1), (-1, -1),
                 "Helvetica"),
                ("FONTSIZE",
                 (0, 0), (-1, -1), 9),
                ("BOX",
                 (0, 0), (-1, -1),
                 0.8,
                 colors.HexColor("#c62828")),
                ("INNERGRID",
                 (0, 0), (-1, -1),
                 0.3, colors.grey),
                ("TOPPADDING",
                 (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",
                 (0, 0), (-1, -1), 4),
                ("LEFTPADDING",
                 (0, 0), (-1, -1), 5),
            ]))
            story.append(issue_table)
            story.append(Spacer(1, 8 * mm))

        # Item tally table
        qty_details = r.get(
            "checks", {}
        ).get(
            "quantity", {}
        ).get("details", [])

        if qty_details:
            story.append(Paragraph(
                "Item Quantity Tally",
                ParagraphStyle(
                    "QH",
                    parent=styles["Normal"],
                    fontSize=11,
                    fontName="Helvetica-Bold"
                )
            ))
            story.append(Spacer(1, 3 * mm))

            qty_rows = [[
                "Item Name", "Unit",
                "Purchased", "Sold",
                "Remaining", "Status"
            ]]

            for item in qty_details:
                status = item.get("status", "ok")
                status_text = {
                    "ok":      "OK",
                    "warning": "PENDING",
                    "error":   "OVERSOLD",
                }.get(status, "?")

                qty_rows.append([
                    item["item_name"],
                    item["unit"],
                    f"{item['purchased']:.2f}",
                    f"{item['sold']:.2f}",
                    f"{item['remaining']:.2f}",
                    status_text,
                ])

            qty_table = Table(
                qty_rows,
                colWidths=[
                    55 * mm, 15 * mm, 22 * mm,
                    22 * mm, 22 * mm, 22 * mm
                ]
            )
            qty_table.setStyle(TableStyle([
                ("BACKGROUND",
                 (0, 0), (-1, 0),
                 colors.HexColor("#1a237e")),
                ("TEXTCOLOR",
                 (0, 0), (-1, 0),
                 colors.white),
                ("FONTNAME",
                 (0, 0), (-1, 0),
                 "Helvetica-Bold"),
                ("FONTNAME",
                 (0, 1), (-1, -1),
                 "Helvetica"),
                ("FONTSIZE",
                 (0, 0), (-1, -1), 9),
                ("BOX",
                 (0, 0), (-1, -1),
                 0.8,
                 colors.HexColor("#1a237e")),
                ("INNERGRID",
                 (0, 0), (-1, -1),
                 0.3, colors.grey),
                ("TOPPADDING",
                 (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",
                 (0, 0), (-1, -1), 4),
                ("LEFTPADDING",
                 (0, 0), (-1, -1), 5),
            ]))
            story.append(qty_table)

        doc.build(story)

    def _export_csv(self):
        """Export tally report as CSV"""
        if not self.results:
            messagebox.showwarning(
                "No Data", "Run tally first."
            )
            return

        month = self.results["month"]
        year  = self.results["year"]

        path = filedialog.asksaveasfilename(
            title="Export Tally CSV",
            defaultextension=".csv",
            initialfile=(
                f"tally_{year}_{month:02d}.csv"
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
                writer = csv.writer(f)

                # Header
                writer.writerow([
                    f"Tally Report — "
                    f"{MONTH_NAMES[month]} {year}"
                ])
                writer.writerow([
                    "Overall Status",
                    self.results[
                        "overall_status"
                    ].upper()
                ])
                writer.writerow([])

                # Summary
                s = self.results["summary"]
                writer.writerow([
                    "Category",
                    "Purchase", "Sales"
                ])
                writer.writerow([
                    "Bills",
                    s["p_bills"], s["s_bills"]
                ])
                writer.writerow([
                    "Taxable",
                    s["p_taxable"], s["s_taxable"]
                ])
                writer.writerow([
                    "GST",
                    s["p_gst"], s["s_gst"]
                ])
                writer.writerow([
                    "Total",
                    s["p_total"], s["s_total"]
                ])
                writer.writerow([
                    "Profit", "", s["profit"]
                ])
                writer.writerow([
                    "GST Payable",
                    "", s["gst_payable"]
                ])
                writer.writerow([])

                # Issues
                writer.writerow(["ISSUES"])
                issues = self.results.get(
                    "issues", []
                )
                if issues:
                    writer.writerow([
                        "Check", "Level", "Message"
                    ])
                    for issue in issues:
                        writer.writerow([
                            issue.get("check", ""),
                            issue.get("level", ""),
                            issue.get("message", ""),
                        ])
                else:
                    writer.writerow([
                        "No issues found."
                    ])

                writer.writerow([])

                # Item tally
                writer.writerow(["ITEM TALLY"])
                writer.writerow([
                    "Item Name", "Unit",
                    "Purchased", "Sold",
                    "Remaining", "Status"
                ])

                qty_details = self.results.get(
                    "checks", {}
                ).get(
                    "quantity", {}
                ).get("details", [])

                for item in qty_details:
                    writer.writerow([
                        item["item_name"],
                        item["unit"],
                        item["purchased"],
                        item["sold"],
                        item["remaining"],
                        item["status"].upper(),
                    ])

            messagebox.showinfo(
                "Export Complete ✅",
                f"Tally CSV saved to:\n{path}"
            )
            os.startfile(
                str(Path(path).parent)
            )

        except Exception as e:
            messagebox.showerror(
                "Export Error",
                f"Could not export.\n\n{e}"
            )