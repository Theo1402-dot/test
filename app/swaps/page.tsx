import { getDb } from "@/lib/db";
import { Swap, swapMtm, fmtUsd, fmtNum, fmtDate, Entity, Counterparty, Product, Location } from "@/lib/calc";
import { saveSwap, deleteSwap } from "./actions";

export const dynamic = "force-dynamic";

export default function Swaps() {
  const db = getDb();
  const rows = db.prepare(`
    SELECT s.*, e.code AS entity_code, c.name AS counterparty_name,
           p.code AS product_code, l.code AS location_code
    FROM swaps s
    LEFT JOIN entities e ON e.id = s.entity_id
    LEFT JOIN counterparties c ON c.id = s.counterparty_id
    LEFT JOIN products p ON p.id = s.product_id
    LEFT JOIN locations l ON l.id = s.location_id
    ORDER BY s.swap_date DESC, s.id DESC
  `).all() as any[];

  const entities = db.prepare("SELECT * FROM entities ORDER BY code").all() as Entity[];
  const counterparties = db.prepare("SELECT * FROM counterparties ORDER BY name").all() as Counterparty[];
  const products = db.prepare("SELECT * FROM products ORDER BY code").all() as Product[];
  const locations = db.prepare("SELECT * FROM locations ORDER BY code").all() as Location[];

  let totalPnl = 0, openPnl = 0;
  for (const r of rows) totalPnl += swapMtm(r);
  const buys = rows.filter((r) => r.side === "BUY");
  const sells = rows.filter((r) => r.side === "SELL");
  const buyQty = buys.reduce((s, r) => s + r.qty_m3, 0);
  const sellQty = sells.reduce((s, r) => s + r.qty_m3, 0);

  return (
    <>
      <h1>Swaps</h1>
      <p className="muted">Vessel-level swaps. Mark-to-market = (mtm − swap) × qty for BUY, opposite for SELL.</p>

      <div className="grid grid-4">
        <Kpi label="Total Swaps" value={String(rows.length)} sub={`${buys.length} BUY · ${sells.length} SELL`} />
        <Kpi label="BUY volume" value={`${fmtNum(buyQty, 0)} m³`} />
        <Kpi label="SELL volume" value={`${fmtNum(Math.abs(sellQty), 0)} m³`} />
        <Kpi label="Total MTM P&amp;L" value={fmtUsd(totalPnl)} sub={totalPnl >= 0 ? "Gain" : "Loss"} />
      </div>

      <h2>All swaps</h2>
      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        {rows.length === 0 ? <div className="empty">No swaps yet.</div> : (
          <table>
            <thead><tr>
              <th>Swap #</th><th>Date</th><th>Entity</th><th>Counterparty</th>
              <th>Side</th><th>Product</th><th>Vessel</th>
              <th className="num">Qty m³</th>
              <th className="num">Swap $</th><th className="num">MTM $</th>
              <th className="num">P&amp;L</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((r) => {
                const pnl = swapMtm(r);
                return (
                  <tr key={r.id}>
                    <td>{r.swap_no ?? `#${r.id}`}</td>
                    <td>{fmtDate(r.swap_date)}</td>
                    <td><span className="tag">{r.entity_code ?? "—"}</span></td>
                    <td>{r.counterparty_name ?? "—"}</td>
                    <td><span className={`badge ${r.side === "BUY" ? "blue" : "green"}`}>{r.side}</span></td>
                    <td><span className="tag">{r.product_code}</span></td>
                    <td className="muted">{r.vessel ?? "—"}</td>
                    <td className="num">{fmtNum(r.qty_m3, 0)}</td>
                    <td className="num">{r.swap_price_usd_per_m3 != null ? fmtUsd(r.swap_price_usd_per_m3, 2) : "—"}</td>
                    <td className="num">{r.mtm_price_usd_per_m3 != null ? fmtUsd(r.mtm_price_usd_per_m3, 2) : "—"}</td>
                    <td className="num" style={{ color: pnl > 0 ? "var(--green)" : pnl < 0 ? "var(--red)" : undefined }}>
                      {fmtUsd(pnl)}
                    </td>
                    <td><form action={deleteSwap.bind(null, r.id)}><button className="btn danger">×</button></form></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <h2>Add swap</h2>
      <form action={saveSwap.bind(null, null)} className="card inline">
        <div className="row">
          <label>Swap #<input name="swap_no" /></label>
          <label>Date<input type="date" name="swap_date" defaultValue={new Date().toISOString().slice(0,10)} /></label>
          <label>Entity
            <select name="entity_id" defaultValue="">
              <option value="">—</option>
              {entities.map((e) => <option key={e.id} value={e.id}>{e.code}</option>)}
            </select>
          </label>
          <label>Counterparty
            <select name="counterparty_id" defaultValue="">
              <option value="">—</option>
              {counterparties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
        </div>
        <div className="row">
          <label>Side *
            <select name="side" required defaultValue="BUY">
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
          </label>
          <label>Product *
            <select name="product_id" required defaultValue="">
              <option value="" disabled>—</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
            </select>
          </label>
          <label>Location
            <select name="location_id" defaultValue="">
              <option value="">—</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}
            </select>
          </label>
          <label>Vessel<input name="vessel" /></label>
        </div>
        <div className="row">
          <label>Qty m³ *<input type="number" step="0.001" required name="qty_m3" /></label>
          <label>Swap price ($/m³)<input type="number" step="0.01" name="swap_price_usd_per_m3" /></label>
          <label>MTM price ($/m³)<input type="number" step="0.01" name="mtm_price_usd_per_m3" /></label>
          <label>&nbsp;<button type="submit">Add swap</button></label>
        </div>
        <div className="row-2">
          <label>Notes<input name="notes" /></label>
        </div>
      </form>
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}
