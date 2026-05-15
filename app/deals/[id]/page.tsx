import { getDb } from "@/lib/db";
import {
  Deal, Loading, Payment, Counterparty, Entity, Product, Location, Terminal, Doc,
  dealMetrics, fmtUsd, fmtNum, fmtDate,
} from "@/lib/calc";
import Link from "next/link";
import { notFound } from "next/navigation";
import { DealForm } from "../DealForm";
import { addLoading, deleteLoading, addPayment, deletePayment, deleteDeal, setDealStatus } from "../actions";

export const dynamic = "force-dynamic";

export default function DealDetail({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const db = getDb();
  const deal = db.prepare("SELECT * FROM deals WHERE id=?").get(id) as Deal | undefined;
  if (!deal) notFound();
  const cp = db.prepare("SELECT * FROM counterparties WHERE id=?").get(deal.counterparty_id) as Counterparty;
  const entity = db.prepare("SELECT * FROM entities WHERE id=?").get(deal.entity_id) as Entity;
  const product = db.prepare("SELECT * FROM products WHERE id=?").get(deal.product_id) as Product;
  const loc = deal.location_id ? db.prepare("SELECT * FROM locations WHERE id=?").get(deal.location_id) as Location | undefined : undefined;
  const loadings = db.prepare("SELECT * FROM deal_loadings WHERE deal_id=? ORDER BY COALESCE(loading_date, nomination_date) DESC").all(id) as Loading[];
  const payments = db.prepare("SELECT * FROM payments WHERE deal_id=? ORDER BY payment_date DESC").all(id) as Payment[];
  const terminals = db.prepare("SELECT * FROM terminals").all() as Terminal[];
  const docs = db.prepare("SELECT * FROM documents WHERE deal_id=? ORDER BY issue_date DESC").all(id) as Doc[];
  const banks = db.prepare("SELECT id, label FROM banks WHERE entity_id=?").all(deal.entity_id) as { id: number; label: string }[];

  const m = dealMetrics(deal, loadings, payments);

  return (
    <>
      <div className="toolbar">
        <h1>Deal {deal.deal_no} <span className="pill">{entity.code}</span>
          <span className={`badge ${deal.type === "SALE" ? "green" : "blue"}`} style={{ marginLeft: 8 }}>{deal.type}</span>
          <span className={`badge ${{draft:"gray",open:"blue",closed:"green",cancelled:"red"}[deal.status]}`} style={{ marginLeft: 6 }}>{deal.status}</span>
        </h1>
        <div className="row-actions">
          <Link href="/deals" className="btn secondary">← All deals</Link>
          <Link href={`/documents/new?type=PFI&deal_id=${deal.id}`} className="btn">+ PFI</Link>
          <Link href={`/documents/new?type=FINAL_INVOICE&deal_id=${deal.id}`} className="btn">+ Final Invoice</Link>
        </div>
      </div>

      <div className="grid grid-4">
        <Kpi label="Counterparty" value={cp.name} sub={cp.country ?? ""} />
        <Kpi label="Product" value={product.code} sub={product.name} />
        <Kpi label="Location" value={loc?.code ?? "—"} sub={deal.incoterm} />
        <Kpi label="Deal Date" value={fmtDate(deal.deal_date)} sub={`${fmtDate(deal.beg_date)} → ${fmtDate(deal.end_date)}`} />
      </div>

      <div className="grid grid-4" style={{ marginTop: 12 }}>
        <Kpi label="Quantity" value={`${fmtNum(deal.qty_m3, 0)} m³`} sub={`${fmtUsd(deal.price_usd_per_m3, 2)}/m³`} />
        <Kpi label="Deal Amount" value={fmtUsd(m.dealAmountUsd)} sub={`Loaded: ${fmtNum(m.loadedQtyM3,0)} m³, bal: ${fmtNum(m.balanceQtyM3,0)} m³`} />
        <Kpi label="Paid In" value={fmtUsd(m.paidUsd)} sub={`Paid-for qty: ${fmtNum(m.qtyPaidForM3,0)} m³`} />
        <Kpi label={deal.type === "SALE" ? "O/A In Use" : "Prepaid (overhang)"}
             value={fmtUsd(deal.type === "SALE" ? m.oaInUseUsd : m.prepaidUsd)}
             sub={`Funds bal: ${fmtUsd(m.fundsBalanceUsd)}`} />
      </div>

      <h2>Edit deal</h2>
      <DealForm deal={deal} />

      <h2>Loadings / Nominations</h2>
      <div className="card" style={{ padding: 0, marginBottom: 12 }}>
        {loadings.length === 0 ? <div className="empty">No loadings recorded.</div> : (
          <table>
            <thead><tr>
              <th>Nom.</th><th>Loading</th><th>Release</th>
              <th>Arrival</th><th>Departure</th>
              <th className="num">Qty m³</th><th>Truck/Vessel</th><th>Destination</th><th></th>
            </tr></thead>
            <tbody>
              {loadings.map((l) => (
                <tr key={l.id}>
                  <td>{fmtDate(l.nomination_date)}</td>
                  <td>{fmtDate(l.loading_date)}</td>
                  <td>{fmtDate(l.release_date)}</td>
                  <td>{fmtDate(l.arrival_date)}</td>
                  <td>{fmtDate(l.departure_date)}</td>
                  <td className="num">{fmtNum(l.qty_m3, 2)}</td>
                  <td>{l.truck_plate ?? l.vessel ?? "—"}</td>
                  <td className="muted">{l.destination ?? "—"}</td>
                  <td><form action={deleteLoading.bind(null, deal.id, l.id)}><button className="btn danger">×</button></form></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <form action={addLoading.bind(null, deal.id)} className="card inline">
        <div className="row">
          <label>Nomination date<input type="date" name="nomination_date" /></label>
          <label>Loading date<input type="date" name="loading_date" /></label>
          <label>Release date<input type="date" name="release_date" /></label>
          <label>Qty (m³) *<input type="number" step="0.001" required name="qty_m3" /></label>
        </div>
        <div className="row">
          <label>Arrival<input type="datetime-local" name="arrival_date" /></label>
          <label>Departure<input type="datetime-local" name="departure_date" /></label>
          <label>Truck plate<input name="truck_plate" /></label>
          <label>Vessel<input name="vessel" /></label>
        </div>
        <div className="row">
          <label>Terminal
            <select name="terminal_id" defaultValue="">
              <option value="">—</option>
              {terminals.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
          <label style={{ gridColumn: "span 2" }}>Destination<input name="destination" /></label>
          <label>&nbsp;<button type="submit">Add loading</button></label>
        </div>
      </form>

      <h2>Payments</h2>
      <div className="card" style={{ padding: 0, marginBottom: 12 }}>
        {payments.length === 0 ? <div className="empty">No payments recorded.</div> : (
          <table>
            <thead><tr><th>Date</th><th>Direction</th><th className="num">Amount</th><th>Reference</th><th>Bank</th><th></th></tr></thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id}>
                  <td>{fmtDate(p.payment_date)}</td>
                  <td><span className={`badge ${p.direction === "IN" ? "green" : "amber"}`}>{p.direction}</span></td>
                  <td className="num">{fmtUsd(p.amount_usd)}</td>
                  <td>{p.reference ?? "—"}</td>
                  <td className="muted">{p.bank_id ? banks.find((b) => b.id === p.bank_id)?.label : "—"}</td>
                  <td><form action={deletePayment.bind(null, deal.id, p.id)}><button className="btn danger">×</button></form></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <form action={addPayment.bind(null, deal.id)} className="card inline">
        <div className="row">
          <label>Date *<input type="date" name="payment_date" required defaultValue={new Date().toISOString().slice(0,10)} /></label>
          <label>Direction
            <select name="direction" defaultValue="IN">
              <option value="IN">IN (received)</option>
              <option value="OUT">OUT (paid)</option>
            </select>
          </label>
          <label>Amount USD *<input type="number" step="0.01" required name="amount_usd" /></label>
          <label>Bank
            <select name="bank_id" defaultValue="">
              <option value="">—</option>
              {banks.map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
            </select>
          </label>
        </div>
        <div className="row-2">
          <label>Reference<input name="reference" /></label>
          <div style={{ alignSelf: "end" }}><button type="submit">Add payment</button></div>
        </div>
      </form>

      <h2>Documents</h2>
      <div className="card" style={{ padding: 0, marginBottom: 12 }}>
        {docs.length === 0 ? <div className="empty">No documents yet. Use the buttons above to generate.</div> : (
          <table>
            <thead><tr><th>#</th><th>Type</th><th>Issue</th><th>Due</th><th className="num">Amount</th><th>Status</th></tr></thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td><Link href={`/documents/${d.id}`}>{d.doc_no}</Link></td>
                  <td><span className="badge blue">{d.doc_type}</span></td>
                  <td>{fmtDate(d.issue_date)}</td>
                  <td>{fmtDate(d.due_date)}</td>
                  <td className="num">{fmtUsd(d.amount_usd)}</td>
                  <td><span className={`badge ${{draft:"gray",issued:"amber",paid:"green",cancelled:"red"}[d.status]}`}>{d.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>Actions</h2>
      <div className="card" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {deal.status !== "closed" && (
          <form action={setDealStatus.bind(null, deal.id, "closed")}><button className="btn">Close deal</button></form>
        )}
        {deal.status !== "open" && (
          <form action={setDealStatus.bind(null, deal.id, "open")}><button className="btn secondary">Re-open</button></form>
        )}
        {deal.status !== "cancelled" && (
          <form action={setDealStatus.bind(null, deal.id, "cancelled")}><button className="btn secondary">Cancel</button></form>
        )}
        <form action={deleteDeal.bind(null, deal.id)}><button className="btn danger">Delete deal</button></form>
      </div>
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}
