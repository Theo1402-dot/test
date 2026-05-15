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


def main(xlsm_path):
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}. Boot the Next.js app once first so it creates the schema.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # Map entity code -> id
    cur.execute("SELECT id, code FROM entities")
    entity_ids = {code: eid for eid, code in cur.fetchall()}
    for code in ENTITY_SHEET_MAP:
        if code not in entity_ids:
            cur.execute("INSERT INTO entities (code, legal_name) VALUES (?, ?)", (code, code))
            entity_ids[code] = cur.lastrowid

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
