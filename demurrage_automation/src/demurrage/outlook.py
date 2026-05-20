"""Email drafting.

  * Windows: pywin32 -> Outlook COM, draft lands in Outlook Drafts.
  * Non-Windows: write a .eml file in outputs/eml/ that opens in any mail client.

NEVER calls .Send() — PROJECT_BRIEF §6.1 hard rule.
"""

from __future__ import annotations

import html
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid
from pathlib import Path
from typing import Iterable, Optional

import yaml

from . import config as cfg
from .workbook import Claim, Company, read_claims, read_company

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class ContactBlock:
    """One counterparty's AR contacts. Mirrors a top-level key in contacts.yaml."""

    consignee: str
    primary: list[str]
    cc: list[str]
    greeting: str

    @property
    def is_drafftable(self) -> bool:
        """True iff at least one usable address (no [TBD], no empties)."""
        return any(_is_real_address(a) for a in self.primary)


@dataclass
class EmailDraft:
    """The minimal payload we hand to Outlook / write to a .eml file."""

    to: list[str]
    cc: list[str]
    subject: str
    body_text: str
    body_html: str
    attachments: list[Path] = field(default_factory=list)
    save_only: bool = True  # True = .Save() to Drafts; False = .Display() opens compose
    related_claim_no: Optional[str] = None  # informational, for logging


# ---------------------------------------------------------------------------
# Contacts loader
# ---------------------------------------------------------------------------


def _is_real_address(item: str) -> bool:
    """An address is "real" if it parses to something containing '@' and is not
    a placeholder like '[TBD]'.
    """
    if not item:
        return False
    cleaned = item.strip()
    if not cleaned or cleaned.upper() == "[TBD]" or "[TBD]" in cleaned.upper():
        return False
    _, addr = _parse_one(cleaned)
    return "@" in addr


def _parse_one(item: str) -> tuple[str, str]:
    """('Kelvin Chongo <kelvin@x>',) -> ('Kelvin Chongo', 'kelvin@x')."""
    parsed = getaddresses([item])
    if not parsed:
        return ("", "")
    name, addr = parsed[0]
    return (name.strip(), addr.strip())


def _extract_emails(items: Iterable[str]) -> list[str]:
    """Return only the bare email addresses, dropping placeholders."""
    out: list[str] = []
    for item in items:
        if not _is_real_address(item):
            continue
        _, addr = _parse_one(item)
        if addr:
            out.append(addr)
    return out


