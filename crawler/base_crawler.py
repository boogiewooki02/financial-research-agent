from __future__ import annotations

import hashlib
from datetime import date, datetime


def generate_report_id(
    source: str,
    ticker: str,
    published_at: str,
    title: str,
    pdf_url: str | None = None,
    original_url: str | None = None,
) -> str:
    identity = f"{title}|{pdf_url or original_url or ''}"
    hash8 = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
    compact_date = published_at.replace("-", "") if published_at else "unknown"
    return f"{source.upper()}_{ticker or 'UNKNOWN'}_{compact_date}_{hash8}"


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%y-%m-%d", "%y.%m.%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def normalize_date(value: str | None) -> str:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else (value or "")


def subtract_months(value: date, months: int) -> date:
    month_index = value.month - 1 - months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = (
        31,
        29 if _is_leap_year(year) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    )
    return date(year, month, min(value.day, month_lengths[month - 1]))


def is_within_months(value: str | None, months: int) -> bool:
    parsed = parse_date(value)
    if parsed is None:
        return False
    return parsed >= subtract_months(date.today(), months)


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
