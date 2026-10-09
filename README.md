# Hardware Shop Billing System

A desktop billing and inventory management application for a hardware shop. It includes sales billing, purchase tracking, reports, customer management, GST-ready invoice generation, and database-backed storage.

## Project type

- Python desktop application
- GUI: Tkinter
- Database: SQLite
- Reports/PDFs: reportlab, weasyprint, fpdf2
- OCR / file handling: Pillow, pytesseract, pdf2image, PyMuPDF

## Requirements

- Python 3.10+ recommended; Python 3.13 is supported with the dependency versions in this project
- Linux/macOS/Windows with a desktop session
- For headless Linux environments, use Xvfb to run the GUI

## 1) Open the project folder

```bash
cd "/home/mani/Desktop/bill/hardware_shop_billing (2)/hardware_shop_billing"
```

> If your project folder name contains spaces or parentheses, some Python build tools can fail during installation. In that case, copy or symlink the project to a simple path such as `/home/mani/hardware_billing_app` before running `pip install`.

## 2) Create a virtual environment (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3) Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 4) Run the app

### Normal desktop run

```bash
python3 main.py
```

### If the system is headless or no GUI is available

```bash
xvfb-run -a python3 main.py
```

## First run behavior

On first launch, the app checks whether setup is complete. If required files are missing, it automatically runs `setup.py` to create:

- config/settings.json
- database/shop_database.db
- required folders under bills/, templates/, data/, modules/, assets/

## Main files

- `main.py` – application entry point
- `setup.py` – project initialization and database creation
- `modules/` – app functionality for bills, reports, settings, sales, purchases, and dashboard
- `config/settings.json` – shop information and app settings
- `database/shop_database.db` – SQLite database
- `bills/` – generated purchase/sales reports and bill storage

## Typical workflow

1. Launch the app
2. Complete shop setup in the Settings screen
3. Add purchases and sales data
4. Generate reports and GST bills
5. Print or export PDFs as required

## Troubleshooting

### Module not found error

Reinstall dependencies:

```bash
pip install -r requirements.txt
```

### Tkinter fails on Linux

Use a virtual display:

```bash
xvfb-run -a python3 main.py
```

### App is blocked because setup is not complete

Run:

```bash
python3 setup.py
```

Then launch the application again.

## Notes

This project stores generated billing files under `bills/` in month-based folders. The database and settings are created locally in the project directory, so no external server is required.
