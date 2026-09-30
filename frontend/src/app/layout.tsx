import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

import { typeStyles } from "@/components/ui/styles";
import { DEMO_REP_NAME } from "@/lib/demo-identity";

export const metadata: Metadata = {
  title: "Prospect Intelligence",
  description: "Evidence-backed network-fit briefs with rep-reviewed outreach for carrier sales.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  colorScheme: "light",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" className="min-w-80 bg-white">
      <body className="flex min-h-dvh flex-col bg-white font-sans text-slate-950 antialiased">
        <header className="flex h-12 shrink-0 items-center justify-between gap-4 border-b border-slate-200 px-4 sm:px-5">
          <h1 className={typeStyles.wordmark}>Prospect Intelligence</h1>
          <p className={typeStyles.utility}>{DEMO_REP_NAME} · Demo tenant</p>
        </header>
        <main className="flex flex-1">{children}</main>
      </body>
    </html>
  );
}
