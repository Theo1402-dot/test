import { getDb } from "@/lib/db";
import { Entity } from "@/lib/calc";
import { saveEntity, deleteEntity } from "../actions";

export const dynamic = "force-dynamic";

export default function EntitiesPage() {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM entities ORDER BY code").all() as Entity[];
  return (
    <>
      <h1>Entities</h1>
      <p className="muted">Trading entities (MOCOH, MOCZAM, …). Every deal & document is issued by one entity.</p>

      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        <table>
          <thead><tr><th>Code</th><th>Legal Name</th><th>Address</th><th>Tax ID</th><th></th></tr></thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id}>
                <td><span className="tag">{e.code}</span></td>
                <td>{e.legal_name}</td>
                <td className="muted">{e.address ?? "—"}</td>
                <td className="muted">{e.tax_id ?? "—"}</td>
                <td className="row-actions">
                  <form action={saveEntity.bind(null, e.id)} style={{ display: "none" }} id={`f${e.id}`}></form>
                  <form action={deleteEntity.bind(null, e.id)}><button className="btn danger" type="submit">Delete</button></form>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Add entity</h2>
      <form action={saveEntity.bind(null, null)} className="card inline">
        <div className="row">
          <label>Code *<input name="code" required placeholder="MOCOH" /></label>
          <label>Legal Name *<input name="legal_name" required placeholder="MOCOHSA" /></label>
          <label>Tax ID<input name="tax_id" /></label>
          <label>&nbsp;<button type="submit">Add</button></label>
        </div>
        <div className="row-2">
          <label>Address<input name="address" placeholder="Rue de la Corraterie 5-7, 1204 Geneva" /></label>
        </div>
      </form>
    </>
  );
}
