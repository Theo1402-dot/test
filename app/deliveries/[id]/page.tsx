import { getDb } from "@/lib/db";
import {
  ClientRow, DeliveryRow,
  cargoValue, computeDemurrage, fmtDate, fmtNum, fmtUsd, invoiceTotal, outstandingUsd,
} from "@/lib/calc";
import Link from "next/link";
import { notFound } from "next/navigation";
import { deleteDelivery, markInvoiced, updateDelivery } from "../actions";

export const dynamic = "force-dynamic";

function dtLocal(s: string | null) {
  if (!s) return "";
  return s.replace(" ", "T").slice(0, 16);
}

export default function DeliveryDetail({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const db = getDb();
  const d = db.prepare("SELECT * FROM deliveries WHERE id = ?").get(id) as DeliveryRow | undefined;
  if (!d) notFound();
  const client = db.prepare("SELECT * FROM clients WHERE id = ?").get(d.client_id) as ClientRow;

  const dem = computeDemurrage(d);
  const cargo = cargoValue(d);
  const invTotal = invoiceTotal(d);
  const outstanding = outstandingUsd(d);

  const update = updateDelivery.bind(null, d.id);
  const del = deleteDelivery.bind(null, d.id);
  const invoice = markInvoiced.bind(null, d.id);

  return (
    <>
      <div className="toolbar">
        <h1>{d.reference || `Delivery #${d.id}`} <span className="pill">{client.name}</span></h1>
        <Link href="/deliveries" className="btn secondary">← All deliveries</Link>
      </div>

      <div className="grid grid-4">
        <div className="card kpi">
          <div className="label">Cargo Value</div>
          <div className="value">{fmtUsd(cargo)}</div>
          <div className="sub">{fmtNum(d.volume_m3)} m³ × {fmtUsd(d.price_per_m3_usd)}/m³</div>
        </div>
        <div className="card kpi">
          <div className="label">Time at Site</div>
          <div className="value">{fmtNum(dem.hoursAtSite, 1)} h</div>
          <div className="sub">Laytime: {fmtNum(d.laytime_hours, 1)} h</div>
        </div>
        <div className="card kpi">
          <div className="label">Demurrage</div>
          <div className="value" style={{ color: dem.amountUsd > 0 ? "var(--red)" : undefined }}>{fmtUsd(dem.amountUsd)}</div>
          <div className="sub">{dem.demurrageDays} day(s) × {fmtUsd(d.demurrage_usd_per_day)}</div>
        </div>
        <div className="card kpi">
          <div className="label">Outstanding</div>
          <div className="value">{fmtUsd(outstanding)}</div>
          <div className="sub">Invoice total: {fmtUsd(invTotal)} · Paid: {fmtUsd(d.paid_amount_usd)}</div>
        </div>
      </div>

      <h2>Edit</h2>
      <form action={update} className="card inline">
        <div className="row">
          <label>Reference
            <input name="reference" defaultValue={d.reference ?? ""} />
          </label>
          <label>Product
            <select name="product" defaultValue={d.product}>
              <option value="gasoil">Gasoil</option>
              <option value="gasoline">Gasoline</option>
            </select>
          </label>
          <label>Volume (m³)
            <input type="number" step="0.01" name="volume_m3" defaultValue={d.volume_m3} />
          </label>
          <label>Price USD/m³
            <input type="number" step="0.01" name="price_per_m3_usd" defaultValue={d.price_per_m3_usd} />
          </label>
        </div>

        <div className="row">
          <label>Destination
            <input name="destination" defaultValue={d.destination ?? ""} />
          </label>
          <label>Truck plate
            <input name="truck_plate" defaultValue={d.truck_plate ?? ""} />
          </label>
          <label>Loading
            <input type="datetime-local" name="loading_date" defaultValue={dtLocal(d.loading_date)} />
          </label>
          <label>Status
            <select name="status" defaultValue={d.status}>
              <option value="in_transit">In transit</option>
              <option value="delivered">Delivered</option>
              <option value="invoiced">Invoiced</option>
              <option value="paid">Paid</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
        </div>

        <div className="row">
          <label>Arrival
            <input type="datetime-local" name="arrival_date" defaultValue={dtLocal(d.arrival_date)} />
          </label>
          <label>Departure
            <input type="datetime-local" name="departure_date" defaultValue={dtLocal(d.departure_date)} />
          </label>
          <label>Laytime (h)
            <input type="number" step="0.5" name="laytime_hours" defaultValue={d.laytime_hours} />
          </label>
          <label>Demurrage rate USD/day
            <input type="number" step="1" name="demurrage_usd_per_day" defaultValue={d.demurrage_usd_per_day} />
          </label>
        </div>

        <div className="row">
          <label>Invoice date
            <input type="date" name="invoice_date" defaultValue={d.invoice_date?.slice(0,10) ?? ""} />
          </label>
          <label>Due date
            <input type="date" name="due_date" defaultValue={d.due_date?.slice(0,10) ?? ""} />
          </label>
          <label>Paid date
            <input type="date" name="paid_date" defaultValue={d.paid_date?.slice(0,10) ?? ""} />
          </label>
          <label>Paid amount (USD)
            <input type="number" step="0.01" name="paid_amount_usd" defaultValue={d.paid_amount_usd} />
          </label>
        </div>

        <div className="row-2">
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <input type="checkbox" name="demurrage_billed" defaultChecked={!!d.demurrage_billed} />
            <span>Demurrage included in invoice</span>
          </label>
          <label>Notes
            <input name="notes" defaultValue={d.notes ?? ""} />
          </label>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button type="submit">Save changes</button>
        </div>
      </form>

      <h2>Actions</h2>
      <div className="card" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {d.status !== "invoiced" && d.status !== "paid" && (
          <form action={invoice}><button className="btn">Mark as invoiced (terms: {client.payment_terms_days}d)</button></form>
        )}
        <form action={del}><button className="btn danger" type="submit">Delete delivery</button></form>
      </div>

      <h2>Demurrage breakdown</h2>
      <div className="card">
        <table>
          <tbody>
            <tr><td>Arrival</td><td>{fmtDate(d.arrival_date)}</td></tr>
            <tr><td>Departure</td><td>{fmtDate(d.departure_date)}</td></tr>
            <tr><td>Hours at site</td><td className="num">{fmtNum(dem.hoursAtSite, 2)} h</td></tr>
            <tr><td>Laytime allowance</td><td className="num">{fmtNum(d.laytime_hours, 2)} h</td></tr>
            <tr><td>Excess hours</td><td className="num">{fmtNum(dem.demurrageHours, 2)} h</td></tr>
            <tr><td>Demurrage days (ceiling, no pro-rata)</td><td className="num">{dem.demurrageDays}</td></tr>
            <tr><td>Rate</td><td className="num">{fmtUsd(d.demurrage_usd_per_day)} / day</td></tr>
            <tr><td><strong>Demurrage amount</strong></td><td className="num"><strong>{fmtUsd(dem.amountUsd)}</strong></td></tr>
          </tbody>
        </table>
      </div>
    </>
  );
}
