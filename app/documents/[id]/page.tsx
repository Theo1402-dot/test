import { getDb } from "@/lib/db";
import { Doc, Entity, Counterparty, Bank, Deal, Product, fmtUsd, fmtNum, fmtDateLong } from "@/lib/calc";
import Link from "next/link";
import { notFound } from "next/navigation";
import { deleteDocument, updateDocument } from "../actions";
import PrintButton from "./PrintButton";

export const dynamic = "force-dynamic";

const TITLES: Record<string, string> = {
  PFI: "PROVISIONAL INVOICE",
  FINAL_INVOICE: "FINAL INVOICE",
  STORAGE_INVOICE: "STORAGE INVOICE",
};

export default function DocumentPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const db = getDb();
  const doc = db.prepare("SELECT * FROM documents WHERE id=?").get(id) as Doc | undefined;
  if (!doc) notFound();
  const entity = db.prepare("SELECT * FROM entities WHERE id=?").get(doc.entity_id) as Entity;
  const cp = db.prepare("SELECT * FROM counterparties WHERE id=?").get(doc.counterparty_id) as Counterparty;
  const bank = doc.bank_id ? db.prepare("SELECT * FROM banks WHERE id=?").get(doc.bank_id) as Bank | undefined : undefined;
  const banks = db.prepare("SELECT * FROM banks WHERE entity_id=? ORDER BY is_default DESC, label").all(doc.entity_id) as Bank[];
  const deal = doc.deal_id ? db.prepare("SELECT * FROM deals WHERE id=?").get(doc.deal_id) as Deal | undefined : undefined;
  const product = deal ? db.prepare("SELECT * FROM products WHERE id=?").get(deal.product_id) as Product : undefined;

  const title = TITLES[doc.doc_type];

  return (
    <>
      <div className="toolbar no-print">
        <h1>{doc.doc_no}
          <span className={`badge ${{PFI:"blue",FINAL_INVOICE:"green",STORAGE_INVOICE:"purple"}[doc.doc_type]}`} style={{marginLeft:8}}>{doc.doc_type}</span>
          <span className={`badge ${{draft:"gray",issued:"amber",paid:"green",cancelled:"red"}[doc.status]}`} style={{marginLeft:6}}>{doc.status}</span>
        </h1>
        <div className="row-actions">
          <Link href="/documents" className="btn secondary">← All documents</Link>
          <PrintButton />
        </div>
      </div>

      {/* Printable document */}
      <div className="doc-page">
        <div style={{ textAlign: "center", letterSpacing: "0.08em", fontWeight: 700, fontSize: 18 }}>{title}</div>
        <div style={{ textAlign: "right", color: "#666", fontSize: 12, marginTop: 4 }}>{doc.doc_no}</div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 28 }}>
          <div className="doc-block">
            <div className="label">FROM</div>
            <div className="value"><strong>{entity.legal_name}</strong></div>
            <div className="value" style={{ whiteSpace: "pre-line", color: "#555" }}>{entity.address ?? ""}</div>
          </div>
          <div className="doc-block">
            <div className="label">TO</div>
            <div className="value"><strong>{cp.legal_name ?? cp.name}</strong></div>
            <div className="value" style={{ whiteSpace: "pre-line", color: "#555" }}>{cp.address ?? cp.country ?? ""}</div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24, marginTop: 16 }}>
          <KV label="DATE" value={fmtDateLong(doc.issue_date)} />
          <KV label={doc.doc_type === "STORAGE_INVOICE" ? "STORAGE AGREEMENT" : "DEAL REF"} value={deal?.deal_no ?? "—"} />
          <KV label="PRODUCT" value={product?.name?.toUpperCase() ?? (doc.doc_type === "STORAGE_INVOICE" ? "STORAGE SERVICES" : "—")} />
        </div>

        {doc.doc_type !== "STORAGE_INVOICE" ? (
          <>
            <div style={{ marginTop: 16 }}>
              <KV label="QUANTITY" value={`${fmtNum(doc.qty_m3 ?? 0, 3)} M3 AT 20° +/- OPERATIONAL TOLERANCE`} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24, marginTop: 16 }}>
              <KV label="DELIVERY" value={deal?.incoterm ?? "—"} />
              <KV label="DELIVERY RANGE" value={`${fmtDateLong(deal?.beg_date ?? null)} – ${fmtDateLong(deal?.end_date ?? null)}`} />
              <KV label="PRICE" value={`${fmtNum(doc.price_usd_per_m3 ?? 0, 2)} $/M3`} />
            </div>
          </>
        ) : (
          <>
            <div style={{ marginTop: 16 }}>
              <KV label="QUANTITY" value={`${fmtNum(doc.qty_m3 ?? 0, 3)} M3`} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginTop: 16 }}>
              <KV label="PERIOD FROM" value={fmtDateLong(doc.period_from)} />
              <KV label="PERIOD TO" value={fmtDateLong(doc.period_to)} />
            </div>
          </>
        )}

        <div style={{ marginTop: 24, padding: "12px 16px", background: "#f7f7f7", borderRadius: 4 }}>
          <div className="label">AMOUNT DUE</div>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{fmtUsd(doc.amount_usd, 2)} {doc.currency}</div>
          {doc.due_date && <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>Due: {fmtDateLong(doc.due_date)}</div>}
        </div>

        {doc.payment_terms_text && (
          <div style={{ marginTop: 24 }}>
            <div className="label">PAYMENT DUE</div>
            <div className="value" style={{ marginTop: 4 }}>{doc.payment_terms_text}</div>
          </div>
        )}

        {bank && (
          <div style={{ marginTop: 24 }}>
            <div className="label">PAYMENT DETAILS — IN {bank.currency} BY TELEGRAPHIC TRANSFER TO</div>
            <table style={{ marginTop: 8 }}>
              <tbody>
                <Row k="BENEFICIARY" v={bank.beneficiary} />
                <Row k="BENEFICIARY BANK" v={bank.bank_name + (bank.bank_address ? `, ${bank.bank_address}` : "")} />
                <Row k="SWIFT" v={bank.swift} />
                {bank.iban && <Row k="IBAN" v={bank.iban} />}
                {bank.account_no && !bank.iban && <Row k="ACCOUNT NO" v={bank.account_no} />}
                {bank.correspondent_bank && <Row k="CORRESPONDENT" v={bank.correspondent_bank} />}
                {bank.correspondent_swift && <Row k="CORRESPONDENT SWIFT" v={bank.correspondent_swift} />}
              </tbody>
            </table>
            <div style={{ marginTop: 12, fontSize: 11, color: "#666", fontStyle: "italic" }}>
              Payment with liberating effect can only be made to this account held with the above mentioned bank, as assignee of the proceeds of this invoice.
            </div>
          </div>
        )}
      </div>

      {/* Edit panel */}
      <h2 className="no-print">Edit document</h2>
      <form action={updateDocument.bind(null, doc.id)} className="card inline no-print">
        <div className="row">
          <label>Issue date<input type="date" name="issue_date" defaultValue={doc.issue_date.slice(0,10)} /></label>
          <label>Due date<input type="date" name="due_date" defaultValue={doc.due_date?.slice(0,10) ?? ""} /></label>
          <label>Qty m³<input type="number" step="0.001" name="qty_m3" defaultValue={doc.qty_m3 ?? ""} /></label>
          <label>Price $/m³<input type="number" step="0.01" name="price_usd_per_m3" defaultValue={doc.price_usd_per_m3 ?? ""} /></label>
        </div>
        <div className="row">
          <label>Amount USD<input type="number" step="0.01" name="amount_usd" defaultValue={doc.amount_usd} /></label>
          <label>Bank
            <select name="bank_id" defaultValue={doc.bank_id ?? ""}>
              <option value="">—</option>
              {banks.map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
            </select>
          </label>
          <label>Status
            <select name="status" defaultValue={doc.status}>
              <option value="draft">Draft</option>
              <option value="issued">Issued</option>
              <option value="paid">Paid</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <label>Paid amount<input type="number" step="0.01" name="paid_amount_usd" defaultValue={doc.paid_amount_usd} /></label>
        </div>
        <div className="row">
          <label>Paid date<input type="date" name="paid_date" defaultValue={doc.paid_date?.slice(0,10) ?? ""} /></label>
          <label style={{ gridColumn: "span 3" }}>Payment terms text<input name="payment_terms_text" defaultValue={doc.payment_terms_text ?? ""} /></label>
        </div>
        <div className="row-2">
          <label>Notes<input name="notes" defaultValue={doc.notes ?? ""} /></label>
          <div style={{ alignSelf: "end", display: "flex", gap: 8 }}>
            <button type="submit">Save</button>
          </div>
        </div>
      </form>

      <div className="card no-print" style={{ marginTop: 12, display: "flex", gap: 8 }}>
        <form action={deleteDocument.bind(null, doc.id)}><button className="btn danger">Delete document</button></form>
      </div>
    </>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return <div className="doc-block"><div className="label">{label}</div><div className="value">{value}</div></div>;
}
function Row({ k, v }: { k: string; v: string | null | undefined }) {
  return <tr><td style={{ color: "#888", fontSize: 11, paddingRight: 16 }}>{k}</td><td style={{ fontFamily: "ui-monospace, Menlo, monospace" }}>{v ?? "—"}</td></tr>;
}

