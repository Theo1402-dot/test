import { getDb } from "./db";

// -------- Types --------

export type Entity = { id: number; code: string; legal_name: string; address: string | null; tax_id: string | null };
export type Bank = {
  id: number; entity_id: number; label: string; currency: string;
  beneficiary: string; bank_name: string; bank_address: string | null;
  swift: string | null; iban: string | null; account_no: string | null;
  correspondent_bank: string | null; correspondent_swift: string | null;
  is_default: number; active: number;
};
export type Counterparty = {
  id: number; name: string; legal_name: string | null; country: string | null;
  address: string | null; contact_name: string | null; contact_email: string | null;
  contact_phone: string | null; allowed_oa_usd: number;
  default_payment_term: string | null;
  default_demurrage_usd_per_day: number; default_laytime_hours: number; notes: string | null;
};
export type FrameContract = {
  id: number; counterparty_id: number;
  itt_deals: number; fca_deals: number; ddu_deals: number;
  truck_dem_usd_per_day: number | null;
  ppmt: number; oa: number; sblc: number;
  date_signed: string | null; expiry_date: string | null; notes: string | null;
};
export type Product = { id: number; code: string; name: string; density_kg_per_m3: number | null };
export type Location = { id: number; code: string; name: string; country: string | null; type: string | null };
export type Terminal = { id: number; location_id: number; name: string; operator: string | null; capacity_m3: number | null };
export type StorageAgreement = {
  id: number; location_id: number; terminal_id: number | null; counterparty_id: number | null;
  agreement_in_place: number; kyc_clearance: number; cend_in_place: number; due_dil_done: number;
  throughput_ago_pct: number | null; throughput_pms_pct: number | null;
  fee_first_30d_usd_per_m3: number | null; fee_next_30d_usd_per_m3: number | null;
  fh_parcels_usd_per_m3_per_mo: number | null; agency_fee_usd_per_m3_per_mo: number | null;
  contract_expiry: string | null; renewal: string | null; notes: string | null;
};
export type Deal = {
  id: number; deal_no: string;
  entity_id: number; counterparty_id: number;
  type: "PURCH" | "SALE"; deal_date: string;
  product_id: number; incoterm: string; location_id: number | null;
  beg_date: string | null; end_date: string | null;
  price_usd_per_m3: number; qty_m3: number;
  payment_term_text: string; payment_term_code: string | null;
  oa_days: number | null; oa_trigger: string | null;
  status: "draft" | "open" | "closed" | "cancelled";
  due_date: string | null; sblc_id: number | null; comments: string | null;
  created_at: string;
};
export type Loading = {
  id: number; deal_id: number;
  nomination_date: string | null; loading_date: string | null; release_date: string | null;
  arrival_date: string | null; departure_date: string | null;
  qty_m3: number; truck_plate: string | null; vessel: string | null;
  terminal_id: number | null; destination: string | null; notes: string | null;
};
export type Payment = {
  id: number; deal_id: number; payment_date: string;
  amount_usd: number; direction: "IN" | "OUT";
  reference: string | null; bank_id: number | null; notes: string | null;
};
export type Doc = {
  id: number; doc_type: "PFI" | "FINAL_INVOICE" | "STORAGE_INVOICE";
  doc_no: string; deal_id: number | null; storage_agreement_id: number | null;
  entity_id: number; counterparty_id: number; bank_id: number | null;
  issue_date: string; due_date: string | null; currency: string;
  qty_m3: number | null; price_usd_per_m3: number | null; amount_usd: number;
  period_from: string | null; period_to: string | null;
  payment_terms_text: string | null; notes: string | null;
  status: "draft" | "issued" | "paid" | "cancelled";
  paid_date: string | null; paid_amount_usd: number;
};

// -------- Deal derived metrics --------

export type DealMetrics = {
  dealAmountUsd: number;
  loadedQtyM3: number;
  balanceQtyM3: number;
  paidUsd: number;
  qtyPaidForM3: number;
  fundsBalanceUsd: number;   // paid - (loaded * price). negative = O/A in use (we are owed)
  oaInUseUsd: number;        // for sales only: max(0, loaded*price - paid)
  prepaidUsd: number;        // for purchases: max(0, paid - loaded*price)
};

export function dealMetrics(d: Deal, loadings: Loading[], payments: Payment[]): DealMetrics {
  const dealAmountUsd = round2(d.price_usd_per_m3 * d.qty_m3);
  const loadedQtyM3 = round3(loadings.reduce((s, l) => s + (l.qty_m3 || 0), 0));
  const balanceQtyM3 = round3(d.qty_m3 - loadedQtyM3);
  const paidUsd = round2(payments.reduce((s, p) => s + (p.direction === "IN" ? p.amount_usd : -p.amount_usd), 0));
  const qtyPaidForM3 = d.price_usd_per_m3 > 0 ? round3(paidUsd / d.price_usd_per_m3) : 0;
  const loadedValue = round2(loadedQtyM3 * d.price_usd_per_m3);
  const fundsBalanceUsd = round2(paidUsd - loadedValue);
  const oaInUseUsd = d.type === "SALE" ? Math.max(0, round2(loadedValue - paidUsd)) : 0;
  const prepaidUsd = d.type === "PURCH" ? Math.max(0, round2(paidUsd - loadedValue)) : 0;
  return { dealAmountUsd, loadedQtyM3, balanceQtyM3, paidUsd, qtyPaidForM3, fundsBalanceUsd, oaInUseUsd, prepaidUsd };
}

