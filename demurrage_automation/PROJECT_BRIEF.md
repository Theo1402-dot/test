# MOCOH Demurrage Automation — Build Brief

**For:** Claude Code, working inside this folder.
**Owner:** Theo (operations, MOCOH SA, East Africa flows).
**Goal:** Turn `MOCOH_DEMURRAGE_2026.xlsm` (already built — see `data/`) into a fully automated demurrage workflow. Capture trips → build claims → generate invoice PDFs → draft Outlook emails to counterparties → track status → dun overdue → report. **Nothing is auto-sent without me clicking Send in Outlook.**

---

## 0. Context you need to know

The workbook is already designed. Don't redesign it. Your job is to build the Python layer **around** it.

### Existing sheets and their roles (do not rename)
| Sheet | Purpose |
|---|---|
| `Cover` | Landing page, navigation, headline KPIs |
| `Dashboard` | Live KPIs (total demurrage, by consignee, by transporter, top deals) |
| `Trips Ledger` | One row per truck loading. Source of truth for trips. |
| `Claims` | One row per claim (= one deal, one period). Status lifecycle: Draft → Sent → Paid / Overdue |
| `Deals` | Deal registry: deal no., consignee, route, product, laytime, rate |
| `Invoice` | Invoice template (renders for a single claim selected in `B20`) |
| `Annex` | Per-trip detail printed behind the invoice |
| `Assumptions` | Defaults: laytime 2d, rate $250/d, FX, reporting period |
| `Company` | MOCOH SA issuer info, bank details, invoice prefix `MOC-DEM-2026-` |
| `AuditLog` | Append-only log of mutations |
| `Macros` | VBA reference (already pasted in `ThisWorkbook` and a Module) |

### Existing column layout (memorize, do not change)

**`Trips Ledger` (header row 6, data starts row 7):**
B=Deal No., C=Claim No., D=Consignee, E=Date Loaded, F=Loading Port, G=Destination, H=Product, I=Truck No., J=Trailer Reg., K=Transporter, L=Driver, M=Arrival, N=Offloaded, O=Waiting (d), P=Laytime (d), Q=Excess (d), R=Rate (USD), S=Demurrage (USD), T=Status, U=Sanity, V=Month

**`Claims` (header row 6, data row 7+):**
B=Claim No., C=Issue Date, D=Deal No., E=Consignee, F=Bill-To Address, G=Period From, H=Period To, I=# Trips, J=Amount (USD), K=Currency, L=Status, M=Due Date, N=Paid Date, O=Days Overdue, P=Aging, Q=Notes, R=Actions

**`Deals` (header row 6, data row 7+):**
B=Deal No., C=Consignee, D=Route, E=Loading Port, F=Destination, G=Product, H=Laytime (days), I=Rate (USD/day), J=Transport (USD/m³), K=Transporter

### Existing VBA already in the workbook (don't touch)
`IssueClaim`, `MarkPaid`, `CreateClaimFromFiltered`, `LogAudit`, `PublishInvoicePDF`, and a `Workbook_SheetChange` handler that logs status edits. Keep them — Python work alongside, doesn't replace.

### Counterparties currently in the book
Rubis Energy Zambia, Reliance Energy Zambia, Lake Petroleum Zambia, ARV Energy, La Grace De Dieu Avec Nous Sarl. (More will come — onboarding is config, not code.)

---

## 1. Target folder layout

Build exactly this. Don't invent extra dirs.

```
demurrage_automation/
├── PROJECT_BRIEF.md                       ← this file
├── README.md                              ← short, for daily use
├── pyproject.toml                         ← deps + console scripts
├── .env.example                           ← OUTLOOK_PROFILE, etc.
├── data/
│   ├── MOCOH_DEMURRAGE_2026.xlsm          ← source of truth (already there)
│   ├── contacts.yaml                      ← counterparty AR contacts + cc list
│   └── templates/
│       ├── invoice_email.txt              ← initial invoice cover email
│       ├── reminder_friendly.txt          ← D+0 after due
│       ├── reminder_firm.txt              ← D+7
│       └── reminder_final.txt             ← D+14, cc management
├── outputs/
│   ├── invoices/                          ← generated PDFs, named by claim no.
│   └── logs/                              ← timestamped run logs
├── src/demurrage/
│   ├── __init__.py
│   ├── config.py                          ← paths, sheet/column constants
│   ├── workbook.py                        ← all openpyxl read/write
│   ├── calculations.py                    ← waiting → excess → demurrage math
│   ├── claims.py                          ← group trips by deal+period → claim
│   ├── invoice_pdf.py                     ← render Invoice+Annex → PDF (xlwings)
│   ├── outlook.py                         ← draft Outlook mails (pywin32)
│   ├── dunning.py                         ← scan overdue, draft reminders
│   ├── dashboard.py                       ← recompute KPIs (writes back to Dashboard sheet)
│   └── audit.py                           ← append rows to AuditLog
├── scripts/                               ← thin CLI entry points
│   ├── import_trips.py
│   ├── build_claims.py
│   ├── draft_invoices.py
│   ├── run_dunning.py
│   ├── refresh_dashboard.py
│   └── reconcile.py
└── tests/
    ├── test_calculations.py
    ├── test_claims.py
    └── fixtures/sample_workbook.xlsm
```

