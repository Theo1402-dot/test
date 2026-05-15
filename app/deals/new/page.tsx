import Link from "next/link";
import { DealForm } from "../DealForm";

export const dynamic = "force-dynamic";

export default function NewDeal({ searchParams }: { searchParams: { counterparty_id?: string } }) {
  const cpId = searchParams.counterparty_id ? Number(searchParams.counterparty_id) : undefined;
  return (
    <>
      <div className="toolbar">
        <h1>New Deal</h1>
        <Link href="/deals" className="btn secondary">Cancel</Link>
      </div>
      <DealForm defaultCounterpartyId={cpId} />
    </>
  );
}
