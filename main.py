# main.py
# ============================================================
# HARDWARE SHOP BILLING SYSTEM
# Main entry point — Run this file to start the application
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys
from pathlib import Path

# ============================================================
# BASE DIRECTORY SETUP
# ============================================================
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "settings.json"
DB_PATH = BASE_DIR / "database" / "shop_database.db"

# ============================================================
# CHECK SETUP IS DONE BEFORE STARTING
# ============================================================
def check_setup():
    """Check if setup.py was run, if not run it automatically."""
    if not CONFIG_PATH.exists() or not DB_PATH.exists():
        print("[MAIN] First run detected — running setup...")
        import setup
        setup.run_setup()

    try:
        import setup
        setup.ensure_database_schema(str(DB_PATH))
    except Exception as exc:
        print(f"[MAIN] Schema check failed: {exc}")


# ============================================================
# LOAD SETTINGS
# ============================================================
def load_settings():
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except:
        return {
            "shop": {
                "name": "",
                "gstin": "",
                "address": "",
                "phone": ""
            },
            "app": {
                "setup_complete": False
            }
        }


def save_settings(settings: dict):
    """Save settings back to config/settings.json"""
    with open(CONFIG_PATH, "w") as f:
        json.dump(settings, f, indent=4)


# ============================================================
# COLOR THEME
# ============================================================
COLORS = {
    "primary":      "#1a237e",   # Dark blue — header, sidebar
    "primary_light":"#3949ab",   # Medium blue — buttons
    "accent":       "#ff6f00",   # Orange — highlights
    "success":      "#2e7d32",   # Green — success messages
    "warning":      "#f57f17",   # Yellow — warnings
    "danger":       "#c62828",   # Red — errors
    "bg_main":      "#f5f5f5",   # Light grey — main background
    "bg_card":      "#ffffff",   # White — card backgrounds
    "text_dark":    "#212121",   # Near black — main text
    "text_light":   "#ffffff",   # White — text on dark bg
    "text_muted":   "#757575",   # Grey — secondary text
    "border":       "#e0e0e0",   # Light grey — borders
    "sidebar_bg":   "#1a237e",   # Dark blue sidebar
    "sidebar_hover":"#283593",   # Hover on sidebar
}

FONTS = {
    "heading":      ("Helvetica", 18, "bold"),
    "subheading":   ("Helvetica", 14, "bold"),
    "body":         ("Helvetica", 11),
    "body_bold":    ("Helvetica", 11, "bold"),
    "small":        ("Helvetica", 9),
    "button":       ("Helvetica", 11, "bold"),
    "nav":          ("Helvetica", 12, "bold"),
}


