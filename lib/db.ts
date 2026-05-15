import Database from "better-sqlite3";
import path from "path";
import fs from "fs";

const DATA_DIR = path.join(process.cwd(), "data");
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
const dbPath = path.join(DATA_DIR, "ops.db");

declare global {
  // eslint-disable-next-line no-var
  var __db: Database.Database | undefined;
}

function init(db: Database.Database) {
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");

  db.exec(`
    -- Trading entities (MOCOH, MOCZAM, ...)
    CREATE TABLE IF NOT EXISTS entities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT NOT NULL UNIQUE,
      legal_name TEXT NOT NULL,
      address TEXT,
      tax_id TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    -- Bank accounts belonging to an entity
    CREATE TABLE IF NOT EXISTS banks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
      label TEXT NOT NULL,
      currency TEXT NOT NULL DEFAULT 'USD',
      beneficiary TEXT NOT NULL,
      bank_name TEXT NOT NULL,
      bank_address TEXT,
      swift TEXT,
      iban TEXT,
      account_no TEXT,
      correspondent_bank TEXT,
      correspondent_swift TEXT,
      is_default INTEGER NOT NULL DEFAULT 0,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_banks_entity ON banks(entity_id);

    -- Counterparties (clients & suppliers)
    CREATE TABLE IF NOT EXISTS counterparties (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      legal_name TEXT,
      country TEXT,
      address TEXT,
      contact_name TEXT,
      contact_email TEXT,
      contact_phone TEXT,
      allowed_oa_usd REAL NOT NULL DEFAULT 0,
      default_payment_term TEXT,
      default_demurrage_usd_per_day REAL NOT NULL DEFAULT 0,
      default_laytime_hours REAL NOT NULL DEFAULT 24,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    -- Frame contracts per counterparty: which incoterms / payment options agreed
    CREATE TABLE IF NOT EXISTS frame_contracts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      counterparty_id INTEGER NOT NULL REFERENCES counterparties(id) ON DELETE CASCADE,
      itt_deals INTEGER NOT NULL DEFAULT 0,
      fca_deals INTEGER NOT NULL DEFAULT 0,
      ddu_deals INTEGER NOT NULL DEFAULT 0,
      truck_dem_usd_per_day REAL,
      ppmt INTEGER NOT NULL DEFAULT 0,
      oa INTEGER NOT NULL DEFAULT 0,
      sblc INTEGER NOT NULL DEFAULT 0,
      date_signed TEXT,
      expiry_date TEXT,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_frame_counterparty ON frame_contracts(counterparty_id);

    -- Products
    CREATE TABLE IF NOT EXISTS products (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      density_kg_per_m3 REAL
    );

    -- Locations
    CREATE TABLE IF NOT EXISTS locations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL,
      country TEXT,
      type TEXT
    );

    -- Terminals at locations
    CREATE TABLE IF NOT EXISTS terminals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
      name TEXT NOT NULL,
      operator TEXT,
      capacity_m3 REAL,
      UNIQUE(location_id, name)
    );
    CREATE INDEX IF NOT EXISTS idx_terminals_location ON terminals(location_id);

    -- Storage agreements
    CREATE TABLE IF NOT EXISTS storage_agreements (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
      terminal_id INTEGER REFERENCES terminals(id) ON DELETE SET NULL,
      counterparty_id INTEGER REFERENCES counterparties(id) ON DELETE SET NULL,
      agreement_in_place INTEGER NOT NULL DEFAULT 0,
      kyc_clearance INTEGER NOT NULL DEFAULT 0,
      cend_in_place INTEGER NOT NULL DEFAULT 0,
      due_dil_done INTEGER NOT NULL DEFAULT 0,
      throughput_ago_pct REAL,
      throughput_pms_pct REAL,
      fee_first_30d_usd_per_m3 REAL,
      fee_next_30d_usd_per_m3 REAL,
      fh_parcels_usd_per_m3_per_mo REAL,
      agency_fee_usd_per_m3_per_mo REAL,
      contract_expiry TEXT,
      renewal TEXT,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_storage_location ON storage_agreements(location_id);

    -- Deals (purchases and sales)
    CREATE TABLE IF NOT EXISTS deals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      deal_no TEXT NOT NULL UNIQUE,
      entity_id INTEGER NOT NULL REFERENCES entities(id),
      counterparty_id INTEGER NOT NULL REFERENCES counterparties(id),
      type TEXT NOT NULL CHECK (type IN ('PURCH','SALE')),
      deal_date TEXT NOT NULL,
      product_id INTEGER NOT NULL REFERENCES products(id),
      incoterm TEXT NOT NULL,
      location_id INTEGER REFERENCES locations(id),
      beg_date TEXT,
      end_date TEXT,
      price_usd_per_m3 REAL NOT NULL,
      qty_m3 REAL NOT NULL,
      payment_term_text TEXT NOT NULL,
      payment_term_code TEXT,
      oa_days INTEGER,
      oa_trigger TEXT,
      status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('draft','open','closed','cancelled')),
      due_date TEXT,
      sblc_id INTEGER,
      comments TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_deals_entity ON deals(entity_id);
    CREATE INDEX IF NOT EXISTS idx_deals_party ON deals(counterparty_id);
    CREATE INDEX IF NOT EXISTS idx_deals_product ON deals(product_id);
    CREATE INDEX IF NOT EXISTS idx_deals_location ON deals(location_id);
    CREATE INDEX IF NOT EXISTS idx_deals_status ON deals(status);

    -- Loadings / nominations against a deal
    CREATE TABLE IF NOT EXISTS deal_loadings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
      nomination_date TEXT,
      loading_date TEXT,
      release_date TEXT,
      arrival_date TEXT,
      departure_date TEXT,
      qty_m3 REAL NOT NULL,
      truck_plate TEXT,
      vessel TEXT,
      terminal_id INTEGER REFERENCES terminals(id),
      destination TEXT,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_loadings_deal ON deal_loadings(deal_id);

    -- Payments (in/out) against deals
    CREATE TABLE IF NOT EXISTS payments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
      payment_date TEXT NOT NULL,
      amount_usd REAL NOT NULL,
      direction TEXT NOT NULL CHECK (direction IN ('IN','OUT')),
      reference TEXT,
      bank_id INTEGER REFERENCES banks(id),
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_payments_deal ON payments(deal_id);

    -- SBLCs / securities
    CREATE TABLE IF NOT EXISTS securities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      counterparty_id INTEGER NOT NULL REFERENCES counterparties(id) ON DELETE CASCADE,
      type TEXT NOT NULL,
      reference TEXT,
      amount_usd REAL NOT NULL,
      issue_date TEXT,
      expiry_date TEXT,
      lds_date TEXT,
      covering TEXT,
      notes TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_securities_counterparty ON securities(counterparty_id);

    -- Documents: PFIs (proforma) and Invoices (final / storage)
    CREATE TABLE IF NOT EXISTS documents (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      doc_type TEXT NOT NULL CHECK (doc_type IN ('PFI','FINAL_INVOICE','STORAGE_INVOICE')),
      doc_no TEXT NOT NULL,
      deal_id INTEGER REFERENCES deals(id) ON DELETE SET NULL,
      storage_agreement_id INTEGER REFERENCES storage_agreements(id) ON DELETE SET NULL,
      entity_id INTEGER NOT NULL REFERENCES entities(id),
      counterparty_id INTEGER NOT NULL REFERENCES counterparties(id),
      bank_id INTEGER REFERENCES banks(id),
      issue_date TEXT NOT NULL,
      due_date TEXT,
      currency TEXT NOT NULL DEFAULT 'USD',
      qty_m3 REAL,
      price_usd_per_m3 REAL,
      amount_usd REAL NOT NULL,
      period_from TEXT,
      period_to TEXT,
      payment_terms_text TEXT,
      notes TEXT,
      status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','issued','paid','cancelled')),
      paid_date TEXT,
      paid_amount_usd REAL NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(doc_type, doc_no)
    );
    CREATE INDEX IF NOT EXISTS idx_documents_deal ON documents(deal_id);
    CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type);

    -- Document numbering sequences
    CREATE TABLE IF NOT EXISTS doc_sequences (
      doc_type TEXT NOT NULL,
      entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
      year INTEGER NOT NULL,
      seq INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (doc_type, entity_id, year)
    );

    -- Swaps (e.g. Beira swaps between trading entities)
    CREATE TABLE IF NOT EXISTS swaps (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      swap_no TEXT,
      swap_date TEXT,
      entity_id INTEGER REFERENCES entities(id),
      counterparty_id INTEGER REFERENCES counterparties(id),
      location_id INTEGER REFERENCES locations(id),
      side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
      product_id INTEGER NOT NULL REFERENCES products(id),
      vessel TEXT,
      qty_m3 REAL NOT NULL,
      swap_price_usd_per_m3 REAL,
      mtm_price_usd_per_m3 REAL,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_swaps_counterparty ON swaps(counterparty_id);

    -- MI Losses (measured / inventory losses)
    CREATE TABLE IF NOT EXISTS mi_losses (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      loss_date TEXT,
      location_id INTEGER REFERENCES locations(id),
      terminal_id INTEGER REFERENCES terminals(id),
      terminal_name TEXT,
      product_id INTEGER REFERENCES products(id),
      qty_m3 REAL NOT NULL,
      reference TEXT,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_losses_location ON mi_losses(location_id);
  `);

  // Idempotent column additions for evolving schema. SQLite doesn't support
  // IF NOT EXISTS on columns, so we try and ignore duplicate-column errors.
  const tryAdd = (sql: string) => {
    try { db.exec(sql); } catch (e: any) {
      if (!String(e?.message ?? "").includes("duplicate column")) throw e;
    }
  };
  tryAdd(`ALTER TABLE deal_loadings ADD COLUMN laytime_hours REAL`);
  tryAdd(`ALTER TABLE deal_loadings ADD COLUMN demurrage_usd_per_day REAL`);
  tryAdd(`ALTER TABLE deal_loadings ADD COLUMN noic_route TEXT`);
  tryAdd(`ALTER TABLE deal_loadings ADD COLUMN noic_terminal TEXT`);
  tryAdd(`ALTER TABLE deal_loadings ADD COLUMN noic_fee_usd REAL`);
  tryAdd(`ALTER TABLE deal_loadings ADD COLUMN noic_paid_usd REAL`);

  if ((db.prepare("SELECT COUNT(*) c FROM entities").get() as any).c === 0) {
    seed(db);
  }
}

