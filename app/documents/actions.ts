"use server";

import { getDb, nextDocNumber } from "@/lib/db";
import { Deal, dealMetrics, StorageAgreement } from "@/lib/calc";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

const s = (v: FormDataEntryValue | null) => { const t = (v ?? "").toString().trim(); return t || null; };
const n = (v: FormDataEntryValue | null, def: number | null = null) => {
  const t = (v ?? "").toString().trim();
  if (!t) return def;
  const x = Number(t);
  return isFinite(x) ? x : def;
};

export async function createPfiFromDeal(dealId: number, fd: FormData) {
  const db = getDb();
  const deal = db.prepare("SELECT * FROM deals WHERE id=?").get(dealId) as Deal | undefined;
  if (!deal) throw new Error("Deal not found");
  const bankId = n(fd.get("bank_id")) ?? (db.prepare("SELECT id FROM banks WHERE entity_id=? AND is_default=1").get(deal.entity_id) as any)?.id;
  if (!bankId) throw new Error("No bank account found for this entity");

  const qty = n(fd.get("qty_m3"), deal.qty_m3)!;
  const price = n(fd.get("price_usd_per_m3"), deal.price_usd_per_m3)!;
  const amount = Math.round(qty * price * 100) / 100;

  const docNo = nextDocNumber("PFI", deal.entity_id);
  const issueDate = s(fd.get("issue_date")) ?? new Date().toISOString().slice(0,10);

  const r = db.prepare(`INSERT INTO documents (doc_type, doc_no, deal_id, entity_id, counterparty_id, bank_id,
    issue_date, currency, qty_m3, price_usd_per_m3, amount_usd, payment_terms_text, notes, status)
    VALUES ('PFI',?,?,?,?,?,?,'USD',?,?,?,?,?, 'issued')`).run(
      docNo, dealId, deal.entity_id, deal.counterparty_id, bankId,
      issueDate, qty, price, amount,
      s(fd.get("payment_terms_text")) ?? deal.payment_term_text,
      s(fd.get("notes")),
    );
  revalidatePath("/documents"); revalidatePath(`/deals/${dealId}`);
  redirect(`/documents/${r.lastInsertRowid}`);
}

export async function createFinalInvoiceFromDeal(dealId: number, fd: FormData) {
  const db = getDb();
  const deal = db.prepare("SELECT * FROM deals WHERE id=?").get(dealId) as Deal | undefined;
  if (!deal) throw new Error("Deal not found");
  const loadings = db.prepare("SELECT * FROM deal_loadings WHERE deal_id=?").all(dealId) as any[];
  const payments = db.prepare("SELECT * FROM payments WHERE deal_id=?").all(dealId) as any[];
  const m = dealMetrics(deal, loadings, payments);

  const qty = n(fd.get("qty_m3"), m.loadedQtyM3 || deal.qty_m3)!;
  const price = n(fd.get("price_usd_per_m3"), deal.price_usd_per_m3)!;
  const amount = Math.round(qty * price * 100) / 100;
  const bankId = n(fd.get("bank_id")) ?? (db.prepare("SELECT id FROM banks WHERE entity_id=? AND is_default=1").get(deal.entity_id) as any)?.id;
  if (!bankId) throw new Error("No bank account found for this entity");

  const docNo = nextDocNumber("FINAL_INVOICE", deal.entity_id);
  const issueDate = s(fd.get("issue_date")) ?? new Date().toISOString().slice(0,10);
  const dueDate = s(fd.get("due_date"));

  const r = db.prepare(`INSERT INTO documents (doc_type, doc_no, deal_id, entity_id, counterparty_id, bank_id,
    issue_date, due_date, currency, qty_m3, price_usd_per_m3, amount_usd, payment_terms_text, notes, status)
    VALUES ('FINAL_INVOICE',?,?,?,?,?,?,?,'USD',?,?,?,?,?, 'issued')`).run(
      docNo, dealId, deal.entity_id, deal.counterparty_id, bankId,
      issueDate, dueDate, qty, price, amount,
      s(fd.get("payment_terms_text")) ?? deal.payment_term_text,
      s(fd.get("notes")),
    );
  revalidatePath("/documents"); revalidatePath(`/deals/${dealId}`);
  redirect(`/documents/${r.lastInsertRowid}`);
}

