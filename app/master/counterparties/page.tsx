import { getDb } from "@/lib/db";
import { Counterparty, counterpartyExposure, fmtUsd } from "@/lib/calc";
import Link from "next/link";
import { saveCounterparty } from "../actions";

export const dynamic = "force-dynamic";

export default function CounterpartiesPage() {
  const expo = counterpartyExposure();
  return (
    <>
      <div className="toolbar">
        <h1>Counterparties</h1>
        <Link href="/master/counterparties/new" className="btn">+ New Counterparty</Link>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Name</th><th>Country</th>
              <th className="num">Allowed O/A</th>
              <th className="num">O/A In Use</th>
              <th className="num">Remaining</th>
              <th>Utilisation</th>
              <th className="num">Open Deals</th>
              <th>Default Payment</th>
            </tr>
          </thead>
          <tbody>
            {expo.map((row) => {
              const pct = Math.min(100, row.utilisation * 100);
              const cls = row.utilisation >= 1 ? "red" : row.utilisation >= 0.8 ? "amber" : "";
              return (
                <tr key={row.counterparty.id}>
                  <td><Link href={`/master/counterparties/${row.counterparty.id}`}>{row.counterparty.name}</Link></td>
                  <td className="muted">{row.counterparty.country ?? "—"}</td>
                  <td className="num">{fmtUsd(row.counterparty.allowed_oa_usd)}</td>
                  <td className="num">{fmtUsd(row.oaInUseUsd)}</td>
                  <td className="num">{fmtUsd(row.remainingOaUsd)}</td>
                  <td style={{ minWidth: 140 }}>
                    <div style={{ fontSize: 11 }}>{(row.utilisation*100).toFixed(0)}%</div>
                    <div className="bar-track"><div className={`bar-fill ${cls}`} style={{ width: `${pct}%` }} /></div>
                  </td>
                  <td className="num">{row.openDeals}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{row.counterparty.default_payment_term ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
