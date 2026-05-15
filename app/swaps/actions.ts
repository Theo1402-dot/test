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

export async function saveSwap(id: number | null, fd: FormData) {
  const db = getDb();
  const args = [
    s(fd.get("swap_no")), s(fd.get("swap_date")),
    n(fd.get("entity_id")), n(fd.get("counterparty_id")), n(fd.get("location_id")),
    s(fd.get("side")) ?? "BUY", n(fd.get("product_id")),
    s(fd.get("vessel")), n(fd.get("qty_m3"), 0),
    n(fd.get("swap_price_usd_per_m3")), n(fd.get("mtm_price_usd_per_m3")),
    s(fd.get("notes")),
  ];
  if (id) {
    db.prepare(`UPDATE swaps SET swap_no=?, swap_date=?, entity_id=?, counterparty_id=?, location_id=?,
      side=?, product_id=?, vessel=?, qty_m3=?, swap_price_usd_per_m3=?, mtm_price_usd_per_m3=?, notes=?
      WHERE id=?`).run(...args, id);
  } else {
    db.prepare(`INSERT INTO swaps (swap_no, swap_date, entity_id, counterparty_id, location_id,
      side, product_id, vessel, qty_m3, swap_price_usd_per_m3, mtm_price_usd_per_m3, notes)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).run(...args);
  }
  revalidatePath("/swaps");
  redirect("/swaps");
}

export async function deleteSwap(id: number) {
  getDb().prepare("DELETE FROM swaps WHERE id=?").run(id);
  revalidatePath("/swaps");
  redirect("/swaps");
}
