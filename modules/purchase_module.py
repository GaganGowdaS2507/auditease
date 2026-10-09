# modules/purchase_module.py
# ============================================================
# PURCHASE MODULE — COMPLETE FIXED VERSION
# Fixes:
# 1. CSV parser handles your bill format
#    (Sl No, Description, HSN/SAC, Quantity,
#     Unit, Rate, Discount%, GST%, Amount)
# 2. GST rate is now EDITABLE (not just dropdown)
#    Supports any GST% like 6%, 3%, etc.
# 3. Unit field accepts typed values (Mtrs, Nos, etc.)
# 4. Save button always visible
# 5. Discount % handled from CSV
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import json
import shutil
import os
import csv
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

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
}

MONTH_NAMES = [
    "", "January", "February", "March", "April",
    "May", "June", "July", "August", "September",
    "October", "November", "December"
]

# GST rates — common ones + allow custom entry
GST_RATES_COMMON = [
    "0", "3", "5", "6", "12", "18", "28"
]

# Units — common + allow custom typing
UNITS_COMMON = [
    "piece", "Nos", "kg", "meter", "Mtrs",
    "liter", "bag", "box", "bundle", "roll",
    "sheet", "pair", "set", "ton"
]


# ============================================================
# HELPERS
# ============================================================
def load_settings() -> dict:
    """Load settings safely"""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {
            "billing": {"tax_scheme": "regular"},
            "storage": {
                "bills_root_folder": str(
                    BASE_DIR / "bills"
                )
            }
        }


def round2(value) -> float:
    """Round to 2 decimal places"""
    return float(
        Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
    )


def safe_float(value, default=0.0) -> float:
    """Convert to float safely"""
    try:
        if value is None:
            return default
        cleaned = str(value).replace(
            ",", ""
        ).strip()
        return float(cleaned) if cleaned else default
    except Exception:
        return default


class DBHelper:
    def __init__(self):
        self.db_path = DB_PATH

    def query(self, sql, params=()):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
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
            cur = conn.cursor()
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
# FOLDER HELPER
# ============================================================
def get_month_folder(
    year: int, month: int,
    category: str, settings: dict
) -> Path:
    """Returns and creates organized folder path"""
    root = Path(
        settings["storage"]["bills_root_folder"]
    )
    month_folder = (
        root / str(year) /
        f"{month:02d}_{MONTH_NAMES[month]}"
    )
    target = month_folder / category
    target.mkdir(parents=True, exist_ok=True)
    return target


# ============================================================
# CSV PARSER — Handles your bill format
# ============================================================
def parse_csv_bill(file_path: str) -> list:
    """
    Parse dealer CSV bill into list of item dicts.

    Rate is NOT read from the Rate column (which is pre-discount).
    Instead: rate = amount / (quantity × (1 + gst/100))
    This gives the effective post-discount per-unit rate.
    """
    items = []

    with open(file_path, "r",
              encoding="utf-8-sig") as f:
        content = f.read()

    # Try to detect delimiter
    delimiter = ","
    if ";" in content and "," not in content:
        delimiter = ";"

    lines = content.splitlines()

    # Find the header row
    header_row_idx = -1
    headers        = []

    for i, line in enumerate(lines):
        if not line.strip():
            continue
        cols = [
            c.strip().strip('"').lower()
            for c in line.split(delimiter)
        ]
        # Check if this looks like a header
        header_keywords = [
            "description", "item", "name",
            "hsn", "sac", "quantity", "qty",
            "rate", "price", "gst", "amount"
        ]
        matches = sum(
            1 for kw in header_keywords
            if any(kw in col for col in cols)
        )
        if matches >= 2:
            header_row_idx = i
            headers = cols
            break

    if header_row_idx == -1:
        raise ValueError(
            "Could not find header row in CSV.\n"
            "Expected columns like: Description, "
            "HSN/SAC, Quantity, Unit, Rate, GST%"
        )

    # Map column names to indices
    col_map = {}
    for idx, col in enumerate(headers):
        # Item name / description
        if any(kw in col for kw in [
            "description", "item_name",
            "item name", "name", "particulars"
        ]):
            col_map["item_name"] = idx

        # HSN code
        elif any(kw in col for kw in [
            "hsn", "sac", "hsn/sac",
            "hsn_code", "hsncode"
        ]):
            col_map["hsn_code"] = idx

        # Quantity
        elif any(kw in col for kw in [
            "quantity", "qty"
        ]):
            col_map["quantity"] = idx

        # Unit
        elif col in ["unit", "uom", "u.o.m"]:
            col_map["unit"] = idx

        # Rate / Price
        elif any(kw in col for kw in [
            "rate", "price", "purchase_rate",
            "unit price", "unit rate"
        ]):
            # Avoid matching "gst rate" here
            if "gst" not in col:
                col_map["rate"] = idx

        # Discount
        elif any(kw in col for kw in [
            "discount", "disc", "disc%",
            "discount %", "discount%"
        ]):
            col_map["discount"] = idx

        # GST Rate
        elif any(kw in col for kw in [
            "gst %", "gst%", "gst_rate",
            "tax %", "tax%", "igst%",
            "cgst%", "sgst%"
        ]):
            col_map["gst_rate"] = idx

        # Amount / Total
        elif any(kw in col for kw in [
            "amount", "total", "net amount",
            "taxable", "value"
        ]):
            col_map["amount"] = idx

    # Parse data rows
    for line in lines[header_row_idx + 1:]:
        if not line.strip():
            continue

        cols = [
            c.strip().strip('"')
            for c in line.split(delimiter)
        ]

        if len(cols) < 3:
            continue

        # Get item name
        item_name = ""
        if "item_name" in col_map:
            item_name = cols[
                col_map["item_name"]
            ].strip()

        if not item_name:
            continue

        # Skip summary/footer rows
        skip_keywords = [
            "subtotal", "sub total", "total",
            "grand total", "cgst", "sgst", "igst",
            "tax", "discount", "freight",
            "round off", "net payable",
            "amount payable", "balance"
        ]
        if any(
            kw in item_name.lower()
            for kw in skip_keywords
        ):
            continue

        # Skip if item name is just a number
        if item_name.isdigit():
            continue

        # Get HSN code
        hsn_code = "-"
        if "hsn_code" in col_map:
            raw_hsn = cols[
                col_map["hsn_code"]
            ].strip()
            # HSN codes are typically 4-8 digits
            if raw_hsn and raw_hsn.replace(
                ".", ""
            ).isdigit():
                hsn_code = raw_hsn
            elif raw_hsn:
                hsn_code = raw_hsn

        # REPLACE lines ~385–434 (the block from "# Get rate" to end of item append)

        # Get quantity
        quantity = 0.0
        if "quantity" in col_map:
            quantity = safe_float(cols[col_map["quantity"]], 0)

        if quantity <= 0:
            continue

        # Get unit
        unit = "piece"
        if "unit" in col_map:
            raw_unit = cols[col_map["unit"]].strip()
            if raw_unit:
                unit = raw_unit

        # ── CHANGED: Skip reading "Rate" column entirely ──
        # Get amount (the final printed total after all discounts)
        amount = 0.0
        if "amount" in col_map:
            amount = safe_float(cols[col_map["amount"]], 0)

        # Get GST rate from bill (stored for reference)
        gst_rate = 18.0
        if "gst_rate" in col_map:
            gst_rate = safe_float(cols[col_map["gst_rate"]], 18)

        # ── COMPOSITION SCHEME: rate = amount / quantity ──
        # Shop is on COMPOSITION SCHEME — no GST is collected on sales.
        # The purchase "amount" is the final total after all discounts.
        # Simply divide by quantity to get effective per-unit purchase rate.
        # Formula: rate = amount / quantity  (NO GST stripping)
        rate = 0.0
        if amount > 0 and quantity > 0:
            rate = round2(amount / quantity)

        if rate <= 0:
            continue  # skip rows where we can't derive a valid rate

        items.append({
            "item_name":    item_name,
            "hsn_code":     hsn_code,
            "quantity":     quantity,
            "unit":         unit,
            "rate":         rate,           # derived: amount / qty (post-discount, no GST strip)
            "gst_rate":     gst_rate,
            "discount_pct": 0.0,            # discount already baked into amount
            "amount":       amount,
        })

