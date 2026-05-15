import { getDb } from "@/lib/db";
import { Counterparty, Security, fmtUsd, fmtDate } from "@/lib/calc";
import Link from "next/link";
import { saveSecurity, deleteSecurity } from "./actions";

export const dynamic = "force-dynamic";

const TYPES = ["SBLC", "BG", "PARENT_GUARANTEE", "OTHER"];

function daysUntil(d: string | null) {
  if (!d) return null;
  const t = new Date(d.replace(" ", "T")).getTime();
  if (!isFinite(t)) return null;
  return Math.floor((t - Date.now()) / 86400000);
}

export default function BySecurity() {
  const db = getDb();
  const rows = db.prepare(`
    SELECT s.*, c.name AS counterparty_name FROM securities s
    JOIN counterparties c ON c.id = s.counterparty_id
    ORDER BY s.expiry_date ASC NULLS LAST, c.name
  `).all() as (Security & { counterparty_name: string })[];
  const counterparties = db.prepare("SELECT * FROM counterparties ORDER BY name").all() as Counterparty[];

  const total = rows.reduce((s, r) => s + r.amount_usd, 0);
  const expiringSoon = rows.filter((r) => {
    const d = daysUntil(r.expiry_date);
    return d != null && d >= 0 && d <= 30;
  });
  const expired = rows.filter((r) => {
    const d = daysUntil(r.expiry_date);
    return d != null && d < 0;
  });

  return (
    <>
      <h1>By Security / SBLC</h1>
      <p className="muted">Standby Letters of Credit, bank guarantees and parent guarantees backing counterparty exposure.</p>

      <div className="grid grid-4">
        <Kpi label="Total Covered" value={fmtUsd(total)} sub={`${rows.length} securities`} />
        <Kpi label="Expiring ≤30 days" value={String(expiringSoon.length)} sub={fmtUsd(expiringSoon.reduce((s, r) => s + r.amount_usd, 0))} />
        <Kpi label="Expired" value={String(expired.length)} sub={fmtUsd(expired.reduce((s, r) => s + r.amount_usd, 0))} />
        <Kpi label="Counterparties Covered" value={String(new Set(rows.map((r) => r.counterparty_id)).size)} />
      </div>

      <h2>Securities</h2>
      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        {rows.length === 0 ? <div className="empty">No securities yet.</div> : (
          <table>
            <thead><tr>
              <th>Counterparty</th><th>Type</th><th>Reference</th>
              <th className="num">Amount</th>
              <th>Issue</th><th>Expiry</th><th>LDS</th>
              <th>Covering</th><th></th>
            </tr></thead>
            <tbody>
              {rows.map((r) => {
                const days = daysUntil(r.expiry_date);
                const expiryClass = days == null ? "" : days < 0 ? "red" : days <= 30 ? "amber" : "";
                return (
                  <tr key={r.id}>
                    <td><Link href={`/master/counterparties/${r.counterparty_id}`}>{r.counterparty_name}</Link></td>
                    <td><span className="badge blue">{r.type}</span></td>
                    <td className="muted">{r.reference ?? "—"}</td>
                    <td className="num">{fmtUsd(r.amount_usd)}</td>
                    <td>{fmtDate(r.issue_date)}</td>
                    <td>
                      {fmtDate(r.expiry_date)}
                      {days != null && (
                        <div style={{ fontSize: 11 }}>
                          <span className={`badge ${expiryClass}`}>
                            {days < 0 ? `${-days}d expired` : days <= 30 ? `${days}d left` : `${days}d`}
                          </span>
                        </div>
                      )}
                    </td>
                    <td>{fmtDate(r.lds_date)}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{r.covering ?? "—"}</td>
                    <td><form action={deleteSecurity.bind(null, r.id)}><button className="btn danger">×</button></form></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <h2>Add security</h2>
      <form action={saveSecurity.bind(null, null)} className="card inline">
        <div className="row">
          <label>Counterparty *
            <select name="counterparty_id" required>
              <option value="" disabled selected>—</option>
              {counterparties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label>Type
            <select name="type" defaultValue="SBLC">
              {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label>Reference<input name="reference" placeholder="SBLC ref / bank ref" /></label>
          <label>Amount USD *<input type="number" step="0.01" required name="amount_usd" /></label>
        </div>
        <div className="row">
          <label>Issue date<input type="date" name="issue_date" /></label>
          <label>Expiry date<input type="date" name="expiry_date" /></label>
          <label>LDS<input type="date" name="lds_date" /></label>
          <label>&nbsp;<button type="submit">Add</button></label>
        </div>
        <div className="row-2">
          <label>Covering (free text)<input name="covering" placeholder="PRODUCTS + DEMURRAGE up to USD …" /></label>
          <label>Notes<input name="notes" /></label>
        </div>
      </form>
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}