---

## 2. Tech stack

- **Python 3.11+**
- `openpyxl` — read/write xlsm without breaking VBA (`keep_vba=True`)
- `xlwings` — drives Excel COM to render PDF using the existing Invoice+Annex template (Windows; falls back to LibreOffice headless on non-Windows)
- `pywin32` — Outlook COM (`win32com.client.Dispatch("Outlook.Application")`) on Windows; on Mac/Linux build `.eml` files via `email.message.EmailMessage`
- `pydantic` v2 — strict models for Trip, Claim, Contact, EmailDraft
- `typer` — CLI entry points
- `pyyaml` — contacts.yaml
- `python-dotenv` — `.env`
- `pytest` — tests

Pin everything in `pyproject.toml`. Expose console scripts: `demurrage-import`, `demurrage-build-claims`, `demurrage-draft`, `demurrage-dun`, `demurrage-refresh`, `demurrage-reconcile`.

**Platform detection:** `src/demurrage/outlook.py` checks `sys.platform`. On `win32` → real Outlook drafts. Otherwise → `.eml` files in `outputs/eml/` that open in any mail client.

---

## 3. Module specs

### 3.1 `config.py`
Single source of truth for paths and column positions. Mirror section 0 exactly. Example:
```python
WORKBOOK_PATH = ROOT / "data" / "MOCOH_DEMURRAGE_2026.xlsm"
TRIPS_HEADER_ROW = 6
TRIPS = {"deal_no": "B", "claim_no": "C", "consignee": "D", "date_loaded": "E",
         "loading_port": "F", "destination": "G", "product": "H",
         "truck_no": "I", "trailer": "J", "transporter": "K", "driver": "L",
         "arrival": "M", "offloaded": "N", "waiting_d": "O", "laytime_d": "P",
         "excess_d": "Q", "rate_usd": "R", "demurrage_usd": "S",
         "status": "T", "sanity": "U", "month": "V"}
```

### 3.2 `workbook.py`
- `open_wb()` — `load_workbook(..., keep_vba=True, data_only=False)`
- `read_trips() -> list[Trip]` — pydantic models, skip rows where Date Loaded is empty
- `read_claims()`, `read_deals()`, `read_assumptions()`, `read_company()`
- `write_claims(rows)` — appends new claims, never overwrites existing rows
- `update_claim_status(claim_no, status, paid_date=None)` — mirrors `MarkPaid` macro
- **Every write calls `audit.log(...)`**
- Save with `wb.save(path)`; the VBA project must survive (test it).

### 3.3 `calculations.py`
Pure functions, no I/O:
- `waiting_days(date_loaded, arrival, offloaded) -> int`
- `excess_days(waiting, laytime) -> int` — `max(0, waiting - laytime)`
- `demurrage(excess, rate) -> float`
- `aging_bucket(days_overdue) -> Literal["Current", "1-30", "31-60", "61-90", "90+"]`

All these are already implemented as Excel formulas in the workbook — Python versions exist for **validation** (catch discrepancies) and for **claim aggregation** (sum without Excel open). Unit-test every edge case.

### 3.4 `claims.py`
- `group_trips_to_claims(trips, period_from, period_to) -> list[ClaimDraft]`
  - Group by `deal_no`
  - Filter trips where `date_loaded ∈ [period_from, period_to]`
  - Sum `demurrage_usd`, count trips, compute `period_from`/`period_to` from actual dates in group
  - Claim No. = `"{deal_no}-DEM"`
- `upsert_claims(drafts)` — if claim exists in `Claims` sheet, update amount/trip count only if Status == "Draft". Never touch claims in Sent/Paid status.

