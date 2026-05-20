"""
Date Parser
===========
Handles all date formats encountered in Danish and international construction schedules:
  - Danish short:   "ma 05-01-26", "ti 16-12-25"  (day-prefix + dd-mm-yy)
  - ISO 8601:       "2026-01-05T00:00:00Z", "2025-11-03 00:00:00"
  - dd-mm-yyyy:     "05-01-2026", "01-03-2022"
  - dd-mm-yy:       "05-01-26"
  - dd.mm.yyyy:     "05.01.2026"
  - MM/DD/YYYY:     "01/05/2026"
  - Primavera:      "12-JAN-26 08:00:00"
  - Duration str:   "50d", "3u", "74.38d" → returns None (not a date)
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional

_DANISH_DAY_PREFIX = re.compile(
    r"^(man|ma|tir|ti|ons|on|tor|to|fre|fr|lør|lø|søn|sø)\s+", re.IGNORECASE
)

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "may": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10,
    "nov": 11, "dec": 12,
}

_FORMATS = [
    "%d-%m-%Y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d.%m.%y",
    "%d/%m/%Y",   # Danish/European slash format — must precede American
    "%d/%m/%y",
    "%Y/%m/%d",
    "%m/%d/%Y",   # American slash format — fallback only
    "%m/%d/%y",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
]

_PRIMAVERA_RE = re.compile(
    r"(\d{1,2})-([A-Za-z]{3})-(\d{2,4})(?:\s+\d{1,2}:\d{2}:\d{2})?", re.IGNORECASE
)

_DURATION_RE = re.compile(r"^\d+[\.,]?\d*\s*[dDhHwWmMuU]?$")


def parse_date(value: str) -> Optional[datetime]:
    """
    Parse a date string from any known schedule format.
    Returns None if the value is not a parseable date (e.g. duration strings, "-").
    All datetimes are returned as UTC-aware.
    """
    if not value or not value.strip():
        return None

    v = value.strip()

    if v in ("-", "—", "N/A", "n/a", ""):
        return None

    if _DURATION_RE.match(v):
        return None

    v = _DANISH_DAY_PREFIX.sub("", v).strip()

    m = _PRIMAVERA_RE.match(v)
    if m:
        day = int(m.group(1))
        month = _MONTH_MAP.get(m.group(2).lower(), 0)
        year_raw = m.group(3)
        year = int(year_raw)
        if year < 100:
            year += 2000 if year < 70 else 1900
        if month:
            try:
                return datetime(year, month, day, tzinfo=timezone.utc)
            except ValueError:
                pass

    for fmt in _FORMATS:
        try:
            dt = datetime.strptime(v, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def parse_duration_to_hours(value: str) -> int:
    """
    Convert duration string to working hours.
    Conventions:
      - "50d"    → 50 × 8 = 400h
      - "3u"     → 3 × 40 = 120h  (weeks)
      - "48"     → 48h   (bare integer assumed hours for Plandisc)
      - "74.38d" → round(74.38 × 8) = 595h
      - "0d"     → 0h   (milestone)
    """
    if not value or not value.strip():
        return 0

    v = value.strip().replace(",", ".")

    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*([dDhHwWuUmM]?)$", v)
    if not m:
        return 0

    try:
        num = float(m.group(1).replace(",", "."))
    except ValueError:
        return 0
    unit = m.group(2).lower()

    if unit == "d":
        return round(num * 8)
    elif unit == "" or unit == "h":
        return round(num)
    elif unit in ("w", "u"):
        return round(num * 40)
    elif unit == "m":
        return round(num * 160)

    return round(num)
