import { getDb } from "@/lib/db";
import { ClientRow } from "@/lib/calc";
import { createDelivery } from "../actions";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function NewDelivery() {
  const db = getDb();
  const clients = db.prepare("SELECT * FROM clients ORDER BY name").all() as ClientRow[];

  if (clients.length === 0) {
    return (
      <>
        <h1>New Delivery</h1>
        <div className="card">
          <p>You need at least one client first.</p>
          <Link href="/clients/new" className="btn">+ Add Client</Link>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="toolbar">
        <h1>New Delivery</h1>
        <Link href="/deliveries" className="btn secondary">Cancel</Link>
      </div>
      <form action={createDelivery} className="card inline">
        <div className="row">
          <label>Client *
            <select name="client_id" required>
              {clients.map((c) => (
                <option key={c.id} value={c.id}
                  data-laytime={c.default_laytime_hours}
                  data-rate={c.default_demurrage_usd_per_day}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>Reference
            <input name="reference" placeholder="e.g. ATL-2026-016" />
          </label>
          <label>Product *
            <select name="product" required defaultValue="gasoil">
              <option value="gasoil">Gasoil</option>
              <option value="gasoline">Gasoline</option>
            </select>
          </label>
          <label>Status
            <select name="status" defaultValue="in_transit">
              <option value="in_transit">In transit</option>
              <option value="delivered">Delivered</option>
              <option value="invoiced">Invoiced</option>
            </select>
          </label>
        </div>

        <div className="row">
          <label>Volume (m³) *
            <input type="number" step="0.01" name="volume_m3" required />
          </label>
          <label>Price (USD/m³) *
            <input type="number" step="0.01" name="price_per_m3_usd" required />
          </label>
          <label>Destination
            <input name="destination" placeholder="Depot / city" />
          </label>
          <label>Truck plate
            <input name="truck_plate" />
          </label>
        </div>

        <div className="row">
          <label>Loading date
            <input type="datetime-local" name="loading_date" />
          </label>
          <label>Arrival at unloading
            <input type="datetime-local" name="arrival_date" />
          </label>
          <label>Departure from unloading
            <input type="datetime-local" name="departure_date" />
          </label>
          <label>&nbsp;
            <span className="muted" style={{ fontSize: 11 }}>
              Demurrage = days at site beyond laytime (no pro-rata).
            </span>
          </label>
        </div>

        <div className="row">
          <label>Laytime (hours) — blank = client default
            <input type="number" step="0.5" name="laytime_hours" />
          </label>
          <label>Demurrage rate (USD/day) — blank = client default
            <input type="number" step="1" name="demurrage_usd_per_day" />
          </label>
          <label style={{ gridColumn: "span 2" }}>Notes
            <input name="notes" />
          </label>
        </div>

        <div>
          <button type="submit">Save Delivery</button>
        </div>
      </form>
    </>
  );
}
