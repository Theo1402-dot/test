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
    CREATE TABLE IF NOT EXISTS clients (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      country TEXT,
      contact TEXT,
      credit_limit_usd REAL NOT NULL DEFAULT 0,
      default_laytime_hours REAL NOT NULL DEFAULT 24,
      default_demurrage_usd_per_day REAL NOT NULL DEFAULT 250,
      payment_terms_days INTEGER NOT NULL DEFAULT 30,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS deliveries (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
      reference TEXT,
      product TEXT NOT NULL CHECK (product IN ('gasoil','gasoline')),
      volume_m3 REAL NOT NULL,
      price_per_m3_usd REAL NOT NULL,
      destination TEXT,
      truck_plate TEXT,
      loading_date TEXT,
      arrival_date TEXT,
      departure_date TEXT,
      laytime_hours REAL NOT NULL,
      demurrage_usd_per_day REAL NOT NULL,
      status TEXT NOT NULL DEFAULT 'in_transit'
        CHECK (status IN ('in_transit','delivered','invoiced','paid','cancelled')),
      invoice_date TEXT,
      due_date TEXT,
      paid_date TEXT,
      paid_amount_usd REAL NOT NULL DEFAULT 0,
      demurrage_billed INTEGER NOT NULL DEFAULT 0,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_deliveries_client ON deliveries(client_id);
    CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status);
  `);

  const count = db.prepare("SELECT COUNT(*) AS c FROM clients").get() as { c: number };
  if (count.c === 0) seed(db);
}

function seed(db: Database.Database) {
  const insertClient = db.prepare(`
    INSERT INTO clients (name, country, contact, credit_limit_usd,
      default_laytime_hours, default_demurrage_usd_per_day, payment_terms_days)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `);
  const c1 = insertClient.run("Atlas Fuels SARL", "Morocco", "ops@atlasfuels.ma", 500000, 24, 300, 30).lastInsertRowid;
  const c2 = insertClient.run("Sahara Petroleum", "Senegal", "trading@sahara-petro.sn", 250000, 36, 250, 45).lastInsertRowid;
  const c3 = insertClient.run("Nordic Bunkers AS", "Norway", "buy@nordicbunkers.no", 750000, 24, 400, 30).lastInsertRowid;

  const insertDel = db.prepare(`
    INSERT INTO deliveries (client_id, reference, product, volume_m3, price_per_m3_usd,
      destination, truck_plate, loading_date, arrival_date, departure_date,
      laytime_hours, demurrage_usd_per_day, status, invoice_date, due_date, paid_amount_usd, demurrage_billed)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  // Past invoiced delivery, partially paid, with demurrage incurred
  insertDel.run(c1, "ATL-2026-014", "gasoil", 33, 820, "Casablanca depot", "AB-1234-MA",
    "2026-04-10 08:00", "2026-04-11 06:00", "2026-04-12 14:00",
    24, 300, "invoiced", "2026-04-12", "2026-05-12", 0, 0);

  // Older overdue invoice
  insertDel.run(c2, "SAH-2026-021", "gasoline", 30, 880, "Dakar terminal", "DK-2210",
    "2026-03-01 09:00", "2026-03-04 11:00", "2026-03-04 20:00",
    36, 250, "invoiced", "2026-03-05", "2026-04-19", 12000, 0);

  // In transit
  insertDel.run(c3, "NOR-2026-105", "gasoil", 36, 790, "Oslo depot", "NO-44-991",
    "2026-05-13 06:00", null, null,
    24, 400, "in_transit", null, null, 0, 0);

  // Delivered awaiting invoice
  insertDel.run(c1, "ATL-2026-015", "gasoline", 32, 900, "Tangier", "AB-2299-MA",
    "2026-05-08 07:00", "2026-05-09 08:00", "2026-05-09 13:00",
    24, 300, "delivered", null, null, 0, 0);

  // Paid in full
  insertDel.run(c3, "NOR-2026-100", "gasoil", 36, 780, "Bergen", "NO-44-880",
    "2026-04-20 06:00", "2026-04-22 07:00", "2026-04-22 12:00",
    24, 400, "paid", "2026-04-22", "2026-05-22", 28080, 0);
}

export function getDb(): Database.Database {
  if (!global.__db) {
    const db = new Database(dbPath);
    init(db);
    global.__db = db;
  }
  return global.__db;
}
