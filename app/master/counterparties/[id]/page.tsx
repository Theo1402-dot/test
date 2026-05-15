import { getDb } from "@/lib/db";
import { Counterparty, FrameContract, Deal, Loading, Payment, dealMetrics, fmtUsd, fmtNum, fmtDate } from "@/lib/calc";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CounterpartyForm } from "../CounterpartyForm";
import { deleteCounterparty, saveFrameContract } from "../../actions";

export const dynamic = "force-dynamic";

export default function CounterpartyDetail({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const db = getDb();
  const cp = db.prepare("SELECT * FROM counterparties WHERE id=?").get(id) as Counterparty | undefined;
  if (!cp) notFound();
  const fc = db.prepare("SELECT * FROM frame_contracts WHERE counterparty_id=?").get(id) as FrameContract | undefined;
  const deals = db.prepare("SELECT * FROM deals WHERE counterparty_id=? ORDER BY deal_date DESC").all(id) as Deal[];
  const allLoadings = db.prepare("SELECT * FROM deal_loadings WHERE deal_id IN (SELECT id FROM deals WHERE counterparty_id=?)").all(id) as Loading[];
  const allPayments = db.prepare("SELECT * FROM payments WHERE deal_id IN (SELECT id FROM deals WHERE counterparty_id=?)").all(id) as Payment[];

  let oaInUse = 0, totalLoadedM3 = 0, totalRemainingM3 = 0;
  for (const d of deals) {
    const m = dealMetrics(d, allLoadings.filter((l) => l.deal_id === d.id), allPayments.filter((p) => p.deal_id === d.id));
    if (d.status === "open" || d.status === "draft") {
      if (d.type === "SALE") oaInUse += m.oaInUseUsd;
      totalLoadedM3 += m.loadedQtyM3;
      totalRemainingM3 += m.balanceQtyM3;
    }
  }
  const util = cp.allowed_oa_usd > 0 ? oaInUse / cp.allowed_oa_usd : 0;

  return (
    <>
      <div className="toolbar">
        <h1>{cp.name} <span className="pill">{cp.country ?? ""}</span></h1>
        <div className="row-actions">
          <Link href="/master/counterparties" className="btn secondary">← Back</Link>
          <Link href={`/deals/new?counterparty_id=${cp.id}`} className="btn">+ New deal</Link>
        </div>
      </div>

      <div className="grid grid-4">
        <Kpi label="Allowed O/A" value={fmtUsd(cp.allowed_oa_usd)} />
        <Kpi label="O/A in Use" value={fmtUsd(oaInUse)} sub={`${(util*100).toFixed(0)}% utilisation`} />
        <Kpi label="Loaded (open deals)" value={`${fmtNum(totalLoadedM3,0)} m³`} />
        <Kpi label="Remaining to load" value={`${fmtNum(totalRemainingM3,0)} m³`} />
      </div>

      <h2>Counterparty details</h2>
      <CounterpartyForm cp={cp} />

      <h2>Frame contract</h2>
      <form action={saveFrameContract.bind(null, cp.id)} className="card inline">
        <div className="row">
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <input type="checkbox" name="itt_deals" defaultChecked={fc?.itt_deals === 1} /> ITT deals
          </label>
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <input type="checkbox" name="fca_deals" defaultChecked={fc?.fca_deals === 1} /> FCA deals
          </label>
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <input type="checkbox" name="ddu_deals" defaultChecked={fc?.ddu_deals === 1} /> DDU deals
          </label>
          <label>Truck Demurrage (USD/day)<input type="number" name="truck_dem_usd_per_day" defaultValue={fc?.truck_dem_usd_per_day ?? ""} /></label>
        </div>
        <div className="row">
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <input type="checkbox" name="ppmt" defaultChecked={fc?.ppmt === 1} /> PPMT allowed
          </label>
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <input type="checkbox" name="oa" defaultChecked={fc?.oa === 1} /> O/A allowed
          </label>
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <input type="checkbox" name="sblc" defaultChecked={fc?.sblc === 1} /> SBLC
          </label>
          <label>Date Signed<input type="date" name="date_signed" defaultValue={fc?.date_signed?.slice(0,10) ?? ""} /></label>
        </div>
        <div className="row">
          <label>Expiry<input type="date" name="expiry_date" defaultValue={fc?.expiry_date?.slice(0,10) ?? ""} /></label>
          <label style={{ gridColumn: "span 3" }}>Notes<input name="notes" defaultValue={fc?.notes ?? ""} /></label>
        </div>
        <div><button type="submit">Save frame contract</button></div>
      </form>

      <h2>Deals</h2>
      <div className="card" style={{ padding: 0 }}>
        {deals.length === 0 ? <div className="empty">No deals.</div> : (
          <table>
            <thead><tr><th>Deal #</th><th>Date</th><th>Type</th><th>Product</th><th>Incoterm</th>
              <th className="num">Qty m³</th><th className="num">Price</th><th className="num">Amount</th>
              <th className="num">Loaded</th><th>Status</th></tr></thead>
            <tbody>
              {deals.map((d) => {
                const m = dealMetrics(d, allLoadings.filter((l) => l.deal_id === d.id), allPayments.filter((p) => p.deal_id === d.id));
                return (
                  <tr key={d.id}>
                    <td><Link href={`/deals/${d.id}`}>{d.deal_no}</Link></td>
                    <td>{fmtDate(d.deal_date)}</td>
                    <td><span className={`badge ${d.type === "SALE" ? "green" : "blue"}`}>{d.type}</span></td>
                    <td><span className="tag">{(db.prepare("SELECT code FROM products WHERE id=?").get(d.product_id) as any).code}</span></td>
                    <td className="muted" style={{ fontSize: 12 }}>{d.incoterm}</td>
                    <td className="num">{fmtNum(d.qty_m3, 0)}</td>
                    <td className="num">{fmtUsd(d.price_usd_per_m3, 2)}</td>
                    <td className="num">{fmtUsd(m.dealAmountUsd)}</td>
                    <td className="num">{fmtNum(m.loadedQtyM3, 0)}</td>
                    <td>{statusBadge(d.status)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ marginTop: 12 }}>
        <form action={deleteCounterparty.bind(null, cp.id)}><button className="btn danger">Delete counterparty</button></form>
      </div>
    </>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div>{sub && <div className="sub">{sub}</div>}</div>;
}
function statusBadge(s: string) {
  const map: Record<string, string> = { draft: "gray", open: "blue", closed: "green", cancelled: "red" };
  return <span className={`badge ${map[s] ?? "gray"}`}>{s}</span>;
}
