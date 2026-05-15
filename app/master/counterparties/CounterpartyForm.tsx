import { Counterparty } from "@/lib/calc";
import { saveCounterparty } from "../actions";

export function CounterpartyForm({ cp }: { cp?: Counterparty }) {
  return (
    <form action={saveCounterparty.bind(null, cp?.id ?? null)} className="card inline">
      <div className="row">
        <label>Name *<input name="name" required defaultValue={cp?.name ?? ""} /></label>
        <label>Legal Name<input name="legal_name" defaultValue={cp?.legal_name ?? ""} /></label>
        <label>Country<input name="country" defaultValue={cp?.country ?? ""} /></label>
        <label>Allowed O/A (USD)<input type="number" step="0.01" name="allowed_oa_usd" defaultValue={cp?.allowed_oa_usd ?? 0} /></label>
      </div>
      <div className="row">
        <label>Contact Name<input name="contact_name" defaultValue={cp?.contact_name ?? ""} /></label>
        <label>Contact Email<input name="contact_email" defaultValue={cp?.contact_email ?? ""} /></label>
        <label>Contact Phone<input name="contact_phone" defaultValue={cp?.contact_phone ?? ""} /></label>
        <label>Default Payment Term<input name="default_payment_term" defaultValue={cp?.default_payment_term ?? ""} /></label>
      </div>
      <div className="row">
        <label>Default Demurrage (USD/day)<input type="number" name="default_demurrage_usd_per_day" defaultValue={cp?.default_demurrage_usd_per_day ?? 0} /></label>
        <label>Default Laytime (hours)<input type="number" step="0.5" name="default_laytime_hours" defaultValue={cp?.default_laytime_hours ?? 24} /></label>
        <label style={{ gridColumn: "span 2" }}>Address<input name="address" defaultValue={cp?.address ?? ""} /></label>
      </div>
      <div className="row-2">
        <label>Notes<input name="notes" defaultValue={cp?.notes ?? ""} /></label>
        <div style={{ alignSelf: "end" }}><button type="submit">{cp ? "Save changes" : "Create"}</button></div>
      </div>
    </form>
  );
}
