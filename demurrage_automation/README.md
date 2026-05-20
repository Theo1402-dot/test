# MOCOH Demurrage Automation

Python layer around `data/MOCOH_DEMURRAGE_2026.xlsm`. Trips → claims → invoice PDFs → Outlook drafts → dunning → KPI refresh. **Nothing is auto-sent — every email lands in Outlook Drafts.** See `PROJECT_BRIEF.md` for the full spec.

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # add ,windows on Windows for pywin32/xlwings
cp .env.example .env               # edit MANAGEMENT_CC, EMAIL_SIGNATURE if needed
pytest                             # smoke tests
```

## Daily flow (target state, M1–M8)

| Step | Command | Lands in |
|---|---|---|
| Import a new truck log CSV | `demurrage-import path/to/trips.csv` | Trips Ledger |
| Build claims for a period | `demurrage-build-claims --from 2026-05-01 --to 2026-05-31` | Claims sheet |
| Render PDFs + Outlook drafts | `demurrage-draft --all-drafts` | `outputs/invoices/`, Outlook Drafts |
| Friday dunning sweep | `demurrage-dun` (use `--dry-run` first) | Outlook Drafts |
| Refresh dashboard | `demurrage-refresh` | Dashboard sheet |
| Verify Python vs Excel | `demurrage-reconcile` | log + stdout |

## Hard rules

1. Never auto-send email — drafts only.
2. Never overwrite a Sent or Paid claim.
3. VBA project must survive every save (`keep_vba=True` + post-save verify).
4. All paths via `src/demurrage/config.py` + `.env`.
5. Idempotent: same input ⇒ same output.

## Layout

```
src/demurrage/    core modules
scripts/          CLI shims (also wired in pyproject.toml [project.scripts])
data/             xlsm + contacts.yaml + email templates
outputs/          PDFs, .eml fallbacks, run logs
tests/            pytest suite
```
