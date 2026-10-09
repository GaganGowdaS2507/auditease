# modules/html_renderer.py
# ============================================================
# HTML RENDERER
# Renders Jinja2 HTML templates with bill/report data
# Opens in browser for preview and printing
# Also converts HTML to PDF using weasyprint (optional)
# ============================================================

import json
import os
import webbrowser
import tempfile
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

# ============================================================
# PATHS
# ============================================================
BASE_DIR      = Path(__file__).parent.parent
CONFIG_PATH   = BASE_DIR / "config" / "settings.json"
TEMPLATES_DIR = BASE_DIR / "templates"

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


def format_date_display(date_val) -> str:
    """Format date as DD-MM-YYYY"""
    if isinstance(date_val, date):
        return date_val.strftime("%d-%m-%Y")
    try:
        d = datetime.strptime(str(date_val), "%Y-%m-%d")
        return d.strftime("%d-%m-%Y")
    except Exception:
        return str(date_val)


def amount_in_words(amount: float) -> str:
    """Convert amount to words"""
    try:
        from num2words import num2words
        rupees = int(amount)
        paise  = round((amount - rupees) * 100)
        words  = num2words(
            rupees, lang="en_IN"
        ).title()
        if paise > 0:
            paise_words = num2words(
                paise, lang="en_IN"
            ).title()
            return (
                f"{words} Rupees and "
                f"{paise_words} Paise Only"
            )
        return f"{words} Rupees Only"
    except Exception:
        return f"Rupees {amount:.2f} Only"


def format_inr(amount: float) -> str:
    """Format as Indian Rupees string"""
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
            formatted = (
                ",".join(groups) + "," + last3
            )
        result = f"₹{formatted}{paise}"
        return f"-{result}" if is_neg else result
    except Exception:
        return f"₹{amount:.2f}"


