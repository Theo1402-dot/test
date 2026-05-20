"""Pure demurrage math. No I/O, no openpyxl imports.

Mirrors the Excel formulas in `MOCOH_DEMURRAGE_2026.xlsm`:

    Trips Ledger
      O (Waiting)   = IF(OR(M="",N=""),"",N-M)
      Q (Excess)    = IF(O="","",MAX(0, O - P))
      S (Demurrage) = IF(Q="","", Q * R)

    Claims
      P (Aging) buckets: Paid | Current(<=0) | 1-30 | 31-60 | 61-90 | 90+

Python versions exist so we can (a) cross-check the sheet via the reconcile CLI
and (b) aggregate claims without opening Excel.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional, Union

AgingBucket = Literal["Current", "1-30", "31-60", "61-90", "90+"]

DateLike = Union[datetime, date, None]


def _to_date(value: DateLike) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"Expected date/datetime, got {type(value).__name__}")


def waiting_days(
    date_loaded: DateLike, arrival: DateLike, offloaded: DateLike
) -> Optional[int]:
    """Days between arrival at destination and offload completion.

    Returns None if either arrival or offloaded is missing (matches the
    sheet, where Waiting renders as blank text in that case).

    `date_loaded` is accepted so the public signature mirrors PROJECT_BRIEF.md
    section 3.3; it is not used in the value computation (the workbook
    formula doesn't use it either), but a sanity check enforces
    date_loaded <= arrival <= offloaded when all three are present.
    """
    a = _to_date(arrival)
    o = _to_date(offloaded)
    if a is None or o is None:
        return None
    dl = _to_date(date_loaded)
    if dl is not None and a < dl:
        raise ValueError(f"arrival {a} predates date_loaded {dl}")
    if o < a:
        raise ValueError(f"offloaded {o} predates arrival {a}")
    return (o - a).days


def excess_days(
    waiting: Optional[float], laytime: Optional[float]
) -> Optional[int]:
    """Excess days past free time. max(0, waiting - laytime)."""
    if waiting is None:
        return None
    if laytime is None:
        raise ValueError("laytime is required when waiting is known")
    if waiting < 0:
        raise ValueError(f"waiting cannot be negative (got {waiting})")
    if laytime < 0:
        raise ValueError(f"laytime cannot be negative (got {laytime})")
    return int(max(0, waiting - laytime))


def demurrage(excess: Optional[float], rate: Optional[float]) -> Optional[float]:
    """Demurrage USD = excess × rate. None if excess is unknown."""
    if excess is None:
        return None
    if rate is None:
        raise ValueError("rate is required when excess is known")
    if excess < 0 or rate < 0:
        raise ValueError(f"excess and rate must be non-negative (got {excess}, {rate})")
    return float(excess) * float(rate)


def trip_status(waiting: Optional[float], excess: Optional[float]) -> str:
    """Mirrors column T: PENDING | DEMURRAGE | ON-TIME."""
    if waiting is None:
        return "PENDING"
    if excess is not None and excess > 0:
        return "DEMURRAGE"
    return "ON-TIME"


def aging_bucket(days_overdue: Optional[int]) -> AgingBucket:
    """Bucket per Claims!P formula. Boundaries: <=0 Current, 30, 60, 90."""
    if days_overdue is None or days_overdue <= 0:
        return "Current"
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def days_overdue(due_date: DateLike, today: DateLike = None, status: str = "Sent") -> Optional[int]:
    """Mirrors Claims!O: 0 if Paid, blank if not Sent, else max(0, today - due)."""
    if status == "Paid":
        return 0
    if status != "Sent":
        return None
    d = _to_date(due_date)
    if d is None:
        return None
    t = _to_date(today) or date.today()
    return max(0, (t - d).days)
