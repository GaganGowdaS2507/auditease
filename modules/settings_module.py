# modules/settings_module.py
# ============================================================
# SETTINGS MODULE — COMPLETE FIXED VERSION
# Combines all features from original + save fix
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import re
import sqlite3
from pathlib import Path

# ============================================================
# PATHS
# ============================================================
BASE_DIR    = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "settings.json"
ASSETS_DIR  = BASE_DIR / "assets"
DB_PATH     = BASE_DIR / "database" / "shop_database.db"

# ============================================================
# COLORS & FONTS
# ============================================================
COLORS = {
    "primary":       "#1a237e",
    "primary_light": "#3949ab",
    "accent":        "#ff6f00",
    "success":       "#2e7d32",
    "warning":       "#f57f17",
    "danger":        "#c62828",
    "bg_main":       "#f5f5f5",
    "bg_card":       "#ffffff",
    "text_dark":     "#212121",
    "text_light":    "#ffffff",
    "text_muted":    "#757575",
    "border":        "#e0e0e0",
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
}


# ============================================================
# LOAD / SAVE SETTINGS — FIXED
# ============================================================
def load_settings() -> dict:
    """
    Load settings from JSON file.
    AUTO-CREATES file with defaults if missing.
    Never crashes even if file is corrupt.
    """
    # Ensure config folder exists
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        default = _default_settings()
        _write_settings(default)
        return default

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with defaults to fill any missing keys
            return _merge_with_defaults(data)
    except Exception as e:
        print(f"[Settings] Load error: {e}")
        default = _default_settings()
        _write_settings(default)
        return default


def save_settings(data: dict) -> bool:
    """
    Save settings to JSON file.
    Returns True on success, False on failure.
    """
    try:
        CONFIG_PATH.parent.mkdir(
            parents=True, exist_ok=True
        )
        _write_settings(data)
        print(f"[Settings] Saved to: {CONFIG_PATH}")
        return True
    except Exception as e:
        print(f"[Settings] Save error: {e}")
        return False


def _write_settings(data: dict):
    """Write settings dict to JSON file"""
    with open(
        CONFIG_PATH, "w", encoding="utf-8"
    ) as f:
        json.dump(data, f, indent=4,
                  ensure_ascii=False)


def _default_settings() -> dict:
    """Return complete default settings"""
    bills_folder = str(BASE_DIR / "bills")
    db_path      = str(
        BASE_DIR / "database" / "shop_database.db"
    )
    return {
        "shop": {
            "name":          "",
            "owner_name":    "",
            "address_line1": "",
            "address_line2": "",
            "city":          "",
            "state":         "Karnataka",
            "pincode":       "",
            "phone":         "",
            "email":         "",
            "gstin":         "",
            "state_code":    "29",
            "pan":           ""
        },
        "billing": {
            "tax_scheme":            "regular",
            "bill_prefix":           "INV",
            "bill_start_number":     1,
            "current_bill_number":   1,
            "bill_year":             2026,
            "default_margin_type":   "range",
            "default_margin_min":    10,
            "default_margin_max":    20,
            "default_margin_global": 15,
            "flat_markup_amount":    5,
            "target_profit_amount":  0
        },
        "print": {
            "paper_size":      "both",
            "thermal_width_mm": 80,
            "printer_name":    ""
        },
        "storage": {
            "bills_root_folder": bills_folder,
            "database_path":     db_path,
            "backup_enabled":    True
        },
        "bank": {
            "bank_name":    "",
            "account_name": "",
            "account_no":   "",
            "ifsc":         "",
            "branch":       ""
        },
        "app": {
            "setup_complete": False,
            "version":        "1.0.0"
        }
    }


def _merge_with_defaults(data: dict) -> dict:
    """
    Merge loaded settings with defaults.
    Fills any keys that are missing in the file.
    """
    defaults = _default_settings()
    for section, values in defaults.items():
        if section not in data:
            data[section] = values
        elif isinstance(values, dict):
            for key, val in values.items():
                if key not in data[section]:
                    data[section][key] = val
    return data


# ============================================================
# REUSABLE UI COMPONENTS
# ============================================================
def make_card(
    parent, title: str, color: str = None
) -> tk.Frame:
    """Create a white card section with colored title bar"""
    outer = tk.Frame(parent, bg=COLORS["bg_main"])
    outer.pack(fill="x", padx=25, pady=8)

    # Shadow effect
    shadow = tk.Frame(outer, bg="#d0d0d0")
    shadow.pack(
        fill="both", expand=True,
        padx=(2, 0), pady=(2, 0)
    )

    card = tk.Frame(
        shadow,
        bg=COLORS["bg_card"],
        padx=20, pady=15
    )
    card.pack(fill="both", expand=True)

    # Color bar at top
    tk.Frame(
        card,
        bg=color if color else COLORS["primary"],
        height=4
    ).pack(fill="x", pady=(0, 12))

    tk.Label(
        card,
        text=title,
        font=FONTS["subheading"],
        bg=COLORS["bg_card"],
        fg=COLORS["text_dark"]
    ).pack(anchor="w", pady=(0, 10))

    content = tk.Frame(card, bg=COLORS["bg_card"])
    content.pack(fill="x")
    return content


