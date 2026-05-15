"use server";

import { getDb } from "@/lib/db";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

function s(v: FormDataEntryValue | null) {
  const t = (v ?? "").toString().trim();
  return t === "" ? null : t;
}
function n(v: FormDataEntryValue | null) {
  const t = (v ?? "").toString().trim();
  if (t === "") return null;
  const x = Number(t);
  return isFinite(x) ? x : null;
}

export async function createDelivery(formData: FormData) {
  const db = getDb();
  const clientId = Number(formData.get("client_id"));
  const client = db.prepare("SELECT * FROM clients WHERE id = ?").get(clientId) as any;
  if (!client) throw new Error("Client not found");

  const laytime = n(formData.get("laytime_hours")) ?? client.default_laytime_hours;
  const rate = n(formData.get("demurrage_usd_per_day")) ?? client.default_demurrage_usd_per_day;

  const result = db.prepare(`
    INSERT INTO deliveries (client_id, reference, product, volume_m3, price_per_m3_usd,
      destination, truck_plate, loading_date, arrival_date, departure_date,
      laytime_hours, demurrage_usd_per_day, status, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    clientId,
    s(formData.get("reference")),
    s(formData.get("product")) ?? "gasoil",
    n(formData.get("volume_m3")) ?? 0,
    n(formData.get("price_per_m3_usd")) ?? 0,
    s(formData.get("destination")),
    s(formData.get("truck_plate")),
    s(formData.get("loading_date")),
    s(formData.get("arrival_date")),
    s(formData.get("departure_date")),
    laytime,
    rate,
    s(formData.get("status")) ?? "in_transit",
    s(formData.get("notes")),
  );

  revalidatePath("/deliveries");
  revalidatePath("/");
  redirect(`/deliveries/${result.lastInsertRowid}`);
}

export async function updateDelivery(id: number, formData: FormData) {
  const db = getDb();
  db.prepare(`
    UPDATE deliveries SET
      reference = ?, product = ?, volume_m3 = ?, price_per_m3_usd = ?,
      destination = ?, truck_plate = ?, loading_date = ?, arrival_date = ?,
      departure_date = ?, laytime_hours = ?, demurrage_usd_per_day = ?,
      status = ?, invoice_date = ?, due_date = ?, paid_date = ?,
      paid_amount_usd = ?, demurrage_billed = ?, notes = ?
    WHERE id = ?
  `).run(
    s(formData.get("reference")),
    s(formData.get("product")),
    n(formData.get("volume_m3")) ?? 0,
    n(formData.get("price_per_m3_usd")) ?? 0,
    s(formData.get("destination")),
    s(formData.get("truck_plate")),
    s(formData.get("loading_date")),
    s(formData.get("arrival_date")),
    s(formData.get("departure_date")),
    n(formData.get("laytime_hours")) ?? 24,
    n(formData.get("demurrage_usd_per_day")) ?? 0,
    s(formData.get("status")) ?? "in_transit",
    s(formData.get("invoice_date")),
    s(formData.get("due_date")),
    s(formData.get("paid_date")),
    n(formData.get("paid_amount_usd")) ?? 0,
    formData.get("demurrage_billed") ? 1 : 0,
    s(formData.get("notes")),
    id,
  );
  revalidatePath("/deliveries");
  revalidatePath(`/deliveries/${id}`);
  revalidatePath("/");
}

export async function deleteDelivery(id: number) {
  const db = getDb();
  db.prepare("DELETE FROM deliveries WHERE id = ?").run(id);
  revalidatePath("/deliveries");
  revalidatePath("/");
  redirect("/deliveries");
}

export async function markInvoiced(id: number) {
  const db = getDb();
  const today = new Date().toISOString().slice(0, 10);
  const row = db.prepare("SELECT d.*, c.payment_terms_days FROM deliveries d JOIN clients c ON c.id = d.client_id WHERE d.id = ?").get(id) as any;
  const due = new Date(); due.setDate(due.getDate() + (row?.payment_terms_days ?? 30));
  db.prepare("UPDATE deliveries SET status = 'invoiced', invoice_date = ?, due_date = ? WHERE id = ?")
    .run(today, due.toISOString().slice(0, 10), id);
  revalidatePath("/deliveries");
  revalidatePath(`/deliveries/${id}`);
  revalidatePath("/");
}