# ============================================================
# ITEM ROW — Single editable row
# ============================================================
class ItemRow:
    """
    One item row in the purchase entry form.
    FIXED: GST rate is now editable Entry (not dropdown)
    FIXED: Unit is editable Combobox (can type custom)
    """

    def __init__(
        self, parent, row_num: int,
        on_change_callback,
        on_delete_callback,
        hsn_data: dict
    ):
        self.parent    = parent
        self.row_num   = row_num
        self.on_change = on_change_callback
        self.on_delete = on_delete_callback
        self.hsn_data  = hsn_data

        # Variables
        self.var_name     = tk.StringVar()
        self.var_hsn      = tk.StringVar(value="-")
        self.var_qty      = tk.StringVar(value="1")
        self.var_unit     = tk.StringVar(value="piece")
        self.var_rate     = tk.StringVar(value="0")
        self.var_gst_rate = tk.StringVar(value="18")
        self.var_gst_amt  = tk.StringVar(value="0.00")
        self.var_total    = tk.StringVar(value="0.00")

        self.frame = tk.Frame(parent, bg=COLORS["bg_card"])
        self._build()
        self._bind_calculations()

    def _build(self):
        """Build row UI"""
        bg = (
            COLORS["row_even"]
            if self.row_num % 2 == 0
            else COLORS["row_odd"]
        )
        self.frame.configure(bg=bg)

        # Row number label
        tk.Label(
            self.frame,
            text=str(self.row_num),
            font=FONTS["table"],
            bg=bg,
            fg=COLORS["text_muted"],
            width=3
        ).grid(row=0, column=0, padx=(5, 2), pady=3)

        # ---- Item Name (wide entry) ----
        self.name_entry = tk.Entry(
            self.frame,
            textvariable=self.var_name,
            font=FONTS["table"],
            width=25,
            relief="solid",
            bd=1,
            bg="white"
        )
        self.name_entry.grid(
            row=0, column=1, padx=3, pady=3
        )

        # ---- HSN Code (editable) ----
        self.hsn_entry = tk.Entry(
            self.frame,
            textvariable=self.var_hsn,
            font=FONTS["table"],
            width=10,
            relief="solid",
            bd=1,
            bg="white"
        )
        self.hsn_entry.grid(
            row=0, column=2, padx=3, pady=3
        )

        # ---- Quantity ----
        self.qty_entry = tk.Entry(
            self.frame,
            textvariable=self.var_qty,
            font=FONTS["table"],
            width=8,
            relief="solid",
            bd=1,
            bg="white"
        )
        self.qty_entry.grid(
            row=0, column=3, padx=3, pady=3
        )

        # ---- Unit — EDITABLE Combobox ----
        # Father can type "Mtrs", "Nos" etc.
        self.unit_cb = ttk.Combobox(
            self.frame,
            textvariable=self.var_unit,
            values=UNITS_COMMON,
            font=FONTS["table"],
            width=7,
            # NOT readonly — allows typing
        )
        self.unit_cb.grid(
            row=0, column=4, padx=3, pady=3
        )

        # ---- Rate (purchase rate) ----
        self.rate_entry = tk.Entry(
            self.frame,
            textvariable=self.var_rate,
            font=FONTS["table"],
            width=10,
            relief="solid",
            bd=1,
            bg="white"
        )
        self.rate_entry.grid(
            row=0, column=5, padx=3, pady=3
        )

        # ---- GST Rate — EDITABLE Entry ----
        # FIXED: Changed from readonly Combobox
        # to editable Entry so 6%, 3% etc work
        self.gst_entry = tk.Entry(
            self.frame,
            textvariable=self.var_gst_rate,
            font=FONTS["table"],
            width=6,
            relief="solid",
            bd=1,
            bg="#fff9c4"  # light yellow to stand out
        )
        self.gst_entry.grid(
            row=0, column=6, padx=3, pady=3
        )

        # Small "%" label next to GST
        tk.Label(
            self.frame,
            text="%",
            font=FONTS["small"],
            bg=bg,
            fg=COLORS["text_muted"]
        ).grid(row=0, column=7, padx=(0, 3))

        # ---- GST Amount (read-only, calculated) ----
        tk.Entry(
            self.frame,
            textvariable=self.var_gst_amt,
            font=FONTS["table"],
            width=10,
            relief="solid",
            bd=1,
            bg="#f0f0f0",
            state="readonly"
        ).grid(row=0, column=8, padx=3, pady=3)

        # ---- Total (read-only, calculated) ----
        tk.Entry(
            self.frame,
            textvariable=self.var_total,
            font=FONTS["table_bold"],
            width=12,
            relief="solid",
            bd=1,
            bg="#e8f5e9",
            fg=COLORS["success"],
            state="readonly"
        ).grid(row=0, column=9, padx=3, pady=3)

        # ---- Delete button ----
        tk.Button(
            self.frame,
            text="✕",
            font=FONTS["small"],
            bg=COLORS["danger"],
            fg="white",
            relief="flat",
            padx=5,
            pady=2,
            cursor="hand2",
            command=lambda: self.on_delete(self)
        ).grid(row=0, column=10, padx=5, pady=3)

    def _bind_calculations(self):
        """Bind auto-calculation on field changes"""
        for var in [
            self.var_qty,
            self.var_rate,
            self.var_gst_rate
        ]:
            var.trace_add(
                "write",
                lambda *a: self._calculate()
            )

        self.var_name.trace_add(
            "write",
            lambda *a: self._try_autofill_hsn()
        )

    def _calculate(self):
        """
        Calculate GST amount and total.
        Formula: taxable = qty × rate
                 gst_amt = taxable × gst% / 100
                 total   = taxable + gst_amt
        """
        try:
            qty      = safe_float(self.var_qty.get())
            rate     = safe_float(self.var_rate.get())
            gst_rate = safe_float(
                self.var_gst_rate.get(), 18
            )

            if qty <= 0 or rate <= 0:
                self.var_gst_amt.set("0.00")
                self.var_total.set("0.00")
                self.on_change()
                return

            taxable = qty * rate
            gst_amt = round2(taxable * gst_rate / 100)
            total   = round2(taxable + gst_amt)

            self.var_gst_amt.set(f"{gst_amt:.2f}")
            self.var_total.set(f"{total:.2f}")

            self.on_change()
        except Exception:
            pass

    def _try_autofill_hsn(self):
        """Auto-fill HSN from items master database"""
        name = self.var_name.get().strip().lower()
        if len(name) < 3:
            return

        row = db.query_one("""
            SELECT hsn_code, gst_rate, unit
            FROM items_master
            WHERE item_name_lower LIKE ?
            LIMIT 1
        """, (f"%{name}%",))

        if row:
            if row.get("hsn_code") and \
                    row["hsn_code"] != "-":
                self.var_hsn.set(row["hsn_code"])
            if row.get("gst_rate"):
                self.var_gst_rate.set(
                    str(row["gst_rate"])
                )
            if row.get("unit"):
                self.var_unit.set(row["unit"])
            self._calculate()

    def get_data(self) -> dict:
        """Return current row data as dict"""
        return {
            "item_name":  self.var_name.get().strip(),
            "hsn_code":   self.var_hsn.get().strip()
                          or "-",
            "quantity":   safe_float(self.var_qty.get()),
            "unit":       self.var_unit.get().strip()
                          or "piece",
            "rate":       safe_float(self.var_rate.get()),
            "gst_rate":   safe_float(
                self.var_gst_rate.get(), 18
            ),
            "gst_amount": safe_float(
                self.var_gst_amt.get()
            ),
            "total":      safe_float(
                self.var_total.get()
            ),
        }

    def set_data(self, data: dict):
        """Load data into row fields"""
        self.var_name.set(
            data.get("item_name", "")
        )
        self.var_hsn.set(
            data.get("hsn_code", "-")
        )
        self.var_qty.set(
            str(data.get("quantity", 1))
        )
        self.var_unit.set(
            data.get("unit", "piece")
        )
        self.var_rate.set(
            str(round2(data.get("rate", 0)))
        )
        # Set GST rate as-is (supports 6%, 3%, etc.)
        gst = data.get("gst_rate", 18)
        self.var_gst_rate.set(str(gst))
        self._calculate()

    def is_valid(self) -> tuple:
        """Validate row. Returns (ok, error_msg)"""
        data = self.get_data()
        if not data["item_name"]:
            return (
                False,
                f"Row {self.row_num}: "
                f"Item name is required"
            )
        if data["quantity"] <= 0:
            return (
                False,
                f"Row {self.row_num}: "
                f"Quantity must be > 0"
            )
        if data["rate"] <= 0:
            return (
                False,
                f"Row {self.row_num}: "
                f"Rate must be > 0"
            )
        return True, ""

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def destroy(self):
        self.frame.destroy()


