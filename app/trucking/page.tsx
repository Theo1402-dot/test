import { getDb } from "@/lib/db";
import {
  Deal, Loading, Payment, Counterparty,
  dealMetrics, computeDemurrage, fmtUsd, fmtNum, fmtDate,
} from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

function daysLeftToLift(end: string | null): number | null {
  if (!end) return null;
  const t = new Date(end.replace(" ", "T")).getTime();
  if (!isFinite(t)) return null;
  return Math.floor((t - Date.now()) / 86400000);
}

export default function Trucking() {
  const db = getDb();
  const deals = db.prepare(`
    SELECT d.*, c.name AS counterparty_name, p.code AS product_code, e.code AS entity_code, l.code AS location_code
    FROM deals d
    JOIN counterparties c ON c.id = d.counterparty_id
    JOIN products p ON p.id = d.product_id
    JOIN entities e ON e.id = d.entity_id
    LEFT JOIN locations l ON l.id = d.location_id
    WHERE d.status='open' AND (d.incoterm LIKE 'FCA%' OR d.incoterm LIKE 'DDU%')
    ORDER BY d.end_date ASC NULLS LAST, d.deal_date DESC
  `).all() as any[];
  const loadings = db.prepare("SELECT * FROM deal_loadings").all() as Loading[];
  const payments = db.prepare("SELECT * FROM payments").all() as Payment[];

  // Demurrage rollup across all loadings that have actual arrival/departure
  const allLoadings = loadings.filter((l) => l.arrival_date && l.departure_date);
  let demTotal = 0, demUnbilled = 0;
  const recentDemurrage: Array<{ deal_no: string; counterparty: string; loading: Loading; amount: number; days: number }> = [];
  for (const l of allLoadings) {
    const lay = l.laytime_hours ?? 24;
    const rate = l.demurrage_usd_per_day ?? 0;
    if (rate === 0) continue;
    const dem = computeDemurrage({ arrival_date: l.arrival_date, departure_date: l.departure_date, laytime_hours: lay, demurrage_usd_per_day: rate });
    if (dem.amountUsd > 0) {
      demTotal += dem.amountUsd;
      demUnbilled += dem.amountUsd; // we treat all as unbilled for now (no billed flag yet on loading)
      const d = db.prepare(`SELECT d.deal_no, c.name AS cp FROM deals d JOIN counterparties c ON c.id = d.counterparty_id WHERE d.id=?`).get(l.deal_id) as any;
      recentDemurrage.push({ deal_no: d?.deal_no ?? `#${l.deal_id}`, counterparty: d?.cp ?? "", loading: l, amount: dem.amountUsd, days: dem.demurrageDays });
    }
  }
  recentDemurrage.sort((a, b) => b.amount - a.amount);

  return (
    <>
      <h1>Trucking Overview</h1>
      <p className="muted">Open FCA / DDU deals with lifting status. Loading-level demurrage is computed automatically when arrival/departure timestamps are recorded.</p>

      <div className="grid grid-4">
        <Kpi label="Open FCA/DDU deals" value={String(deals.length)} />
        <Kpi label="Loadings recorded" value={String(loadings.length)} />
        <Kpi label="Demurrage incurred" value={fmtUsd(demTotal)} sub={`${recentDemurrage.length} loadings over laytime`} />
        <Kpi label="Demurrage unbilled" value={fmtUsd(demUnbilled)} />
      </div>

      <h2>Open deals — lifting status</h2>
      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        {deals.length === 0 ? <div className="empty">No open FCA/DDU deals.</div> : (
          <table>
            <thead><tr>
              <th>Deal #</th><th>Counterparty</th><th>Product</th><th>Incoterm</th>
              <th>Lift beg</th><th>Lift end</th><th className="num">Days left</th>
              <th className="num">Deal m³</th><th className="num">Loaded</th><th className="num">Bal.</th>
              <th>Pmt term</th>
            </tr></thead>
            <tbody>
              {deals.map((d) => {
                const m = dealMetrics(d, loadings.filter((l) => l.deal_id === d.id), payments.filter((p) => p.deal_id === d.id));
                const days = daysLeftToLift(d.end_date);
                const cls = days == null ? "" : days < 0 ? "red" : days <= 5 ? "amber" : "";
                return (
                  <tr key={d.id}>
                    <td><Link href={`/deals/${d.id}`}>{d.deal_no}</Link></td>
                    <td>{d.counterparty_name}</td>
                    <td><span className="tag">{d.product_code}</span></td>
                    <td className="muted" style={{ fontSize: 12 }}>{d.incoterm}</td>
                    <td>{fmtDate(d.beg_date)}</td>
                    <td>{fmtDate(d.end_date)}</td>
                    <td className="num"><span className={`badge ${cls}`}>{days ?? "—"}</span></td>
                    <td className="num">{fmtNum(d.qty_m3, 0)}</td>
                    <td className="num">{fmtNum(m.loadedQtyM3, 0)}</td>
                    <td className="num">{fmtNum(m.balanceQtyM3, 0)}</td>
                    <td className="muted" style={{ fontSize: 12 }}>{d.payment_term_code ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <h2>Demurrage events</h2>
      <div className="card" style={{ padding: 0 }}>
        {recentDemurrage.length === 0 ? (
          <div className="empty">No demurrage incurred. Set <code>laytime_hours</code> + <code>demurrage_usd_per_day</code> on a loading to compute automatically.</div>
        ) : (
          <table>
            <thead><tr>
              <th>Deal #</th><th>Counterparty</th><th>Truck</th>
              <th>Arrival</th><th>Departure</th>
              <th className="num">Days over</th><th className="num">Rate</th><th className="num">Amount</th>
            </tr></thead>
            <tbody>
              {recentDemurrage.slice(0, 50).map(({ deal_no, counterparty, loading: l, days, amount }) => (
                <tr key={l.id}>
                  <td><Link href={`/deals/${l.deal_id}`}>{deal_no}</Link></td>
                  <td>{counterparty}</td>
                  <td className="muted">{l.truck_plate ?? l.vessel ?? "—"}</td>
                  <td>{fmtDate(l.arrival_date)}</td>
                  <td>{fmtDate(l.departure_date)}</td>
                  <td className="num">{days}</td>
                  <td className="num">{fmtUsd(l.demurrage_usd_per_day ?? 0)}</td>
                  <td className="num"><strong>{fmtUsd(amount)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}
