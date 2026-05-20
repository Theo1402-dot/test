"""demurrage-reconcile: compare Python-computed demurrage vs sheet values.

Catches manual cell overrides and formula drift. Exits non-zero on mismatch.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

import typer

from .. import config as cfg
from ..calculations import demurrage as calc_demurrage
from ..calculations import excess_days, waiting_days
from ..workbook import open_wb, read_assumptions, read_deals

# Demurrage values are USD, so anything closer than half a cent is "equal".
ATOL = 0.005


@dataclass
class Mismatch:
    row: int
    deal_no: str
    field: str
    sheet_value: object
    python_value: object


def _close(a: Optional[float], b: Optional[float]) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= ATOL


def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print every row, not just mismatches."),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Exit on the first mismatch."),
) -> None:
    """Reconcile Python-computed values against the live Trips Ledger sheet."""
    logger = cfg.get_logger("reconcile")
    logger.info("Starting reconcile against %s", cfg.WORKBOOK_PATH)

    assumptions = read_assumptions()
    deals_by_no: dict[str, object] = {d.deal_no: d for d in read_deals() if d.deal_no}

    wb = open_wb(data_only=True)
    mismatches: list[Mismatch] = []
    checked = 0
    skipped = 0
    try:
        ws = wb[cfg.SHEET_TRIPS]
        for r in range(cfg.TRIPS_FIRST_DATA_ROW, ws.max_row + 1):
            date_loaded = ws.cell(row=r, column=5).value  # E
            if date_loaded in (None, ""):
                continue
            arrival = ws.cell(row=r, column=13).value     # M
            offloaded = ws.cell(row=r, column=14).value   # N
            sheet_waiting = ws.cell(row=r, column=15).value  # O
            sheet_laytime = ws.cell(row=r, column=16).value  # P
            sheet_excess = ws.cell(row=r, column=17).value   # Q
            sheet_rate = ws.cell(row=r, column=18).value     # R
            sheet_demurrage = ws.cell(row=r, column=19).value  # S
            deal_no = ws.cell(row=r, column=2).value         # B

            try:
                py_waiting = waiting_days(date_loaded, arrival, offloaded)
            except ValueError as e:
                # Sanity column flags these; reconcile just records and continues.
                logger.warning("Row %d: %s", r, e)
                skipped += 1
                continue

            # Treat sheet's "" (blank-string-from-formula) as None for compare.
            sheet_waiting_norm: Optional[float] = (
                None if sheet_waiting in (None, "") else float(sheet_waiting)
            )
            sheet_excess_norm: Optional[float] = (
                None if sheet_excess in (None, "") else float(sheet_excess)
            )
            sheet_demurrage_norm: Optional[float] = (
                None if sheet_demurrage in (None, "") else float(sheet_demurrage)
            )

            # Use the deal's laytime/rate if known; otherwise fall back to Assumptions
            # — same precedence as the workbook's IFERROR(VLOOKUP(...), DEF_*) formula.
            deal = deals_by_no.get(str(deal_no)) if deal_no is not None else None
            laytime = (deal.laytime_d if deal and deal.laytime_d is not None
                       else assumptions.laytime_days)
            rate = (deal.rate_usd_per_day if deal and deal.rate_usd_per_day is not None
                    else assumptions.rate_usd_per_day)
            # If the sheet has its own laytime/rate (e.g. manually overridden), prefer it
            # for the comparison so we're isolating drift in derived columns.
            if sheet_laytime not in (None, ""):
                laytime = float(sheet_laytime)
            if sheet_rate not in (None, ""):
                rate = float(sheet_rate)

            py_excess = excess_days(py_waiting, laytime) if py_waiting is not None else None
            py_demurrage = calc_demurrage(py_excess, rate) if py_excess is not None else None

            checked += 1
            for field, sv, pv in [
                ("waiting_d", sheet_waiting_norm, py_waiting),
                ("excess_d", sheet_excess_norm, py_excess),
                ("demurrage_usd", sheet_demurrage_norm, py_demurrage),
            ]:
                if not _close(sv, pv):
                    m = Mismatch(row=r, deal_no=str(deal_no), field=field,
                                 sheet_value=sv, python_value=pv)
                    mismatches.append(m)
                    logger.error(
                        "MISMATCH row=%d deal=%s field=%s sheet=%r python=%r",
                        r, deal_no, field, sv, pv,
                    )
                    if fail_fast:
                        _summary(checked, skipped, mismatches, logger)
                        raise typer.Exit(code=1)
            if verbose:
                logger.info("row=%d deal=%s waiting=%s excess=%s demurrage=%.2f",
                            r, deal_no, py_waiting, py_excess, py_demurrage or 0.0)
    finally:
        wb.close()

    _summary(checked, skipped, mismatches, logger)
    if mismatches:
        raise typer.Exit(code=1)


def _summary(checked: int, skipped: int, mismatches: list[Mismatch], logger) -> None:
    logger.info(
        "Reconcile done: %d trips checked, %d skipped, %d mismatch%s.",
        checked, skipped, len(mismatches), "" if len(mismatches) == 1 else "es",
    )
    if mismatches:
        typer.echo(f"\n{len(mismatches)} mismatch(es):", err=True)
        for m in mismatches:
            typer.echo(
                f"  row={m.row} deal={m.deal_no} field={m.field} "
                f"sheet={m.sheet_value!r} python={m.python_value!r}",
                err=True,
            )
    else:
        typer.echo(f"OK — {checked} trips, zero mismatches.")


def app() -> None:
    """Console-script entry: `demurrage-reconcile`."""
    typer.run(main)


if __name__ == "__main__":
    app()
