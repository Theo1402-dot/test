import { getDb } from "@/lib/db";

export const dynamic = "force-dynamic";

export default function MasterOverview() {
  const db = getDb();
  const counts = {
    entities: (db.prepare("SELECT COUNT(*) c FROM entities").get() as any).c,
    banks: (db.prepare("SELECT COUNT(*) c FROM banks").get() as any).c,
    counterparties: (db.prepare("SELECT COUNT(*) c FROM counterparties").get() as any).c,
    products: (db.prepare("SELECT COUNT(*) c FROM products").get() as any).c,
    locations: (db.prepare("SELECT COUNT(*) c FROM locations").get() as any).c,
    storage: (db.prepare("SELECT COUNT(*) c FROM storage_agreements").get() as any).c,
  };
  return (
    <>
      <h1>Master Data</h1>
      <p className="muted">Manage reference data used across deals, positions and documents.</p>
      <div className="grid grid-4">
        <Kpi label="Entities" value={String(counts.entities)} />
        <Kpi label="Banks" value={String(counts.banks)} />
        <Kpi label="Counterparties" value={String(counts.counterparties)} />
        <Kpi label="Products" value={String(counts.products)} />
        <Kpi label="Locations" value={String(counts.locations)} />
        <Kpi label="Storage Agreements" value={String(counts.storage)} />
      </div>
    </>
  );
}
function Kpi({ label, value }: { label: string; value: string }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div></div>;
}
