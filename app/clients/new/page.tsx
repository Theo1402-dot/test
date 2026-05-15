import Link from "next/link";
import { createClient } from "../actions";

export default function NewClient() {
  return (
    <>
      <div className="toolbar">
        <h1>New Client</h1>
        <Link href="/clients" className="btn secondary">Cancel</Link>
      </div>
      <form action={createClient} className="card inline">
        <div className="row">
          <label>Name *<input name="name" required /></label>
          <label>Country<input name="country" /></label>
          <label>Contact (email/phone)<input name="contact" /></label>
          <label>Payment terms (days)<input type="number" name="payment_terms_days" defaultValue={30} /></label>
        </div>
        <div className="row">
          <label>Credit limit (USD)<input type="number" step="0.01" name="credit_limit_usd" defaultValue={0} /></label>
          <label>Default laytime (hours)<input type="number" step="0.5" name="default_laytime_hours" defaultValue={24} /></label>
          <label>Default demurrage rate (USD/day)<input type="number" step="1" name="default_demurrage_usd_per_day" defaultValue={250} /></label>
          <label>&nbsp;<button type="submit">Save Client</button></label>
        </div>
      </form>
    </>
  );
}
