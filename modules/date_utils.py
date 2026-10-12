# modules/date_utils.py
# ============================================================
# DATE RANGE & CONVERSION UTILITIES
# Provides robust date range calculations, presets, and
# formatting across all modules in the Hardware Shop Billing System.
# ============================================================

from datetime import date, datetime, timedelta
import calendar
from typing import Tuple, Optional


DATE_PRESETS = [
    "This Month",
    "Last Month",
    "This Financial Year",
    "Last Financial Year",
    "Last 30 Days",
    "Last 90 Days",
    "All Time",
    "Custom Range",
]


def parse_flexible_date(value, default: Optional[date] = None) -> Optional[date]:
    """
    Parse a date from string (YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY)
    or datetime/date object.
    """
    if value is None:
        return default

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    cleaned = str(value).strip().strip('"').strip("'")
    if not cleaned:
        return default

    # Split timestamp part if present
    cleaned = cleaned.split(" ")[0].split("T")[0]

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d-%m-%y",
        "%d/%m/%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    return default


def format_date_display(d: Optional[date | str]) -> str:
    """Format date to DD/MM/YYYY for UI display."""
    if not d:
        return ""
    if isinstance(d, str):
        parsed = parse_flexible_date(d)
        if parsed:
            return parsed.strftime("%d/%m/%Y")
        return d
    return d.strftime("%d/%m/%Y")


def format_date_iso(d: Optional[date | str]) -> str:
    """Format date to YYYY-MM-DD for database storage/queries."""
    if not d:
        return ""
    if isinstance(d, str):
        parsed = parse_flexible_date(d)
        if parsed:
            return parsed.strftime("%Y-%m-%d")
        return d
    return d.strftime("%Y-%m-%d")


def get_financial_year_dates(for_date: Optional[date] = None, offset_years: int = 0) -> Tuple[date, date]:
    """
    Return (start_date, end_date) for Indian Financial Year (1 April - 31 March).
    offset_years: 0 for current FY, -1 for last FY, etc.
    """
    ref = for_date or date.today()
    fy_start_year = ref.year if ref.month >= 4 else ref.year - 1
    fy_start_year += offset_years

    start_date = date(fy_start_year, 4, 1)
    end_date = date(fy_start_year + 1, 3, 31)
    return start_date, end_date


def get_financial_year(for_date: Optional[date] = None) -> str:
    """Return financial year string (e.g. '2025-26') for a given date."""
    ref = for_date or date.today()
    fy_start_year = ref.year if ref.month >= 4 else ref.year - 1
    return f"{fy_start_year}-{str(fy_start_year + 1)[-2:]}"


def get_month_dates(year_or_month: int, month_or_year: int) -> Tuple[date, date]:
    """Return (start_date, end_date) for a given calendar month and year. Accepts (year, month) or (month, year)."""
    if year_or_month > 12:
        year, month = int(year_or_month), int(month_or_year)
    elif month_or_year > 12:
        month, year = int(year_or_month), int(month_or_year)
    else:
        year, month = int(year_or_month), int(month_or_year)
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, 1), date(year, month, last_day)


def get_date_range_for_preset(preset: str, ref_date: Optional[date] = None) -> Tuple[date, date]:
    """
    Return (start_date, end_date) for any named preset.
    """
    today = ref_date or date.today()

    if preset == "This Month":
        return get_month_dates(today.year, today.month)

    elif preset == "Last Month":
        first_of_month = date(today.year, today.month, 1)
        last_day_prev_month = first_of_month - timedelta(days=1)
        return get_month_dates(last_day_prev_month.year, last_day_prev_month.month)

    elif preset == "This Financial Year":
        return get_financial_year_dates(today, offset_years=0)

    elif preset == "Last Financial Year":
        return get_financial_year_dates(today, offset_years=-1)

    elif preset == "Last 30 Days":
        return today - timedelta(days=29), today

    elif preset == "Last 90 Days":
        return today - timedelta(days=89), today

    elif preset == "All Time":
        return date(2020, 1, 1), date(2099, 12, 31)

    # Default to This Month
    return get_month_dates(today.year, today.month)