// -------- Aggregate exposure per counterparty --------

export type CounterpartyExposure = {
  counterparty: Counterparty;
  qtyBalanceM3: number;
  usdBalance: number;        // net USD owed to us (positive = they owe us)
  oaInUseUsd: number;        // current O/A consumption
  remainingOaUsd: number;    // allowed - used
  utilisation: number;
  openDeals: number;
};

export function counterpartyExposure(): CounterpartyExposure[] {
  const db = getDb();
  const parties = db.prepare("SELECT * FROM counterparties ORDER BY name").all() as Counterparty[];
  const deals = db.prepare("SELECT * FROM deals WHERE status IN ('open','draft')").all() as Deal[];
  const loadings = db.prepare("SELECT * FROM deal_loadings").all() as Loading[];
  const payments = db.prepare("SELECT * FROM payments").all() as Payment[];

  return parties.map((c) => {
    const myDeals = deals.filter((d) => d.counterparty_id === c.id);
    let qtyBal = 0, usdBal = 0, oaInUse = 0;
    for (const d of myDeals) {
      const ld = loadings.filter((x) => x.deal_id === d.id);
      const pm = payments.filter((x) => x.deal_id === d.id);
      const m = dealMetrics(d, ld, pm);
      if (d.type === "SALE") {
        qtyBal += m.balanceQtyM3;
        usdBal += m.oaInUseUsd;
        oaInUse += m.oaInUseUsd;
      } else {
        // PURCH: prepaid means we are owed product
        qtyBal -= m.balanceQtyM3; // we are owed barrels (negative balance to us)
        usdBal -= m.prepaidUsd;
      }
    }
    const remaining = c.allowed_oa_usd - oaInUse;
    const utilisation = c.allowed_oa_usd > 0 ? oaInUse / c.allowed_oa_usd : 0;
    return {
      counterparty: c,
      qtyBalanceM3: round3(qtyBal),
      usdBalance: round2(usdBal),
      oaInUseUsd: round2(oaInUse),
      remainingOaUsd: round2(remaining),
      utilisation,
      openDeals: myDeals.length,
    };
  });
}

// -------- Aggregate position per location/product --------

export type LocationPosition = {
  locationCode: string;
  locationName: string;
  productCode: string;
  productName: string;
  purchasedM3: number;
  soldM3: number;
  unsoldM3: number;       // purchased - sold
  loadedPurchM3: number;
  loadedSaleM3: number;
  fcaNomNotLoadedM3: number;
  fcaSoldNotNomM3: number; // sold-not-loaded
  physicalBalanceM3: number; // loadedPurch - loadedSale
  inTankUnsoldM3: number;    // physical - (sold-not-loaded)
};

export function locationPositions(): LocationPosition[] {
  const db = getDb();
  const deals = db.prepare("SELECT * FROM deals WHERE status IN ('open','draft','closed')").all() as Deal[];
  const loadings = db.prepare("SELECT * FROM deal_loadings").all() as Loading[];
  const products = db.prepare("SELECT * FROM products").all() as Product[];
  const locations = db.prepare("SELECT * FROM locations").all() as Location[];

  const pById = new Map(products.map((p) => [p.id, p]));
  const lById = new Map(locations.map((l) => [l.id, l]));
  const ldByDeal = new Map<number, number>();
  for (const l of loadings) ldByDeal.set(l.deal_id, (ldByDeal.get(l.deal_id) || 0) + (l.qty_m3 || 0));

  const key = (locId: number, prodId: number) => `${locId}|${prodId}`;
  const buckets = new Map<string, LocationPosition>();
  function get(locId: number, prodId: number): LocationPosition {
    const k = key(locId, prodId);
    let b = buckets.get(k);
    if (!b) {
      const loc = lById.get(locId);
      const pr = pById.get(prodId);
      if (!loc || !pr) return null as any;
      b = {
        locationCode: loc.code, locationName: loc.name,
        productCode: pr.code, productName: pr.name,
        purchasedM3: 0, soldM3: 0, unsoldM3: 0,
        loadedPurchM3: 0, loadedSaleM3: 0,
        fcaNomNotLoadedM3: 0, fcaSoldNotNomM3: 0,
        physicalBalanceM3: 0, inTankUnsoldM3: 0,
      };
      buckets.set(k, b);
    }
    return b;
  }

  for (const d of deals) {
    if (!d.location_id) continue;
    const b = get(d.location_id, d.product_id);
    if (!b) continue;
    const loaded = ldByDeal.get(d.id) || 0;
    if (d.type === "PURCH") {
      b.purchasedM3 += d.qty_m3;
      b.loadedPurchM3 += loaded;
    } else {
      b.soldM3 += d.qty_m3;
      b.loadedSaleM3 += loaded;
      b.fcaSoldNotNomM3 += Math.max(0, d.qty_m3 - loaded);
    }
  }
  for (const b of buckets.values()) {
    b.unsoldM3 = round3(b.purchasedM3 - b.soldM3);
    b.physicalBalanceM3 = round3(b.loadedPurchM3 - b.loadedSaleM3);
    b.inTankUnsoldM3 = round3(b.physicalBalanceM3 - b.fcaSoldNotNomM3);
    b.purchasedM3 = round3(b.purchasedM3);
    b.soldM3 = round3(b.soldM3);
    b.loadedPurchM3 = round3(b.loadedPurchM3);
    b.loadedSaleM3 = round3(b.loadedSaleM3);
    b.fcaSoldNotNomM3 = round3(b.fcaSoldNotNomM3);
  }
  return Array.from(buckets.values()).sort((a, b) =>
    a.locationCode.localeCompare(b.locationCode) || a.productCode.localeCompare(b.productCode));
}

