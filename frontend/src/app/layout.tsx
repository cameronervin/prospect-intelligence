import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

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
      <body className="min-h-dvh bg-white font-sans text-slate-950 antialiased">{children}</body>
    </html>
  );
}
