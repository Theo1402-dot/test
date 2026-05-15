import { getDb } from "@/lib/db";
import { StorageAgreement, Location, Counterparty, fmtUsd } from "@/lib/calc";
import Link from "next/link";
import { deleteStorageAgreement, saveStorageAgreement } from "../actions";

export const dynamic = "force-dynamic";

export default function StoragePage() {
  const db = getDb();
  const rows = db.prepare(`
    SELECT s.*, l.code AS location_code, l.name AS location_name,
      c.name AS counterparty_name
    FROM storage_agreements s
    LEFT JOIN locations l ON l.id = s.location_id
    LEFT JOIN counterparties c ON c.id = s.counterparty_id
    ORDER BY l.code, c.name
  `).all() as (StorageAgreement & { location_code: string; location_name: string; counterparty_name: string | null })[];
  const locations = db.prepare("SELECT * FROM locations ORDER BY code").all() as Location[];
  const counterparties = db.prepare("SELECT * FROM counterparties ORDER BY name").all() as Counterparty[];

  return (
    <>
      <h1>Storage Agreements</h1>
      <p className="muted">Used to generate storage invoices and track depot capacity.</p>

      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        <table>
          <thead>
            <tr>
              <th>Location</th><th>Terminal / Operator</th>
              <th>Agreement</th><th>KYC</th><th>CEND</th><th>DD</th>
              <th className="num">Fee 1st 30d</th>
              <th className="num">Fee Next 30d</th>
              <th>Expiry</th><th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id}>
                <td><span className="tag">{s.location_code}</span> {s.location_name}</td>
                <td>{s.counterparty_name ?? "—"}</td>
                <td>{tick(s.agreement_in_place)}</td>
                <td>{tick(s.kyc_clearance)}</td>
                <td>{tick(s.cend_in_place)}</td>
                <td>{tick(s.due_dil_done)}</td>
                <td className="num">{s.fee_first_30d_usd_per_m3 != null ? `$${s.fee_first_30d_usd_per_m3}/m³` : "—"}</td>
                <td className="num">{s.fee_next_30d_usd_per_m3 != null ? `$${s.fee_next_30d_usd_per_m3}/m³` : "—"}</td>
                <td>{s.contract_expiry?.slice(0,10) ?? "—"}</td>
                <td><form action={deleteStorageAgreement.bind(null, s.id)}><button className="btn danger">Delete</button></form></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Add storage agreement</h2>
      <form action={saveStorageAgreement.bind(null, null)} className="card inline">
        <div className="row">
          <label>Location *
            <select name="location_id" required>
              <option value="" disabled selected>—</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.code}</option>)}
            </select>
          </label>
          <label>Storage operator (counterparty)
            <select name="counterparty_id" defaultValue="">
              <option value="">—</option>
              {counterparties.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <label>Contract Expiry<input type="date" name="contract_expiry" /></label>
          <label>Renewal<input name="renewal" /></label>
        </div>
        <div className="row">
          <Check name="agreement_in_place" label="Agreement in place" />
          <Check name="kyc_clearance" label="KYC clearance" />
          <Check name="cend_in_place" label="CEND in place" />
          <Check name="due_dil_done" label="Due dil done" />
        </div>
        <div className="row">
          <label>Throughput AGO %<input type="number" step="0.01" name="throughput_ago_pct" /></label>
          <label>Throughput PMS %<input type="number" step="0.01" name="throughput_pms_pct" /></label>
          <label>Fee 1st 30d ($/m³)<input type="number" step="0.001" name="fee_first_30d_usd_per_m3" /></label>
          <label>Fee Next 30d ($/m³)<input type="number" step="0.001" name="fee_next_30d_usd_per_m3" /></label>
        </div>
        <div className="row">
          <label>FH Parcels ($/m³/mo)<input type="number" step="0.001" name="fh_parcels_usd_per_m3_per_mo" /></label>
          <label>Agency Fee ($/m³/mo)<input type="number" step="0.001" name="agency_fee_usd_per_m3_per_mo" /></label>
          <label style={{ gridColumn: "span 2" }}>Notes<input name="notes" /></label>
        </div>
        <div><button type="submit">Add agreement</button></div>
      </form>
    </>
  );
}

function tick(v: number) { return v ? <span className="badge green">✓</span> : <span className="badge gray">—</span>; }
function Check({ name, label }: { name: string; label: string }) {
  return <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}><input type="checkbox" name={name} /> {label}</label>;
}
