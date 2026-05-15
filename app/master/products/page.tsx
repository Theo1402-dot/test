import { getDb } from "@/lib/db";
import { Product } from "@/lib/calc";
import { saveProduct, deleteProduct } from "../actions";

export const dynamic = "force-dynamic";

export default function ProductsPage() {
  const rows = getDb().prepare("SELECT * FROM products ORDER BY code").all() as Product[];
  return (
    <>
      <h1>Products</h1>
      <p className="muted">Used for deal capture, position views and density-based MT ↔ m³ conversion.</p>
      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        <table>
          <thead><tr><th>Code</th><th>Name</th><th className="num">Density (kg/m³)</th><th></th></tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
                <td><span className="tag">{p.code}</span></td>
                <td>{p.name}</td>
                <td className="num">{p.density_kg_per_m3 ?? "—"}</td>
                <td><form action={deleteProduct.bind(null, p.id)}><button className="btn danger">Delete</button></form></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Add product</h2>
      <form action={saveProduct.bind(null, null)} className="card inline">
        <div className="row">
          <label>Code *<input name="code" required /></label>
          <label>Name *<input name="name" required /></label>
          <label>Density kg/m³<input type="number" name="density_kg_per_m3" /></label>
          <label>&nbsp;<button type="submit">Add</button></label>
        </div>
      </form>
    </>
  );
}
