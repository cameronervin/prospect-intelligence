import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "LangChain Take-Home",
  description: "A domain-neutral foundation for an enterprise agent system.",
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
            <span className="font-semibold tracking-tight">LangChain Take-Home</span>
            <span className="text-sm text-muted-foreground">Initial scaffold</span>
          </div>
        </header>
        <main className="mx-auto w-[min(100%-2rem,72rem)] py-[clamp(3rem,8vw,7rem)]">
          {children}
        </main>
      </body>
    </html>
  );
}
