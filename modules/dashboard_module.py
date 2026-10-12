# modules/dashboard_module.py
# ============================================================
# DASHBOARD MODULE
# Home screen showing:
# 1. Monthly summary cards (current month)
# 2. Year selector — view any month/year
# 3. Purchase vs Sales tally status
# 4. Recent bills list
# 5. Quick action buttons
# 6. Monthly calendar overview (which months have data)
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import json
from pathlib import Path
from datetime import date, datetime
import calendar
from modules.date_utils import (
    DATE_PRESETS,
    get_date_range_for_preset,
    parse_flexible_date,
    format_date_display,
    format_date_iso,
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
    "primary":       "#1a237e",
    "primary_light": "#3949ab",
    "accent":        "#ff6f00",
    "success":       "#2e7d32",
    "success_light": "#e8f5e9",
    "warning":       "#f57f17",
    "warning_light": "#fff3e0",
    "danger":        "#c62828",
    "danger_light":  "#ffebee",
    "bg_main":       "#f5f5f5",
    "bg_card":       "#ffffff",
    "text_dark":     "#212121",
    "text_light":    "#ffffff",
    "text_muted":    "#757575",
    "border":        "#e0e0e0",
    "tally_ok":      "#2e7d32",
    "tally_warn":    "#f57f17",
    "tally_bad":     "#c62828",
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
    "number":     ("Helvetica", 20, "bold"),
    "number_sm":  ("Helvetica", 14, "bold"),
}

MONTH_NAMES = [
    "", "January", "February", "March", "April",
    "May", "June", "July", "August", "September",
    "October", "November", "December"
]


# ============================================================
# DATABASE HELPER
# ============================================================
class DBHelper:
    """Simple database query helper"""

    def __init__(self):
        self.db_path = DB_PATH

    def query(self, sql: str, params: tuple = ()) -> list:
        """Run SELECT query and return rows"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"[DB ERROR] {e}")
            return []

    def query_one(self, sql: str, params: tuple = ()) -> dict:
        """Run SELECT query and return single row"""
        rows = self.query(sql, params)
        return rows[0] if rows else {}

    def execute(self, sql: str, params: tuple = ()):
        """Run INSERT/UPDATE/DELETE"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB ERROR] {e}")


db = DBHelper()


# ============================================================
# LOAD SETTINGS
# ============================================================
def load_settings() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