# ============================================================
# MAIN APPLICATION CLASS
# ============================================================
class HardwareShopApp(tk.Tk):
    """
    Main application window.
    
    Layout:
    ┌─────────────────────────────────────────────────┐
    │  HEADER (Shop name, logo, current date)         │
    ├──────────────┬──────────────────────────────────┤
    │              │                                  │
    │   SIDEBAR    │         MAIN CONTENT             │
    │  (Navigation)│         (Active Module)          │
    │              │                                  │
    │  Dashboard   │                                  │
    │  Purchase    │                                  │
    │  Sales       │                                  │
    │  Reports     │                                  │
    │  Customers   │                                  │
    │  Settings    │                                  │
    │              │                                  │
    ├──────────────┴──────────────────────────────────┤
    │  STATUSBAR (Messages, current module info)      │
    └─────────────────────────────────────────────────┘
    """

    def __init__(self):
        super().__init__()

        # Load settings first
        self.settings = load_settings()

        # Window configuration
        self.title("Hardware Shop Billing System")
        self.geometry("1280x800")
        self.minsize(1024, 700)
        self.configure(bg=COLORS["bg_main"])

        # Center window on screen
        self._center_window(1280, 800)

        # Track active navigation button
        self.active_nav = None

        # Track current frame shown in content area
        self.current_frame = None

        # Build UI
        self._build_ui()

        # Check if shop settings are filled
        self._check_first_run()

        # Show dashboard by default
        self.show_dashboard()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)


    # ----------------------------------------------------------
    # WINDOW HELPERS
    # ----------------------------------------------------------
    def _center_window(self, width: int, height: int):
        """Center the window on screen"""
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")


    def _on_close(self):
        """Handle application close"""
        if messagebox.askokcancel(
            "Exit",
            "Are you sure you want to exit\nHardware Shop Billing System?"
        ):
            self.destroy()
            sys.exit(0)


    # ----------------------------------------------------------
    # BUILD MAIN UI STRUCTURE
    # ----------------------------------------------------------
    def _build_ui(self):
        """Build the complete UI layout"""

        # ---- HEADER ----
        self._build_header()

        # ---- BODY (sidebar + content) ----
        body_frame = tk.Frame(self, bg=COLORS["bg_main"])
        body_frame.pack(fill="both", expand=True)

        # ---- SIDEBAR ----
        self._build_sidebar(body_frame)

        # ---- CONTENT AREA ----
        self._build_content_area(body_frame)

        # ---- STATUS BAR ----
        self._build_statusbar()


    # ----------------------------------------------------------
    # HEADER
    # ----------------------------------------------------------
    def _build_header(self):
        """Build top header bar"""
        header = tk.Frame(self, bg=COLORS["primary"], height=70)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        # Left side — App title + shop name
        left_frame = tk.Frame(header, bg=COLORS["primary"])
        left_frame.pack(side="left", padx=20, pady=10)

        tk.Label(
            left_frame,
            text="⚙ Hardware Shop Billing System",
            font=FONTS["heading"],
            bg=COLORS["primary"],
            fg=COLORS["text_light"]
        ).pack(anchor="w")

        # Shop name from settings (shown after setup)
        shop_name = self.settings["shop"].get("name", "")
        self.shop_name_label = tk.Label(
            left_frame,
            text=shop_name if shop_name else "Please complete shop setup →",
            font=FONTS["small"],
            bg=COLORS["primary"],
            fg="#90caf9"
        )
        self.shop_name_label.pack(anchor="w")

        # Right side — Date + GSTIN
        right_frame = tk.Frame(header, bg=COLORS["primary"])
        right_frame.pack(side="right", padx=20, pady=10)

        from datetime import date
        today = date.today().strftime("%d %B %Y")
        tk.Label(
            right_frame,
            text=f"📅 {today}",
            font=FONTS["body"],
            bg=COLORS["primary"],
            fg=COLORS["text_light"]
        ).pack(anchor="e")

        gstin = self.settings["shop"].get("gstin", "")
        self.gstin_label = tk.Label(
            right_frame,
            text=f"GSTIN: {gstin}" if gstin else "GSTIN: Not set",
            font=FONTS["small"],
            bg=COLORS["primary"],
            fg="#90caf9"
        )
        self.gstin_label.pack(anchor="e")


    # ----------------------------------------------------------
    # SIDEBAR NAVIGATION
    # ----------------------------------------------------------
    def _build_sidebar(self, parent):
        """Build left navigation sidebar"""

        self.sidebar = tk.Frame(
            parent,
            bg=COLORS["sidebar_bg"],
            width=220
        )
        self.sidebar.pack(fill="y", side="left")
        self.sidebar.pack_propagate(False)

        # Navigation items
        # (label, icon, command)
        nav_items = [
            ("Dashboard",    "🏠", self.show_dashboard),
            ("Purchase Bills","📥", self.show_purchase),
            ("Sales Bills",  "📤", self.show_sales),
            ("Reports",      "📊", self.show_reports),
            ("Customers",    "👥", self.show_customers),
            ("Settings",     "⚙️",  self.show_settings),
        ]

        # Spacer at top
        tk.Frame(
            self.sidebar,
            bg=COLORS["sidebar_bg"],
            height=20
        ).pack(fill="x")

        # Store nav buttons for active state tracking
        self.nav_buttons = {}

        for label, icon, command in nav_items:
            btn = self._create_nav_button(
                self.sidebar,
                label,
                icon,
                command
            )
            self.nav_buttons[label] = btn

        # Version at bottom of sidebar
        tk.Label(
            self.sidebar,
            text="v1.0.0",
            font=FONTS["small"],
            bg=COLORS["sidebar_bg"],
            fg="#5c6bc0"
        ).pack(side="bottom", pady=10)


    def _create_nav_button(self, parent, label, icon, command):
        """Create a single navigation button in sidebar"""

        # Wrapper frame for hover effect
        btn_frame = tk.Frame(
            parent,
            bg=COLORS["sidebar_bg"],
            cursor="hand2"
        )
        btn_frame.pack(fill="x", pady=2, padx=8)

        # Inner button label
        btn_label = tk.Label(
            btn_frame,
            text=f"  {icon}  {label}",
            font=FONTS["nav"],
            bg=COLORS["sidebar_bg"],
            fg=COLORS["text_light"],
            anchor="w",
            padx=10,
            pady=12
        )
        btn_label.pack(fill="x")

        # Hover effects
        def on_enter(e):
            if self.active_nav != label:
                btn_frame.configure(bg=COLORS["sidebar_hover"])
                btn_label.configure(bg=COLORS["sidebar_hover"])

        def on_leave(e):
            if self.active_nav != label:
                btn_frame.configure(bg=COLORS["sidebar_bg"])
                btn_label.configure(bg=COLORS["sidebar_bg"])

        def on_click(e):
            self._set_active_nav(label)
            command()

        btn_frame.bind("<Enter>", on_enter)
        btn_frame.bind("<Leave>", on_leave)
        btn_frame.bind("<Button-1>", on_click)
        btn_label.bind("<Enter>", on_enter)
        btn_label.bind("<Leave>", on_leave)
        btn_label.bind("<Button-1>", on_click)

        return (btn_frame, btn_label)


    def _set_active_nav(self, active_label: str):
        """Highlight active nav button"""
        for label, (frame, lbl) in self.nav_buttons.items():
            if label == active_label:
                frame.configure(bg=COLORS["accent"])
                lbl.configure(bg=COLORS["accent"])
                self.active_nav = active_label
            else:
                frame.configure(bg=COLORS["sidebar_bg"])
                lbl.configure(bg=COLORS["sidebar_bg"])
    # # In _build_sidebar, add to nav_items:
    # ("Tally",  "✅", self.show_tally),

    # # Add this method to HardwareShopApp:
    # def _safe_tally(self):
    #     self._clear_content()
    #     self._set_active_nav("Tally")
    #     self.set_status("Tally Verification", "info")
    #     try:
    #         from modules.tally_module import TallyFrame
    #         frame = TallyFrame(self.content_area, self)
    #     except ImportError:
    #         Cls = make_placeholder_frame(
    #             "✅ Tally",
    #             "Purchase vs Sales verification"
    #         )
    #         frame = Cls(self.content_area, self)
    #     frame.pack(fill="both", expand=True)
    #     self.current_frame = frame

    # HardwareShopApp.show_tally = _safe_tally

    # ----------------------------------------------------------
    # CONTENT AREA
    # ----------------------------------------------------------
    def _build_content_area(self, parent):
        """Build main content area (right side of sidebar)"""

        self.content_area = tk.Frame(
            parent,
            bg=COLORS["bg_main"]
        )
        self.content_area.pack(
            fill="both",
            expand=True,
            side="left"
        )


    def _clear_content(self):
        """Remove current content from content area"""
        for widget in self.content_area.winfo_children():
            widget.destroy()


    # ----------------------------------------------------------
    # STATUS BAR
    # ----------------------------------------------------------
    def _build_statusbar(self):
        """Build bottom status bar"""

        statusbar = tk.Frame(
            self,
            bg=COLORS["primary"],
            height=30
        )
        statusbar.pack(fill="x", side="bottom")
        statusbar.pack_propagate(False)

        self.status_var = tk.StringVar()
        self.status_var.set("✅ System Ready")

        tk.Label(
            statusbar,
            textvariable=self.status_var,
            font=FONTS["small"],
            bg=COLORS["primary"],
            fg=COLORS["text_light"],
            anchor="w",
            padx=10
        ).pack(side="left", fill="y")

        # Right side — db path info
        tk.Label(
            statusbar,
            text=f"DB: {DB_PATH}",
            font=FONTS["small"],
            bg=COLORS["primary"],
            fg="#5c6bc0",
            anchor="e",
            padx=10
        ).pack(side="right", fill="y")


    def set_status(self, message: str, status_type: str = "info"):
        """Update status bar message
        
        status_type options: info, success, warning, error
        """
        icons = {
            "info":    "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error":   "❌"
        }
        icon = icons.get(status_type, "ℹ️")
        self.status_var.set(f"{icon} {message}")


    # ----------------------------------------------------------
    # FIRST RUN CHECK
    # ----------------------------------------------------------
    def _check_first_run(self):
        """Check if shop settings are filled"""
        shop = self.settings["shop"]
        setup_complete = self.settings["app"].get("setup_complete", False)

        if not setup_complete or not shop.get("name"):
            messagebox.showinfo(
                "Welcome!",
                "Welcome to Hardware Shop Billing System!\n\n"
                "Please fill in your Shop Details first.\n"
                "Go to ⚙️ Settings to complete setup."
            )


    def refresh_header(self):
        """Refresh header after settings update"""
        self.settings = load_settings()
        shop_name = self.settings["shop"].get("name", "")
        gstin = self.settings["shop"].get("gstin", "")

        self.shop_name_label.configure(
            text=shop_name if shop_name else "Please complete shop setup →"
        )
        self.gstin_label.configure(
            text=f"GSTIN: {gstin}" if gstin else "GSTIN: Not set"
        )


    # ----------------------------------------------------------
    # NAVIGATION — Show Each Module
    # ----------------------------------------------------------
    def show_dashboard(self):
        """Show dashboard home screen"""
        self._clear_content()
        self._set_active_nav("Dashboard")
        self.set_status("Dashboard", "info")

        from modules.dashboard_module import DashboardFrame
        frame = DashboardFrame(self.content_area, self)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame


    def show_purchase(self):
        """Show purchase bills module"""
        self._clear_content()
        self._set_active_nav("Purchase Bills")
        self.set_status("Purchase Bills — Upload and manage dealer bills", "info")

        from modules.purchase_module import PurchaseFrame
        frame = PurchaseFrame(self.content_area, self)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame


    def show_sales(self):
        """Show sales bill generation module"""
        self._clear_content()
        self._set_active_nav("Sales Bills")
        self.set_status("Sales Bills — Generate and manage customer bills", "info")

        from modules.sales_module import SalesFrame
        frame = SalesFrame(self.content_area, self)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame


    def show_reports(self):
        """Show reports module"""
        self._clear_content()
        self._set_active_nav("Reports")
        self.set_status("Reports — Monthly and Annual summaries", "info")

        from modules.report_module import ReportFrame
        frame = ReportFrame(self.content_area, self)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame


    def show_customers(self):
        """Show customer management module"""
        self._clear_content()
        self._set_active_nav("Customers")
        self.set_status("Customers — Manage customer database", "info")

        from modules.customer_module import CustomerFrame
        frame = CustomerFrame(self.content_area, self)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame


    def show_settings(self):
        """Show settings module"""
        self._clear_content()
        self._set_active_nav("Settings")
        self.set_status("Settings — Shop details and preferences", "info")

        from modules.settings_module import SettingsFrame
        frame = SettingsFrame(self.content_area, self)
        frame.pack(fill="both", expand=True)
        self.current_frame = frame

    def show_tally(self):
        """Show tally verification module"""
        self._clear_content()
        self._set_active_nav("Tally")
        self.set_status("Tally Verification", "info")

        try:
            from modules.tally_module import TallyFrame
            frame = TallyFrame(self.content_area, self)
        except ImportError:
            Cls = make_placeholder_frame(
                "✅ Tally",
                "Purchase vs Sales verification"
            )
            frame = Cls(self.content_area, self)

        frame.pack(fill="both", expand=True)
        self.current_frame = frame

