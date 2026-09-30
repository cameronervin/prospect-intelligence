import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type StatusTone = "ready" | "degraded" | "danger" | "review" | "active" | "neutral";

const toneClass: Record<StatusTone, string> = {
  ready: "bg-ready-soft text-ready",
  degraded: "bg-degraded-soft text-degraded",
  danger: "bg-danger-soft text-danger",
  review: "bg-accent-soft text-accent-strong",
  active: "bg-foreground text-background",
  neutral: "bg-surface text-foreground-soft ring-1 ring-line-strong ring-inset",
};

/** Pill geometry is reserved for genuine status values. */
export function StatusPill({
  tone,
  children,
}: Readonly<{ tone: StatusTone; children: ReactNode }>) {
  return (
    <span
      className={cn(
        "inline-flex h-5.5 shrink-0 items-center rounded-full px-2 text-xs font-semibold whitespace-nowrap",
        toneClass[tone],
      )}
    >
      {children}
    </span>
  );
}
