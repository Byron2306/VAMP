"""Date parsing helpers for Outlook/OneDrive scraping.

Selectors and scraping logic often receive locale-aware labels such as
"Yesterday" or "12 Oct". These helpers centralise parsing so the
scrapers can remain small and focused on DOM traversal.
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("vamp.date_utils")


@dataclass(frozen=True)
class MonthBounds:
    """Explicit month start/end boundaries.

    The end bound is the first moment of the following month, making it
    safe for ``start <= ts < end`` comparisons.
    """

    start: datetime
    end: datetime


_RELATIVE_KEYWORDS = {
    "today": 0,
    "yesterday": -1,
}

_WEEKDAY_NAMES = {
    name.lower(): idx for idx, name in enumerate(calendar.day_name)
}
_WEEKDAY_SHORT = {name[:3].lower(): idx for name, idx in _WEEKDAY_NAMES.items()}


def _normalise_now(now: Optional[datetime]) -> datetime:
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base


def compute_month_bounds(year: int, month: int, *, tzinfo=timezone.utc) -> MonthBounds:
    """Return the start and end bounds for a given month.

    The ``end`` value is the start of the next month, keeping comparisons
    half-open (``start <= ts < end``) to avoid fencepost errors.
    """

    start = datetime(year, month, 1, tzinfo=tzinfo)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=tzinfo)
    else:
        end = datetime(year, month + 1, 1, tzinfo=tzinfo)
    return MonthBounds(start=start, end=end)


def parse_outlook_date(label: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Parse Outlook Web date strings into a timezone-aware ``datetime``.

    Args:
        label: The raw label from the Outlook UI (e.g. ``"Yesterday"``,
            ``"Mon"``, ``"12 Oct"``, ``"12 Oct 2025"``, or ``"14:32"``).
        now: Reference time for relative parsing (defaults to ``UTC`` now).

    Returns:
        A timezone-aware ``datetime`` on success, or ``None`` if parsing
        fails. Callers are expected to log failures and skip rows rather
        than crash the entire scan.
    """

    text = (label or "").strip()
    if not text:
        return None

    base_now = _normalise_now(now)
    lower = text.lower()

    # Relative keywords: Today / Yesterday
    if lower in _RELATIVE_KEYWORDS:
        day_delta = _RELATIVE_KEYWORDS[lower]
        base_date = (base_now + timedelta(days=day_delta)).date()
        return datetime.combine(base_date, base_now.timetz(), tzinfo=base_now.tzinfo)

    # Weekday labels (Mon, Tue, Monday, etc.) – assume most recent past
    if lower in _WEEKDAY_NAMES:
        target = _WEEKDAY_NAMES[lower]
    elif lower in _WEEKDAY_SHORT:
        target = _WEEKDAY_SHORT[lower]
    else:
        target = None

    if target is not None:
        delta = (base_now.weekday() - target) % 7
        delta = delta or 7  # prefer previous occurrence
        base_date = (base_now - timedelta(days=delta)).date()
        return datetime.combine(base_date, base_now.timetz(), tzinfo=base_now.tzinfo)

    # Time-only labels (e.g. "14:32" or "2:45 PM") – assume today
    time_formats = ["%H:%M", "%I:%M %p"]
    for fmt in time_formats:
        try:
            parsed_time = datetime.strptime(text, fmt).time()
            combined = datetime.combine(base_now.date(), parsed_time, tzinfo=base_now.tzinfo)
            # If the time appears to be in the future (e.g. across midnight),
            # assume it referred to the previous day.
            if combined > base_now + timedelta(minutes=5):
                combined -= timedelta(days=1)
            return combined
        except Exception:
            continue

    # Absolute dates – with or without year
    date_formats = [
        "%d %b %Y",
        "%d %B %Y",
        "%d %b",
        "%d %B",
        "%Y-%m-%d",
    ]
    for fmt in date_formats:
        try:
            parsed = datetime.strptime(text, fmt)
            year = parsed.year if "%Y" in fmt else base_now.year
            parsed = parsed.replace(year=year)
            parsed = parsed.replace(tzinfo=base_now.tzinfo)
            if parsed > base_now + timedelta(days=1):
                # Outlook sometimes omits the year; assume previous year if we
                # landed in the future.
                parsed = parsed.replace(year=parsed.year - 1)
            return parsed
        except Exception:
            continue

    logger.debug("parse_outlook_date: unable to parse '%s'", text)
    return None


__all__ = ["MonthBounds", "compute_month_bounds", "parse_outlook_date"]