# ============================================================
# TABLE HEADER — Updated for new column layout
# ============================================================
def build_items_table_header(parent):
    """
    Build column headers matching ItemRow columns.
    """
    header = tk.Frame(parent, bg=COLORS["header_bg"])
    header.pack(fill="x")

    columns = [
        ("#",          3),
        ("Item Name", 25),
        ("HSN Code",  10),
        ("Qty",        8),
        ("Unit",       7),
        ("Rate (₹)",  10),
        ("GST%",       6),
        ("",           2),  # % label spacer
        ("GST Amt",   10),
        ("Total (₹)", 12),
        ("",           5),  # delete spacer
    ]

    for col_name, width in columns:
        tk.Label(
            header,
            text=col_name,
            font=FONTS["table_bold"],
            bg=COLORS["header_bg"],
            fg="white",
            width=width,
            anchor="w",
            padx=5,
            pady=6
        ).pack(side="left")

    return header


# ============================================================
# ADD/EDIT PURCHASE BILL DIALOG
# ============================================================
class PurchaseBillDialog(tk.Toplevel):
    """
    Modal dialog for adding or editing a purchase bill.

    FIXED:
    - Save button always visible at bottom
    - CSV import uses smart parser
    - GST % is editable
    - Unit is editable
    """

    def __init__(
        self, parent, app,
        edit_bill_id: int = None,
        on_save_callback=None
    ):
        super().__init__(parent)
        self.app          = app
        self.edit_bill_id = edit_bill_id
        self.on_save      = on_save_callback
        self.settings     = load_settings()
        self.item_rows    = []
        self.hsn_data     = self._load_hsn_data()
        self.uploaded_file_path = None

        title = (
            "Edit Purchase Bill"
            if edit_bill_id
            else "Add Purchase Bill"
        )
        self.title(title)
        self.geometry("1150x800")
        self.minsize(1000, 700)
        self.resizable(True, True)
        self.configure(bg=COLORS["bg_main"])
        self.grab_set()

        # Center
        self.update_idletasks()
        pw = parent.winfo_rootx()
        py = parent.winfo_rooty()
        self.geometry(f"+{pw+30}+{py+20}")

        self._build_ui()

        if edit_bill_id:
            self._load_bill_for_edit(edit_bill_id)
        else:
            self._add_item_row()

    def _load_hsn_data(self) -> dict:
        try:
            hsn_path = BASE_DIR / "data" / "hsn_master.json"
            with open(hsn_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    # ----------------------------------------------------------
    # BUILD UI
    # ----------------------------------------------------------
    def _build_ui(self):
        """
        Layout (top to bottom):
        1. Header bar (title)
        2. Bill details (dealer, date, bill no)
        3. Upload section (image/pdf/csv buttons)
        4. Items table (scrollable, expandable)
        5. Footer (totals + SAVE button) ← always visible
        """

        # 1. Header
        self._build_header()

        # 2. Bill details
        self._build_bill_details()

        # 3. Upload section
        self._build_upload_section()

        # 4. Items table (fill remaining space)
        self._build_items_section()

        # 5. Footer with totals + save button
        #    Built LAST so it stays at bottom
        self._build_footer()

    def _build_header(self):
        hdr = tk.Frame(
            self, bg=COLORS["primary"], pady=10
        )
        hdr.pack(fill="x")

        tk.Label(
            hdr,
            text=(
                "✏️  Edit Purchase Bill"
                if self.edit_bill_id
                else "📥  Add New Purchase Bill"
            ),
            font=FONTS["heading"],
            bg=COLORS["primary"],
            fg="white"
        ).pack(side="left", padx=20)

        # Quick save button in header too
        tk.Button(
            hdr,
            text="💾 Save Bill",
            font=FONTS["button"],
            bg=COLORS["accent"],
            fg="white",
            relief="flat",
            padx=15,
            pady=5,
            cursor="hand2",
            command=self._save_bill
        ).pack(side="right", padx=20)

    # ----------------------------------------------------------
    # BILL DETAILS
    # ----------------------------------------------------------
    def _build_bill_details(self):
        """Dealer, bill no, date, type, notes"""
        card = tk.Frame(
            self,
            bg=COLORS["bg_card"],
            padx=15,
            pady=10
        )
        card.pack(fill="x", padx=10, pady=(8, 4))

        # Row 1 — Dealer | Bill No | Date
        row1 = tk.Frame(card, bg=COLORS["bg_card"])
        row1.pack(fill="x", pady=4)

        # Dealer name
        tk.Label(
            row1,
            text="Dealer / Supplier *",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["primary"]
        ).pack(side="left", padx=(0, 5))

        self.var_dealer = tk.StringVar()
        tk.Entry(
            row1,
            textvariable=self.var_dealer,
            font=FONTS["body"],
            width=22,
            relief="solid",
            bd=1,
            bg="#fafafa"
        ).pack(side="left", padx=(0, 20))

        # Bill number
        tk.Label(
            row1,
            text="Bill Number *",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["primary"]
        ).pack(side="left", padx=(0, 5))

        self.var_bill_no = tk.StringVar()
        tk.Entry(
            row1,
            textvariable=self.var_bill_no,
            font=FONTS["body"],
            width=15,
            relief="solid",
            bd=1,
            bg="#fafafa"
        ).pack(side="left", padx=(0, 20))

        # Date
        tk.Label(
            row1,
            text="Bill Date *",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["primary"]
        ).pack(side="left", padx=(0, 5))

        self.var_bill_date = tk.StringVar(
            value=date.today().strftime("%d-%m-%Y")
        )
        tk.Entry(
            row1,
            textvariable=self.var_bill_date,
            font=FONTS["body"],
            width=13,
            relief="solid",
            bd=1,
            bg="#fafafa"
        ).pack(side="left", padx=(0, 5))

        tk.Label(
            row1,
            text="(DD-MM-YYYY)",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        ).pack(side="left")

        # Row 2 — Bill type | Notes
        row2 = tk.Frame(card, bg=COLORS["bg_card"])
        row2.pack(fill="x", pady=4)

        tk.Label(
            row2,
            text="Bill Type:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(0, 8))

        self.var_bill_type = tk.StringVar(
            value=self.settings.get(
                "billing", {}
            ).get("tax_scheme", "regular")
        )

        for val, lbl in [
            ("regular",     "Regular GST"),
            ("composition", "Composition Scheme"),
        ]:
            tk.Radiobutton(
                row2,
                text=lbl,
                variable=self.var_bill_type,
                value=val,
                font=FONTS["label"],
                bg=COLORS["bg_card"],
                activebackground=COLORS["bg_card"]
            ).pack(side="left", padx=(0, 15))

        tk.Label(
            row2,
            text="Notes:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(20, 5))

        self.var_notes = tk.StringVar()
        tk.Entry(
            row2,
            textvariable=self.var_notes,
            font=FONTS["body"],
            width=40,
            relief="solid",
            bd=1,
            bg="#fafafa"
        ).pack(side="left")

    # ----------------------------------------------------------
    # UPLOAD SECTION
    # ----------------------------------------------------------
    def _build_upload_section(self):
        """Upload buttons — Image / PDF / CSV / OCR"""
        upload_frame = tk.Frame(
            self,
            bg="#e3f2fd",
            padx=12,
            pady=8
        )
        upload_frame.pack(
            fill="x", padx=10, pady=(0, 4)
        )

        # Title + status on same row
        top_row = tk.Frame(upload_frame, bg="#e3f2fd")
        top_row.pack(fill="x", pady=(0, 6))

        tk.Label(
            top_row,
            text="📎 Upload Original Bill:",
            font=FONTS["label_bold"],
            bg="#e3f2fd",
            fg=COLORS["primary"]
        ).pack(side="left")

        self.upload_path_var = tk.StringVar(
            value="No file selected"
        )
        tk.Label(
            top_row,
            textvariable=self.upload_path_var,
            font=FONTS["small"],
            bg="#e3f2fd",
            fg=COLORS["text_muted"],
            wraplength=500
        ).pack(side="left", padx=15)

        # Buttons row
        btn_row = tk.Frame(upload_frame, bg="#e3f2fd")
        btn_row.pack(fill="x")

        buttons = [
            ("📷 Image\n(JPG/PNG)",
             COLORS["primary"],
             lambda: self._upload_file("image")),
            ("📄 PDF\n(Dealer PDF)",
             COLORS["primary_light"],
             lambda: self._upload_file("pdf")),
            ("📊 Import CSV\n(Auto-fill items)",
             COLORS["success"],
             self._import_from_csv),
            ("🔍 OCR Extract\n(Read from image)",
             COLORS["accent"],
             self._extract_ocr),
            ("⬇️ CSV Template\n(Download blank)",
             COLORS["text_muted"],
             self._download_csv_template),
        ]

        for label, color, cmd in buttons:
            tk.Button(
                btn_row,
                text=label,
                font=FONTS["small"],
                bg=color,
                fg="white",
                relief="flat",
                padx=12,
                pady=6,
                cursor="hand2",
                command=cmd
            ).pack(side="left", padx=(0, 6))

    def _upload_file(self, file_type: str):
        """Browse and select a file"""
        if file_type == "image":
            filetypes = [
                ("Images",
                 "*.jpg *.jpeg *.png *.bmp *.tiff"),
                ("All files", "*.*")
            ]
        else:
            filetypes = [
                ("PDF files", "*.pdf"),
                ("All files", "*.*")
            ]

        path = filedialog.askopenfilename(
            title=f"Select {file_type.upper()} Bill",
            filetypes=filetypes
        )
        if path:
            self.uploaded_file_path = path
            self.upload_path_var.set(
                f"✅ {Path(path).name}"
            )

    def _import_from_csv(self):
        """
        Import items from CSV — handles your bill format.
        Columns: Sl No, Description, HSN/SAC,
                 Quantity, Unit, Rate, Discount%, GST%, Amount
        """
        path = filedialog.askopenfilename(
            title="Select CSV Bill File",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )
        if not path:
            return

        try:
            self.uploaded_file_path = path

            # Use smart CSV parser
            items = parse_csv_bill(path)

            if not items:
                messagebox.showwarning(
                    "No Items Found",
                    "Could not find any items in the CSV.\n\n"
                    "Please check the file format."
                )
                return

            # Clear existing rows
            for row in self.item_rows:
                row.destroy()
            self.item_rows.clear()

            # Populate rows
            for item in items:
                row = self._add_item_row()
                row.set_data(item)

            self.upload_path_var.set(
                f"✅ {Path(path).name} "
                f"— {len(items)} items imported"
            )
            self._recalculate_totals()

            # # Show what was imported
            # discount_note = ""
            # items_with_disc = [
            #     i for i in items
            #     if i.get("discount_pct", 0) > 0
            # ]
            # if items_with_disc:
            #     discount_note = (
            #         f"\n\n⚠️  Discount applied on "
            #         f"{len(items_with_disc)} items.\n"
            #         f"Rate shown is after discount."
            #     )

            messagebox.showinfo(
                "✅ CSV Imported Successfully",
                f"Imported {len(items)} items.\n\n"
                f"Please review:\n"
                f"• Item names\n"
                f"• HSN codes\n"
                f"• GST rates (your bill uses 6%)\n"
                f"• Quantities and rates"
                + discount_note +
                "\n\nClick '💾 Save Bill' when done."
            )

        except Exception as e:
            messagebox.showerror(
                "CSV Import Error",
                f"Could not read CSV.\n\n"
                f"Error: {e}\n\n"
                f"Supported formats:\n"
                f"• Your dealer bill format\n"
                f"  (Description, HSN/SAC, Qty, "
                f"Unit, Rate, Discount%, GST%, Amount)\n"
                f"• Our template format\n"
                f"  (item_name, hsn_code, quantity, "
                f"unit, purchase_rate, gst_rate)"
            )

    def _extract_ocr(self):
        """OCR extraction from image/PDF"""
        if not self.uploaded_file_path:
            messagebox.showwarning(
                "No File",
                "Upload an image or PDF first,\n"
                "then click OCR Extract."
            )
            return

        try:
            from modules.ocr_module import OCRExtractor
            extractor = OCRExtractor()

            ext = Path(
                self.uploaded_file_path
            ).suffix.lower()

            if ext in [
                ".jpg", ".jpeg", ".png",
                ".bmp", ".tiff"
            ]:
                items = extractor.extract_from_image(
                    self.uploaded_file_path
                )
            elif ext == ".pdf":
                items = extractor.extract_from_pdf(
                    self.uploaded_file_path
                )
            else:
                messagebox.showerror(
                    "Unsupported",
                    "OCR works on images and PDFs only."
                )
                return

            if not items:
                messagebox.showwarning(
                    "OCR Result",
                    "OCR could not extract items.\n"
                    "Please enter items manually."
                )
                return

            for row in self.item_rows:
                row.destroy()
            self.item_rows.clear()

            for item in items:
                r = self._add_item_row()
                r.set_data(item)

            self._recalculate_totals()
            messagebox.showinfo(
                "OCR Complete",
                f"Extracted {len(items)} items.\n"
                "⚠️  Review all data carefully."
            )

        except ImportError:
            messagebox.showerror(
                "OCR Not Available",
                "Install: pip install pytesseract Pillow\n"
                "Also install Tesseract OCR engine."
            )
        except Exception as e:
            messagebox.showerror(
                "OCR Error", str(e)
            )

    def _download_csv_template(self):
        """Download CSV template for manual entry"""
        path = filedialog.asksaveasfilename(
            title="Save CSV Template",
            defaultextension=".csv",
            initialfile="purchase_bill_template.csv",
            filetypes=[("CSV files", "*.csv")]
        )
        if not path:
            return

        try:
            with open(
                path, "w", newline="",
                encoding="utf-8-sig"
            ) as f:
                writer = csv.writer(f)
                writer.writerow([
                    "item_name", "hsn_code",
                    "quantity", "unit",
                    "purchase_rate", "gst_rate"
                ])
                samples = [
                    ["GI Pipe 1 inch 6mtr",
                     "7306", "10", "piece",
                     "250.00", "18"],
                    ["PVC Pipe 2 inch",
                     "3917", "20", "Mtrs",
                     "85.00", "18"],
                    ["Ball Valve 1 inch",
                     "8481", "15", "Nos",
                     "120.00", "18"],
                    ["CPVC Pipe 1 inch",
                     "39172390", "250", "Mtrs",
                     "200.00", "6"],
                    ["CPVC Elbow 90°",
                     "39172390", "100", "Nos",
                     "37.55", "6"],
                ]
                writer.writerows(samples)
                for _ in range(20):
                    writer.writerow(
                        ["", "-", "", "piece", "", "18"]
                    )

            messagebox.showinfo(
                "Template Downloaded ✅",
                f"Template saved.\nOpen in Excel, "
                f"fill items, then import."
            )
            os.startfile(path)
        except Exception as e:
            messagebox.showerror(
                "Error", str(e)
            )

    # ----------------------------------------------------------
    # ITEMS TABLE
    # ----------------------------------------------------------
    def _build_items_section(self):
        """Scrollable items table with Add/Clear buttons"""

        # Section bar
        sec = tk.Frame(self, bg=COLORS["primary"])
        sec.pack(fill="x", padx=10, pady=(0, 0))

        tk.Label(
            sec,
            text="📦  Items in this Bill",
            font=FONTS["subheading"],
            bg=COLORS["primary"],
            fg="white"
        ).pack(side="left", padx=10, pady=6)

        # Buttons in section bar
        for label, color, cmd in [
            ("🗑️ Clear All",
             COLORS["danger"],
             self._clear_all_rows),
            ("➕ Add Row",
             COLORS["success"],
             self._add_item_row),
        ]:
            tk.Button(
                sec,
                text=label,
                font=FONTS["label_bold"],
                bg=color,
                fg="white",
                relief="flat",
                padx=10,
                pady=4,
                cursor="hand2",
                command=cmd
            ).pack(side="right", padx=5, pady=4)

        # Table container
        table_outer = tk.Frame(
            self, bg=COLORS["bg_main"]
        )
        table_outer.pack(
            fill="both", expand=True,
            padx=10, pady=0
        )

        # Column headers
        build_items_table_header(table_outer)

        # Canvas for scrollable rows
        canvas = tk.Canvas(
            table_outer,
            bg=COLORS["bg_card"],
            highlightthickness=1,
            highlightbackground=COLORS["border"]
        )
        sb_y = ttk.Scrollbar(
            table_outer,
            orient="vertical",
            command=canvas.yview
        )
        sb_x = ttk.Scrollbar(
            table_outer,
            orient="horizontal",
            command=canvas.xview
        )
        canvas.configure(
            yscrollcommand=sb_y.set,
            xscrollcommand=sb_x.set
        )

        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")
        canvas.pack(
            side="left", fill="both", expand=True
        )

        self.items_inner = tk.Frame(
            canvas, bg=COLORS["bg_card"]
        )
        cw = canvas.create_window(
            (0, 0),
            window=self.items_inner,
            anchor="nw"
        )

        self.items_inner.bind(
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

    def _add_item_row(self) -> ItemRow:
        """Add new empty item row"""
        row_num = len(self.item_rows) + 1
        row = ItemRow(
            parent=self.items_inner,
            row_num=row_num,
            on_change_callback=self._recalculate_totals,
            on_delete_callback=self._delete_item_row,
            hsn_data=self.hsn_data
        )
        row.pack(fill="x")
        self.item_rows.append(row)
        self._recalculate_totals()
        return row

    def _delete_item_row(self, row: ItemRow):
        """Remove item row"""
        if len(self.item_rows) <= 1:
            messagebox.showwarning(
                "Cannot Delete",
                "At least one row required."
            )
            return
        self.item_rows.remove(row)
        row.destroy()
        for i, r in enumerate(self.item_rows):
            r.row_num = i + 1
        self._recalculate_totals()

    def _clear_all_rows(self):
        """Clear all rows"""
        if not messagebox.askyesno(
            "Clear All", "Remove all item rows?"
        ):
            return
        for row in self.item_rows:
            row.destroy()
        self.item_rows.clear()
        self._add_item_row()

    # ----------------------------------------------------------
    # FOOTER — ALWAYS VISIBLE
    # ----------------------------------------------------------
    def _build_footer(self):
        """
        Totals + Save/Cancel buttons.
        Uses pack(side="bottom") to stay at bottom.
        """
        footer = tk.Frame(
            self,
            bg=COLORS["bg_card"],
            pady=10,
            padx=15,
            relief="raised",
            bd=1
        )
        # pack at bottom — always visible
        footer.pack(
            fill="x", side="bottom",
            padx=10, pady=5
        )

        # Left — Totals display
        totals = tk.Frame(footer, bg=COLORS["bg_card"])
        totals.pack(side="left")

        self.lbl_subtotal = tk.Label(
            totals,
            text="Taxable: ₹0.00",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        )
        self.lbl_subtotal.pack(anchor="w")

        self.lbl_gst_total = tk.Label(
            totals,
            text="Total GST: ₹0.00",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["warning"]
        )
        self.lbl_gst_total.pack(anchor="w")

        self.lbl_grand = tk.Label(
            totals,
            text="Grand Total: ₹0.00",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["success"]
        )
        self.lbl_grand.pack(anchor="w")

        self.lbl_count = tk.Label(
            totals,
            text="Items: 0",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        )
        self.lbl_count.pack(anchor="w")

        # Right — Buttons
        btns = tk.Frame(footer, bg=COLORS["bg_card"])
        btns.pack(side="right")

        tk.Button(
            btns,
            text="✕  Cancel",
            font=FONTS["button"],
            bg=COLORS["text_muted"],
            fg="white",
            relief="flat",
            padx=20,
            pady=10,
            cursor="hand2",
            command=self.destroy
        ).pack(side="left", padx=8)

        # SAVE BILL — large prominent button
        tk.Button(
            btns,
            text="💾  Save Purchase Bill",
            font=FONTS["button"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=25,
            pady=10,
            cursor="hand2",
            command=self._save_bill
        ).pack(side="left")

    # ----------------------------------------------------------
    # RECALCULATE TOTALS
    # ----------------------------------------------------------
    def _recalculate_totals(self):
        """Sum all rows → update footer labels"""
        subtotal  = 0.0
        gst_total = 0.0
        count     = 0

        for row in self.item_rows:
            try:
                qty  = safe_float(row.var_qty.get())
                rate = safe_float(row.var_rate.get())
                gst  = safe_float(
                    row.var_gst_rate.get(), 18
                )
                if qty > 0 and rate > 0:
                    taxable   = qty * rate
                    gst_amt   = round2(
                        taxable * gst / 100
                    )
                    subtotal  += taxable
                    gst_total += gst_amt
                    count += 1
            except Exception:
                pass

        grand = round2(subtotal + gst_total)

        self.lbl_subtotal.configure(
            text=f"Taxable: ₹{subtotal:,.2f}"
        )
        self.lbl_gst_total.configure(
            text=f"Total GST: ₹{gst_total:,.2f}"
        )
        self.lbl_grand.configure(
            text=f"Grand Total: ₹{grand:,.2f}"
        )
        self.lbl_count.configure(
            text=f"{count} items | {len(self.item_rows)} rows"
        )

    # ----------------------------------------------------------
    # SAVE BILL
    # ----------------------------------------------------------
    def _save_bill(self):
        """Validate and save to database"""
        errors = []

        dealer = self.var_dealer.get().strip()
        if not dealer:
            errors.append("• Dealer name is required")

        bill_no = self.var_bill_no.get().strip()
        if not bill_no:
            errors.append("• Bill number is required")

        try:
            bill_date = datetime.strptime(
                self.var_bill_date.get().strip(),
                "%d-%m-%Y"
            )
        except ValueError:
            errors.append(
                "• Invalid date. Use DD-MM-YYYY"
            )
            bill_date = None

        valid_rows = []
        for row in self.item_rows:
            data = row.get_data()
            if not data["item_name"] and \
                    data["quantity"] == 0:
                continue
            ok, msg = row.is_valid()
            if not ok:
                errors.append(f"• {msg}")
            else:
                valid_rows.append(data)

        if not valid_rows:
            errors.append("• No valid items to save")

        if errors:
            messagebox.showerror(
                "Fix These Errors",
                "\n".join(errors)
            )
            return

        subtotal  = sum(
            r["quantity"] * r["rate"]
            for r in valid_rows
        )
        gst_total = sum(
            r["gst_amount"] for r in valid_rows
        )
        grand     = round2(subtotal + gst_total)
        month     = bill_date.month
        year      = bill_date.year

        try:
            if self.edit_bill_id:
                db.execute("""
                    UPDATE purchase_bills SET
                        dealer_name=?, bill_number=?,
                        bill_date=?, bill_month=?,
                        bill_year=?, subtotal=?,
                        total_gst=?, grand_total=?,
                        bill_type=?, notes=?
                    WHERE id=?
                """, (
                    dealer, bill_no,
                    bill_date.strftime("%Y-%m-%d"),
                    month, year,
                    round2(subtotal),
                    round2(gst_total),
                    grand,
                    self.var_bill_type.get(),
                    self.var_notes.get().strip(),
                    self.edit_bill_id
                ))
                db.execute("""
                    DELETE FROM purchase_items
                    WHERE purchase_bill_id=?
                """, (self.edit_bill_id,))
                bill_id = self.edit_bill_id
            else:
                bill_id = db.execute("""
                    INSERT INTO purchase_bills
                    (bill_number, dealer_name,
                     bill_date, bill_month, bill_year,
                     subtotal, total_gst, grand_total,
                     bill_type, notes, file_path)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    bill_no, dealer,
                    bill_date.strftime("%Y-%m-%d"),
                    month, year,
                    round2(subtotal),
                    round2(gst_total),
                    grand,
                    self.var_bill_type.get(),
                    self.var_notes.get().strip(),
                    ""
                ))

            # Save items
            for item in valid_rows:
                taxable = item["quantity"] * item["rate"]

                master = db.query_one("""
                    SELECT id FROM items_master
                    WHERE item_name_lower=?
                """, (item["item_name"].lower(),))

                if master:
                    master_id = master["id"]
                    if item["hsn_code"] != "-":
                        db.execute("""
                            UPDATE items_master
                            SET hsn_code=?,
                                gst_rate=?,
                                unit=?,
                                updated_at=
                                  CURRENT_TIMESTAMP
                            WHERE id=?
                        """, (
                            item["hsn_code"],
                            item["gst_rate"],
                            item["unit"],
                            master_id
                        ))
                else:
                    master_id = db.execute("""
                        INSERT INTO items_master
                        (item_name, item_name_lower,
                         hsn_code, gst_rate, unit)
                        VALUES (?,?,?,?,?)
                    """, (
                        item["item_name"],
                        item["item_name"].lower(),
                        item["hsn_code"],
                        item["gst_rate"],
                        item["unit"]
                    ))

                gst_amt = round2(
                    taxable * item["gst_rate"] / 100
                )
                total = round2(taxable + gst_amt)

                db.execute("""
                    INSERT INTO purchase_items
                    (purchase_bill_id, item_master_id,
                     item_name, hsn_code,
                     quantity, unit,
                     purchase_rate, gst_rate,
                     gst_amount, total_amount,
                     remaining_qty)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    bill_id, master_id,
                    item["item_name"],
                    item["hsn_code"],
                    item["quantity"],
                    item["unit"],
                    item["rate"],
                    item["gst_rate"],
                    gst_amt, total,
                    item["quantity"]
                ))

            if self.uploaded_file_path:
                self._copy_uploaded_file(
                    self.uploaded_file_path,
                    month, year, bill_id
                )

            self._update_monthly_summary(month, year)

            messagebox.showinfo(
                "✅ Bill Saved!",
                f"Purchase bill saved!\n\n"
                f"Dealer : {dealer}\n"
                f"Bill No: {bill_no}\n"
                f"Items  : {len(valid_rows)}\n"
                f"Total  : ₹{grand:,.2f}"
            )

            if self.on_save:
                self.on_save()

            self.destroy()

        except Exception as e:
            messagebox.showerror(
                "Save Error",
                f"Could not save.\n\nError: {e}"
            )

    def _copy_uploaded_file(
        self, src_path, month, year, bill_id
    ):
        try:
            settings    = load_settings()
            dest_folder = get_month_folder(
                year, month, "Purchases", settings
            )
            src  = Path(src_path)
            dest = (
                dest_folder / "uploaded" /
                f"PB_{year}{month:02d}_{bill_id}"
                f"{src.suffix}"
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            db.execute("""
                UPDATE purchase_bills
                SET file_path=? WHERE id=?
            """, (str(dest), bill_id))
        except Exception as e:
            print(f"[FILE] {e}")

    def _update_monthly_summary(self, month, year):
        p = db.query_one("""
            SELECT COUNT(*) AS cnt,
              COALESCE(SUM(subtotal),0) AS tp,
              COALESCE(SUM(total_gst),0) AS tg
            FROM purchase_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        s = db.query_one("""
            SELECT COUNT(*) AS cnt,
              COALESCE(SUM(subtotal),0) AS ts,
              COALESCE(SUM(total_cgst),0) AS tc,
              COALESCE(SUM(total_sgst),0) AS tsg
            FROM sales_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        profit  = s.get("ts", 0) - p.get("tp", 0)
        out_gst = s.get("tc", 0) + s.get("tsg", 0)
        payable = max(0, out_gst - p.get("tg", 0))

        db.execute("""
            INSERT INTO monthly_summary
            (month,year,total_purchase,
             total_purchase_gst,total_sales,
             total_cgst,total_sgst,total_profit,
             gst_payable,bills_count_purchase,
             bills_count_sales,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,
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
            p.get("tp", 0), p.get("tg", 0),
            s.get("ts", 0),
            s.get("tc", 0), s.get("tsg", 0),
            profit, payable,
            p.get("cnt", 0), s.get("cnt", 0)
        ))

    def _load_bill_for_edit(self, bill_id):
        bill = db.query_one("""
            SELECT * FROM purchase_bills WHERE id=?
        """, (bill_id,))
        if not bill:
            self.destroy()
            return

        self.var_dealer.set(bill["dealer_name"])
        self.var_bill_no.set(bill["bill_number"])
        try:
            d = datetime.strptime(
                bill["bill_date"], "%Y-%m-%d"
            )
            self.var_bill_date.set(
                d.strftime("%d-%m-%Y")
            )
        except Exception:
            self.var_bill_date.set(bill["bill_date"])

        self.var_bill_type.set(bill["bill_type"])
        self.var_notes.set(bill.get("notes", ""))

        items = db.query("""
            SELECT * FROM purchase_items
            WHERE purchase_bill_id=? ORDER BY id
        """, (bill_id,))

        for item in items:
            row = self._add_item_row()
            row.set_data({
                "item_name": item["item_name"],
                "hsn_code":  item["hsn_code"],
                "quantity":  item["quantity"],
                "unit":      item["unit"],
                "rate":      item["purchase_rate"],
                "gst_rate":  item["gst_rate"],
            })
        self._recalculate_totals()


# ============================================================
# PURCHASE FRAME — Main View (unchanged, kept complete)
# ============================================================
class PurchaseFrame(tk.Frame):

    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS["bg_main"])
        self.app      = app
        self.settings = load_settings()

        today = date.today()
        self.filter_month = tk.IntVar(value=today.month)
        self.filter_year  = tk.IntVar(value=today.year)

        self._build_ui()
        self._load_bills()

    def _build_ui(self):
        self._build_top_bar()
        self._build_summary_bar()
        self._build_bills_table()
        self._build_items_pool()

    def _build_top_bar(self):
        top = tk.Frame(self, bg=COLORS["bg_main"])
        top.pack(fill="x", padx=25, pady=(20, 5))

        tk.Label(
            top,
            text="📥  Purchase Bills",
            font=FONTS["heading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        right = tk.Frame(top, bg=COLORS["bg_main"])
        right.pack(side="right")

        tk.Label(
            right, text="Month:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(0, 5))

        self.month_cb = ttk.Combobox(
            right, values=MONTH_NAMES[1:],
            width=11, font=FONTS["body"],
            state="readonly"
        )
        self.month_cb.set(
            MONTH_NAMES[self.filter_month.get()]
        )
        self.month_cb.pack(side="left", padx=3)
        self.month_cb.bind(
            "<<ComboboxSelected>>",
            lambda e: self._on_filter_change(
                self.month_cb.get(), None
            )
        )

        current_year = date.today().year
        self.year_cb = ttk.Combobox(
            right,
            values=[
                str(y) for y in range(
                    current_year - 3, current_year + 2
                )
            ],
            width=7, font=FONTS["body"],
            state="readonly"
        )
        self.year_cb.set(str(self.filter_year.get()))
        self.year_cb.pack(side="left", padx=3)
        self.year_cb.bind(
            "<<ComboboxSelected>>",
            lambda e: self._on_filter_change(
                None, self.year_cb.get()
            )
        )

        tk.Button(
            right,
            text="➕  Add Purchase Bill",
            font=FONTS["button"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=15, pady=8,
            cursor="hand2",
            command=self._open_add_dialog
        ).pack(side="left", padx=(15, 0))

    def _on_filter_change(self, month_name, year_str):
        if month_name:
            self.filter_month.set(
                MONTH_NAMES.index(month_name)
            )
        if year_str:
            self.filter_year.set(int(year_str))
        self._load_bills()

    def _build_summary_bar(self):
        bar = tk.Frame(
            self, bg=COLORS["primary"], pady=8
        )
        bar.pack(fill="x", padx=25)

        self.lbl_summary_bills = tk.Label(
            bar, text="Bills: 0",
            font=FONTS["body_bold"],
            bg=COLORS["primary"], fg="white"
        )
        self.lbl_summary_bills.pack(
            side="left", padx=20
        )

        for sep_text in ["|", "|", "|"]:
            tk.Label(
                bar, text=sep_text,
                font=FONTS["body"],
                bg=COLORS["primary"],
                fg="#5c6bc0"
            ).pack(side="left")

        self.lbl_summary_taxable = tk.Label(
            bar, text="Taxable: ₹0.00",
            font=FONTS["body_bold"],
            bg=COLORS["primary"], fg="white"
        )
        self.lbl_summary_taxable.pack(
            side="left", padx=20
        )

        self.lbl_summary_gst = tk.Label(
            bar, text="GST: ₹0.00",
            font=FONTS["body_bold"],
            bg=COLORS["primary"], fg="#90caf9"
        )
        self.lbl_summary_gst.pack(
            side="left", padx=20
        )

        self.lbl_summary_total = tk.Label(
            bar, text="Grand Total: ₹0.00",
            font=FONTS["subheading"],
            bg=COLORS["primary"], fg="#a5d6a7"
        )
        self.lbl_summary_total.pack(
            side="left", padx=20
        )

    def _build_bills_table(self):
        container = tk.Frame(
            self, bg=COLORS["bg_main"]
        )
        container.pack(
            fill="both", expand=True,
            padx=25, pady=8
        )

        tk.Label(
            container,
            text="Purchase Bills List",
            font=FONTS["subheading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 5))

        hdr = tk.Frame(
            container, bg=COLORS["header_bg"]
        )
        hdr.pack(fill="x")

        for col, width in [
            ("#", 4), ("Dealer", 22),
            ("Bill No", 14), ("Date", 12),
            ("Items", 6), ("Taxable", 12),
            ("GST", 10), ("Total", 13),
            ("Actions", 20),
        ]:
            tk.Label(
                hdr, text=col,
                font=FONTS["table_bold"],
                bg=COLORS["header_bg"],
                fg="white", width=width,
                anchor="w", padx=5, pady=7
            ).pack(side="left")

        body_outer = tk.Frame(
            container, bg=COLORS["bg_card"],
            relief="solid", bd=1
        )
        body_outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            body_outer, bg=COLORS["bg_card"],
            highlightthickness=0
        )
        sb = ttk.Scrollbar(
            body_outer, orient="vertical",
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
            (0, 0), window=self.bills_body,
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

    def _build_items_pool(self):
        pool = tk.Frame(
            self, bg=COLORS["bg_card"],
            padx=20, pady=12
        )
        pool.pack(fill="x", padx=25, pady=(0, 15))

        title_row = tk.Frame(pool, bg=COLORS["bg_card"])
        title_row.pack(fill="x")

        tk.Label(
            title_row,
            text="📦 Monthly Stock Pool",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Label(
            title_row,
            text="(All items this month — "
                 "used for generating sales bills)",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        ).pack(side="left", padx=10)

        phdr = tk.Frame(
            pool, bg=COLORS["primary_light"]
        )
        phdr.pack(fill="x", pady=(8, 0))

        for col, width in [
            ("Item Name", 25), ("HSN", 10),
            ("Total Qty", 10), ("Unit", 8),
            ("Avg Rate", 10), ("Remaining", 10),
            ("GST%", 6), ("Status", 10),
        ]:
            tk.Label(
                phdr, text=col,
                font=FONTS["table_bold"],
                bg=COLORS["primary_light"],
                fg="white", width=width,
                anchor="w", padx=5, pady=5
            ).pack(side="left")

        self.pool_body = tk.Frame(
            pool, bg=COLORS["bg_card"]
        )
        self.pool_body.pack(fill="x")

    def _load_bills(self):
        month = self.filter_month.get()
        year  = self.filter_year.get()

        for w in self.bills_body.winfo_children():
            w.destroy()

        bills = db.query("""
            SELECT pb.*,
              (SELECT COUNT(*) FROM purchase_items pi
               WHERE pi.purchase_bill_id = pb.id)
               AS item_count
            FROM purchase_bills pb
            WHERE pb.bill_month=? AND pb.bill_year=?
            ORDER BY pb.bill_date, pb.id
        """, (month, year))

        totals = db.query_one("""
            SELECT COUNT(*) AS cnt,
              COALESCE(SUM(subtotal),0) AS taxable,
              COALESCE(SUM(total_gst),0) AS gst,
              COALESCE(SUM(grand_total),0) AS total
            FROM purchase_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        self.lbl_summary_bills.configure(
            text=f"Bills: {totals.get('cnt', 0)}"
        )
        self.lbl_summary_taxable.configure(
            text=f"Taxable: "
                 f"₹{totals.get('taxable', 0):,.2f}"
        )
        self.lbl_summary_gst.configure(
            text=f"GST: ₹{totals.get('gst', 0):,.2f}"
        )
        self.lbl_summary_total.configure(
            text=f"Grand Total: "
                 f"₹{totals.get('total', 0):,.2f}"
        )

        if not bills:
            tk.Label(
                self.bills_body,
                text=(
                    f"No purchase bills found for\n"
                    f"{MONTH_NAMES[month]} {year}.\n\n"
                    "Click '➕ Add Purchase Bill'"
                ),
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"],
                justify="center"
            ).pack(pady=30)
            self._load_pool(month, year)
            return

        for i, bill in enumerate(bills):
            self._render_bill_row(bill, i)
        self._load_pool(month, year)

    def _render_bill_row(self, bill, idx):
        bg = (
            COLORS["row_even"]
            if idx % 2 == 0
            else COLORS["row_odd"]
        )
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
            (str(idx + 1),               4),
            (bill["dealer_name"],        22),
            (bill["bill_number"],        14),
            (date_str,                   12),
            (str(bill["item_count"]),     6),
            (f"₹{bill['subtotal']:,.0f}",12),
            (f"₹{bill['total_gst']:,.0f}",10),
            (f"₹{bill['grand_total']:,.0f}",13),
        ]:
            tk.Label(
                row, text=text,
                font=FONTS["table"],
                bg=bg, fg=COLORS["text_dark"],
                width=width, anchor="w",
                padx=5, pady=6
            ).pack(side="left")

        act = tk.Frame(row, bg=bg)
        act.pack(side="left", padx=5)
        bid = bill["id"]

        tk.Button(
            act, text="✏️",
            font=FONTS["small"],
            bg=COLORS["primary_light"],
            fg="white", relief="flat",
            padx=6, pady=3, cursor="hand2",
            command=lambda b=bid: self._edit_bill(b)
        ).pack(side="left", padx=2)

        tk.Button(
            act, text="📦",
            font=FONTS["small"],
            bg=COLORS["accent"],
            fg="white", relief="flat",
            padx=6, pady=3, cursor="hand2",
            command=lambda b=bid: self._view_items(b)
        ).pack(side="left", padx=2)

        tk.Button(
            act, text="🗑️",
            font=FONTS["small"],
            bg=COLORS["danger"],
            fg="white", relief="flat",
            padx=6, pady=3, cursor="hand2",
            command=lambda b=bid: self._delete_bill(b)
        ).pack(side="left", padx=2)

    def _load_pool(self, month, year):
        for w in self.pool_body.winfo_children():
            w.destroy()

        items = db.query("""
            SELECT pi.item_name, pi.hsn_code,
              pi.unit, pi.gst_rate,
              SUM(pi.quantity) AS total_qty,
              SUM(pi.remaining_qty) AS remaining_qty,
              AVG(pi.purchase_rate) AS avg_rate
            FROM purchase_items pi
            JOIN purchase_bills pb
              ON pi.purchase_bill_id = pb.id
            WHERE pb.bill_month=? AND pb.bill_year=?
            GROUP BY pi.item_name, pi.unit
            ORDER BY pi.item_name
        """, (month, year))

        if not items:
            tk.Label(
                self.pool_body,
                text="No items yet. Add purchase bills.",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).pack(pady=10)
            return

        for i, item in enumerate(items):
            bg = (
                COLORS["row_even"]
                if i % 2 == 0
                else COLORS["row_odd"]
            )
            row = tk.Frame(self.pool_body, bg=bg)
            row.pack(fill="x")

            remaining = item["remaining_qty"] or 0
            total     = item["total_qty"] or 0
            status = (
                "✅ Done" if remaining == 0 else
                "⚠️ Partial" if remaining < total else
                "📦 Pending"
            )
            sc = (
                COLORS["success"] if remaining == 0
                else COLORS["warning"]
                if remaining < total
                else COLORS["text_muted"]
            )

            for text, width in [
                (item["item_name"],          25),
                (item["hsn_code"] or "-",    10),
                (f"{total:.1f}",             10),
                (item["unit"],                8),
                (f"₹{item['avg_rate']:.2f}", 10),
                (f"{remaining:.1f}",         10),
                (f"{item['gst_rate']:.0f}%",  6),
            ]:
                tk.Label(
                    row, text=text,
                    font=FONTS["table"],
                    bg=bg, fg=COLORS["text_dark"],
                    width=width, anchor="w",
                    padx=5, pady=5
                ).pack(side="left")

            tk.Label(
                row, text=status,
                font=FONTS["table_bold"],
                bg=bg, fg=sc,
                width=10, anchor="w", padx=5
            ).pack(side="left")

    def _open_add_dialog(self):
        PurchaseBillDialog(
            self, self.app,
            on_save_callback=self._load_bills
        )

    def _edit_bill(self, bill_id):
        PurchaseBillDialog(
            self, self.app,
            edit_bill_id=bill_id,
            on_save_callback=self._load_bills
        )

    def _view_items(self, bill_id):
        items = db.query("""
            SELECT * FROM purchase_items
            WHERE purchase_bill_id=? ORDER BY id
        """, (bill_id,))
        bill = db.query_one("""
            SELECT * FROM purchase_bills WHERE id=?
        """, (bill_id,))

        popup = tk.Toplevel(self)
        popup.title(
            f"{bill.get('dealer_name','')} | "
            f"{bill.get('bill_number','')}"
        )
        popup.geometry("900x500")
        popup.configure(bg=COLORS["bg_main"])

        tk.Label(
            popup,
            text=f"📦 {bill.get('bill_number')} — "
                 f"{bill.get('dealer_name')}",
            font=FONTS["subheading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", padx=20, pady=(15, 5))

        hdr = tk.Frame(popup, bg=COLORS["header_bg"])
        hdr.pack(fill="x", padx=20)
        for col, width in [
            ("Item", 28), ("HSN", 10), ("Qty", 8),
            ("Unit", 8), ("Rate", 10), ("GST%", 6),
            ("GST Amt", 10), ("Total", 12),
            ("Remaining", 10)
        ]:
            tk.Label(
                hdr, text=col,
                font=FONTS["table_bold"],
                bg=COLORS["header_bg"],
                fg="white", width=width,
                anchor="w", padx=5, pady=6
            ).pack(side="left")

        body = tk.Frame(popup, bg=COLORS["bg_card"])
        body.pack(fill="both", expand=True, padx=20)

        for i, item in enumerate(items):
            bg = (
                COLORS["row_even"]
                if i % 2 == 0
                else COLORS["row_odd"]
            )
            row = tk.Frame(body, bg=bg)
            row.pack(fill="x")
            for text, width in [
                (item["item_name"],              28),
                (item["hsn_code"] or "-",        10),
                (f"{item['quantity']:.2f}",       8),
                (item["unit"],                    8),
                (f"₹{item['purchase_rate']:.2f}",10),
                (f"{item['gst_rate']:.0f}%",      6),
                (f"₹{item['gst_amount']:.2f}",   10),
                (f"₹{item['total_amount']:.2f}",  12),
                (f"{item['remaining_qty']:.2f}",  10),
            ]:
                tk.Label(
                    row, text=text,
                    font=FONTS["table"],
                    bg=bg, fg=COLORS["text_dark"],
                    width=width, anchor="w",
                    padx=5, pady=5
                ).pack(side="left")

    def _delete_bill(self, bill_id):
        bill = db.query_one("""
            SELECT * FROM purchase_bills WHERE id=?
        """, (bill_id,))
        if not bill:
            return

        month = bill["bill_month"]
        year  = bill["bill_year"]

        sales = db.query_one("""
            SELECT COUNT(*) AS cnt FROM sales_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        msg = (
            "Sales bills exist for this month.\n"
            "Deleting may cause mismatch.\nContinue?"
            if sales.get("cnt", 0) > 0
            else f"Delete bill from "
                 f"{bill['dealer_name']}?\n"
                 f"Total: ₹{bill['grand_total']:,.2f}\n"
                 f"Cannot be undone."
        )

        if not messagebox.askyesno(
            "Delete Bill", msg
        ):
            return

        db.execute("""
            DELETE FROM purchase_items
            WHERE purchase_bill_id=?
        """, (bill_id,))
        db.execute("""
            DELETE FROM purchase_bills WHERE id=?
        """, (bill_id,))

        self.app.set_status(
            "Purchase bill deleted", "warning"
        )
        self._load_bills()