import { getDb } from "@/lib/db";
import { ClientRow, DeliveryRow, cargoValue, computeDemurrage, fmtUsd, fmtNum } from "@/lib/calc";
import Link from "next/link";

export const dynamic = "force-dynamic";

const STATUS_COLORS: Record<string, string> = {
  in_transit: "blue",
  delivered: "purple",
  invoiced: "amber",
  paid: "green",
  cancelled: "gray",
};

export default function Deliveries({ searchParams }: { searchParams: { status?: string; client?: string } }) {
  const db = getDb();
  const clients = db.prepare("SELECT * FROM clients ORDER BY name").all() as ClientRow[];

  const where: string[] = [];
  const params: any[] = [];
  if (searchParams.status) { where.push("status = ?"); params.push(searchParams.status); }
  if (searchParams.client) { where.push("client_id = ?"); params.push(Number(searchParams.client)); }
  const sql = "SELECT * FROM deliveries " +
    (where.length ? `WHERE ${where.join(" AND ")} ` : "") +
    "ORDER BY COALESCE(loading_date, created_at) DESC";
  const deliveries = db.prepare(sql).all(...params) as DeliveryRow[];

  return (
    <>
      <div className="toolbar">
        <h1>Deliveries</h1>
        <Link href="/deliveries/new" className="btn">+ New Delivery</Link>
      </div>

      <form className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          <label>Status
            <select name="status" defaultValue={searchParams.status ?? ""}>
              <option value="">All</option>
              <option value="in_transit">In transit</option>
              <option value="delivered">Delivered</option>
              <option value="invoiced">Invoiced</option>
              <option value="paid">Paid</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <label>Client
            <select name="client" defaultValue={searchParams.client ?? ""}>
              <option value="">All</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <div style={{ alignSelf: "end" }}>
            <button type="submit">Filter</button>
            {" "}<Link href="/deliveries" className="btn secondary">Reset</Link>
          </div>
        </div>
      </form>

      <div className="card" style={{ padding: 0 }}>
        {deliveries.length === 0 ? <div className="empty">No deliveries yet.</div> : (
          <table>
            <thead>
              <tr>
                <th>Ref</th>
                <th>Client</th>
                <th>Product</th>
                <th className="num">Volume (m³)</th>
                <th className="num">Cargo Value</th>
                <th>Arrival</th>
                <th>Departure</th>
                <th className="num">Demurrage</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {deliveries.map((d) => {
                const c = clients.find((x) => x.id === d.client_id);
                const dem = computeDemurrage(d);
                return (
                  <tr key={d.id}>
                    <td><Link href={`/deliveries/${d.id}`}>{d.reference || `#${d.id}`}</Link>
                      <div className="muted" style={{ fontSize: 11 }}>{d.truck_plate}</div></td>
                    <td>{c?.name}</td>
                    <td><span className={`badge ${d.product === "gasoil" ? "amber" : "purple"}`}>{d.product}</span></td>
                    <td className="num">{fmtNum(d.volume_m3, 2)}</td>
                    <td className="num">{fmtUsd(cargoValue(d))}</td>
                    <td>{d.arrival_date?.slice(0,16) ?? "—"}</td>
                    <td>{d.departure_date?.slice(0,16) ?? "—"}</td>
                    <td className="num">{dem.amountUsd > 0
                      ? <span title={`${dem.demurrageDays} day(s) × ${fmtUsd(d.demurrage_usd_per_day)}`}>{fmtUsd(dem.amountUsd)}</span>
                      : <span className="muted">—</span>}</td>
                    <td><span className={`badge ${STATUS_COLORS[d.status]}`}>{d.status.replace("_", " ")}</span></td>
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
