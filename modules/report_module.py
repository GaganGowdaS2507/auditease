# modules/report_module.py
# ============================================================
# REPORT MODULE
# Generates monthly and annual reports
#
# Features:
# 1. Monthly Report
#    - Purchase summary
#    - Sales summary
#    - GST payable (Output - Input)
#    - Profit summary
#    - Item-wise tally
#    - Top selling items
# 2. Annual Report
#    - Month-wise turnover table
#    - Total annual purchase/sales/profit
#    - GST annual summary
#    - Threshold tracker (₹40L / ₹1.5Cr)
# 3. Export to PDF
# 4. Export to CSV
# 5. GSTR-1 ready summary
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
    "number_sm":  ("Helvetica", 13, "bold"),
}

MONTH_NAMES = [
    "", "January", "February", "March",
    "April", "May", "June", "July",
    "August", "September", "October",
    "November", "December"
]

# GST registration threshold
GST_THRESHOLD     = 4000000   # ₹40 Lakhs
COMPOSITION_LIMIT = 15000000  # ₹1.5 Crores


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
    """Format amount in Indian style: ₹1,23,456.78"""
    try:
        is_negative = amount < 0
        amount      = abs(amount)
        rupees      = int(amount)
        paise_str   = f"{amount - rupees:.2f}"[1:]

        # Indian number formatting
        s = str(rupees)
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

        result = f"₹{formatted}{paise_str}"
        return f"-{result}" if is_negative else result
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


db = DBHelper()


