"""All openpyxl read/write against MOCOH_DEMURRAGE_2026.xlsm.

Hard guarantees:
  * load with keep_vba=True so the VBA project survives every save.
  * write_claims and update_claim_status NEVER overwrite Sent/Paid claims.
  * every mutation is mirrored to AuditLog via audit.log().
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel, ConfigDict, Field

from . import config as cfg
from .audit import log as audit_log


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Trip(BaseModel):
    model_config = ConfigDict(extra="ignore")

    row: int
    deal_no: Optional[str] = None
    claim_no: Optional[str] = None
    consignee: Optional[str] = None
    date_loaded: Optional[datetime] = None
    loading_port: Optional[str] = None
    destination: Optional[str] = None
    product: Optional[str] = None
    truck_no: Optional[str] = None
    trailer: Optional[str] = None
    transporter: Optional[str] = None
    driver: Optional[str] = None
    arrival: Optional[datetime] = None
    offloaded: Optional[datetime] = None
    waiting_d: Optional[float] = None
    laytime_d: Optional[float] = None
    excess_d: Optional[float] = None
    rate_usd: Optional[float] = None
    demurrage_usd: Optional[float] = None
    status: Optional[str] = None


class Claim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    row: int
    claim_no: Optional[str] = None
    issue_date: Optional[datetime] = None
    deal_no: Optional[str] = None
    consignee: Optional[str] = None
    bill_to: Optional[str] = None
    period_from: Optional[datetime] = None
    period_to: Optional[datetime] = None
    num_trips: Optional[int] = None
    amount_usd: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None
    paid_date: Optional[datetime] = None
    days_overdue: Optional[int] = None
    aging: Optional[str] = None
    notes: Optional[str] = None


class Deal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    row: int
    deal_no: Optional[str] = None
    consignee: Optional[str] = None
    route: Optional[str] = None
    loading_port: Optional[str] = None
    destination: Optional[str] = None
    product: Optional[str] = None
    laytime_d: Optional[float] = None
    rate_usd_per_day: Optional[float] = None
    transport_usd_per_m3: Optional[float] = None
    transporter: Optional[str] = None


class Assumptions(BaseModel):
    laytime_days: float = cfg.DEFAULT_LAYTIME_DAYS
    rate_usd_per_day: float = cfg.DEFAULT_RATE_USD_PER_DAY
    currency: str = cfg.DEFAULT_CURRENCY
    fx_rate: float = cfg.DEFAULT_FX
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class Company(BaseModel):
    legal_name: str = ""
    trading_name: str = ""
    address: str = ""
    vat: str = ""
    phone: str = ""
    email: str = ""
    bank_name: str = ""
    account_name: str = ""
    iban: str = ""
    swift: str = ""
    correspondent_bank: str = Field(default="")


# ---------------------------------------------------------------------------
# Workbook open/save
# ---------------------------------------------------------------------------


def open_wb(path: Path | None = None, *, data_only: bool = False) -> Workbook:
    """Open the workbook preserving VBA. data_only=True returns formula results."""
    path = path or cfg.WORKBOOK_PATH
    if not path.exists():
        raise FileNotFoundError(f"Workbook not found: {path}")
    return load_workbook(path, keep_vba=True, data_only=data_only)


def save_wb(wb: Workbook, path: Path | None = None) -> Path:
    """Save the workbook. Asserts VBA archive survived the round trip."""
    path = path or cfg.WORKBOOK_PATH
    wb.save(path)
    # Smoke-check the VBA project is still present.
    verify = load_workbook(path, keep_vba=True)
    if verify.vba_archive is None:
        raise RuntimeError(
            f"VBA archive lost on save to {path}. Refusing to proceed."
        )
    verify.close()
    return path


@contextmanager
def workbook_session(
    path: Path | None = None, *, data_only: bool = False, save: bool = False
) -> Iterator[Workbook]:
    """Open, yield, optionally save, always close."""
    wb = open_wb(path, data_only=data_only)
    try:
        yield wb
        if save:
            save_wb(wb, path)
    finally:
        wb.close()


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _cell(ws: Worksheet, row: int, col_letter: str):
    return ws.cell(row=row, column=column_index_from_string(col_letter))


def _read_row(ws: Worksheet, row: int, cols: dict[str, str]) -> dict[str, object]:
    return {name: _cell(ws, row, letter).value for name, letter in cols.items()}


def _row_is_blank(ws: Worksheet, row: int, cols: dict[str, str]) -> bool:
    return all(_cell(ws, row, letter).value in (None, "") for letter in cols.values())


def _coerce_str(value: object) -> Optional[str]:
    if value is None:
        return None
    return str(value).strip() or None


def _coerce_dt(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


def _coerce_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.startswith("="):
        return None  # unresolved formula — caller should use data_only=True
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def read_trips(wb: Workbook | None = None) -> list[Trip]:
    """Return all trips with a non-empty Date Loaded. data_only=True is recommended
    if you want the calculated waiting/excess/demurrage numbers rather than formulas.
    """
    own = wb is None
    if own:
        wb = open_wb(data_only=True)
    try:
        ws = wb[cfg.SHEET_TRIPS]
        trips: list[Trip] = []
        for r in range(cfg.TRIPS_FIRST_DATA_ROW, ws.max_row + 1):
            date_loaded = _coerce_dt(_cell(ws, r, cfg.TRIPS["date_loaded"]).value)
            if date_loaded is None:
                continue
            trips.append(
                Trip(
                    row=r,
                    deal_no=_coerce_str(_cell(ws, r, cfg.TRIPS["deal_no"]).value),
                    claim_no=_coerce_str(_cell(ws, r, cfg.TRIPS["claim_no"]).value),
                    consignee=_coerce_str(_cell(ws, r, cfg.TRIPS["consignee"]).value),
                    date_loaded=date_loaded,
                    loading_port=_coerce_str(_cell(ws, r, cfg.TRIPS["loading_port"]).value),
                    destination=_coerce_str(_cell(ws, r, cfg.TRIPS["destination"]).value),
                    product=_coerce_str(_cell(ws, r, cfg.TRIPS["product"]).value),
                    truck_no=_coerce_str(_cell(ws, r, cfg.TRIPS["truck_no"]).value),
                    trailer=_coerce_str(_cell(ws, r, cfg.TRIPS["trailer"]).value),
                    transporter=_coerce_str(_cell(ws, r, cfg.TRIPS["transporter"]).value),
                    driver=_coerce_str(_cell(ws, r, cfg.TRIPS["driver"]).value),
                    arrival=_coerce_dt(_cell(ws, r, cfg.TRIPS["arrival"]).value),
                    offloaded=_coerce_dt(_cell(ws, r, cfg.TRIPS["offloaded"]).value),
                    waiting_d=_coerce_float(_cell(ws, r, cfg.TRIPS["waiting_d"]).value),
                    laytime_d=_coerce_float(_cell(ws, r, cfg.TRIPS["laytime_d"]).value),
                    excess_d=_coerce_float(_cell(ws, r, cfg.TRIPS["excess_d"]).value),
                    rate_usd=_coerce_float(_cell(ws, r, cfg.TRIPS["rate_usd"]).value),
                    demurrage_usd=_coerce_float(_cell(ws, r, cfg.TRIPS["demurrage_usd"]).value),
                    status=_coerce_str(_cell(ws, r, cfg.TRIPS["status"]).value),
                )
            )
        return trips
    finally:
        if own:
            wb.close()


def read_claims(wb: Workbook | None = None) -> list[Claim]:
    own = wb is None
    if own:
        wb = open_wb(data_only=True)
    try:
        ws = wb[cfg.SHEET_CLAIMS]
        out: list[Claim] = []
        for r in range(cfg.CLAIMS_FIRST_DATA_ROW, ws.max_row + 1):
            claim_no = _coerce_str(_cell(ws, r, cfg.CLAIMS["claim_no"]).value)
            if not claim_no:
                continue
            out.append(
                Claim(
                    row=r,
                    claim_no=claim_no,
                    issue_date=_coerce_dt(_cell(ws, r, cfg.CLAIMS["issue_date"]).value),
                    deal_no=_coerce_str(_cell(ws, r, cfg.CLAIMS["deal_no"]).value),
                    consignee=_coerce_str(_cell(ws, r, cfg.CLAIMS["consignee"]).value),
                    bill_to=_coerce_str(_cell(ws, r, cfg.CLAIMS["bill_to"]).value),
                    period_from=_coerce_dt(_cell(ws, r, cfg.CLAIMS["period_from"]).value),
                    period_to=_coerce_dt(_cell(ws, r, cfg.CLAIMS["period_to"]).value),
                    num_trips=int(_coerce_float(_cell(ws, r, cfg.CLAIMS["num_trips"]).value) or 0) or None,
                    amount_usd=_coerce_float(_cell(ws, r, cfg.CLAIMS["amount_usd"]).value),
                    currency=_coerce_str(_cell(ws, r, cfg.CLAIMS["currency"]).value),
                    status=_coerce_str(_cell(ws, r, cfg.CLAIMS["status"]).value),
                    due_date=_coerce_dt(_cell(ws, r, cfg.CLAIMS["due_date"]).value),
                    paid_date=_coerce_dt(_cell(ws, r, cfg.CLAIMS["paid_date"]).value),
                    days_overdue=int(_coerce_float(_cell(ws, r, cfg.CLAIMS["days_overdue"]).value) or 0) or None,
                    aging=_coerce_str(_cell(ws, r, cfg.CLAIMS["aging"]).value),
                    notes=_coerce_str(_cell(ws, r, cfg.CLAIMS["notes"]).value),
                )
            )
        return out
    finally:
        if own:
            wb.close()


def read_deals(wb: Workbook | None = None) -> list[Deal]:
    own = wb is None
    if own:
        wb = open_wb(data_only=True)
    try:
        ws = wb[cfg.SHEET_DEALS]
        out: list[Deal] = []
        for r in range(cfg.DEALS_FIRST_DATA_ROW, ws.max_row + 1):
            deal_no = _coerce_str(_cell(ws, r, cfg.DEALS["deal_no"]).value)
            if not deal_no:
                continue
            out.append(
                Deal(
                    row=r,
                    deal_no=deal_no,
                    consignee=_coerce_str(_cell(ws, r, cfg.DEALS["consignee"]).value),
                    route=_coerce_str(_cell(ws, r, cfg.DEALS["route"]).value),
                    loading_port=_coerce_str(_cell(ws, r, cfg.DEALS["loading_port"]).value),
                    destination=_coerce_str(_cell(ws, r, cfg.DEALS["destination"]).value),
                    product=_coerce_str(_cell(ws, r, cfg.DEALS["product"]).value),
                    laytime_d=_coerce_float(_cell(ws, r, cfg.DEALS["laytime_d"]).value),
                    rate_usd_per_day=_coerce_float(_cell(ws, r, cfg.DEALS["rate_usd_per_day"]).value),
                    transport_usd_per_m3=_coerce_float(_cell(ws, r, cfg.DEALS["transport_usd_per_m3"]).value),
                    transporter=_coerce_str(_cell(ws, r, cfg.DEALS["transporter"]).value),
                )
            )
        return out
    finally:
        if own:
            wb.close()


def read_assumptions(wb: Workbook | None = None) -> Assumptions:
    """Pull defaults from the Assumptions sheet. Falls back to config.py constants."""
    own = wb is None
    if own:
        wb = open_wb(data_only=True)
    try:
        ws = wb[cfg.SHEET_ASSUMPTIONS]
        kv: dict[str, object] = {}
        for r in range(1, ws.max_row + 1):
            label = _coerce_str(ws.cell(row=r, column=2).value)
            value = ws.cell(row=r, column=3).value
            if label:
                kv[label.lower()] = value
        return Assumptions(
            laytime_days=_coerce_float(kv.get("default laytime (days)")) or cfg.DEFAULT_LAYTIME_DAYS,
            rate_usd_per_day=_coerce_float(kv.get("default demurrage rate (usd/day)")) or cfg.DEFAULT_RATE_USD_PER_DAY,
            currency=_coerce_str(kv.get("currency")) or cfg.DEFAULT_CURRENCY,
            fx_rate=_coerce_float(kv.get("fx rate (local → usd)")) or cfg.DEFAULT_FX,
            period_start=_coerce_dt(kv.get("period start")),
            period_end=_coerce_dt(kv.get("period end")),
        )
    finally:
        if own:
            wb.close()


def read_company(wb: Workbook | None = None) -> Company:
    own = wb is None
    if own:
        wb = open_wb(data_only=True)
    try:
        ws = wb[cfg.SHEET_COMPANY]
        kv: dict[str, str] = {}
        for r in range(1, ws.max_row + 1):
            label = _coerce_str(ws.cell(row=r, column=2).value)
            value = _coerce_str(ws.cell(row=r, column=3).value)
            if label:
                kv[label.lower()] = value or ""
        return Company(
            legal_name=kv.get("legal name", ""),
            trading_name=kv.get("trading name", ""),
            address=kv.get("address", ""),
            vat=kv.get("vat / tin / reg.", ""),
            phone=kv.get("phone", ""),
            email=kv.get("email", ""),
            bank_name=kv.get("beneficiary bank", ""),
            account_name=kv.get("account name", ""),
            iban=kv.get("iban", ""),
            swift=kv.get("swift / bic", ""),
            correspondent_bank=kv.get("correspondent bank", ""),
        )
    finally:
        if own:
            wb.close()


# ---------------------------------------------------------------------------
# Writers — every mutation goes through audit_log
# ---------------------------------------------------------------------------


def _next_claim_row(ws: Worksheet) -> int:
    """First row in the Claims data block that has no claim_no."""
    col = cfg.CLAIMS["claim_no"]
    for r in range(cfg.CLAIMS_FIRST_DATA_ROW, ws.max_row + 2):
        if _cell(ws, r, col).value in (None, ""):
            return r
    return ws.max_row + 1


def _find_claim_row(ws: Worksheet, claim_no: str) -> Optional[int]:
    col = cfg.CLAIMS["claim_no"]
    for r in range(cfg.CLAIMS_FIRST_DATA_ROW, ws.max_row + 1):
        if _coerce_str(_cell(ws, r, col).value) == claim_no:
            return r
    return None


def write_claims(wb: Workbook, drafts: list[dict]) -> list[tuple[str, str]]:
    """Append/update claim rows. Returns list of (claim_no, action).

    Rules:
      * If claim exists and status is in CLAIM_LOCKED_STATUSES, skip.
      * If claim exists and status == "Draft", update amount/num_trips/period only.
      * Otherwise append a new row with Status = "Draft".
    """
    ws = wb[cfg.SHEET_CLAIMS]
    actions: list[tuple[str, str]] = []

    for draft in drafts:
        claim_no = draft["claim_no"]
        existing_row = _find_claim_row(ws, claim_no)
        if existing_row is not None:
            current_status = _coerce_str(
                _cell(ws, existing_row, cfg.CLAIMS["status"]).value
            ) or "Draft"
            if current_status in cfg.CLAIM_LOCKED_STATUSES:
                actions.append((claim_no, f"skipped ({current_status})"))
                audit_log(
                    wb,
                    sheet=cfg.SHEET_CLAIMS,
                    address=f"{cfg.CLAIMS['claim_no']}{existing_row}",
                    field="upsert",
                    old=current_status,
                    new=current_status,
                    action="skip locked claim",
                )
                continue
            _apply_claim_fields(ws, existing_row, draft, update_only=True)
            actions.append((claim_no, "updated"))
            audit_log(
                wb,
                sheet=cfg.SHEET_CLAIMS,
                address=f"{cfg.CLAIMS['claim_no']}{existing_row}",
                field="amount_usd",
                old="",
                new=str(draft.get("amount_usd", "")),
                action="update draft claim",
            )
        else:
            new_row = _next_claim_row(ws)
            _apply_claim_fields(ws, new_row, draft, update_only=False)
            actions.append((claim_no, "created"))
            audit_log(
                wb,
                sheet=cfg.SHEET_CLAIMS,
                address=f"{cfg.CLAIMS['claim_no']}{new_row}",
                field="(new)",
                old="",
                new=claim_no,
                action="create claim",
            )

    _expand_table(ws, cfg.SHEET_CLAIMS)
    return actions


def _apply_claim_fields(ws: Worksheet, row: int, draft: dict, *, update_only: bool) -> None:
    mapping = {
        "claim_no": cfg.CLAIMS["claim_no"],
        "issue_date": cfg.CLAIMS["issue_date"],
        "deal_no": cfg.CLAIMS["deal_no"],
        "consignee": cfg.CLAIMS["consignee"],
        "bill_to": cfg.CLAIMS["bill_to"],
        "period_from": cfg.CLAIMS["period_from"],
        "period_to": cfg.CLAIMS["period_to"],
        "num_trips": cfg.CLAIMS["num_trips"],
        "amount_usd": cfg.CLAIMS["amount_usd"],
        "currency": cfg.CLAIMS["currency"],
        "status": cfg.CLAIMS["status"],
        "due_date": cfg.CLAIMS["due_date"],
        "paid_date": cfg.CLAIMS["paid_date"],
        "notes": cfg.CLAIMS["notes"],
    }
    # On update, leave status/issue_date/due_date alone — they were set when the
    # draft was first created and we don't want to silently bump them.
    if update_only:
        for k in ("status", "issue_date", "due_date", "paid_date"):
            mapping.pop(k, None)
    else:
        draft = {**draft}
        draft.setdefault("status", "Draft")
        draft.setdefault("currency", cfg.DEFAULT_CURRENCY)

    for field, letter in mapping.items():
        if field in draft and draft[field] is not None:
            _cell(ws, row, letter).value = draft[field]


def update_claim_status(
    wb: Workbook,
    claim_no: str,
    new_status: str,
    paid_date: Optional[datetime] = None,
) -> bool:
    """Mirrors the MarkPaid / IssueClaim VBA helpers. Returns True if updated."""
    if new_status not in cfg.CLAIM_STATUSES:
        raise ValueError(
            f"Unknown status {new_status!r}. Allowed: {cfg.CLAIM_STATUSES}"
        )
    ws = wb[cfg.SHEET_CLAIMS]
    row = _find_claim_row(ws, claim_no)
    if row is None:
        return False
    status_cell = _cell(ws, row, cfg.CLAIMS["status"])
    old_status = _coerce_str(status_cell.value) or ""

    # The Paid status is allowed to flow from Sent; otherwise locked statuses
    # cannot be regressed by Python code.
    if old_status in cfg.CLAIM_LOCKED_STATUSES and new_status != "Paid":
        raise PermissionError(
            f"Refusing to overwrite claim {claim_no} (status={old_status})."
        )
    if old_status == "Paid":
        raise PermissionError(f"Claim {claim_no} is already Paid; not updating.")

    status_cell.value = new_status
    if new_status == "Paid":
        _cell(ws, row, cfg.CLAIMS["paid_date"]).value = paid_date or datetime.now()
    if new_status == "Sent":
        _cell(ws, row, cfg.CLAIMS["issue_date"]).value = datetime.now()

    audit_log(
        wb,
        sheet=cfg.SHEET_CLAIMS,
        address=f"{cfg.CLAIMS['status']}{row}",
        field="Status",
        old=old_status,
        new=new_status,
        action=f"set status -> {new_status}",
    )
    return True


def _expand_table(ws: Worksheet, sheet_name: str) -> None:
    """Grow the named Excel table on a sheet to cover all populated rows.

    Without this, rows appended past the original table range are not part of
    the ListObject and structured references in formulas/macros stop seeing them.
    """
    table_map = {
        cfg.SHEET_CLAIMS: "Claims",
        cfg.SHEET_TRIPS: "Trips",
        cfg.SHEET_DEALS: "Deals",
        cfg.SHEET_AUDIT: cfg.AUDIT_TABLE_NAME,
    }
    name = table_map.get(sheet_name)
    if not name or name not in ws.tables:
        return
    tbl = ws.tables[name]
    start, end = tbl.ref.split(":")
    # Parse end e.g. "R16"
    end_col_letters = "".join(c for c in end if c.isalpha())
    # Find last populated row by scanning the first column of the table.
    start_col_letters = "".join(c for c in start if c.isalpha())
    start_row = int("".join(c for c in start if c.isdigit()))
    last_row = start_row
    for r in range(start_row + 1, ws.max_row + 1):
        if _cell(ws, r, start_col_letters).value not in (None, ""):
            last_row = r
    new_ref = f"{start_col_letters}{start_row}:{end_col_letters}{last_row}"
    if new_ref != tbl.ref:
        tbl.ref = new_ref
