import "./globals.css";
import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Oil Trading Ops",
  description: "Demurrage calculator and client exposure tracker",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <div className="brand">
            <span className="logo">⛽</span>
            <span>Oil Trading Ops</span>
          </div>
          <nav>
            <Link href="/">Dashboard</Link>
            <Link href="/deliveries">Deliveries</Link>
            <Link href="/clients">Clients</Link>
            <Link href="/demurrage">Demurrage</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
