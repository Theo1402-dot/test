#!/usr/bin/env python3
"""
One-shot bulk import of historical deals from the BALANCE_OVERVIEW xlsm into
the application's SQLite DB.

Usage:
  python3 scripts/import_xlsm.py <path-to.xlsm>

Reads:
  - 'DEALS (MOCOH)' and 'DEALS (MOCZAM)' sheets
Writes to data/ops.db:
  - counterparties  (created on the fly if missing)
  - deals           (one row per worksheet row)
  - deal_loadings   (one synthesised loading per deal carrying LOADED/NOM qty)
  - payments        (one synthesised payment carrying PAID amount)

Idempotent: deals are keyed by (deal_no, entity_id); re-running skips
already-imported deals. New counterparties get default O/A = 0; you can
tune via Master Data afterwards.

Run the app at least once before importing (so the schema & entities exist).
"""

import sqlite3
import sys
import warnings
import os
from datetime import datetime, date

warnings.filterwarnings("ignore")

import openpyxl  # type: ignore

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ops.db")

ENTITY_SHEET_MAP = {
    "MOCOH":  "DEALS (MOCOH)",
    "MOCZAM": "DEALS (MOCZAM)",
}

# Column indices (1-based) in DEALS sheets based on header inspection
COL_DEAL_NO      = 1
COL_COUNTERPARTY = 2
COL_TYPE         = 3   # PURCH / SALE
COL_DEAL_DATE    = 4
COL_PRODUCT      = 5
COL_DELIVERY     = 6   # incoterm
COL_BEG_DATE     = 7
COL_END_DATE     = 8
COL_PRICE        = 9
COL_QTY          = 10
COL_AMOUNT       = 11  # formula, ignore
COL_PMT_TERM     = 12
COL_PAID         = 13
COL_LOADED       = 15  # LOADED/NOM QTY
COL_FUNDS_BAL    = 17
COL_DUE_DATE     = 19
COL_COMMENTS     = 21


