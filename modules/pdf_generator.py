# modules/pdf_generator.py
# ============================================================
# PDF GENERATOR MODULE
# Generates professional GST bills in PDF format
#
# Features:
# 1. A4 size GST bill (Regular scheme)
# 2. A4 size Composition bill
# 3. Thermal receipt format (80mm width)
# 4. Shop header with logo placeholder
# 5. Items table with GST breakup
# 6. Totals section (taxable + CGST + SGST + grand total)
# 7. Amount in words (Indian numbering)
# 8. Bank details footer
# 9. Legal declarations
# 10. Bill number + QR placeholder
# ============================================================

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.lib.styles import (
    getSampleStyleSheet, ParagraphStyle
)
from reportlab.lib.enums import (
    TA_LEFT, TA_CENTER, TA_RIGHT
)
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable,
    KeepTogether
)
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import json
import os
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from num2words import num2words

# ============================================================
# PATHS
# ============================================================
BASE_DIR    = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config" / "settings.json"
ASSETS_DIR  = BASE_DIR / "assets"

# ============================================================
# THERMAL BILL CONSTANTS
# ============================================================
THERMAL_WIDTH_MM  = 80
THERMAL_WIDTH_PT  = THERMAL_WIDTH_MM * mm
THERMAL_MARGIN_PT = 3 * mm

# ============================================================
# COLOR PALETTE FOR PDF
# ============================================================
PDF_COLORS = {
    "primary":      colors.HexColor("#1a237e"),
    "primary_light":colors.HexColor("#3949ab"),
    "accent":       colors.HexColor("#ff6f00"),
    "success":      colors.HexColor("#2e7d32"),
    "light_blue":   colors.HexColor("#e3f2fd"),
    "light_green":  colors.HexColor("#e8f5e9"),
    "light_grey":   colors.HexColor("#f5f5f5"),
    "border":       colors.HexColor("#bdbdbd"),
    "text_dark":    colors.HexColor("#212121"),
    "text_muted":   colors.HexColor("#757575"),
    "white":        colors.white,
    "black":        colors.black,
    "header_bg":    colors.HexColor("#1a237e"),
    "header_text":  colors.white,
    "row_even":     colors.HexColor("#f9f9f9"),
    "row_odd":      colors.white,
    "total_bg":     colors.HexColor("#e8f5e9"),
    "grand_bg":     colors.HexColor("#1a237e"),
}


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


def amount_in_words(amount: float) -> str:
    """
    Convert amount to Indian English words.
    Example: 12345.50 → "Twelve Thousand Three Hundred
                         Forty Five Rupees and
                         Fifty Paise Only"
    """
    try:
        rupees = int(amount)
        paise  = round((amount - rupees) * 100)

        rupee_words = num2words(
            rupees,
            lang="en_IN"
        ).title()

        if paise > 0:
            paise_words = num2words(
                paise,
                lang="en_IN"
            ).title()
            return (
                f"{rupee_words} Rupees and "
                f"{paise_words} Paise Only"
            )
        else:
            return f"{rupee_words} Rupees Only"
    except Exception:
        return f"Rupees {amount:.2f} Only"


def format_date(date_val) -> str:
    """Format date for display on bill"""
    if isinstance(date_val, date):
        return date_val.strftime("%d-%m-%Y")
    try:
        d = datetime.strptime(str(date_val), "%Y-%m-%d")
        return d.strftime("%d-%m-%Y")
    except Exception:
        return str(date_val)