# ============================================================
# HTML RENDERER CLASS
# ============================================================
class HTMLRenderer:
    """
    Renders HTML templates for bills and reports.

    Usage:
        renderer = HTMLRenderer()

        # Render and open in browser
        renderer.render_sales_bill(bill_data,
                                   bill_number)

        # Render to HTML string
        html = renderer.render_to_string(
            "gst_bill_template.html", context
        )

        # Render and save to file
        renderer.render_to_file(
            "gst_bill_template.html",
            context,
            "output.html"
        )
    """

    def __init__(self):
        self.settings = load_settings()
        self.shop     = self.settings.get("shop", {})
        self.bank     = self.settings.get("bank", {})

        # Try to load Jinja2
        try:
            from jinja2 import (
                Environment, FileSystemLoader
            )
            self.jinja_env = Environment(
                loader=FileSystemLoader(
                    str(TEMPLATES_DIR)
                )
            )
            self.has_jinja = True
        except ImportError:
            self.has_jinja = False
            print(
                "[HTML] Jinja2 not installed. "
                "Run: pip install jinja2"
            )

    def _render_template(
        self,
        template_name: str,
        context: dict
    ) -> str:
        """
        Render a Jinja2 template with context.
        Returns HTML string.
        """
        if not self.has_jinja:
            return self._render_fallback(
                template_name, context
            )

        try:
            template = self.jinja_env.get_template(
                template_name
            )
            return template.render(**context)
        except Exception as e:
            print(
                f"[HTML] Template error: {e}"
            )
            return f"<html><body>Error: {e}</body></html>"

    def _render_fallback(
        self,
        template_name: str,
        context: dict
    ) -> str:
        """
        Fallback: simple string replacement
        if Jinja2 not available.
        """
        template_path = TEMPLATES_DIR / template_name
        if not template_path.exists():
            return (
                "<html><body>"
                "Template not found."
                "</body></html>"
            )

        with open(template_path, "r",
                  encoding="utf-8") as f:
            html = f.read()

        # Simple replacements for basic variables
        for key, value in context.items():
            if isinstance(value, (str, int, float)):
                html = html.replace(
                    f"{{{{ {key} }}}}", str(value)
                )

        return html

    def _get_shop_context(self) -> dict:
        """Build shop-related template context"""
        shop = self.shop
        bank = self.bank

        addr_parts = [
            shop.get("address_line1", ""),
            shop.get("address_line2", ""),
            shop.get("city", ""),
            shop.get("state", "Karnataka"),
            shop.get("pincode", ""),
        ]
        full_addr = ", ".join(
            p for p in addr_parts if p
        )

        return {
            "shop_name":    shop.get("name", ""),
            "shop_owner":   shop.get("owner_name", ""),
            "shop_address": full_addr,
            "shop_phone":   shop.get("phone", ""),
            "shop_email":   shop.get("email", ""),
            "shop_gstin":   shop.get("gstin", ""),
            "shop_pan":     shop.get("pan", ""),
            "bank_name":    bank.get("bank_name", ""),
            "account_name": bank.get(
                "account_name", ""
            ),
            "account_no":   bank.get("account_no", ""),
            "ifsc":         bank.get("ifsc", ""),
            "branch":       bank.get("branch", ""),
            "generated_on": datetime.now().strftime(
                "%d-%m-%Y %H:%M"
            ),
        }

    # ----------------------------------------------------------
    # RENDER SALES BILL
    # ----------------------------------------------------------
    def render_sales_bill(
        self,
        bill_data:   dict,
        bill_number: str,
        open_browser: bool = True,
        save_path:    str  = None
    ) -> str:
        """
        Render sales bill as HTML.

        Args:
            bill_data:    Bill dict from sales module
            bill_number:  e.g. INV-2026-0001
            open_browser: Open in default browser
            save_path:    Save HTML to this path

        Returns:
            Rendered HTML string
        """
        bill_type = bill_data.get(
            "bill_type", "regular"
        )

        # Choose template
        if bill_type == "composition":
            template = "composition_bill_template.html"
        else:
            template = "gst_bill_template.html"

        # Build context
        cust = bill_data.get("customer", {})
        context = {
            **self._get_shop_context(),

            # Bill info
            "bill_number":  bill_number,
            "bill_date":    format_date_display(
                bill_data.get("bill_date", date.today())
            ),
            "bill_type":    bill_type,
            "payment_mode": "Cash",

            # Customer
            "customer_name":    cust.get("name", ""),
            "customer_address": cust.get(
                "address", ""
            ),
            "customer_city":    cust.get("city", ""),
            "customer_phone":   cust.get("phone", ""),

            # Items
            "items": bill_data.get("items", []),

            # Totals
            "subtotal":    round2(
                bill_data.get("subtotal", 0)
            ),
            "total_cgst":  round2(
                bill_data.get("total_cgst", 0)
            ),
            "total_sgst":  round2(
                bill_data.get("total_sgst", 0)
            ),
            "grand_total": round2(
                bill_data.get("grand_total", 0)
            ),
            "round_off":   0,

            # Amount in words
            "amount_in_words": amount_in_words(
                bill_data.get("grand_total", 0)
            ),
        }

        html = self._render_template(template, context)

        if save_path:
            with open(save_path, "w",
                      encoding="utf-8") as f:
                f.write(html)

        if open_browser:
            self._open_in_browser(html)

        return html

    # ----------------------------------------------------------
    # RENDER MONTHLY REPORT
    # ----------------------------------------------------------
    def render_monthly_report(
        self,
        report_data:  dict,
        open_browser: bool = True,
        save_path:    str  = None
    ) -> str:
        """
        Render monthly report as HTML.

        Args:
            report_data:  Data from ReportDataFetcher
            open_browser: Open in default browser
            save_path:    Save HTML to this path
        """
        import sqlite3
        DB_PATH = BASE_DIR / "database" / "shop_database.db"

        MONTH_NAMES_LIST = [
            "", "January", "February", "March",
            "April", "May", "June", "July",
            "August", "September", "October",
            "November", "December"
        ]

        month = report_data.get("month", 1)
        year  = report_data.get("year", 2026)
        p     = report_data.get("purchase", {})
        s     = report_data.get("sales", {})

        # Get detailed bills from DB
        def query(sql, params=()):
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                cur  = conn.cursor()
                cur.execute(sql, params)
                rows = [dict(r) for r in
                        cur.fetchall()]
                conn.close()
                return rows
            except Exception:
                return []

        purchase_bills = query("""
            SELECT * FROM purchase_bills
            WHERE bill_month=? AND bill_year=?
            ORDER BY bill_date
        """, (month, year))

        sales_bills = query("""
            SELECT * FROM sales_bills
            WHERE bill_month=? AND bill_year=?
            ORDER BY bill_date, bill_number
        """, (month, year))

        # Format dates in bills
        for bill in purchase_bills:
            bill["bill_date_fmt"] = (
                format_date_display(bill["bill_date"])
            )
        for bill in sales_bills:
            bill["bill_date_fmt"] = (
                format_date_display(bill["bill_date"])
            )

        # Item tally
        p_items = {
            i["item_name"].lower(): i
            for i in report_data.get(
                "purchase_items", []
            )
        }
        s_items = {
            i["item_name"].lower(): i
            for i in report_data.get(
                "sales_items", []
            )
        }
        all_keys  = sorted(
            set(p_items.keys()) | set(s_items.keys())
        )
        item_tally = []
        tally_ok   = True

        for key in all_keys:
            pi = p_items.get(key, {})
            si = s_items.get(key, {})
            purchased = pi.get("purchased", 0)
            remaining = pi.get("remaining", 0)
            sold      = round(purchased - remaining, 3)

            if abs(remaining) > 0.01:
                tally_ok = False
                status   = "warning"
            else:
                status = "ok"

            item_tally.append({
                "item_name":  (
                    pi.get("item_name") or
                    si.get("item_name") or
                    key.title()
                ),
                "hsn_code": (
                    pi.get("hsn_code") or
                    si.get("hsn_code") or "-"
                ),
                "unit":       pi.get("unit") or
                              si.get("unit") or "-",
                "purchased":  purchased,
                "sold":       sold,
                "remaining":  remaining,
                "buy_rate":   pi.get(
                    "avg_buy_rate", 0
                ) or 0,
                "sell_rate":  si.get(
                    "avg_sell_rate", 0
                ) or 0,
                "margin_pct": si.get(
                    "avg_margin", 0
                ) or 0,
                "status":     status,
            })

        # GST rate summary
        gst_rate_summary = []
        for gst_row in report_data.get(
            "gst_summary", []
        ):
            inp = next(
                (
                    r for r in
                    report_data.get("input_gst", [])
                    if r["gst_rate"] == gst_row["gst_rate"]
                ),
                {}
            )
            gst_r    = gst_row["gst_rate"]
            out_cgst = gst_row.get("cgst", 0)
            out_sgst = gst_row.get("sgst", 0)
            out_total = out_cgst + out_sgst
            in_gst   = inp.get("gst", 0)
            net_pay  = round2(
                max(0, out_total - in_gst)
            )
            gst_rate_summary.append({
                "gst_rate":    gst_r,
                "cgst_rate":   gst_r / 2,
                "sgst_rate":   gst_r / 2,
                "taxable":     gst_row.get(
                    "taxable", 0
                ),
                "cgst":        out_cgst,
                "sgst":        out_sgst,
                "output_total": out_total,
                "input_gst":   in_gst,
                "net_payable": net_pay,
            })

        # Remaining items count
        remaining_items = sum(
            1 for item in item_tally
            if item["remaining"] > 0.01
        )

        context = {
            **self._get_shop_context(),

            # Report info
            "month_name":   MONTH_NAMES_LIST[month],
            "year":         year,
            "month":        month,

            # Summary
            "purchase_total_fmt":
                format_inr(p.get("total", 0)),
            "purchase_taxable_fmt":
                format_inr(p.get("taxable", 0)),
            "purchase_gst_fmt":
                format_inr(
                    report_data.get("p_gst", 0)
                ),
            "purchase_bill_count":
                p.get("bill_count", 0),
            "sales_total_fmt":
                format_inr(s.get("total", 0)),
            "sales_taxable_fmt":
                format_inr(s.get("taxable", 0)),
            "sales_cgst_fmt":
                format_inr(
                    report_data.get("s_cgst", 0)
                ),
            "sales_sgst_fmt":
                format_inr(
                    report_data.get("s_sgst", 0)
                ),
            "sales_bill_count":
                s.get("bill_count", 0),
            "profit_fmt":
                format_inr(report_data.get("profit", 0)),
            "margin_pct":
                report_data.get("margin_pct", 0),
            "gst_payable_fmt":
                format_inr(
                    report_data.get("gst_payable", 0)
                ),
            "input_gst_fmt":
                format_inr(
                    report_data.get("p_gst", 0)
                ),
            "output_gst_fmt":
                format_inr(
                    report_data.get("s_gst", 0)
                ),

            # Tally
            "tally_ok":       tally_ok,
            "remaining_items": remaining_items,

            # Bills
            "purchase_bills":   purchase_bills,
            "sales_bills":      sales_bills,
            "item_tally":       item_tally,
            "gst_rate_summary": gst_rate_summary,
        }

        html = self._render_template(
            "report_template.html", context
        )

        if save_path:
            with open(
                save_path, "w", encoding="utf-8"
            ) as f:
                f.write(html)

        if open_browser:
            self._open_in_browser(html)

        return html

    # ----------------------------------------------------------
    # OPEN IN BROWSER
    # ----------------------------------------------------------
    def _open_in_browser(self, html: str):
        """
        Save HTML to temp file and open in browser.
        Browser handles printing via Ctrl+P.
        """
        try:
            # Create temp file
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".html",
                delete=False,
                encoding="utf-8"
            ) as f:
                f.write(html)
                temp_path = f.name

            # Open in default browser
            webbrowser.open(
                f"file:///{temp_path}"
            )

            print(
                f"[HTML] Opened in browser: "
                f"{temp_path}"
            )
        except Exception as e:
            print(f"[HTML] Browser open error: {e}")

    # ----------------------------------------------------------
    # CONVERT HTML TO PDF (optional)
    # ----------------------------------------------------------
    def html_to_pdf(
        self,
        html: str,
        output_path: str
    ) -> bool:
        """
        Convert HTML to PDF using WeasyPrint.
        Only works if WeasyPrint is installed.

        pip install weasyprint
        """
        try:
            from weasyprint import HTML

            HTML(string=html).write_pdf(output_path)
            print(
                f"[HTML] PDF saved: {output_path}"
            )
            return True

        except ImportError:
            print(
                "[HTML] WeasyPrint not installed.\n"
                "Run: pip install weasyprint\n"
                "Note: WeasyPrint needs GTK on Windows."
            )
            return False

        except Exception as e:
            print(f"[HTML] PDF error: {e}")
            return False

    # ----------------------------------------------------------
    # QUICK RENDER (for direct use)
    # ----------------------------------------------------------
    def render_to_string(
        self,
        template_name: str,
        context: dict
    ) -> str:
        """Render any template with context"""
        return self._render_template(
            template_name, context
        )

    def render_to_file(
        self,
        template_name: str,
        context: dict,
        output_path: str
    ) -> bool:
        """Render template and save to file"""
        try:
            html = self._render_template(
                template_name, context
            )
            with open(
                output_path, "w", encoding="utf-8"
            ) as f:
                f.write(html)
            return True
        except Exception as e:
            print(f"[HTML] File render error: {e}")
            return False