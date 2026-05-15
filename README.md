# Trading Ops

Mid-office application for an oil trading desk selling gasoil and gasoline on
DDU / FCA / DAP basis. Replaces the BALANCE_OVERVIEW Excel workbook with a
single-source-of-truth web app.

## Modules

| Page | Purpose |
|---|---|
| **/** Dashboard | KPIs, counterparty exposure, position by location |
| **/deals** | All deals (purchases & sales) with loadings + payments sub-tables |
| **/trucking** | Open FCA/DDU deals: lifting status, days-to-lift, demurrage events |
| **/positions/counterparty** | Qty & USD balances, O/A in use, utilisation per counterparty |
| **/positions/location** | Purchased/sold/loaded/in-tank per location × product |
| **/positions/security** | SBLC / BG / parent guarantees with expiry alerts |
| **/positions/aging** | AR aging buckets (current / 0–30 / 31–60 / 61–90 / 90+) |
| **/documents** | PFIs, final invoices, storage invoices — auto-numbered, printable |
| **/swaps** | Vessel-level swaps with MTM and P&L |
| **/losses** | MI losses by location × terminal × product |
| **/noic** | NOIC summary: Msasa / Feruka routed deals + NOIC fees |
| **/master** | Entities, banks, counterparties, frame contracts, products, locations, storage agreements |

## Two ways to run it

### 1 — Get a public URL on your phone (Render, ~5 min, ~$8/mo)

1. Push this repo to GitHub if you haven't already.
2. Sign up at <https://render.com> (free account).
3. Click **New** → **Blueprint** → connect your GitHub repo.
4. Render reads `render.yaml` and offers to create:
   - a Web service (Starter plan, $7/mo)
   - a 1 GB persistent disk for the SQLite database ($1/mo)
5. Click **Apply**. Wait 3–5 minutes for the first build.
6. Open the URL Render gives you (something like `https://trading-ops-xyz.onrender.com`). Works on phone, anywhere.

To import your historical workbook on Render:
- Render Web Shell (in the dashboard) → upload the `.xlsm` file → run `python3 scripts/import_xlsm.py /tmp/workbook.xlsm`

### 2 — Quick public URL from your laptop (free, temporary)

If you don't want to deploy yet, use ngrok to expose `localhost:3000` to a public URL:

```bash
# Run the app locally first
npm install && npm run dev

# In a separate terminal, install ngrok (macOS):
brew install ngrok
# Or download from https://ngrok.com/download

# Then expose port 3000:
ngrok http 3000
```

ngrok prints a URL like `https://abc123.ngrok-free.app`. Open it on your phone. Free tier is fine for personal use; the URL stays alive only while ngrok is running on your laptop.

### 3 — Docker (no Node install required)

Install Docker Desktop from <https://www.docker.com/products/docker-desktop/>, then:

```bash
git clone <your repo>
cd <repo>
git checkout claude/oil-trading-demurrage-app-dk9Ev
docker compose up --build
```

First build takes 1–2 minutes. Open <http://localhost:3000>.

To stop: `Ctrl+C` in the terminal, or `docker compose down` from another shell.
The SQLite database lives in `./data/` and persists across restarts.

### 4 — Plain Node (fastest iteration)

Needs Node 20+ and Python 3 with `openpyxl` (only for the importer).

```bash
git clone <your repo>
cd <repo>
git checkout claude/oil-trading-demurrage-app-dk9Ev
npm install
npm run dev
```

Open <http://localhost:3000>. The DB is created in `./data/ops.db` on first request and seeded with a few demo records.

To make it reachable from your phone on the same WiFi: `npm run dev -- -H 0.0.0.0` then on your phone open `http://<laptop-IP>:3000`.

## Importing historical data

Once the app is running (Docker or Node), import deals from your existing
BALANCE_OVERVIEW workbook in one shot:

```bash
# Inside docker:
docker exec trading-ops python3 scripts/import_xlsm.py /path/inside/container/workbook.xlsm

# Locally:
pip install openpyxl
python3 scripts/import_xlsm.py /path/to/BALANCE_OVERVIEW.xlsm
```

The importer:
- Reads the **DEALS (MOCOH)**, **DEALS (MOCZAM)**, **BEIRA SWAPS** and **MI LOSSES** sheets
- Auto-creates counterparties, products, locations as needed
- Auto-extracts location from the incoterm string (`FCA BEIRA` → BEIRA)
- Normalises payment terms (`O/A 10D AFTER RELEASE` → code: OA, days: 10, trigger: RELEASE)
- Synthesises one loading + one payment per deal carrying the historical aggregate quantity and paid amount, so position rollups are correct from day 1
- Is **idempotent**: re-running skips already-imported deal numbers and swap numbers

Test result on the production workbook: 722 deals, 79 swaps, 27 MI losses imported, 0 errors.

## Demurrage rule

Per-loading, no pro-rata:

```
hours_at_site   = departure_time − arrival_time
excess_hours    = max(0, hours_at_site − laytime_hours)
demurrage_days  = ceil(excess_hours / 24)
demurrage_usd   = demurrage_days × demurrage_usd_per_day
```

Set `laytime_hours` + `demurrage_usd_per_day` on a loading and the system computes it automatically. The counterparty's frame-contract rate flows through as a default.

## Documents (PFI / Invoice)

1. Open a deal → **+ PFI** or **+ Final Invoice**
2. Pick a bank account (the entity's default is pre-selected; override per document if needed)
3. Click **Generate** → printable HTML document opens
4. Use the browser's **Print → Save as PDF** to produce the PDF

The PFI template matches the MOCOHSA layout: FROM / TO blocks, deal ref, qty at 20°C, incoterm, delivery range, price $/m³, amount, payment terms, full bank block (beneficiary, SWIFT, IBAN, correspondent + correspondent SWIFT), and the liberating-effect footer.

Document numbers are auto-assigned per entity per year:
`PFI-MOCOH-2026-0001`, `INV-MOCOH-2026-0001`, `SI-MOCOH-2026-0001`.

## Data model

Single source of truth:

```
deals (purchase or sale)
├── deal_loadings   (truck/vessel nominations & loadings against the deal)
├── payments        (cash flows in/out tied to the deal)
└── documents       (PFI / final invoice / storage invoice issued for the deal)

counterparties
├── frame_contracts (incoterm/payment permissions, default demurrage rate)
└── securities      (SBLC/BG/parent guarantee covering exposure)
```

All position views (By Counterparty, By Location, By Security, AR Aging) are **derived** from this — there are no duplicate per-location copies of the same data, which is the bug class that bedevils Excel.