### 3.5 `invoice_pdf.py`
Renders one PDF per claim using the existing Invoice + Annex template:
```python
def render_invoice_pdf(claim_no: str) -> Path:
    # 1. Open workbook with xlwings (visible=False)
    # 2. Set Invoice!B20 = claim_no   (this drives all the dynamic content)
    # 3. Force calc: app.calculate()
    # 4. ExportAsFixedFormat on sheets ["Invoice", "Annex"] → PDF
    # 5. Save as outputs/invoices/{claim_no}_{consignee_slug}_{date}.pdf
    # 6. Close without saving the workbook (we changed B20 only for render)
```
Returns the PDF path. Filename slug: `MOC-DEM-2026-187296_RubisEnergyZambia_2026-05-20.pdf`.

Fallback on non-Windows: open with LibreOffice headless, same approach. Note as a TODO if not implemented yet, but Windows path must work.

### 3.6 `outlook.py`
The heart of the email automation. **All drafts land in Outlook's Drafts folder. Never call `.Send()`.**

```python
@dataclass
class EmailDraft:
    to: list[str]
    cc: list[str]
    subject: str
    body_html: str
    attachments: list[Path]
    save_only: bool = True   # True = .Save() to Drafts. False = .Display() to pop window.

def create_outlook_draft(draft: EmailDraft) -> str:
    """Returns Outlook EntryID of the created draft."""
```

Implementation (Windows):
```python
import win32com.client
ol = win32com.client.Dispatch("Outlook.Application")
mail = ol.CreateItem(0)  # 0 = olMailItem
mail.To = "; ".join(draft.to)
mail.CC = "; ".join(draft.cc)
mail.Subject = draft.subject
mail.HTMLBody = draft.body_html
for att in draft.attachments:
    mail.Attachments.Add(str(att.resolve()))
if draft.save_only:
    mail.Save()        # appears in Drafts
else:
    mail.Display()     # opens the compose window
return mail.EntryID
```

Resolve recipients from `data/contacts.yaml`:
```yaml
Rubis Energy Zambia:
  primary: ["ap@rubisenergy.zm"]
  cc: ["ops.zambia@rubis.com"]
  greeting: "Dear Rubis team"
Lake Petroleum Zambia:
  primary: ["finance@lakepetroleum.zm"]
  cc: []
  greeting: "Dear Lake Petroleum team"
Reliance Energy Zambia:
  primary: ["[TBD]"]
  cc: []
  greeting: "Dear Reliance team"
```
Theo will fill `[TBD]` himself. If a recipient is `[TBD]`, **do not draft** — log a warning and skip that claim.

### 3.7 `dunning.py`
- `scan_overdue() -> list[OverdueClaim]` — reads Claims, filters `Status == "Sent" AND today > Due Date`
- For each, compute days overdue and pick template:
  - 0 ≤ days < 7  → `reminder_friendly.txt`
  - 7 ≤ days < 14 → `reminder_firm.txt`
  - days ≥ 14    → `reminder_final.txt` (auto-cc management address from `.env`)
- Build `EmailDraft`s with the original invoice PDF re-attached
- Save to Outlook Drafts
- Log each action to AuditLog

### 3.8 `dashboard.py`
Recomputes the Dashboard sheet cells that aren't live formulas (the "By Consignee" / "By Transporter" / "Top Deals" pivots). Sourced from `Trips Ledger`. Run after big imports. **Don't break the navigation row or KPI tiles** — only rewrite data ranges.

### 3.9 `audit.py`
`log(sheet, address, field, old, new, action)` — appends to AuditLog with `datetime.now()`, `os.getlogin()`. Same shape as VBA `LogAudit`.

---

## 4. Email templates (`data/templates/`)

Plain text with `{placeholders}`. Rendered with `str.format(**ctx)`. Context fields available: `greeting`, `claim_no`, `deal_no`, `consignee`, `period_from`, `period_to`, `num_trips`, `amount_usd`, `due_date`, `days_overdue`, `bank_block`, `signature`.

### `invoice_email.txt`
```
{greeting},

Please find attached our demurrage invoice {claim_no} covering deal {deal_no}.

  Period      : {period_from} → {period_to}
  Trips       : {num_trips}
  Amount due  : USD {amount_usd:,.2f}
  Due date    : {due_date}

Per-trip detail is in the annex. Payment instructions:

{bank_block}

Please confirm receipt and let me know if you have any questions.

Best regards,
{signature}
```

### `reminder_friendly.txt`
```
{greeting},

A gentle reminder that invoice {claim_no} for USD {amount_usd:,.2f} fell due on {due_date} ({days_overdue} days ago). Could you confirm payment status?

Invoice re-attached for convenience.

Best regards,
{signature}
```

### `reminder_firm.txt`
```
{greeting},

Invoice {claim_no} (USD {amount_usd:,.2f}) is now {days_overdue} days past due. Please advise expected payment date by return.

Re-attached.

Regards,
{signature}
```

