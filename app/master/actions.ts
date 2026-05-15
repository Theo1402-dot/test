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
const b = (v: FormDataEntryValue | null) => (v ? 1 : 0);

// -------- Entities --------
export async function saveEntity(id: number | null, fd: FormData) {
  const db = getDb();
  if (id) {
    db.prepare("UPDATE entities SET code=?, legal_name=?, address=?, tax_id=? WHERE id=?")
      .run(s(fd.get("code")), s(fd.get("legal_name")), s(fd.get("address")), s(fd.get("tax_id")), id);
  } else {
    db.prepare("INSERT INTO entities (code, legal_name, address, tax_id) VALUES (?,?,?,?)")
      .run(s(fd.get("code")), s(fd.get("legal_name")), s(fd.get("address")), s(fd.get("tax_id")));
  }
  revalidatePath("/master/entities"); redirect("/master/entities");
}
export async function deleteEntity(id: number) {
  getDb().prepare("DELETE FROM entities WHERE id=?").run(id);
  revalidatePath("/master/entities"); redirect("/master/entities");
}

// -------- Banks --------
export async function saveBank(id: number | null, fd: FormData) {
  const db = getDb();
  const args = [
    n(fd.get("entity_id")), s(fd.get("label")), s(fd.get("currency")) ?? "USD",
    s(fd.get("beneficiary")), s(fd.get("bank_name")), s(fd.get("bank_address")),
    s(fd.get("swift")), s(fd.get("iban")), s(fd.get("account_no")),
    s(fd.get("correspondent_bank")), s(fd.get("correspondent_swift")),
    b(fd.get("is_default")), b(fd.get("active")),
  ];
  if (id) {
    db.prepare(`UPDATE banks SET entity_id=?, label=?, currency=?, beneficiary=?,
      bank_name=?, bank_address=?, swift=?, iban=?, account_no=?,
      correspondent_bank=?, correspondent_swift=?, is_default=?, active=? WHERE id=?`).run(...args, id);
  } else {
    db.prepare(`INSERT INTO banks (entity_id, label, currency, beneficiary, bank_name, bank_address,
      swift, iban, account_no, correspondent_bank, correspondent_swift, is_default, active)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(...args);
  }
  // If is_default checked, clear other defaults for same entity
  if (fd.get("is_default")) {
    const entId = n(fd.get("entity_id"));
    db.prepare("UPDATE banks SET is_default=0 WHERE entity_id=? AND id<>?").run(entId, id ?? -1);
  }
  revalidatePath("/master/banks"); redirect("/master/banks");
}
export async function deleteBank(id: number) {
  getDb().prepare("DELETE FROM banks WHERE id=?").run(id);
  revalidatePath("/master/banks"); redirect("/master/banks");
}

// -------- Counterparties --------
export async function saveCounterparty(id: number | null, fd: FormData) {
  const db = getDb();
  const args = [
    s(fd.get("name")), s(fd.get("legal_name")), s(fd.get("country")), s(fd.get("address")),
    s(fd.get("contact_name")), s(fd.get("contact_email")), s(fd.get("contact_phone")),
    n(fd.get("allowed_oa_usd"), 0), s(fd.get("default_payment_term")),
    n(fd.get("default_demurrage_usd_per_day"), 0), n(fd.get("default_laytime_hours"), 24),
    s(fd.get("notes")),
  ];
  if (id) {
    db.prepare(`UPDATE counterparties SET name=?, legal_name=?, country=?, address=?,
      contact_name=?, contact_email=?, contact_phone=?, allowed_oa_usd=?, default_payment_term=?,
      default_demurrage_usd_per_day=?, default_laytime_hours=?, notes=? WHERE id=?`).run(...args, id);
  } else {
    const r = db.prepare(`INSERT INTO counterparties (name, legal_name, country, address,
      contact_name, contact_email, contact_phone, allowed_oa_usd, default_payment_term,
      default_demurrage_usd_per_day, default_laytime_hours, notes)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)`).run(...args);
    id = r.lastInsertRowid as number;
  }
  revalidatePath("/master/counterparties"); redirect(`/master/counterparties/${id}`);
}
export async function deleteCounterparty(id: number) {
  getDb().prepare("DELETE FROM counterparties WHERE id=?").run(id);
  revalidatePath("/master/counterparties"); redirect("/master/counterparties");
}

// -------- Frame contract --------
export async function saveFrameContract(counterpartyId: number, fd: FormData) {
  const db = getDb();
  const existing = db.prepare("SELECT id FROM frame_contracts WHERE counterparty_id=?").get(counterpartyId) as any;
  const args = [
    b(fd.get("itt_deals")), b(fd.get("fca_deals")), b(fd.get("ddu_deals")),
    n(fd.get("truck_dem_usd_per_day")),
    b(fd.get("ppmt")), b(fd.get("oa")), b(fd.get("sblc")),
    s(fd.get("date_signed")), s(fd.get("expiry_date")), s(fd.get("notes")),
  ];
  if (existing) {
    db.prepare(`UPDATE frame_contracts SET itt_deals=?, fca_deals=?, ddu_deals=?,
      truck_dem_usd_per_day=?, ppmt=?, oa=?, sblc=?, date_signed=?, expiry_date=?, notes=?
      WHERE counterparty_id=?`).run(...args, counterpartyId);
  } else {
    db.prepare(`INSERT INTO frame_contracts (counterparty_id, itt_deals, fca_deals, ddu_deals,
      truck_dem_usd_per_day, ppmt, oa, sblc, date_signed, expiry_date, notes)
      VALUES (?,?,?,?,?,?,?,?,?,?,?)`).run(counterpartyId, ...args);
  }
  revalidatePath(`/master/counterparties/${counterpartyId}`);
}

// -------- Products --------
export async function saveProduct(id: number | null, fd: FormData) {
  const db = getDb();
  if (id) {
    db.prepare("UPDATE products SET code=?, name=?, density_kg_per_m3=? WHERE id=?")
      .run(s(fd.get("code")), s(fd.get("name")), n(fd.get("density_kg_per_m3")), id);
  } else {
    db.prepare("INSERT INTO products (code, name, density_kg_per_m3) VALUES (?,?,?)")
      .run(s(fd.get("code")), s(fd.get("name")), n(fd.get("density_kg_per_m3")));
  }
  revalidatePath("/master/products"); redirect("/master/products");
}
export async function deleteProduct(id: number) {
  getDb().prepare("DELETE FROM products WHERE id=?").run(id);
  revalidatePath("/master/products"); redirect("/master/products");
}

// -------- Locations --------
export async function saveLocation(id: number | null, fd: FormData) {
  const db = getDb();
  const args = [s(fd.get("code")), s(fd.get("name")), s(fd.get("country")), s(fd.get("type"))];
  if (id) {
    db.prepare("UPDATE locations SET code=?, name=?, country=?, type=? WHERE id=?").run(...args, id);
  } else {
    db.prepare("INSERT INTO locations (code, name, country, type) VALUES (?,?,?,?)").run(...args);
  }
  revalidatePath("/master/locations"); redirect("/master/locations");
}
export async function deleteLocation(id: number) {
  getDb().prepare("DELETE FROM locations WHERE id=?").run(id);
  revalidatePath("/master/locations"); redirect("/master/locations");
}

// -------- Storage agreements --------
export async function saveStorageAgreement(id: number | null, fd: FormData) {
  const db = getDb();
  const args = [
    n(fd.get("location_id")), n(fd.get("terminal_id")), n(fd.get("counterparty_id")),
    b(fd.get("agreement_in_place")), b(fd.get("kyc_clearance")), b(fd.get("cend_in_place")), b(fd.get("due_dil_done")),
    n(fd.get("throughput_ago_pct")), n(fd.get("throughput_pms_pct")),
    n(fd.get("fee_first_30d_usd_per_m3")), n(fd.get("fee_next_30d_usd_per_m3")),
    n(fd.get("fh_parcels_usd_per_m3_per_mo")), n(fd.get("agency_fee_usd_per_m3_per_mo")),
    s(fd.get("contract_expiry")), s(fd.get("renewal")), s(fd.get("notes")),
  ];
  if (id) {
    db.prepare(`UPDATE storage_agreements SET location_id=?, terminal_id=?, counterparty_id=?,
      agreement_in_place=?, kyc_clearance=?, cend_in_place=?, due_dil_done=?,
      throughput_ago_pct=?, throughput_pms_pct=?, fee_first_30d_usd_per_m3=?, fee_next_30d_usd_per_m3=?,
      fh_parcels_usd_per_m3_per_mo=?, agency_fee_usd_per_m3_per_mo=?,
      contract_expiry=?, renewal=?, notes=? WHERE id=?`).run(...args, id);
  } else {
    db.prepare(`INSERT INTO storage_agreements (location_id, terminal_id, counterparty_id,
      agreement_in_place, kyc_clearance, cend_in_place, due_dil_done,
      throughput_ago_pct, throughput_pms_pct, fee_first_30d_usd_per_m3, fee_next_30d_usd_per_m3,
      fh_parcels_usd_per_m3_per_mo, agency_fee_usd_per_m3_per_mo, contract_expiry, renewal, notes)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(...args);
  }
  revalidatePath("/master/storage"); redirect("/master/storage");
}
export async function deleteStorageAgreement(id: number) {
  getDb().prepare("DELETE FROM storage_agreements WHERE id=?").run(id);
  revalidatePath("/master/storage"); redirect("/master/storage");
}
