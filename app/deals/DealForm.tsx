import { getDb } from "@/lib/db";
import { Deal, Entity, Counterparty, Product, Location } from "@/lib/calc";
import { saveDeal } from "./actions";

const INCOTERMS = [
  "FCA BEIRA", "FCA MAPUTO", "FCA MATOLA", "FCA MSASA", "FCA MTWARA", "FCA TANGA", "FCA DAR", "FCA DES",
  "DAP BEIRA", "DAP WB",
  "DDU LUSAKA", "DDU GABORONE", "DDU LUBUMBASHI",
  "ITT MSASA", "ITT FERUKA", "ITT MATOLA",
];

const PAYMENT_CODES = ["PPMT", "OA", "LC", "SBLC", "NET_OFF"];
const OA_TRIGGERS = ["LOADING", "RELEASE", "DELIVERY", "INVOICE", "DISCHARGE", "ARRIVAL", "OFFLOADING", "NOR"];

export function DealForm({
  deal, defaultCounterpartyId,
}: {
  deal?: Deal;
  defaultCounterpartyId?: number;
}) {
  const db = getDb();
  const entities = db.prepare("SELECT * FROM entities ORDER BY code").all() as Entity[];
  const counterparties = db.prepare("SELECT * FROM counterparties ORDER BY name").all() as Counterparty[];
  const products = db.prepare("SELECT * FROM products ORDER BY code").all() as Product[];
  const locations = db.prepare("SELECT * FROM locations ORDER BY code").all() as Location[];

  return (
    <form action={saveDeal.bind(null, deal?.id ?? null)} className="card inline">
      <div className="row">
        <label>Deal # *<input name="deal_no" required defaultValue={deal?.deal_no ?? ""} placeholder="190496" /></label>
        <label>Entity *
          <select name="entity_id" required defaultValue={deal?.entity_id ?? ""}>
            <option value="" disabled>—</option>
            {entities.map((e) => <option key={e.id} value={e.id}>{e.code} — {e.legal_name}</option>)}
          </select>
        </label>
        <label>Counterparty *
          <select name="counterparty_id" required defaultValue={deal?.counterparty_id ?? defaultCounterpartyId ?? ""}>
            <option value="" disabled>—</option>
            {counterparties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label>Type *
          <select name="type" required defaultValue={deal?.type ?? "SALE"}>
            <option value="SALE">SALE</option>
            <option value="PURCH">PURCHASE</option>
          </select>
        </label>
      </div>

      <div className="row">
        <label>Deal Date *<input type="date" name="deal_date" required defaultValue={deal?.deal_date?.slice(0,10) ?? new Date().toISOString().slice(0,10)} /></label>
        <label>Product *
          <select name="product_id" required defaultValue={deal?.product_id ?? ""}>
            <option value="" disabled>—</option>
            {products.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </select>
        </label>
        <label>Incoterm *
          <input name="incoterm" required list="incoterm-list" defaultValue={deal?.incoterm ?? ""} placeholder="FCA BEIRA" />
          <datalist id="incoterm-list">
            {INCOTERMS.map((i) => <option key={i} value={i} />)}
          </datalist>
        </label>
        <label>Location (auto from incoterm)
          <select name="location_id" defaultValue={deal?.location_id ?? ""}>
            <option value="">— auto —</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}
          </select>
        </label>
      </div>

      <div className="row">
        <label>Beg Date<input type="date" name="beg_date" defaultValue={deal?.beg_date?.slice(0,10) ?? ""} /></label>
        <label>End Date<input type="date" name="end_date" defaultValue={deal?.end_date?.slice(0,10) ?? ""} /></label>
        <label>Quantity (m³) *<input type="number" step="0.001" name="qty_m3" required defaultValue={deal?.qty_m3 ?? ""} /></label>
        <label>Price (USD/m³) *<input type="number" step="0.01" name="price_usd_per_m3" required defaultValue={deal?.price_usd_per_m3 ?? ""} /></label>
      </div>

      <div className="row-2">
        <label>Payment Term (full text) *
          <input name="payment_term_text" required defaultValue={deal?.payment_term_text ?? ""}
            placeholder="O/A 10D AFTER RELEASE" />
        </label>
        <label>Comments<input name="comments" defaultValue={deal?.comments ?? ""} /></label>
      </div>

      <div className="row">
        <label>Payment Code (auto)
          <select name="payment_term_code" defaultValue={deal?.payment_term_code ?? ""}>
            <option value="">— auto —</option>
            {PAYMENT_CODES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label>O/A Days (if OA)
          <input type="number" name="oa_days" defaultValue={deal?.oa_days ?? ""} />
        </label>
        <label>O/A Trigger
          <select name="oa_trigger" defaultValue={deal?.oa_trigger ?? ""}>
            <option value="">—</option>
            {OA_TRIGGERS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>Status
          <select name="status" defaultValue={deal?.status ?? "open"}>
            <option value="draft">Draft</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit">{deal ? "Save changes" : "Create deal"}</button>
      </div>
    </form>
  );
}
