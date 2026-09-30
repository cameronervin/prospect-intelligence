import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type StatusTone = "ready" | "degraded" | "danger" | "review" | "active" | "neutral";

const toneClass: Record<StatusTone, string> = {
  ready: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 ring-inset",
  degraded: "bg-amber-50 text-amber-700 ring-1 ring-amber-200 ring-inset",
  danger: "bg-red-50 text-red-700 ring-1 ring-red-200 ring-inset",
  review: "bg-orange-50 text-orange-800 ring-1 ring-orange-200 ring-inset",
  active: "bg-slate-950 text-white",
  neutral: "bg-slate-100 text-slate-700 ring-1 ring-slate-300 ring-inset",
};

/** Pill geometry is reserved for genuine status values. */
export function StatusPill({
  tone,
  children,
}: Readonly<{ tone: StatusTone; children: ReactNode }>) {
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center rounded-full px-2 text-xs font-semibold whitespace-nowrap",
        toneClass[tone],
      )}
    >
      {children}
    </span>
  );
}
