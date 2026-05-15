import Link from "next/link";

export default function PositionsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="subnav">
        <Link href="/positions/counterparty">By Counterparty</Link>
        <Link href="/positions/location">By Location</Link>
        <Link href="/positions/security">By Security / SBLC</Link>
        <Link href="/positions/aging">AR Aging</Link>
      </div>
      {children}
    </>
  );
}
