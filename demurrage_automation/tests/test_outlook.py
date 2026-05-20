"""Outlook drafting (with .eml fallback on non-Windows)."""

from __future__ import annotations

import email
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from demurrage import config as cfg
from demurrage.outlook import (
    ContactBlock,
    EmailDraft,
    _create_eml_file,
    _extract_emails,
    _is_real_address,
    _parse_one,
    _text_to_html,
    build_invoice_email,
    build_reminder_email,
    create_outlook_draft,
    load_contacts,
    render_template,
    resolve_recipients,
)
from demurrage.workbook import Claim, Company


# ---------- address parsing ----------


@pytest.mark.parametrize(
    "item,is_real",
    [
        ("Kelvin Chongo <kelvin.chongo@rubiszambia.com>", True),
        ("bondodelphin@lagraddie.com", True),
        ("[TBD]", False),
        ("Pending [TBD] resolution", False),
        ("", False),
        ("   ", False),
        ("not-an-email", False),
    ],
)
def test_is_real_address(item, is_real):
    assert _is_real_address(item) is is_real


def test_parse_one_strips_brackets():
    name, addr = _parse_one("Kelvin Chongo <kelvin.chongo@rubiszambia.com>")
    assert name == "Kelvin Chongo"
    assert addr == "kelvin.chongo@rubiszambia.com"


def test_extract_emails_drops_placeholders_and_blanks():
    items = [
        "Kelvin Chongo <kelvin.chongo@rubiszambia.com>",
        "[TBD]",
        "bondodelphin@lagraddie.com",
        "",
        "Reliance Energy Zambia Limited <sales@relianceenergy-zm.com>",
    ]
    assert _extract_emails(items) == [
        "kelvin.chongo@rubiszambia.com",
        "bondodelphin@lagraddie.com",
        "sales@relianceenergy-zm.com",
    ]


# ---------- contacts.yaml ----------


def test_contacts_loads_real_file():
    contacts = load_contacts()
    assert "Rubis Energy Zambia" in contacts
    assert "ARV Energy" in contacts
    rubis = contacts["Rubis Energy Zambia"]
    assert rubis.consignee == "Rubis Energy Zambia"
    assert any("rubiszambia.com" in a for a in rubis.primary)
    assert rubis.greeting.startswith("Dear Rubis")


def test_contacts_skipped_when_only_tbd(tmp_path: Path, monkeypatch):
    p = tmp_path / "contacts.yaml"
    p.write_text(yaml.safe_dump({
        "Nobody Co": {"primary": ["[TBD]"], "cc": [], "greeting": "Dear Nobody"},
        "Real Co": {"primary": ["ar@real.com"], "cc": [], "greeting": "Dear Real"},
    }), encoding="utf-8")
    monkeypatch.setattr(cfg, "CONTACTS_PATH", p)
    contacts = load_contacts()
    assert contacts["Nobody Co"].is_drafftable is False
    assert contacts["Real Co"].is_drafftable is True


def test_resolve_recipients_uses_first_extracted_address():
    contacts = load_contacts()
    block, to_, cc_ = resolve_recipients("Lake Petroleum Zambia", contacts)
    assert block.consignee == "Lake Petroleum Zambia"
    assert "bhanu.pratap@lakeoilgroup.com" in to_
    assert all("@" in a for a in to_)
    assert cc_ == []


def test_resolve_recipients_missing_consignee_raises():
    with pytest.raises(KeyError):
        resolve_recipients("Acme Imaginary Ltd", load_contacts())


# ---------- template render ----------


def test_render_invoice_email_substitutes_all_fields():
    ctx = {
        "greeting": "Dear team",
        "claim_no": "TEST-DEM",
        "deal_no": "TEST",
        "consignee": "Test Co",
        "period_from": "2026-05-01",
        "period_to": "2026-05-31",
        "num_trips": 4,
        "amount_usd": 1234.5,
        "due_date": "2026-06-19",
        "days_overdue": 0,
        "bank_block": "  IBAN  CH...",
        "signature": "Theo",
    }
    text = render_template("invoice_email", ctx)
    assert "TEST-DEM" in text
    assert "USD 1,234.50" in text
    assert "Dear team" in text
    assert "{" not in text and "}" not in text


