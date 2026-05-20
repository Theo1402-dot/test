"""demurrage-draft: render invoice PDFs for one or many Draft claims.

  $ demurrage-draft --claim 187296-DEM
  $ demurrage-draft --all-drafts

M4 scope: PDF rendering only. Outlook draft creation is wired in M5 — the
--with-outlook flag is reserved here so the CLI surface doesn't churn later.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from .. import config as cfg
from ..invoice_pdf import render_invoice_pdf
from ..workbook import read_claims


def _eligible_drafts() -> list[str]:
    """Claim numbers with Status == 'Draft' — the targets of --all-drafts."""
    return [c.claim_no for c in read_claims() if c.claim_no and c.status == "Draft"]


def main(
    claim: Optional[str] = typer.Option(
        None, "--claim", "-c", help="Render a single claim, e.g. 187296-DEM."
    ),
    all_drafts: bool = typer.Option(
        False, "--all-drafts", help="Render every claim with Status == 'Draft'."
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Override outputs/invoices/.", file_okay=False
    ),
    with_outlook: bool = typer.Option(
        False,
        "--with-outlook",
        help="Reserved for M5: also create an Outlook draft per PDF.",
    ),
    fail_fast: bool = typer.Option(
        False, "--fail-fast", help="Exit on the first render failure."
    ),
) -> None:
    """Render Invoice + Annex for a Draft claim to PDF (M4 scope)."""
    if claim and all_drafts:
        raise typer.BadParameter("--claim and --all-drafts are mutually exclusive.")
    if not claim and not all_drafts:
        raise typer.BadParameter("Pass --claim CLAIM_NO or --all-drafts.")

    logger = cfg.get_logger("draft")
    targets = [claim] if claim else _eligible_drafts()
    if not targets:
        typer.echo("No Draft claims to render.")
        return

    if with_outlook:
        # Don't pretend to do something we won't until M5.
        typer.echo(
            "WARNING: --with-outlook is not implemented until M5; rendering PDFs only.",
            err=True,
        )

    today = date.today()
    rendered: list[tuple[str, Path]] = []
    failed: list[tuple[str, str]] = []

    for claim_no in targets:
        try:
            logger.info("Rendering invoice PDF for %s", claim_no)
            path = render_invoice_pdf(
                claim_no, output_dir=output_dir, issue_date=today
            )
            rendered.append((claim_no, path))
            logger.info("Wrote %s (%d bytes)", path, path.stat().st_size)
        except Exception as exc:  # noqa: BLE001 — CLI boundary
            logger.error("Failed to render %s: %s", claim_no, exc)
            failed.append((claim_no, str(exc)))
            if fail_fast:
                break

    typer.echo(f"\nRendered {len(rendered)} PDF(s):")
    for claim_no, path in rendered:
        typer.echo(f"  + {claim_no:<22s} {path}")
    if failed:
        typer.echo(f"\n{len(failed)} failure(s):", err=True)
        for claim_no, msg in failed:
            typer.echo(f"  ! {claim_no:<22s} {msg}", err=True)
        raise typer.Exit(code=1)


def app() -> None:
    """Console-script entry: `demurrage-draft`."""
    typer.run(main)


if __name__ == "__main__":
    app()