function seed(db: Database.Database) {
  // Entities
  const insEnt = db.prepare(`INSERT INTO entities (code, legal_name, address) VALUES (?,?,?)`);
  const mocoh = insEnt.run("MOCOH", "MOCOHSA", "Rue de la Corraterie 5-7, 1204 Geneva, Switzerland").lastInsertRowid as number;
  const moczam = insEnt.run("MOCZAM", "MOCZAM LTD", "Maputo, Mozambique").lastInsertRowid as number;

  // Banks
  const insBank = db.prepare(`
    INSERT INTO banks (entity_id, label, currency, beneficiary, bank_name, bank_address,
      swift, iban, account_no, correspondent_bank, correspondent_swift, is_default)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
  `);
  insBank.run(mocoh, "ING Geneva (USD)", "USD", "MOCOHSA",
    "ING BANK N.V., AMSTERDAM, LANCY/ GENEVA BRANCH", "Geneva, Switzerland",
    "BBRUCHGTXXX", "CH64 0838 70000 0107152 1", null,
    "JP MORGAN CHASE NY", "CHASUS33XXX", 1);
  insBank.run(moczam, "Default USD", "USD", "MOCZAM LTD", "TBD", "Maputo, Mozambique",
    null, null, null, null, null, 1);

  // Products
  const insP = db.prepare(`INSERT INTO products (code, name, density_kg_per_m3) VALUES (?,?,?)`);
  insP.run("AGO", "Automotive Gasoil", 845);
  insP.run("PMS", "Premium Motor Spirit (Gasoline)", 745);
  insP.run("JET", "Jet A-1", 800);
  insP.run("COND", "Condensate", 720);
  insP.run("VLSFO", "Very Low Sulphur Fuel Oil", 980);

  // Locations
  const insL = db.prepare(`INSERT INTO locations (code, name, country, type) VALUES (?,?,?,?)`);
  const locs: [string,string,string,string][] = [
    ["BEIRA","Beira","Mozambique","port"],
    ["MAPUTO","Maputo","Mozambique","port"],
    ["MATOLA","Matola","Mozambique","port"],
    ["MSASA","Msasa (Harare)","Zimbabwe","inland"],
    ["FERUKA","Feruka","Zimbabwe","inland"],
    ["DES","DES","Mozambique","port"],
    ["LUSAKA","Lusaka","Zambia","inland"],
    ["MTWARA","Mtwara","Tanzania","port"],
    ["TANGA","Tanga","Tanzania","port"],
    ["DAR","Dar es Salaam","Tanzania","port"],
    ["GABORONE","Gaborone","Botswana","inland"],
    ["LUBUMBASHI","Lubumbashi","DRC","inland"],
    ["MBAVUKU","Mbavuku","Zimbabwe","inland"],
    ["WB","Walvis Bay","Namibia","port"],
  ];
  for (const l of locs) insL.run(...l);

  // Counterparties (a few real ones from the workbook so it feels live)
  const insC = db.prepare(`
    INSERT INTO counterparties (name, country, address, contact_email, allowed_oa_usd, default_payment_term)
    VALUES (?,?,?,?,?,?)
  `);
  const etg = insC.run("ETG COMMODITIES LTD", "Mauritius", "3rd Floor, Rogers House, Port Louis, Mauritius",
    "ops@etgcommodities.com", 500000, "O/A 10D AFTER RELEASE").lastInsertRowid as number;
  const ipg = insC.run("IPG", "Switzerland", null, null, 0, "PPMT").lastInsertRowid as number;
  const vit = insC.run("VITOL", "Switzerland", null, null, 0, "PPMT").lastInsertRowid as number;
  const rel = insC.run("RELIANCE", "India", null, null, 0, "PPMT").lastInsertRowid as number;
  insC.run("PYGMA", null, null, null, 200000, "O/A 30D");
  insC.run("MONALUXE", null, null, null, 300000, "O/A 30D");
  insC.run("REAL DRIVE PETROLEUM", null, null, null, 0, "PPMT");

  // A few demo deals
  const insD = db.prepare(`
    INSERT INTO deals (deal_no, entity_id, counterparty_id, type, deal_date, product_id,
      incoterm, location_id, beg_date, end_date, price_usd_per_m3, qty_m3,
      payment_term_text, payment_term_code, oa_days, oa_trigger, status, comments)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
  `);
  const pAgo = (db.prepare("SELECT id FROM products WHERE code='AGO'").get() as any).id;
  const pPms = (db.prepare("SELECT id FROM products WHERE code='PMS'").get() as any).id;
  const lBeira = (db.prepare("SELECT id FROM locations WHERE code='BEIRA'").get() as any).id;
  const lMaputo = (db.prepare("SELECT id FROM locations WHERE code='MAPUTO'").get() as any).id;

  insD.run("190496", mocoh, etg, "SALE", "2026-04-10", pPms, "FCA BEIRA", lBeira,
    "2026-04-10", "2026-04-30", 920, 300,
    "O/A 10D after release. Release = actual or 30/4, whichever earlier. Over limit → PPMT.",
    "OA", 10, "RELEASE", "open", "Sample deal matching uploaded PFI");
  insD.run("159932", mocoh, ipg, "PURCH", "2024-09-06", pAgo, "FCA BEIRA", lBeira,
    "2024-09-06", "2024-09-30", 635, 515,
    "Prepayment", "PPMT", null, null, "closed", "Closed deal");
  insD.run("160187", mocoh, rel, "SALE", "2024-09-06", pAgo, "FCA BEIRA", lBeira,
    "2024-09-09", "2024-09-30", 629, 394.974,
    "Prepayment", "PPMT", null, null, "closed", "Closed deal");
  insD.run("160417", mocoh, vit, "PURCH", "2024-09-13", pAgo, "FCA BEIRA", lBeira,
    "2024-09-17", "2024-10-17", 616, 200,
    "Prepayment", "PPMT", null, null, "closed", "Closed deal");

  // Loadings & payments on the open ETG deal
  const dealEtg = (db.prepare("SELECT id FROM deals WHERE deal_no=?").get("190496") as any).id;
  db.prepare(`INSERT INTO deal_loadings (deal_id, loading_date, qty_m3, truck_plate, destination) VALUES (?,?,?,?,?)`)
    .run(dealEtg, "2026-04-12", 90, "MZ-123-AB", "FCA Beira");
  db.prepare(`INSERT INTO deal_loadings (deal_id, loading_date, qty_m3, truck_plate, destination) VALUES (?,?,?,?,?)`)
    .run(dealEtg, "2026-04-15", 120, "MZ-456-CD", "FCA Beira");
  db.prepare(`INSERT INTO payments (deal_id, payment_date, amount_usd, direction, reference) VALUES (?,?,?,?,?)`)
    .run(dealEtg, "2026-04-20", 100000, "IN", "First partial payment");
}

export function getDb(): Database.Database {
  if (!global.__db) {
    const db = new Database(dbPath);
    init(db);
    global.__db = db;
  }
  return global.__db;
}

export function nextDocNumber(docType: string, entityId: number) {
  const db = getDb();
  const year = new Date().getFullYear();
  const row = db.prepare(
    "SELECT seq FROM doc_sequences WHERE doc_type=? AND entity_id=? AND year=?"
  ).get(docType, entityId, year) as { seq: number } | undefined;
  const seq = (row?.seq ?? 0) + 1;
  if (row) {
    db.prepare("UPDATE doc_sequences SET seq=? WHERE doc_type=? AND entity_id=? AND year=?")
      .run(seq, docType, entityId, year);
  } else {
    db.prepare("INSERT INTO doc_sequences (doc_type, entity_id, year, seq) VALUES (?,?,?,?)")
      .run(docType, entityId, year, seq);
  }
  const ent = db.prepare("SELECT code FROM entities WHERE id=?").get(entityId) as { code: string };
  const prefix = docType === "PFI" ? "PFI" : docType === "STORAGE_INVOICE" ? "SI" : "INV";
  return `${prefix}-${ent.code}-${year}-${String(seq).padStart(4,"0")}`;
}
