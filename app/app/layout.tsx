import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Chapter 99 Explorer",
  description: "What Chapter 99 actually does to a tariff line -- resolved rates, exclusions, and notes.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <Link href="/" className="site-title">
            Chapter&nbsp;99 Explorer
          </Link>
          <span className="site-subtitle">temporary duty modifications, resolved</span>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
