import { getDb } from "@/lib/db";
import { Deal, Counterparty, Entity, Bank, StorageAgreement, Product, dealMetrics, fmtUsd } from "@/lib/calc";
import Link from "next/link";
import { createPfiFromDeal, createFinalInvoiceFromDeal, createStorageInvoice } from "../actions";

export const dynamic = "force-dynamic";

export default function NewDocument({ searchParams }: {
  searchParams: { type?: string; deal_id?: string };
}) {
  const type = (searchParams.type ?? "PFI") as "PFI" | "FINAL_INVOICE" | "STORAGE_INVOICE";
  const db = getDb();

  if (type === "STORAGE_INVOICE") {
    const entities = db.prepare("SELECT * FROM entities ORDER BY code").all() as Entity[];
    const agreements = db.prepare(`
      SELECT s.*, l.code AS location_code, c.name AS counterparty_name
      FROM storage_agreements s
      LEFT JOIN locations l ON l.id = s.location_id
      LEFT JOIN counterparties c ON c.id = s.counterparty_id
    `).all() as (StorageAgreement & { location_code: string; counterparty_name: string })[];
    const banks = db.prepare("SELECT * FROM banks ORDER BY entity_id, label").all() as Bank[];

    return (
      <>
        <div className="toolbar">
          <h1>New Storage Invoice</h1>
          <Link href="/documents" className="btn secondary">Cancel</Link>
        </div>
        <form action={createStorageInvoice} className="card inline">
          <div className="row">
            <label>Storage agreement *
              <select name="storage_agreement_id" required>
                <option value="" disabled selected>—</option>
                {agreements.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.location_code} — {a.counterparty_name} (${a.fee_first_30d_usd_per_m3 ?? "?"}/m³ first 30d)
                  </option>
                ))}
              </select>
            </label>
            <label>Issuing entity *
              <select name="entity_id" required>
                <option value="" disabled selected>—</option>
                {entities.map((e) => <option key={e.id} value={e.id}>{e.code}</option>)}
              </select>
            </label>
            <label>Bank (optional override)
              <select name="bank_id" defaultValue="">
                <option value="">— default for entity —</option>
                {banks.map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
              </select>
            </label>
            <label>Volume stored (m³) *<input type="number" step="0.001" required name="qty_m3" /></label>
          </div>
          <div className="row">
            <label>Period from<input type="date" name="period_from" /></label>
            <label>Period to<input type="date" name="period_to" /></label>
            <label>Days stored<input type="number" name="days" defaultValue={30} /></label>
            <label>Due date<input type="date" name="due_date" /></label>
          </div>
          <div className="row">
            <label>Issue date<input type="date" name="issue_date" defaultValue={new Date().toISOString().slice(0,10)} /></label>
            <label style={{ gridColumn: "span 3" }}>Notes<input name="notes" /></label>
          </div>
          <p className="muted" style={{ fontSize: 12 }}>
            Storage fee is computed as <code>qty × fee_first_30d × (min(days,30)/30) + qty × fee_next_30d × ceil(max(0,days−30)/30)</code>.
            Fees come from the storage agreement.
          </p>
          <div><button type="submit">Generate Storage Invoice</button></div>
        </form>
      </>
    );
  }

  // PFI or Final Invoice — needs a deal
  const dealId = searchParams.deal_id ? Number(searchParams.deal_id) : null;
  const deals = db.prepare(`
    SELECT d.*, c.name AS counterparty_name, p.code AS product_code, e.code AS entity_code
    FROM deals d JOIN counterparties c ON c.id = d.counterparty_id
    JOIN products p ON p.id = d.product_id JOIN entities e ON e.id = d.entity_id
    WHERE d.status IN ('open','draft','closed') ORDER BY d.deal_date DESC
  `).all() as (Deal & { counterparty_name: string; product_code: string; entity_code: string })[];

  if (!dealId) {
    return (
      <>
        <div className="toolbar">
          <h1>New {type === "PFI" ? "PFI" : "Final Invoice"} — pick a deal</h1>
          <Link href="/documents" className="btn secondary">Cancel</Link>
        </div>
        <div className="card" style={{ padding: 0 }}>
          <table>
            <thead><tr><th>Deal #</th><th>Entity</th><th>Counterparty</th><th>Product</th><th>Incoterm</th><th className="num">Qty</th><th className="num">Price</th><th></th></tr></thead>
            <tbody>
              {deals.map((d) => (
                <tr key={d.id}>
                  <td>{d.deal_no}</td>
                  <td><span className="tag">{d.entity_code}</span></td>
                  <td>{d.counterparty_name}</td>
                  <td><span className="tag">{d.product_code}</span></td>
                  <td className="muted">{d.incoterm}</td>
                  <td className="num">{d.qty_m3}</td>
                  <td className="num">{fmtUsd(d.price_usd_per_m3, 2)}</td>
                  <td><Link className="btn" href={`/documents/new?type=${type}&deal_id=${d.id}`}>Use →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    );
  }

  const deal = db.prepare("SELECT * FROM deals WHERE id=?").get(dealId) as Deal | undefined;
  if (!deal) return <p>Deal not found.</p>;
  const cp = db.prepare("SELECT * FROM counterparties WHERE id=?").get(deal.counterparty_id) as Counterparty;
  const product = db.prepare("SELECT * FROM products WHERE id=?").get(deal.product_id) as Product;
  const banks = db.prepare("SELECT * FROM banks WHERE entity_id=? AND active=1 ORDER BY is_default DESC, label").all(deal.entity_id) as Bank[];
  const defaultBank = banks.find((b) => b.is_default) ?? banks[0];
  const loadings = db.prepare("SELECT * FROM deal_loadings WHERE deal_id=?").all(dealId);
  const payments = db.prepare("SELECT * FROM payments WHERE deal_id=?").all(dealId);
  const m = dealMetrics(deal, loadings as any, payments as any);

  const action = type === "PFI" ? createPfiFromDeal : createFinalInvoiceFromDeal;
  const defaultQty = type === "FINAL_INVOICE" ? (m.loadedQtyM3 || deal.qty_m3) : deal.qty_m3;
  const defaultDue = (() => {
    if (type !== "FINAL_INVOICE") return "";
    if (deal.oa_days != null) {
      const d = new Date();
      d.setDate(d.getDate() + deal.oa_days);
      return d.toISOString().slice(0,10);
    }
    return "";
  })();

  return (
    <>
      <div className="toolbar">
        <h1>New {type === "PFI" ? "PFI" : "Final Invoice"}</h1>
        <Link href={`/deals/${deal.id}`} className="btn secondary">← Deal {deal.deal_no}</Link>
      </div>

      <div className="grid grid-4">
        <Kpi label="Counterparty" value={cp.name} sub={cp.country ?? ""} />
        <Kpi label="Product" value={product.code} sub={deal.incoterm} />
        <Kpi label="Deal qty / price" value={`${deal.qty_m3} m³ × ${fmtUsd(deal.price_usd_per_m3,2)}`} />
        <Kpi label="Loaded so far" value={`${m.loadedQtyM3} m³`} sub={`Paid: ${fmtUsd(m.paidUsd)}`} />
      </div>

      <form action={action.bind(null, deal.id)} className="card inline" style={{ marginTop: 12 }}>
        <div className="row">
          <label>Issue date<input type="date" name="issue_date" defaultValue={new Date().toISOString().slice(0,10)} /></label>
          {type === "FINAL_INVOICE" && (
            <label>Due date<input type="date" name="due_date" defaultValue={defaultDue} /></label>
          )}
          <label>Qty (m³) *<input type="number" step="0.001" required name="qty_m3" defaultValue={defaultQty} /></label>
          <label>Price (USD/m³) *<input type="number" step="0.01" required name="price_usd_per_m3" defaultValue={deal.price_usd_per_m3} /></label>
        </div>
        <div className="row">
          <label>Bank account
            <select name="bank_id" defaultValue={defaultBank?.id ?? ""}>
              {banks.length === 0 && <option value="">No banks configured</option>}
              {banks.map((b) => (
                <option key={b.id} value={b.id}>{b.label} {b.is_default ? "(default)" : ""}</option>
              ))}
            </select>
          </label>
          <label style={{ gridColumn: "span 3" }}>Payment terms (full text on document)
            <input name="payment_terms_text" defaultValue={deal.payment_term_text} />
          </label>
        </div>
        <div className="row-2">
          <label>Notes (internal, not on document)<input name="notes" /></label>
          <div style={{ alignSelf: "end" }}>
            <button type="submit">Generate {type === "PFI" ? "PFI" : "Final Invoice"}</button>
          </div>
        </div>
      </form>
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value" style={{ fontSize: 16 }}>{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}
