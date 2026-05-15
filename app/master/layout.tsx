import Link from "next/link";

export default function MasterLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="subnav">
        <Link href="/master">Overview</Link>
        <Link href="/master/entities">Entities</Link>
        <Link href="/master/banks">Banks</Link>
        <Link href="/master/counterparties">Counterparties</Link>
        <Link href="/master/products">Products</Link>
        <Link href="/master/locations">Locations</Link>
        <Link href="/master/storage">Storage</Link>
      </div>
      {children}
    </>
  );
}
