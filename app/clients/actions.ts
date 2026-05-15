"use server";

import { getDb } from "@/lib/db";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

function s(v: FormDataEntryValue | null) {
  const t = (v ?? "").toString().trim();
  return t === "" ? null : t;
}
function n(v: FormDataEntryValue | null, def = 0) {
  const t = (v ?? "").toString().trim();
  if (t === "") return def;
  const x = Number(t);
  return isFinite(x) ? x : def;
}

export async function createClient(formData: FormData) {
  const db = getDb();
  const name = s(formData.get("name"));
  if (!name) throw new Error("Name required");
  const r = db.prepare(`
    INSERT INTO clients (name, country, contact, credit_limit_usd,
      default_laytime_hours, default_demurrage_usd_per_day, payment_terms_days)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(
    name,
    s(formData.get("country")),
    s(formData.get("contact")),
    n(formData.get("credit_limit_usd")),
    n(formData.get("default_laytime_hours"), 24),
    n(formData.get("default_demurrage_usd_per_day"), 250),
    Math.trunc(n(formData.get("payment_terms_days"), 30)),
  );
  revalidatePath("/clients");
  revalidatePath("/");
  redirect(`/clients/${r.lastInsertRowid}`);
}

export async function updateClient(id: number, formData: FormData) {
  const db = getDb();
  db.prepare(`
    UPDATE clients SET name = ?, country = ?, contact = ?,
      credit_limit_usd = ?, default_laytime_hours = ?,
      default_demurrage_usd_per_day = ?, payment_terms_days = ?
    WHERE id = ?
  `).run(
    s(formData.get("name")),
    s(formData.get("country")),
    s(formData.get("contact")),
    n(formData.get("credit_limit_usd")),
    n(formData.get("default_laytime_hours"), 24),
    n(formData.get("default_demurrage_usd_per_day"), 250),
    Math.trunc(n(formData.get("payment_terms_days"), 30)),
    id,
  );
  revalidatePath("/clients");
  revalidatePath(`/clients/${id}`);
  revalidatePath("/");
}

export async function deleteClient(id: number) {
  const db = getDb();
  db.prepare("DELETE FROM clients WHERE id = ?").run(id);
  revalidatePath("/clients");
  revalidatePath("/");
  redirect("/clients");
}