def load_contacts(path: Optional[Path] = None) -> dict[str, ContactBlock]:
    """Parse contacts.yaml into a {consignee: ContactBlock} dict."""
    path = path or cfg.CONTACTS_PATH
    if not path.exists():
        raise FileNotFoundError(f"Contacts file missing: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, ContactBlock] = {}
    for name, block in raw.items():
        if not isinstance(block, dict):
            continue
        out[name] = ContactBlock(
            consignee=name,
            primary=list(block.get("primary", []) or []),
            cc=list(block.get("cc", []) or []),
            greeting=str(block.get("greeting") or f"Dear {name} team"),
        )
    return out


def resolve_recipients(
    consignee: str, contacts: dict[str, ContactBlock]
) -> tuple[ContactBlock, list[str], list[str]]:
    """Look up the consignee's contacts and resolve to bare addresses.

    Returns (ContactBlock, to_addresses, cc_addresses). Raises KeyError if the
    consignee isn't in contacts.yaml.
    """
    if consignee not in contacts:
        raise KeyError(f"No contacts.yaml entry for consignee: {consignee!r}")
    block = contacts[consignee]
    return block, _extract_emails(block.primary), _extract_emails(block.cc)


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


TemplateName = str  # "invoice_email" | "reminder_friendly" | "reminder_firm" | "reminder_final"


def _load_template(name: TemplateName) -> str:
    path = cfg.TEMPLATES_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Email template missing: {path}")
    return path.read_text(encoding="utf-8")


def _format_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _bank_block(company: Company) -> str:
    """Compose payment instructions from the Company sheet's bank rows."""
    parts = [
        ("Beneficiary bank", company.bank_name),
        ("Account name", company.account_name),
        ("IBAN", company.iban),
        ("SWIFT / BIC", company.swift),
        ("Correspondent bank", company.correspondent_bank),
    ]
    return "\n".join(f"  {label:<20s} {value}" for label, value in parts if value)


def render_template(name: TemplateName, context: dict) -> str:
    """Run str.format on the template with `context`. Missing keys raise KeyError."""
    template = _load_template(name)
    return template.format(**context)


def _text_to_html(text: str) -> str:
    """Escape, preserve indentation by injecting non-breaking spaces, nl2br, wrap.

    Keeps the email readable in HTML clients while still letting plain-text
    readers see the same content (we always store both versions).
    """
    escaped = html.escape(text)
    # Preserve leading spaces visually in HTML (Outlook collapses them otherwise).
    lines = []
    for line in escaped.splitlines():
        leading = len(line) - len(line.lstrip(" "))
        if leading:
            line = "&nbsp;" * leading + line[leading:]
        lines.append(line)
    body = "<br>\n".join(lines)
    return (
        '<html><body><div style="font-family:Calibri,Arial,sans-serif;'
        'font-size:11pt;color:#222;">' + body + "</div></body></html>"
    )


# ---------------------------------------------------------------------------
# Builders — turn a claim into an EmailDraft
# ---------------------------------------------------------------------------


def build_invoice_email(
    claim: Claim,
    pdf_path: Path,
    *,
    contacts: Optional[dict[str, ContactBlock]] = None,
    company: Optional[Company] = None,
    signature: Optional[str] = None,
) -> EmailDraft:
    """Compose the initial-invoice cover email for a claim."""
    contacts = contacts or load_contacts()
    company = company or read_company()
    if not claim.consignee:
        raise ValueError(f"Claim {claim.claim_no} has no consignee — cannot draft")
    block, to_, cc_ = resolve_recipients(claim.consignee, contacts)
    sig = signature or cfg.EMAIL_SIGNATURE

    context = {
        "greeting": block.greeting,
        "claim_no": claim.claim_no,
        "deal_no": claim.deal_no or "",
        "consignee": claim.consignee,
        "period_from": _format_date(claim.period_from),
        "period_to": _format_date(claim.period_to),
        "num_trips": claim.num_trips or 0,
        "amount_usd": float(claim.amount_usd or 0.0),
        "due_date": _format_date(claim.due_date),
        "days_overdue": claim.days_overdue or 0,
        "bank_block": _bank_block(company),
        "signature": sig,
    }
    text = render_template("invoice_email", context)
    return EmailDraft(
        to=to_,
        cc=cc_,
        subject=f"MOCOH SA Demurrage Invoice {claim.claim_no} — Deal {claim.deal_no}",
        body_text=text,
        body_html=_text_to_html(text),
        attachments=[pdf_path] if pdf_path else [],
        related_claim_no=claim.claim_no,
    )


def build_reminder_email(
    claim: Claim,
    pdf_path: Path,
    *,
    template: TemplateName,
    contacts: Optional[dict[str, ContactBlock]] = None,
    company: Optional[Company] = None,
    signature: Optional[str] = None,
    management_cc: Optional[str] = None,
) -> EmailDraft:
    """Compose a dunning reminder. M6 uses this; defined here so the template
    rendering lives next to its sibling.
    """
    contacts = contacts or load_contacts()
    company = company or read_company()
    block, to_, cc_ = resolve_recipients(claim.consignee or "", contacts)
    sig = signature or cfg.EMAIL_SIGNATURE
    if template == "reminder_final":
        mgmt = management_cc or cfg.MANAGEMENT_CC
        if mgmt and mgmt.upper() != "[TBD]" and "@" in mgmt and mgmt not in cc_:
            cc_ = [*cc_, mgmt]

    context = {
        "greeting": block.greeting,
        "claim_no": claim.claim_no,
        "deal_no": claim.deal_no or "",
        "consignee": claim.consignee or "",
        "period_from": _format_date(claim.period_from),
        "period_to": _format_date(claim.period_to),
        "num_trips": claim.num_trips or 0,
        "amount_usd": float(claim.amount_usd or 0.0),
        "due_date": _format_date(claim.due_date),
        "days_overdue": claim.days_overdue or 0,
        "bank_block": _bank_block(company),
        "signature": sig,
    }
    text = render_template(template, context)
    subject_prefix = {
        "reminder_friendly": "Reminder",
        "reminder_firm": "Payment past due",
        "reminder_final": "Final notice",
    }.get(template, "Reminder")
    return EmailDraft(
        to=to_,
        cc=cc_,
        subject=f"[{subject_prefix}] Invoice {claim.claim_no} — {context['days_overdue']} days overdue",
        body_text=text,
        body_html=_text_to_html(text),
        attachments=[pdf_path] if pdf_path else [],
        related_claim_no=claim.claim_no,
    )


# ---------------------------------------------------------------------------
# Persist the draft (platform-dispatched)
# ---------------------------------------------------------------------------


def create_outlook_draft(draft: EmailDraft) -> str:
    """Create the draft and return an opaque handle.

      * Windows: Outlook EntryID (a hex string Outlook uses to address a mail item)
      * Non-Windows: absolute path to the .eml file we wrote
    """
    if not draft.to:
        raise ValueError("Cannot draft email with empty To: line")
    if sys.platform == "win32":
        return _create_via_outlook_com(draft)
    return _create_eml_file(draft)


def _create_via_outlook_com(draft: EmailDraft) -> str:
    """pywin32 + classic Outlook COM. Hits Drafts via .Save(); never .Send()."""
    import win32com.client  # imported lazily so non-Windows imports are clean

    ol = win32com.client.Dispatch("Outlook.Application")
    mail = ol.CreateItem(0)  # 0 = olMailItem
    mail.To = "; ".join(draft.to)
    if draft.cc:
        mail.CC = "; ".join(draft.cc)
    mail.Subject = draft.subject
    mail.HTMLBody = draft.body_html
    for att in draft.attachments:
        mail.Attachments.Add(str(Path(att).resolve()))
    if draft.save_only:
        mail.Save()          # appears in Drafts
    else:
        mail.Display()       # opens compose window for the user
    return mail.EntryID


def _slug_for_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "draft"


def _create_eml_file(draft: EmailDraft) -> str:
    """Write a MIME-multipart .eml file double-clickable in any mail client."""
    msg = EmailMessage()
    msg["Subject"] = draft.subject
    msg["To"] = ", ".join(draft.to)
    if draft.cc:
        msg["Cc"] = ", ".join(draft.cc)
    msg["Message-ID"] = make_msgid(domain="mocoh.com")
    msg["X-Mocoh-Claim"] = draft.related_claim_no or ""
    msg.set_content(draft.body_text)
    msg.add_alternative(draft.body_html, subtype="html")

    for att in draft.attachments:
        att = Path(att)
        if not att.exists():
            log.warning("Attachment missing, skipping: %s", att)
            continue
        data = att.read_bytes()
        maintype, _, subtype = _guess_mime(att).partition("/")
        msg.add_attachment(
            data,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att.name,
        )

    name = f"{_slug_for_filename(draft.related_claim_no or 'draft')}_{datetime.now():%Y%m%d_%H%M%S}.eml"
    out_path = cfg.EML_DIR / name
    out_path.write_bytes(bytes(msg))
    return str(out_path.resolve())


def _guess_mime(path: Path) -> str:
    import mimetypes

    mtype, _ = mimetypes.guess_type(str(path))
    return mtype or "application/octet-stream"