# ============================================================
# REPORT DATA FETCHER
# ============================================================
class ReportDataFetcher:
    """
    Fetches all report data from database.
    Separates DB logic from UI logic.
    """

    # ----------------------------------------------------------
    # MONTHLY DATA
    # ----------------------------------------------------------
    def get_monthly_data(
        self, month: int, year: int
    ) -> dict:
        """Fetch all data needed for monthly report"""

        # Purchase summary
        purchase = db.query_one("""
            SELECT
                COUNT(*)                   AS bill_count,
                COUNT(DISTINCT dealer_name) AS dealer_count,
                COALESCE(SUM(subtotal),    0) AS taxable,
                COALESCE(SUM(total_gst),   0) AS gst,
                COALESCE(SUM(grand_total), 0) AS total
            FROM purchase_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        # Sales summary
        sales = db.query_one("""
            SELECT
                COUNT(*)                     AS bill_count,
                COUNT(DISTINCT customer_name) AS customer_count,
                COALESCE(SUM(subtotal),      0) AS taxable,
                COALESCE(SUM(total_cgst),    0) AS cgst,
                COALESCE(SUM(total_sgst),    0) AS sgst,
                COALESCE(SUM(grand_total),   0) AS total,
                AVG(grand_total)               AS avg_bill
            FROM sales_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        # Item-wise purchase pool
        purchase_items = db.query("""
            SELECT
                pi.item_name,
                pi.hsn_code,
                pi.unit,
                pi.gst_rate,
                SUM(pi.quantity)      AS purchased,
                SUM(pi.remaining_qty) AS remaining,
                AVG(pi.purchase_rate) AS avg_buy_rate,
                SUM(pi.total_amount)  AS purchase_total
            FROM purchase_items pi
            JOIN purchase_bills pb
                ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_month=? AND pb.bill_year=?
            GROUP BY pi.item_name, pi.unit
            ORDER BY purchase_total DESC
        """, (month, year))

        # Item-wise sales
        sales_items = db.query("""
            SELECT
                si.item_name,
                si.hsn_code,
                si.unit,
                si.gst_rate,
                SUM(si.quantity)      AS sold_qty,
                AVG(si.selling_rate)  AS avg_sell_rate,
                SUM(si.taxable_amount) AS taxable,
                SUM(si.cgst_amount)   AS cgst,
                SUM(si.sgst_amount)   AS sgst,
                SUM(si.total_amount)  AS sales_total,
                AVG(si.margin_percent) AS avg_margin
            FROM sales_items si
            JOIN sales_bills sb
                ON si.sales_bill_id = sb.id
            WHERE sb.bill_month=? AND sb.bill_year=?
            GROUP BY si.item_name, si.unit
            ORDER BY sales_total DESC
        """, (month, year))

        # GST summary by rate
        gst_summary = db.query("""
            SELECT
                si.gst_rate,
                SUM(si.taxable_amount) AS taxable,
                SUM(si.cgst_amount)    AS cgst,
                SUM(si.sgst_amount)    AS sgst
            FROM sales_items si
            JOIN sales_bills sb
                ON si.sales_bill_id = sb.id
            WHERE sb.bill_month=? AND sb.bill_year=?
            GROUP BY si.gst_rate
            ORDER BY si.gst_rate
        """, (month, year))

        # GST input by rate (from purchases)
        input_gst = db.query("""
            SELECT
                pi.gst_rate,
                SUM(pi.quantity * pi.purchase_rate)
                    AS taxable,
                SUM(pi.gst_amount) AS gst
            FROM purchase_items pi
            JOIN purchase_bills pb
                ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_month=? AND pb.bill_year=?
            GROUP BY pi.gst_rate
            ORDER BY pi.gst_rate
        """, (month, year))

        # Top 5 sales bills
        top_bills = db.query("""
            SELECT
                bill_number,
                customer_name,
                bill_date,
                grand_total
            FROM sales_bills
            WHERE bill_month=? AND bill_year=?
            ORDER BY grand_total DESC
            LIMIT 5
        """, (month, year))

        # Calculations
        p_taxable  = purchase.get("taxable", 0)
        s_taxable  = sales.get("taxable", 0)
        p_gst      = purchase.get("gst", 0)
        s_cgst     = sales.get("cgst", 0)
        s_sgst     = sales.get("sgst", 0)
        s_gst      = s_cgst + s_sgst
        profit     = round2(s_taxable - p_taxable)
        gst_payable = round2(max(0, s_gst - p_gst))
        margin_pct = (
            round2(profit / p_taxable * 100)
            if p_taxable > 0 else 0
        )

        return {
            "month":          month,
            "year":           year,
            "purchase":       purchase,
            "sales":          sales,
            "purchase_items": purchase_items,
            "sales_items":    sales_items,
            "gst_summary":    gst_summary,
            "input_gst":      input_gst,
            "top_bills":      top_bills,
            "profit":         profit,
            "gst_payable":    gst_payable,
            "margin_pct":     margin_pct,
            "p_gst":          p_gst,
            "s_gst":          s_gst,
            "s_cgst":         s_cgst,
            "s_sgst":         s_sgst,
        }

    # ----------------------------------------------------------
    # ANNUAL DATA
    # ----------------------------------------------------------
    def get_annual_data(self, year: int) -> dict:
        """Fetch all data for annual report"""

        # Month-wise summary
        monthly = db.query("""
            SELECT
                bill_month,
                COUNT(*) AS p_count,
                COALESCE(SUM(subtotal),    0) AS p_taxable,
                COALESCE(SUM(total_gst),   0) AS p_gst,
                COALESCE(SUM(grand_total), 0) AS p_total
            FROM purchase_bills
            WHERE bill_year=?
            GROUP BY bill_month
            ORDER BY bill_month
        """, (year,))

        monthly_sales = db.query("""
            SELECT
                bill_month,
                COUNT(*) AS s_count,
                COALESCE(SUM(subtotal),   0) AS s_taxable,
                COALESCE(SUM(total_cgst), 0) AS s_cgst,
                COALESCE(SUM(total_sgst), 0) AS s_sgst,
                COALESCE(SUM(grand_total),0) AS s_total
            FROM sales_bills
            WHERE bill_year=?
            GROUP BY bill_month
            ORDER BY bill_month
        """, (year,))

        # Annual totals
        annual_purchase = db.query_one("""
            SELECT
                COUNT(*) AS cnt,
                COALESCE(SUM(subtotal),    0) AS taxable,
                COALESCE(SUM(total_gst),   0) AS gst,
                COALESCE(SUM(grand_total), 0) AS total
            FROM purchase_bills
            WHERE bill_year=?
        """, (year,))

        annual_sales = db.query_one("""
            SELECT
                COUNT(*) AS cnt,
                COALESCE(SUM(subtotal),   0) AS taxable,
                COALESCE(SUM(total_cgst), 0) AS cgst,
                COALESCE(SUM(total_sgst), 0) AS sgst,
                COALESCE(SUM(grand_total),0) AS total
            FROM sales_bills
            WHERE bill_year=?
        """, (year,))

        # Build month-wise combined data
        p_by_month = {
            r["bill_month"]: r for r in monthly
        }
        s_by_month = {
            r["bill_month"]: r for r in monthly_sales
        }

        months_data = []
        annual_profit  = 0
        annual_gst_pay = 0

        for m in range(1, 13):
            p = p_by_month.get(m, {})
            s = s_by_month.get(m, {})

            p_tax = p.get("p_taxable", 0)
            s_tax = s.get("s_taxable", 0)
            p_gst = p.get("p_gst", 0)
            s_gst = (
                s.get("s_cgst", 0) +
                s.get("s_sgst", 0)
            )

            profit  = round2(s_tax - p_tax)
            payable = round2(max(0, s_gst - p_gst))

            annual_profit  += profit
            annual_gst_pay += payable

            months_data.append({
                "month":       m,
                "month_name":  MONTH_NAMES[m],
                "p_count":     p.get("p_count", 0),
                "p_taxable":   p_tax,
                "p_gst":       p_gst,
                "p_total":     p.get("p_total", 0),
                "s_count":     s.get("s_count", 0),
                "s_taxable":   s_tax,
                "s_cgst":      s.get("s_cgst", 0),
                "s_sgst":      s.get("s_sgst", 0),
                "s_total":     s.get("s_total", 0),
                "profit":      profit,
                "gst_payable": payable,
            })

        # Annual totals
        a_p = annual_purchase
        a_s = annual_sales
        annual_p_total = a_p.get("total", 0)
        annual_s_total = a_s.get("total", 0)
        annual_p_gst   = a_p.get("gst", 0)
        annual_s_gst   = (
            a_s.get("cgst", 0) +
            a_s.get("sgst", 0)
        )

        # Turnover threshold check
        turnover     = annual_s_total
        threshold_pct = (
            turnover / GST_THRESHOLD * 100
            if GST_THRESHOLD > 0 else 0
        )
        comp_limit_pct = (
            turnover / COMPOSITION_LIMIT * 100
            if COMPOSITION_LIMIT > 0 else 0
        )

        return {
            "year":             year,
            "months_data":      months_data,
            "annual_p_count":   a_p.get("cnt", 0),
            "annual_p_taxable": a_p.get("taxable", 0),
            "annual_p_gst":     annual_p_gst,
            "annual_p_total":   annual_p_total,
            "annual_s_count":   a_s.get("cnt", 0),
            "annual_s_taxable": a_s.get("taxable", 0),
            "annual_s_cgst":    a_s.get("cgst", 0),
            "annual_s_sgst":    a_s.get("sgst", 0),
            "annual_s_total":   annual_s_total,
            "annual_profit":    round2(annual_profit),
            "annual_gst_pay":   round2(annual_gst_pay),
            "turnover":         turnover,
            "threshold_pct":    round2(threshold_pct),
            "comp_limit_pct":   round2(comp_limit_pct),
        }


# ============================================================
# REPORT FRAME — MAIN VIEW
# ============================================================
class ReportFrame(tk.Frame):
    """
    Reports main view.

    Layout:
    ┌──────────────────────────────────────────────┐
    │  Title          [Monthly] [Annual] tabs      │
    ├──────────────────────────────────────────────┤
    │  [Month/Year selector]  [Generate] [Export]  │
    ├──────────────────────────────────────────────┤
    │                                              │
    │  Report Content (scrollable)                 │
    │                                              │
    └──────────────────────────────────────────────┘
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS["bg_main"])
        self.app      = app
        self.settings = load_settings()
        self.fetcher  = ReportDataFetcher()

        today = date.today()
        self.view_month = tk.IntVar(value=today.month)
        self.view_year  = tk.IntVar(value=today.year)
        self.active_tab = tk.StringVar(value="monthly")

        self._build_ui()
        self._load_monthly_report()

    # ----------------------------------------------------------
    # BUILD UI
    # ----------------------------------------------------------
    def _build_ui(self):
        self._build_top_bar()
        self._build_tab_bar()
        self._build_scroll_area()

    def _build_top_bar(self):
        top = tk.Frame(self, bg=COLORS["bg_main"])
        top.pack(fill="x", padx=25, pady=(20, 5))

        tk.Label(
            top,
            text="📊  Reports",
            font=FONTS["heading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        # Right controls
        right = tk.Frame(top, bg=COLORS["bg_main"])
        right.pack(side="right")

        # Month selector
        tk.Label(
            right,
            text="Month:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(0, 5))

        self.month_cb = ttk.Combobox(
            right,
            values=MONTH_NAMES[1:],
            width=11,
            font=FONTS["body"],
            state="readonly"
        )
        self.month_cb.set(
            MONTH_NAMES[self.view_month.get()]
        )
        self.month_cb.pack(side="left", padx=3)
        self.month_cb.bind(
            "<<ComboboxSelected>>",
            lambda e: self._on_month_change(
                self.month_cb.get()
            )
        )

        # Year selector
        current_year = date.today().year
        self.year_cb = ttk.Combobox(
            right,
            values=[
                str(y) for y in range(
                    current_year - 3,
                    current_year + 2
                )
            ],
            width=7,
            font=FONTS["body"],
            state="readonly"
        )
        self.year_cb.set(str(self.view_year.get()))
        self.year_cb.pack(side="left", padx=3)
        self.year_cb.bind(
            "<<ComboboxSelected>>",
            lambda e: self._on_year_change(
                self.year_cb.get()
            )
        )

        # Export buttons
        tk.Button(
            right,
            text="📄 Export PDF",
            font=FONTS["label_bold"],
            bg=COLORS["danger"],
            fg="white",
            relief="flat",
            padx=12, pady=6,
            cursor="hand2",
            command=self._export_pdf
        ).pack(side="left", padx=(10, 3))

        tk.Button(
            right,
            text="📊 Export CSV",
            font=FONTS["label_bold"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=12, pady=6,
            cursor="hand2",
            command=self._export_csv
        ).pack(side="left", padx=3)

    def _build_tab_bar(self):
        """Monthly / Annual tab switcher"""
        tab_bar = tk.Frame(
            self, bg=COLORS["bg_main"]
        )
        tab_bar.pack(
            fill="x", padx=25, pady=(5, 0)
        )

        self.tab_btns = {}
        for key, label in [
            ("monthly", "📅 Monthly Report"),
            ("annual",  "📆 Annual Report"),
            ("gstr",    "🧾 GST Summary"),
        ]:
            btn = tk.Button(
                tab_bar,
                text=label,
                font=FONTS["label_bold"],
                relief="flat",
                padx=15, pady=8,
                cursor="hand2",
                command=lambda k=key:
                    self._switch_tab(k)
            )
            btn.pack(side="left", padx=(0, 3))
            self.tab_btns[key] = btn

        tk.Frame(
            self,
            bg=COLORS["primary"],
            height=2
        ).pack(fill="x", padx=25)

        self._switch_tab("monthly")

    def _switch_tab(self, tab_key: str):
        """Switch report tab"""
        self.active_tab.set(tab_key)

        for key, btn in self.tab_btns.items():
            if key == tab_key:
                btn.configure(
                    bg=COLORS["primary"],
                    fg="white"
                )
            else:
                btn.configure(
                    bg=COLORS["border"],
                    fg=COLORS["text_dark"]
                )

        if tab_key == "monthly":
            self._load_monthly_report()
        elif tab_key == "annual":
            self._load_annual_report()
        elif tab_key == "gstr":
            self._load_gstr_summary()

    def _build_scroll_area(self):
        """Scrollable content area"""
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

    def _on_month_change(self, month_name):
        self.view_month.set(
            MONTH_NAMES.index(month_name)
        )
        if self.active_tab.get() == "monthly":
            self._load_monthly_report()
        elif self.active_tab.get() == "gstr":
            self._load_gstr_summary()

    def _on_year_change(self, year_str):
        self.view_year.set(int(year_str))
        tab = self.active_tab.get()
        if tab == "monthly":
            self._load_monthly_report()
        elif tab == "annual":
            self._load_annual_report()
        elif tab == "gstr":
            self._load_gstr_summary()

    # ----------------------------------------------------------
    # MONTHLY REPORT
    # ----------------------------------------------------------
    def _load_monthly_report(self):
        """Build and display monthly report"""
        self._clear_content()

        month = self.view_month.get()
        year  = self.view_year.get()
        data  = self.fetcher.get_monthly_data(
            month, year
        )

        self._render_monthly_header(data)
        self._render_summary_cards(data)
        self._render_gst_payable_box(data)
        self._render_purchase_table(data)
        self._render_sales_table(data)
        self._render_item_tally_table(data)
        self._render_top_bills(data)

    def _render_monthly_header(self, data: dict):
        """Month/Year title"""
        month = data["month"]
        year  = data["year"]

        hdr = tk.Frame(
            self.content, bg=COLORS["primary"],
            pady=12
        )
        hdr.pack(fill="x", padx=20, pady=(15, 0))

        tk.Label(
            hdr,
            text=f"📅  Monthly Report — "
                 f"{MONTH_NAMES[month]} {year}",
            font=FONTS["subheading"],
            bg=COLORS["primary"],
            fg="white"
        ).pack(side="left", padx=15)

        # Status badge
        p_total = data["purchase"].get("total", 0)
        s_total = data["sales"].get("total", 0)

        if p_total == 0:
            status = "⚠️ No Data"
            sc     = "#f57f17"
        elif s_total == 0:
            status = "⚠️ Sales Missing"
            sc     = "#f57f17"
        else:
            status = "✅ Complete"
            sc     = "#a5d6a7"

        tk.Label(
            hdr,
            text=status,
            font=FONTS["body_bold"],
            bg=COLORS["primary"],
            fg=sc
        ).pack(side="right", padx=15)

    def _render_summary_cards(self, data: dict):
        """6 summary stat cards"""
        p = data["purchase"]
        s = data["sales"]

        cards_frame = tk.Frame(
            self.content, bg=COLORS["bg_main"]
        )
        cards_frame.pack(
            fill="x", padx=20, pady=10
        )

        # Row 1
        row1 = tk.Frame(
            cards_frame, bg=COLORS["bg_main"]
        )
        row1.pack(fill="x")

        card_defs_r1 = [
            ("📥 Purchase Total",
             format_inr(p.get("total", 0)),
             f"{p.get('bill_count', 0)} bills from "
             f"{p.get('dealer_count', 0)} dealers",
             "#1565c0"),
            ("📤 Sales Total",
             format_inr(s.get("total", 0)),
             f"{s.get('bill_count', 0)} bills to "
             f"{s.get('customer_count', 0)} customers",
             "#2e7d32"),
            ("💰 Gross Profit",
             format_inr(data["profit"]),
             f"Margin: {data['margin_pct']:.1f}%",
             "#e65100"),
        ]

        for title, value, sub, color in card_defs_r1:
            self._make_stat_card(
                row1, title, value, sub, color
            )

        # Row 2
        row2 = tk.Frame(
            cards_frame, bg=COLORS["bg_main"]
        )
        row2.pack(fill="x", pady=(8, 0))

        card_defs_r2 = [
            ("📥 Input GST",
             format_inr(data["p_gst"]),
             "GST paid on purchases",
             "#4527a0"),
            ("📤 Output GST",
             format_inr(data["s_gst"]),
             f"CGST: {format_inr(data['s_cgst'])}  "
             f"SGST: {format_inr(data['s_sgst'])}",
             "#00695c"),
            ("🧾 GST Payable",
             format_inr(data["gst_payable"]),
             "Output GST − Input GST",
             "#b71c1c"
             if data["gst_payable"] > 0
             else "#2e7d32"),
        ]

        for title, value, sub, color in card_defs_r2:
            self._make_stat_card(
                row2, title, value, sub, color
            )

    def _make_stat_card(
        self, parent, title, value, sub, color
    ):
        """Create one stat card widget"""
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
            card,
            text=title,
            font=FONTS["label_bold"],
            bg=color,
            fg="#e0e0e0"
        ).pack(anchor="w")

        tk.Label(
            card,
            text=value,
            font=FONTS["number_sm"],
            bg=color,
            fg="white"
        ).pack(anchor="w", pady=(5, 0))

        tk.Label(
            card,
            text=sub,
            font=FONTS["small"],
            bg=color,
            fg="#e0e0e0"
        ).pack(anchor="w")

    def _render_gst_payable_box(self, data: dict):
        """GST payable breakdown box"""
        box = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=12
        )
        box.pack(
            fill="x", padx=20, pady=5
        )

        tk.Label(
            box,
            text="🧾 GST Payable Calculation",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 8))

        # GST summary by rate
        gst_data = data.get("gst_summary", [])
        input_data = data.get("input_gst", [])

        # Build input GST map
        input_map = {
            r["gst_rate"]: r
            for r in input_data
        }

        if not gst_data:
            tk.Label(
                box,
                text="No GST data for this month.",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack()
            return

        # Table
        hdr_frame = tk.Frame(
            box, bg=COLORS["header_bg"]
        )
        hdr_frame.pack(fill="x")

        for col, width in [
            ("GST Rate", 10),
            ("Taxable Sales", 15),
            ("Output CGST",  13),
            ("Output SGST",  13),
            ("Output Total", 13),
            ("Input GST",    13),
            ("Net Payable",  13),
        ]:
            tk.Label(
                hdr_frame,
                text=col,
                font=FONTS["table_bold"],
                bg=COLORS["header_bg"],
                fg="white",
                width=width,
                anchor="w",
                padx=5, pady=6
            ).pack(side="left")

        total_net = 0

        for i, row in enumerate(gst_data):
            bg = (COLORS["row_even"]
                  if i % 2 == 0
                  else COLORS["row_odd"])
            rf = tk.Frame(box, bg=bg)
            rf.pack(fill="x")

            gst_rate  = row["gst_rate"]
            cgst_r    = gst_rate / 2
            sgst_r    = gst_rate / 2
            out_cgst  = row["cgst"]
            out_sgst  = row["sgst"]
            out_total = out_cgst + out_sgst

            inp       = input_map.get(gst_rate, {})
            in_gst    = inp.get("gst", 0)
            net_pay   = round2(
                max(0, out_total - in_gst)
            )
            total_net += net_pay

            for text, width in [
                (f"{gst_rate:.0f}% "
                 f"(C:{cgst_r:.0f}% S:{sgst_r:.0f}%)",
                 10),
                (format_inr(row["taxable"]), 15),
                (format_inr(out_cgst),       13),
                (format_inr(out_sgst),       13),
                (format_inr(out_total),      13),
                (format_inr(in_gst),         13),
                (format_inr(net_pay),        13),
            ]:
                tk.Label(
                    rf,
                    text=text,
                    font=FONTS["table"],
                    bg=bg,
                    fg=COLORS["text_dark"],
                    width=width,
                    anchor="w",
                    padx=5, pady=5
                ).pack(side="left")

        # Total row
        total_row = tk.Frame(
            box, bg=COLORS["primary"]
        )
        total_row.pack(fill="x")

        for text, width in [
            ("TOTAL", 10),
            (format_inr(
                sum(r["taxable"] for r in gst_data)
            ), 15),
            (format_inr(data["s_cgst"]), 13),
            (format_inr(data["s_sgst"]), 13),
            (format_inr(data["s_gst"]),  13),
            (format_inr(data["p_gst"]),  13),
            (format_inr(data["gst_payable"]), 13),
        ]:
            tk.Label(
                total_row,
                text=text,
                font=FONTS["table_bold"],
                bg=COLORS["primary"],
                fg="white",
                width=width,
                anchor="w",
                padx=5, pady=7
            ).pack(side="left")

    def _render_purchase_table(self, data: dict):
        """Purchase bills summary table"""
        section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=12
        )
        section.pack(
            fill="x", padx=20, pady=5
        )

        tk.Label(
            section,
            text="📥 Purchase Summary",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 8))

        # Get dealer-wise breakdown
        dealers = db.query("""
            SELECT
                dealer_name,
                COUNT(*) AS bill_count,
                SUM(subtotal)    AS taxable,
                SUM(total_gst)   AS gst,
                SUM(grand_total) AS total,
                MIN(bill_date)   AS first_date,
                MAX(bill_date)   AS last_date
            FROM purchase_bills
            WHERE bill_month=? AND bill_year=?
            GROUP BY dealer_name
            ORDER BY total DESC
        """, (data["month"], data["year"]))

        if not dealers:
            tk.Label(
                section,
                text="No purchase data for this month.",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(pady=10)
            return

        # Table header
        hdr = tk.Frame(section, bg=COLORS["header_bg"])
        hdr.pack(fill="x")

        for col, width in [
            ("Dealer Name",  22), ("Bills",   6),
            ("Taxable",      14), ("GST",     12),
            ("Total",        14), ("Period",  18),
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

        for i, dealer in enumerate(dealers):
            bg = (COLORS["row_even"]
                  if i % 2 == 0
                  else COLORS["row_odd"])
            row = tk.Frame(section, bg=bg)
            row.pack(fill="x")

            # Format dates
            try:
                d1 = datetime.strptime(
                    dealer["first_date"], "%Y-%m-%d"
                ).strftime("%d/%m")
                d2 = datetime.strptime(
                    dealer["last_date"], "%Y-%m-%d"
                ).strftime("%d/%m")
                period = f"{d1} – {d2}"
            except Exception:
                period = ""

            for text, width in [
                (dealer["dealer_name"],        22),
                (str(dealer["bill_count"]),     6),
                (format_inr(dealer["taxable"]),14),
                (format_inr(dealer["gst"]),    12),
                (format_inr(dealer["total"]),  14),
                (period,                       18),
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

    def _render_sales_table(self, data: dict):
        """Sales bills summary table"""
        section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=12
        )
        section.pack(
            fill="x", padx=20, pady=5
        )

        tk.Label(
            section,
            text="📤 Sales Summary",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 8))

        s = data["sales"]

        # Quick stats
        stats_row = tk.Frame(
            section, bg=COLORS["bg_card"]
        )
        stats_row.pack(fill="x", pady=5)

        for label, value in [
            ("Total Bills",
             str(s.get("bill_count", 0))),
            ("Unique Customers",
             str(s.get("customer_count", 0))),
            ("Avg Bill Amount",
             format_inr(s.get("avg_bill", 0) or 0)),
            ("Sales Total",
             format_inr(s.get("total", 0))),
        ]:
            box = tk.Frame(
                stats_row,
                bg=COLORS["success_light"],
                padx=12, pady=8
            )
            box.pack(
                side="left", padx=5,
                fill="both", expand=True
            )
            tk.Label(
                box,
                text=label,
                font=FONTS["small"],
                bg=COLORS["success_light"],
                fg=COLORS["text_muted"]
            ).pack()
            tk.Label(
                box,
                text=value,
                font=FONTS["label_bold"],
                bg=COLORS["success_light"],
                fg=COLORS["success"]
            ).pack()

    def _render_item_tally_table(self, data: dict):
        """Item-wise purchase vs sales tally"""
        section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=12
        )
        section.pack(
            fill="x", padx=20, pady=5
        )

        tk.Label(
            section,
            text="📦 Item-wise Tally",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 8))

        p_items = {
            i["item_name"].lower(): i
            for i in data.get("purchase_items", [])
        }
        s_items = {
            i["item_name"].lower(): i
            for i in data.get("sales_items", [])
        }

        all_items = set(p_items.keys()) | set(s_items.keys())

        if not all_items:
            tk.Label(
                section,
                text="No item data available.",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(pady=10)
            return

        # Header
        hdr = tk.Frame(section, bg=COLORS["header_bg"])
        hdr.pack(fill="x")

        for col, width in [
            ("Item Name",    22), ("Unit",     8),
            ("Purchased",    10), ("Sold",     10),
            ("Remaining",    10), ("Buy Rate", 11),
            ("Sell Rate",    11), ("Margin%",   9),
            ("Status",        8),
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

        for i, item_key in enumerate(
            sorted(all_items)
        ):
            p = p_items.get(item_key, {})
            s = s_items.get(item_key, {})

            bg = (COLORS["row_even"]
                  if i % 2 == 0
                  else COLORS["row_odd"])
            row = tk.Frame(section, bg=bg)
            row.pack(fill="x")

            purchased = p.get("purchased", 0)
            remaining = p.get("remaining", 0)
            sold      = round(
                purchased - remaining, 3
            )
            buy_rate  = p.get("avg_buy_rate", 0) or 0
            sell_rate = s.get("avg_sell_rate", 0) or 0
            margin    = s.get("avg_margin", 0) or 0

            ok = abs(remaining) < 0.01
            status       = "✅" if ok else f"⚠️{remaining:.1f}"
            status_color = (
                COLORS["success"]
                if ok else COLORS["warning"]
            )

            item_name = (
                p.get("item_name") or
                s.get("item_name") or
                item_key.title()
            )
            unit = (
                p.get("unit") or
                s.get("unit") or "-"
            )

            for text, width in [
                (item_name,             22),
                (unit,                   8),
                (f"{purchased:.1f}",    10),
                (f"{sold:.1f}",         10),
                (f"{remaining:.1f}",    10),
                (f"₹{buy_rate:.2f}",   11),
                (f"₹{sell_rate:.2f}",  11),
                (f"{margin:.1f}%",      9),
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

    def _render_top_bills(self, data: dict):
        """Top 5 highest value sales bills"""
        section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=12
        )
        section.pack(
            fill="x", padx=20, pady=(5, 15)
        )

        tk.Label(
            section,
            text="🏆 Top 5 Sales Bills",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 8))

        top_bills = data.get("top_bills", [])
        if not top_bills:
            tk.Label(
                section,
                text="No sales bills yet.",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(pady=10)
            return

        hdr = tk.Frame(section, bg=COLORS["header_bg"])
        hdr.pack(fill="x")

        for col, width in [
            ("Rank",        5), ("Bill No",   14),
            ("Customer",   22), ("Date",      12),
            ("Amount",     15),
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

        for i, bill in enumerate(top_bills):
            bg = (COLORS["row_even"]
                  if i % 2 == 0
                  else COLORS["row_odd"])
            row = tk.Frame(section, bg=bg)
            row.pack(fill="x")

            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            medal  = medals[i] if i < 5 else str(i + 1)

            try:
                d = datetime.strptime(
                    bill["bill_date"], "%Y-%m-%d"
                ).strftime("%d/%m/%Y")
            except Exception:
                d = bill["bill_date"]

            for text, width in [
                (medal,                            5),
                (bill["bill_number"],             14),
                (bill["customer_name"],           22),
                (d,                               12),
                (format_inr(bill["grand_total"]), 15),
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

    # ----------------------------------------------------------
    # ANNUAL REPORT
    # ----------------------------------------------------------
    def _load_annual_report(self):
        """Build and display annual report"""
        self._clear_content()

        year = self.view_year.get()
        data = self.fetcher.get_annual_data(year)

        self._render_annual_header(data)
        self._render_annual_cards(data)
        self._render_turnover_tracker(data)
        self._render_annual_table(data)

    def _render_annual_header(self, data: dict):
        hdr = tk.Frame(
            self.content,
            bg=COLORS["primary"],
            pady=12
        )
        hdr.pack(fill="x", padx=20, pady=(15, 0))

        tk.Label(
            hdr,
            text=f"📆  Annual Report — {data['year']}",
            font=FONTS["subheading"],
            bg=COLORS["primary"],
            fg="white"
        ).pack(side="left", padx=15)

    def _render_annual_cards(self, data: dict):
        """Annual totals stat cards"""
        cards = tk.Frame(
            self.content, bg=COLORS["bg_main"]
        )
        cards.pack(fill="x", padx=20, pady=10)

        card_defs = [
            ("📥 Annual Purchases",
             format_inr(data["annual_p_total"]),
             f"{data['annual_p_count']} bills",
             "#1565c0"),
            ("📤 Annual Sales",
             format_inr(data["annual_s_total"]),
             f"{data['annual_s_count']} bills",
             "#2e7d32"),
            ("💰 Annual Profit",
             format_inr(data["annual_profit"]),
             "Gross profit on taxable",
             "#e65100"),
            ("🧾 Annual GST Payable",
             format_inr(data["annual_gst_pay"]),
             "Total output − input GST",
             "#6a1b9a"),
        ]

        for title, value, sub, color in card_defs:
            self._make_stat_card(
                cards, title, value, sub, color
            )

    def _render_turnover_tracker(self, data: dict):
        """GST threshold tracker"""
        section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=15
        )
        section.pack(fill="x", padx=20, pady=8)

        tk.Label(
            section,
            text="📏 Annual Turnover Tracker",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 10))

        turnover  = data["turnover"]
        t_pct     = min(data["threshold_pct"], 100)
        c_pct     = min(data["comp_limit_pct"], 100)

        # GST registration threshold bar
        for label, amount, pct, color, note in [
            ("GST Registration Threshold",
             GST_THRESHOLD,
             t_pct,
             COLORS["warning"],
             "Mandatory GST registration above ₹40 Lakhs"),
            ("Composition Scheme Limit",
             COMPOSITION_LIMIT,
             c_pct,
             COLORS["primary"],
             "Cannot use composition above ₹1.5 Crores"),
        ]:
            bar_frame = tk.Frame(
                section, bg=COLORS["bg_card"]
            )
            bar_frame.pack(fill="x", pady=5)

            tk.Label(
                bar_frame,
                text=label,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_dark"]
            ).pack(anchor="w")

            info_row = tk.Frame(
                bar_frame, bg=COLORS["bg_card"]
            )
            info_row.pack(fill="x")

            tk.Label(
                info_row,
                text=f"Your turnover: "
                     f"{format_inr(turnover)}  /  "
                     f"Limit: {format_inr(amount)}  "
                     f"({pct:.1f}%)",
                font=FONTS["small"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(side="left")

            # Progress bar
            prog_outer = tk.Frame(
                bar_frame,
                bg=COLORS["border"],
                height=16
            )
            prog_outer.pack(fill="x", pady=3)

            bar_color = (
                COLORS["danger"]
                if pct >= 90 else
                COLORS["warning"]
                if pct >= 70 else
                color
            )

            prog_inner = tk.Frame(
                prog_outer,
                bg=bar_color,
                height=16
            )
            prog_inner.place(
                relx=0, rely=0,
                relwidth=min(pct / 100, 1),
                relheight=1
            )

            # Percentage label inside bar
            tk.Label(
                prog_outer,
                text=f"{pct:.1f}%",
                font=FONTS["small"],
                bg=bar_color if pct > 10 else COLORS["border"],
                fg="white"
            ).place(
                relx=max(0, min(pct / 100, 1) - 0.08),
                rely=0,
                relheight=1
            )

            tk.Label(
                bar_frame,
                text=note,
                font=FONTS["small"],
                bg=COLORS["bg_card"],
                fg=(COLORS["danger"]
                    if pct >= 90
                    else COLORS["text_muted"])
            ).pack(anchor="w")

    def _render_annual_table(self, data: dict):
        """Month-wise annual table"""
        section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=12
        )
        section.pack(
            fill="x", padx=20, pady=(5, 15)
        )

        tk.Label(
            section,
            text="📅 Month-wise Breakdown",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 8))

        # Header
        hdr = tk.Frame(section, bg=COLORS["header_bg"])
        hdr.pack(fill="x")

        for col, width in [
            ("Month",      10), ("P.Bills",   7),
            ("P.Total",    14), ("S.Bills",   7),
            ("S.Total",    14), ("Profit",    13),
            ("GST Pay",    13), ("Status",     8),
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

        for i, m in enumerate(data["months_data"]):
            bg = (COLORS["row_even"]
                  if i % 2 == 0
                  else COLORS["row_odd"])
            row = tk.Frame(section, bg=bg)
            row.pack(fill="x")

            # Highlight current month
            today = date.today()
            is_current = (
                m["month"] == today.month and
                data["year"] == today.year
            )
            if is_current:
                bg = "#e3f2fd"
                row.configure(bg=bg)

            has_data = m["p_count"] > 0
            status = (
                "✅" if m["p_count"] > 0 and
                         m["s_count"] > 0
                else "⚠️" if m["p_count"] > 0
                else "—"
            )
            status_color = (
                COLORS["success"]
                if status == "✅" else
                COLORS["warning"]
                if status == "⚠️" else
                COLORS["text_muted"]
            )

            for text, width in [
                (m["month_name"][:3] +
                 (" ◀" if is_current else ""), 10),
                (str(m["p_count"]) if has_data else "—", 7),
                (format_inr(m["p_total"])
                 if has_data else "—", 14),
                (str(m["s_count"])
                 if m["s_count"] > 0 else "—", 7),
                (format_inr(m["s_total"])
                 if m["s_count"] > 0 else "—", 14),
                (format_inr(m["profit"])
                 if has_data else "—", 13),
                (format_inr(m["gst_payable"])
                 if has_data else "—", 13),
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

        # Totals row
        total_row = tk.Frame(
            section, bg=COLORS["primary"]
        )
        total_row.pack(fill="x")

        for text, width in [
            ("ANNUAL TOTAL", 10),
            (str(data["annual_p_count"]), 7),
            (format_inr(data["annual_p_total"]), 14),
            (str(data["annual_s_count"]), 7),
            (format_inr(data["annual_s_total"]), 14),
            (format_inr(data["annual_profit"]), 13),
            (format_inr(data["annual_gst_pay"]), 13),
            ("", 8),
        ]:
            tk.Label(
                total_row,
                text=text,
                font=FONTS["table_bold"],
                bg=COLORS["primary"],
                fg="white",
                width=width,
                anchor="w",
                padx=5, pady=8
            ).pack(side="left")

    # ----------------------------------------------------------
    # GSTR SUMMARY
    # ----------------------------------------------------------
    def _load_gstr_summary(self):
        """Build GSTR-ready GST summary"""
        self._clear_content()

        month = self.view_month.get()
        year  = self.view_year.get()
        data  = self.fetcher.get_monthly_data(
            month, year
        )

        hdr = tk.Frame(
            self.content,
            bg=COLORS["primary"],
            pady=12
        )
        hdr.pack(fill="x", padx=20, pady=(15, 10))

        tk.Label(
            hdr,
            text=f"🧾  GST Summary — "
                 f"{MONTH_NAMES[month]} {year}",
            font=FONTS["subheading"],
            bg=COLORS["primary"],
            fg="white"
        ).pack(side="left", padx=15)

        # GSTR-1 summary (Outward supplies)
        gstr_section = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=15
        )
        gstr_section.pack(
            fill="x", padx=20, pady=5
        )

        tk.Label(
            gstr_section,
            text="GSTR-1 Summary (Outward Supplies — B2C)",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 8))

        # B2C sales summary by GST rate
        gst_data = data.get("gst_summary", [])

        hdr_f = tk.Frame(
            gstr_section, bg=COLORS["header_bg"]
        )
        hdr_f.pack(fill="x")

        for col, width in [
            ("GST Rate",   10), ("Taxable Value", 18),
            ("CGST",       14), ("SGST",          14),
            ("Total Tax",  14),
        ]:
            tk.Label(
                hdr_f,
                text=col,
                font=FONTS["table_bold"],
                bg=COLORS["header_bg"],
                fg="white",
                width=width,
                anchor="w",
                padx=5, pady=6
            ).pack(side="left")

        for i, row in enumerate(gst_data):
            bg = (COLORS["row_even"]
                  if i % 2 == 0
                  else COLORS["row_odd"])
            rf = tk.Frame(gstr_section, bg=bg)
            rf.pack(fill="x")

            for text, width in [
                (f"{row['gst_rate']:.0f}%",  10),
                (format_inr(row["taxable"]), 18),
                (format_inr(row["cgst"]),    14),
                (format_inr(row["sgst"]),    14),
                (format_inr(
                    row["cgst"] + row["sgst"]
                ), 14),
            ]:
                tk.Label(
                    rf,
                    text=text,
                    font=FONTS["table"],
                    bg=bg,
                    fg=COLORS["text_dark"],
                    width=width,
                    anchor="w",
                    padx=5, pady=5
                ).pack(side="left")

        # GSTR-3B summary
        gstr3b = tk.Frame(
            self.content,
            bg=COLORS["bg_card"],
            padx=20, pady=15
        )
        gstr3b.pack(fill="x", padx=20, pady=5)

        tk.Label(
            gstr3b,
            text="GSTR-3B Summary (Tax Payable)",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 10))

        p = data["purchase"]
        s = data["sales"]

        entries = [
            ("3.1 Outward taxable supplies (B2C)",
             format_inr(s.get("taxable", 0)),
             format_inr(data["s_cgst"]),
             format_inr(data["s_sgst"])),
            ("4 Input Tax Credit (ITC) available",
             format_inr(p.get("taxable", 0)),
             format_inr(data["p_gst"] / 2),
             format_inr(data["p_gst"] / 2)),
            ("Net GST Payable (3.1 - 4)",
             "—",
             format_inr(
                 max(0, data["s_cgst"] -
                     data["p_gst"] / 2)
             ),
             format_inr(
                 max(0, data["s_sgst"] -
                     data["p_gst"] / 2)
             )),
        ]

        for label, taxable, cgst, sgst in entries:
            row_f = tk.Frame(gstr3b, bg=COLORS["bg_card"])
            row_f.pack(fill="x", pady=4)

            tk.Label(
                row_f,
                text=label,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_dark"],
                width=45,
                anchor="w"
            ).pack(side="left", padx=(0, 10))

            for val, lbl in [
                (taxable, "Taxable"),
                (cgst,    "CGST"),
                (sgst,    "SGST"),
            ]:
                box = tk.Frame(
                    row_f,
                    bg=COLORS["success_light"],
                    padx=8, pady=4
                )
                box.pack(side="left", padx=3)
                tk.Label(
                    box,
                    text=lbl,
                    font=FONTS["small"],
                    bg=COLORS["success_light"],
                    fg=COLORS["text_muted"]
                ).pack()
                tk.Label(
                    box,
                    text=val,
                    font=FONTS["label_bold"],
                    bg=COLORS["success_light"],
                    fg=COLORS["success"]
                ).pack()

        # Disclaimer
        tk.Label(
            self.content,
            text="⚠️  This is a summary for reference only. "
                 "Please consult your CA/accountant "
                 "before filing GST returns.",
            font=FONTS["small"],
            bg=COLORS["bg_main"],
            fg=COLORS["warning"],
            wraplength=700,
            justify="left"
        ).pack(
            anchor="w", padx=25, pady=(5, 15)
        )

    # ----------------------------------------------------------
    # EXPORT FUNCTIONS
    # ----------------------------------------------------------
    def _export_pdf(self):
        """Export current report to PDF"""
        tab   = self.active_tab.get()
        month = self.view_month.get()
        year  = self.view_year.get()

        if tab == "monthly":
            default_name = (
                f"report_{year}_{month:02d}"
                f"_{MONTH_NAMES[month]}.pdf"
            )
        else:
            default_name = f"annual_report_{year}.pdf"

        path = filedialog.asksaveasfilename(
            title="Export Report as PDF",
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[
                ("PDF files", "*.pdf"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        try:
            from modules.pdf_generator import (
                PDFGenerator
            )
            settings = load_settings()

            if tab == "monthly":
                data = self.fetcher.get_monthly_data(
                    month, year
                )
                self._generate_monthly_pdf(
                    data, path, settings
                )
            else:
                data = self.fetcher.get_annual_data(year)
                self._generate_annual_pdf(
                    data, path, settings
                )

            messagebox.showinfo(
                "Export Complete ✅",
                f"Report saved to:\n{path}"
            )
            os.startfile(path)

        except Exception as e:
            messagebox.showerror(
                "Export Error",
                f"Could not export PDF.\n\n{e}"
            )

    def _generate_monthly_pdf(
        self,
        data: dict,
        path: str,
        settings: dict
    ):
        """Generate monthly report PDF"""
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

        month = data["month"]
        year  = data["year"]
        shop  = settings.get("shop", {})

        doc = SimpleDocTemplate(
            path,
            pagesize=A4,
            rightMargin=15*mm,
            leftMargin=15*mm,
            topMargin=12*mm,
            bottomMargin=15*mm,
            title=(
                f"Monthly Report "
                f"{MONTH_NAMES[month]} {year}"
            )
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
            f"Monthly Report — "
            f"{MONTH_NAMES[month]} {year}",
            ParagraphStyle(
                "RT",
                parent=styles["Normal"],
                fontSize=13,
                fontName="Helvetica-Bold",
                alignment=TA_CENTER
            )
        ))
        story.append(Spacer(1, 8*mm))

        # Summary table
        p = data["purchase"]
        s = data["sales"]

        summary_data = [
            ["Metric", "Purchase", "Sales"],
            ["Bills",
             str(p.get("bill_count", 0)),
             str(s.get("bill_count", 0))],
            ["Taxable Amount",
             format_inr(p.get("taxable", 0)),
             format_inr(s.get("taxable", 0))],
            ["Total GST",
             format_inr(data["p_gst"]),
             format_inr(data["s_gst"])],
            ["Grand Total",
             format_inr(p.get("total", 0)),
             format_inr(s.get("total", 0))],
            ["Profit", "—",
             format_inr(data["profit"])],
            ["GST Payable", "—",
             format_inr(data["gst_payable"])],
        ]

        summary_table = Table(
            summary_data,
            colWidths=[70*mm, 55*mm, 55*mm]
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
            ("BACKGROUND",
             (0, -1), (-1, -1),
             colors.HexColor("#e8f5e9")),
            ("FONTNAME",
             (0, -1), (-1, -1),
             "Helvetica-Bold"),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 8*mm))

        # Item tally table
        story.append(Paragraph(
            "Item-wise Tally",
            ParagraphStyle(
                "IH",
                parent=styles["Normal"],
                fontSize=12,
                fontName="Helvetica-Bold"
            )
        ))
        story.append(Spacer(1, 3*mm))

        p_items = {
            i["item_name"].lower(): i
            for i in data.get("purchase_items", [])
        }
        s_items = {
            i["item_name"].lower(): i
            for i in data.get("sales_items", [])
        }
        all_items = sorted(
            set(p_items.keys()) | set(s_items.keys())
        )

        tally_rows = [[
            "Item", "Unit",
            "Purchased", "Sold", "Remaining",
            "Status"
        ]]

        for key in all_items:
            p_i = p_items.get(key, {})
            s_i = s_items.get(key, {})
            purchased = p_i.get("purchased", 0)
            remaining = p_i.get("remaining", 0)
            sold      = round(
                purchased - remaining, 3
            )
            ok     = abs(remaining) < 0.01
            status = "OK" if ok else f"⚠ {remaining:.1f}"

            tally_rows.append([
                p_i.get("item_name") or
                s_i.get("item_name") or
                key.title(),
                p_i.get("unit") or
                s_i.get("unit") or "-",
                f"{purchased:.1f}",
                f"{sold:.1f}",
                f"{remaining:.1f}",
                status,
            ])

        if len(tally_rows) > 1:
            tally_table = Table(
                tally_rows,
                colWidths=[
                    55*mm, 15*mm, 22*mm,
                    22*mm, 22*mm, 22*mm
                ]
            )
            tally_table.setStyle(TableStyle([
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
            story.append(tally_table)

        doc.build(story)

    def _generate_annual_pdf(
        self,
        data: dict,
        path: str,
        settings: dict
    ):
        """Generate annual report PDF"""
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

        year = data["year"]
        shop = settings.get("shop", {})

        doc = SimpleDocTemplate(
            path,
            pagesize=A4,
            rightMargin=12*mm,
            leftMargin=12*mm,
            topMargin=12*mm,
            bottomMargin=12*mm,
            title=f"Annual Report {year}"
        )

        styles = getSampleStyleSheet()
        story  = []

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
            f"Annual Report — {year}",
            ParagraphStyle(
                "RT",
                parent=styles["Normal"],
                fontSize=14,
                fontName="Helvetica-Bold",
                alignment=TA_CENTER
            )
        ))
        story.append(Spacer(1, 8*mm))

        # Month-wise table
        annual_rows = [[
            "Month",
            "P.Bills", "P.Total",
            "S.Bills", "S.Total",
            "Profit", "GST Pay"
        ]]

        for m in data["months_data"]:
            annual_rows.append([
                m["month_name"][:3],
                str(m["p_count"])
                if m["p_count"] > 0 else "—",
                format_inr(m["p_total"])
                if m["p_count"] > 0 else "—",
                str(m["s_count"])
                if m["s_count"] > 0 else "—",
                format_inr(m["s_total"])
                if m["s_count"] > 0 else "—",
                format_inr(m["profit"])
                if m["p_count"] > 0 else "—",
                format_inr(m["gst_payable"])
                if m["p_count"] > 0 else "—",
            ])

        # Total row
        annual_rows.append([
            "TOTAL",
            str(data["annual_p_count"]),
            format_inr(data["annual_p_total"]),
            str(data["annual_s_count"]),
            format_inr(data["annual_s_total"]),
            format_inr(data["annual_profit"]),
            format_inr(data["annual_gst_pay"]),
        ])

        annual_table = Table(
            annual_rows,
            colWidths=[
                20*mm, 15*mm, 30*mm,
                15*mm, 30*mm, 28*mm, 28*mm
            ]
        )
        annual_table.setStyle(TableStyle([
            ("BACKGROUND",
             (0, 0), (-1, 0),
             colors.HexColor("#1a237e")),
            ("TEXTCOLOR",
             (0, 0), (-1, 0),
             colors.white),
            ("BACKGROUND",
             (0, -1), (-1, -1),
             colors.HexColor("#e8f5e9")),
            ("FONTNAME",
             (0, 0), (-1, 0),
             "Helvetica-Bold"),
            ("FONTNAME",
             (0, -1), (-1, -1),
             "Helvetica-Bold"),
            ("FONTNAME",
             (0, 1), (-1, -2),
             "Helvetica"),
            ("FONTSIZE",
             (0, 0), (-1, -1), 9),
            ("BOX",
             (0, 0), (-1, -1),
             1, colors.HexColor("#1a237e")),
            ("INNERGRID",
             (0, 0), (-1, -1),
             0.3, colors.grey),
            ("ALIGN",
             (1, 0), (-1, -1), "RIGHT"),
            ("TOPPADDING",
             (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",
             (0, 0), (-1, -1), 5),
            ("LEFTPADDING",
             (0, 0), (-1, -1), 5),
        ]))
        story.append(annual_table)
        story.append(Spacer(1, 8*mm))

        # Turnover info
        story.append(Paragraph(
            f"Annual Turnover: "
            f"{format_inr(data['turnover'])}  |  "
            f"GST Threshold Used: "
            f"{data['threshold_pct']:.1f}%",
            ParagraphStyle(
                "TI",
                parent=styles["Normal"],
                fontSize=10,
                fontName="Helvetica-Bold"
            )
        ))

        doc.build(story)

    def _export_csv(self):
        """Export report data to CSV"""
        tab   = self.active_tab.get()
        month = self.view_month.get()
        year  = self.view_year.get()

        if tab == "monthly":
            default_name = (
                f"report_{year}_{month:02d}.csv"
            )
        else:
            default_name = f"annual_{year}.csv"

        path = filedialog.asksaveasfilename(
            title="Export Report as CSV",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        try:
            if tab == "monthly":
                data = self.fetcher.get_monthly_data(
                    month, year
                )
                self._write_monthly_csv(data, path)
            else:
                data = self.fetcher.get_annual_data(year)
                self._write_annual_csv(data, path)

            messagebox.showinfo(
                "Export Complete ✅",
                f"CSV saved to:\n{path}"
            )
            os.startfile(
                str(Path(path).parent)
            )

        except Exception as e:
            messagebox.showerror(
                "Export Error",
                f"Could not export CSV.\n\n{e}"
            )

    def _write_monthly_csv(
        self, data: dict, path: str
    ):
        """Write monthly report CSV"""
        with open(
            path, "w", newline="",
            encoding="utf-8-sig"
        ) as f:
            writer = csv.writer(f)

            # Summary section
            writer.writerow(
                [f"Monthly Report — "
                 f"{MONTH_NAMES[data['month']]} "
                 f"{data['year']}"]
            )
            writer.writerow([])
            writer.writerow([
                "Category", "Bills",
                "Taxable", "GST", "Total"
            ])

            p = data["purchase"]
            s = data["sales"]

            writer.writerow([
                "Purchase",
                p.get("bill_count", 0),
                p.get("taxable", 0),
                data["p_gst"],
                p.get("total", 0)
            ])
            writer.writerow([
                "Sales",
                s.get("bill_count", 0),
                s.get("taxable", 0),
                data["s_gst"],
                s.get("total", 0)
            ])
            writer.writerow([
                "Profit", "",
                data["profit"],
                "", ""
            ])
            writer.writerow([
                "GST Payable", "", "",
                data["gst_payable"], ""
            ])

            writer.writerow([])

            # Item tally
            writer.writerow([
                "Item Name", "Unit",
                "Purchased", "Sold",
                "Remaining", "Status"
            ])

            p_items = {
                i["item_name"].lower(): i
                for i in data.get(
                    "purchase_items", []
                )
            }
            s_items = {
                i["item_name"].lower(): i
                for i in data.get(
                    "sales_items", []
                )
            }

            for key in sorted(
                set(p_items.keys()) |
                set(s_items.keys())
            ):
                p_i = p_items.get(key, {})
                s_i = s_items.get(key, {})
                purchased = p_i.get("purchased", 0)
                remaining = p_i.get("remaining", 0)
                sold = round(
                    purchased - remaining, 3
                )
                status = (
                    "OK"
                    if abs(remaining) < 0.01
                    else f"Remaining: {remaining}"
                )
                writer.writerow([
                    p_i.get("item_name") or
                    s_i.get("item_name") or
                    key.title(),
                    p_i.get("unit") or
                    s_i.get("unit") or "-",
                    purchased, sold,
                    remaining, status
                ])

    def _write_annual_csv(
        self, data: dict, path: str
    ):
        """Write annual report CSV"""
        with open(
            path, "w", newline="",
            encoding="utf-8-sig"
        ) as f:
            writer = csv.writer(f)

            writer.writerow(
                [f"Annual Report — {data['year']}"]
            )
            writer.writerow([])
            writer.writerow([
                "Month",
                "Purchase Bills", "Purchase Total",
                "Sales Bills", "Sales Total",
                "Profit", "GST Payable"
            ])

            for m in data["months_data"]:
                writer.writerow([
                    m["month_name"],
                    m["p_count"]
                    if m["p_count"] > 0 else "",
                    m["p_total"]
                    if m["p_count"] > 0 else "",
                    m["s_count"]
                    if m["s_count"] > 0 else "",
                    m["s_total"]
                    if m["s_count"] > 0 else "",
                    m["profit"]
                    if m["p_count"] > 0 else "",
                    m["gst_payable"]
                    if m["p_count"] > 0 else "",
                ])

            writer.writerow([
                "ANNUAL TOTAL",
                data["annual_p_count"],
                data["annual_p_total"],
                data["annual_s_count"],
                data["annual_s_total"],
                data["annual_profit"],
                data["annual_gst_pay"],
            ])

            writer.writerow([])
            writer.writerow([
                "Annual Turnover",
                data["turnover"]
            ])
            writer.writerow([
                "GST Threshold Used %",
                f"{data['threshold_pct']:.1f}%"
            ])