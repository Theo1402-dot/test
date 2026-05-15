import { getDb } from "@/lib/db";
import {
  ClientRow, DeliveryRow,
  accruedDemurrageUsd, agingBucket, cargoValue, computeDemurrage,
  fmtUsd, inTransitValueUsd, outstandingUsd,
} from "@/lib/calc";
import Link from "next/link";
import { notFound } from "next/navigation";
import { deleteClient, updateClient } from "../actions";

export const dynamic = "force-dynamic";

const STATUS_COLORS: Record<string, string> = {
  in_transit: "blue", delivered: "purple", invoiced: "amber", paid: "green", cancelled: "gray",
};

export default function ClientDetail({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const db = getDb();
  const c = db.prepare("SELECT * FROM clients WHERE id = ?").get(id) as ClientRow | undefined;
  if (!c) notFound();
  const dels = db.prepare("SELECT * FROM deliveries WHERE client_id = ? ORDER BY COALESCE(loading_date, created_at) DESC")
    .all(id) as DeliveryRow[];

  const ar = dels.reduce((s, d) => s + outstandingUsd(d), 0);
  const inT = dels.reduce((s, d) => s + inTransitValueUsd(d), 0);
  const dem = dels.reduce((s, d) => s + accruedDemurrageUsd(d), 0);
  const total = ar + inT;
  const util = c.credit_limit_usd > 0 ? total / c.credit_limit_usd : 0;
  const headroom = c.credit_limit_usd - total;

  const buckets: Record<string, number> = { current: 0, "0-30": 0, "31-60": 0, "61-90": 0, "90+": 0 };
  for (const d of dels) {
    if (d.status === "invoiced") {
      const b = agingBucket(d.due_date);
      if (b in buckets) buckets[b] += outstandingUsd(d);
    }
  }

  const update = updateClient.bind(null, c.id);
  const del = deleteClient.bind(null, c.id);

  return (
    <>
      <div className="toolbar">
        <h1>{c.name} <span className="pill">{c.country ?? ""}</span></h1>
        <Link href="/clients" className="btn secondary">← All clients</Link>
      </div>

      <div className="grid grid-4">
        <Kpi label="AR Outstanding" value={fmtUsd(ar)} />
        <Kpi label="In-Transit" value={fmtUsd(inT)} />
        <Kpi label="Demurrage (unbilled)" value={fmtUsd(dem)} />
        <Kpi label={headroom < 0 ? "Over Limit By" : "Available Credit"}
             value={fmtUsd(Math.abs(headroom))}
             sub={`${(util*100).toFixed(0)}% of ${fmtUsd(c.credit_limit_usd)}`} />
      </div>

      <h2>AR Aging</h2>
      <div className="grid grid-4">
        <Kpi label="Current" value={fmtUsd(buckets.current)} />
        <Kpi label="0–30" value={fmtUsd(buckets["0-30"])} />
        <Kpi label="31–60" value={fmtUsd(buckets["31-60"])} />
        <Kpi label="61–90 / 90+" value={fmtUsd(buckets["61-90"] + buckets["90+"])} />
      </div>

      <h2>Edit client</h2>
      <form action={update} className="card inline">
        <div className="row">
          <label>Name<input name="name" defaultValue={c.name} required /></label>
          <label>Country<input name="country" defaultValue={c.country ?? ""} /></label>
          <label>Contact<input name="contact" defaultValue={c.contact ?? ""} /></label>
          <label>Payment terms (days)<input type="number" name="payment_terms_days" defaultValue={c.payment_terms_days} /></label>
        </div>
        <div className="row">
          <label>Credit limit USD<input type="number" step="0.01" name="credit_limit_usd" defaultValue={c.credit_limit_usd} /></label>
          <label>Default laytime (h)<input type="number" step="0.5" name="default_laytime_hours" defaultValue={c.default_laytime_hours} /></label>
          <label>Default demurrage USD/day<input type="number" step="1" name="default_demurrage_usd_per_day" defaultValue={c.default_demurrage_usd_per_day} /></label>
          <label>&nbsp;<button type="submit">Save</button></label>
        </div>
      </form>

      <div style={{ marginTop: 12 }}>
        <form action={del}><button className="btn danger">Delete client</button></form>
      </div>

      <h2>Deliveries</h2>
      <div className="card" style={{ padding: 0 }}>
        {dels.length === 0 ? <div className="empty">No deliveries for this client yet.</div> : (
          <table>
            <thead>
              <tr>
                <th>Ref</th><th>Product</th><th className="num">m³</th><th className="num">Cargo Value</th>
                <th className="num">Demurrage</th><th>Status</th><th className="num">Outstanding</th>
              </tr>
            </thead>
            <tbody>
              {dels.map((d) => {
                const dc = computeDemurrage(d);
                return (
                  <tr key={d.id}>
                    <td><Link href={`/deliveries/${d.id}`}>{d.reference || `#${d.id}`}</Link></td>
                    <td><span className={`badge ${d.product === "gasoil" ? "amber" : "purple"}`}>{d.product}</span></td>
                    <td className="num">{d.volume_m3}</td>
                    <td className="num">{fmtUsd(cargoValue(d))}</td>
                    <td className="num">{dc.amountUsd ? fmtUsd(dc.amountUsd) : <span className="muted">—</span>}</td>
                    <td><span className={`badge ${STATUS_COLORS[d.status]}`}>{d.status.replace("_"," ")}</span></td>
                    <td className="num">{fmtUsd(outstandingUsd(d))}</td>
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

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}
