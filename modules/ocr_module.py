# modules/ocr_module.py
# ============================================================
# OCR MODULE
# Extracts item data from uploaded purchase bill images/PDFs
#
# Features:
# 1. Image OCR via Tesseract
# 2. PDF text extraction (digital PDFs — no OCR needed)
# 3. PDF image extraction (scanned PDFs — needs OCR)
# 4. Smart text parser — finds items, qty, rate, HSN, GST
# 5. Returns structured list of items
# 6. Always shows result for manual review/correction
#
# IMPORTANT:
# OCR is a HELPER — not guaranteed to be 100% accurate.
# Father must ALWAYS review extracted data before saving.
# ============================================================

import re
import json
from pathlib import Path
from typing import Optional

# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).parent.parent
HSN_PATH = BASE_DIR / "data" / "hsn_master.json"

# ============================================================
# COMMON HARDWARE ITEM PATTERNS
# Used to identify items in OCR text
# ============================================================
HARDWARE_KEYWORDS = [
    # Pipes
    "pipe", "gi pipe", "pvc pipe", "cpvc", "upvc",
    "hdpe", "column pipe", "casing pipe",
    # Fittings
    "elbow", "tee", "coupling", "reducer", "union",
    "flange", "nipple", "socket", "bend",
    # Valves
    "valve", "ball valve", "gate valve", "check valve",
    "globe valve", "butterfly valve", "tap", "faucet",
    # Cement & Building
    "cement", "opc", "ppc", "white cement",
    "rod", "ms rod", "tmt", "bar", "steel",
    "wire", "binding wire",
    # Hardware
    "nail", "screw", "bolt", "nut", "washer",
    "anchor", "rawl plug", "hook", "hinge",
    "lock", "padlock", "handle", "knob",
    # Paint
    "paint", "primer", "putty", "distemper",
    "enamel", "emulsion", "varnish", "thinner",
    # Electrical
    "switch", "socket", "wire", "cable",
    "conduit", "mcb", "fuse", "holder",
    # Tools
    "hammer", "spanner", "wrench", "plier",
    "tape", "drill", "cutter", "saw",
    # Sanitary
    "basin", "sink", "commode", "seat",
    "shower", "mixer", "cistern",
]

# ============================================================
# GST RATES SET — for validation
# ============================================================
VALID_GST_RATES = {0, 5, 12, 18, 28}

# ============================================================
# UNITS MAPPING
# Standardize various unit spellings
# ============================================================
UNIT_MAP = {
    "pcs":    "piece",  "pc":     "piece",
    "pieces": "piece",  "nos":    "piece",
    "no":     "piece",  "number": "piece",
    "kgs":    "kg",     "k.g":    "kg",
    "k.g.":   "kg",     "kilogram":"kg",
    "mtr":    "meter",  "mtrs":   "meter",
    "mts":    "meter",  "mt":     "meter",
    "metre":  "meter",  "metres": "meter",
    "ltr":    "liter",  "ltrs":   "liter",
    "l":      "liter",  "litre":  "liter",
    "litres": "liter",
    "bags":   "bag",    "bgs":    "bag",
    "rolls":  "roll",   "rls":    "roll",
    "sheets": "sheet",  "sht":    "sheet",
    "sets":   "set",    "pairs":  "pair",
    "boxes":  "box",    "bx":     "box",
    "bundle": "bundle", "bdl":    "bundle",
    "bundles":"bundle",
}


