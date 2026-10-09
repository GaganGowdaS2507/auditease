# modules/customer_module.py
# ============================================================
# CUSTOMER MODULE
# Manages customer database and Karnataka name generation
#
# Features:
# 1. Add / Edit / Delete customers manually
# 2. Auto-generate Karnataka names
# 3. Track used names per month (avoid repeats)
# 4. Search customers
# 5. Import customers from CSV
# 6. Export customer list
# 7. Smart name picker for sales bill generation
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import json
import csv
import random
import re
from pathlib import Path
from datetime import date

# ============================================================
# PATHS
# ============================================================
BASE_DIR      = Path(__file__).parent.parent
CONFIG_PATH   = BASE_DIR / "config" / "settings.json"
DB_PATH       = BASE_DIR / "database" / "shop_database.db"
NAMES_PATH    = BASE_DIR / "data"    / "karnataka_names.json"

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
    "danger":         "#c62828",
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


# ============================================================
# DATABASE HELPER
# ============================================================
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
# KARNATAKA NAME GENERATOR
# ============================================================
class KarnatakaNameGenerator:
    """
    Generates realistic Karnataka customer names.

    Features:
    - Uses real Karnataka first names and last names
    - Tracks used names per month to avoid repeats
    - Gender-balanced generation
    - City-aware (Karnataka cities only)
    - Prefix titles (Sri, Smt, etc.)
    """

    def __init__(self):
        self.names_data = self._load_names()
        self._used_names_cache = {}  # month_year → set of names

    def _load_names(self) -> dict:
        """Load Karnataka names from JSON file"""
        try:
            with open(NAMES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[NAMES] Load error: {e}")
            return self._fallback_names()

    def _fallback_names(self) -> dict:
        """Minimal fallback if JSON file missing"""
        return {
            "male_first_names": [
                "Ramesh", "Suresh", "Mahesh", "Nagaraj",
                "Basavaraj", "Shivakumar", "Prakash",
                "Venkatesh", "Ganesh", "Rajesh"
            ],
            "female_first_names": [
                "Lakshmi", "Savitha", "Rekha", "Meena",
                "Pushpa", "Geetha", "Kavitha", "Usha"
            ],
            "last_names": [
                "Gowda", "Shetty", "Patil", "Naik",
                "Reddy", "Rao", "Swamy", "Nayak",
                "Kulkarni", "Hegde"
            ],
            "cities_karnataka": [
                "Bangalore", "Mysore", "Hubli",
                "Dharwad", "Mangalore", "Belgaum",
                "Tumkur", "Shimoga", "Udupi", "Hassan"
            ]
        }

    def _get_used_names(
        self, month: int, year: int
    ) -> set:
        """Get set of names already used this month"""
        key = f"{month}_{year}"

        if key not in self._used_names_cache:
            # Load from database
            rows = db.query("""
                SELECT customer_name
                FROM sales_bills
                WHERE bill_month=? AND bill_year=?
            """, (month, year))

            self._used_names_cache[key] = {
                r["customer_name"].lower()
                for r in rows
            }

        return self._used_names_cache[key]

    def refresh_cache(self, month: int, year: int):
        """Refresh the used names cache"""
        key = f"{month}_{year}"
        if key in self._used_names_cache:
            del self._used_names_cache[key]

    def generate_name(
        self,
        month: int,
        year: int,
        gender: str = "random",
        max_attempts: int = 50
    ) -> str:
        """
        Generate a unique Karnataka name not used this month.

        Args:
            month: Bill month (1-12)
            year: Bill year
            gender: "male", "female", or "random"
            max_attempts: Max tries before allowing repeat

        Returns:
            Full name string like "Sri Ramesh Gowda"
        """
        used_names = self._get_used_names(month, year)
        names_data = self.names_data

        male_first   = names_data.get("male_first_names", [])
        female_first = names_data.get("female_first_names", [])
        last_names   = names_data.get("last_names", [])

        attempts = 0

        while attempts < max_attempts:
            # Choose gender
            if gender == "random":
                is_male = random.random() > 0.3  # 70% male
            else:
                is_male = (gender == "male")

            # Pick names
            if is_male and male_first:
                first = random.choice(male_first)
                prefix = random.choice([
                    "Sri", "Sri", "Sri",  # weighted more
                    "Mr.", "", ""
                ])
            elif female_first:
                first = random.choice(female_first)
                prefix = random.choice([
                    "Smt.", "Smt.", "Kum.",
                    "Mrs.", "", ""
                ])
            else:
                first  = random.choice(
                    male_first or ["Ramesh"]
                )
                prefix = "Sri"

            last   = random.choice(last_names) if last_names \
                     else "Gowda"

            # Build full name
            if prefix:
                full_name = f"{prefix} {first} {last}"
            else:
                full_name = f"{first} {last}"

            # Check uniqueness
            if full_name.lower() not in used_names:
                # Add to cache
                used_names.add(full_name.lower())
                return full_name

            attempts += 1

        # Max attempts reached — add number suffix
        base = f"Sri {random.choice(male_first)} " \
               f"{random.choice(last_names)}"
        suffix = random.randint(2, 99)
        return f"{base} {suffix}"

    def generate_batch(
        self,
        count: int,
        month: int,
        year: int
    ) -> list:
        """
        Generate a batch of unique customer names.

        Args:
            count: Number of names needed
            month: Bill month
            year: Bill year

        Returns:
            List of unique name strings
        """
        names = []
        # Mix genders: ~70% male, ~30% female
        for i in range(count):
            gender = "male" if random.random() > 0.3 \
                     else "female"
            name = self.generate_name(month, year, gender)
            names.append(name)
        return names

    def get_city(self) -> str:
        """Return a random Karnataka city"""
        cities = self.names_data.get(
            "cities_karnataka", ["Bangalore"]
        )
        return random.choice(cities)

    def get_all_names_from_db(self) -> list:
        """Get all manually entered customer names"""
        return db.query("""
            SELECT * FROM customers
            WHERE is_auto_generated = 0
            ORDER BY name
        """)

    def pick_customer_for_bill(
        self,
        month: int,
        year: int,
        prefer_manual: bool = True
    ) -> dict:
        """
        Pick a customer for a sales bill.

        Priority:
        1. Manual customers not yet used this month
        2. Auto-generated Karnataka name

        Returns dict with name, city, phone
        """
        used_names = self._get_used_names(month, year)

        if prefer_manual:
            # Try to use manual customers first
            manual = db.query("""
                SELECT * FROM customers
                WHERE is_auto_generated = 0
                ORDER BY RANDOM()
                LIMIT 20
            """)

            for customer in manual:
                if customer["name"].lower() \
                        not in used_names:
                    used_names.add(
                        customer["name"].lower()
                    )
                    return {
                        "name":    customer["name"],
                        "city":    customer.get("city", ""),
                        "phone":   customer.get("phone", ""),
                        "address": customer.get("address",""),
                        "source":  "manual"
                    }

        # Fall back to auto-generated
        name = self.generate_name(month, year)
        city = self.get_city()
        return {
            "name":    name,
            "city":    city,
            "phone":   "",
            "address": "",
            "source":  "auto"
        }


# ============================================================
# ADD / EDIT CUSTOMER DIALOG
# ============================================================
class CustomerDialog(tk.Toplevel):
    """
    Modal dialog for adding or editing a customer.
    """

    def __init__(
        self, parent,
        edit_customer_id: int = None,
        on_save_callback=None
    ):
        super().__init__(parent)
        self.edit_id     = edit_customer_id
        self.on_save     = on_save_callback

        title = ("Edit Customer"
                 if edit_customer_id
                 else "Add New Customer")
        self.title(title)
        self.geometry("500x420")
        self.resizable(False, False)
        self.configure(bg=COLORS["bg_main"])
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        self.geometry(f"+{px+100}+{py+80}")

        self.vars = {}
        self._build_ui()

        if edit_customer_id:
            self._load_customer(edit_customer_id)

    def _build_ui(self):
        """Build dialog UI"""

        # Header
        hdr = tk.Frame(
            self, bg=COLORS["primary"], pady=12
        )
        hdr.pack(fill="x")

        tk.Label(
            hdr,
            text=("✏️ Edit Customer"
                  if self.edit_id
                  else "👤 Add New Customer"),
            font=FONTS["subheading"],
            bg=COLORS["primary"],
            fg="white"
        ).pack(side="left", padx=20)

        # Form
        form = tk.Frame(
            self, bg=COLORS["bg_card"],
            padx=25, pady=20
        )
        form.pack(fill="both", expand=True,
                  padx=15, pady=10)

        # Fields
        fields = [
            ("Customer Name *", "name",    35, True,
             "e.g. Sri Ramesh Gowda"),
            ("Phone Number",    "phone",   15, False,
             "e.g. 9876543210"),
            ("City",            "city",    20, False,
             "e.g. Hubli"),
            ("Address",         "address", 35, False,
             "Street, Area (optional)"),
        ]

        for i, (label, key, width,
                required, hint) in enumerate(fields):
            self.vars[key] = tk.StringVar()

            tk.Label(
                form,
                text=label,
                font=FONTS["label_bold"],
                bg=COLORS["bg_card"],
                fg=(COLORS["primary"]
                    if required
                    else COLORS["text_dark"])
            ).grid(
                row=i, column=0,
                sticky="w", padx=(0, 15), pady=8
            )

            entry = tk.Entry(
                form,
                textvariable=self.vars[key],
                font=FONTS["body"],
                width=width,
                relief="solid",
                bd=1,
                bg="#fafafa"
            )
            entry.grid(
                row=i, column=1,
                sticky="w", pady=8
            )

            tk.Label(
                form,
                text=hint,
                font=FONTS["small"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).grid(
                row=i, column=2,
                sticky="w", padx=(8, 0)
            )

            entry.bind(
                "<FocusIn>",
                lambda e, ent=entry:
                    ent.configure(bg="white", bd=2)
            )
            entry.bind(
                "<FocusOut>",
                lambda e, ent=entry:
                    ent.configure(bg="#fafafa", bd=1)
            )

        # Notes
        tk.Label(
            form,
            text="Notes",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).grid(
            row=len(fields), column=0,
            sticky="nw", padx=(0, 15), pady=8
        )

        self.vars["notes"] = tk.StringVar()
        tk.Entry(
            form,
            textvariable=self.vars["notes"],
            font=FONTS["body"],
            width=35,
            relief="solid",
            bd=1,
            bg="#fafafa"
        ).grid(
            row=len(fields), column=1,
            sticky="w", pady=8
        )

        # Buttons
        btn_row = tk.Frame(self, bg=COLORS["bg_main"])
        btn_row.pack(fill="x", padx=15, pady=(0, 15))

        tk.Button(
            btn_row,
            text="✕ Cancel",
            font=FONTS["button"],
            bg=COLORS["text_muted"],
            fg="white",
            relief="flat",
            padx=20, pady=8,
            cursor="hand2",
            command=self.destroy
        ).pack(side="right", padx=5)

        tk.Button(
            btn_row,
            text="💾 Save Customer",
            font=FONTS["button"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=20, pady=8,
            cursor="hand2",
            command=self._save
        ).pack(side="right")

    def _load_customer(self, customer_id: int):
        """Load customer data for editing"""
        row = db.query_one("""
            SELECT * FROM customers WHERE id=?
        """, (customer_id,))

        if not row:
            return

        self.vars["name"].set(row.get("name", ""))
        self.vars["phone"].set(row.get("phone", ""))
        self.vars["city"].set(row.get("city", ""))
        self.vars["address"].set(row.get("address", ""))

    def _save(self):
        """Validate and save customer"""
        errors = []

        name = self.vars["name"].get().strip()
        if not name:
            errors.append("• Customer name is required")
        elif len(name) < 2:
            errors.append(
                "• Name too short (minimum 2 characters)"
            )

        phone = self.vars["phone"].get().strip()
        if phone and not re.match(r'^\d{10}$', phone):
            errors.append(
                "• Phone must be 10 digits (or leave blank)"
            )

        if errors:
            messagebox.showerror(
                "Validation Error",
                "\n".join(errors)
            )
            return

        try:
            if self.edit_id:
                db.execute("""
                    UPDATE customers SET
                        name=?, phone=?, city=?,
                        address=?
                    WHERE id=?
                """, (
                    name, phone,
                    self.vars["city"].get().strip(),
                    self.vars["address"].get().strip(),
                    self.edit_id
                ))
                msg = f"Customer '{name}' updated."
            else:
                # Check duplicate
                existing = db.query_one("""
                    SELECT id FROM customers
                    WHERE LOWER(name)=?
                    AND is_auto_generated=0
                """, (name.lower(),))

                if existing:
                    if not messagebox.askyesno(
                        "Duplicate",
                        f"Customer '{name}' already exists.\n"
                        "Add anyway?"
                    ):
                        return

                db.execute("""
                    INSERT INTO customers
                    (name, phone, city, address,
                     is_auto_generated)
                    VALUES (?,?,?,?,0)
                """, (
                    name, phone,
                    self.vars["city"].get().strip(),
                    self.vars["address"].get().strip(),
                ))
                msg = f"Customer '{name}' added."

            if self.on_save:
                self.on_save()

            messagebox.showinfo("Saved ✅", msg)
            self.destroy()

        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Could not save customer.\n{e}"
            )


# ============================================================
# CUSTOMER FRAME — MAIN VIEW
# ============================================================
class CustomerFrame(tk.Frame):
    """
    Customer management main view.

    Layout:
    ┌──────────────────────────────────────────────┐
    │  Title        [+ Add]  [Import CSV] [Export] │
    ├──────────────────────────────────────────────┤
    │  Search bar                                  │
    ├──────────────────────────────────────────────┤
    │  LEFT: Customer List Table                   │
    │  RIGHT: Auto-name Generator Panel            │
    ├──────────────────────────────────────────────┤
    │  Monthly Usage Stats                         │
    └──────────────────────────────────────────────┘
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS["bg_main"])
        self.app       = app
        self.generator = KarnatakaNameGenerator()

        today = date.today()
        self.view_month = tk.IntVar(value=today.month)
        self.view_year  = tk.IntVar(value=today.year)
        self.search_var = tk.StringVar()
        self.search_var.trace_add(
            "write",
            lambda *a: self._on_search_change()
        )

        self._build_ui()
        self._load_customers()

    # ----------------------------------------------------------
    # BUILD UI
    # ----------------------------------------------------------
    def _build_ui(self):
        self._build_top_bar()
        self._build_search_bar()

        # Main content — two columns
        content = tk.Frame(self, bg=COLORS["bg_main"])
        content.pack(
            fill="both", expand=True,
            padx=20, pady=5
        )

        # Left — customer list
        left = tk.Frame(content, bg=COLORS["bg_main"])
        left.pack(
            side="left", fill="both",
            expand=True, padx=(0, 8)
        )
        self._build_customer_table(left)

        # Right — generator panel
        right = tk.Frame(
            content, bg=COLORS["bg_card"],
            padx=15, pady=15,
            width=320
        )
        right.pack(side="left", fill="y")
        right.pack_propagate(False)
        self._build_generator_panel(right)

        # Bottom — monthly stats
        self._build_monthly_stats()

    def _build_top_bar(self):
        top = tk.Frame(self, bg=COLORS["bg_main"])
        top.pack(fill="x", padx=25, pady=(20, 5))

        tk.Label(
            top,
            text="👥  Customers",
            font=FONTS["heading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        # Right buttons
        right = tk.Frame(top, bg=COLORS["bg_main"])
        right.pack(side="right")

        for label, color, cmd in [
            ("📊 Export CSV",
             COLORS["text_muted"],
             self._export_csv),
            ("📥 Import CSV",
             COLORS["primary_light"],
             self._import_csv),
            ("➕ Add Customer",
             COLORS["success"],
             self._open_add_dialog),
        ]:
            tk.Button(
                right,
                text=label,
                font=FONTS["label_bold"],
                bg=color,
                fg="white",
                relief="flat",
                padx=12,
                pady=7,
                cursor="hand2",
                command=cmd
            ).pack(side="left", padx=4)

    def _build_search_bar(self):
        search_frame = tk.Frame(
            self, bg=COLORS["bg_card"],
            padx=15, pady=10
        )
        search_frame.pack(
            fill="x", padx=25, pady=5
        )

        tk.Label(
            search_frame,
            text="🔍 Search:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left", padx=(0, 10))

        search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            font=FONTS["body"],
            width=35,
            relief="solid",
            bd=1,
            bg="white"
        )
        search_entry.pack(side="left")
        search_entry.bind(
            "<FocusIn>",
            lambda e: search_entry.configure(bd=2)
        )
        search_entry.bind(
            "<FocusOut>",
            lambda e: search_entry.configure(bd=1)
        )

        tk.Button(
            search_frame,
            text="✕ Clear",
            font=FONTS["small"],
            bg=COLORS["border"],
            fg=COLORS["text_dark"],
            relief="flat",
            padx=8, pady=4,
            cursor="hand2",
            command=lambda: self.search_var.set("")
        ).pack(side="left", padx=8)

        # Customer count label
        self.count_label = tk.Label(
            search_frame,
            text="",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        )
        self.count_label.pack(side="right")

    def _build_customer_table(self, parent):
        """Scrollable customer list table"""

        tk.Label(
            parent,
            text="Manual Customers",
            font=FONTS["subheading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 5))

        # Header
        header = tk.Frame(parent, bg=COLORS["header_bg"])
        header.pack(fill="x")

        for col, width in [
            ("#",          4), ("Name",     25),
            ("Phone",     12), ("City",     15),
            ("Bills",      6), ("Actions", 16),
        ]:
            tk.Label(
                header,
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
        canvas.pack(side="left", fill="both", expand=True)

        self.table_body = tk.Frame(
            canvas, bg=COLORS["bg_card"]
        )
        cw = canvas.create_window(
            (0, 0),
            window=self.table_body,
            anchor="nw"
        )

        self.table_body.bind(
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

    def _build_generator_panel(self, parent):
        """Karnataka name auto-generator panel"""

        tk.Label(
            parent,
            text="🎲 Name Generator",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 5))

        tk.Label(
            parent,
            text="Auto-generate Karnataka names\n"
                 "for sales bills",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"],
            justify="left"
        ).pack(anchor="w", pady=(0, 10))

        # Month/Year for generation
        period_frame = tk.Frame(
            parent, bg=COLORS["bg_card"]
        )
        period_frame.pack(fill="x", pady=5)

        tk.Label(
            period_frame,
            text="For Month:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        today = date.today()
        month_cb = ttk.Combobox(
            period_frame,
            values=MONTH_NAMES[1:],
            width=10,
            font=FONTS["small"],
            state="readonly"
        )
        month_cb.set(MONTH_NAMES[self.view_month.get()])
        month_cb.pack(side="left", padx=5)
        month_cb.bind(
            "<<ComboboxSelected>>",
            lambda e: self.view_month.set(
                MONTH_NAMES.index(month_cb.get())
            )
        )

        year_cb = ttk.Combobox(
            period_frame,
            values=[str(y) for y in range(
                today.year - 2, today.year + 2
            )],
            width=6,
            font=FONTS["small"],
            state="readonly"
        )
        year_cb.set(str(self.view_year.get()))
        year_cb.pack(side="left", padx=3)
        year_cb.bind(
            "<<ComboboxSelected>>",
            lambda e: self.view_year.set(
                int(year_cb.get())
            )
        )

        # Count selector
        count_frame = tk.Frame(
            parent, bg=COLORS["bg_card"]
        )
        count_frame.pack(fill="x", pady=8)

        tk.Label(
            count_frame,
            text="How many names:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        self.gen_count = tk.IntVar(value=5)
        tk.Spinbox(
            count_frame,
            from_=1, to=50,
            textvariable=self.gen_count,
            font=FONTS["body"],
            width=5,
            relief="solid",
            bd=1
        ).pack(side="left", padx=10)

        # Generate button
        tk.Button(
            parent,
            text="🎲 Generate Names",
            font=FONTS["button"],
            bg=COLORS["accent"],
            fg="white",
            relief="flat",
            padx=15, pady=8,
            cursor="hand2",
            command=self._generate_names
        ).pack(fill="x", pady=5)

        # Generated names display
        tk.Label(
            parent,
            text="Generated Names:",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(10, 3))

        self.names_listbox = tk.Listbox(
            parent,
            font=FONTS["label"],
            height=12,
            relief="solid",
            bd=1,
            selectmode="multiple",
            bg="white",
            fg=COLORS["text_dark"],
            selectbackground=COLORS["primary_light"],
            selectforeground="white"
        )
        self.names_listbox.pack(fill="x", pady=3)

        # Action buttons for generated names
        action_frame = tk.Frame(
            parent, bg=COLORS["bg_card"]
        )
        action_frame.pack(fill="x", pady=5)

        tk.Button(
            action_frame,
            text="💾 Save Selected",
            font=FONTS["small"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=8, pady=5,
            cursor="hand2",
            command=self._save_generated_names
        ).pack(side="left", padx=(0, 5))

        tk.Button(
            action_frame,
            text="💾 Save All",
            font=FONTS["small"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=8, pady=5,
            cursor="hand2",
            command=self._save_all_generated_names
        ).pack(side="left")

        tk.Button(
            action_frame,
            text="🔄 Regenerate",
            font=FONTS["small"],
            bg=COLORS["text_muted"],
            fg="white",
            relief="flat",
            padx=8, pady=5,
            cursor="hand2",
            command=self._generate_names
        ).pack(side="right")

        # Preview info
        self.gen_info_label = tk.Label(
            parent,
            text="",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"],
            wraplength=280,
            justify="left"
        )
        self.gen_info_label.pack(
            anchor="w", pady=(5, 0)
        )

    def _build_monthly_stats(self):
        """Show customer usage stats for the month"""
        stats_frame = tk.Frame(
            self,
            bg=COLORS["bg_card"],
            padx=20, pady=12
        )
        stats_frame.pack(
            fill="x", padx=25, pady=(5, 15)
        )

        tk.Label(
            stats_frame,
            text="📊 Monthly Customer Usage",
            font=FONTS["subheading"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", pady=(0, 8))

        # Stats row
        self.stats_row = tk.Frame(
            stats_frame, bg=COLORS["bg_card"]
        )
        self.stats_row.pack(fill="x")

        self.stats_labels = {}

        for key, label, color in [
            ("total_customers",
             "Total Customers in DB",
             COLORS["primary"]),
            ("used_this_month",
             "Used This Month",
             COLORS["accent"]),
            ("manual_customers",
             "Manual Entries",
             COLORS["success"]),
            ("auto_generated",
             "Auto-Generated",
             COLORS["text_muted"]),
        ]:
            card = tk.Frame(
                self.stats_row,
                bg=color,
                padx=15, pady=10
            )
            card.pack(side="left", padx=5)

            tk.Label(
                card,
                text=label,
                font=FONTS["small"],
                bg=color,
                fg="white"
            ).pack()

            lbl = tk.Label(
                card,
                text="0",
                font=FONTS["subheading"],
                bg=color,
                fg="white"
            )
            lbl.pack()
            self.stats_labels[key] = lbl

    # ----------------------------------------------------------
    # LOAD & DISPLAY CUSTOMERS
    # ----------------------------------------------------------
    def _load_customers(self, search: str = ""):
        """Fetch and display customers from DB"""

        # Clear table
        for w in self.table_body.winfo_children():
            w.destroy()

        # Query
        if search:
            customers = db.query("""
                SELECT
                    c.*,
                    (SELECT COUNT(*)
                     FROM sales_bills sb
                     WHERE LOWER(sb.customer_name)
                           = LOWER(c.name)
                    ) AS bill_count
                FROM customers c
                WHERE c.is_auto_generated = 0
                AND LOWER(c.name) LIKE ?
                ORDER BY c.name
            """, (f"%{search.lower()}%",))
        else:
            customers = db.query("""
                SELECT
                    c.*,
                    (SELECT COUNT(*)
                     FROM sales_bills sb
                     WHERE LOWER(sb.customer_name)
                           = LOWER(c.name)
                    ) AS bill_count
                FROM customers c
                WHERE c.is_auto_generated = 0
                ORDER BY c.name
            """)

        # Update count
        self.count_label.configure(
            text=f"{len(customers)} customers found"
        )

        if not customers:
            msg = (
                "No customers found."
                if not search
                else f"No customers matching '{search}'"
            )
            tk.Label(
                self.table_body,
                text=msg + "\n\nClick '➕ Add Customer' "
                           "to add manually.\nOr use the "
                           "Name Generator →",
                font=FONTS["body"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"],
                justify="center"
            ).pack(pady=30)
        else:
            for i, c in enumerate(customers):
                self._render_customer_row(c, i)

        # Update stats
        self._update_stats()

    def _render_customer_row(
        self, customer: dict, idx: int
    ):
        """Render one customer row in table"""
        bg = (COLORS["row_even"]
              if idx % 2 == 0
              else COLORS["row_odd"])

        row = tk.Frame(self.table_body, bg=bg)
        row.pack(fill="x")

        data = [
            (str(idx + 1),              4),
            (customer["name"],         25),
            (customer.get("phone",""), 12),
            (customer.get("city", ""), 15),
            (str(customer.get(
                "bill_count", 0)),       6),
        ]

        for text, width in data:
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

        cid = customer["id"]

        tk.Button(
            act,
            text="✏️",
            font=FONTS["small"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=6, pady=3,
            cursor="hand2",
            command=lambda i=cid: self._edit_customer(i)
        ).pack(side="left", padx=2)

        tk.Button(
            act,
            text="🗑️",
            font=FONTS["small"],
            bg=COLORS["danger"],
            fg="white",
            relief="flat",
            padx=6, pady=3,
            cursor="hand2",
            command=lambda i=cid:
                self._delete_customer(i)
        ).pack(side="left", padx=2)

    def _update_stats(self):
        """Update monthly usage stat cards"""
        month = self.view_month.get()
        year  = self.view_year.get()

        # Total manual customers
        total = db.query_one("""
            SELECT COUNT(*) AS cnt
            FROM customers
            WHERE is_auto_generated = 0
        """)

        # Used this month
        used = db.query_one("""
            SELECT COUNT(DISTINCT customer_name) AS cnt
            FROM sales_bills
            WHERE bill_month=? AND bill_year=?
        """, (month, year))

        # Auto-generated saved
        auto = db.query_one("""
            SELECT COUNT(*) AS cnt
            FROM customers
            WHERE is_auto_generated = 1
        """)

        self.stats_labels["total_customers"].configure(
            text=str(total.get("cnt", 0))
        )
        self.stats_labels["used_this_month"].configure(
            text=str(used.get("cnt", 0))
        )
        self.stats_labels["manual_customers"].configure(
            text=str(total.get("cnt", 0))
        )
        self.stats_labels["auto_generated"].configure(
            text=str(auto.get("cnt", 0))
        )

    # ----------------------------------------------------------
    # NAME GENERATOR ACTIONS
    # ----------------------------------------------------------
    def _generate_names(self):
        """Generate batch of Karnataka names"""
        count = self.gen_count.get()
        month = self.view_month.get()
        year  = self.view_year.get()

        # Clear listbox
        self.names_listbox.delete(0, tk.END)

        # Refresh cache
        self.generator.refresh_cache(month, year)

        # Generate
        names = self.generator.generate_batch(
            count, month, year
        )

        for name in names:
            self.names_listbox.insert(tk.END, name)

        # Select all by default
        self.names_listbox.select_set(0, tk.END)

        # Update info
        month_name = MONTH_NAMES[month]
        self.gen_info_label.configure(
            text=f"Generated {count} names for "
                 f"{month_name} {year}.\n"
                 "These names are NOT yet used this month.\n"
                 "Select and save to customer database."
        )

    def _save_generated_names(self):
        """Save selected names from listbox to DB"""
        selected = self.names_listbox.curselection()
        if not selected:
            messagebox.showwarning(
                "Nothing Selected",
                "Please select names to save.\n"
                "Click on names in the list to select them."
            )
            return

        saved = 0
        for idx in selected:
            name = self.names_listbox.get(idx)
            city = self.generator.get_city()

            # Check if already exists
            existing = db.query_one("""
                SELECT id FROM customers
                WHERE LOWER(name)=?
            """, (name.lower(),))

            if not existing:
                db.execute("""
                    INSERT INTO customers
                    (name, city, is_auto_generated)
                    VALUES (?,?,1)
                """, (name, city))
                saved += 1

        self._load_customers()
        messagebox.showinfo(
            "Saved ✅",
            f"Saved {saved} customer names to database."
        )

    def _save_all_generated_names(self):
        """Save all generated names to DB"""
        count = self.names_listbox.size()
        if count == 0:
            messagebox.showwarning(
                "Empty",
                "Generate names first."
            )
            return

        self.names_listbox.select_set(0, tk.END)
        self._save_generated_names()

    # ----------------------------------------------------------
    # CRUD ACTIONS
    # ----------------------------------------------------------
    def _open_add_dialog(self):
        CustomerDialog(
            self,
            on_save_callback=self._load_customers
        )

    def _edit_customer(self, customer_id: int):
        CustomerDialog(
            self,
            edit_customer_id=customer_id,
            on_save_callback=self._load_customers
        )

    def _delete_customer(self, customer_id: int):
        customer = db.query_one("""
            SELECT * FROM customers WHERE id=?
        """, (customer_id,))

        if not customer:
            return

        # Check if used in any bills
        used = db.query_one("""
            SELECT COUNT(*) AS cnt
            FROM sales_bills
            WHERE LOWER(customer_name)=?
        """, (customer["name"].lower(),))

        if used.get("cnt", 0) > 0:
            if not messagebox.askyesno(
                "Customer In Use",
                f"'{customer['name']}' has been used in "
                f"{used['cnt']} sales bills.\n\n"
                "Deleting won't affect existing bills.\n"
                "Continue?"
            ):
                return
        else:
            if not messagebox.askyesno(
                "Delete Customer",
                f"Delete '{customer['name']}'?\n"
                "This cannot be undone."
            ):
                return

        db.execute("""
            DELETE FROM customers WHERE id=?
        """, (customer_id,))

        self.app.set_status(
            f"Customer deleted", "warning"
        )
        self._load_customers()

    # ----------------------------------------------------------
    # SEARCH
    # ----------------------------------------------------------
    def _on_search_change(self):
        """Filter customers as user types"""
        search = self.search_var.get().strip()
        self._load_customers(search)

    # ----------------------------------------------------------
    # IMPORT / EXPORT
    # ----------------------------------------------------------
    def _import_csv(self):
        """Import customers from CSV file"""
        path = filedialog.askopenfilename(
            title="Select Customer CSV",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        try:
            imported = 0
            skipped  = 0

            with open(
                path, "r", encoding="utf-8-sig"
            ) as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Normalize keys
                    row_data = {
                        k.lower().strip(): v.strip()
                        for k, v in row.items()
                    }

                    name = (
                        row_data.get("name") or
                        row_data.get("customer_name") or
                        row_data.get("customer") or ""
                    ).strip()

                    if not name:
                        skipped += 1
                        continue

                    # Check duplicate
                    existing = db.query_one("""
                        SELECT id FROM customers
                        WHERE LOWER(name)=?
                    """, (name.lower(),))

                    if existing:
                        skipped += 1
                        continue

                    phone = (
                        row_data.get("phone") or
                        row_data.get("mobile") or
                        row_data.get("contact") or ""
                    )
                    city  = (
                        row_data.get("city") or
                        row_data.get("town") or ""
                    )
                    addr  = (
                        row_data.get("address") or
                        row_data.get("addr") or ""
                    )

                    db.execute("""
                        INSERT INTO customers
                        (name, phone, city, address,
                         is_auto_generated)
                        VALUES (?,?,?,?,0)
                    """, (name, phone, city, addr))
                    imported += 1

            self._load_customers()
            messagebox.showinfo(
                "Import Complete ✅",
                f"Imported: {imported} customers\n"
                f"Skipped (duplicate/empty): {skipped}"
            )

        except Exception as e:
            messagebox.showerror(
                "Import Error",
                f"Could not import CSV.\n\n{e}\n\n"
                "Expected columns: name, phone, city, address"
            )

    def _export_csv(self):
        """Export all manual customers to CSV"""
        path = filedialog.asksaveasfilename(
            title="Save Customer List",
            defaultextension=".csv",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ],
            initialfile="customers_export.csv"
        )

        if not path:
            return

        try:
            customers = db.query("""
                SELECT name, phone, city, address
                FROM customers
                WHERE is_auto_generated = 0
                ORDER BY name
            """)

            with open(
                path, "w", newline="",
                encoding="utf-8-sig"
            ) as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "name", "phone",
                        "city", "address"
                    ]
                )
                writer.writeheader()
                writer.writerows(customers)

            messagebox.showinfo(
                "Export Complete ✅",
                f"Exported {len(customers)} customers to:\n"
                f"{path}"
            )

            # Open file location
            import os
            os.startfile(str(Path(path).parent))

        except Exception as e:
            messagebox.showerror(
                "Export Error",
                f"Could not export.\n\n{e}"
            )