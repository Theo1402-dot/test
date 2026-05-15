import { getDb } from "@/lib/db";
import { Doc, fmtUsd, fmtDate } from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

function bucket(due: string | null) {
  if (!due) return "no_due";
  const d = new Date(due.replace(" ", "T")).getTime();
  if (!isFinite(d)) return "no_due";
  const days = Math.floor((Date.now() - d) / 86400000);
  if (days < 0) return "current";
  if (days <= 30) return "0-30";
  if (days <= 60) return "31-60";
  if (days <= 90) return "61-90";
  return "90+";
}

export default function Aging() {
  const db = getDb();
  const docs = db.prepare(`
    SELECT d.*, c.name AS counterparty_name, e.code AS entity_code
    FROM documents d
    JOIN counterparties c ON c.id = d.counterparty_id
    JOIN entities e ON e.id = d.entity_id
    WHERE d.doc_type IN ('FINAL_INVOICE','STORAGE_INVOICE') AND d.status='issued'
    ORDER BY d.due_date ASC NULLS LAST
  `).all() as any[];

  const open = docs.map((d) => ({ ...d, outstanding: Math.max(0, d.amount_usd - d.paid_amount_usd), bucket: bucket(d.due_date) }))
    .filter((d) => d.outstanding > 0);

  const buckets: Record<string, number> = { current: 0, "0-30": 0, "31-60": 0, "61-90": 0, "90+": 0, no_due: 0 };
  for (const d of open) buckets[d.bucket] = (buckets[d.bucket] || 0) + d.outstanding;
  const total = open.reduce((s, d) => s + d.outstanding, 0);

  return (
    <>
      <h1>AR Aging</h1>
      <p className="muted">Outstanding final &amp; storage invoices, bucketed by days past due.</p>

      <div className="grid grid-4">
        <Kpi label="Total Outstanding" value={fmtUsd(total)} sub={`${open.length} invoices`} />
        <Kpi label="Current (not due)" value={fmtUsd(buckets.current)} />
        <Kpi label="0–30 overdue" value={fmtUsd(buckets["0-30"])} />
        <Kpi label="60+ overdue" value={fmtUsd((buckets["31-60"] || 0) + (buckets["61-90"] || 0) + (buckets["90+"] || 0))} />
      </div>

      <h2>Per counterparty</h2>
      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        <PerCounterparty open={open} />
      </div>

      <h2>All open invoices</h2>
      <div className="card" style={{ padding: 0 }}>
        {open.length === 0 ? <div className="empty">No outstanding invoices ✓</div> : (
          <table>
            <thead><tr>
              <th>Doc #</th><th>Type</th><th>Entity</th><th>Counterparty</th>
              <th>Issue</th><th>Due</th><th className="num">Amount</th><th className="num">Outstanding</th><th>Aging</th>
            </tr></thead>
            <tbody>
              {open.map((d) => {
                const cls = d.bucket === "current" ? "" : d.bucket === "0-30" ? "amber" : "red";
                return (
                  <tr key={d.id}>
                    <td><Link href={`/documents/${d.id}`}>{d.doc_no}</Link></td>
                    <td><span className="badge blue">{d.doc_type === "FINAL_INVOICE" ? "INV" : "STORAGE"}</span></td>
                    <td><span className="tag">{d.entity_code}</span></td>
                    <td>{d.counterparty_name}</td>
                    <td>{fmtDate(d.issue_date)}</td>
                    <td>{fmtDate(d.due_date)}</td>
                    <td className="num">{fmtUsd(d.amount_usd)}</td>
                    <td className="num">{fmtUsd(d.outstanding)}</td>
                    <td><span className={`badge ${cls}`}>{d.bucket}</span></td>
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

function PerCounterparty({ open }: { open: any[] }) {
  const grouped = new Map<number, { name: string; current: number; b0: number; b1: number; b2: number; b3: number; nodue: number; total: number }>();
  for (const d of open) {
    const g = grouped.get(d.counterparty_id) ?? { name: d.counterparty_name, current: 0, b0: 0, b1: 0, b2: 0, b3: 0, nodue: 0, total: 0 };
    if (d.bucket === "current") g.current += d.outstanding;
    else if (d.bucket === "0-30") g.b0 += d.outstanding;
    else if (d.bucket === "31-60") g.b1 += d.outstanding;
    else if (d.bucket === "61-90") g.b2 += d.outstanding;
    else if (d.bucket === "90+") g.b3 += d.outstanding;
    else g.nodue += d.outstanding;
    g.total += d.outstanding;
    grouped.set(d.counterparty_id, g);
  }
  const rows = Array.from(grouped.values()).sort((a, b) => b.total - a.total);
  if (rows.length === 0) return <div className="empty">No outstanding invoices.</div>;
  return (
    <table>
      <thead><tr>
        <th>Counterparty</th>
        <th className="num">Current</th>
        <th className="num">0–30</th>
        <th className="num">31–60</th>
        <th className="num">61–90</th>
        <th className="num">90+</th>
        <th className="num">No due</th>
        <th className="num">Total</th>
      </tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name}>
            <td>{r.name}</td>
            <td className="num">{fmtUsd(r.current)}</td>
            <td className="num">{fmtUsd(r.b0)}</td>
            <td className="num">{fmtUsd(r.b1)}</td>
            <td className="num">{fmtUsd(r.b2)}</td>
            <td className="num" style={{ color: r.b3 > 0 ? "var(--red)" : undefined }}>{fmtUsd(r.b3)}</td>
            <td className="num">{fmtUsd(r.nodue)}</td>
            <td className="num"><strong>{fmtUsd(r.total)}</strong></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}
