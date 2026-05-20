"""Aggregate trips into claim drafts and upsert them into the Claims sheet.

PROJECT_BRIEF §3.4 contract:
  group_trips_to_claims(trips, period_from, period_to) -> list[ClaimDraft]
    * group by deal_no
    * keep trips with date_loaded in [period_from, period_to]
    * sum demurrage_usd, count trips, compute true period span from group dates
    * Claim No. = "{deal_no}-DEM"

  upsert_claims(drafts)
    * if claim exists and status == Draft -> update amount/num_trips/period only
    * never touch claims in Sent/Paid status
    * otherwise append a new Draft row
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from openpyxl.workbook import Workbook
from pydantic import BaseModel, ConfigDict

from . import config as cfg
from .calculations import demurrage as calc_demurrage
from .calculations import excess_days, waiting_days
from .workbook import Assumptions, Deal, Trip, write_claims


class ClaimDraft(BaseModel):
    """One row destined for the Claims sheet."""

    model_config = ConfigDict(extra="forbid")

    claim_no: str
    deal_no: str
    consignee: str
    period_from: datetime
    period_to: datetime
    num_trips: int
    amount_usd: float
    trip_rows: list[int]  # rows in Trips Ledger that fed this claim


def _to_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    raise TypeError(f"Expected date/datetime, got {type(value).__name__}")


def _trip_demurrage(
    trip: Trip,
    *,
    deals_by_no: Optional[dict[str, Deal]],
    assumptions: Optional[Assumptions],
) -> float:
    """Compute one trip's demurrage USD.

    Prefers Python recomputation from literal arrival/offloaded + deal/assumption
    laytime+rate. This is robust against openpyxl's cached-value stripping
    (saved workbooks lose Excel's formula results until reopened in Excel).
    Falls back to the cached `trip.demurrage_usd` only when arrival/offloaded
    aren't present — i.e. for synthetic trips constructed in unit tests.
    """
    if trip.arrival is not None and trip.offloaded is not None:
        deal = deals_by_no.get(trip.deal_no) if (deals_by_no and trip.deal_no) else None
        laytime = (
            deal.laytime_d if (deal and deal.laytime_d is not None)
            else (assumptions.laytime_days if assumptions else cfg.DEFAULT_LAYTIME_DAYS)
        )
        rate = (
            deal.rate_usd_per_day if (deal and deal.rate_usd_per_day is not None)
            else (assumptions.rate_usd_per_day if assumptions else cfg.DEFAULT_RATE_USD_PER_DAY)
        )
        w = waiting_days(trip.date_loaded, trip.arrival, trip.offloaded)
        if w is None:
            return 0.0
        ex = excess_days(w, laytime) or 0
        return calc_demurrage(ex, rate) or 0.0
    return float(trip.demurrage_usd or 0.0)


def group_trips_to_claims(
    trips: Iterable[Trip],
    period_from: date | datetime,
    period_to: date | datetime,
    *,
    deals_by_no: Optional[dict[str, Deal]] = None,
    assumptions: Optional[Assumptions] = None,
) -> list[ClaimDraft]:
    """Group eligible trips by deal_no and roll up.

    "Eligible" = date_loaded ∈ [period_from, period_to] (inclusive both ends).

    When `deals_by_no` is provided (production path), demurrage is recomputed
    in Python from the literal arrival/offloaded/laytime/rate columns. This
    prevents the openpyxl cached-value-stripping issue from producing
    spurious 0 amounts on re-runs. Without `deals_by_no`, the function uses
    `trip.demurrage_usd` directly (useful for pure unit tests).
    """
    pf = _to_dt(period_from)
    pt = _to_dt(period_to)
    if pf is None or pt is None:
        raise ValueError("period_from and period_to are required")
    if pt < pf:
        raise ValueError(f"period_to {pt} predates period_from {pf}")

    buckets: dict[str, list[Trip]] = {}
    for t in trips:
        if not t.deal_no or not t.date_loaded:
            continue
        if not (pf <= t.date_loaded <= pt):
            continue
        buckets.setdefault(t.deal_no, []).append(t)

    drafts: list[ClaimDraft] = []
    for deal_no, members in sorted(buckets.items()):
        consignee = next((m.consignee for m in members if m.consignee), "") or ""
        amount = sum(
            _trip_demurrage(m, deals_by_no=deals_by_no, assumptions=assumptions)
            for m in members
        )
        loaded_dates = [m.date_loaded for m in members if m.date_loaded]
        if not loaded_dates:
            continue
        drafts.append(
            ClaimDraft(
                claim_no=f"{deal_no}-DEM",
                deal_no=str(deal_no),
                consignee=consignee,
                period_from=min(loaded_dates),
                period_to=max(loaded_dates),
                num_trips=len(members),
                amount_usd=float(round(amount, 2)),
                trip_rows=sorted(m.row for m in members),
            )
        )
    return drafts


def _build_bill_to_lookup(wb: Workbook) -> dict[str, str]:
    """Read the Company!Consignees table (B30:D33+) into {consignee: bill_to}."""
    ws = wb[cfg.SHEET_COMPANY]
    out: dict[str, str] = {}
    # Header is at row 30 ("Consignee | Bill-To Address | Email"); data starts row 31.
    for r in range(31, ws.max_row + 1):
        name = ws.cell(row=r, column=2).value
        addr = ws.cell(row=r, column=3).value
        if isinstance(name, str) and name.strip():
            out[name.strip()] = (addr or "").strip() if isinstance(addr, str) else ""
    return out


def drafts_to_rows(
    drafts: Iterable[ClaimDraft],
    wb: Workbook,
    *,
    issue_date: Optional[datetime] = None,
    payment_terms_days: int = cfg.PAYMENT_TERMS_DAYS,
) -> list[dict]:
    """Convert ClaimDrafts into the dict shape expected by workbook.write_claims."""
    bill_to = _build_bill_to_lookup(wb)
    issued = issue_date or datetime.now().replace(microsecond=0)
    due = issued + timedelta(days=payment_terms_days)
    rows: list[dict] = []
    for d in drafts:
        rows.append(
            {
                "claim_no": d.claim_no,
                "issue_date": issued,
                "deal_no": d.deal_no,
                "consignee": d.consignee,
                "bill_to": bill_to.get(d.consignee, ""),
                "period_from": d.period_from,
                "period_to": d.period_to,
                "num_trips": d.num_trips,
                "amount_usd": d.amount_usd,
                "currency": cfg.DEFAULT_CURRENCY,
                "status": "Draft",
                "due_date": due,
                "notes": f"Auto-built from trips rows {d.trip_rows[0]}-{d.trip_rows[-1]}",
            }
        )
    return rows


def upsert_claims(
    wb: Workbook,
    drafts: list[ClaimDraft],
    *,
    issue_date: Optional[datetime] = None,
) -> list[tuple[str, str]]:
    """Write/refresh draft rows. Returns [(claim_no, "created"|"updated"|"skipped (...)")]."""
    rows = drafts_to_rows(drafts, wb, issue_date=issue_date)
    return write_claims(wb, rows)
