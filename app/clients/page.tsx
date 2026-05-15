import { getDb } from "@/lib/db";
import {
  ClientRow, DeliveryRow,
  accruedDemurrageUsd, fmtUsd, inTransitValueUsd, outstandingUsd,
} from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function Clients() {
  const db = getDb();
  const clients = db.prepare("SELECT * FROM clients ORDER BY name").all() as ClientRow[];
  const deliveries = db.prepare("SELECT * FROM deliveries").all() as DeliveryRow[];

  return (
    <>
      <div className="toolbar">
        <h1>Clients</h1>
        <Link href="/clients/new" className="btn">+ New Client</Link>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Country</th>
              <th>Contact</th>
              <th className="num">Credit Limit</th>
              <th className="num">AR</th>
              <th className="num">In Transit</th>
              <th className="num">Demurrage</th>
              <th>Utilisation</th>
              <th className="num">Payment Terms</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((c) => {
              const dels = deliveries.filter((d) => d.client_id === c.id);
              const ar = dels.reduce((s, d) => s + outstandingUsd(d), 0);
              const inT = dels.reduce((s, d) => s + inTransitValueUsd(d), 0);
              const dem = dels.reduce((s, d) => s + accruedDemurrageUsd(d), 0);
              const total = ar + inT;
              const util = c.credit_limit_usd > 0 ? total / c.credit_limit_usd : 0;
              const cls = util >= 1 ? "red" : util >= 0.8 ? "amber" : "";
              return (
                <tr key={c.id}>
                  <td><Link href={`/clients/${c.id}`}>{c.name}</Link></td>
                  <td>{c.country ?? "—"}</td>
                  <td className="muted">{c.contact ?? "—"}</td>
                  <td className="num">{fmtUsd(c.credit_limit_usd)}</td>
                  <td className="num">{fmtUsd(ar)}</td>
                  <td className="num">{fmtUsd(inT)}</td>
                  <td className="num">{fmtUsd(dem)}</td>
                  <td style={{ minWidth: 140 }}>
                    <div style={{ fontSize: 11 }}>{(util * 100).toFixed(0)}%</div>
                    <div className="bar-track"><div className={`bar-fill ${cls}`} style={{ width: `${Math.min(100, util*100)}%` }} /></div>
                  </td>
                  <td className="num">{c.payment_terms_days} d</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