# ============================================================
# OCR EXTRACTOR CLASS
# ============================================================
class OCRExtractor:
    """
    Extracts structured item data from bill images and PDFs.

    Usage:
        extractor = OCRExtractor()
        items = extractor.extract_from_image("bill.jpg")
        items = extractor.extract_from_pdf("bill.pdf")

    Returns list of dicts:
        [
            {
                "item_name": "GI Pipe 1 inch",
                "hsn_code": "7306",
                "quantity": 10.0,
                "unit": "piece",
                "rate": 250.0,
                "gst_rate": 18.0,
                "gst_amount": 450.0,
                "total": 2950.0,
                "confidence": "high"/"medium"/"low"
            },
            ...
        ]
    """

    def __init__(self):
        self.hsn_lookup = self._load_hsn_lookup()


    # ----------------------------------------------------------
    # HSN LOOKUP
    # ----------------------------------------------------------
    def _load_hsn_lookup(self) -> dict:
        """
        Build a flat keyword → HSN/GST mapping from hsn_master.json
        Used to auto-assign HSN when not found in bill text
        """
        lookup = {}
        try:
            with open(HSN_PATH, "r") as f:
                data = json.load(f)

            for category, items in data.items():
                for item in items:
                    desc = item["description"].lower()
                    words = desc.split()
                    for word in words:
                        if len(word) > 3:
                            lookup[word] = {
                                "hsn":      item["hsn"],
                                "gst_rate": item["gst_rate"]
                            }
        except Exception as e:
            print(f"[OCR] HSN load error: {e}")

        return lookup


    # ----------------------------------------------------------
    # EXTRACT FROM IMAGE
    # ----------------------------------------------------------
    def extract_from_image(self, image_path: str) -> list:
        """
        Extract items from a bill image using Tesseract OCR.

        Steps:
        1. Load and preprocess image
        2. Run Tesseract OCR
        3. Parse extracted text
        4. Return structured items
        """
        try:
            import pytesseract
            from PIL import Image, ImageEnhance, ImageFilter
        except ImportError:
            raise ImportError(
                "pytesseract and Pillow are required.\n"
                "Run: pip install pytesseract Pillow"
            )

        print(f"[OCR] Processing image: {image_path}")

        # ---- Load image ----
        img = Image.open(image_path)

        # ---- Preprocess for better OCR ----
        img = self._preprocess_image(img)

        # ---- Run OCR ----
        # Config: treat as single block of text,
        # use English language
        custom_config = (
            r'--oem 3 --psm 6 '
            r'-l eng '
            r'--dpi 300'
        )

        try:
            text = pytesseract.image_to_string(
                img,
                config=custom_config
            )
        except Exception as e:
            raise Exception(f"Tesseract OCR failed: {e}\n"
                            "Make sure Tesseract is installed.")

        print(f"[OCR] Raw text length: {len(text)} chars")
        print(f"[OCR] Raw text preview:\n{text[:500]}")

        # ---- Parse text ----
        items = self._parse_bill_text(text)
        return items


    def _preprocess_image(self, img):
        """
        Preprocess image to improve OCR accuracy.

        Steps:
        1. Convert to greyscale
        2. Increase contrast
        3. Sharpen
        4. Resize if too small (OCR needs minimum resolution)
        """
        from PIL import Image, ImageEnhance, ImageFilter

        # Convert to RGB if needed
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Resize if image is too small
        w, h = img.size
        if w < 1000:
            scale = 1000 / w
            img = img.resize(
                (int(w * scale), int(h * scale)),
                Image.LANCZOS
            )

        # Convert to greyscale
        img = img.convert("L")

        # Increase contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        # Threshold (binarize) for cleaner text
        img = img.point(lambda p: 255 if p > 128 else 0)

        return img


    # ----------------------------------------------------------
    # EXTRACT FROM PDF
    # ----------------------------------------------------------
    def extract_from_pdf(self, pdf_path: str) -> list:
        """
        Extract items from a PDF bill.

        Strategy:
        1. Try digital text extraction first (PyMuPDF)
           → Works for computer-generated PDFs
        2. If no text found, fall back to image OCR
           → Works for scanned PDFs
        """
        print(f"[OCR] Processing PDF: {pdf_path}")

        # ---- Try digital text extraction ----
        text = self._extract_pdf_text(pdf_path)

        if text and len(text.strip()) > 50:
            print(
                f"[OCR] Digital PDF detected. "
                f"Text length: {len(text)}"
            )
            items = self._parse_bill_text(text)
            if items:
                return items

        # ---- Fall back to image OCR ----
        print("[OCR] Falling back to image OCR for PDF...")
        return self._extract_pdf_as_images(pdf_path)


    def _extract_pdf_text(self, pdf_path: str) -> str:
        """
        Extract digital text from PDF using PyMuPDF (fitz).
        Fast and accurate for computer-generated PDFs.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            print("[OCR] PyMuPDF not installed. "
                  "Run: pip install PyMuPDF")
            return ""

        try:
            doc  = fitz.open(pdf_path)
            text = ""

            for page_num in range(len(doc)):
                page = doc[page_num]
                # Extract text with layout preservation
                text += page.get_text("text")
                text += "\n--- PAGE BREAK ---\n"

            doc.close()
            return text

        except Exception as e:
            print(f"[OCR] PDF text extraction error: {e}")
            return ""


    def _extract_pdf_as_images(self, pdf_path: str) -> list:
        """
        Convert PDF pages to images and OCR each page.
        Used for scanned/image PDFs.
        """
        try:
            import fitz
            from PIL import Image
            import io
        except ImportError:
            raise ImportError(
                "PyMuPDF required. Run: pip install PyMuPDF"
            )

        all_items = []

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                print(
                    f"[OCR] Processing PDF page "
                    f"{page_num + 1}/{len(doc)}"
                )
                page = doc[page_num]

                # Render page to image at 300 DPI
                mat  = fitz.Matrix(300 / 72, 300 / 72)
                pix  = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")

                # Convert to PIL Image
                img = Image.open(io.BytesIO(img_data))

                # Preprocess and OCR
                img = self._preprocess_image(img)

                try:
                    import pytesseract
                    text = pytesseract.image_to_string(
                        img,
                        config=r'--oem 3 --psm 6 -l eng'
                    )
                    items = self._parse_bill_text(text)
                    all_items.extend(items)
                except Exception as e:
                    print(f"[OCR] Page OCR error: {e}")

            doc.close()

        except Exception as e:
            print(f"[OCR] PDF image extraction error: {e}")

        # Merge duplicate items from multi-page
        return self._merge_duplicate_items(all_items)


    # ----------------------------------------------------------
    # TEXT PARSER — CORE LOGIC
    # ----------------------------------------------------------
    def _parse_bill_text(self, text: str) -> list:
        """
        Parse raw OCR/PDF text and extract structured items.

        Strategy:
        1. Split text into lines
        2. Try table row patterns (most dealer bills are tables)
        3. Try item-description patterns
        4. Try amount-based detection
        5. Validate and clean results
        """
        if not text or len(text.strip()) < 10:
            return []

        lines = [
            line.strip()
            for line in text.split("\n")
            if line.strip()
        ]

        print(f"[OCR] Total lines to parse: {len(lines)}")

        items = []

        # ---- Strategy 1: Full table row pattern ----
        # Pattern: Item Name | HSN | Qty | Unit | Rate | GST | Total
        items = self._parse_table_rows(lines)

        if items:
            print(
                f"[OCR] Strategy 1 found {len(items)} items"
            )
            return self._post_process(items)

        # ---- Strategy 2: Partial table (no HSN column) ----
        items = self._parse_partial_table(lines)

        if items:
            print(
                f"[OCR] Strategy 2 found {len(items)} items"
            )
            return self._post_process(items)

        # ---- Strategy 3: Item + amount on same line ----
        items = self._parse_item_amount_lines(lines)

        if items:
            print(
                f"[OCR] Strategy 3 found {len(items)} items"
            )
            return self._post_process(items)

        print("[OCR] No items found by any strategy")
        return []


    # ----------------------------------------------------------
    # STRATEGY 1: Full Table Row
    # ----------------------------------------------------------
    def _parse_table_rows(self, lines: list) -> list:
        """
        Parse lines that look like full table rows.

        Expected pattern (in any order):
        ItemName  HSN  Qty  Unit  Rate  GST%  Total

        Examples:
        "GI Pipe 1inch  7306  10  pcs  250.00  18  2950.00"
        "Cement OPC 50kg  2523  5  bags  350  28  2240"
        """
        items = []

        # Pattern for a table row with numbers
        # Looks for: text ... number ... number ... number
        row_pattern = re.compile(
            r'^(.+?)\s+'           # Item name (anything)
            r'(\d{4})?\s*'         # Optional HSN (4 digits)
            r'(\d+\.?\d*)\s+'      # Quantity
            r'([a-zA-Z.]+)?\s*'    # Optional unit
            r'(\d+\.?\d*)\s+'      # Rate
            r'(0|5|12|18|28)?\s*'  # Optional GST%
            r'(\d+\.?\d*)\s*$'     # Total
        )

        for line in lines:
            # Skip header lines
            if self._is_header_line(line):
                continue

            match = row_pattern.match(line)
            if not match:
                # Try simplified: name + 3 numbers
                match = self._try_three_number_line(line)

            if match:
                item = self._extract_from_match(match, line)
                if item and self._is_valid_item(item):
                    items.append(item)

        return items


    def _try_three_number_line(
        self, line: str
    ) -> Optional[re.Match]:
        """
        Try to match: [Item Name] [Number] [Number] [Number]
        The three numbers are qty, rate, total
        """
        pattern = re.compile(
            r'^([a-zA-Z][a-zA-Z0-9\s\-\.\/\\()\'"]+?)'
            r'\s+'
            r'(\d+\.?\d*)'  # number 1 — qty
            r'\s+'
            r'(\d+\.?\d*)'  # number 2 — rate
            r'\s+'
            r'(\d+\.?\d*)'  # number 3 — total/gst_amt
            r'\s*$'
        )
        return pattern.match(line.strip())


    def _extract_from_match(self, match, original_line):
        try:
            groups = match.groups()

            if len(groups) >= 7:
                # Full match: name, hsn, qty, unit, rate, gst, total
                item_name = groups[0].strip()
                hsn_code  = groups[1] or "-"
                quantity  = float(groups[2])
                unit      = self._normalize_unit(groups[3] or "piece")
                # ── CHANGED: ignore groups[4] (bill's Rate column) ──
                gst_rate  = float(groups[5] or 18)
                total     = float(groups[6])

                # rate = total / qty (total is post-discount, incl. GST)
                if quantity > 0 and total > 0:
                    rate = round(total / quantity, 2)  # Composition scheme: no GST strip
                else:
                    return None

            elif len(groups) >= 4:
                # Partial match: name, qty, [middle], total
                item_name    = groups[0].strip()
                hsn_code     = "-"
                quantity     = float(groups[1])
                unit         = "piece"
                gst_rate     = 18
                # ── CHANGED: treat groups[3] as total ──
                total        = float(groups[3])

                if quantity > 0 and total > 0:
                    rate = round(total / quantity, 2)  # Composition scheme: no GST strip
                else:
                    return None
            else:
                return None

            if quantity <= 0 or rate <= 0:
                return None

            taxable    = quantity * rate
            gst_amt    = round(taxable * gst_rate / 100, 2)
            calc_total = round(taxable + gst_amt, 2)

            return {
                "item_name":  self._clean_item_name(item_name),
                "hsn_code":   hsn_code,
                "quantity":   quantity,
                "unit":       unit,
                "rate":       rate,       # derived from total/qty
                "gst_rate":   gst_rate,
                "gst_amount": gst_amt,
                "total":      calc_total,
                "confidence": "medium",
                "_raw_total": total,
            }
        except Exception:
            return None


    # ----------------------------------------------------------
    # STRATEGY 2: Partial Table
    # ----------------------------------------------------------
    def _parse_partial_table(self, lines: list) -> list:
        """
        Parse tables that don't have HSN column or unit column.
        Dealer bills in small shops often skip some columns.

        Pattern: ItemName  Qty  Rate  Total
        """
        items = []

        # Find lines with exactly 3-4 numbers
        number_pattern = re.compile(r'\d+\.?\d*')

        for line in lines:
            if self._is_header_line(line):
                continue
            if self._is_total_line(line):
                continue

            numbers = number_pattern.findall(line)

            if len(numbers) < 3:
                continue

            # Get the text part (before first number)
            first_num_pos = re.search(
                r'\d', line
            )
            if not first_num_pos:
                continue

            text_part = line[:first_num_pos.start()].strip()

            if not text_part or len(text_part) < 2:
                continue

            # Check if text looks like an item name
            if not self._looks_like_item(text_part):
                continue

            try:
                nums = [float(n) for n in numbers[:4]]

                # ── CHANGED: derive rate from total/qty ──
                if len(nums) == 3:
                    qty, _, total = nums          # ignore middle number (bill rate)
                    gst_rate = 18
                elif len(nums) >= 4:
                    qty = nums[0]
                    total = nums[-1]              # last number is always total
                    if nums[2] in VALID_GST_RATES:
                        gst_rate = nums[2]
                    else:
                        gst_rate = 18
                else:
                    continue

                if qty <= 0 or total <= 0:
                    continue

                # rate = total / qty (total is post-discount, incl. GST)
                rate    = round(total / qty, 2)  # Composition scheme: no GST strip
                taxable = qty * rate
                gst_amt = round(taxable * gst_rate / 100, 2)

                # Try to find HSN from item name
                hsn_info = self._guess_hsn_from_name(text_part)

                item = {
                    "item_name":  self._clean_item_name(
                        text_part
                    ),
                    "hsn_code":   hsn_info.get("hsn", "-"),
                    "quantity":   qty,
                    "unit":       "piece",
                    "rate":       rate,
                    "gst_rate":   (
                        hsn_info.get("gst_rate", gst_rate)
                    ),
                    "gst_amount": gst_amt,
                    "total":      round(taxable + gst_amt, 2),
                    "confidence": "low",
                }

                if self._is_valid_item(item):
                    items.append(item)

            except (ValueError, IndexError):
                continue

        return items


    # ----------------------------------------------------------
    # STRATEGY 3: Item + Amount Lines
    # ----------------------------------------------------------
    def _parse_item_amount_lines(self, lines: list) -> list:
        """
        Last resort: find item names near amount values.
        Groups consecutive lines and tries to pair
        item descriptions with their amounts.
        """
        items   = []
        i       = 0
        amount_pattern = re.compile(
            r'\b(\d{1,6}\.?\d{0,2})\b'
        )

        while i < len(lines):
            line = lines[i]

            # Skip headers and totals
            if (self._is_header_line(line) or
                    self._is_total_line(line)):
                i += 1
                continue

            # Check if line has item keyword
            if self._looks_like_item(line):
                amounts = amount_pattern.findall(line)
                nums    = [float(a) for a in amounts
                           if float(a) > 0]

                if len(nums) >= 2:
                    # Take last 2 numbers as rate, total
                    # OR last 3 as qty, rate, total
                    if len(nums) >= 3:
                        qty   = nums[-3]
                        total = nums[-1]
                    else:
                        qty   = 1
                        total = nums[-1]

                    # ── CHANGED: derive rate from total/qty ──
                    if qty > 0 and total > 0:
                        hsn_info = self._guess_hsn_from_name(line)
                        gst_rate = hsn_info.get("gst_rate", 18)
                        rate     = round(total / qty, 2)  # Composition scheme: no GST strip
                        taxable  = qty * rate
                        gst_amt  = round(taxable * gst_rate / 100, 2)
                        # ... rest of item dict unchanged
                        item = {
                            "item_name":  self._clean_item_name(
                                line
                            ),
                            "hsn_code":   hsn_info.get(
                                "hsn", "-"
                            ),
                            "quantity":   qty,
                            "unit":       "piece",
                            "rate":       rate,
                            "gst_rate":   gst_rate,
                            "gst_amount": gst_amt,
                            "total":      round(
                                taxable + gst_amt, 2
                            ),
                            "confidence": "low",
                        }
                        if self._is_valid_item(item):
                            items.append(item)
            i += 1

        return items


    # ----------------------------------------------------------
    # POST PROCESSING
    # ----------------------------------------------------------
    def _post_process(self, items: list) -> list:
        """
        Clean and validate extracted items.

        Steps:
        1. Remove duplicates
        2. Fix common OCR errors in item names
        3. Validate amounts
        4. Fill missing HSN codes
        5. Standardize units
        """
        cleaned = []
        seen_names = set()

        for item in items:
            # Skip duplicates
            name_key = item["item_name"].lower().strip()
            if name_key in seen_names:
                # Might be a duplicate — add quantities instead
                for existing in cleaned:
                    if existing["item_name"].lower() == name_key:
                        existing["quantity"] += item["quantity"]
                        existing["gst_amount"] = round(
                            existing["quantity"] *
                            existing["rate"] *
                            existing["gst_rate"] / 100, 2
                        )
                        existing["total"] = round(
                            existing["quantity"] *
                            existing["rate"] +
                            existing["gst_amount"], 2
                        )
                        break
                continue

            seen_names.add(name_key)

            # Fix OCR common errors in item name
            item["item_name"] = self._fix_ocr_errors(
                item["item_name"]
            )

            # Fill HSN if missing
            if item["hsn_code"] == "-":
                hsn_info = self._guess_hsn_from_name(
                    item["item_name"]
                )
                if hsn_info.get("hsn"):
                    item["hsn_code"] = hsn_info["hsn"]
                    # Only update GST if it's still default 18
                    if item["gst_rate"] == 18:
                        item["gst_rate"] = hsn_info.get(
                            "gst_rate", 18
                        )

            # Recalculate GST and total cleanly
            taxable          = item["quantity"] * item["rate"]
            item["gst_amount"] = round(
                taxable * item["gst_rate"] / 100, 2
            )
            item["total"]    = round(
                taxable + item["gst_amount"], 2
            )

            cleaned.append(item)

        print(
            f"[OCR] Post-processing: "
            f"{len(items)} → {len(cleaned)} items"
        )
        return cleaned


    def _merge_duplicate_items(self, items: list) -> list:
        """Merge items with same name (from multi-page PDF)"""
        merged = {}

        for item in items:
            key = item["item_name"].lower().strip()
            if key in merged:
                merged[key]["quantity"] += item["quantity"]
                taxable = (
                    merged[key]["quantity"] *
                    merged[key]["rate"]
                )
                merged[key]["gst_amount"] = round(
                    taxable * merged[key]["gst_rate"] / 100, 2
                )
                merged[key]["total"] = round(
                    taxable + merged[key]["gst_amount"], 2
                )
            else:
                merged[key] = item.copy()

        return list(merged.values())


    # ----------------------------------------------------------
    # HELPER METHODS
    # ----------------------------------------------------------
    def _is_header_line(self, line: str) -> bool:
        """Check if line is a table header (not an item)"""
        header_keywords = [
            "sl no", "sl.no", "s.no", "sno",
            "item name", "description", "particulars",
            "hsn", "qty", "quantity", "unit",
            "rate", "price", "amount", "total",
            "cgst", "sgst", "igst", "tax",
            "invoice", "bill", "gstin", "gst no",
            "date", "buyer", "seller", "vendor",
            "sr no", "sr.no", "#", "no."
        ]
        line_lower = line.lower().strip()
        return any(
            kw in line_lower
            for kw in header_keywords
        ) and not any(
            c.isdigit()
            for c in line_lower[:5]
        )

    def _is_total_line(self, line: str) -> bool:
        """Check if line is a total/summary line"""
        total_keywords = [
            "total", "grand total", "subtotal",
            "sub total", "net amount", "net total",
            "amount payable", "balance due",
            "round off", "discount",
            "cgst total", "sgst total",
            "tax total", "taxable total",
            "add:", "less:", "balance"
        ]
        line_lower = line.lower()
        return any(kw in line_lower for kw in total_keywords)

    def _looks_like_item(self, text: str) -> bool:
        """Check if text looks like a hardware item name"""
        if not text or len(text) < 3:
            return False

        # Must start with letter
        if not text[0].isalpha():
            return False

        # Check against hardware keywords
        text_lower = text.lower()
        if any(kw in text_lower for kw in HARDWARE_KEYWORDS):
            return True

        # Generic check: starts with capital letter,
        # has reasonable length
        if (text[0].isupper() and
                3 <= len(text.split()) <= 8 and
                not self._is_header_line(text) and
                not self._is_total_line(text)):
            return True

        return False

    def _normalize_unit(self, unit_str: str) -> str:
        """Normalize unit string to standard form"""
        if not unit_str:
            return "piece"
        unit_lower = unit_str.lower().strip().rstrip(".")
        return UNIT_MAP.get(unit_lower, unit_lower) or "piece"

    def _clean_item_name(self, name: str) -> str:
        """
        Clean extracted item name.
        Remove special chars, fix spacing, title case.
        """
        if not name:
            return "Unknown Item"

        # Remove common OCR artifacts
        name = re.sub(r'[|\\/_\[\]{}]', ' ', name)

        # Remove leading numbers (row numbers)
        name = re.sub(r'^\d+[\.\)]\s*', '', name)

        # Remove extra spaces
        name = ' '.join(name.split())

        # Title case
        name = name.strip().title()

        # Limit length
        if len(name) > 80:
            name = name[:80].strip()

        return name or "Unknown Item"

    def _fix_ocr_errors(self, text: str) -> str:
        """Fix common OCR misread characters"""
        # Common OCR substitutions
        replacements = {
            '0': 'O',   # 0 vs O (in text context only)
            '1': 'I',   # 1 vs I (in text context only)
            '|': 'I',   # Pipe vs I
            '!': 'I',   # Exclamation vs I
        }

        # Only fix if surrounded by letters (not in numbers)
        result = []
        words  = text.split()

        for word in words:
            # Only fix words that are mostly letters
            letter_count = sum(1 for c in word if c.isalpha())
            digit_count  = sum(1 for c in word if c.isdigit())

            if letter_count > digit_count:
                for bad, good in replacements.items():
                    # Only replace if between letters
                    word = re.sub(
                        f'(?<=[A-Za-z]){re.escape(bad)}'
                        f'(?=[A-Za-z])',
                        good,
                        word
                    )
            result.append(word)

        return ' '.join(result)

    def _guess_hsn_from_name(self, item_name: str) -> dict:
        """
        Try to find HSN code and GST rate from item name
        using the HSN lookup dictionary.
        """
        name_lower = item_name.lower()

        # Check each word in item name
        words = name_lower.split()
        for word in words:
            if word in self.hsn_lookup:
                return self.hsn_lookup[word]

        # Try partial match on longer words
        for keyword, info in self.hsn_lookup.items():
            if (len(keyword) > 4 and
                    keyword in name_lower):
                return info

        return {"hsn": "-", "gst_rate": 18}

    def _is_valid_item(self, item: dict) -> bool:
        """
        Validate an extracted item.
        Rejects obviously wrong extractions.
        """
        if not item:
            return False

        name = item.get("item_name", "")
        qty  = item.get("quantity", 0)
        rate = item.get("rate", 0)

        # Name checks
        if not name or len(name) < 2:
            return False
        if name.lower() in (
            "total", "amount", "grand total",
            "subtotal", "tax", "gst"
        ):
            return False

        # Quantity checks
        if qty <= 0 or qty > 100000:
            return False

        # Rate checks
        if rate <= 0 or rate > 1000000:
            return False

        # Total sanity check
        expected = qty * rate
        actual   = item.get("total", 0)
        if actual > 0:
            # Allow 30% tolerance for OCR errors
            if abs(actual - expected) / max(expected, 1) > 0.3:
                # Recalculate
                gst_rate = item.get("gst_rate", 18)
                with_gst = expected * (1 + gst_rate / 100)
                # Still within tolerance of gst-inclusive?
                if (abs(actual - with_gst) /
                        max(with_gst, 1) > 0.3):
                    return False

        return True


# ============================================================
# CSV EXPORT TEMPLATE
# ============================================================
def generate_csv_template(output_path: str):
    """
    Generate a blank CSV template for manual bill entry.
    Father can fill this in Excel/Sheets and import.
    """
    import csv

    headers = [
        "item_name",
        "hsn_code",
        "quantity",
        "unit",
        "purchase_rate",
        "gst_rate"
    ]

    sample_rows = [
        ["GI Pipe 1 inch 6mtr", "7306", "10",
         "piece", "250.00", "18"],
        ["PVC Pipe 2 inch", "3917", "20",
         "piece", "85.00", "18"],
        ["Ball Valve 1 inch", "8481", "15",
         "piece", "120.00", "18"],
        ["Cement OPC 50kg", "2523", "50",
         "bag", "350.00", "28"],
        ["MS Nails 4inch 1kg", "7317", "100",
         "kg", "80.00", "18"],
    ]

    try:
        with open(output_path, "w",
                  newline="",
                  encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(sample_rows)
            # Add empty rows for father to fill
            for _ in range(20):
                writer.writerow(["", "-", "", "piece", "", "18"])

        print(f"[CSV] Template created: {output_path}")
        return True

    except Exception as e:
        print(f"[CSV] Template error: {e}")
        return False


# ============================================================
# TESSERACT INSTALLATION CHECKER
# ============================================================
def check_tesseract_installed() -> tuple:
    """
    Check if Tesseract OCR is installed on the system.
    Returns (is_installed: bool, message: str)
    """
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        return True, f"Tesseract {version} found ✅"
    except ImportError:
        return (
            False,
            "pytesseract not installed.\n"
            "Run: pip install pytesseract"
        )
    except Exception:
        return (
            False,
            "Tesseract OCR engine not found.\n\n"
            "Download from:\n"
            "https://github.com/UB-Mannheim/tesseract/wiki\n\n"
            "After installing, add to PATH or set:\n"
            "pytesseract.pytesseract.tesseract_cmd = "
            r"r'C:\Program Files\Tesseract-OCR\tesseract.exe'"
        )


# ============================================================
# QUICK TEST FUNCTION
# ============================================================
def test_ocr_on_sample():
    """
    Quick test to verify OCR is working.
    Creates a simple test image with text and tries to OCR it.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import pytesseract

        # Create test image
        img  = Image.new("RGB", (600, 200), color="white")
        draw = ImageDraw.Draw(img)

        test_text = (
            "GI Pipe 1inch    7306    10    piece"
            "    250.00    18    2950.00"
        )
        draw.text((10, 80), test_text, fill="black")

        # OCR it
        result = pytesseract.image_to_string(img)
        print(f"[TEST] OCR result: {result}")

        return "GI Pipe" in result or "Pipe" in result

    except Exception as e:
        print(f"[TEST] OCR test failed: {e}")
        return False