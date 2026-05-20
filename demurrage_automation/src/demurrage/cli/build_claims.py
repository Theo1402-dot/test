"""demurrage-build-claims: group trips into draft claims for a reporting period.

  $ demurrage-build-claims --from 2026-05-01 --to 2026-05-31

Idempotent. Re-running with the same period:
  * existing Draft rows for the same claim_no are updated in place (no duplicate)
  * Sent/Paid/'Drafted in Outlook' rows are left untouched (logged + skipped)
  * new claims are appended above the Claims!Total row, which is auto-refreshed
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import typer

from .. import config as cfg
from ..claims import group_trips_to_claims, upsert_claims
from ..workbook import open_wb, read_assumptions, read_deals, read_trips, save_wb


def _parse_iso_date(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as e:
        raise typer.BadParameter(
            f"Expected ISO date YYYY-MM-DD, got {value!r}: {e}"
        )


def main(
    period_from: str = typer.Option(..., "--from", "-f", help="Period start (inclusive), YYYY-MM-DD."),
    period_to: str = typer.Option(..., "--to", "-t", help="Period end (inclusive), YYYY-MM-DD."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would change; do not save the workbook."),
    issue_date: Optional[str] = typer.Option(None, "--issue-date", help="Override Issue Date (defaults to today). YYYY-MM-DD."),
) -> None:
    """Build draft claims for the [--from, --to] period and upsert into Claims."""
    logger = cfg.get_logger("build_claims")
    pf = _parse_iso_date(period_from)
    pt = _parse_iso_date(period_to)
    if pt < pf:
        raise typer.BadParameter(f"--to {pt:%Y-%m-%d} precedes --from {pf:%Y-%m-%d}")
    issued = _parse_iso_date(issue_date) if issue_date else None

    logger.info("Building claims for %s -> %s%s", pf.date(), pt.date(),
                " (dry-run)" if dry_run else "")

    trips = read_trips()
    logger.info("Read %d trip rows", len(trips))
    deals = read_deals()
    deals_by_no = {d.deal_no: d for d in deals if d.deal_no}
    assumptions = read_assumptions()
    drafts = group_trips_to_claims(
        trips, pf, pt, deals_by_no=deals_by_no, assumptions=assumptions
    )
    logger.info("Grouped into %d claim draft(s)", len(drafts))

    if not drafts:
        typer.echo("No eligible trips in period — nothing to do.")
        return

    if dry_run:
        typer.echo(f"\nDRY RUN: {len(drafts)} claim draft(s) for {pf.date()} -> {pt.date()}\n")
        _print_table(drafts)
        return

    # Write phase: open with data_only=False so formulas survive.
    wb = open_wb(data_only=False)
    try:
        actions = upsert_claims(wb, drafts, issue_date=issued)
        save_wb(wb)
    finally:
        wb.close()

    created = sum(1 for _, a in actions if a == "created")
    updated = sum(1 for _, a in actions if a == "updated")
    skipped = sum(1 for _, a in actions if a.startswith("skipped"))
    logger.info("Upsert done: %d created, %d updated, %d skipped.",
                created, updated, skipped)
    typer.echo(
        f"\n{len(actions)} claim(s) processed: "
        f"{created} created, {updated} updated, {skipped} skipped."
    )
    for claim_no, action in actions:
        marker = "+" if action == "created" else ("~" if action == "updated" else "·")
        typer.echo(f"  {marker} {claim_no:<18s} {action}")


def _print_table(drafts) -> None:
    typer.echo(
        f"{'Claim No.':<18s} {'Deal':<10s} {'Consignee':<28s} "
        f"{'From':<11s} {'To':<11s} {'#Trips':>6s} {'Amount (USD)':>14s}"
    )
    typer.echo("-" * 100)
    for d in drafts:
        typer.echo(
            f"{d.claim_no:<18s} {d.deal_no:<10s} {d.consignee[:28]:<28s} "
            f"{d.period_from:%Y-%m-%d} {d.period_to:%Y-%m-%d} "
            f"{d.num_trips:>6d} {d.amount_usd:>14,.2f}"
        )


def app() -> None:
    """Console-script entry: `demurrage-build-claims`."""
    typer.run(main)


if __name__ == "__main__":
    app()
