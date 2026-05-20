"""Append-only writer for the AuditLog sheet.

Matches the shape of the VBA LogAudit subroutine exactly:
    Timestamp | User | Sheet | Cell | Field | Old | New | Action
"""

from __future__ import annotations

import getpass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from openpyxl.utils import column_index_from_string

from . import config as cfg

if TYPE_CHECKING:  # avoid runtime import cycle with workbook.py
    from openpyxl.workbook import Workbook


def _current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def _next_audit_row(ws) -> int:
    """First fully-empty row past the AuditLog header."""
    ts_col = column_index_from_string(cfg.AUDIT_COLS["timestamp"])
    for r in range(cfg.AUDIT_FIRST_DATA_ROW, ws.max_row + 2):
        if ws.cell(row=r, column=ts_col).value in (None, ""):
            return r
    return ws.max_row + 1


def log(
    wb: "Workbook",
    *,
    sheet: str,
    address: str,
    field: str,
    old: object,
    new: object,
    action: str,
    when: Optional[datetime] = None,
    user: Optional[str] = None,
) -> int:
    """Append one row to AuditLog. Returns the row written."""
    ws = wb[cfg.SHEET_AUDIT]
    r = _next_audit_row(ws)
    ws.cell(row=r, column=column_index_from_string(cfg.AUDIT_COLS["timestamp"])).value = when or datetime.now()
    ws.cell(row=r, column=column_index_from_string(cfg.AUDIT_COLS["user"])).value = user or _current_user()
    ws.cell(row=r, column=column_index_from_string(cfg.AUDIT_COLS["sheet"])).value = sheet
    ws.cell(row=r, column=column_index_from_string(cfg.AUDIT_COLS["cell"])).value = address
    ws.cell(row=r, column=column_index_from_string(cfg.AUDIT_COLS["field"])).value = field
    ws.cell(row=r, column=column_index_from_string(cfg.AUDIT_COLS["old"])).value = "" if old is None else str(old)
    ws.cell(row=r, column=column_index_from_string(cfg.AUDIT_COLS["new"])).value = "" if new is None else str(new)
    ws.cell(row=r, column=column_index_from_string(cfg.AUDIT_COLS["action"])).value = action

    _expand_audit_table(ws, r)
    return r


def _expand_audit_table(ws, last_row: int) -> None:
    """Grow the AuditLog ListObject to include the newly appended row."""
    if cfg.AUDIT_TABLE_NAME not in ws.tables:
        return
    tbl = ws.tables[cfg.AUDIT_TABLE_NAME]
    start, end = tbl.ref.split(":")
    end_col = "".join(c for c in end if c.isalpha())
    start_col = "".join(c for c in start if c.isalpha())
    start_row = int("".join(c for c in start if c.isdigit()))
    new_ref = f"{start_col}{start_row}:{end_col}{max(last_row, start_row + 1)}"
    if new_ref != tbl.ref:
        tbl.ref = new_ref