def to_iso(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    if not s:
        return None
    # Try a couple of formats
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def to_num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_payment_term(text):
    """Returns (code, oa_days, trigger)"""
    if not text:
        return (None, None, None)
    u = str(text).upper()
    if "PPMT" in u and "O/A" not in u:
        return ("PPMT", None, None)
    if "SBLC" in u:
        return ("SBLC", None, None)
    if "NET OFF" in u:
        return ("NET_OFF", None, None)
    if "DOC LC" in u or "L/C" in u or u.strip() == "LC":
        return ("LC", None, None)
    if "O/A" in u:
        days = None
        import re
        m = re.search(r"(\d{1,3})\s*D", u)
        if m:
            days = int(m.group(1))
        trig = None
        for kw in ("RELEASE", "LOADING", "DELIVERY", "INVOICE", "DISCHARGE", "ARRIVAL", "OFFLOADING", "NOR"):
            if kw in u:
                trig = kw
                break
        return ("OA", days, trig)
    return (None, None, None)


def location_id_from_incoterm(cur, incoterm):
    if not incoterm:
        return None
    u = str(incoterm).upper()
    cur.execute("SELECT id, code FROM locations")
    locs = cur.fetchall()
    locs.sort(key=lambda x: -len(x[1]))  # longest first
    for lid, code in locs:
        if code in u:
            return lid
    return None


def get_or_create_counterparty(cur, name):
    if not name:
        return None
    name = str(name).strip()
    cur.execute("SELECT id FROM counterparties WHERE UPPER(name) = UPPER(?)", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("""INSERT INTO counterparties (name, allowed_oa_usd, default_demurrage_usd_per_day, default_laytime_hours)
                   VALUES (?, 0, 0, 24)""", (name,))
    return cur.lastrowid


def get_or_create_product(cur, code):
    if not code:
        return None
    code = str(code).strip().upper()
    if not code:
        return None
    cur.execute("SELECT id FROM products WHERE code = ?", (code,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO products (code, name) VALUES (?, ?)", (code, code))
    return cur.lastrowid


def import_swaps(cur, wb):
    if "BEIRA SWAPS" not in wb.sheetnames:
        return 0
    ws = wb["BEIRA SWAPS"]
    cur.execute("SELECT id, code FROM products")
    prod_by_code = {c: i for i, c in cur.fetchall()}
    cur.execute("SELECT id FROM locations WHERE code='BEIRA'")
    beira_id = (cur.fetchone() or [None])[0]
    n = 0
    for r in range(2, ws.max_row + 1):
        deal_no = ws.cell(row=r, column=1).value
        if not deal_no:
            continue
        cp_name = ws.cell(row=r, column=2).value
        side_raw = (ws.cell(row=r, column=3).value or "").strip().upper()
        side = "BUY" if side_raw in ("BUY", "PURCH", "PURCHASE") else "SELL"
        prod_code = (ws.cell(row=r, column=4).value or "").strip().upper()
        vessel = ws.cell(row=r, column=5).value
        qty = to_num(ws.cell(row=r, column=6).value) or 0
        swap_px = to_num(ws.cell(row=r, column=7).value)
        mtm_px = to_num(ws.cell(row=r, column=8).value)
        cp_id = get_or_create_counterparty(cur, cp_name) if cp_name else None
        prod_id = prod_by_code.get(prod_code)
        if not prod_id and prod_code:
            prod_id = get_or_create_product(cur, prod_code)
            prod_by_code[prod_code] = prod_id
        if not prod_id:
            continue
        # Idempotent on swap_no
        cur.execute("SELECT id FROM swaps WHERE swap_no=?", (str(deal_no),))
        if cur.fetchone():
            continue
        cur.execute("""INSERT INTO swaps (swap_no, location_id, counterparty_id, side, product_id,
                       vessel, qty_m3, swap_price_usd_per_m3, mtm_price_usd_per_m3)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (str(deal_no), beira_id, cp_id, side, prod_id,
                     str(vessel) if vessel else None, abs(qty), swap_px, mtm_px))
        n += 1
    return n


def import_mi_losses(cur, wb):
    if "MI LOSSES" not in wb.sheetnames:
        return 0
    ws = wb["MI LOSSES"]
    cur.execute("SELECT id, code FROM locations")
    loc_by_code = {c: i for i, c in cur.fetchall()}
    cur.execute("SELECT id, code FROM products")
    prod_by_code = {c: i for i, c in cur.fetchall()}
    n = 0
    # Data starts at row 7 in the inspected workbook
    for r in range(7, ws.max_row + 1):
        loc = ws.cell(row=r, column=2).value
        terminal = ws.cell(row=r, column=3).value
        prod = ws.cell(row=r, column=4).value
        qty = to_num(ws.cell(row=r, column=5).value)
        if not loc or qty is None:
            continue
        loc_code = str(loc).upper().strip()
        loc_id = loc_by_code.get(loc_code)
        prod_code = str(prod).upper().strip() if prod else None
        prod_id = prod_by_code.get(prod_code) if prod_code else None
        if not prod_id and prod_code:
            prod_id = get_or_create_product(cur, prod_code)
            prod_by_code[prod_code] = prod_id
        cur.execute("""INSERT INTO mi_losses (location_id, terminal_name, product_id, qty_m3, notes)
                       VALUES (?,?,?,?,?)""",
                    (loc_id, str(terminal) if terminal else None, prod_id, qty, "Imported from MI LOSSES sheet"))
        n += 1
    return n


SCHEMA = r"""
CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
  legal_name TEXT NOT NULL, address TEXT, tax_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS banks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id INTEGER NOT NULL REFERENCES entities(id),
  label TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
  beneficiary TEXT NOT NULL, bank_name TEXT NOT NULL, bank_address TEXT,
  swift TEXT, iban TEXT, account_no TEXT,
  correspondent_bank TEXT, correspondent_swift TEXT,
  is_default INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS counterparties (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
  legal_name TEXT, country TEXT, address TEXT,
  contact_name TEXT, contact_email TEXT, contact_phone TEXT,
  allowed_oa_usd REAL NOT NULL DEFAULT 0, default_payment_term TEXT,
  default_demurrage_usd_per_day REAL NOT NULL DEFAULT 0,
  default_laytime_hours REAL NOT NULL DEFAULT 24, notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS frame_contracts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  counterparty_id INTEGER NOT NULL REFERENCES counterparties(id) ON DELETE CASCADE,
  itt_deals INTEGER NOT NULL DEFAULT 0, fca_deals INTEGER NOT NULL DEFAULT 0,
  ddu_deals INTEGER NOT NULL DEFAULT 0, truck_dem_usd_per_day REAL,
  ppmt INTEGER NOT NULL DEFAULT 0, oa INTEGER NOT NULL DEFAULT 0,
  sblc INTEGER NOT NULL DEFAULT 0, date_signed TEXT, expiry_date TEXT, notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL, density_kg_per_m3 REAL);
CREATE TABLE IF NOT EXISTS locations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL, country TEXT, type TEXT);
CREATE TABLE IF NOT EXISTS terminals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
  name TEXT NOT NULL, operator TEXT, capacity_m3 REAL, UNIQUE(location_id, name));
CREATE TABLE IF NOT EXISTS storage_agreements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
  terminal_id INTEGER, counterparty_id INTEGER,
  agreement_in_place INTEGER NOT NULL DEFAULT 0, kyc_clearance INTEGER NOT NULL DEFAULT 0,
  cend_in_place INTEGER NOT NULL DEFAULT 0, due_dil_done INTEGER NOT NULL DEFAULT 0,
  throughput_ago_pct REAL, throughput_pms_pct REAL,
  fee_first_30d_usd_per_m3 REAL, fee_next_30d_usd_per_m3 REAL,
  fh_parcels_usd_per_m3_per_mo REAL, agency_fee_usd_per_m3_per_mo REAL,
  contract_expiry TEXT, renewal TEXT, notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS deals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, deal_no TEXT NOT NULL UNIQUE,
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  counterparty_id INTEGER NOT NULL REFERENCES counterparties(id),
  type TEXT NOT NULL CHECK (type IN ('PURCH','SALE')),
  deal_date TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id),
  incoterm TEXT NOT NULL, location_id INTEGER REFERENCES locations(id),
  beg_date TEXT, end_date TEXT,
  price_usd_per_m3 REAL NOT NULL, qty_m3 REAL NOT NULL,
  payment_term_text TEXT NOT NULL, payment_term_code TEXT,
  oa_days INTEGER, oa_trigger TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('draft','open','closed','cancelled')),
  due_date TEXT, sblc_id INTEGER, comments TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS deal_loadings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
  nomination_date TEXT, loading_date TEXT, release_date TEXT,
  arrival_date TEXT, departure_date TEXT,
  qty_m3 REAL NOT NULL, truck_plate TEXT, vessel TEXT,
  terminal_id INTEGER, destination TEXT, notes TEXT,
  laytime_hours REAL, demurrage_usd_per_day REAL,
  noic_route TEXT, noic_terminal TEXT,
  noic_fee_usd REAL, noic_paid_usd REAL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
  payment_date TEXT NOT NULL, amount_usd REAL NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('IN','OUT')),
  reference TEXT, bank_id INTEGER, notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS securities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  counterparty_id INTEGER NOT NULL REFERENCES counterparties(id) ON DELETE CASCADE,
  type TEXT NOT NULL, reference TEXT, amount_usd REAL NOT NULL,
  issue_date TEXT, expiry_date TEXT, lds_date TEXT, covering TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_type TEXT NOT NULL CHECK (doc_type IN ('PFI','FINAL_INVOICE','STORAGE_INVOICE')),
  doc_no TEXT NOT NULL, deal_id INTEGER, storage_agreement_id INTEGER,
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  counterparty_id INTEGER NOT NULL REFERENCES counterparties(id),
  bank_id INTEGER, issue_date TEXT NOT NULL, due_date TEXT,
  currency TEXT NOT NULL DEFAULT 'USD',
  qty_m3 REAL, price_usd_per_m3 REAL, amount_usd REAL NOT NULL,
  period_from TEXT, period_to TEXT, payment_terms_text TEXT, notes TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','paid','cancelled')),
  paid_date TEXT, paid_amount_usd REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(doc_type, doc_no));
