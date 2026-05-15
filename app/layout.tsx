import "./globals.css";
import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Trading Ops",
  description: "Oil trading mid-office: deals, positions, documents",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <div className="brand">
            <span className="logo">⛽</span>
            <span>Trading Ops</span>
          </div>
          <nav>
            <Link href="/">Dashboard</Link>
            <Link href="/deals">Deals</Link>
            <Link href="/positions/counterparty">By Counterparty</Link>
            <Link href="/positions/location">By Location</Link>
            <Link href="/documents">Documents</Link>
            <Link href="/master">Master Data</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
