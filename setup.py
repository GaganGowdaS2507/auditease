# setup.py
# Run this ONCE when installing the software
# Creates all required folders and initializes database

import os
import json
import sqlite3
from pathlib import Path

# ============================================================
# BASE DIRECTORY — Everything lives here
# ============================================================
BASE_DIR = Path(__file__).parent
print(f"[SETUP] Base directory: {BASE_DIR}")

# ============================================================
# ALL FOLDER PATHS
# ============================================================
FOLDERS_TO_CREATE = [
    BASE_DIR / "config",
    BASE_DIR / "database",
    BASE_DIR / "modules",
    BASE_DIR / "templates",
    BASE_DIR / "assets" / "fonts",
    BASE_DIR / "data",
    BASE_DIR / "bills",         # Root bills folder
    # Monthly folders created dynamically by app
    # when father starts adding bills
]

def create_folders():
    """Create all required folders"""
    print("\n[SETUP] Creating folder structure...")
    for folder in FOLDERS_TO_CREATE:
        folder.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Created: {folder}")
    print("[SETUP] All folders created successfully.\n")


# ============================================================
# DEFAULT SETTINGS FILE
# ============================================================
DEFAULT_SETTINGS = {
    "shop": {
        "name": "",
        "owner_name": "",
        "address_line1": "",
        "address_line2": "",
        "city": "",
        "state": "Karnataka",
        "pincode": "",
        "phone": "",
        "email": "",
        "gstin": "",
        "state_code": "29",
        "pan": ""
    },
    "billing": {
        "tax_scheme": "regular",       # "regular" or "composition"
        "bill_prefix": "INV",
        "bill_start_number": 1,
        "current_bill_number": 1,
        "bill_year": 2026,
        "default_margin_type": "range", # "global", "itemwise", "range"
        "default_margin_min": 10,
        "default_margin_max": 20,
        "default_margin_global": 15
    },
    "print": {
        "paper_size": "both",          # "a4", "thermal", "both"
        "thermal_width_mm": 80,
        "printer_name": ""
    },
    "storage": {
        "bills_root_folder": str(BASE_DIR / "bills"),
        "database_path": str(BASE_DIR / "database" / "shop_database.db"),
        "backup_enabled": True
    },
    "app": {
        "setup_complete": False,
        "version": "1.0.0"
    }
}

def create_default_settings():
    """Create settings.json if not exists"""
    settings_path = BASE_DIR / "config" / "settings.json"
    if not settings_path.exists():
        with open(settings_path, "w") as f:
            json.dump(DEFAULT_SETTINGS, f, indent=4)
        print(f"  ✅ Created: settings.json")
    else:
        print(f"  ℹ️  settings.json already exists — skipping")


