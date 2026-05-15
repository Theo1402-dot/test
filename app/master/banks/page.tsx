import { getDb } from "@/lib/db";
import { Bank, Entity } from "@/lib/calc";
import { saveBank, deleteBank } from "../actions";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function BanksPage() {
  const db = getDb();
  const banks = db.prepare(`
    SELECT b.*, e.code AS entity_code FROM banks b
    JOIN entities e ON e.id = b.entity_id ORDER BY e.code, b.label
  `).all() as (Bank & { entity_code: string })[];
  const entities = db.prepare("SELECT * FROM entities ORDER BY code").all() as Entity[];

  return (
    <>
      <h1>Bank Accounts</h1>
      <p className="muted">Each bank belongs to an entity. The default bank is pre-selected on PFIs / invoices but can be overridden per document.</p>

      <div className="card" style={{ padding: 0, marginBottom: 16 }}>
        <table>
          <thead>
            <tr><th>Entity</th><th>Label</th><th>Beneficiary</th><th>Bank</th><th>SWIFT</th><th>IBAN / Acct</th><th>Correspondent</th><th>Default</th><th></th></tr>
          </thead>
          <tbody>
            {banks.map((b) => (
              <tr key={b.id}>
                <td><span className="tag">{b.entity_code}</span></td>
                <td><Link href={`/master/banks/${b.id}`}>{b.label}</Link></td>
                <td>{b.beneficiary}</td>
                <td>{b.bank_name}</td>
                <td className="muted">{b.swift ?? "—"}</td>
                <td className="muted">{b.iban ?? b.account_no ?? "—"}</td>
                <td className="muted">{b.correspondent_bank ?? "—"}</td>
                <td>{b.is_default ? <span className="badge green">default</span> : ""}</td>
                <td><form action={deleteBank.bind(null, b.id)}><button className="btn danger">Delete</button></form></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Add bank</h2>
      <BankForm entities={entities} />
    </>
  );
}

export function BankForm({ entities, bank }: { entities: Entity[]; bank?: Bank }) {
  return (
    <form action={saveBank.bind(null, bank?.id ?? null)} className="card inline">
      <div className="row">
        <label>Entity *
          <select name="entity_id" required defaultValue={bank?.entity_id ?? ""}>
            <option value="" disabled>—</option>
            {entities.map((e) => <option key={e.id} value={e.id}>{e.code}</option>)}
          </select>
        </label>
        <label>Label *<input name="label" required defaultValue={bank?.label ?? ""} placeholder="ING Geneva (USD)" /></label>
        <label>Currency<input name="currency" defaultValue={bank?.currency ?? "USD"} /></label>
        <label>Beneficiary *<input name="beneficiary" required defaultValue={bank?.beneficiary ?? ""} /></label>
      </div>
      <div className="row">
        <label>Bank Name *<input name="bank_name" required defaultValue={bank?.bank_name ?? ""} placeholder="ING BANK N.V., AMSTERDAM" /></label>
        <label>Bank Address<input name="bank_address" defaultValue={bank?.bank_address ?? ""} /></label>
        <label>SWIFT<input name="swift" defaultValue={bank?.swift ?? ""} placeholder="BBRUCHGTXXX" /></label>
        <label>IBAN<input name="iban" defaultValue={bank?.iban ?? ""} placeholder="CH64 0838 70000 0107152 1" /></label>
      </div>
      <div className="row">
        <label>Account No (if no IBAN)<input name="account_no" defaultValue={bank?.account_no ?? ""} /></label>
        <label>Correspondent Bank<input name="correspondent_bank" defaultValue={bank?.correspondent_bank ?? ""} placeholder="JP MORGAN CHASE NY" /></label>
        <label>Correspondent SWIFT<input name="correspondent_swift" defaultValue={bank?.correspondent_swift ?? ""} placeholder="CHASUS33XXX" /></label>
        <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input type="checkbox" name="is_default" defaultChecked={bank?.is_default === 1} /> Default for entity
        </label>
      </div>
      <div className="row-2">
        <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <input type="checkbox" name="active" defaultChecked={bank?.active !== 0} /> Active
        </label>
        <div style={{ alignSelf: "end" }}><button type="submit">{bank ? "Save changes" : "Add bank"}</button></div>
      </div>
    </form>
  );
}
