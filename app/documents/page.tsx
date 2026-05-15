import { getDb } from "@/lib/db";
import { Doc, fmtUsd, fmtDate } from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

const TYPE: Record<string, string> = {
  PFI: "blue", FINAL_INVOICE: "green", STORAGE_INVOICE: "purple",
};
const STATUS: Record<string, string> = {
  draft: "gray", issued: "amber", paid: "green", cancelled: "red",
};

export default function Documents({ searchParams }: {
  searchParams: { type?: string; status?: string; entity?: string };
}) {
  const db = getDb();
  const where: string[] = []; const params: any[] = [];
  if (searchParams.type) { where.push("d.doc_type = ?"); params.push(searchParams.type); }
  if (searchParams.status) { where.push("d.status = ?"); params.push(searchParams.status); }
  if (searchParams.entity) { where.push("d.entity_id = ?"); params.push(Number(searchParams.entity)); }

  const rows = db.prepare(`
    SELECT d.*, e.code AS entity_code, c.name AS counterparty_name,
           dl.deal_no AS deal_no, b.label AS bank_label
    FROM documents d
    LEFT JOIN entities e ON e.id = d.entity_id
    LEFT JOIN counterparties c ON c.id = d.counterparty_id
    LEFT JOIN deals dl ON dl.id = d.deal_id
    LEFT JOIN banks b ON b.id = d.bank_id
    ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
    ORDER BY d.issue_date DESC, d.id DESC
  `).all(...params) as any[];

  const entities = db.prepare("SELECT id, code FROM entities ORDER BY code").all() as { id: number; code: string }[];

  return (
    <>
      <div className="toolbar">
        <h1>Documents</h1>
        <div className="row-actions">
          <Link href="/documents/new?type=PFI" className="btn">+ PFI</Link>
          <Link href="/documents/new?type=FINAL_INVOICE" className="btn">+ Final Invoice</Link>
          <Link href="/documents/new?type=STORAGE_INVOICE" className="btn">+ Storage Invoice</Link>
        </div>
      </div>

      <form className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          <label>Type
            <select name="type" defaultValue={searchParams.type ?? ""}>
              <option value="">All</option>
              <option value="PFI">PFI</option>
              <option value="FINAL_INVOICE">Final Invoice</option>
              <option value="STORAGE_INVOICE">Storage Invoice</option>
            </select>
          </label>
          <label>Status
            <select name="status" defaultValue={searchParams.status ?? ""}>
              <option value="">All</option>
              <option value="draft">Draft</option>
              <option value="issued">Issued</option>
              <option value="paid">Paid</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <label>Entity
            <select name="entity" defaultValue={searchParams.entity ?? ""}>
              <option value="">All</option>
              {entities.map((e) => <option key={e.id} value={e.id}>{e.code}</option>)}
            </select>
          </label>
          <div style={{ alignSelf: "end" }}>
            <button type="submit">Filter</button>{" "}
            <Link className="btn secondary" href="/documents">Reset</Link>
          </div>
        </div>
      </form>

      <div className="card" style={{ padding: 0 }}>
        {rows.length === 0 ? <div className="empty">No documents yet.</div> : (
          <table>
            <thead><tr>
              <th>#</th><th>Type</th><th>Entity</th><th>Counterparty</th>
              <th>Linked Deal</th><th>Issue</th><th>Due</th>
              <th className="num">Amount</th><th className="num">Paid</th><th>Status</th>
            </tr></thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <td><Link href={`/documents/${d.id}`}>{d.doc_no}</Link></td>
                  <td><span className={`badge ${TYPE[d.doc_type]}`}>{d.doc_type}</span></td>
                  <td><span className="tag">{d.entity_code}</span></td>
                  <td>{d.counterparty_name}</td>
                  <td>{d.deal_no ? <Link href={`/deals/${d.deal_id}`}>{d.deal_no}</Link> : <span className="muted">—</span>}</td>
                  <td>{fmtDate(d.issue_date)}</td>
                  <td>{fmtDate(d.due_date)}</td>
                  <td className="num">{fmtUsd(d.amount_usd)}</td>
                  <td className="num">{fmtUsd(d.paid_amount_usd)}</td>
                  <td><span className={`badge ${STATUS[d.status]}`}>{d.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
