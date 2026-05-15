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

export async function saveLoss(id: number | null, fd: FormData) {
  const db = getDb();
  const args = [
    s(fd.get("loss_date")), n(fd.get("location_id")), n(fd.get("terminal_id")),
    s(fd.get("terminal_name")), n(fd.get("product_id")),
    n(fd.get("qty_m3"), 0), s(fd.get("reference")), s(fd.get("notes")),
  ];
  if (id) {
    db.prepare(`UPDATE mi_losses SET loss_date=?, location_id=?, terminal_id=?,
      terminal_name=?, product_id=?, qty_m3=?, reference=?, notes=? WHERE id=?`).run(...args, id);
  } else {
    db.prepare(`INSERT INTO mi_losses (loss_date, location_id, terminal_id,
      terminal_name, product_id, qty_m3, reference, notes) VALUES (?,?,?,?,?,?,?,?)`).run(...args);
  }
  revalidatePath("/losses");
  redirect("/losses");
}

export async function deleteLoss(id: number) {
  getDb().prepare("DELETE FROM mi_losses WHERE id=?").run(id);
  revalidatePath("/losses");
  redirect("/losses");
}
