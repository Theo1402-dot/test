import Link from "next/link";
import { CounterpartyForm } from "../CounterpartyForm";

export default function NewCounterparty() {
  return (
    <>
      <div className="toolbar">
        <h1>New Counterparty</h1>
        <Link href="/master/counterparties" className="btn secondary">Cancel</Link>
      </div>
      <CounterpartyForm />
    </>
  );
}
