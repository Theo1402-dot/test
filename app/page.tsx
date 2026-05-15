import { getDb } from "@/lib/db";
import {
  ClientRow, DeliveryRow,
  accruedDemurrageUsd, agingBucket, cargoValue,
  computeDemurrage, fmtUsd, inTransitValueUsd, invoiceTotal, outstandingUsd,
} from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function Dashboard() {
  const db = getDb();
  const clients = db.prepare("SELECT * FROM clients ORDER BY name").all() as ClientRow[];
  const deliveries = db.prepare("SELECT * FROM deliveries ORDER BY created_at DESC").all() as DeliveryRow[];

  let totalAR = 0, totalInTransit = 0, totalAccrued = 0, totalCreditLimit = 0;
  const buckets: Record<string, number> = { current: 0, "0-30": 0, "31-60": 0, "61-90": 0, "90+": 0 };

  for (const d of deliveries) {
    totalAR += outstandingUsd(d);
    totalInTransit += inTransitValueUsd(d);
    totalAccrued += accruedDemurrageUsd(d);
    if (d.status === "invoiced") {
      const b = agingBucket(d.due_date);
      if (b in buckets) buckets[b] += outstandingUsd(d);
    }
  }
  for (const c of clients) totalCreditLimit += c.credit_limit_usd;

  // Per-client exposure rollup
  const clientExposure = clients.map((c) => {
    const dels = deliveries.filter((d) => d.client_id === c.id);
    const ar = dels.reduce((s, d) => s + outstandingUsd(d), 0);
    const inTransit = dels.reduce((s, d) => s + inTransitValueUsd(d), 0);
    const demAccrued = dels.reduce((s, d) => s + accruedDemurrageUsd(d), 0);
    const total = ar + inTransit;
    const util = c.credit_limit_usd > 0 ? total / c.credit_limit_usd : 0;
    return { client: c, ar, inTransit, demAccrued, total, util };
  }).sort((a, b) => b.total - a.total);

  const overdue = deliveries.filter((d) => d.status === "invoiced" &&
    outstandingUsd(d) > 0 &&
    agingBucket(d.due_date) !== "current" && agingBucket(d.due_date) !== "not_due");

  const recentDemurrage = deliveries
    .map((d) => ({ d, calc: computeDemurrage(d) }))
    .filter((x) => x.calc.amountUsd > 0)
    .sort((a, b) => b.calc.amountUsd - a.calc.amountUsd)
    .slice(0, 5);

  return (
    <>
      <h1>Dashboard</h1>

      <div className="grid grid-4">
        <Kpi label="Accounts Receivable" value={fmtUsd(totalAR)} sub={`${deliveries.filter(d => d.status === "invoiced").length} open invoices`} />
        <Kpi label="In-Transit / Delivered" value={fmtUsd(totalInTransit)} sub={`${deliveries.filter(d => d.status === "in_transit" || d.status === "delivered").length} trucks`} />
        <Kpi label="Demurrage Accrued (Unbilled)" value={fmtUsd(totalAccrued)} sub="Pending recovery" />
        <Kpi label="Total Credit Limits" value={fmtUsd(totalCreditLimit)} sub={`${clients.length} clients`} />
      </div>

      <h2>AR Aging</h2>
      <div className="grid grid-4">
        <Kpi label="Current" value={fmtUsd(buckets.current)} />
        <Kpi label="0–30 overdue" value={fmtUsd(buckets["0-30"])} />
        <Kpi label="31–60 overdue" value={fmtUsd(buckets["31-60"])} />
        <Kpi label="61–90 / 90+ overdue" value={fmtUsd(buckets["61-90"] + buckets["90+"])} />
      </div>

      <h2>Client Exposure</h2>
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Client</th>
              <th className="num">Credit Limit</th>
              <th className="num">AR</th>
              <th className="num">In Transit</th>
              <th className="num">Demurrage</th>
              <th className="num">Total Exposure</th>
              <th>Utilisation</th>
            </tr>
          </thead>
          <tbody>
            {clientExposure.map((row) => {
              const pct = Math.min(100, row.util * 100);
              const cls = row.util >= 1 ? "red" : row.util >= 0.8 ? "amber" : "";
              return (
                <tr key={row.client.id}>
                  <td><Link href={`/clients/${row.client.id}`}>{row.client.name}</Link>
                    <div className="muted" style={{ fontSize: 11 }}>{row.client.country}</div>
                  </td>
                  <td className="num">{fmtUsd(row.client.credit_limit_usd)}</td>
                  <td className="num">{fmtUsd(row.ar)}</td>
                  <td className="num">{fmtUsd(row.inTransit)}</td>
                  <td className="num">{fmtUsd(row.demAccrued)}</td>
                  <td className="num"><strong>{fmtUsd(row.total)}</strong></td>
                  <td style={{ minWidth: 160 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                      <span>{(row.util * 100).toFixed(0)}%</span>
                      {row.util >= 1 && <span className="badge red">OVER LIMIT</span>}
                      {row.util >= 0.8 && row.util < 1 && <span className="badge amber">HIGH</span>}
                    </div>
                    <div className="bar-track">
                      <div className={`bar-fill ${cls}`} style={{ width: `${pct}%` }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="grid grid-2" style={{ marginTop: 18 }}>
        <div>
          <h2>Overdue Invoices</h2>
          <div className="card" style={{ padding: 0 }}>
            {overdue.length === 0 ? <div className="empty">No overdue invoices ✓</div> : (
              <table>
                <thead><tr><th>Ref</th><th>Client</th><th>Due</th><th className="num">Outstanding</th><th>Aging</th></tr></thead>
                <tbody>
                  {overdue.map((d) => {
                    const c = clients.find((x) => x.id === d.client_id);
                    const b = agingBucket(d.due_date);
                    return (
                      <tr key={d.id}>
                        <td><Link href={`/deliveries/${d.id}`}>{d.reference || `#${d.id}`}</Link></td>
                        <td>{c?.name}</td>
                        <td>{d.due_date?.slice(0,10)}</td>
                        <td className="num">{fmtUsd(outstandingUsd(d))}</td>
                        <td><span className={`badge ${b === "0-30" ? "amber" : "red"}`}>{b}</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div>
          <h2>Top Demurrage Events</h2>
          <div className="card" style={{ padding: 0 }}>
            {recentDemurrage.length === 0 ? <div className="empty">No demurrage incurred</div> : (
              <table>
                <thead><tr><th>Ref</th><th>Client</th><th className="num">Days</th><th className="num">Amount</th><th>Status</th></tr></thead>
                <tbody>
                  {recentDemurrage.map(({ d, calc }) => {
                    const c = clients.find((x) => x.id === d.client_id);
                    return (
                      <tr key={d.id}>
                        <td><Link href={`/deliveries/${d.id}`}>{d.reference || `#${d.id}`}</Link></td>
                        <td>{c?.name}</td>
                        <td className="num">{calc.demurrageDays}</td>
                        <td className="num">{fmtUsd(calc.amountUsd)}</td>
                        <td>{d.demurrage_billed
                          ? <span className="badge green">billed</span>
                          : <span className="badge amber">unbilled</span>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}
