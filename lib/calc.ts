export type DeliveryRow = {
  id: number;
  client_id: number;
  reference: string | null;
  product: "gasoil" | "gasoline";
  volume_m3: number;
  price_per_m3_usd: number;
  destination: string | null;
  truck_plate: string | null;
  loading_date: string | null;
  arrival_date: string | null;
  departure_date: string | null;
  laytime_hours: number;
  demurrage_usd_per_day: number;
  status: "in_transit" | "delivered" | "invoiced" | "paid" | "cancelled";
  invoice_date: string | null;
  due_date: string | null;
  paid_date: string | null;
  paid_amount_usd: number;
  demurrage_billed: number;
  notes: string | null;
  created_at: string;
};

export type ClientRow = {
  id: number;
  name: string;
  country: string | null;
  contact: string | null;
  credit_limit_usd: number;
  default_laytime_hours: number;
  default_demurrage_usd_per_day: number;
  payment_terms_days: number;
  created_at: string;
};

const HOUR_MS = 3600 * 1000;
const DAY_MS = 24 * HOUR_MS;

/**
 * Demurrage: laytime first, then USD/day per truck with NO pro-rata.
 * Any portion of a day beyond laytime counts as a full day.
 */
export function computeDemurrage(d: Pick<DeliveryRow,
  "arrival_date" | "departure_date" | "laytime_hours" | "demurrage_usd_per_day">) {
  if (!d.arrival_date || !d.departure_date) {
    return { hoursAtSite: 0, demurrageHours: 0, demurrageDays: 0, amountUsd: 0 };
  }
  const arr = new Date(d.arrival_date.replace(" ", "T")).getTime();
  const dep = new Date(d.departure_date.replace(" ", "T")).getTime();
  if (!isFinite(arr) || !isFinite(dep) || dep <= arr) {
    return { hoursAtSite: 0, demurrageHours: 0, demurrageDays: 0, amountUsd: 0 };
  }
  const hoursAtSite = (dep - arr) / HOUR_MS;
  const demurrageHours = Math.max(0, hoursAtSite - d.laytime_hours);
  // No pro-rata: any started day counts as a full day
  const demurrageDays = demurrageHours > 0 ? Math.ceil(demurrageHours / 24) : 0;
  const amountUsd = demurrageDays * d.demurrage_usd_per_day;
  return {
    hoursAtSite: round2(hoursAtSite),
    demurrageHours: round2(demurrageHours),
    demurrageDays,
    amountUsd: round2(amountUsd),
  };
}

export function cargoValue(d: Pick<DeliveryRow, "volume_m3" | "price_per_m3_usd">) {
  return round2(d.volume_m3 * d.price_per_m3_usd);
}

export function invoiceTotal(d: DeliveryRow) {
  const cargo = cargoValue(d);
  const dem = d.demurrage_billed ? computeDemurrage(d).amountUsd : 0;
  return round2(cargo + dem);
}

export function outstandingUsd(d: DeliveryRow): number {
  if (d.status === "paid" || d.status === "cancelled") return 0;
  if (d.status === "invoiced") {
    return Math.max(0, round2(invoiceTotal(d) - d.paid_amount_usd));
  }
  return 0;
}

export function inTransitValueUsd(d: DeliveryRow): number {
  if (d.status === "in_transit" || d.status === "delivered") {
    return cargoValue(d);
  }
  return 0;
}

export function accruedDemurrageUsd(d: DeliveryRow): number {
  if (d.status === "cancelled") return 0;
  if (d.demurrage_billed) return 0; // already part of the invoice
  return computeDemurrage(d).amountUsd;
}

export function agingBucket(dueDate: string | null, today = new Date()): string {
  if (!dueDate) return "not_due";
  const due = new Date(dueDate.replace(" ", "T")).getTime();
  const days = Math.floor((today.getTime() - due) / DAY_MS);
  if (days < 0) return "current";
  if (days <= 30) return "0-30";
  if (days <= 60) return "31-60";
  if (days <= 90) return "61-90";
  return "90+";
}

export function round2(n: number) {
  return Math.round(n * 100) / 100;
}

export function fmtUsd(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(n || 0);
}

export function fmtNum(n: number, digits = 2) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  }).format(n || 0);
}

export function fmtDate(s: string | null) {
  if (!s) return "—";
  return s.replace("T", " ").slice(0, 16);
}