# ============================================================
# DATABASE SCHEMA
# ============================================================
def ensure_database_schema(db_path: str | None = None):
    """Add missing columns for older databases created before item_date tracking."""
    db_file = Path(db_path) if db_path else BASE_DIR / "database" / "shop_database.db"
    if not db_file.exists():
        return False

    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()

    for table_name in ["purchase_items", "sales_items"]:
        try:
            columns = [row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]
            if "item_date" not in columns:
                cursor.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN item_date TEXT DEFAULT ''"
                )
                print(f"  ✅ Migrated: {table_name} adds item_date column")
            else:
                print(f"  ℹ️  Schema OK: {table_name} already has item_date")
        except Exception as exc:
            print(f"  ⚠️  Could not migrate {table_name}: {exc}")

    try:
        table_exists = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='purchase_bills'"
        ).fetchone()
        if not table_exists:
            raise RuntimeError("purchase_bills table does not exist")

        from modules.purchase_module import parse_csv_bill, round2

        bills_missing_items = cursor.execute("""
            SELECT id, bill_date, file_path
            FROM purchase_bills
            WHERE id NOT IN (
                SELECT DISTINCT purchase_bill_id
                FROM purchase_items
            )
        """).fetchall()

        for bill_id, bill_date, file_path in bills_missing_items:
            if not file_path or not Path(file_path).exists():
                continue

            items = parse_csv_bill(str(file_path))
            if not items:
                continue

            for item in items:
                item_date = item.get("item_date") or bill_date
                quantity = float(item.get("quantity", 0) or 0)
                rate = float(item.get("rate", 0) or 0)
                gst_rate = float(item.get("gst_rate", 0) or 0)
                gst_amount = round2(quantity * rate * gst_rate / 100)
                total_amount = round2((quantity * rate) + gst_amount)

                cursor.execute("""
                    INSERT INTO purchase_items (
                        purchase_bill_id, item_name, item_date, hsn_code,
                        quantity, unit, purchase_rate, gst_rate,
                        gst_amount, total_amount, remaining_qty
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    bill_id,
                    item.get("item_name", "").strip(),
                    item_date,
                    item.get("hsn_code", "-"),
                    quantity,
                    item.get("unit", "piece"),
                    rate,
                    gst_rate,
                    gst_amount,
                    total_amount,
                    quantity,
                ))

        conn.commit()
        print("  ✅ Repaired missing purchase item rows from uploaded CSV files")
    except Exception as exc:
        if "purchase_bills table does not exist" not in str(exc):
            print(f"  ⚠️  Could not repair purchase item rows: {exc}")

    conn.close()
    return True


def create_database():
    """Create SQLite database with all tables"""
    db_path = BASE_DIR / "database" / "shop_database.db"
    print(f"\n[SETUP] Creating database at: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --------------------------------------------------------
    # TABLE 1: items_master
    # Stores all item types seen across all purchase bills
    # Auto-learns new items over time
    # --------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items_master (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name       TEXT NOT NULL,
            item_name_lower TEXT NOT NULL,          -- for search
            hsn_code        TEXT DEFAULT '-',
            gst_rate        REAL DEFAULT 18.0,      -- percentage
            unit            TEXT DEFAULT 'piece',   -- piece/meter/kg/liter
            category        TEXT DEFAULT 'general', -- pipes/cement/tools etc
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  ✅ Table: items_master")

    # --------------------------------------------------------
    # TABLE 2: customers
    # Stores customer names — manual + auto-generated
    # --------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            phone           TEXT DEFAULT '',
            address         TEXT DEFAULT '',
            city            TEXT DEFAULT '',
            is_auto_generated INTEGER DEFAULT 0,   -- 1=Karnataka name gen
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  ✅ Table: customers")

    # --------------------------------------------------------
    # TABLE 3: purchase_bills
    # One row per purchase bill uploaded
    # --------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_bills (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number     TEXT NOT NULL,          -- dealer's bill number
            dealer_name     TEXT NOT NULL,
            bill_date       TEXT NOT NULL,          -- YYYY-MM-DD
            bill_month      INTEGER NOT NULL,       -- 1-12
            bill_year       INTEGER NOT NULL,       -- 2026
            subtotal        REAL NOT NULL,          -- taxable value
            total_gst       REAL NOT NULL,
            grand_total     REAL NOT NULL,          -- subtotal + gst
            bill_type       TEXT DEFAULT 'regular', -- regular/composition
            file_path       TEXT DEFAULT '',        -- uploaded file path
            notes           TEXT DEFAULT '',
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("  ✅ Table: purchase_bills")

    # --------------------------------------------------------
    # TABLE 4: purchase_items
    # One row per item in each purchase bill
    # --------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_bill_id INTEGER NOT NULL,
            item_master_id  INTEGER,                -- links to items_master
            item_name       TEXT NOT NULL,
            item_date       TEXT DEFAULT '',        -- YYYY-MM-DD for this item
            hsn_code        TEXT DEFAULT '-',
            quantity        REAL NOT NULL,
            unit            TEXT DEFAULT 'piece',
            purchase_rate   REAL NOT NULL,          -- taxable rate per unit
            gst_rate        REAL NOT NULL,          -- percentage
            gst_amount      REAL NOT NULL,          -- total GST for this item
            total_amount    REAL NOT NULL,          -- qty × rate + gst
            remaining_qty   REAL NOT NULL,          -- for split tracking
            FOREIGN KEY (purchase_bill_id) REFERENCES purchase_bills(id),
            FOREIGN KEY (item_master_id) REFERENCES items_master(id)
        )
    """)
    print("  ✅ Table: purchase_items")

    try:
        cursor.execute("ALTER TABLE purchase_items ADD COLUMN item_date TEXT DEFAULT ''")
    except Exception:
        pass

    # --------------------------------------------------------
    # TABLE 5: sales_bills
    # One row per generated sales bill
    # --------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_bills (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number     TEXT NOT NULL UNIQUE,   -- INV-2026-0001
            customer_id     INTEGER,
            customer_name   TEXT NOT NULL,
            bill_date       TEXT NOT NULL,          -- YYYY-MM-DD
            bill_month      INTEGER NOT NULL,
            bill_year       INTEGER NOT NULL,
            subtotal        REAL NOT NULL,          -- taxable value
            total_cgst      REAL NOT NULL,
            total_sgst      REAL NOT NULL,
            grand_total     REAL NOT NULL,
            bill_type       TEXT DEFAULT 'regular', -- regular/composition
            margin_applied  REAL DEFAULT 0,         -- average margin %
            file_path       TEXT DEFAULT '',        -- generated PDF path
            is_printed      INTEGER DEFAULT 0,
            linked_month    INTEGER NOT NULL,       -- which purchase month
            linked_year     INTEGER NOT NULL,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    print("  ✅ Table: sales_bills")

    # --------------------------------------------------------
    # TABLE 6: sales_items
    # One row per item in each sales bill
    # --------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sales_bill_id   INTEGER NOT NULL,
            purchase_item_id INTEGER,               -- links back to purchase
            item_name       TEXT NOT NULL,
            item_date       TEXT DEFAULT '',        -- YYYY-MM-DD for this item
            hsn_code        TEXT DEFAULT '-',
            quantity        REAL NOT NULL,
            unit            TEXT DEFAULT 'piece',
            selling_rate    REAL NOT NULL,          -- taxable selling rate
            gst_rate        REAL NOT NULL,
            cgst_rate       REAL NOT NULL,          -- half of gst_rate
            sgst_rate       REAL NOT NULL,          -- half of gst_rate
            cgst_amount     REAL NOT NULL,
            sgst_amount     REAL NOT NULL,
            total_amount    REAL NOT NULL,          -- qty×rate + cgst + sgst
            margin_percent  REAL NOT NULL,          -- margin applied
            FOREIGN KEY (sales_bill_id) REFERENCES sales_bills(id),
            FOREIGN KEY (purchase_item_id) REFERENCES purchase_items(id)
        )
    """)
    print("  ✅ Table: sales_items")

    try:
        cursor.execute("ALTER TABLE sales_items ADD COLUMN item_date TEXT DEFAULT ''")
    except Exception:
        pass

    # --------------------------------------------------------
    # TABLE 7: bill_number_tracker
    # Ensures sequential bill numbers — never skip
    # --------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bill_number_tracker (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            prefix          TEXT DEFAULT 'INV',
            year            INTEGER NOT NULL,
            last_number     INTEGER DEFAULT 0,
            UNIQUE(prefix, year)
        )
    """)
    print("  ✅ Table: bill_number_tracker")

    # --------------------------------------------------------
    # TABLE 8: monthly_summary
    # Pre-calculated monthly totals for quick reports
    # --------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_summary (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            month               INTEGER NOT NULL,
            year                INTEGER NOT NULL,
            total_purchase      REAL DEFAULT 0,
            total_purchase_gst  REAL DEFAULT 0,
            total_sales         REAL DEFAULT 0,
            total_cgst          REAL DEFAULT 0,
            total_sgst          REAL DEFAULT 0,
            total_profit        REAL DEFAULT 0,
            gst_payable         REAL DEFAULT 0,     -- output - input GST
            bills_count_purchase INTEGER DEFAULT 0,
            bills_count_sales    INTEGER DEFAULT 0,
            is_finalized        INTEGER DEFAULT 0,  -- 0=draft, 1=finalized
            updated_at          TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(month, year)
        )
    """)
    print("  ✅ Table: monthly_summary")

    conn.commit()
    conn.close()
    print("[SETUP] Database created successfully.\n")


# ============================================================
# HSN MASTER DATA FILE
# ============================================================
HSN_MASTER = {
    "pipes_and_fittings": [
        {"hsn": "7304", "description": "Seamless iron/steel pipes", "gst_rate": 18},
        {"hsn": "7306", "description": "Welded iron/steel pipes (GI Pipe)", "gst_rate": 18},
        {"hsn": "7307", "description": "Pipe fittings (elbows, bends, couplings)", "gst_rate": 18},
        {"hsn": "3917", "description": "PVC Pipes and fittings", "gst_rate": 18},
        {"hsn": "3917", "description": "CPVC Pipes", "gst_rate": 18},
        {"hsn": "8481", "description": "Valves, taps, cocks (ball valve, gate valve)", "gst_rate": 18}
    ],
    "cement_and_building": [
        {"hsn": "2523", "description": "Portland cement, white cement", "gst_rate": 28},
        {"hsn": "7214", "description": "MS Rods, iron bars", "gst_rate": 18},
        {"hsn": "7210", "description": "Steel sheets", "gst_rate": 18},
        {"hsn": "7317", "description": "Nails, tacks, staples (iron/steel)", "gst_rate": 18},
        {"hsn": "7318", "description": "Screws, bolts, nuts, washers", "gst_rate": 18}
    ],
    "paint_and_chemicals": [
        {"hsn": "3208", "description": "Paints (synthetic, oil-based)", "gst_rate": 18},
        {"hsn": "3209", "description": "Water-based paints", "gst_rate": 18},
        {"hsn": "3210", "description": "Varnishes, distempers", "gst_rate": 18},
        {"hsn": "3214", "description": "Putty, sealants", "gst_rate": 18}
    ],
    "electrical": [
        {"hsn": "8536", "description": "Switches, sockets, plugs", "gst_rate": 18},
        {"hsn": "8544", "description": "Electric wires, cables", "gst_rate": 18},
        {"hsn": "9405", "description": "Bulbs, tube lights, LED", "gst_rate": 12}
    ],
    "tools_and_hardware": [
        {"hsn": "8205", "description": "Hand tools (hammers, spanners, pliers)", "gst_rate": 18},
        {"hsn": "8204", "description": "Wrenches and spanners", "gst_rate": 18},
        {"hsn": "8301", "description": "Locks, padlocks", "gst_rate": 18},
        {"hsn": "8302", "description": "Hinges, handles, brackets", "gst_rate": 18},
        {"hsn": "8481", "description": "Taps, faucets, shower heads", "gst_rate": 18}
    ],
    "sanitary": [
        {"hsn": "6910", "description": "Ceramic wash basins, sinks", "gst_rate": 18},
        {"hsn": "3922", "description": "Plastic baths, showers, sinks", "gst_rate": 18},
        {"hsn": "7324", "description": "Stainless steel sinks", "gst_rate": 18}
    ]
}

def create_hsn_master():
    """Create HSN master JSON file"""
    hsn_path = BASE_DIR / "data" / "hsn_master.json"
    with open(hsn_path, "w") as f:
        json.dump(HSN_MASTER, f, indent=4)
    print(f"  ✅ Created: hsn_master.json ({sum(len(v) for v in HSN_MASTER.values())} items)")


# ============================================================
# KARNATAKA CUSTOMER NAMES
# ============================================================
KARNATAKA_NAMES = {
    "male_first_names": [
        "Ramesh", "Suresh", "Mahesh", "Manjunath", "Basavaraj",
        "Shivakumar", "Nagesh", "Venkatesh", "Srinivas", "Prakash",
        "Ravi", "Kumar", "Ganesh", "Siddappa", "Hanumanthu",
        "Basappa", "Mallappa", "Channappa", "Girish", "Nagaraj",
        "Rajesh", "Lokesh", "Santosh", "Pradeep", "Deepak",
        "Ashok", "Mohan", "Krishnamurthy", "Subramanya", "Prabhakar",
        "Thimmappa", "Rudrappa", "Veeresh", "Shivarudrappa", "Mahadevappa",
        "Ningappa", "Gurusiddappa", "Parasappa", "Yamanagouda", "Basagouda",
        "Virupaksha", "Eranna", "Maranna", "Shankrappa", "Revanna",
        "Huliyappa", "Kallappa", "Devaraju", "Muthuraju", "Nanjunda"
    ],
    "female_first_names": [
        "Lakshmi", "Savitha", "Rekha", "Meena", "Pushpa",
        "Geetha", "Usha", "Sumathi", "Kavitha", "Radha",
        "Shantha", "Vijaya", "Saroja", "Kamala", "Hemavathi",
        "Nagaveni", "Bhagyamma", "Sharadha", "Yashoda", "Parvathi"
    ],
    "last_names": [
        "Gowda", "Shetty", "Patil", "Naik", "Reddy",
        "Hegde", "Rao", "Swamy", "Nayak", "Kulkarni",
        "Joshi", "Bhat", "Kamath", "Prabhu", "Shenoy",
        "Poojary", "Goundar", "Vokkaliga", "Lingayat", "Mudaliar",
        "Raju", "Kumar", "Murthy", "Sharma", "Verma",
        "Hosamani", "Kambale", "Doddamani", "Walikar", "Sajjan",
        "Angadi", "Gadad", "Mulimani", "Havanur", "Koppad"
    ],
    "cities_karnataka": [
        "Bangalore", "Mysore", "Hubli", "Dharwad", "Mangalore",
        "Belgaum", "Gulbarga", "Davangere", "Bellary", "Shimoga",
        "Tumkur", "Raichur", "Bijapur", "Hospet", "Gadag",
        "Udupi", "Hassan", "Mandya", "Chikmagalur", "Kolar",
        "Bidar", "Chitradurga", "Bagalkot", "Haveri", "Koppal",
        "Yadgir", "Chamarajanagar", "Kodagu", "Chikkaballapur", "Bangalore Rural"
    ]
}

def create_karnataka_names():
    """Create Karnataka names JSON file"""
    names_path = BASE_DIR / "data" / "karnataka_names.json"
    with open(names_path, "w") as f:
        json.dump(KARNATAKA_NAMES, f, indent=4)
    male_count = len(KARNATAKA_NAMES["male_first_names"])
    female_count = len(KARNATAKA_NAMES["female_first_names"])
    last_count = len(KARNATAKA_NAMES["last_names"])
    print(f"  ✅ Created: karnataka_names.json")
    print(f"     ({male_count} male + {female_count} female first names, {last_count} last names)")


# ============================================================
# CREATE __init__.py FOR MODULES
# ============================================================
def create_init_files():
    """Create __init__.py for modules package"""
    init_path = BASE_DIR / "modules" / "__init__.py"
    with open(init_path, "w") as f:
        f.write("# Hardware Shop Billing System - Modules Package\n")
    print(f"  ✅ Created: modules/__init__.py")


# ============================================================
# MAIN SETUP RUNNER
# ============================================================
def run_setup():
    print("=" * 60)
    print("  HARDWARE SHOP BILLING SYSTEM — SETUP")
    print("=" * 60)

    # Step 1: Create folders
    create_folders()

    # Step 2: Create settings
    print("[SETUP] Creating configuration files...")
    create_default_settings()

    # Step 3: Create database
    create_database()

    # Step 4: Create data files
    print("\n[SETUP] Creating data files...")
    create_hsn_master()
    create_karnataka_names()

    # Step 5: Create module init
    print("\n[SETUP] Creating module files...")
    create_init_files()

    print("\n" + "=" * 60)
    print("  ✅ SETUP COMPLETE!")
    print("  Run main.py to start the application")
    print("=" * 60)


if __name__ == "__main__":
    run_setup()