# ============================================================
# SETTINGS FRAME — MAIN CLASS
# ============================================================
class SettingsFrame(tk.Frame):
    """
    Complete Settings UI.

    Tabs:
    1. Shop Details  — name, address, contact
    2. GST Details   — GSTIN, scheme
    3. Billing       — prefix, margin, paper
    4. Storage       — bills folder path
    5. Bank Details  — for bill footer
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS["bg_main"])
        self.app      = app
        self.settings = load_settings()
        self.vars     = {}

        self._build_ui()
        self._load_values()

    # ----------------------------------------------------------
    # BUILD MAIN UI
    # ----------------------------------------------------------
    def _build_ui(self):
        self._build_top_bar()
        self._build_tabs()

    def _build_top_bar(self):
        """Title + Save button bar"""
        top = tk.Frame(self, bg=COLORS["bg_main"])
        top.pack(fill="x", padx=25, pady=(20, 5))

        tk.Label(
            top,
            text="⚙️  Shop Settings",
            font=FONTS["heading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(side="left")

        tk.Label(
            top,
            text="Configure your shop details "
                 "and billing preferences",
            font=FONTS["body"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_muted"]
        ).pack(side="left", padx=(15, 0), pady=(8, 0))

        # Top action buttons
        btn_box = tk.Frame(top, bg=COLORS["bg_main"])
        btn_box.pack(side="right")

        tk.Button(
            btn_box,
            text="🗑️  Reset All Data",
            font=FONTS["button"],
            bg=COLORS["danger"],
            fg="white",
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._clear_all_data
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btn_box,
            text="💾  Save All Settings",
            font=FONTS["button"],
            bg=COLORS["success"],
            fg="white",
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=self._save_all
        ).pack(side="left")

    def _build_tabs(self):
        """Tab buttons + content area"""
        tab_bar = tk.Frame(self, bg=COLORS["bg_main"])
        tab_bar.pack(fill="x", padx=25, pady=(5, 0))

        self.tab_buttons = {}
        self.tab_frames  = {}

        tabs = [
            ("shop",    "🏪 Shop Details"),
            ("gst",     "📋 GST Details"),
            ("billing", "🧾 Billing Preferences"),
            ("storage", "📁 Storage Settings"),
            ("bank",    "🏦 Bank Details"),
        ]

        for key, label in tabs:
            btn = tk.Button(
                tab_bar,
                text=label,
                font=FONTS["label_bold"],
                relief="flat",
                padx=15,
                pady=8,
                cursor="hand2",
                command=lambda k=key:
                    self._switch_tab(k)
            )
            btn.pack(side="left", padx=(0, 3))
            self.tab_buttons[key] = btn

        # Blue separator line
        tk.Frame(
            self,
            bg=COLORS["primary"],
            height=2
        ).pack(fill="x", padx=25)

        # Build scrollable content area
        self._build_scroll_area()

        # Build all tab frames
        self._build_shop_tab()
        self._build_gst_tab()
        self._build_billing_tab()
        self._build_storage_tab()
        self._build_bank_tab()

        # Show default tab
        self._switch_tab("shop")

    def _build_scroll_area(self):
        """Scrollable canvas for tab content"""
        outer = tk.Frame(self, bg=COLORS["bg_main"])
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            outer,
            bg=COLORS["bg_main"],
            highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(
            outer,
            orient="vertical",
            command=self.canvas.yview
        )
        self.canvas.configure(
            yscrollcommand=scrollbar.set
        )

        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(
            side="left", fill="both", expand=True
        )

        self.scroll_frame = tk.Frame(
            self.canvas,
            bg=COLORS["bg_main"]
        )
        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.scroll_frame,
            anchor="nw"
        )

        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(
                self.canvas_window, width=e.width
            )
        )
        self.canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"
            )
        )

    # ----------------------------------------------------------
    # TAB SWITCHING
    # ----------------------------------------------------------
    def _switch_tab(self, tab_key: str):
        """Highlight active tab and show its frame"""
        for key, btn in self.tab_buttons.items():
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

        for key, frame in self.tab_frames.items():
            if key == tab_key:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        self.canvas.yview_moveto(0)

    # ----------------------------------------------------------
    # HELPER: Create entry field in grid
    # ----------------------------------------------------------
    def _make_entry_row(
        self,
        parent,
        var_key:  str,
        label:    str,
        row:      int,
        width:    int = 30,
        hint:     str = "",
        required: bool = False,
        col:      int = 0
    ) -> tk.Entry:
        """
        Create label + entry field pair in grid.
        Stores StringVar in self.vars[var_key].
        Returns the Entry widget.
        """
        self.vars[var_key] = tk.StringVar()

        lbl_text = f"{label} *" if required else label
        tk.Label(
            parent,
            text=lbl_text,
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=(COLORS["primary"]
                if required
                else COLORS["text_dark"])
        ).grid(
            row=row, column=col,
            sticky="w", padx=(0, 15), pady=6
        )

        entry = tk.Entry(
            parent,
            textvariable=self.vars[var_key],
            font=FONTS["body"],
            width=width,
            relief="solid",
            bd=1,
            bg="#fafafa"
        )
        entry.grid(
            row=row, column=col + 1,
            sticky="w", pady=6
        )

        if hint:
            tk.Label(
                parent,
                text=hint,
                font=FONTS["small"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_muted"]
            ).grid(
                row=row, column=col + 2,
                sticky="w", padx=(10, 0), pady=6
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

        return entry

    # ----------------------------------------------------------
    # TAB 1: SHOP DETAILS
    # ----------------------------------------------------------
    def _build_shop_tab(self):
        """Shop name, address, contact details"""
        frame = tk.Frame(
            self.scroll_frame,
            bg=COLORS["bg_main"]
        )
        self.tab_frames["shop"] = frame

        # Card 1 — Basic Info
        card1 = make_card(
            frame,
            "🏪 Shop Basic Information",
            COLORS["primary"]
        )

        self._make_entry_row(
            card1, "shop_name", "Shop Name *", 0,
            width=35,
            hint="e.g. Sri Manjunath Hardware",
            required=True
        )
        self._make_entry_row(
            card1, "owner_name", "Owner Name *", 1,
            width=35,
            hint="e.g. Basavaraj Patil",
            required=True
        )
        self._make_entry_row(
            card1, "phone", "Phone Number *", 2,
            width=20,
            hint="10 digit mobile number",
            required=True
        )
        self._make_entry_row(
            card1, "email",
            "Email (optional)", 3,
            width=30,
            hint="e.g. shop@gmail.com"
        )

        # Card 2 — Address
        card2 = make_card(
            frame,
            "📍 Shop Address",
            COLORS["primary_light"]
        )

        self._make_entry_row(
            card2, "address_line1",
            "Address Line 1 *", 0,
            width=40,
            hint="Shop number, Street name",
            required=True
        )
        self._make_entry_row(
            card2, "address_line2",
            "Address Line 2", 1,
            width=40,
            hint="Area, Landmark (optional)"
        )
        self._make_entry_row(
            card2, "city", "City / Town *", 2,
            width=25,
            hint="e.g. Hubli",
            required=True
        )
        self._make_entry_row(
            card2, "pincode", "PIN Code *", 3,
            width=10,
            hint="e.g. 580001",
            required=True
        )

        # State — fixed Karnataka
        tk.Label(
            card2,
            text="State",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).grid(
            row=4, column=0,
            sticky="w", padx=(0, 15), pady=6
        )
        tk.Label(
            card2,
            text="✅  Karnataka  (State Code: 29)  — Fixed",
            font=FONTS["body"],
            bg=COLORS["bg_card"],
            fg=COLORS["success"]
        ).grid(row=4, column=1, sticky="w", pady=6)

    # ----------------------------------------------------------
    # TAB 2: GST DETAILS
    # ----------------------------------------------------------
    def _build_gst_tab(self):
        """GSTIN entry + validation + tax scheme"""
        frame = tk.Frame(
            self.scroll_frame,
            bg=COLORS["bg_main"]
        )
        self.tab_frames["gst"] = frame

        # Card 1 — GST Registration
        card = make_card(
            frame,
            "📋 GST Registration Details",
            COLORS["primary"]
        )

        # GSTIN
        tk.Label(
            card,
            text="GSTIN *",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["primary"]
        ).grid(
            row=0, column=0,
            sticky="w", padx=(0, 15), pady=8
        )

        self.vars["gstin"] = tk.StringVar()
        gstin_entry = tk.Entry(
            card,
            textvariable=self.vars["gstin"],
            font=("Courier New", 12),
            width=18,
            relief="solid",
            bd=1,
            bg="#fafafa"
        )
        gstin_entry.grid(
            row=0, column=1, sticky="w", pady=8
        )
        gstin_entry.bind(
            "<FocusIn>",
            lambda e: gstin_entry.configure(
                bg="white", bd=2
            )
        )
        gstin_entry.bind(
            "<FocusOut>",
            lambda e: gstin_entry.configure(
                bg="#fafafa", bd=1
            )
        )

        tk.Label(
            card,
            text="Format: 29XXXXXXXXXXX1Z5  "
                 "(29 = Karnataka)",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        ).grid(
            row=0, column=2,
            sticky="w", padx=(10, 0)
        )

        # Validate button
        tk.Button(
            card,
            text="✓ Validate",
            font=FONTS["small"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=8, pady=4,
            cursor="hand2",
            command=self._validate_gstin
        ).grid(row=0, column=3, padx=(10, 0), pady=8)

        # Validation result label
        self.gstin_status_label = tk.Label(
            card,
            text="",
            font=FONTS["small"],
            bg=COLORS["bg_card"]
        )
        self.gstin_status_label.grid(
            row=1, column=1, columnspan=2,
            sticky="w", pady=(0, 5)
        )

        # PAN
        self._make_entry_row(
            card, "pan",
            "PAN Number", 2,
            width=15,
            hint="e.g. ABCDE1234F"
        )

        # Card 2 — Tax Scheme
        card2 = make_card(
            frame, "💼 Tax Scheme",
            COLORS["accent"]
        )

        self.vars["tax_scheme"] = tk.StringVar(
            value="regular"
        )

        # Regular GST
        reg_frame = tk.Frame(card2, bg=COLORS["bg_card"])
        reg_frame.grid(
            row=0, column=0, columnspan=3,
            sticky="w", pady=5
        )
        tk.Radiobutton(
            reg_frame,
            text="Regular GST",
            variable=self.vars["tax_scheme"],
            value="regular",
            font=FONTS["body_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            activebackground=COLORS["bg_card"],
            command=self._on_scheme_change
        ).pack(side="left")
        tk.Label(
            reg_frame,
            text="  →  Bill shows CGST + SGST separately. "
                 "Input Tax Credit available.",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        ).pack(side="left")

        # Composition
        comp_frame = tk.Frame(
            card2, bg=COLORS["bg_card"]
        )
        comp_frame.grid(
            row=1, column=0, columnspan=3,
            sticky="w", pady=5
        )
        tk.Radiobutton(
            comp_frame,
            text="Composition Scheme",
            variable=self.vars["tax_scheme"],
            value="composition",
            font=FONTS["body_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            activebackground=COLORS["bg_card"],
            command=self._on_scheme_change
        ).pack(side="left")
        tk.Label(
            comp_frame,
            text="  →  No tax on bill. Flat 1% on turnover. "
                 "No Input Tax Credit.",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        ).pack(side="left")

        # Scheme info box
        self.scheme_info = tk.Label(
            card2,
            text="",
            font=FONTS["label"],
            bg="#e8f5e9",
            fg=COLORS["success"],
            wraplength=600,
            justify="left",
            padx=10, pady=8
        )
        self.scheme_info.grid(
            row=2, column=0, columnspan=3,
            sticky="w", pady=(10, 0)
        )
        self._on_scheme_change()

    def _validate_gstin(self):
        """Validate GSTIN format for Karnataka"""
        gstin = self.vars["gstin"].get().strip().upper()
        self.vars["gstin"].set(gstin)

        pattern = (
            r'^29[A-Z]{5}[0-9]{4}[A-Z]'
            r'[1-9A-Z]Z[0-9A-Z]$'
        )

        if not gstin:
            self.gstin_status_label.configure(
                text="⚠️  GSTIN is required",
                fg=COLORS["warning"]
            )
        elif re.match(pattern, gstin):
            self.gstin_status_label.configure(
                text="✅  Valid Karnataka GSTIN format",
                fg=COLORS["success"]
            )
        elif not gstin.startswith("29"):
            self.gstin_status_label.configure(
                text="❌  Must start with 29 "
                     "(Karnataka state code)",
                fg=COLORS["danger"]
            )
        else:
            self.gstin_status_label.configure(
                text="❌  Invalid GSTIN format. "
                     "Expected: 29XXXXXXXXXXX1Z5",
                fg=COLORS["danger"]
            )

    def _on_scheme_change(self):
        """Update info box when scheme changes"""
        scheme = self.vars["tax_scheme"].get()
        if scheme == "regular":
            self.scheme_info.configure(
                text="ℹ️  Regular GST: Bills will show "
                     "CGST and SGST breakup. "
                     "You can claim Input Tax Credit "
                     "on purchases. "
                     "File GSTR-1 and GSTR-3B monthly.",
                bg="#e8f5e9",
                fg=COLORS["success"]
            )
        else:
            self.scheme_info.configure(
                text="ℹ️  Composition Scheme: Bills will "
                     "NOT show tax amount. "
                     "Mandatory footer: 'Composition "
                     "taxable person, not eligible to "
                     "collect tax on supplies'. "
                     "Pay 1% of quarterly turnover. "
                     "File CMP-08 quarterly.",
                bg="#fff3e0",
                fg=COLORS["warning"]
            )

    # ----------------------------------------------------------
    # TAB 3: BILLING PREFERENCES
    # ----------------------------------------------------------
    def _build_billing_tab(self):
        """Bill number, margin, paper size"""
        frame = tk.Frame(
            self.scroll_frame,
            bg=COLORS["bg_main"]
        )
        self.tab_frames["billing"] = frame

        # Card 1 — Bill Number Settings
        card = make_card(
            frame,
            "🔢 Bill Number Settings",
            COLORS["primary"]
        )

        self._make_entry_row(
            card, "bill_prefix",
            "Bill Prefix", 0,
            width=10,
            hint="Bills: INV-2026-0001, INV-2026-0002..."
        )
        self._make_entry_row(
            card, "bill_start_number",
            "Starting Bill Number", 1,
            width=10,
            hint="Use 1 for new year. "
                 "Use higher if continuing from manual."
        )

        # Card 2 — Profit Margin / Flat Markup
        card2 = make_card(
            frame,
            "💰 Selling Rate Settings (Composition Scheme)",
            COLORS["success"]
        )

        # Flat markup row (₹5 on purchase rate)
        tk.Label(
            card2,
            text="Flat Markup per Item (₹)",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).grid(row=0, column=0, sticky="w", padx=(0, 15), pady=8)

        self.vars["flat_markup_amount"] = tk.StringVar(value="5")
        tk.Entry(
            card2,
            textvariable=self.vars["flat_markup_amount"],
            font=FONTS["body"],
            width=8,
            relief="solid", bd=1
        ).grid(row=0, column=1, sticky="w", pady=8)
        tk.Label(
            card2,
            text="Selling Rate = Purchase Rate + this amount  "
                 "(No GST — Composition Scheme)",
            font=FONTS["hint"] if "hint" in FONTS else FONTS["label"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"] if "text_muted" in COLORS else COLORS["text_dark"]
        ).grid(row=0, column=2, sticky="w", padx=(5,0), pady=8)

        tk.Label(
            card2,
            text="Margin Type",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).grid(
            row=0, column=0,
            sticky="w", padx=(0, 15), pady=8
        )

        self.vars["margin_type"] = tk.StringVar(
            value="range"
        )

        margin_radio_frame = tk.Frame(
            card2, bg=COLORS["bg_card"]
        )
        margin_radio_frame.grid(
            row=0, column=1, columnspan=2,
            sticky="w", pady=8
        )

        margin_options = {
            "range":
                "Random Range  "
                "(Recommended — most natural)",
            "global":
                "Fixed Global % "
                "(Same margin for all items)",
            "flat":
                "Fixed Rupee Markup  "
                "(Purchase Rate + ₹X)",
            "target_profit":
                "Target Profit ₹  "
                "(Set exact desired total profit in ₹)",
            "itemwise":
                "Item-wise %   "
                "(Set per item while entering bill)",
        }

        for value, label in margin_options.items():
            tk.Radiobutton(
                margin_radio_frame,
                text=label,
                variable=self.vars["margin_type"],
                value=value,
                font=FONTS["label"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_dark"],
                activebackground=COLORS["bg_card"],
                command=self._on_margin_type_change
            ).pack(anchor="w", pady=3)

        # Range frame
        self.range_frame = tk.Frame(
            card2, bg="#e8f5e9",
            padx=15, pady=10
        )
        self.range_frame.grid(
            row=1, column=0, columnspan=3,
            sticky="w", pady=5
        )

        tk.Label(
            self.range_frame,
            text="Minimum Margin %",
            font=FONTS["label_bold"],
            bg="#e8f5e9",
            fg=COLORS["text_dark"]
        ).grid(
            row=0, column=0,
            sticky="w", padx=(0, 15), pady=5
        )

        self.vars["margin_min"] = tk.StringVar(
            value="10"
        )
        tk.Entry(
            self.range_frame,
            textvariable=self.vars["margin_min"],
            font=FONTS["body"],
            width=8,
            relief="solid", bd=1
        ).grid(row=0, column=1, sticky="w", pady=5)

        tk.Label(
            self.range_frame,
            text="Maximum Margin %",
            font=FONTS["label_bold"],
            bg="#e8f5e9",
            fg=COLORS["text_dark"]
        ).grid(
            row=0, column=2,
            sticky="w", padx=(20, 15), pady=5
        )

        self.vars["margin_max"] = tk.StringVar(
            value="20"
        )
        tk.Entry(
            self.range_frame,
            textvariable=self.vars["margin_max"],
            font=FONTS["body"],
            width=8,
            relief="solid", bd=1
        ).grid(row=0, column=3, sticky="w", pady=5)

        tk.Label(
            self.range_frame,
            text="System randomly assigns margin between "
                 "min and max for each item.\n"
                 "Example: Cement 13%, Pipes 18% "
                 "— looks natural.",
            font=FONTS["small"],
            bg="#e8f5e9",
            fg=COLORS["success"]
        ).grid(
            row=1, column=0, columnspan=4,
            sticky="w", pady=(5, 0)
        )

        # Global margin frame
        self.global_frame = tk.Frame(
            card2, bg="#e3f2fd",
            padx=15, pady=10
        )
        self.global_frame.grid(
            row=2, column=0, columnspan=3,
            sticky="w", pady=5
        )

        tk.Label(
            self.global_frame,
            text="Global Margin %",
            font=FONTS["label_bold"],
            bg="#e3f2fd",
            fg=COLORS["text_dark"]
        ).grid(
            row=0, column=0,
            sticky="w", padx=(0, 15), pady=5
        )

        self.vars["margin_global"] = tk.StringVar(
            value="15"
        )
        tk.Entry(
            self.global_frame,
            textvariable=self.vars["margin_global"],
            font=FONTS["body"],
            width=8,
            relief="solid", bd=1
        ).grid(row=0, column=1, sticky="w", pady=5)

        tk.Label(
            self.global_frame,
            text="Same % applied to all items in all bills",
            font=FONTS["small"],
            bg="#e3f2fd",
            fg=COLORS["text_muted"]
        ).grid(
            row=0, column=2,
            sticky="w", padx=(10, 0)
        )

        # Flat markup frame
        self.flat_frame = tk.Frame(
            card2, bg="#fff8e1",
            padx=15, pady=10
        )
        self.flat_frame.grid(
            row=3, column=0, columnspan=3,
            sticky="w", pady=5
        )

        tk.Label(
            self.flat_frame,
            text="Flat Markup ₹",
            font=FONTS["label_bold"],
            bg="#fff8e1",
            fg=COLORS["text_dark"]
        ).grid(
            row=0, column=0,
            sticky="w", padx=(0, 15), pady=5
        )

        self.vars["flat_markup_amount"] = tk.StringVar(
            value="5"
        )
        tk.Entry(
            self.flat_frame,
            textvariable=self.vars["flat_markup_amount"],
            font=FONTS["body"],
            width=8,
            relief="solid", bd=1
        ).grid(row=0, column=1, sticky="w", pady=5)

        tk.Label(
            self.flat_frame,
            text="Fixed ₹ amount added to purchase rate for each item",
            font=FONTS["small"],
            bg="#fff8e1",
            fg=COLORS["text_muted"]
        ).grid(
            row=0, column=2,
            sticky="w", padx=(10, 0)
        )

        # Target profit frame
        self.target_profit_frame = tk.Frame(
            card2, bg="#ede7f6",
            padx=15, pady=10
        )
        self.target_profit_frame.grid(
            row=4, column=0, columnspan=3,
            sticky="w", pady=5
        )

        tk.Label(
            self.target_profit_frame,
            text="Target Profit ₹",
            font=FONTS["label_bold"],
            bg="#ede7f6",
            fg=COLORS["text_dark"]
        ).grid(
            row=0, column=0,
            sticky="w", padx=(0, 15), pady=5
        )

        self.vars["target_profit_amount"] = tk.StringVar(
            value="0"
        )
        tk.Entry(
            self.target_profit_frame,
            textvariable=self.vars["target_profit_amount"],
            font=FONTS["body"],
            width=10,
            relief="solid", bd=1
        ).grid(row=0, column=1, sticky="w", pady=5)

        tk.Label(
            self.target_profit_frame,
            text="Desired monthly sales profit in ₹ (exact total achieved)",
            font=FONTS["small"],
            bg="#ede7f6",
            fg=COLORS["text_muted"]
        ).grid(
            row=0, column=2,
            sticky="w", padx=(10, 0)
        )

        self._on_margin_type_change()

        # Card 3 — Paper Size
        card3 = make_card(
            frame,
            "🖨️ Bill Paper Size",
            COLORS["primary_light"]
        )

        self.vars["paper_size"] = tk.StringVar(
            value="both"
        )

        paper_options = [
            ("a4",
             "A4 Size  (Full page — professional)"),
            ("thermal",
             "Thermal Receipt  (80mm roll printer)"),
            ("both",
             "Both  (Generate both formats)"),
        ]

        for value, label in paper_options:
            tk.Radiobutton(
                card3,
                text=label,
                variable=self.vars["paper_size"],
                value=value,
                font=FONTS["label"],
                bg=COLORS["bg_card"],
                fg=COLORS["text_dark"],
                activebackground=COLORS["bg_card"]
            ).pack(anchor="w", pady=4)

    def _on_margin_type_change(self):
        """Show/hide margin config frames"""
        mtype = self.vars["margin_type"].get()

        # Range frame — enable for range/itemwise
        for child in self.range_frame.winfo_children():
            try:
                child.configure(
                    state="normal"
                    if mtype in ("range", "itemwise")
                    else "disabled"
                )
            except Exception:
                pass

        # Global frame — enable only for global
        for child in self.global_frame.winfo_children():
            try:
                child.configure(
                    state="normal"
                    if mtype == "global"
                    else "disabled"
                )
            except Exception:
                pass

        # Flat frame — enable only for flat
        if hasattr(self, "flat_frame"):
            for child in self.flat_frame.winfo_children():
                try:
                    child.configure(
                        state="normal"
                        if mtype == "flat"
                        else "disabled"
                    )
                except Exception:
                    pass

        # Target profit frame — enable only for target_profit
        if hasattr(self, "target_profit_frame"):
            for child in self.target_profit_frame.winfo_children():
                try:
                    child.configure(
                        state="normal"
                        if mtype == "target_profit"
                        else "disabled"
                    )
                except Exception:
                    pass

    # ----------------------------------------------------------
    # TAB 4: STORAGE SETTINGS
    # ----------------------------------------------------------
    def _build_storage_tab(self):
        """Bills folder path setting"""
        frame = tk.Frame(
            self.scroll_frame,
            bg=COLORS["bg_main"]
        )
        self.tab_frames["storage"] = frame

        card = make_card(
            frame,
            "📁 Bills Storage Location",
            COLORS["primary"]
        )

        tk.Label(
            card,
            text="Bills Root Folder",
            font=FONTS["label_bold"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"]
        ).grid(
            row=0, column=0,
            sticky="w", padx=(0, 15), pady=8
        )

        self.vars["bills_folder"] = tk.StringVar()
        path_entry = tk.Entry(
            card,
            textvariable=self.vars["bills_folder"],
            font=FONTS["body"],
            width=45,
            relief="solid", bd=1,
            bg="#fafafa"
        )
        path_entry.grid(
            row=0, column=1, sticky="w", pady=8
        )

        tk.Button(
            card,
            text="📂 Browse",
            font=FONTS["label_bold"],
            bg=COLORS["primary_light"],
            fg="white",
            relief="flat",
            padx=10, pady=5,
            cursor="hand2",
            command=self._browse_folder
        ).grid(row=0, column=2, padx=(10, 0), pady=8)

        # Folder structure preview
        tk.Label(
            card,
            text="📁 Selected Folder\n"
                 "  └── 📁 2026\n"
                 "       └── 📁 06_June\n"
                 "            ├── 📁 Purchases\n"
                 "            │    └── uploaded bills\n"
                 "            ├── 📁 Sales\n"
                 "            │    └── generated bills\n"
                 "            └── 📁 Reports\n"
                 "                 └── monthly reports",
            font=("Courier", 10),
            bg="#f5f5f5",
            fg=COLORS["text_dark"],
            justify="left",
            padx=15, pady=10
        ).grid(
            row=1, column=0, columnspan=3,
            sticky="w", pady=(10, 0)
        )

        tk.Button(
            card,
            text="📂 Open Bills Folder",
            font=FONTS["label_bold"],
            bg=COLORS["accent"],
            fg="white",
            relief="flat",
            padx=12, pady=6,
            cursor="hand2",
            command=self._open_bills_folder
        ).grid(
            row=2, column=0, columnspan=3,
            sticky="w", pady=(15, 5)
        )

        # Card 2 — Danger Zone / Full Reset
        card_reset = make_card(
            frame,
            "⚠️ Database & Test Data Reset",
            COLORS["danger"]
        )

        tk.Label(
            card_reset,
            text="Completely clear all previous transactions, purchase bills, sales bills, and reset invoice numbering.\n"
                 "Use this whenever you want to test with a clean slate.\n\n"
                 "• Clears: Purchase Bills, Sales Bills, Monthly Summaries, Auto-generated Customers, Item Master entries.\n"
                 "• Resets: Sales invoice sequence counter back to #1.\n"
                 "• Preserves: Shop profile, GST configuration, Bank accounts, and Billing preferences.",
            font=FONTS["body"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_dark"],
            justify="left"
        ).grid(
            row=0, column=0, columnspan=3,
            sticky="w", pady=(0, 15)
        )

        tk.Button(
            card_reset,
            text="🗑️ Reset & Clear All Data",
            font=FONTS["button"],
            bg=COLORS["danger"],
            fg="white",
            relief="flat",
            padx=18, pady=10,
            cursor="hand2",
            command=self._clear_all_data
        ).grid(
            row=1, column=0,
            sticky="w", pady=(0, 5)
        )

    def _browse_folder(self):
        """Open folder browser"""
        folder = filedialog.askdirectory(
            title="Select Bills Storage Folder",
            initialdir=str(BASE_DIR)
        )
        if folder:
            self.vars["bills_folder"].set(folder)

    def _open_bills_folder(self):
        """Open bills folder in file explorer"""
        folder = self.vars["bills_folder"].get()
        if folder and os.path.exists(folder):
            os.startfile(folder)
        else:
            messagebox.showwarning(
                "Folder Not Found",
                "Bills folder does not exist yet.\n"
                "Save settings first."
            )

    def _clear_all_data(self):
        """Completely reset all transaction data, purchase/sales bills, inventory, and counters for testing."""
        confirmed = messagebox.askyesno(
            "Confirm Full Data Reset",
            "Are you sure you want to completely clear all previous transaction data?\n\n"
            "This will permanently delete:\n"
            " • All Purchase Bills and line items\n"
            " • All Sales Bills and line items\n"
            " • All Monthly Summaries\n"
            " • Auto-generated customer records\n"
            " • Auto-learned Item Master catalog entries\n"
            " • Uploaded and generated bill files in storage\n"
            " • Reset sales invoice numbering back to #1\n\n"
            "Shop Settings, GST profile, and Bank Details will NOT be deleted.\n\n"
            "Proceed with the reset?",
            icon="warning"
        )
        if not confirmed:
            return

        try:
            # 1. Clean Database
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("BEGIN TRANSACTION")
            cur.execute("DELETE FROM sales_items")
            cur.execute("DELETE FROM sales_bills")
            cur.execute("DELETE FROM purchase_items")
            cur.execute("DELETE FROM purchase_bills")
            cur.execute("DELETE FROM monthly_summary")
            cur.execute("DELETE FROM bill_number_tracker")
            cur.execute("DELETE FROM customers WHERE is_auto_generated = 1")
            cur.execute("DELETE FROM items_master")
            cur.execute("""
                DELETE FROM sqlite_sequence WHERE name IN (
                    'sales_items',
                    'sales_bills',
                    'purchase_items',
                    'purchase_bills',
                    'monthly_summary',
                    'bill_number_tracker',
                    'customers',
                    'items_master'
                )
            """)
            conn.commit()
            cur.execute("VACUUM")
            conn.close()

            # 2. Reset invoice counter in settings.json
            current_settings = load_settings()
            if "billing" in current_settings:
                start_no = current_settings["billing"].get("bill_start_number", 1)
                current_settings["billing"]["current_bill_number"] = start_no
                save_settings(current_settings)
                self.settings = current_settings
                if "current_bill_no" in self.vars:
                    self.vars["current_bill_no"].set(str(start_no))

            # 3. Clean files in bills storage folder
            bills_folder = Path(self.vars.get("bills_folder", {}).get() if hasattr(self.vars.get("bills_folder"), "get") else (BASE_DIR / "bills"))
            if bills_folder.exists():
                for root, dirs, files in os.walk(bills_folder):
                    for f in files:
                        if f != ".gitkeep":
                            try:
                                os.remove(os.path.join(root, f))
                            except Exception:
                                pass

            # 4. Notify app
            if hasattr(self, "app") and self.app:
                self.app.set_status("All previous data cleared successfully. System reset to fresh state.", "info")

            messagebox.showinfo(
                "Reset Successful",
                "✅ All previous data has been completely cleared!\n\n"
                "• Inventory and stock pools reset to 0\n"
                "• All purchase and sales bills removed\n"
                "• Invoice number tracker reset to #1\n"
                "• Bills storage folder cleaned\n\n"
                "System is ready for clean testing."
            )
        except Exception as exc:
            messagebox.showerror(
                "Reset Failed",
                f"Failed to reset data:\n{exc}"
            )

    # ----------------------------------------------------------
    # TAB 5: BANK DETAILS
    # ----------------------------------------------------------
    def _build_bank_tab(self):
        """Bank details for bill footer"""
        frame = tk.Frame(
            self.scroll_frame,
            bg=COLORS["bg_main"]
        )
        self.tab_frames["bank"] = frame

        card = make_card(
            frame,
            "🏦 Bank Details (shown in bill footer)",
            COLORS["primary"]
        )

        bank_fields = [
            ("bank_name",    "Bank Name",      0,
             "e.g. State Bank of India"),
            ("account_name", "Account Name",   1,
             "e.g. Sri Manjunath Hardware"),
            ("account_no",   "Account Number", 2,
             "e.g. 12345678901"),
            ("ifsc",         "IFSC Code",      3,
             "e.g. SBIN0001234"),
            ("branch",       "Branch",         4,
             "e.g. Hubli Main Branch"),
        ]

        for key, label, row, hint in bank_fields:
            self._make_entry_row(
                card, key, label, row,
                width=30, hint=hint
            )

        tk.Label(
            card,
            text="ℹ️  Bank details are optional but helpful "
                 "for customers making bank transfers.",
            font=FONTS["small"],
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"]
        ).grid(
            row=5, column=0, columnspan=3,
            sticky="w", pady=(15, 0)
        )

    # ----------------------------------------------------------
    # LOAD VALUES FROM SETTINGS FILE
    # ----------------------------------------------------------
    def _load_values(self):
        """
        Load all saved settings into form fields.
        Safe: uses .get() with default so missing
        keys never crash.
        """
        s = self.settings

        def v(key: str, default=""):
            """Get StringVar and set value"""
            var = self.vars.get(key)
            if var:
                var.set(str(default) if default else "")

        # Shop
        shop = s.get("shop", {})
        v("shop_name",     shop.get("name",          ""))
        v("owner_name",    shop.get("owner_name",     ""))
        v("phone",         shop.get("phone",          ""))
        v("email",         shop.get("email",          ""))
        v("address_line1", shop.get("address_line1",  ""))
        v("address_line2", shop.get("address_line2",  ""))
        v("city",          shop.get("city",           ""))
        v("pincode",       shop.get("pincode",        ""))
        v("gstin",         shop.get("gstin",          ""))
        v("pan",           shop.get("pan",            ""))

        # Billing
        billing = s.get("billing", {})
        scheme = billing.get("tax_scheme", "regular")
        if "tax_scheme" in self.vars:
            self.vars["tax_scheme"].set(scheme)

        v("bill_prefix",
          billing.get("bill_prefix", "INV"))
        v("bill_start_number",
          billing.get("bill_start_number", 1))

        margin_type = billing.get(
            "default_margin_type", "range"
        )
        if "margin_type" in self.vars:
            self.vars["margin_type"].set(margin_type)

        v("margin_min",
          billing.get("default_margin_min", 10))
        v("margin_max",
          billing.get("default_margin_max", 20))
        v("margin_global",
          billing.get("default_margin_global", 15))

        v("flat_markup_amount",
          billing.get("flat_markup_amount", 5))
        v("target_profit_amount",
          billing.get("target_profit_amount", 0))

        paper = s.get("print", {}).get(
            "paper_size", "both"
        )
        if "paper_size" in self.vars:
            self.vars["paper_size"].set(paper)

        # Storage
        bills_folder = s.get("storage", {}).get(
            "bills_root_folder",
            str(BASE_DIR / "bills")
        )
        v("bills_folder", bills_folder)

        # Bank
        bank = s.get("bank", {})
        v("bank_name",    bank.get("bank_name",    ""))
        v("account_name", bank.get("account_name", ""))
        v("account_no",   bank.get("account_no",   ""))
        v("ifsc",         bank.get("ifsc",         ""))
        v("branch",       bank.get("branch",       ""))

        # Refresh dynamic UI
        self._on_margin_type_change()
        self._on_scheme_change()

    # ----------------------------------------------------------
    # SAVE ALL — FIXED & COMPLETE
    # ----------------------------------------------------------
    def _save_all(self):
        """
        Validate all fields and save to settings.json
        Shows clear error messages for missing fields.
        """

        def get(key: str, default="") -> str:
            """Safely get StringVar value"""
            var = self.vars.get(key)
            return var.get().strip() if var else default

        # ---- VALIDATION ----
        errors = []

        shop_name = get("shop_name")
        if not shop_name:
            errors.append("• Shop Name is required")

        owner_name = get("owner_name")
        if not owner_name:
            errors.append("• Owner Name is required")

        phone = get("phone")
        if not phone:
            errors.append("• Phone Number is required")
        elif not re.match(r'^\d{10}$', phone):
            errors.append(
                "• Phone Number must be 10 digits"
            )

        address = get("address_line1")
        if not address:
            errors.append(
                "• Address Line 1 is required"
            )

        city = get("city")
        if not city:
            errors.append("• City is required")

        pincode = get("pincode")
        if pincode and not re.match(r'^\d{6}$', pincode):
            errors.append(
                "• PIN Code must be 6 digits"
            )

        gstin = get("gstin").upper()
        if not gstin:
            errors.append("• GSTIN is required")

        # Margin validation
        try:
            m_min = float(get("margin_min") or "10")
            m_max = float(get("margin_max") or "20")
            if m_min >= m_max:
                errors.append(
                    "• Min margin must be less than Max"
                )
            if m_min < 0 or m_max > 100:
                errors.append(
                    "• Margin must be between 0% and 100%"
                )
        except ValueError:
            errors.append(
                "• Margin values must be numbers"
            )

        if errors:
            messagebox.showerror(
                "Please Fix These Errors",
                "\n".join(errors)
            )
            return

        # ---- BUILD SETTINGS DICT ----
        # Load existing to preserve any extra keys
        settings = load_settings()

        # Update shop section
        settings["shop"].update({
            "name":          shop_name,
            "owner_name":    owner_name,
            "phone":         phone,
            "email":         get("email"),
            "address_line1": address,
            "address_line2": get("address_line2"),
            "city":          city,
            "state":         "Karnataka",
            "pincode":       pincode,
            "gstin":         gstin,
            "state_code":    "29",
            "pan":           get("pan").upper(),
        })

        # Update billing section
        tax_scheme = self.vars.get(
            "tax_scheme", tk.StringVar()
        ).get() or "regular"

        margin_type = self.vars.get(
            "margin_type", tk.StringVar()
        ).get() or "range"

        paper_size = self.vars.get(
            "paper_size", tk.StringVar()
        ).get() or "both"

        settings["billing"].update({
            "tax_scheme":
                tax_scheme,
            "bill_prefix":
                (get("bill_prefix") or "INV").upper(),
            "bill_start_number":
                int(get("bill_start_number") or "1"),
            "default_margin_type":
                margin_type,
            "default_margin_min":
                float(get("margin_min") or "10"),
            "default_margin_max":
                float(get("margin_max") or "20"),
            "default_margin_global":
                float(get("margin_global") or "15"),
            "flat_markup_amount":
                float(get("flat_markup_amount") or "5"),
            "target_profit_amount":
                float(get("target_profit_amount") or "0"),
        })

        # Update print section
        settings["print"].update({
            "paper_size": paper_size,
        })

        # Update storage section
        bills_folder = get("bills_folder")
        if not bills_folder:
            bills_folder = str(BASE_DIR / "bills")

        settings["storage"].update({
            "bills_root_folder": bills_folder,
        })

        # Create bills folder if it doesn't exist
        Path(bills_folder).mkdir(
            parents=True, exist_ok=True
        )

        # Update bank section
        settings["bank"] = {
            "bank_name":    get("bank_name"),
            "account_name": get("account_name"),
            "account_no":   get("account_no"),
            "ifsc":         get("ifsc").upper(),
            "branch":       get("branch"),
        }

        # Mark setup as complete
        settings["app"]["setup_complete"] = True

        # ---- SAVE TO FILE ----
        success = save_settings(settings)

        if success:
            # Refresh app header with new shop name
            if hasattr(self.app, "refresh_header"):
                self.app.refresh_header()

            # Update status bar
            if hasattr(self.app, "set_status"):
                self.app.set_status(
                    "Settings saved successfully!",
                    "success"
                )

            messagebox.showinfo(
                "✅ Saved Successfully!",
                f"All settings saved!\n\n"
                f"Shop Name : {shop_name}\n"
                f"GSTIN     : {gstin}\n"
                f"Scheme    : {tax_scheme.title()}\n"
                f"Bills at  : {bills_folder}"
            )
        else:
            messagebox.showerror(
                "❌ Save Failed",
                "Could not save settings file.\n\n"
                "Please check:\n"
                "1. config/ folder exists\n"
                "2. You have write permission\n"
                "3. settings.json is not open elsewhere"
            )