# ============================================================
# DASHBOARD FRAME
# ============================================================
class DashboardFrame(tk.Frame):
    """
    Full dashboard home screen

    Layout:
    ┌──────────────────────────────────────────────────────┐
    │  Title + Month/Year Selector          [Refresh]      │
    ├──────────────────────────────────────────────────────┤
    │  [Purchase Card] [Sales Card] [Profit Card]          │
    │  [GST Payable]   [Bills Count] [Tally Status]        │
    ├──────────────────────────────────────────────────────┤
    │  LEFT: Recent Bills    │  RIGHT: Year Overview       │
    │  (table of last 10)    │  (12 months grid)           │
    ├──────────────────────────────────────────────────────┤
    │  Quick Actions                                       │
    └──────────────────────────────────────────────────────┘
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS["bg_main"])
        self.app      = app
        self.settings = load_settings()

        today = date.today()
        self.preset_var = tk.StringVar(value="This Month")
        s_date, e_date = get_date_range_for_preset("This Month")
        self.from_date_var = tk.StringVar(value=format_date_display(s_date) if s_date else "")
        self.to_date_var   = tk.StringVar(value=format_date_display(e_date) if e_date else "")
        self.view_month = tk.IntVar(value=today.month)
        self.view_year  = tk.IntVar(value=today.year)

        self._build_ui()
        self._load_dashboard_data()


    # ----------------------------------------------------------
    # BUILD UI SKELETON
    # ----------------------------------------------------------
    def _build_ui(self):
        """Build the complete dashboard layout"""

        # ---- Scrollable outer container ----
        outer = tk.Frame(self, bg=COLORS["bg_main"])
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            outer,
            bg=COLORS["bg_main"],
            highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=canvas.yview
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.scroll_frame = tk.Frame(canvas, bg=COLORS["bg_main"])
        canvas_window = canvas.create_window(
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
                canvas_window, width=e.width
            )
        )
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"
            )
        )

        # ---- Build sections ----
        self._build_top_bar()
        self._build_stat_cards()
        self._build_middle_section()
        self._build_quick_actions()


    # ----------------------------------------------------------
    # TOP BAR — Title + Date Range Selector
    # ----------------------------------------------------------
    def _build_top_bar(self):
        """Title row with date range presets and refresh"""
        top = tk.Frame(
            self.scroll_frame,
            bg=COLORS["bg_main"]
        )
        top.pack(fill="x", padx=25, pady=(20, 10))

        # Left — Title
        left = tk.Frame(top, bg=COLORS["bg_main"])
        left.pack(side="left")

        tk.Label(
            left,
            text="🏠  Dashboard",
            font=FONTS["heading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w")

        self.subtitle_label = tk.Label(
            left,
            text="",
            font=FONTS["body"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_muted"]
        )
        self.subtitle_label.pack(anchor="w")

        # Right — Period presets + From/To dates + Refresh
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

        # Refresh button
        tk.Button(
            right,
            text="🔄 Refresh",
            font=FONTS["label_bold"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._load_dashboard_data
        ).pack(side="left", padx=(10, 0))

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
        self._load_dashboard_data()

    def _get_active_date_range(self):
        s_raw = self.from_date_var.get().strip()
        e_raw = self.to_date_var.get().strip()
        s_date = parse_flexible_date(s_raw) if s_raw else None
        e_date = parse_flexible_date(e_raw) if e_raw else None
        return s_date, e_date

    # ----------------------------------------------------------
    # STAT CARDS ROW
    # ----------------------------------------------------------
    def _build_stat_cards(self):
        """6 summary cards in 2 rows of 3"""
        self.cards_frame = tk.Frame(
            self.scroll_frame,
            bg=COLORS["bg_main"]
        )
        self.cards_frame.pack(fill="x", padx=20, pady=5)

        # Row 1
        row1 = tk.Frame(self.cards_frame, bg=COLORS["bg_main"])
        row1.pack(fill="x")

        # Row 2
        row2 = tk.Frame(self.cards_frame, bg=COLORS["bg_main"])
        row2.pack(fill="x", pady=(8, 0))

        # Define cards — (key, title, icon, color, row)
        card_defs = [
            # Row 1
            ("purchase_total", "Total Purchases",
             "📥", "#1565c0", row1),
            ("sales_total",    "Total Sales",
             "📤", "#2e7d32", row1),
            ("stock_total",    "Active Stock on Hand",
             "📦", "#00838f", row1),
            # Row 2
            ("profit_total",   "Gross Profit",
             "💰", "#e65100", row2),
            ("gst_payable",    "GST Payable",
             "🧾", "#6a1b9a", row2),
            ("tally_status",   "Inventory Tally",
             "✅", "#1b5e20", row2),
        ]

        self.stat_labels = {}

        for key, title, icon, color, row_frame in card_defs:
            card = tk.Frame(
                row_frame,
                bg=color,
                padx=18,
                pady=14
            )
            card.pack(side="left", padx=8, pady=5,
                      fill="both", expand=True)

            # Icon + Title
            header = tk.Frame(card, bg=color)
            header.pack(fill="x")

            tk.Label(
                header,
                text=icon,
                font=("Helvetica", 16),
                bg=color,
                fg="white"
            ).pack(side="left")

            tk.Label(
                header,
                text=f"  {title}",
                font=FONTS["label_bold"],
                bg=color,
                fg="#e0e0e0"
            ).pack(side="left")

            # Value label (updated with data)
            value_lbl = tk.Label(
                card,
                text="Loading...",
                font=FONTS["number_sm"],
                bg=color,
                fg="white"
            )
            value_lbl.pack(anchor="w", pady=(8, 0))

            # Sub label
            sub_lbl = tk.Label(
                card,
                text="",
                font=FONTS["smaller"],
                bg=color,
                fg="#e0e0e0"
            )
            sub_lbl.pack(anchor="w")

            self.stat_labels[key] = (value_lbl, sub_lbl)


    # ----------------------------------------------------------
    # MIDDLE SECTION — Recent Bills + Year Overview
    # ----------------------------------------------------------
    def _build_middle_section(self):
        """Two-column middle section"""
        mid = tk.Frame(self.scroll_frame, bg=COLORS["bg_main"])
        mid.pack(fill="both", expand=True, padx=20, pady=10)

        # Left column — Recent Bills
        left = tk.Frame(mid, bg=COLORS["bg_card"],
                        padx=15, pady=15)
        left.pack(side="left", fill="both",
                  expand=True, padx=(5, 8))

        # Title
        title_row = tk.Frame(left, bg=COLORS["bg_card"])
        title_row.pack(fill="x", pady=(0, 10))

        tk.Label(
            title_row,
            text="📄 Recent Sales Bills",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Button(
            title_row,
            text="View All →",
            font=FONTS["small"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            command=self.app.show_sales
        ).pack(side="right")

        # Table headers
        self._build_recent_bills_table(left)

        # Right column — Year overview
        right = tk.Frame(mid, bg=COLORS["bg_card"],
                         padx=15, pady=15)
        right.pack(side="left", fill="both",
                   padx=(0, 5), ipadx=10)

        tk.Label(
            right,
            text="📅 Year Overview",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 10))

        self.year_overview_frame = tk.Frame(
            right,
            bg=COLORS["bg_card"]
        )
        self.year_overview_frame.pack(fill="both", expand=True)


    def _build_recent_bills_table(self, parent):
        """Build recent bills table with headers"""

        # Header row
        headers = [
            ("Bill No",       12),
            ("Customer",      18),
            ("Date",          12),
            ("Amount",        12),
            ("Status",         8),
        ]

        header_frame = tk.Frame(parent, bg=COLORS["primary"])
        header_frame.pack(fill="x")

        for col_name, width in headers:
            tk.Label(
                header_frame,
                text=col_name,
                font=FONTS["label_bold"],
                bg=COLORS["primary"],
                fg="white",
                width=width,
                anchor="w",
                padx=5,
                pady=6
            ).pack(side="left")

        # Scrollable table area
        table_outer = tk.Frame(parent, bg=COLORS["bg_card"])
        table_outer.pack(fill="both", expand=True)

        # Bills rows frame (populated with data)
        self.bills_table_frame = tk.Frame(
            table_outer,
            bg=COLORS["bg_card"]
        )
        self.bills_table_frame.pack(fill="both", expand=True)

        tk.Label(
            self.bills_table_frame,
            text="Loading...",
            font=FONTS["body"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        ).pack(pady=20)


    # ----------------------------------------------------------
    # QUICK ACTIONS
    # ----------------------------------------------------------
    def _build_quick_actions(self):
        """Quick action buttons at bottom"""
        section = tk.Frame(
            self.scroll_frame,
            bg=COLORS["bg_main"]
        )
        section.pack(fill="x", padx=25, pady=(10, 20))

        tk.Label(
            section,
            text="⚡ Quick Actions",
            font=FONTS["subheading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 10))

        btn_row = tk.Frame(section, bg=COLORS["bg_main"])
        btn_row.pack(fill="x")

        actions = [
            ("📥  Add Purchase Bill",
             self.app.show_purchase,
             COLORS["primary"]),

            ("📤  Generate Sales Bills",
             self.app.show_sales,
             COLORS["success"]),

            ("📊  Monthly Report",
             self.app.show_reports,
             COLORS["accent"]),

            ("👥  Manage Customers",
             self.app.show_customers,
             "#6a1b9a"),

            ("⚙️  Settings",
             self.app.show_settings,
             COLORS["text_muted"]),
        ]

        for label, command, color in actions:
            btn = tk.Button(
                btn_row,
                text=label,
                font=FONTS["button"],
                bg=color,
                fg="white",
                relief="flat",
                padx=18,
                pady=10,
                cursor="hand2",
                command=command
            )
            btn.pack(side="left", padx=6)

            # Hover effect
            btn.bind(
                "<Enter>",
                lambda e, b=btn, c=color: b.configure(
                    bg=self._darken(c)
                )
            )
            btn.bind(
                "<Leave>",
                lambda e, b=btn, c=color: b.configure(bg=c)
            )


    @staticmethod
    def _darken(hex_color: str) -> str:
        """Darken a hex color slightly for hover"""
        try:
            hex_color = hex_color.lstrip("#")
            r, g, b = (int(hex_color[i:i+2], 16)
                       for i in (0, 2, 4))
            r = max(0, r - 30)
            g = max(0, g - 30)
            b = max(0, b - 30)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color


    # ----------------------------------------------------------
    # LOAD DASHBOARD DATA
    # ----------------------------------------------------------
    def _load_dashboard_data(self):
        """Fetch all data from DB and update UI"""
        s_date, e_date = self._get_active_date_range()
        if s_date and e_date:
            subtitle = f"Showing data from {format_date_display(s_date)} to {format_date_display(e_date)}"
        elif s_date:
            subtitle = f"Showing data from {format_date_display(s_date)} onwards"
        elif e_date:
            subtitle = f"Showing data up to {format_date_display(e_date)}"
        else:
            subtitle = "Showing all time data"
        self.subtitle_label.configure(text=subtitle)

        # Load each section
        self._load_stat_cards(s_date, e_date)
        self._load_recent_bills(s_date, e_date)
        self._load_year_overview(self.view_year.get())


    # ----------------------------------------------------------
    # STAT CARDS DATA
    # ----------------------------------------------------------
    def _load_stat_cards(self, s_date=None, e_date=None):
        """Fetch stats for the date range and update cards"""
        conds_p = []
        conds_s = []
        params_p = []
        params_s = []

        if s_date:
            conds_p.append("pb.bill_date >= ?")
            params_p.append(format_date_iso(s_date))
            conds_s.append("sb.bill_date >= ?")
            params_s.append(format_date_iso(s_date))
        if e_date:
            conds_p.append("pb.bill_date <= ?")
            params_p.append(format_date_iso(e_date))
            conds_s.append("sb.bill_date <= ?")
            params_s.append(format_date_iso(e_date))

        where_p = f"WHERE {' AND '.join(conds_p)}" if conds_p else ""
        where_s = f"WHERE {' AND '.join(conds_s)}" if conds_s else ""

        # ---- Purchase totals in period ----
        p = db.query_one(f"""
            SELECT
                COUNT(*)                      AS bill_count,
                COALESCE(SUM(subtotal),    0) AS total_taxable,
                COALESCE(SUM(total_gst),   0) AS total_gst,
                COALESCE(SUM(grand_total), 0) AS grand_total
            FROM purchase_bills pb
            {where_p}
        """, tuple(params_p))

        # ---- Sales totals in period ----
        s = db.query_one(f"""
            SELECT
                COUNT(*)                      AS bill_count,
                COALESCE(SUM(subtotal),    0) AS total_taxable,
                COALESCE(SUM(total_cgst),  0) AS total_cgst,
                COALESCE(SUM(total_sgst),  0) AS total_sgst,
                COALESCE(SUM(grand_total), 0) AS grand_total
            FROM sales_bills sb
            {where_s}
        """, tuple(params_s))

        # ---- Active Stock on Hand (Carried Forward Unsold Inventory) ----
        stock_params = []
        stock_cond = ["pi.remaining_qty > 0.0001"]
        if e_date:
            stock_cond.append("pb.bill_date <= ?")
            stock_params.append(format_date_iso(e_date))

        stock = db.query_one(f"""
            SELECT
                COALESCE(SUM(pi.remaining_qty * pi.purchase_rate), 0) AS stock_val,
                COALESCE(SUM(pi.remaining_qty), 0) AS stock_units
            FROM purchase_items pi
            JOIN purchase_bills pb ON pi.purchase_bill_id = pb.id
            WHERE {' AND '.join(stock_cond)}
        """, tuple(stock_params))

        # ---- Cost of Goods Sold (COGS) for Period Sales ----
        cogs_data = db.query_one(f"""
            SELECT
                COALESCE(SUM(si.quantity * pi.purchase_rate), 0) AS cogs,
                COALESCE(SUM(si.quantity * si.selling_rate), 0) AS sales_taxable
            FROM sales_items si
            JOIN sales_bills sb ON si.sales_bill_id = sb.id
            LEFT JOIN purchase_items pi ON si.purchase_item_id = pi.id
            {where_s}
        """, tuple(params_s))

        purchase_total   = p.get("grand_total", 0)
        purchase_taxable = p.get("total_taxable", 0)
        purchase_gst     = p.get("total_gst", 0)

        sales_total      = s.get("grand_total", 0)
        sales_taxable    = s.get("total_taxable", 0)
        output_cgst      = s.get("total_cgst", 0)
        output_sgst      = s.get("total_sgst", 0)
        output_gst       = output_cgst + output_sgst
        p_count = p.get("bill_count", 0)
        s_count = s.get("bill_count", 0)
        active_val = stock.get("stock_val", 0)
        active_units = stock.get("stock_units", 0)

        cogs = cogs_data.get("cogs", 0)
        if s_count == 0 or sales_taxable <= 0:
            profit = 0.0
            profit_sub = "No sales in period"
        elif cogs > 0:
            profit = sales_taxable - cogs
            margin_pct = (profit / cogs * 100) if cogs > 0 else 0
            profit_sub = f"{margin_pct:.1f}% margin on sold goods"
        else:
            profit = sales_taxable - purchase_taxable
            profit_sub = "On taxable value"

        gst_payable = max(0.0, output_gst - purchase_gst)

        # Check negative stock
        neg_item = db.query_one("SELECT COUNT(*) AS cnt FROM purchase_items WHERE remaining_qty < -0.001")
        has_negative = (neg_item.get("cnt", 0) > 0)

        if has_negative:
            tally_text = "❌ Stock Error"
            tally_sub = "Negative stock detected"
            tally_color = COLORS["tally_bad"]
        elif p_count == 0 and s_count == 0:
            tally_text = "No period data"
            tally_sub = "No transactions in range"
            tally_color = "#9e9e9e"
        elif active_units <= 0.001 and s_count > 0:
            tally_text = "✅ 100% Sold"
            tally_sub = "All stock accounted for"
            tally_color = COLORS["tally_ok"]
        else:
            tally_text = "✅ Reconciled"
            tally_sub = f"{active_units:.1f} units in stock"
            tally_color = COLORS["tally_ok"]

        updates = {
            "purchase_total": (
                f"₹{purchase_total:,.2f}",
                f"{p_count} bills  |  GST: ₹{purchase_gst:,.2f}"
            ),
            "sales_total": (
                f"₹{sales_total:,.2f}",
                f"{s_count} bills  |  GST: ₹{output_gst:,.2f}"
            ),
            "stock_total": (
                f"₹{active_val:,.2f}",
                f"{active_units:.1f} units carried forward"
            ),
            "profit_total": (
                f"₹{profit:,.2f}",
                profit_sub
            ),
            "gst_payable": (
                f"₹{gst_payable:,.2f}",
                "Output GST - Input GST"
            ),
            "tally_status": (
                tally_text,
                tally_sub
            ),
        }

        for key, (value, sub) in updates.items():
            if key in self.stat_labels:
                val_lbl, sub_lbl = self.stat_labels[key]
                val_lbl.configure(text=value)
                sub_lbl.configure(text=sub)

        # Color tally card based on status
        if "tally_status" in self.stat_labels:
            val_lbl, sub_lbl = self.stat_labels["tally_status"]
            parent_frame = val_lbl.master
            parent_frame.configure(bg=tally_color)
            for child in parent_frame.winfo_children():
                try:
                    child.configure(bg=tally_color)
                    for subchild in child.winfo_children():
                        try:
                            subchild.configure(bg=tally_color)
                        except Exception:
                            pass
                except Exception:
                    pass


    # ----------------------------------------------------------
    # RECENT BILLS TABLE DATA
    # ----------------------------------------------------------
    def _load_recent_bills(self, s_date=None, e_date=None):
        """Fetch last 10 sales bills in the date range and display in table"""
        for widget in self.bills_table_frame.winfo_children():
            widget.destroy()

        conds = []
        params = []
        if s_date:
            conds.append("sb.bill_date >= ?")
            params.append(format_date_iso(s_date))
        if e_date:
            conds.append("sb.bill_date <= ?")
            params.append(format_date_iso(e_date))
        where = f"WHERE {' AND '.join(conds)}" if conds else ""

        bills = db.query(f"""
            SELECT
                sb.bill_number,
                sb.customer_name,
                sb.bill_date,
                sb.grand_total,
                sb.bill_type,
                sb.is_printed
            FROM sales_bills sb
            {where}
            ORDER BY sb.bill_date DESC, sb.id DESC
            LIMIT 10
        """, tuple(params))

        if not bills:
            range_desc = f"from {format_date_display(s_date)} to {format_date_display(e_date)}" if s_date and e_date else "for this period"
            tk.Label(
                self.bills_table_frame,
                text=f"No sales bills found {range_desc}.\n"
                     "Go to 📤 Sales Bills to generate bills.",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"],
                justify="center"
            ).pack(pady=30)
            return

        # Build rows
        for i, bill in enumerate(bills):
            row_bg = "#f9f9f9" if i % 2 == 0 else "white"
            row = tk.Frame(
                self.bills_table_frame,
                bg=row_bg
            )
            row.pack(fill="x")

            # Bill number
            tk.Label(
                row,
                text=bill["bill_number"],
                font=FONTS["small"],
                bg=row_bg,
                fg=COLORS["primary"],
                width=12,
                anchor="w",
                padx=5,
                pady=5
            ).pack(side="left")

            # Customer name
            tk.Label(
                row,
                text=bill["customer_name"],
                font=FONTS["small"],
                bg=row_bg,
                fg=COLORS["text_dark"],
                width=18,
                anchor="w",
                padx=5
            ).pack(side="left")

            # Date
            try:
                d = datetime.strptime(
                    bill["bill_date"], "%Y-%m-%d"
                )
                date_str = d.strftime("%d %b")
            except Exception:
                date_str = bill["bill_date"]

            tk.Label(
                row,
                text=date_str,
                font=FONTS["small"],
                bg=row_bg,
                fg=COLORS["text_muted"],
                width=12,
                anchor="w",
                padx=5
            ).pack(side="left")

            # Amount
            tk.Label(
                row,
                text=f"₹{bill['grand_total']:,.0f}",
                font=FONTS["label_bold"],
                bg=row_bg,
                fg=COLORS["success"],
                width=12,
                anchor="w",
                padx=5
            ).pack(side="left")

            # Printed status
            status = "🖨️" if bill["is_printed"] else "📄"
            tk.Label(
                row,
                text=status,
                font=FONTS["small"],
                bg=row_bg,
                fg=COLORS["text_muted"],
                width=8,
                anchor="w",
                padx=5
            ).pack(side="left")

        # "Show more" if there are more than 10
        total_count = db.query_one(f"""
            SELECT COUNT(*) AS cnt
            FROM sales_bills sb
            {where}
        """, tuple(params))

        total = total_count.get("cnt", 0)
        if total > 10:
            tk.Label(
                self.bills_table_frame,
                text=f"Showing 10 of {total} bills. "
                     f"Go to Sales Bills for full list.",
                font=FONTS["small"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(pady=8)

        total = total_count.get("cnt", 0)
        if total > 10:
            tk.Label(
                self.bills_table_frame,
                text=f"Showing 10 of {total} bills. "
                     f"Go to Sales Bills for full list.",
                font=FONTS["small"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(pady=8)


    # ----------------------------------------------------------
    # YEAR OVERVIEW GRID
    # ----------------------------------------------------------
    def _load_year_overview(self, year: int):
        """Show 12-month grid with data indicators"""

        # Clear existing
        for widget in self.year_overview_frame.winfo_children():
            widget.destroy()

        # Fetch monthly data for whole year
        monthly_data = db.query("""
            SELECT
                bill_month,
                COUNT(*)            AS p_count,
                SUM(grand_total)    AS p_total
            FROM purchase_bills
            WHERE bill_year=?
            GROUP BY bill_month
        """, (year,))

        monthly_sales = db.query("""
            SELECT
                bill_month,
                COUNT(*)            AS s_count,
                SUM(grand_total)    AS s_total
            FROM sales_bills
            WHERE bill_year=?
            GROUP BY bill_month
        """, (year,))

        # Index by month
        p_data = {row["bill_month"]: row for row in monthly_data}
        s_data = {row["bill_month"]: row for row in monthly_sales}

        # Year title
        tk.Label(
            self.year_overview_frame,
            text=f"📅 {year} — All Months",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 8))

        # Grid: 3 columns × 4 rows
        grid = tk.Frame(
            self.year_overview_frame,
            bg=COLORS["bg_card"]
        )
        grid.pack(fill="both")

        today = date.today()

        for month_num in range(1, 13):
            row_idx = (month_num - 1) // 3
            col_idx = (month_num - 1) % 3

            # Data for this month
            p = p_data.get(month_num, {})
            s = s_data.get(month_num, {})

            p_count = p.get("p_count", 0)
            s_count = s.get("s_count", 0)
            p_total = p.get("p_total", 0) or 0
            s_total = s.get("s_total", 0) or 0

            # Card color based on data status
            is_current = (
                month_num == today.month and
                year == today.year
            )

            if p_count > 0 and s_count > 0:
                card_bg = COLORS["success_light"]
                border_c = COLORS["success"]
            elif p_count > 0 and s_count == 0:
                card_bg = COLORS["warning_light"]
                border_c = COLORS["warning"]
            elif is_current:
                card_bg = "#e3f2fd"
                border_c = COLORS["primary_light"]
            else:
                card_bg = "#f5f5f5"
                border_c = COLORS["border"]

            # Month cell
            cell_outer = tk.Frame(
                grid,
                bg=border_c,
                padx=1,
                pady=1
            )
            cell_outer.grid(
                row=row_idx,
                column=col_idx,
                padx=4,
                pady=4,
                sticky="nsew"
            )

            cell = tk.Frame(
                cell_outer,
                bg=card_bg,
                padx=8,
                pady=6,
                cursor="hand2"
            )
            cell.pack(fill="both", expand=True)

            # Month name
            month_lbl = tk.Label(
                cell,
                text=MONTH_NAMES[month_num][:3].upper() +
                     (" ◀" if is_current else ""),
                font=FONTS["label_bold"],
                bg=card_bg,
                fg=COLORS["primary"] if is_current
                   else COLORS["text_dark"]
            )
            month_lbl.pack(anchor="w")

            # Data lines
            if p_count > 0:
                tk.Label(
                    cell,
                    text=f"📥 {p_count} | ₹{p_total:,.0f}",
                    font=FONTS["smaller"],
                    bg=card_bg,
                    fg=COLORS["primary_light"]
                ).pack(anchor="w")
            else:
                tk.Label(
                    cell,
                    text="📥 No purchases",
                    font=FONTS["smaller"],
                    bg=card_bg,
                    fg=COLORS["text_muted"]
                ).pack(anchor="w")

            if s_count > 0:
                tk.Label(
                    cell,
                    text=f"📤 {s_count} | ₹{s_total:,.0f}",
                    font=FONTS["smaller"],
                    bg=card_bg,
                    fg=COLORS["success"]
                ).pack(anchor="w")
            else:
                tk.Label(
                    cell,
                    text="📤 No sales",
                    font=FONTS["smaller"],
                    bg=card_bg,
                    fg=COLORS["text_muted"]
                ).pack(anchor="w")

            # Click to jump to that month
            def on_click(e, m=month_num, y=year):
                self.view_month.set(m)
                self.view_year.set(y)
                self.month_cb.set(MONTH_NAMES[m])
                self.year_cb.set(str(y))
                self._load_dashboard_data()

            cell.bind("<Button-1>", on_click)
            month_lbl.bind("<Button-1>", on_click)

        # Make columns equal width
        for col in range(3):
            grid.columnconfigure(col, weight=1)

        # Legend
        legend_frame = tk.Frame(
            self.year_overview_frame,
            bg=COLORS["bg_card"]
        )
        legend_frame.pack(fill="x", pady=(10, 0))

        legends = [
            (COLORS["success_light"], COLORS["success"],
             "Both purchase & sales done"),
            (COLORS["warning_light"], COLORS["warning"],
             "Purchase added, sales pending"),
            ("#e3f2fd",               COLORS["primary_light"],
             "Current month"),
            ("#f5f5f5",               COLORS["border"],
             "No data"),
        ]

        for bg, border, label in legends:
            item = tk.Frame(legend_frame, bg=COLORS["bg_card"])
            item.pack(side="left", padx=(0, 15))

            color_box = tk.Frame(
                item,
                bg=border,
                width=12,
                height=12
            )
            color_box.pack(side="left", padx=(0, 4))

            tk.Label(
                item,
                text=label,
                font=FONTS["smaller"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(side="left")