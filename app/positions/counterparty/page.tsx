import { counterpartyExposure, fmtUsd, fmtNum } from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function ByCounterparty() {
  const expo = counterpartyExposure();

  const totalOaUsed = expo.reduce((s, x) => s + x.oaInUseUsd, 0);
  const totalAllowed = expo.reduce((s, x) => s + x.counterparty.allowed_oa_usd, 0);
  const overLimit = expo.filter((x) => x.utilisation >= 1 && x.counterparty.allowed_oa_usd > 0);

  return (
    <>
      <h1>By Counterparty</h1>

      <div className="grid grid-4">
        <Kpi label="Allowed O/A (total)" value={fmtUsd(totalAllowed)} />
        <Kpi label="O/A In Use" value={fmtUsd(totalOaUsed)} />
        <Kpi label="Remaining O/A" value={fmtUsd(totalAllowed - totalOaUsed)} />
        <Kpi label="Counterparties Over Limit" value={String(overLimit.length)} />
      </div>

      <div className="card" style={{ padding: 0, marginTop: 16 }}>
        <table>
          <thead>
            <tr>
              <th>Counterparty</th><th>Country</th>
              <th className="num">Qty balance (m³)</th>
              <th className="num">USD balance owed</th>
              <th className="num">Allowed O/A</th>
              <th className="num">In Use</th>
              <th className="num">Remaining</th>
              <th>Utilisation</th>
              <th className="num">Open deals</th>
            </tr>
          </thead>
          <tbody>
            {expo
              .sort((a, b) => b.utilisation - a.utilisation || b.oaInUseUsd - a.oaInUseUsd)
              .map((row) => {
              const pct = Math.min(100, row.utilisation * 100);
              const cls = row.utilisation >= 1 ? "red" : row.utilisation >= 0.8 ? "amber" : "";
              return (
                <tr key={row.counterparty.id}>
                  <td><Link href={`/master/counterparties/${row.counterparty.id}`}>{row.counterparty.name}</Link></td>
                  <td className="muted">{row.counterparty.country ?? "—"}</td>
                  <td className="num">{fmtNum(row.qtyBalanceM3, 0)}</td>
                  <td className="num">{fmtUsd(row.usdBalance)}</td>
                  <td className="num">{fmtUsd(row.counterparty.allowed_oa_usd)}</td>
                  <td className="num">{fmtUsd(row.oaInUseUsd)}</td>
                  <td className="num">{fmtUsd(row.remainingOaUsd)}</td>
                  <td style={{ minWidth: 160 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                      <span>{(row.utilisation*100).toFixed(0)}%</span>
                      {row.utilisation >= 1 && <span className="badge red">OVER</span>}
                      {row.utilisation >= 0.8 && row.utilisation < 1 && <span className="badge amber">HIGH</span>}
                    </div>
                    <div className="bar-track"><div className={`bar-fill ${cls}`} style={{ width: `${pct}%` }} /></div>
                  </td>
                  <td className="num">{row.openDeals}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div></div>;
}