export async function createStorageInvoice(fd: FormData) {
  const db = getDb();
  const sa_id = n(fd.get("storage_agreement_id"));
  const sa = db.prepare("SELECT * FROM storage_agreements WHERE id=?").get(sa_id) as StorageAgreement | undefined;
  if (!sa || !sa.counterparty_id) throw new Error("Storage agreement or counterparty missing");
  const entityId = n(fd.get("entity_id"))!;
  const bankId = n(fd.get("bank_id")) ?? (db.prepare("SELECT id FROM banks WHERE entity_id=? AND is_default=1").get(entityId) as any)?.id;
  if (!bankId) throw new Error("No bank for entity");
  const qty = n(fd.get("qty_m3"), 0)!;
  const days = n(fd.get("days"), 30)!;
  const fee1 = sa.fee_first_30d_usd_per_m3 ?? 0;
  const fee2 = sa.fee_next_30d_usd_per_m3 ?? 0;
  const firstBlock = Math.min(30, days);
  const restDays = Math.max(0, days - 30);
  const restBlocks = Math.ceil(restDays / 30);
  const amount = Math.round((qty * fee1 * (firstBlock/30) + qty * fee2 * restBlocks) * 100) / 100;

  const docNo = nextDocNumber("STORAGE_INVOICE", entityId);
  const issueDate = s(fd.get("issue_date")) ?? new Date().toISOString().slice(0,10);
  const dueDate = s(fd.get("due_date"));

  const r = db.prepare(`INSERT INTO documents (doc_type, doc_no, storage_agreement_id, entity_id,
    counterparty_id, bank_id, issue_date, due_date, currency, qty_m3, amount_usd,
    period_from, period_to, payment_terms_text, notes, status)
    VALUES ('STORAGE_INVOICE',?,?,?,?,?,?,?,'USD',?,?,?,?,?,?, 'issued')`).run(
      docNo, sa.id, entityId, sa.counterparty_id, bankId, issueDate, dueDate,
      qty, amount,
      s(fd.get("period_from")), s(fd.get("period_to")),
      s(fd.get("payment_terms_text")) ?? `Storage for ${days} days at $${fee1}/m³ first 30d, $${fee2}/m³/30d thereafter`,
      s(fd.get("notes")),
    );
  revalidatePath("/documents");
  redirect(`/documents/${r.lastInsertRowid}`);
}

export async function updateDocument(id: number, fd: FormData) {
  const db = getDb();
  db.prepare(`UPDATE documents SET issue_date=?, due_date=?, qty_m3=?, price_usd_per_m3=?,
    amount_usd=?, payment_terms_text=?, notes=?, bank_id=?, status=?, paid_date=?, paid_amount_usd=?
    WHERE id=?`).run(
      s(fd.get("issue_date")), s(fd.get("due_date")),
      n(fd.get("qty_m3")), n(fd.get("price_usd_per_m3")),
      n(fd.get("amount_usd"), 0),
      s(fd.get("payment_terms_text")), s(fd.get("notes")),
      n(fd.get("bank_id")),
      s(fd.get("status")) ?? "draft",
      s(fd.get("paid_date")), n(fd.get("paid_amount_usd"), 0),
      id,
    );
  revalidatePath(`/documents/${id}`);
  revalidatePath("/documents");
}

export async function deleteDocument(id: number) {
  getDb().prepare("DELETE FROM documents WHERE id=?").run(id);
  revalidatePath("/documents");
  redirect("/documents");
}