# ============================================================
# DASHBOARD FRAME (Inline — simple home screen)
# ============================================================
# dashboard_module.py will have full version
# This is a placeholder that works immediately

class DashboardFramePlaceholder(tk.Frame):
    """
    Simple dashboard showing monthly summary cards
    Full version in modules/dashboard_module.py
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg=COLORS["bg_main"])
        self.app = app
        self._build()

    def _build(self):
        # Title
        tk.Label(
            self,
            text="Dashboard",
            font=FONTS["heading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", padx=30, pady=(30, 5))

        tk.Label(
            self,
            text="Welcome to Hardware Shop Billing System",
            font=FONTS["body"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_muted"]
        ).pack(anchor="w", padx=30, pady=(0, 20))

        # Quick stats row
        self._build_stats_row()

        # Quick action buttons
        self._build_quick_actions()

    def _build_stats_row(self):
        """Build summary stat cards"""
        stats_frame = tk.Frame(self, bg=COLORS["bg_main"])
        stats_frame.pack(fill="x", padx=30, pady=10)

        # Get current month stats from DB
        from datetime import date
        import sqlite3

        today = date.today()
        month = today.month
        year = today.year

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Purchase count this month
            cursor.execute("""
                SELECT COUNT(*), COALESCE(SUM(grand_total), 0)
                FROM purchase_bills
                WHERE bill_month=? AND bill_year=?
            """, (month, year))
            p_count, p_total = cursor.fetchone()

            # Sales count this month
            cursor.execute("""
                SELECT COUNT(*), COALESCE(SUM(grand_total), 0)
                FROM sales_bills
                WHERE bill_month=? AND bill_year=?
            """, (month, year))
            s_count, s_total = cursor.fetchone()

            conn.close()
        except Exception:
            p_count, p_total = 0, 0
            s_count, s_total = 0, 0

        from datetime import date
        month_name = date.today().strftime("%B %Y")

        stats = [
            ("📥 Purchase Bills", f"{p_count} bills", f"₹{p_total:,.2f}", COLORS["primary_light"]),
            ("📤 Sales Bills",    f"{s_count} bills", f"₹{s_total:,.2f}", COLORS["success"]),
            ("💰 Profit (Est.)",  f"{month_name}",    "Calculate in Reports", COLORS["accent"]),
        ]

        for title, subtitle, value, color in stats:
            card = tk.Frame(
                stats_frame,
                bg=color,
                padx=20,
                pady=15
            )
            card.pack(side="left", padx=10, pady=5, fill="y")

            tk.Label(
                card,
                text=title,
                font=FONTS["body_bold"],
                bg=color,
                fg="white"
            ).pack(anchor="w")

            tk.Label(
                card,
                text=subtitle,
                font=FONTS["small"],
                bg=color,
                fg="#e3f2fd"
            ).pack(anchor="w")

            tk.Label(
                card,
                text=value,
                font=FONTS["subheading"],
                bg=color,
                fg="white"
            ).pack(anchor="w", pady=(5, 0))

    def _build_quick_actions(self):
        """Quick action buttons"""
        tk.Label(
            self,
            text="Quick Actions",
            font=FONTS["subheading"],
            bg=COLORS["bg_main"],
            fg=COLORS["text_dark"]
        ).pack(anchor="w", padx=30, pady=(30, 10))

        actions_frame = tk.Frame(self, bg=COLORS["bg_main"])
        actions_frame.pack(fill="x", padx=30)

        actions = [
            ("📥 Add Purchase Bill",  self.app.show_purchase,  COLORS["primary_light"]),
            ("📤 Generate Sales Bills",self.app.show_sales,    COLORS["success"]),
            ("📊 View Reports",        self.app.show_reports,  COLORS["accent"]),
            ("⚙️ Shop Settings",       self.app.show_settings, COLORS["text_muted"]),
        ]

        for label, command, color in actions:
            btn = tk.Button(
                actions_frame,
                text=label,
                font=FONTS["button"],
                bg=color,
                fg="white",
                relief="flat",
                padx=20,
                pady=12,
                cursor="hand2",
                command=command
            )
            btn.pack(side="left", padx=8)


# ============================================================
# MODULE PLACEHOLDER FRAMES
# (Shown if module files not yet created)
# ============================================================
def make_placeholder_frame(module_name: str, description: str):
    """Factory to create placeholder frames for modules"""

    class PlaceholderFrame(tk.Frame):
        def __init__(self, parent, app):
            super().__init__(parent, bg=COLORS["bg_main"])
            tk.Label(
                self,
                text=f"{module_name}",
                font=FONTS["heading"],
                bg=COLORS["bg_main"],
                fg=COLORS["text_dark"]
            ).pack(pady=(50, 10))
            tk.Label(
                self,
                text=description,
                font=FONTS["body"],
                bg=COLORS["bg_main"],
                fg=COLORS["text_muted"]
            ).pack()
            tk.Label(
                self,
                text="(Module loading...)",
                font=FONTS["small"],
                bg=COLORS["bg_main"],
                fg=COLORS["text_muted"]
            ).pack(pady=5)

    return PlaceholderFrame


# ============================================================
# SAFE MODULE IMPORT WRAPPER
# ============================================================
# Patch show methods to use placeholders if modules not ready
def _safe_show(app, module_path: str, class_name: str,
                fallback_name: str, fallback_desc: str):
    """Try to import module, fall back to placeholder if missing"""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls
    except (ImportError, AttributeError):
        return make_placeholder_frame(fallback_name, fallback_desc)


# Monkey-patch show methods with safe imports
_original_show_dashboard = HardwareShopApp.show_dashboard
_original_show_purchase  = HardwareShopApp.show_purchase
_original_show_sales     = HardwareShopApp.show_sales
_original_show_reports   = HardwareShopApp.show_reports
_original_show_customers = HardwareShopApp.show_customers
_original_show_settings  = HardwareShopApp.show_settings


def _safe_dashboard(self):
    self._clear_content()
    self._set_active_nav("Dashboard")
    self.set_status("Dashboard", "info")
    try:
        from modules.dashboard_module import DashboardFrame
        frame = DashboardFrame(self.content_area, self)
    except ImportError:
        frame = DashboardFramePlaceholder(self.content_area, self)
    frame.pack(fill="both", expand=True)
    self.current_frame = frame


def _safe_purchase(self):
    self._clear_content()
    self._set_active_nav("Purchase Bills")
    self.set_status("Purchase Bills", "info")
    try:
        from modules.purchase_module import PurchaseFrame
        frame = PurchaseFrame(self.content_area, self)
    except ImportError:
        Cls = make_placeholder_frame(
            "📥 Purchase Bills",
            "Upload and manage purchase bills from dealers"
        )
        frame = Cls(self.content_area, self)
    frame.pack(fill="both", expand=True)
    self.current_frame = frame


def _safe_sales(self):
    self._clear_content()
    self._set_active_nav("Sales Bills")
    self.set_status("Sales Bills", "info")
    try:
        from modules.sales_module import SalesFrame
        frame = SalesFrame(self.content_area, self)
    except ImportError:
        Cls = make_placeholder_frame(
            "📤 Sales Bills",
            "Generate and manage customer sales bills"
        )
        frame = Cls(self.content_area, self)
    frame.pack(fill="both", expand=True)
    self.current_frame = frame


def _safe_reports(self):
    self._clear_content()
    self._set_active_nav("Reports")
    self.set_status("Reports", "info")
    try:
        from modules.report_module import ReportFrame
        frame = ReportFrame(self.content_area, self)
    except ImportError:
        Cls = make_placeholder_frame(
            "📊 Reports",
            "Monthly and Annual GST reports"
        )
        frame = Cls(self.content_area, self)
    frame.pack(fill="both", expand=True)
    self.current_frame = frame


def _safe_customers(self):
    self._clear_content()
    self._set_active_nav("Customers")
    self.set_status("Customers", "info")
    try:
        from modules.customer_module import CustomerFrame
        frame = CustomerFrame(self.content_area, self)
    except ImportError:
        Cls = make_placeholder_frame(
            "👥 Customers",
            "Manage customer database"
        )
        frame = Cls(self.content_area, self)
    frame.pack(fill="both", expand=True)
    self.current_frame = frame


def _safe_settings(self):
    self._clear_content()
    self._set_active_nav("Settings")
    self.set_status("Settings", "info")
    try:
        from modules.settings_module import SettingsFrame
        frame = SettingsFrame(self.content_area, self)
    except ImportError:
        Cls = make_placeholder_frame(
            "⚙️ Settings",
            "Shop details and billing preferences"
        )
        frame = Cls(self.content_area, self)
    frame.pack(fill="both", expand=True)
    self.current_frame = frame


# Apply safe show methods
HardwareShopApp.show_dashboard = _safe_dashboard
HardwareShopApp.show_purchase  = _safe_purchase
HardwareShopApp.show_sales     = _safe_sales
HardwareShopApp.show_reports   = _safe_reports
HardwareShopApp.show_customers = _safe_customers
HardwareShopApp.show_settings  = _safe_settings


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    # Step 1: Ensure setup is done
    check_setup()

    # Step 2: Launch app
    app = HardwareShopApp()

    # Step 3: Start main loop
    app.mainloop()