# ============================================================
# PDF GENERATOR CLASS
# ============================================================
class PDFGenerator:
    """
    Generates PDF bills for sales.

    Usage:
        gen = PDFGenerator(settings)
        gen.generate_sales_bill(
            bill_data=bill_dict,
            bill_number="INV-2026-0001",
            output_path="path/to/INV-2026-0001.pdf"
        )
    """

    def __init__(self, settings: dict = None):
        if settings is None:
            settings = load_settings()
        self.settings = settings
        self.shop     = settings.get("shop", {})
        self.bank     = settings.get("bank", {})
        self.billing  = settings.get("billing", {})

        # Styles
        self.styles   = getSampleStyleSheet()
        self._setup_styles()

    # ----------------------------------------------------------
    # STYLE SETUP
    # ----------------------------------------------------------
    def _setup_styles(self):
        """Define custom paragraph styles"""

        self.style_shop_name = ParagraphStyle(
            "ShopName",
            parent=self.styles["Normal"],
            fontSize=18,
            fontName="Helvetica-Bold",
            textColor=PDF_COLORS["primary"],
            alignment=TA_CENTER,
            spaceAfter=2
        )

        self.style_shop_address = ParagraphStyle(
            "ShopAddress",
            parent=self.styles["Normal"],
            fontSize=9,
            fontName="Helvetica",
            textColor=PDF_COLORS["text_dark"],
            alignment=TA_CENTER,
            spaceAfter=1
        )

        self.style_bill_title = ParagraphStyle(
            "BillTitle",
            parent=self.styles["Normal"],
            fontSize=13,
            fontName="Helvetica-Bold",
            textColor=PDF_COLORS["white"],
            alignment=TA_CENTER,
        )

        self.style_normal = ParagraphStyle(
            "Normal_",
            parent=self.styles["Normal"],
            fontSize=9,
            fontName="Helvetica",
            textColor=PDF_COLORS["text_dark"],
        )

        self.style_bold = ParagraphStyle(
            "Bold_",
            parent=self.styles["Normal"],
            fontSize=9,
            fontName="Helvetica-Bold",
            textColor=PDF_COLORS["text_dark"],
        )

        self.style_small = ParagraphStyle(
            "Small_",
            parent=self.styles["Normal"],
            fontSize=7.5,
            fontName="Helvetica",
            textColor=PDF_COLORS["text_muted"],
        )

        self.style_footer = ParagraphStyle(
            "Footer_",
            parent=self.styles["Normal"],
            fontSize=8,
            fontName="Helvetica",
            textColor=PDF_COLORS["text_muted"],
            alignment=TA_CENTER,
        )

        self.style_amount_words = ParagraphStyle(
            "AmountWords",
            parent=self.styles["Normal"],
            fontSize=8.5,
            fontName="Helvetica-Bold",
            textColor=PDF_COLORS["success"],
        )

        self.style_composition_note = ParagraphStyle(
            "CompositionNote",
            parent=self.styles["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=colors.red,
            alignment=TA_CENTER,
        )

    # ----------------------------------------------------------
    # MAIN GENERATE FUNCTION
    # ----------------------------------------------------------
    def generate_sales_bill(
        self,
        bill_data:   dict,
        bill_number: str,
        output_path: str,
        paper_size:  str = None
    ):
        """
        Generate PDF bill for a sales bill.

        Args:
            bill_data:   Bill dict from sales module
            bill_number: Bill number string
            output_path: Where to save the PDF
            paper_size:  "a4" or "thermal" or None (uses settings)
        """
        if paper_size is None:
            paper_size = self.settings.get(
                "print", {}
            ).get("paper_size", "a4")

        bill_type = bill_data.get(
            "bill_type", "regular"
        )

        # Ensure output directory exists
        Path(output_path).parent.mkdir(
            parents=True, exist_ok=True
        )

        if paper_size == "thermal":
            self._generate_thermal_bill(
                bill_data, bill_number, output_path
            )
        elif paper_size == "both":
            # Generate A4
            a4_path = output_path.replace(
                ".pdf", "_A4.pdf"
            )
            self._generate_a4_bill(
                bill_data, bill_number,
                a4_path, bill_type
            )
            # Generate thermal
            thermal_path = output_path.replace(
                ".pdf", "_thermal.pdf"
            )
            self._generate_thermal_bill(
                bill_data, bill_number, thermal_path
            )
            # Also save combined path as A4
            self._generate_a4_bill(
                bill_data, bill_number,
                output_path, bill_type
            )
        else:
            # Default A4
            self._generate_a4_bill(
                bill_data, bill_number,
                output_path, bill_type
            )

    # ----------------------------------------------------------
    # A4 BILL GENERATOR
    # ----------------------------------------------------------
    def _generate_a4_bill(
        self,
        bill_data:   dict,
        bill_number: str,
        output_path: str,
        bill_type:   str = "regular"
    ):
        """
        Generate A4 size GST bill PDF.

        Layout:
        ┌──────────────────────────────────────────┐
        │  SHOP NAME (large)                       │
        │  Address | Phone | Email | GSTIN         │
        ├─────────────────┬────────────────────────┤
        │  TAX INVOICE    │  Bill No: INV-2026-0001│
        │  (or BILL OF    │  Date: 15-06-2026      │
        │   SUPPLY for    │  GSTIN: ...            │
        │   composition)  │                        │
        ├─────────────────┴────────────────────────┤
        │  Customer Details                        │
        ├──────────────────────────────────────────┤
        │  Items Table                             │
        │  # | Item | HSN | Qty | Rate | GST | Amt│
        ├──────────────────────────────────────────┤
        │  Totals: Taxable | CGST | SGST | Total  │
        ├──────────────────────────────────────────┤
        │  Amount in Words                         │
        ├──────────────────────────────────────────┤
        │  Bank Details | Terms | Signature        │
        ├──────────────────────────────────────────┤
        │  Composition note (if applicable)        │
        └──────────────────────────────────────────┘
        """

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=12 * mm,
            bottomMargin=15 * mm,
            title=f"Tax Invoice {bill_number}",
        )

        story = []

        # ---- 1. Shop Header ----
        story += self._build_shop_header_a4()

        # ---- 2. Bill Title Bar + Bill Info ----
        story += self._build_bill_info_a4(
            bill_number, bill_data, bill_type
        )

        # ---- 3. Customer Details ----
        story += self._build_customer_section_a4(
            bill_data
        )

        # ---- 4. Items Table ----
        story += self._build_items_table_a4(
            bill_data, bill_type
        )

        # ---- 5. Totals ----
        story += self._build_totals_a4(
            bill_data, bill_type
        )

        # ---- 6. Amount in Words ----
        story += self._build_amount_words_a4(
            bill_data["grand_total"]
        )

        # ---- 7. Footer ----
        story += self._build_footer_a4(bill_type)

        # Build PDF
        doc.build(story)

    # ----------------------------------------------------------
    # SHOP HEADER
    # ----------------------------------------------------------
    def _build_shop_header_a4(self) -> list:
        """Shop name, address, GSTIN header"""
        story = []
        shop  = self.shop

        # Outer border table
        shop_name = shop.get("name", "Hardware Shop")
        owner     = shop.get("owner_name", "")
        addr1     = shop.get("address_line1", "")
        addr2     = shop.get("address_line2", "")
        city      = shop.get("city", "")
        state     = shop.get("state", "Karnataka")
        pincode   = shop.get("pincode", "")
        phone     = shop.get("phone", "")
        email     = shop.get("email", "")
        gstin     = shop.get("gstin", "")

        # Full address string
        addr_parts = [
            p for p in [addr1, addr2, city, state, pincode]
            if p
        ]
        full_addr = ", ".join(addr_parts)

        contact_parts = []
        if phone:
            contact_parts.append(f"📞 {phone}")
        if email:
            contact_parts.append(f"✉ {email}")
        contact_str = "   |   ".join(contact_parts)

        header_data = [
            [Paragraph(
                shop_name,
                self.style_shop_name
            )],
            [Paragraph(
                full_addr,
                self.style_shop_address
            )],
            [Paragraph(
                contact_str,
                self.style_shop_address
            )],
            [Paragraph(
                f"GSTIN: {gstin}",
                ParagraphStyle(
                    "gstin",
                    parent=self.styles["Normal"],
                    fontSize=9,
                    fontName="Helvetica-Bold",
                    textColor=PDF_COLORS["primary"],
                    alignment=TA_CENTER
                )
            )],
        ]

        header_table = Table(
            header_data,
            colWidths=[180 * mm]
        )
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1),
             PDF_COLORS["light_blue"]),
            ("BOX",        (0, 0), (-1, -1),
             1.5, PDF_COLORS["primary"]),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ]))

        story.append(header_table)
        story.append(Spacer(1, 3 * mm))
        return story

    # ----------------------------------------------------------
    # BILL INFO
    # ----------------------------------------------------------
    def _build_bill_info_a4(
        self,
        bill_number: str,
        bill_data:   dict,
        bill_type:   str
    ) -> list:
        """Bill title bar + bill number + date"""
        story = []

        # Title based on scheme
        if bill_type == "composition":
            title_text = "BILL OF SUPPLY"
        else:
            title_text = "TAX INVOICE"

        bill_date = format_date(bill_data["bill_date"])

        # Two-column layout
        left_data = [
            [Paragraph(
                title_text,
                self.style_bill_title
            )]
        ]

        right_data = [
            [
                Paragraph(
                    "Invoice Number:",
                    self.style_small
                ),
                Paragraph(
                    bill_number,
                    self.style_bold
                )
            ],
            [
                Paragraph(
                    "Invoice Date:",
                    self.style_small
                ),
                Paragraph(
                    bill_date,
                    self.style_bold
                )
            ],
            [
                Paragraph(
                    "State:",
                    self.style_small
                ),
                Paragraph(
                    "Karnataka (29)",
                    self.style_normal
                )
            ],
        ]

        left_table = Table(
            left_data,
            colWidths=[65 * mm]
        )
        left_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1),
             PDF_COLORS["primary"]),
            ("VALIGN",     (0, 0), (-1, -1),
             "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))

        right_table = Table(
            right_data,
            colWidths=[35 * mm, 75 * mm]
        )
        right_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1),
             PDF_COLORS["light_grey"]),
            ("FONTNAME",   (0, 0), (0, -1),
             "Helvetica"),
            ("FONTSIZE",   (0, 0), (-1, -1), 8.5),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ]))

        # Combine
        combined = Table(
            [[left_table, right_table]],
            colWidths=[65 * mm, 115 * mm]
        )
        combined.setStyle(TableStyle([
            ("BOX",    (0, 0), (-1, -1),
             1, PDF_COLORS["primary"]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

        story.append(combined)
        story.append(Spacer(1, 3 * mm))
        return story

    # ----------------------------------------------------------
    # CUSTOMER SECTION
    # ----------------------------------------------------------
    def _build_customer_section_a4(
        self, bill_data: dict
    ) -> list:
        """Customer name, city details"""
        story   = []
        cust    = bill_data.get("customer", {})
        name    = cust.get("name", "Cash Customer")
        city    = cust.get("city", "")
        phone   = cust.get("phone", "")
        address = cust.get("address", "")

        cust_lines = [
            [
                Paragraph(
                    "Bill To:",
                    ParagraphStyle(
                        "bt",
                        parent=self.styles["Normal"],
                        fontSize=8,
                        fontName="Helvetica",
                        textColor=PDF_COLORS["text_muted"]
                    )
                ),
                Paragraph("", self.style_normal),
            ],
            [
                Paragraph(
                    name,
                    ParagraphStyle(
                        "cname",
                        parent=self.styles["Normal"],
                        fontSize=11,
                        fontName="Helvetica-Bold",
                        textColor=PDF_COLORS["primary"]
                    )
                ),
                Paragraph("", self.style_normal),
            ],
        ]

        addr_parts = [
            p for p in [address, city, "Karnataka"]
            if p
        ]
        if addr_parts:
            cust_lines.append([
                Paragraph(
                    ", ".join(addr_parts),
                    self.style_normal
                ),
                Paragraph("", self.style_normal),
            ])

        if phone:
            cust_lines.append([
                Paragraph(
                    f"Phone: {phone}",
                    self.style_small
                ),
                Paragraph("", self.style_normal),
            ])

        cust_table = Table(
            cust_lines,
            colWidths=[100 * mm, 80 * mm]
        )
        cust_table.setStyle(TableStyle([
            ("BOX",      (0, 0), (-1, -1),
             0.8, PDF_COLORS["border"]),
            ("LINEBELOW",(0, -1), (-1, -1),
             0.5, PDF_COLORS["border"]),
            ("LEFTPADDING",
             (0, 0), (-1, -1), 10),
            ("TOPPADDING",
             (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",
             (0, 0), (-1, -1), 3),
            ("BACKGROUND",
             (0, 0), (-1, -1),
             PDF_COLORS["light_grey"]),
        ]))

        story.append(cust_table)
        story.append(Spacer(1, 3 * mm))
        return story

    # ----------------------------------------------------------
    # ITEMS TABLE
    # ----------------------------------------------------------
    def _build_items_table_a4(
        self,
        bill_data: dict,
        bill_type: str
    ) -> list:
        """Main items table with GST columns"""
        story = []
        items = bill_data.get("items", [])

        # Build header row
        if bill_type == "composition":
            # Composition — no tax columns
            headers = [
                "#", "Item Description",
                "HSN", "Qty", "Unit",
                "Rate (₹)", "Amount (₹)"
            ]
            col_widths = [
                8*mm, 65*mm, 16*mm, 14*mm,
                14*mm, 22*mm, 22*mm
            ]
        else:
            # Regular GST — with tax columns
            headers = [
                "#", "Item Description",
                "HSN", "Qty", "Unit",
                "Rate (₹)", "Taxable (₹)",
                "CGST", "SGST", "Total (₹)"
            ]
            col_widths = [
                7*mm, 52*mm, 14*mm, 12*mm,
                12*mm, 18*mm, 20*mm,
                16*mm, 16*mm, 18*mm
            ]

        # Header style
        header_style = ParagraphStyle(
            "TH",
            parent=self.styles["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=PDF_COLORS["white"],
            alignment=TA_CENTER
        )

        header_row = [
            Paragraph(h, header_style)
            for h in headers
        ]

        # Data rows
        data_rows = [header_row]

        for i, item in enumerate(items):
            qty      = item.get("quantity", 0)
            rate     = item.get("selling_rate", 0)
            taxable  = round2(qty * rate)
            cgst_r   = item.get("cgst_rate", 9)
            sgst_r   = item.get("sgst_rate", 9)
            cgst_amt = item.get("cgst_amount", 0)
            sgst_amt = item.get("sgst_amount", 0)
            total    = item.get("total_amount", 0)
            hsn      = item.get("hsn_code", "-")

            # Format quantity
            if qty == int(qty):
                qty_str = str(int(qty))
            else:
                qty_str = f"{qty:.2f}"

            cell_style = ParagraphStyle(
                "TD",
                parent=self.styles["Normal"],
                fontSize=8,
                fontName="Helvetica",
                textColor=PDF_COLORS["text_dark"]
            )
            center_style = ParagraphStyle(
                "TDC",
                parent=self.styles["Normal"],
                fontSize=8,
                fontName="Helvetica",
                textColor=PDF_COLORS["text_dark"],
                alignment=TA_CENTER
            )
            right_style = ParagraphStyle(
                "TDR",
                parent=self.styles["Normal"],
                fontSize=8,
                fontName="Helvetica",
                textColor=PDF_COLORS["text_dark"],
                alignment=TA_RIGHT
            )

            if bill_type == "composition":
                row = [
                    Paragraph(
                        str(i + 1), center_style
                    ),
                    Paragraph(
                        item.get("item_name", ""),
                        cell_style
                    ),
                    Paragraph(
                        hsn if hsn != "-" else "",
                        center_style
                    ),
                    Paragraph(qty_str, center_style),
                    Paragraph(
                        item.get("unit", ""), center_style
                    ),
                    Paragraph(
                        f"{rate:.2f}", right_style
                    ),
                    Paragraph(
                        f"{total:.2f}", right_style
                    ),
                ]
            else:
                row = [
                    Paragraph(
                        str(i + 1), center_style
                    ),
                    Paragraph(
                        item.get("item_name", ""),
                        cell_style
                    ),
                    Paragraph(
                        hsn if hsn != "-" else "",
                        center_style
                    ),
                    Paragraph(qty_str, center_style),
                    Paragraph(
                        item.get("unit", ""),
                        center_style
                    ),
                    Paragraph(
                        f"{rate:.2f}", right_style
                    ),
                    Paragraph(
                        f"{taxable:.2f}", right_style
                    ),
                    Paragraph(
                        f"{cgst_r:.0f}%\n₹{cgst_amt:.2f}",
                        center_style
                    ),
                    Paragraph(
                        f"{sgst_r:.0f}%\n₹{sgst_amt:.2f}",
                        center_style
                    ),
                    Paragraph(
                        f"{total:.2f}", right_style
                    ),
                ]

            data_rows.append(row)

        # Empty rows to fill space (min 8 rows)
        while len(data_rows) < 9:
            if bill_type == "composition":
                data_rows.append(
                    ["", "", "", "", "", "", ""]
                )
            else:
                data_rows.append(
                    ["", "", "", "", "", "", "", "", "", ""]
                )

        # Build table
        items_table = Table(
            data_rows,
            colWidths=col_widths,
            repeatRows=1
        )

        # Table styling
        style_cmds = [
            # Header
            ("BACKGROUND", (0, 0), (-1, 0),
             PDF_COLORS["primary"]),
            ("TEXTCOLOR",  (0, 0), (-1, 0),
             PDF_COLORS["white"]),
            ("FONTNAME",   (0, 0), (-1, 0),
             "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, 0), 8),

            # All rows
            ("FONTNAME",   (0, 1), (-1, -1),
             "Helvetica"),
            ("FONTSIZE",   (0, 1), (-1, -1), 8),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),

            # Borders
            ("BOX",        (0, 0), (-1, -1),
             1, PDF_COLORS["primary"]),
            ("INNERGRID",  (0, 0), (-1, -1),
             0.3, PDF_COLORS["border"]),

            # Padding
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),

            # Align number columns right
            ("ALIGNMENT",  (5, 1), (-1, -1), "RIGHT"),
            ("ALIGNMENT",  (0, 0), (4, -1),  "CENTER"),
            ("ALIGNMENT",  (1, 1), (1, -1),  "LEFT"),
        ]

        # Alternating row colors
        for i in range(1, len(data_rows)):
            if i % 2 == 0:
                style_cmds.append((
                    "BACKGROUND",
                    (0, i), (-1, i),
                    PDF_COLORS["row_even"]
                ))

        items_table.setStyle(TableStyle(style_cmds))

        story.append(items_table)
        story.append(Spacer(1, 2 * mm))
        return story

    # ----------------------------------------------------------
    # TOTALS SECTION
    # ----------------------------------------------------------
    def _build_totals_a4(
        self,
        bill_data: dict,
        bill_type: str
    ) -> list:
        """Totals table: taxable + GST + grand total"""
        story = []

        subtotal   = bill_data.get("subtotal", 0)
        total_cgst = bill_data.get("total_cgst", 0)
        total_sgst = bill_data.get("total_sgst", 0)
        grand      = bill_data.get("grand_total", 0)

        right_style = ParagraphStyle(
            "TR",
            parent=self.styles["Normal"],
            fontSize=9,
            fontName="Helvetica",
            alignment=TA_RIGHT,
            textColor=PDF_COLORS["text_dark"]
        )
        right_bold = ParagraphStyle(
            "TRB",
            parent=self.styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT,
            textColor=PDF_COLORS["white"]
        )
        label_style = ParagraphStyle(
            "TL",
            parent=self.styles["Normal"],
            fontSize=9,
            fontName="Helvetica",
            textColor=PDF_COLORS["text_muted"],
            alignment=TA_RIGHT
        )
        label_bold = ParagraphStyle(
            "TLB",
            parent=self.styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            textColor=PDF_COLORS["white"],
            alignment=TA_RIGHT
        )

        if bill_type == "composition":
            totals_data = [
                [
                    Paragraph(
                        "Total Amount:", label_style
                    ),
                    Paragraph(
                        f"₹ {grand:,.2f}", right_style
                    ),
                ],
                [
                    Paragraph(
                        "GRAND TOTAL:", label_bold
                    ),
                    Paragraph(
                        f"₹ {grand:,.2f}", right_bold
                    ),
                ],
            ]
        else:
            totals_data = [
                [
                    Paragraph(
                        "Taxable Amount:", label_style
                    ),
                    Paragraph(
                        f"₹ {subtotal:,.2f}",
                        right_style
                    ),
                ],
                [
                    Paragraph(
                        f"CGST ({total_cgst / subtotal * 100:.0f}% avg):"
                        if subtotal > 0 else "CGST:",
                        label_style
                    ),
                    Paragraph(
                        f"₹ {total_cgst:,.2f}",
                        right_style
                    ),
                ],
                [
                    Paragraph(
                        f"SGST ({total_sgst / subtotal * 100:.0f}% avg):"
                        if subtotal > 0 else "SGST:",
                        label_style
                    ),
                    Paragraph(
                        f"₹ {total_sgst:,.2f}",
                        right_style
                    ),
                ],
                [
                    Paragraph(
                        "GRAND TOTAL:", label_bold
                    ),
                    Paragraph(
                        f"₹ {grand:,.2f}", right_bold
                    ),
                ],
            ]

        # Right-align the totals table
        totals_table = Table(
            totals_data,
            colWidths=[80 * mm, 40 * mm]
        )

        style_cmds = [
            ("ALIGN",      (0, 0), (-1, -1), "RIGHT"),
            ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEABOVE",  (0, -1), (-1, -1),
             1.5, PDF_COLORS["primary"]),
            ("BACKGROUND", (0, -1), (-1, -1),
             PDF_COLORS["primary"]),
            ("BOX",        (0, 0), (-1, -1),
             0.8, PDF_COLORS["border"]),
        ]

        totals_table.setStyle(TableStyle(style_cmds))

        # Wrap in a right-aligned container
        wrapper = Table(
            [[Paragraph("", self.style_normal),
              totals_table]],
            colWidths=[60 * mm, 120 * mm]
        )
        wrapper.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ]))

        story.append(wrapper)
        story.append(Spacer(1, 3 * mm))
        return story

    # ----------------------------------------------------------
    # AMOUNT IN WORDS
    # ----------------------------------------------------------
    def _build_amount_words_a4(
        self, amount: float
    ) -> list:
        """Amount in words section"""
        story = []

        words = amount_in_words(amount)

        aw_data = [[
            Paragraph(
                "Amount in Words:",
                ParagraphStyle(
                    "AWL",
                    parent=self.styles["Normal"],
                    fontSize=8,
                    fontName="Helvetica",
                    textColor=PDF_COLORS["text_muted"]
                )
            ),
            Paragraph(
                words,
                self.style_amount_words
            )
        ]]

        aw_table = Table(
            aw_data,
            colWidths=[35 * mm, 145 * mm]
        )
        aw_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1),
             PDF_COLORS["light_green"]),
            ("BOX",        (0, 0), (-1, -1),
             0.8, PDF_COLORS["success"]),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))

        story.append(aw_table)
        story.append(Spacer(1, 3 * mm))
        return story

    # ----------------------------------------------------------
    # FOOTER
    # ----------------------------------------------------------
    def _build_footer_a4(
        self, bill_type: str
    ) -> list:
        """Bank details, terms, signature, legal notes"""
        story = []
        bank  = self.bank
        shop  = self.shop

        # Three-column footer
        # Left: Bank Details
        # Center: Terms & Conditions
        # Right: Signature

        bank_name = bank.get("bank_name", "")
        acc_name  = bank.get("account_name", "")
        acc_no    = bank.get("account_no", "")
        ifsc      = bank.get("ifsc", "")
        branch    = bank.get("branch", "")

        bank_content = []
        if bank_name:
            bank_content.append(
                f"<b>Bank:</b> {bank_name}"
            )
        if acc_name:
            bank_content.append(
                f"<b>A/C Name:</b> {acc_name}"
            )
        if acc_no:
            bank_content.append(
                f"<b>A/C No:</b> {acc_no}"
            )
        if ifsc:
            bank_content.append(
                f"<b>IFSC:</b> {ifsc}"
            )
        if branch:
            bank_content.append(
                f"<b>Branch:</b> {branch}"
            )

        bank_text = (
            "<br/>".join(bank_content)
            if bank_content
            else "N/A"
        )

        bank_para = Paragraph(
            f"<b>Bank Details:</b><br/>{bank_text}",
            self.style_small
        )

        terms_text = (
            "1. Goods once sold will not be taken back.<br/>"
            "2. Subject to local jurisdiction.<br/>"
            "3. E. &amp; O.E.<br/>"
            "4. Payment due on delivery."
        )
        terms_para = Paragraph(
            f"<b>Terms &amp; Conditions:</b><br/>"
            f"{terms_text}",
            self.style_small
        )

        sig_para = Paragraph(
            f"<br/><br/><br/>"
            f"_______________________<br/>"
            f"<b>{shop.get('name', '')}</b><br/>"
            f"Authorised Signatory",
            ParagraphStyle(
                "sig",
                parent=self.styles["Normal"],
                fontSize=8,
                fontName="Helvetica",
                alignment=TA_CENTER
            )
        )

        footer_data = [[
            bank_para,
            terms_para,
            sig_para
        ]]

        footer_table = Table(
            footer_data,
            colWidths=[65 * mm, 70 * mm, 45 * mm]
        )
        footer_table.setStyle(TableStyle([
            ("BOX",      (0, 0), (-1, -1),
             0.8, PDF_COLORS["border"]),
            ("INNERGRID",(0, 0), (-1, -1),
             0.5, PDF_COLORS["border"]),
            ("VALIGN",   (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("BACKGROUND",
             (0, 0), (-1, -1),
             PDF_COLORS["light_grey"]),
        ]))

        story.append(footer_table)
        story.append(Spacer(1, 3 * mm))

        # Composition scheme mandatory note
        if bill_type == "composition":
            story.append(Paragraph(
                "* Composition taxable person, "
                "not eligible to collect tax on supplies.",
                self.style_composition_note
            ))
            story.append(Spacer(1, 2 * mm))

        # Bottom note
        story.append(Paragraph(
            "This is a computer-generated invoice. "
            "No signature required.",
            self.style_footer
        ))

        return story

    # ----------------------------------------------------------
    # THERMAL BILL GENERATOR
    # ----------------------------------------------------------
    def _generate_thermal_bill(
        self,
        bill_data:   dict,
        bill_number: str,
        output_path: str
    ):
        """
        Generate 80mm thermal receipt format bill.

        Layout (narrow, vertical):
        ┌──────────────────┐
        │   SHOP NAME      │
        │   Address        │
        │   Phone          │
        │   GSTIN          │
        │──────────────────│
        │  TAX INVOICE     │
        │  Bill: INV-001   │
        │  Date: 15-06-26  │
        │──────────────────│
        │  Customer: Name  │
        │──────────────────│
        │ Item    Qty  Amt │
        │ GI Pipe  10  295 │
        │ ...              │
        │──────────────────│
        │ Taxable:  ₹2500  │
        │ CGST 9%:  ₹225   │
        │ SGST 9%:  ₹225   │
        │ TOTAL:    ₹2950  │
        │──────────────────│
        │  Thank You!      │
        │  Visit Again     │
        └──────────────────┘
        """

        # Thermal page size (80mm wide, auto height)
        items     = bill_data.get("items", [])
        bill_type = bill_data.get("bill_type", "regular")

        # Estimate height based on content
        base_height = 120 * mm
        item_height = len(items) * 10 * mm
        total_height = base_height + item_height

        page_size = (THERMAL_WIDTH_PT, total_height)

        doc = SimpleDocTemplate(
            output_path,
            pagesize=page_size,
            rightMargin=THERMAL_MARGIN_PT,
            leftMargin=THERMAL_MARGIN_PT,
            topMargin=3 * mm,
            bottomMargin=5 * mm,
        )

        story = []
        shop  = self.shop
        w     = THERMAL_WIDTH_MM - 6  # usable width mm

        # Styles for thermal
        t_center = ParagraphStyle(
            "TC",
            parent=self.styles["Normal"],
            fontSize=9,
            fontName="Helvetica",
            alignment=TA_CENTER
        )
        t_bold_center = ParagraphStyle(
            "TBC",
            parent=self.styles["Normal"],
            fontSize=10,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER
        )
        t_normal = ParagraphStyle(
            "TN",
            parent=self.styles["Normal"],
            fontSize=8,
            fontName="Helvetica"
        )
        t_bold = ParagraphStyle(
            "TB",
            parent=self.styles["Normal"],
            fontSize=9,
            fontName="Helvetica-Bold"
        )
        t_right = ParagraphStyle(
            "TR",
            parent=self.styles["Normal"],
            fontSize=8,
            fontName="Helvetica",
            alignment=TA_RIGHT
        )
        t_right_bold = ParagraphStyle(
            "TRB",
            parent=self.styles["Normal"],
            fontSize=9,
            fontName="Helvetica-Bold",
            alignment=TA_RIGHT
        )

        # ---- Shop Header ----
        story.append(Paragraph(
            shop.get("name", "Hardware Shop"),
            t_bold_center
        ))

        addr_parts = [
            shop.get("address_line1", ""),
            shop.get("city", ""),
        ]
        addr = ", ".join(p for p in addr_parts if p)
        if addr:
            story.append(Paragraph(addr, t_center))

        if shop.get("phone"):
            story.append(Paragraph(
                f"Ph: {shop['phone']}", t_center
            ))

        if shop.get("gstin"):
            story.append(Paragraph(
                f"GSTIN: {shop['gstin']}", t_center
            ))

        story.append(HRFlowable(
            width=w * mm,
            thickness=0.5,
            color=PDF_COLORS["black"]
        ))

        # ---- Bill Info ----
        title = (
            "BILL OF SUPPLY"
            if bill_type == "composition"
            else "TAX INVOICE"
        )
        story.append(Paragraph(title, t_bold_center))

        story.append(Paragraph(
            f"Bill No: {bill_number}", t_normal
        ))
        story.append(Paragraph(
            f"Date: {format_date(bill_data['bill_date'])}",
            t_normal
        ))

        story.append(HRFlowable(
            width=w * mm,
            thickness=0.3,
            color=PDF_COLORS["text_muted"]
        ))

        # ---- Customer ----
        cust = bill_data.get("customer", {})
        story.append(Paragraph(
            f"To: {cust.get('name', 'Customer')}",
            t_bold
        ))
        if cust.get("city"):
            story.append(Paragraph(
                cust["city"], t_normal
            ))

        story.append(HRFlowable(
            width=w * mm,
            thickness=0.3,
            color=PDF_COLORS["text_muted"]
        ))

        # ---- Items ----
        # Header
        item_hdr = Table(
            [[
                Paragraph("Item", t_bold),
                Paragraph("Qty", t_bold),
                Paragraph("Rate", t_right_bold),
                Paragraph("Amt", t_right_bold),
            ]],
            colWidths=[
                (w * 0.40) * mm,
                (w * 0.15) * mm,
                (w * 0.20) * mm,
                (w * 0.25) * mm,
            ]
        )
        item_hdr.setStyle(TableStyle([
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LINEBELOW",  (0, -1), (-1, -1),
             0.3, PDF_COLORS["black"]),
        ]))
        story.append(item_hdr)

        # Item rows
        for item in items:
            qty = item.get("quantity", 0)
            if qty == int(qty):
                qty_str = str(int(qty))
            else:
                qty_str = f"{qty:.1f}"

            rate  = item.get("selling_rate", 0)
            total = item.get("total_amount", 0)
            name  = item.get("item_name", "")

            # Truncate long names
            if len(name) > 22:
                name = name[:20] + ".."

            row = Table(
                [[
                    Paragraph(name, t_normal),
                    Paragraph(qty_str, t_normal),
                    Paragraph(
                        f"{rate:.0f}", t_right
                    ),
                    Paragraph(
                        f"{total:.0f}", t_right
                    ),
                ]],
                colWidths=[
                    (w * 0.40) * mm,
                    (w * 0.15) * mm,
                    (w * 0.20) * mm,
                    (w * 0.25) * mm,
                ]
            )
            row.setStyle(TableStyle([
                ("FONTSIZE",
                 (0, 0), (-1, -1), 8),
                ("TOPPADDING",
                 (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING",
                 (0, 0), (-1, -1), 2),
            ]))
            story.append(row)

        story.append(HRFlowable(
            width=w * mm,
            thickness=0.5,
            color=PDF_COLORS["black"]
        ))

        # ---- Totals ----
        subtotal   = bill_data.get("subtotal", 0)
        total_cgst = bill_data.get("total_cgst", 0)
        total_sgst = bill_data.get("total_sgst", 0)
        grand      = bill_data.get("grand_total", 0)

        def total_row(label, value, bold=False):
            sty = t_right_bold if bold else t_right
            lsty = t_bold if bold else t_normal
            return Table(
                [[
                    Paragraph(label, lsty),
                    Paragraph(f"₹{value:.2f}", sty),
                ]],
                colWidths=[
                    (w * 0.6) * mm,
                    (w * 0.4) * mm,
                ]
            )

        if bill_type != "composition":
            story.append(
                total_row("Taxable Amt:", subtotal)
            )
            story.append(
                total_row("CGST:", total_cgst)
            )
            story.append(
                total_row("SGST:", total_sgst)
            )

        story.append(HRFlowable(
            width=w * mm,
            thickness=0.5,
            color=PDF_COLORS["black"]
        ))
        story.append(
            total_row("TOTAL:", grand, bold=True)
        )
        story.append(HRFlowable(
            width=w * mm,
            thickness=0.5,
            color=PDF_COLORS["black"]
        ))

        # Composition note
        if bill_type == "composition":
            story.append(Paragraph(
                "* Composition taxable person, "
                "not eligible to collect tax on supplies.",
                ParagraphStyle(
                    "CN",
                    parent=self.styles["Normal"],
                    fontSize=7,
                    fontName="Helvetica",
                    textColor=colors.red,
                    alignment=TA_CENTER
                )
            ))

        # Thank you
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            "Thank You! Visit Again.",
            t_bold_center
        ))
        story.append(Paragraph(
            "Computer generated bill.",
            t_center
        ))

        doc.build(story)


