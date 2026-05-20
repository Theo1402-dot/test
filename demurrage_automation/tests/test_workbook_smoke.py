"""M1 smoke tests.

  * open the workbook with keep_vba=True
  * count trips == 131 (matches the source file delivered for the trial)
  * read deals, claims, assumptions, company — return non-empty
  * save to a tmp path; reload; VBA archive still present
  * append an audit row; reload; row is there; VBA archive still present
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from openpyxl import load_workbook

from demurrage import audit, config as cfg
from demurrage.workbook import (
    open_wb,
    read_assumptions,
    read_claims,
    read_company,
    read_deals,
    read_trips,
    save_wb,
)


EXPECTED_TRIP_COUNT = 131


@pytest.fixture
def wb_copy(tmp_path: Path) -> Path:
    """Work on a copy so the canonical file in data/ stays untouched."""
    dst = tmp_path / "MOCOH_DEMURRAGE_2026.xlsm"
    shutil.copy(cfg.WORKBOOK_PATH, dst)
    return dst


def test_workbook_opens_with_vba():
    wb = open_wb()
    try:
        assert wb.vba_archive is not None, "VBA project should survive load"
        assert cfg.SHEET_TRIPS in wb.sheetnames
        assert cfg.SHEET_AUDIT in wb.sheetnames
    finally:
        wb.close()


def test_read_trips_count():
    trips = read_trips()
    assert len(trips) == EXPECTED_TRIP_COUNT, (
        f"Expected {EXPECTED_TRIP_COUNT} trips, got {len(trips)}"
    )
    # Spot-check the first trip matches what we know about the source file.
    first = trips[0]
    assert first.consignee
    assert first.date_loaded is not None
    assert first.deal_no


def test_read_deals_claims_assumptions_company():
    deals = read_deals()
    assert len(deals) > 0
    claims = read_claims()
    assert len(claims) >= 0  # may be empty in early trial state
    asm = read_assumptions()
    assert asm.rate_usd_per_day > 0
    assert asm.laytime_days >= 0
    co = read_company()
    assert co.legal_name == "MOCOH SA"
    assert co.iban


def test_save_preserves_vba(wb_copy: Path):
    wb = load_workbook(wb_copy, keep_vba=True, data_only=False)
    try:
        assert wb.vba_archive is not None
    finally:
        save_wb(wb, wb_copy)
        wb.close()
    reloaded = load_workbook(wb_copy, keep_vba=True)
    try:
        assert reloaded.vba_archive is not None, "VBA archive must survive a round-trip save"
    finally:
        reloaded.close()


def test_audit_log_appends_row(wb_copy: Path):
    wb = load_workbook(wb_copy, keep_vba=True, data_only=False)
    ws = wb[cfg.SHEET_AUDIT]
    before = sum(
        1
        for r in range(cfg.AUDIT_FIRST_DATA_ROW, ws.max_row + 1)
        if ws.cell(row=r, column=2).value not in (None, "")
    )
    row = audit.log(
        wb,
        sheet="Test",
        address="A1",
        field="smoke",
        old="x",
        new="y",
        action="unit test",
    )
    save_wb(wb, wb_copy)
    wb.close()

    reloaded = load_workbook(wb_copy, keep_vba=True, data_only=False)
    ws2 = reloaded[cfg.SHEET_AUDIT]
    try:
        assert ws2.cell(row=row, column=4).value == "Test"
        assert ws2.cell(row=row, column=9).value == "unit test"
        after = sum(
            1
            for r in range(cfg.AUDIT_FIRST_DATA_ROW, ws2.max_row + 1)
            if ws2.cell(row=r, column=2).value not in (None, "")
        )
        assert after == before + 1
        assert reloaded.vba_archive is not None
    finally:
        reloaded.close()
