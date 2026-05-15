import { getDb } from "@/lib/db";
import { ClientRow, DeliveryRow, computeDemurrage, fmtNum, fmtUsd } from "@/lib/calc";
import Link from "next/link";
import Calculator from "./Calculator";

export const dynamic = "force-dynamic";

export default function DemurrageReport() {
  const db = getDb();
  const clients = db.prepare("SELECT * FROM clients ORDER BY name").all() as ClientRow[];
  const deliveries = db.prepare("SELECT * FROM deliveries ORDER BY COALESCE(arrival_date, created_at) DESC")
    .all() as DeliveryRow[];

  const rows = deliveries.map((d) => ({ d, calc: computeDemurrage(d) }))
    .filter((x) => x.calc.amountUsd > 0);

  const totalBilled = rows.filter((x) => x.d.demurrage_billed).reduce((s, x) => s + x.calc.amountUsd, 0);
  const totalUnbilled = rows.filter((x) => !x.d.demurrage_billed).reduce((s, x) => s + x.calc.amountUsd, 0);

  const perClient = clients.map((c) => {
    const list = rows.filter((x) => x.d.client_id === c.id);
    return {
      client: c,
      count: list.length,
      total: list.reduce((s, x) => s + x.calc.amountUsd, 0),
      unbilled: list.filter((x) => !x.d.demurrage_billed).reduce((s, x) => s + x.calc.amountUsd, 0),
    };
  }).filter((x) => x.total > 0).sort((a, b) => b.total - a.total);

  return (
    <>
      <h1>Demurrage</h1>

      <div className="grid grid-4">
        <div className="card kpi">
          <div className="label">Total demurrage incurred</div>
          <div className="value">{fmtUsd(totalBilled + totalUnbilled)}</div>
          <div className="sub">{rows.length} truck(s) over laytime</div>
        </div>
        <div className="card kpi">
          <div className="label">Unbilled (recoverable)</div>
          <div className="value" style={{ color: "var(--amber)" }}>{fmtUsd(totalUnbilled)}</div>
        </div>
        <div className="card kpi">
          <div className="label">Already billed</div>
          <div className="value">{fmtUsd(totalBilled)}</div>
        </div>
        <div className="card kpi">
          <div className="label">Avg days over</div>
          <div className="value">{rows.length
            ? fmtNum(rows.reduce((s, x) => s + x.calc.demurrageDays, 0) / rows.length, 1)
            : "—"}</div>
        </div>
      </div>

      <h2>Quick calculator</h2>
      <Calculator />

      <h2>By client</h2>
      <div className="card" style={{ padding: 0 }}>
        {perClient.length === 0 ? <div className="empty">No demurrage incurred to date.</div> : (
          <table>
            <thead>
              <tr><th>Client</th><th className="num">Events</th><th className="num">Total</th><th className="num">Unbilled</th></tr>
            </thead>
            <tbody>
              {perClient.map((row) => (
                <tr key={row.client.id}>
                  <td><Link href={`/clients/${row.client.id}`}>{row.client.name}</Link></td>
                  <td className="num">{row.count}</td>
                  <td className="num">{fmtUsd(row.total)}</td>
                  <td className="num" style={{ color: row.unbilled > 0 ? "var(--amber)" : undefined }}>
                    {fmtUsd(row.unbilled)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>All demurrage events</h2>
      <div className="card" style={{ padding: 0 }}>
        {rows.length === 0 ? <div className="empty">No demurrage events.</div> : (
          <table>
            <thead>
              <tr>
                <th>Ref</th><th>Client</th><th>Truck</th>
                <th>Arrival</th><th>Departure</th>
                <th className="num">Hours at site</th>
                <th className="num">Laytime</th>
                <th className="num">Days</th>
                <th className="num">Rate</th>
                <th className="num">Amount</th>
                <th>Billed?</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ d, calc }) => {
                const c = clients.find((x) => x.id === d.client_id);
                return (
                  <tr key={d.id}>
                    <td><Link href={`/deliveries/${d.id}`}>{d.reference || `#${d.id}`}</Link></td>
                    <td>{c?.name}</td>
                    <td className="muted">{d.truck_plate ?? "—"}</td>
                    <td>{d.arrival_date?.slice(0,16)}</td>
                    <td>{d.departure_date?.slice(0,16)}</td>
                    <td className="num">{fmtNum(calc.hoursAtSite, 1)}</td>
                    <td className="num">{fmtNum(d.laytime_hours, 1)}</td>
                    <td className="num">{calc.demurrageDays}</td>
                    <td className="num">{fmtUsd(d.demurrage_usd_per_day)}</td>
                    <td className="num"><strong>{fmtUsd(calc.amountUsd)}</strong></td>
                    <td>{d.demurrage_billed
                      ? <span className="badge green">yes</span>
                      : <span className="badge amber">no</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
