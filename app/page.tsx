import { getDb } from "@/lib/db";
import {
  Deal, Loading, Payment, Doc,
  dealMetrics, counterpartyExposure, locationPositions,
  fmtUsd, fmtNum,
} from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function Dashboard() {
  const db = getDb();
  const deals = db.prepare("SELECT * FROM deals").all() as Deal[];
  const loadings = db.prepare("SELECT * FROM deal_loadings").all() as Loading[];
  const payments = db.prepare("SELECT * FROM payments").all() as Payment[];
  const documents = db.prepare("SELECT * FROM documents").all() as Doc[];
  const expo = counterpartyExposure();
  const positions = locationPositions();

  const open = deals.filter((d) => d.status === "open" || d.status === "draft");
  const openValue = open.reduce((s, d) => s + d.price_usd_per_m3 * d.qty_m3, 0);
  let totalOaInUse = 0, totalLoadedM3 = 0, totalRemainingM3 = 0;
  for (const d of open) {
    const m = dealMetrics(d, loadings.filter((l) => l.deal_id === d.id), payments.filter((p) => p.deal_id === d.id));
    totalLoadedM3 += m.loadedQtyM3;
    totalRemainingM3 += m.balanceQtyM3;
    if (d.type === "SALE") totalOaInUse += m.oaInUseUsd;
  }

  const overLimit = expo.filter((x) => x.utilisation >= 1 && x.counterparty.allowed_oa_usd > 0);
  const highUtil  = expo.filter((x) => x.utilisation >= 0.8 && x.utilisation < 1);

  const draftDocs = documents.filter((d) => d.status === "draft").length;
  const unpaidInvoices = documents.filter((d) => d.doc_type !== "PFI" && d.status === "issued");
  const unpaidAmount = unpaidInvoices.reduce((s, d) => s + Math.max(0, d.amount_usd - d.paid_amount_usd), 0);

  return (
    <>
      <h1>Dashboard</h1>

      <div className="grid grid-4">
        <Kpi label="Open Deals" value={String(open.length)} sub={`${fmtUsd(openValue)} notional`} />
        <Kpi label="O/A In Use (Sales)" value={fmtUsd(totalOaInUse)} sub={`${overLimit.length} clients over limit`} />
        <Kpi label="Open Position Loaded" value={`${fmtNum(totalLoadedM3, 0)} m³`} sub={`${fmtNum(totalRemainingM3, 0)} m³ remaining`} />
        <Kpi label="Unpaid Invoices" value={fmtUsd(unpaidAmount)} sub={`${unpaidInvoices.length} open · ${draftDocs} draft docs`} />
      </div>

      <h2>Counterparty Exposure</h2>
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Counterparty</th>
              <th className="num">Allowed O/A</th>
              <th className="num">O/A in Use</th>
              <th className="num">Remaining</th>
              <th>Utilisation</th>
              <th className="num">Open Deals</th>
            </tr>
          </thead>
          <tbody>
            {expo.filter((x) => x.counterparty.allowed_oa_usd > 0 || x.oaInUseUsd > 0 || x.openDeals > 0)
              .sort((a, b) => b.utilisation - a.utilisation)
              .map((row) => {
              const pct = Math.min(100, row.utilisation * 100);
              const cls = row.utilisation >= 1 ? "red" : row.utilisation >= 0.8 ? "amber" : "";
              return (
                <tr key={row.counterparty.id}>
                  <td><Link href={`/master/counterparties/${row.counterparty.id}`}>{row.counterparty.name}</Link>
                    <div className="muted" style={{ fontSize: 11 }}>{row.counterparty.country ?? ""}</div></td>
                  <td className="num">{fmtUsd(row.counterparty.allowed_oa_usd)}</td>
                  <td className="num">{fmtUsd(row.oaInUseUsd)}</td>
                  <td className="num">{fmtUsd(row.remainingOaUsd)}</td>
                  <td style={{ minWidth: 180 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                      <span>{(row.utilisation * 100).toFixed(0)}%</span>
                      {row.utilisation >= 1 && <span className="badge red">OVER LIMIT</span>}
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

      <h2>Position by Location & Product</h2>
      <div className="card" style={{ padding: 0 }}>
        {positions.length === 0 ? <div className="empty">No positions yet.</div> : (
          <table>
            <thead>
              <tr>
                <th>Location</th><th>Product</th>
                <th className="num">Purchased</th>
                <th className="num">Sold</th>
                <th className="num">Unsold</th>
                <th className="num">Loaded (P)</th>
                <th className="num">Loaded (S)</th>
                <th className="num">Physical Bal.</th>
                <th className="num">In Tank Unsold</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={`${p.locationCode}-${p.productCode}`}>
                  <td>{p.locationName} <span className="tag">{p.locationCode}</span></td>
                  <td><span className={`badge ${p.productCode === "AGO" ? "amber" : p.productCode === "PMS" ? "purple" : "blue"}`}>{p.productCode}</span></td>
                  <td className="num">{fmtNum(p.purchasedM3, 0)}</td>
                  <td className="num">{fmtNum(p.soldM3, 0)}</td>
                  <td className="num">{fmtNum(p.unsoldM3, 0)}</td>
                  <td className="num">{fmtNum(p.loadedPurchM3, 0)}</td>
                  <td className="num">{fmtNum(p.loadedSaleM3, 0)}</td>
                  <td className="num"><strong>{fmtNum(p.physicalBalanceM3, 0)}</strong></td>
                  <td className="num">{fmtNum(p.inTankUnsoldM3, 0)}</td>
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
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}
