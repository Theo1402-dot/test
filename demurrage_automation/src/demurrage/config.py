"""Single source of truth for paths and workbook layout.

Column letters and row offsets mirror PROJECT_BRIEF.md §0 exactly.
Do not change without updating the workbook side-by-side.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
TEMPLATES_DIR = DATA_DIR / "templates"
OUTPUTS_DIR = ROOT / "outputs"
INVOICES_DIR = OUTPUTS_DIR / "invoices"
LOGS_DIR = OUTPUTS_DIR / "logs"
EML_DIR = OUTPUTS_DIR / "eml"

WORKBOOK_PATH = DATA_DIR / "MOCOH_DEMURRAGE_2026.xlsm"
CONTACTS_PATH = DATA_DIR / "contacts.yaml"

INVOICE_PREFIX = "MOC-DEM-2026-"

# --- Sheets (do not rename) ---
SHEET_COVER = "Cover"
SHEET_DASHBOARD = "Dashboard"
SHEET_INVOICE = "Invoice"
SHEET_ANNEX = "Annex"
SHEET_CLAIMS = "Claims"
SHEET_TRIPS = "Trips Ledger"
SHEET_DEALS = "Deals"
SHEET_ASSUMPTIONS = "Assumptions"
SHEET_COMPANY = "Company"
SHEET_AUDIT = "AuditLog"
SHEET_MACROS = "Macros"

# --- Trips Ledger ---
TRIPS_HEADER_ROW = 6
TRIPS_FIRST_DATA_ROW = 7
TRIPS = {
    "deal_no": "B",
    "claim_no": "C",
    "consignee": "D",
    "date_loaded": "E",
    "loading_port": "F",
    "destination": "G",
    "product": "H",
    "truck_no": "I",
    "trailer": "J",
    "transporter": "K",
    "driver": "L",
    "arrival": "M",
    "offloaded": "N",
    "waiting_d": "O",
    "laytime_d": "P",
    "excess_d": "Q",
    "rate_usd": "R",
    "demurrage_usd": "S",
    "status": "T",
    "sanity": "U",
    "month": "V",
}

# --- Claims ---
CLAIMS_HEADER_ROW = 6
CLAIMS_FIRST_DATA_ROW = 7
CLAIMS = {
    "claim_no": "B",
    "issue_date": "C",
    "deal_no": "D",
    "consignee": "E",
    "bill_to": "F",
    "period_from": "G",
    "period_to": "H",
    "num_trips": "I",
    "amount_usd": "J",
    "currency": "K",
    "status": "L",
    "due_date": "M",
    "paid_date": "N",
    "days_overdue": "O",
    "aging": "P",
    "notes": "Q",
    "actions": "R",
}
CLAIM_STATUSES = ("Draft", "Sent", "Paid", "Overdue", "Drafted in Outlook")
CLAIM_LOCKED_STATUSES = ("Sent", "Paid", "Drafted in Outlook")

# --- Deals ---
DEALS_HEADER_ROW = 6
DEALS_FIRST_DATA_ROW = 7
DEALS = {
    "deal_no": "B",
    "consignee": "C",
    "route": "D",
    "loading_port": "E",
    "destination": "F",
    "product": "G",
    "laytime_d": "H",
    "rate_usd_per_day": "I",
    "transport_usd_per_m3": "J",
    "transporter": "K",
}

# --- AuditLog (header at row 5, table named "AuditLog") ---
AUDIT_HEADER_ROW = 5
AUDIT_FIRST_DATA_ROW = 6
AUDIT_TABLE_NAME = "AuditLog"
AUDIT_COLS = {
    "timestamp": "B",
    "user": "C",
    "sheet": "D",
    "cell": "E",
    "field": "F",
    "old": "G",
    "new": "H",
    "action": "I",
}

# --- Defaults (loaded at runtime from Assumptions sheet; these are fallbacks) ---
DEFAULT_LAYTIME_DAYS = 2
DEFAULT_RATE_USD_PER_DAY = 250.0
DEFAULT_CURRENCY = "USD"
DEFAULT_FX = 1.0
PAYMENT_TERMS_DAYS = int(os.environ.get("PAYMENT_TERMS_DAYS", "30"))

# --- Environment ---
OUTLOOK_PROFILE = os.environ.get("OUTLOOK_PROFILE", "")
MANAGEMENT_CC = os.environ.get("MANAGEMENT_CC", "eafoperations@mocoh.com")
EMAIL_SIGNATURE = os.environ.get(
    "EMAIL_SIGNATURE",
    "MOCOH SA — East Africa Operations\ninvoicing@mocoh.com",
).replace("\\n", "\n")

LOGS_DIR.mkdir(parents=True, exist_ok=True)
INVOICES_DIR.mkdir(parents=True, exist_ok=True)
EML_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(command: str) -> logging.Logger:
    """Per-command logger writing to outputs/logs/{YYYY-MM-DD}_{command}.log."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = LOGS_DIR / f"{today}_{command}.log"
    logger = logging.getLogger(f"demurrage.{command}")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.addHandler(sh)
    return logger