def test_text_to_html_escapes_and_keeps_indent():
    rendered = _text_to_html("  Hello <b>world</b>\nLine two")
    assert "&lt;b&gt;" in rendered
    assert "&nbsp;&nbsp;Hello" in rendered
    assert "<br>" in rendered


# ---------- build_invoice_email ----------


def _claim(**over) -> Claim:
    base = dict(
        row=7,
        claim_no="187296-DEM",
        deal_no="187296",
        consignee="Rubis Energy Zambia",
        period_from=datetime(2026, 2, 19),
        period_to=datetime(2026, 2, 20),
        num_trips=12,
        amount_usd=21500.0,
        currency="USD",
        status="Draft",
        due_date=datetime(2026, 6, 19),
    )
    base.update(over)
    return Claim(**base)


def _co() -> Company:
    return Company(
        legal_name="MOCOH SA",
        bank_name="BANQUE INT'L",
        account_name="MOCOHSA",
        iban="CH79 0000 0000 0000 0000 0",
        swift="BICFCHGGXXX",
        correspondent_bank="JPMORGAN NY",
    )


def test_build_invoice_email_populates_recipients_and_subject(tmp_path: Path):
    contacts = load_contacts()
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    d = build_invoice_email(_claim(), pdf, contacts=contacts, company=_co())
    assert "187296-DEM" in d.subject
    assert "Deal 187296" in d.subject
    assert d.to, "must have at least one addressable recipient"
    assert all("@" in a for a in d.to)
    assert "USD 21,500.00" in d.body_text
    assert "<html>" in d.body_html
    assert d.attachments == [pdf]
    assert d.related_claim_no == "187296-DEM"


def test_build_reminder_final_ccs_management():
    contacts = load_contacts()
    pdf = Path("/tmp/missing.pdf")  # attachment doesn't need to exist for the build
    d = build_reminder_email(
        _claim(days_overdue=18),
        pdf,
        template="reminder_final",
        contacts=contacts,
        company=_co(),
        management_cc="eafoperations@mocoh.com",
    )
    assert "eafoperations@mocoh.com" in d.cc
    assert "Final notice" in d.subject


def test_build_reminder_friendly_does_not_cc_management():
    contacts = load_contacts()
    d = build_reminder_email(
        _claim(days_overdue=3),
        Path("/tmp/x.pdf"),
        template="reminder_friendly",
        contacts=contacts,
        company=_co(),
        management_cc="eafoperations@mocoh.com",
    )
    assert "eafoperations@mocoh.com" not in d.cc


# ---------- .eml fallback ----------


def test_eml_file_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cfg, "EML_DIR", tmp_path)
    pdf = tmp_path / "MOC-DEM-2026-187296.pdf"
    pdf.write_bytes(b"%PDF-1.4 attachment-test")
    draft = EmailDraft(
        to=["a@x.com", "b@x.com"],
        cc=["c@x.com"],
        subject="Test subject",
        body_text="Hello\nWorld",
        body_html="<html><body>Hello<br>World</body></html>",
        attachments=[pdf],
        related_claim_no="187296-DEM",
    )
    path = Path(_create_eml_file(draft))
    assert path.exists()
    msg = email.message_from_bytes(path.read_bytes())
    assert msg["Subject"] == "Test subject"
    assert "a@x.com" in msg["To"] and "b@x.com" in msg["To"]
    assert msg["Cc"] == "c@x.com"
    assert msg["X-Mocoh-Claim"] == "187296-DEM"
    # multipart: text/plain + text/html + application/pdf
    parts = list(msg.walk())
    content_types = {p.get_content_type() for p in parts}
    assert "text/plain" in content_types
    assert "text/html" in content_types
    assert "application/pdf" in content_types


def test_create_outlook_draft_empty_to_raises():
    with pytest.raises(ValueError):
        create_outlook_draft(EmailDraft(
            to=[], cc=[], subject="x", body_text="x", body_html="<p>x</p>",
        ))
