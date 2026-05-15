import { getDb } from "@/lib/db";
import { Bank, Entity } from "@/lib/calc";
import { notFound } from "next/navigation";
import { BankForm } from "../page";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default function EditBank({ params }: { params: { id: string } }) {
  const db = getDb();
  const bank = db.prepare("SELECT * FROM banks WHERE id=?").get(Number(params.id)) as Bank | undefined;
  if (!bank) notFound();
  const entities = db.prepare("SELECT * FROM entities ORDER BY code").all() as Entity[];
  return (
    <>
      <div className="toolbar">
        <h1>Edit bank: {bank.label}</h1>
        <Link href="/master/banks" className="btn secondary">← Back</Link>
      </div>
      <BankForm entities={entities} bank={bank} />
    </>
  );
}
