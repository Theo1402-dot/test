// One-off: create a sample PFI + Final Invoice + Storage Invoice from seed data
// so the preview PDF shows all document layouts populated.
import Database from "better-sqlite3";
import path from "path";

const db = new Database(path.join(process.cwd(), "data", "ops.db"));

const deal = db.prepare("SELECT * FROM deals WHERE deal_no='190496'").get();
if (!deal) { console.error("Seed deal 190496 missing"); process.exit(1); }
const bank = db.prepare("SELECT id FROM banks WHERE entity_id=? AND is_default=1").get(deal.entity_id);

function next(type, entId) {
  const y = new Date().getFullYear();
  const row = db.prepare("SELECT seq FROM doc_sequences WHERE doc_type=? AND entity_id=? AND year=?").get(type, entId, y);
  const seq = (row?.seq ?? 0) + 1;
  if (row) db.prepare("UPDATE doc_sequences SET seq=? WHERE doc_type=? AND entity_id=? AND year=?").run(seq, type, entId, y);
  else db.prepare("INSERT INTO doc_sequences VALUES (?,?,?,?)").run(type, entId, y, seq);
  const ent = db.prepare("SELECT code FROM entities WHERE id=?").get(entId);
  const prefix = type === "PFI" ? "PFI" : type === "STORAGE_INVOICE" ? "SI" : "INV";
  return `${prefix}-${ent.code}-${y}-${String(seq).padStart(4,"0")}`;
}

const pfiNo = next("PFI", deal.entity_id);
db.prepare(`INSERT INTO documents (doc_type, doc_no, deal_id, entity_id, counterparty_id, bank_id,
  issue_date, currency, qty_m3, price_usd_per_m3, amount_usd, payment_terms_text, status)
  VALUES ('PFI',?,?,?,?,?, ?, 'USD', ?, ?, ?, ?, 'issued')`).run(
    pfiNo, deal.id, deal.entity_id, deal.counterparty_id, bank.id,
    "2026-04-10", 300, 920, 276000,
    "OPEN ACCOUNT PAYABLE 10 DAYS FROM RELEASE DATE. RELEASE DATE TO BE CONSIDERED ACTUAL RELEASE DATE OR THE 30TH OF APRIL, WHICHEVER IS THE EARLIEST. SHALL THE OPEN ACCOUNT EXCEED THE GRANTED LIMIT; PREPAYMENT WILL BE REQUIRED.",
  );

const invNo = next("FINAL_INVOICE", deal.entity_id);
db.prepare(`INSERT INTO documents (doc_type, doc_no, deal_id, entity_id, counterparty_id, bank_id,
  issue_date, due_date, currency, qty_m3, price_usd_per_m3, amount_usd, payment_terms_text, status)
  VALUES ('FINAL_INVOICE',?,?,?,?,?, ?, ?, 'USD', ?, ?, ?, ?, 'issued')`).run(
    invNo, deal.id, deal.entity_id, deal.counterparty_id, bank.id,
    "2026-04-30", "2026-05-10", 210, 920, 193200,
    "Payment within 10 days from release date. Bank charges outside Switzerland for buyer's account.",
  );

console.log("Generated", pfiNo, "and", invNo);
