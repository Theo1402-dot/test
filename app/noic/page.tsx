import { getDb } from "@/lib/db";
import { fmtUsd, fmtNum, fmtDate } from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function NoicSummary() {
  const db = getDb();

  // Deals routed through Msasa or Feruka — by incoterm or by loading.noic_terminal
  const deals = db.prepare(`
    SELECT d.*, c.name AS counterparty_name, p.code AS product_code, l.code AS location_code
    FROM deals d
    JOIN counterparties c ON c.id = d.counterparty_id
    JOIN products p ON p.id = d.product_id
    LEFT JOIN locations l ON l.id = d.location_id
    WHERE d.incoterm LIKE 'ITT %' OR d.incoterm LIKE 'FCA MSASA' OR d.incoterm LIKE 'FCA FERUKA'
       OR d.id IN (SELECT deal_id FROM deal_loadings WHERE noic_terminal IS NOT NULL)
    ORDER BY d.deal_date DESC
  `).all() as any[];

  const totals: Record<string, { qty: number; deals: number; fee: number; paid: number }> = {
    MSASA: { qty: 0, deals: 0, fee: 0, paid: 0 },
    FERUKA: { qty: 0, deals: 0, fee: 0, paid: 0 },
  };

  for (const d of deals) {
    const term = (d.incoterm || "").toUpperCase();
    const key = term.includes("MSASA") ? "MSASA" : term.includes("FERUKA") ? "FERUKA" : null;
    if (key) {
      totals[key].deals += 1;
      totals[key].qty += d.qty_m3;
    }
  }

  // Aggregate NOIC fees from loadings
  const fees = db.prepare(`
    SELECT noic_terminal AS term, SUM(noic_fee_usd) AS fee, SUM(noic_paid_usd) AS paid
    FROM deal_loadings WHERE noic_terminal IS NOT NULL GROUP BY noic_terminal
  `).all() as any[];
  for (const f of fees) {
    const key = (f.term || "").toUpperCase();
    if (totals[key]) {
      totals[key].fee += f.fee || 0;
      totals[key].paid += f.paid || 0;
    }
  }

  return (
    <>
      <h1>NOIC Summary</h1>
      <p className="muted">Deals routed via the Msasa and Feruka terminals (Beira → Msasa / Beira → Feruka, FCA Msasa / FCA Feruka, ITT). NOIC fees track terminal/pipeline charges per route.</p>

      <div className="grid grid-4">
        <Kpi label="Deals via MSASA" value={String(totals.MSASA.deals)} sub={`${fmtNum(totals.MSASA.qty, 0)} m³`} />
        <Kpi label="Deals via FERUKA" value={String(totals.FERUKA.deals)} sub={`${fmtNum(totals.FERUKA.qty, 0)} m³`} />
        <Kpi label="NOIC fees billed" value={fmtUsd(totals.MSASA.fee + totals.FERUKA.fee)} />
        <Kpi label="NOIC fees outstanding" value={fmtUsd((totals.MSASA.fee + totals.FERUKA.fee) - (totals.MSASA.paid + totals.FERUKA.paid))} />
      </div>

      <h2>NOIC deals</h2>
      <div className="card" style={{ padding: 0 }}>
        {deals.length === 0 ? <div className="empty">No NOIC-routed deals.</div> : (
          <table>
            <thead><tr>
              <th>Deal #</th><th>Date</th><th>Counterparty</th><th>Type</th>
              <th>Product</th><th>Incoterm</th><th className="num">Qty m³</th><th>Status</th>
            </tr></thead>
            <tbody>
              {deals.slice(0, 200).map((d) => (
                <tr key={d.id}>
                  <td><Link href={`/deals/${d.id}`}>{d.deal_no}</Link></td>
                  <td>{fmtDate(d.deal_date)}</td>
                  <td>{d.counterparty_name}</td>
                  <td><span className={`badge ${d.type === "SALE" ? "green" : "blue"}`}>{d.type}</span></td>
                  <td><span className="tag">{d.product_code}</span></td>
                  <td className="muted" style={{ fontSize: 12 }}>{d.incoterm}</td>
                  <td className="num">{fmtNum(d.qty_m3, 0)}</td>
                  <td><span className={`badge ${statusColor(d.status)}`}>{d.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function statusColor(s: string) {
  return ({ draft: "gray", open: "blue", closed: "green", cancelled: "red" } as Record<string, string>)[s] ?? "gray";
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}
