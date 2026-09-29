import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Northstar | Freight Prospect Intelligence",
  description: "Evidence-backed network-fit research for carrier sales teams.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: "#f3f0e8",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-border/80">
          <div className="mx-auto flex w-[min(100%-2rem,72rem)] items-center justify-between py-5">
            <span className="flex items-center gap-2 font-semibold tracking-tight">
              <span
                className="grid size-7 place-items-center rounded-lg bg-foreground text-xs text-background"
                aria-hidden="true"
              >
                N
              </span>
              Northstar
            </span>
            <span className="text-sm text-muted-foreground">Carrier sales workspace</span>
          </div>
        </header>
        <main className="mx-auto w-[min(100%-2rem,76rem)] py-[clamp(3rem,8vw,7rem)]">
          {children}
        </main>
      </body>
    </html>
  );
}
