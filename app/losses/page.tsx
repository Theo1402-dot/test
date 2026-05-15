import { getDb } from "@/lib/db";
import { Location, Product, fmtNum, fmtDate } from "@/lib/calc";
import { saveLoss, deleteLoss } from "./actions";

export const dynamic = "force-dynamic";

export default function Losses() {
  const db = getDb();
  const rows = db.prepare(`
    SELECT m.*, l.code AS location_code, l.name AS location_name,
      p.code AS product_code
    FROM mi_losses m
    LEFT JOIN locations l ON l.id = m.location_id
    LEFT JOIN products p ON p.id = m.product_id
    ORDER BY m.loss_date DESC, m.id DESC
  `).all() as any[];

  const locations = db.prepare("SELECT * FROM locations ORDER BY code").all() as Location[];
  const products = db.prepare("SELECT * FROM products ORDER BY code").all() as Product[];

  // Roll-up by location / terminal / product
  const rolled = new Map<string, { location: string; terminal: string; product: string; qty: number; count: number }>();
  for (const r of rows) {
    const key = `${r.location_code ?? "—"}|${r.terminal_name ?? "—"}|${r.product_code ?? "—"}`;
    const g = rolled.get(key) ?? {
      location: r.location_code ?? "—", terminal: r.terminal_name ?? "—",
      product: r.product_code ?? "—", qty: 0, count: 0,
    };
    g.qty += r.qty_m3;
    g.count += 1;
    rolled.set(key, g);
  }
  const totalQty = rows.reduce((s, r) => s + r.qty_m3, 0);

  return (
    <>
      <h1>MI Losses</h1>
      <p className="muted">Measured / inventory losses per location, terminal and product. Negative = product lost, positive = product gained on quality reconciliation.</p>

      <div className="grid grid-4">
        <Kpi label="Total entries" value={String(rows.length)} />
        <Kpi label="Net qty (m³)" value={fmtNum(totalQty, 1)} sub={totalQty < 0 ? "Loss" : "Gain"} />
        <Kpi label="Locations" value={String(new Set(rows.map((r) => r.location_code)).size)} />
        <Kpi label="Terminals" value={String(new Set(rows.map((r) => r.terminal_name)).size)} />
      </div>

      <h2>By location × terminal × product</h2>
      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        {rolled.size === 0 ? <div className="empty">No losses recorded.</div> : (
          <table>
            <thead><tr><th>Location</th><th>Terminal</th><th>Product</th><th className="num">Entries</th><th className="num">Net Qty (m³)</th></tr></thead>
            <tbody>
              {[...rolled.values()].sort((a, b) => a.qty - b.qty).map((g) => (
                <tr key={`${g.location}-${g.terminal}-${g.product}`}>
                  <td><span className="tag">{g.location}</span></td>
                  <td>{g.terminal}</td>
                  <td><span className="badge blue">{g.product}</span></td>
                  <td className="num">{g.count}</td>
                  <td className="num" style={{ color: g.qty < 0 ? "var(--red)" : "var(--green)" }}>{fmtNum(g.qty, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>All entries</h2>
      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        {rows.length === 0 ? <div className="empty">No entries.</div> : (
          <table>
            <thead><tr>
              <th>Date</th><th>Location</th><th>Terminal</th><th>Product</th>
              <th className="num">Qty m³</th><th>Reference</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{fmtDate(r.loss_date)}</td>
                  <td><span className="tag">{r.location_code ?? "—"}</span></td>
                  <td>{r.terminal_name ?? "—"}</td>
                  <td><span className="badge blue">{r.product_code ?? "—"}</span></td>
                  <td className="num" style={{ color: r.qty_m3 < 0 ? "var(--red)" : "var(--green)" }}>{fmtNum(r.qty_m3, 2)}</td>
                  <td className="muted">{r.reference ?? "—"}</td>
                  <td><form action={deleteLoss.bind(null, r.id)}><button className="btn danger">×</button></form></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>Add loss entry</h2>
      <form action={saveLoss.bind(null, null)} className="card inline">
        <div className="row">
          <label>Date<input type="date" name="loss_date" defaultValue={new Date().toISOString().slice(0,10)} /></label>
          <label>Location *
            <select name="location_id" required defaultValue="">
              <option value="" disabled>—</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}
            </select>
          </label>
          <label>Terminal (free text)<input name="terminal_name" placeholder="MOUNT MERU (MOCOH)" /></label>
          <label>Product *
            <select name="product_id" required defaultValue="">
              <option value="" disabled>—</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
            </select>
          </label>
        </div>
        <div className="row">
          <label>Qty m³ * (negative = loss)<input type="number" step="0.001" required name="qty_m3" /></label>
          <label>Reference<input name="reference" /></label>
          <label style={{ gridColumn: "span 2" }}>Notes<input name="notes" /></label>
        </div>
        <div><button type="submit">Add entry</button></div>
      </form>
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}