// -------- Demurrage (kept from earlier app) --------

const HOUR_MS = 3600 * 1000;

export function computeDemurrage(args: {
  arrival_date: string | null;
  departure_date: string | null;
  laytime_hours: number;
  demurrage_usd_per_day: number;
}) {
  if (!args.arrival_date || !args.departure_date) {
    return { hoursAtSite: 0, demurrageHours: 0, demurrageDays: 0, amountUsd: 0 };
  }
  const arr = new Date(args.arrival_date.replace(" ", "T")).getTime();
  const dep = new Date(args.departure_date.replace(" ", "T")).getTime();
  if (!isFinite(arr) || !isFinite(dep) || dep <= arr) {
    return { hoursAtSite: 0, demurrageHours: 0, demurrageDays: 0, amountUsd: 0 };
  }
  const hoursAtSite = (dep - arr) / HOUR_MS;
  const demurrageHours = Math.max(0, hoursAtSite - args.laytime_hours);
  const demurrageDays = demurrageHours > 0 ? Math.ceil(demurrageHours / 24) : 0;
  return {
    hoursAtSite: round2(hoursAtSite),
    demurrageHours: round2(demurrageHours),
    demurrageDays,
    amountUsd: round2(demurrageDays * args.demurrage_usd_per_day),
  };
}

// -------- Helpers --------

export function round2(n: number) { return Math.round(n * 100) / 100; }
export function round3(n: number) { return Math.round(n * 1000) / 1000; }

export function fmtUsd(n: number, digits = 0) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(n || 0);
}
export function fmtNum(n: number, digits = 2) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(n || 0);
}
export function fmtDate(s: string | null) {
  if (!s) return "—";
  return s.replace("T", " ").slice(0, 10);
}
export function fmtDateLong(s: string | null) {
  if (!s) return "";
  const d = new Date(s.replace(" ", "T"));
  if (!isFinite(d.getTime())) return s;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

// Try to extract a normalised O/A days + trigger from a free-text payment term.
export function parsePaymentTerm(text: string | null): { code: string | null; oaDays: number | null; trigger: string | null } {
  if (!text) return { code: null, oaDays: null, trigger: null };
  const u = text.toUpperCase();
  if (u.includes("PPMT") && !u.includes("O/A")) return { code: "PPMT", oaDays: null, trigger: null };
  if (u.includes("SBLC")) return { code: "SBLC", oaDays: null, trigger: null };
  if (u.includes("NET OFF")) return { code: "NET_OFF", oaDays: null, trigger: null };
  if (u.includes("DOC LC") || u === "LC" || u.includes("DOC LC") || u.includes("L/C")) return { code: "LC", oaDays: null, trigger: null };
  if (u.includes("O/A")) {
    const days = /(\d{1,3})\s*D/i.exec(u);
    let trig: string | null = null;
    if (u.includes("RELEASE")) trig = "RELEASE";
    else if (u.includes("LOADING")) trig = "LOADING";
    else if (u.includes("DELIVERY")) trig = "DELIVERY";
    else if (u.includes("INVOICE")) trig = "INVOICE";
    else if (u.includes("DISCHARGE")) trig = "DISCHARGE";
    else if (u.includes("ARRIVAL")) trig = "ARRIVAL";
    else if (u.includes("OFFLOADING")) trig = "OFFLOADING";
    else if (u.includes("NOR")) trig = "NOR";
    return { code: "OA", oaDays: days ? Number(days[1]) : null, trigger: trig };
  }
  return { code: null, oaDays: null, trigger: null };
}
