import { getDb } from "@/lib/db";
import { Location } from "@/lib/calc";
import { saveLocation, deleteLocation } from "../actions";

export const dynamic = "force-dynamic";

export default function LocationsPage() {
  const rows = getDb().prepare("SELECT * FROM locations ORDER BY code").all() as Location[];
  return (
    <>
      <h1>Locations</h1>
      <p className="muted">Used to identify the delivery point of a deal (Beira, Maputo, Lusaka, …).</p>

      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        <table>
          <thead><tr><th>Code</th><th>Name</th><th>Country</th><th>Type</th><th></th></tr></thead>
          <tbody>
            {rows.map((l) => (
              <tr key={l.id}>
                <td><span className="tag">{l.code}</span></td>
                <td>{l.name}</td>
                <td className="muted">{l.country ?? "—"}</td>
                <td className="muted">{l.type ?? "—"}</td>
                <td><form action={deleteLocation.bind(null, l.id)}><button className="btn danger">Delete</button></form></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Add location</h2>
      <form action={saveLocation.bind(null, null)} className="card inline">
        <div className="row">
          <label>Code *<input name="code" required placeholder="BEIRA" /></label>
          <label>Name *<input name="name" required /></label>
          <label>Country<input name="country" /></label>
          <label>Type
            <select name="type" defaultValue="port">
              <option value="port">port</option>
              <option value="inland">inland</option>
            </select>
          </label>
        </div>
        <div><button type="submit">Add</button></div>
      </form>
    </>
  );
}
