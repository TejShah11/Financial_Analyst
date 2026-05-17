import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LedgerMind — Infosys Financial Analyst",
  description:
    "Agentic financial analyst over Infosys FY26 filings — narrative RAG, quantitative analysis, multi-turn memory.",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full overflow-hidden" style={{ background: "var(--bg-base)" }}>
        {children}
      </body>
    </html>
  );
}
