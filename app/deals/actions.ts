"use server";

import { getDb } from "@/lib/db";
import { parsePaymentTerm } from "@/lib/calc";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

const s = (v: FormDataEntryValue | null) => { const t = (v ?? "").toString().trim(); return t || null; };
const n = (v: FormDataEntryValue | null, def: number | null = null) => {
  const t = (v ?? "").toString().trim();
  if (!t) return def;
  const x = Number(t);
  return isFinite(x) ? x : def;
};

// Auto-extract location_id from incoterm string ("FCA BEIRA" -> BEIRA)
function locationFromIncoterm(incoterm: string | null): number | null {
  if (!incoterm) return null;
  const db = getDb();
  // Find any known location code mentioned in the incoterm
  const locs = db.prepare("SELECT id, code FROM locations").all() as { id: number; code: string }[];
  const u = incoterm.toUpperCase();
  // Try longest match first
  const sorted = locs.slice().sort((a, b) => b.code.length - a.code.length);
  for (const l of sorted) {
    if (u.includes(l.code)) return l.id;
  }
  return null;
}

export async function saveDeal(id: number | null, fd: FormData) {
  const db = getDb();
  const incoterm = s(fd.get("incoterm"));
  const location_id = n(fd.get("location_id")) ?? locationFromIncoterm(incoterm);
  const payment_term_text = s(fd.get("payment_term_text")) ?? "";
  const parsed = parsePaymentTerm(payment_term_text);

  const args = [
    s(fd.get("deal_no")), n(fd.get("entity_id")), n(fd.get("counterparty_id")),
    s(fd.get("type")), s(fd.get("deal_date")), n(fd.get("product_id")),
    incoterm, location_id,
    s(fd.get("beg_date")), s(fd.get("end_date")),
    n(fd.get("price_usd_per_m3"), 0), n(fd.get("qty_m3"), 0),
    payment_term_text,
    s(fd.get("payment_term_code")) ?? parsed.code,
    n(fd.get("oa_days")) ?? parsed.oaDays,
    s(fd.get("oa_trigger")) ?? parsed.trigger,
    s(fd.get("status")) ?? "open",
    s(fd.get("due_date")),
    s(fd.get("comments")),
  ];

  if (id) {
    db.prepare(`UPDATE deals SET deal_no=?, entity_id=?, counterparty_id=?, type=?, deal_date=?,
      product_id=?, incoterm=?, location_id=?, beg_date=?, end_date=?,
      price_usd_per_m3=?, qty_m3=?, payment_term_text=?, payment_term_code=?,
      oa_days=?, oa_trigger=?, status=?, due_date=?, comments=?, updated_at=CURRENT_TIMESTAMP
      WHERE id=?`).run(...args, id);
  } else {
    const r = db.prepare(`INSERT INTO deals (deal_no, entity_id, counterparty_id, type, deal_date,
      product_id, incoterm, location_id, beg_date, end_date, price_usd_per_m3, qty_m3,
      payment_term_text, payment_term_code, oa_days, oa_trigger, status, due_date, comments)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(...args);
    id = r.lastInsertRowid as number;
  }
  revalidatePath("/deals");
  revalidatePath(`/deals/${id}`);
  revalidatePath("/");
  redirect(`/deals/${id}`);
}

export async function deleteDeal(id: number) {
  getDb().prepare("DELETE FROM deals WHERE id=?").run(id);
  revalidatePath("/deals"); revalidatePath("/"); redirect("/deals");
}

export async function addLoading(dealId: number, fd: FormData) {
  const db = getDb();
  db.prepare(`INSERT INTO deal_loadings (deal_id, nomination_date, loading_date, release_date,
    arrival_date, departure_date, qty_m3, truck_plate, vessel, terminal_id, destination, notes,
    laytime_hours, demurrage_usd_per_day, noic_route, noic_terminal, noic_fee_usd, noic_paid_usd)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(
      dealId,
      s(fd.get("nomination_date")), s(fd.get("loading_date")), s(fd.get("release_date")),
      s(fd.get("arrival_date")), s(fd.get("departure_date")),
      n(fd.get("qty_m3"), 0),
      s(fd.get("truck_plate")), s(fd.get("vessel")),
      n(fd.get("terminal_id")), s(fd.get("destination")), s(fd.get("notes")),
      n(fd.get("laytime_hours")), n(fd.get("demurrage_usd_per_day")),
      s(fd.get("noic_route")), s(fd.get("noic_terminal")),
      n(fd.get("noic_fee_usd")), n(fd.get("noic_paid_usd")),
    );
  revalidatePath(`/deals/${dealId}`);
}

export async function deleteLoading(dealId: number, loadingId: number) {
  getDb().prepare("DELETE FROM deal_loadings WHERE id=?").run(loadingId);
  revalidatePath(`/deals/${dealId}`);
}

export async function addPayment(dealId: number, fd: FormData) {
  const db = getDb();
  db.prepare(`INSERT INTO payments (deal_id, payment_date, amount_usd, direction, reference, bank_id, notes)
    VALUES (?,?,?,?,?,?,?)`).run(
      dealId,
      s(fd.get("payment_date")),
      n(fd.get("amount_usd"), 0),
      s(fd.get("direction")) ?? "IN",
      s(fd.get("reference")),
      n(fd.get("bank_id")),
      s(fd.get("notes")),
    );
  revalidatePath(`/deals/${dealId}`);
}

export async function deletePayment(dealId: number, paymentId: number) {
  getDb().prepare("DELETE FROM payments WHERE id=?").run(paymentId);
  revalidatePath(`/deals/${dealId}`);
}

export async function setDealStatus(dealId: number, status: "draft" | "open" | "closed" | "cancelled") {
  getDb().prepare("UPDATE deals SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?").run(status, dealId);
  revalidatePath(`/deals/${dealId}`);
  revalidatePath("/deals");
}