### `reminder_final.txt`
```
{greeting},

Invoice {claim_no} for USD {amount_usd:,.2f} is now {days_overdue} days overdue. We need payment confirmation this week to avoid escalation to management.

Re-attached.

Regards,
{signature}
```

---

## 5. CLI — what Theo will actually run

Wire these in `pyproject.toml` `[project.scripts]`.

| Command | What it does |
|---|---|
| `demurrage-import path/to/trips.csv` | Append rows to Trips Ledger from a CSV (truck log export). Schema-validated. Refuses on duplicates (same truck + date + deal). |
| `demurrage-build-claims --from 2026-05-01 --to 2026-05-31` | Group trips into draft claims for the period. Writes new rows to Claims. Idempotent. |
| `demurrage-draft --claim 187296-DEM` or `--all-drafts` | For each Draft claim: generate PDF, create Outlook draft, optionally flip Claims status to "Drafted in Outlook". |
| `demurrage-dun [--dry-run]` | Scan overdue, create reminder drafts. `--dry-run` prints a table instead of touching Outlook. |
| `demurrage-refresh` | Recompute Dashboard. |
| `demurrage-reconcile` | Compare Python-computed demurrage vs sheet values; report mismatches. Catches manual edits. |

Every command:
- Logs to `outputs/logs/{YYYY-MM-DD}_{cmd}.log`
- Closes Excel/Outlook handles even on exception
- Returns non-zero exit on any error
- Has `--help`

---

## 6. Hard rules — do not violate

1. **Never auto-send email.** Drafts only. Theo clicks Send in Outlook.
2. **Never overwrite a Sent or Paid claim.** Updates only allowed on `Status == "Draft"`.
3. **Preserve VBA.** Always save with `keep_vba=True`. After every save, smoke-test by re-opening and checking `wb.vba_archive` is not None.
4. **No hardcoded paths.** Everything via `config.py` and `.env`.
5. **No silent failures.** If a counterparty has no email in contacts.yaml, log a warning and skip — don't draft to nobody.
6. **Idempotent.** Re-running any command on the same input must produce the same result, not duplicates.
7. **Currency is USD.** No FX conversion unless `Assumptions!FX rate` ≠ 1.
8. **Don't touch the Cover/Dashboard navigation rows** (row 2 in every sheet).

---

## 7. Build order (milestones)

Do these in sequence. Don't proceed to the next until the previous one is tested and I can run it.

1. **M1 — Scaffold:** folder structure, `pyproject.toml`, `config.py`, `workbook.py`, `audit.py`. Test: open workbook, read trips, count = 131, save, re-open in Excel, VBA still works.
2. **M2 — Calculations + reconcile:** `calculations.py`, `tests/test_calculations.py`, `demurrage-reconcile`. Must show zero mismatches against current sheet.
3. **M3 — Claim builder:** `claims.py`, `demurrage-build-claims`. Idempotency test included.
4. **M4 — Invoice PDF:** `invoice_pdf.py`, `demurrage-draft` (PDF only, no Outlook yet). Verify PDF matches what the VBA `PublishInvoicePDF` produces.
5. **M5 — Outlook drafts:** `outlook.py`, `contacts.yaml`, templates, full `demurrage-draft`. Hand-check one draft in Outlook.
6. **M6 — Dunning:** `dunning.py`, `demurrage-dun`, with `--dry-run`.
7. **M7 — Dashboard refresh + import:** `dashboard.py`, `import_trips.py`.
8. **M8 — README + polish:** quickstart in README, .env.example, `--help` everywhere.

At each milestone: commit, run tests, show me a 5-line summary of what changed.

---

## 8. Acceptance criteria

Done when:
- I can drop a CSV of new trips into the folder, run 3 commands, and end with PDF invoices in `outputs/invoices/` and matching drafts in my Outlook Drafts folder, addressed correctly, with the right attachment and a templated body.
- I can run `demurrage-dun` once a week and reminders for everything overdue appear in Drafts.
- Nothing breaks the existing xlsm. VBA macros still run from inside Excel.
- Re-running anything is safe (idempotent).
- A new counterparty is added by editing `contacts.yaml` and `Deals`, no code changes.

---

## 9. Questions to ask me before starting

Only these:
1. Confirm Outlook desktop (classic, not New Outlook) is the target. New Outlook breaks COM — if I'm on New Outlook, you'll generate `.msg` files instead.
2. Confirm AR contact emails for each consignee (or accept `[TBD]` placeholders for now).
3. Confirm management cc address for `reminder_final.txt`.

Everything else — infer from this brief or pick a sensible default and tell me what you picked.