CREATE TABLE IF NOT EXISTS doc_sequences (
  doc_type TEXT NOT NULL, entity_id INTEGER NOT NULL,
  year INTEGER NOT NULL, seq INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (doc_type, entity_id, year));
CREATE TABLE IF NOT EXISTS swaps (
  id INTEGER PRIMARY KEY AUTOINCREMENT, swap_no TEXT, swap_date TEXT,
  entity_id INTEGER, counterparty_id INTEGER, location_id INTEGER,
  side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
  product_id INTEGER NOT NULL REFERENCES products(id),
  vessel TEXT, qty_m3 REAL NOT NULL,
  swap_price_usd_per_m3 REAL, mtm_price_usd_per_m3 REAL, notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS mi_losses (
  id INTEGER PRIMARY KEY AUTOINCREMENT, loss_date TEXT,
  location_id INTEGER, terminal_id INTEGER, terminal_name TEXT,
  product_id INTEGER, qty_m3 REAL NOT NULL, reference TEXT, notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""

def ensure_schema(conn):
    """Match db.ts so import can run before the Next.js app has booted."""
    conn.executescript(SCHEMA)
    # Idempotent column additions
    for sql in (
        "ALTER TABLE deal_loadings ADD COLUMN laytime_hours REAL",
        "ALTER TABLE deal_loadings ADD COLUMN demurrage_usd_per_day REAL",
        "ALTER TABLE deal_loadings ADD COLUMN noic_route TEXT",
        "ALTER TABLE deal_loadings ADD COLUMN noic_terminal TEXT",
        "ALTER TABLE deal_loadings ADD COLUMN noic_fee_usd REAL",
        "ALTER TABLE deal_loadings ADD COLUMN noic_paid_usd REAL",
    ):
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e):
                raise
    conn.commit()


def main(xlsm_path):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    cur = conn.cursor()

    # Bootstrap entities (idempotent)
    for code, legal_name, addr in [
        ("MOCOH", "MOCOHSA", "Rue de la Corraterie 5-7, 1204 Geneva, Switzerland"),
        ("MOCZAM", "MOCZAM LTD", "Maputo, Mozambique"),
    ]:
        cur.execute("INSERT OR IGNORE INTO entities (code, legal_name, address) VALUES (?,?,?)", (code, legal_name, addr))
    cur.execute("SELECT id, code FROM entities")
    entity_ids = {code: eid for eid, code in cur.fetchall()}

    # Bootstrap locations from the incoterms we expect
    for code, name, country, type_ in [
        ("BEIRA","Beira","Mozambique","port"), ("MAPUTO","Maputo","Mozambique","port"),
        ("MATOLA","Matola","Mozambique","port"), ("MSASA","Msasa (Harare)","Zimbabwe","inland"),
        ("FERUKA","Feruka","Zimbabwe","inland"), ("DES","DES","Mozambique","port"),
        ("LUSAKA","Lusaka","Zambia","inland"), ("MTWARA","Mtwara","Tanzania","port"),
        ("TANGA","Tanga","Tanzania","port"), ("DAR","Dar es Salaam","Tanzania","port"),
        ("GABORONE","Gaborone","Botswana","inland"), ("LUBUMBASHI","Lubumbashi","DRC","inland"),
        ("MBAVUKU","Mbavuku","Zimbabwe","inland"), ("WB","Walvis Bay","Namibia","port"),
    ]:
        cur.execute("INSERT OR IGNORE INTO locations (code, name, country, type) VALUES (?,?,?,?)",
                    (code, name, country, type_))

    # Bootstrap products
    for code, name, density in [
        ("AGO","Automotive Gasoil",845), ("PMS","Premium Motor Spirit (Gasoline)",745),
        ("JET","Jet A-1",800), ("COND","Condensate",720), ("VLSFO","Very Low Sulphur Fuel Oil",980),
    ]:
        cur.execute("INSERT OR IGNORE INTO products (code, name, density_kg_per_m3) VALUES (?,?,?)",
                    (code, name, density))

    # Bootstrap default bank per entity (so PFIs can be generated)
    for code, beneficiary, bank, swift, iban, corr, corr_swift in [
        ("MOCOH", "MOCOHSA", "ING BANK N.V., AMSTERDAM, LANCY/ GENEVA BRANCH",
         "BBRUCHGTXXX", "CH64 0838 70000 0107152 1", "JP MORGAN CHASE NY", "CHASUS33XXX"),
        ("MOCZAM", "MOCZAM LTD", "TBD", None, None, None, None),
    ]:
        ent_id = entity_ids.get(code)
        if not ent_id:
            continue
        # Only insert if no banks for this entity yet
        cur.execute("SELECT COUNT(*) FROM banks WHERE entity_id=?", (ent_id,))
        if cur.fetchone()[0] == 0:
            cur.execute("""INSERT INTO banks (entity_id, label, currency, beneficiary, bank_name,
                bank_address, swift, iban, correspondent_bank, correspondent_swift, is_default)
                VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
                (ent_id, f"{code} Default (USD)", "USD", beneficiary, bank, None,
                 swift, iban, corr, corr_swift))

    print(f"Loading workbook {xlsm_path}…")
    wb = openpyxl.load_workbook(xlsm_path, data_only=True)

    stats = {"inserted": 0, "skipped_existing": 0, "skipped_empty": 0, "errors": 0, "loadings": 0, "payments": 0}

    for entity_code, sheet_name in ENTITY_SHEET_MAP.items():
        if sheet_name not in wb.sheetnames:
            print(f"  ! Sheet {sheet_name} not in workbook, skipping")
            continue
        ws = wb[sheet_name]
        entity_id = entity_ids[entity_code]
        print(f"  → {sheet_name} ({ws.max_row - 1} rows)")

        for r in range(2, ws.max_row + 1):
            deal_no = ws.cell(row=r, column=COL_DEAL_NO).value
            if deal_no is None or str(deal_no).strip() == "":
                stats["skipped_empty"] += 1
                continue
            deal_no = str(deal_no).strip()

            try:
                # Check if already imported
                cur.execute("SELECT id FROM deals WHERE deal_no = ?", (deal_no,))
                if cur.fetchone():
                    stats["skipped_existing"] += 1
                    continue

                cp_name = ws.cell(row=r, column=COL_COUNTERPARTY).value
                cp_id = get_or_create_counterparty(cur, cp_name)
                if not cp_id:
                    print(f"    ! row {r} skipped (no counterparty)")
                    stats["skipped_empty"] += 1
                    continue

                deal_type = (ws.cell(row=r, column=COL_TYPE).value or "").upper().strip()
                if deal_type not in ("PURCH", "SALE"):
                    print(f"    ! row {r} skipped (type='{deal_type}')")
                    stats["errors"] += 1
                    continue

                deal_date = to_iso(ws.cell(row=r, column=COL_DEAL_DATE).value)
                if not deal_date:
                    print(f"    ! row {r} skipped (no deal date)")
                    stats["errors"] += 1
                    continue

                product_code = (ws.cell(row=r, column=COL_PRODUCT).value or "").strip()
                product_id = get_or_create_product(cur, product_code)
                if not product_id:
                    print(f"    ! row {r} skipped (no product)")
                    stats["errors"] += 1
                    continue

                incoterm = (ws.cell(row=r, column=COL_DELIVERY).value or "").strip()
                location_id = location_id_from_incoterm(cur, incoterm)

                price = to_num(ws.cell(row=r, column=COL_PRICE).value) or 0
                qty = to_num(ws.cell(row=r, column=COL_QTY).value) or 0
                if price == 0 or qty == 0:
                    # still import — but flag as draft
                    pass

                pmt_text = ws.cell(row=r, column=COL_PMT_TERM).value or ""
                pmt_text = str(pmt_text).strip()
                code, days, trigger = parse_payment_term(pmt_text)

                comments = ws.cell(row=r, column=COL_COMMENTS).value
                comments = str(comments).strip() if comments else None

                # Determine status:
                # - "Closed deal" in comments → closed
                # - else → open
                status = "open"
                if comments and "closed" in comments.lower():
                    status = "closed"

                due_date = to_iso(ws.cell(row=r, column=COL_DUE_DATE).value)
                beg_date = to_iso(ws.cell(row=r, column=COL_BEG_DATE).value)
                end_date = to_iso(ws.cell(row=r, column=COL_END_DATE).value)

                cur.execute("""
                    INSERT INTO deals (deal_no, entity_id, counterparty_id, type, deal_date,
                        product_id, incoterm, location_id, beg_date, end_date,
                        price_usd_per_m3, qty_m3, payment_term_text, payment_term_code,
                        oa_days, oa_trigger, status, due_date, comments)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (deal_no, entity_id, cp_id, deal_type, deal_date,
                      product_id, incoterm or "N/A", location_id, beg_date, end_date,
                      price, qty, pmt_text or "N/A", code, days, trigger, status, due_date, comments))
                deal_id = cur.lastrowid
                stats["inserted"] += 1

                # Synthetic loading carrying historical loaded qty
                loaded = to_num(ws.cell(row=r, column=COL_LOADED).value)
                if loaded and loaded > 0:
                    cur.execute("""INSERT INTO deal_loadings (deal_id, loading_date, qty_m3, notes)
                                   VALUES (?,?,?,?)""",
                                (deal_id, beg_date or deal_date, loaded, "Imported aggregate (historical)"))
                    stats["loadings"] += 1

                # Synthetic payment carrying historical paid amount
                paid = to_num(ws.cell(row=r, column=COL_PAID).value)
                if paid and paid != 0:
                    direction = "IN" if (deal_type == "SALE" and paid > 0) or (deal_type == "PURCH" and paid < 0) else "OUT"
                    # For PURCH we typically *pay* the supplier → OUT
                    if deal_type == "PURCH":
                        direction = "OUT"
                    else:
                        direction = "IN"
                    cur.execute("""INSERT INTO payments (deal_id, payment_date, amount_usd, direction, reference, notes)
                                   VALUES (?,?,?,?,?,?)""",
                                (deal_id, deal_date, abs(paid), direction, "Imported aggregate", "Historical balance carry-over"))
                    stats["payments"] += 1

            except Exception as e:
                stats["errors"] += 1
                print(f"    ! row {r} ({deal_no}): {e}")

    # Swaps + MI losses
    swap_n = import_swaps(cur, wb)
    losses_n = import_mi_losses(cur, wb)
    stats["swaps"] = swap_n
    stats["mi_losses"] = losses_n

    conn.commit()
    conn.close()
    print("\nDone.")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/import_xlsm.py <path-to.xlsm>")
        sys.exit(1)
    main(sys.argv[1])