# ============================================================
# PURCHASE SUMMARY PDF
# ============================================================
def generate_purchase_summary_pdf(
    month: int,
    year: int,
    output_path: str,
    settings: dict = None
):
    """
    Generate a purchase summary PDF for a month.
    Shows all dealer bills and item pool.
    """
    if settings is None:
        settings = load_settings()

    import sqlite3
    DB_PATH = BASE_DIR / "database" / "shop_database.db"

    MONTH_NAMES = [
        "", "January", "February", "March",
        "April", "May", "June", "July",
        "August", "September", "October",
        "November", "December"
    ]

    def query(sql, params=()):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur  = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    bills = query("""
        SELECT pb.*, COUNT(pi.id) AS item_count
        FROM purchase_bills pb
        LEFT JOIN purchase_items pi
            ON pi.purchase_bill_id = pb.id
        WHERE pb.bill_month=? AND pb.bill_year=?
        GROUP BY pb.id
        ORDER BY pb.bill_date
    """, (month, year))

    items_pool = query("""
        SELECT
            pi.item_name,
            pi.hsn_code,
            pi.unit,
            pi.gst_rate,
            SUM(pi.quantity)      AS total_qty,
            SUM(pi.remaining_qty) AS remaining,
            AVG(pi.purchase_rate) AS avg_rate,
            SUM(pi.total_amount)  AS total_amount
        FROM purchase_items pi
        JOIN purchase_bills pb
            ON pi.purchase_bill_id = pb.id
        WHERE pb.bill_month=? AND pb.bill_year=?
        GROUP BY pi.item_name, pi.unit
        ORDER BY pi.item_name
    """, (month, year))

    totals = query("""
        SELECT
            COALESCE(SUM(subtotal),    0) AS taxable,
            COALESCE(SUM(total_gst),   0) AS gst,
            COALESCE(SUM(grand_total), 0) AS total,
            COUNT(*) AS cnt
        FROM purchase_bills
        WHERE bill_month=? AND bill_year=?
    """, (month, year))

    t = totals[0] if totals else {}

    shop  = settings.get("shop", {})
    gen   = PDFGenerator(settings)
    story = []

    # Header
    story += gen._build_shop_header_a4()
    story.append(Paragraph(
        f"PURCHASE SUMMARY — "
        f"{MONTH_NAMES[month].upper()} {year}",
        ParagraphStyle(
            "PS",
            parent=getSampleStyleSheet()["Normal"],
            fontSize=13,
            fontName="Helvetica-Bold",
            textColor=PDF_COLORS["primary"],
            alignment=TA_CENTER
        )
    ))
    story.append(Spacer(1, 5 * mm))

    # Summary stats
    stats_data = [[
        Paragraph(
            f"<b>Total Bills:</b> {t.get('cnt', 0)}",
            gen.style_normal
        ),
        Paragraph(
            f"<b>Taxable Amount:</b> "
            f"₹{t.get('taxable', 0):,.2f}",
            gen.style_normal
        ),
        Paragraph(
            f"<b>Total GST:</b> "
            f"₹{t.get('gst', 0):,.2f}",
            gen.style_normal
        ),
        Paragraph(
            f"<b>Grand Total:</b> "
            f"₹{t.get('total', 0):,.2f}",
            ParagraphStyle(
                "GT",
                parent=getSampleStyleSheet()["Normal"],
                fontSize=10,
                fontName="Helvetica-Bold",
                textColor=PDF_COLORS["success"]
            )
        ),
    ]]

    stats_table = Table(
        stats_data,
        colWidths=[40*mm, 50*mm, 45*mm, 45*mm]
    )
    stats_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1),
         PDF_COLORS["light_blue"]),
        ("BOX",        (0, 0), (-1, -1),
         1, PDF_COLORS["primary"]),
        ("INNERGRID",  (0, 0), (-1, -1),
         0.3, PDF_COLORS["border"]),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 5 * mm))

    # Bills list
    story.append(Paragraph(
        "Purchase Bills",
        ParagraphStyle(
            "BH",
            parent=getSampleStyleSheet()["Normal"],
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=PDF_COLORS["primary"]
        )
    ))
    story.append(Spacer(1, 2 * mm))

    bill_headers = [
        "#", "Dealer Name", "Bill No",
        "Date", "Items", "Taxable (₹)",
        "GST (₹)", "Total (₹)"
    ]
    bill_rows = [[
        Paragraph(h, ParagraphStyle(
            "BHR",
            parent=getSampleStyleSheet()["Normal"],
            fontSize=8,
            fontName="Helvetica-Bold",
            textColor=PDF_COLORS["white"],
            alignment=TA_CENTER
        ))
        for h in bill_headers
    ]]

    for i, b in enumerate(bills):
        row = [
            str(i + 1),
            b["dealer_name"],
            b["bill_number"],
            b["bill_date"],
            str(b["item_count"]),
            f"{b['subtotal']:,.2f}",
            f"{b['total_gst']:,.2f}",
            f"{b['grand_total']:,.2f}",
        ]
        bill_rows.append(row)

    bill_table = Table(
        bill_rows,
        colWidths=[
            8*mm, 45*mm, 25*mm, 22*mm,
            12*mm, 25*mm, 22*mm, 22*mm
        ]
    )
    bill_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0),
         PDF_COLORS["primary"]),
        ("FONTNAME",   (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("BOX",        (0, 0), (-1, -1),
         0.8, PDF_COLORS["primary"]),
        ("INNERGRID",  (0, 0), (-1, -1),
         0.3, PDF_COLORS["border"]),
        ("ALIGN",      (4, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
    ]))
    story.append(bill_table)

    # Build doc
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=12*mm,
        bottomMargin=15*mm,
    )
    doc.build(story)