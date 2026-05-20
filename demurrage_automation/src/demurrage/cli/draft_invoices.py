"""demurrage-draft: render invoice PDFs + (optionally) create Outlook drafts.

  $ demurrage-draft --claim 187296-DEM
  $ demurrage-draft --all-drafts --with-outlook
  $ demurrage-draft --all-drafts --with-outlook --no-mark-drafted

On Windows the draft lands in Outlook's Drafts folder via pywin32.
Elsewhere a .eml file is written under outputs/eml/ that opens in any mail
client. Nothing is ever auto-sent — PROJECT_BRIEF §6.1.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import typer

from .. import config as cfg
from ..invoice_pdf import render_invoice_pdf
from ..outlook import (
    build_invoice_email,
    create_outlook_draft,
    load_contacts,
    resolve_recipients,
)
from ..workbook import Claim, open_wb, read_claims, read_company, save_wb, update_claim_status


def _eligible_drafts() -> list[Claim]:
    return [c for c in read_claims() if c.claim_no and c.status == "Draft"]


def _find_claim(claim_no: str) -> Optional[Claim]:
    for c in read_claims():
        if c.claim_no == claim_no:
            return c
    return None


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
        False, "--with-outlook", help="Also create an Outlook draft (or .eml fallback)."
    ),
    mark_drafted: bool = typer.Option(
        True,
        "--mark-drafted/--no-mark-drafted",
        help="When --with-outlook succeeds, flip the claim's Status to 'Drafted in Outlook' so a re-run won't duplicate the draft.",
    ),
    fail_fast: bool = typer.Option(
        False, "--fail-fast", help="Exit on the first failure."
    ),
) -> None:
    """Render Invoice + Annex PDF for a claim, and (optionally) draft the cover email."""
    if claim and all_drafts:
        raise typer.BadParameter("--claim and --all-drafts are mutually exclusive.")
    if not claim and not all_drafts:
        raise typer.BadParameter("Pass --claim CLAIM_NO or --all-drafts.")

    logger = cfg.get_logger("draft")

    if claim:
        c = _find_claim(claim)
        if c is None:
            raise typer.BadParameter(f"No claim row found for {claim!r}.")
        if c.status != "Draft":
            typer.echo(f"WARNING: {claim} has Status={c.status!r}; rendering anyway.", err=True)
        targets: list[Claim] = [c]
    else:
        targets = _eligible_drafts()

    if not targets:
        typer.echo("No Draft claims to render.")
        return

    contacts = load_contacts() if with_outlook else None
    company = read_company() if with_outlook else None

    today = date.today()
    rendered: list[tuple[str, Path, Optional[str]]] = []  # (claim_no, pdf, draft_handle)
    failed: list[tuple[str, str]] = []
    to_mark: list[str] = []

    for c in targets:
        try:
            logger.info("Rendering invoice PDF for %s", c.claim_no)
            pdf_path = render_invoice_pdf(
                c.claim_no, output_dir=output_dir, issue_date=today,
                consignee=c.consignee or "",
            )
            logger.info("Wrote %s (%d bytes)", pdf_path, pdf_path.stat().st_size)

            handle: Optional[str] = None
            if with_outlook:
                handle = _draft_email_for(c, pdf_path, contacts, company, logger)
                if handle and mark_drafted:
                    to_mark.append(c.claim_no)
            rendered.append((c.claim_no, pdf_path, handle))
        except Exception as exc:  # noqa: BLE001 — CLI boundary
            logger.error("Failed to process %s: %s", c.claim_no, exc)
            failed.append((c.claim_no, str(exc)))
            if fail_fast:
                break

    if to_mark:
        _mark_drafted(to_mark, logger)

    _print_summary(rendered, failed, with_outlook)
    if failed:
        raise typer.Exit(code=1)


def _draft_email_for(
    claim: Claim,
    pdf_path: Path,
    contacts,
    company,
    logger,
) -> Optional[str]:
    """Compose + persist the Outlook draft for one claim. Returns the handle
    (EntryID on Windows, .eml path elsewhere) or None when skipped.
    """
    if not claim.consignee:
        logger.warning("Skipping email for %s: no consignee on claim row.", claim.claim_no)
        return None
    if claim.consignee not in contacts:
        logger.warning(
            "Skipping email for %s: consignee %r missing from contacts.yaml. "
            "Add an entry and re-run.", claim.claim_no, claim.consignee,
        )
        return None
    _, to_, _cc = resolve_recipients(claim.consignee, contacts)
    if not to_:
        logger.warning(
            "Skipping email for %s: contacts.yaml has no usable address for %r "
            "(every primary entry is empty or [TBD]).",
            claim.claim_no, claim.consignee,
        )
        return None

    draft = build_invoice_email(claim, pdf_path, contacts=contacts, company=company)
    handle = create_outlook_draft(draft)
    logger.info("Drafted email for %s -> %s", claim.claim_no, handle)
    return handle


def _mark_drafted(claim_nos: list[str], logger) -> None:
    """Flip the listed claims to Status='Drafted in Outlook'. Best-effort: a
    single update_claim_status failure does not abort the others.
    """
    wb = open_wb(data_only=False)
    try:
        for claim_no in claim_nos:
            try:
                if update_claim_status(wb, claim_no, "Drafted in Outlook"):
                    logger.info("Flipped %s status -> Drafted in Outlook", claim_no)
                else:
                    logger.warning("No row found for %s when marking drafted.", claim_no)
            except PermissionError as e:
                logger.warning("Could not mark %s as drafted: %s", claim_no, e)
        save_wb(wb)
    finally:
        wb.close()


def _print_summary(
    rendered: list[tuple[str, Path, Optional[str]]],
    failed: list[tuple[str, str]],
    with_outlook: bool,
) -> None:
    typer.echo(f"\nRendered {len(rendered)} PDF(s){' + drafted emails' if with_outlook else ''}:")
    for claim_no, pdf, handle in rendered:
        if handle:
            typer.echo(f"  + {claim_no:<22s} PDF={pdf}")
            typer.echo(f"    {'':<22s} draft={handle}")
        else:
            typer.echo(f"  + {claim_no:<22s} PDF={pdf}")
    if failed:
        typer.echo(f"\n{len(failed)} failure(s):", err=True)
        for claim_no, msg in failed:
            typer.echo(f"  ! {claim_no:<22s} {msg}", err=True)


def app() -> None:
    """Console-script entry: `demurrage-draft`."""
    typer.run(main)


if __name__ == "__main__":
    app()
