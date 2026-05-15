"use server";

import { getDb } from "@/lib/db";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

const s = (v: FormDataEntryValue | null) => { const t = (v ?? "").toString().trim(); return t || null; };
const n = (v: FormDataEntryValue | null, def: number | null = null) => {
  const t = (v ?? "").toString().trim();
  if (!t) return def;
  const x = Number(t);
  return isFinite(x) ? x : def;
};

export async function saveSecurity(id: number | null, fd: FormData) {
  const db = getDb();
  const args = [
    n(fd.get("counterparty_id")), s(fd.get("type")) ?? "SBLC",
    s(fd.get("reference")), n(fd.get("amount_usd"), 0),
    s(fd.get("issue_date")), s(fd.get("expiry_date")),
    s(fd.get("lds_date")), s(fd.get("covering")), s(fd.get("notes")),
  ];
  if (id) {
    db.prepare(`UPDATE securities SET counterparty_id=?, type=?, reference=?, amount_usd=?,
      issue_date=?, expiry_date=?, lds_date=?, covering=?, notes=? WHERE id=?`).run(...args, id);
  } else {
    db.prepare(`INSERT INTO securities (counterparty_id, type, reference, amount_usd,
      issue_date, expiry_date, lds_date, covering, notes)
      VALUES (?,?,?,?,?,?,?,?,?)`).run(...args);
  }
  revalidatePath("/positions/security");
  redirect("/positions/security");
}

export async function deleteSecurity(id: number) {
  getDb().prepare("DELETE FROM securities WHERE id=?").run(id);
  revalidatePath("/positions/security");
  redirect("/positions/security");
}
