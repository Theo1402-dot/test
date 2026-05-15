import { getDb } from "@/lib/db";
import { Deal, Loading, Payment, dealMetrics, fmtUsd, fmtNum, fmtDate } from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

const STATUS: Record<string, string> = { draft: "gray", open: "blue", closed: "green", cancelled: "red" };

export default function Deals({ searchParams }: {
  searchParams: { status?: string; counterparty?: string; entity?: string; type?: string; product?: string };
}) {
  const db = getDb();
  const where: string[] = []; const params: any[] = [];
  if (searchParams.status) { where.push("d.status = ?"); params.push(searchParams.status); }
  if (searchParams.counterparty) { where.push("d.counterparty_id = ?"); params.push(Number(searchParams.counterparty)); }
  if (searchParams.entity) { where.push("d.entity_id = ?"); params.push(Number(searchParams.entity)); }
  if (searchParams.type) { where.push("d.type = ?"); params.push(searchParams.type); }
  if (searchParams.product) { where.push("d.product_id = ?"); params.push(Number(searchParams.product)); }

  const sql = `
    SELECT d.*, c.name AS counterparty_name, p.code AS product_code, e.code AS entity_code
    FROM deals d
    JOIN counterparties c ON c.id = d.counterparty_id
    JOIN products p ON p.id = d.product_id
    JOIN entities e ON e.id = d.entity_id
    ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
    ORDER BY d.deal_date DESC, d.id DESC
  `;
  const deals = db.prepare(sql).all(...params) as (Deal & { counterparty_name: string; product_code: string; entity_code: string })[];
  const loadings = db.prepare("SELECT * FROM deal_loadings").all() as Loading[];
  const payments = db.prepare("SELECT * FROM payments").all() as Payment[];

  const counterparties = db.prepare("SELECT id, name FROM counterparties ORDER BY name").all() as { id: number; name: string }[];
  const entities = db.prepare("SELECT id, code FROM entities ORDER BY code").all() as { id: number; code: string }[];
  const products = db.prepare("SELECT id, code FROM products ORDER BY code").all() as { id: number; code: string }[];

  return (
    <>
      <div className="toolbar">
        <h1>Deals</h1>
        <Link href="/deals/new" className="btn">+ New Deal</Link>
      </div>

      <form className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          <label>Entity
            <select name="entity" defaultValue={searchParams.entity ?? ""}>
              <option value="">All</option>
              {entities.map((e) => <option key={e.id} value={e.id}>{e.code}</option>)}
            </select>
          </label>
          <label>Type
            <select name="type" defaultValue={searchParams.type ?? ""}>
              <option value="">All</option>
              <option value="PURCH">Purchase</option>
              <option value="SALE">Sale</option>
            </select>
          </label>
          <label>Product
            <select name="product" defaultValue={searchParams.product ?? ""}>
              <option value="">All</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.code}</option>)}
            </select>
          </label>
          <label>Status
            <select name="status" defaultValue={searchParams.status ?? ""}>
              <option value="">All</option>
              <option value="draft">Draft</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
        </div>
        <div className="row">
          <label style={{ gridColumn: "span 3" }}>Counterparty
            <select name="counterparty" defaultValue={searchParams.counterparty ?? ""}>
              <option value="">All</option>
              {counterparties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <div style={{ alignSelf: "end" }}>
            <button type="submit">Filter</button>{" "}
            <Link className="btn secondary" href="/deals">Reset</Link>
          </div>
        </div>
      </form>

      <div className="card" style={{ padding: 0 }}>
        {deals.length === 0 ? <div className="empty">No deals match the filter.</div> : (
          <table>
            <thead>
              <tr>
                <th>Deal #</th><th>Date</th><th>Entity</th><th>Counterparty</th>
                <th>Type</th><th>Product</th><th>Incoterm</th>
                <th className="num">Qty m³</th><th className="num">Loaded</th><th className="num">Bal.</th>
                <th className="num">Price</th><th className="num">Amount</th>
                <th className="num">Paid</th><th className="num">Funds Bal.</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {deals.map((d) => {
                const m = dealMetrics(d, loadings.filter((l) => l.deal_id === d.id), payments.filter((p) => p.deal_id === d.id));
                return (
                  <tr key={d.id}>
                    <td><Link href={`/deals/${d.id}`}>{d.deal_no}</Link></td>
                    <td>{fmtDate(d.deal_date)}</td>
                    <td><span className="tag">{d.entity_code}</span></td>
                    <td>{d.counterparty_name}</td>
                    <td><span className={`badge ${d.type === "SALE" ? "green" : "blue"}`}>{d.type}</span></td>
                    <td><span className="tag">{d.product_code}</span></td>
                    <td className="muted" style={{ fontSize: 12 }}>{d.incoterm}</td>
                    <td className="num">{fmtNum(d.qty_m3, 0)}</td>
                    <td className="num">{fmtNum(m.loadedQtyM3, 0)}</td>
                    <td className="num">{fmtNum(m.balanceQtyM3, 0)}</td>
                    <td className="num">{fmtUsd(d.price_usd_per_m3, 2)}</td>
                    <td className="num">{fmtUsd(m.dealAmountUsd)}</td>
                    <td className="num">{fmtUsd(m.paidUsd)}</td>
                    <td className="num" style={{ color: m.fundsBalanceUsd < 0 ? "var(--red)" : undefined }}>{fmtUsd(m.fundsBalanceUsd)}</td>
                    <td><span className={`badge ${STATUS[d.status]}`}>{d.status}</span></td>
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
