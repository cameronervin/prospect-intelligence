import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "@fontsource-variable/archivo/wdth.css";
import "./globals.css";

import { DEMO_REP_NAME } from "@/lib/demo-identity";

export const metadata: Metadata = {
  title: "Prospect Intelligence",
  description: "Evidence-backed network-fit briefs with rep-reviewed outreach for carrier sales.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f2f0e9" },
    { media: "(prefers-color-scheme: dark)", color: "#121714" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="border-line flex h-12 items-center justify-between gap-4 border-b px-4 sm:px-5">
          <h1 className="type-wordmark">Prospect Intelligence</h1>
          <p className="type-utility">{DEMO_REP_NAME} · Demo tenant</p>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
