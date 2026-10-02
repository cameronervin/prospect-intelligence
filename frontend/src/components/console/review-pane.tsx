"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

import { typeStyles } from "@/components/ui/styles";
import type { ProspectRun } from "@/lib/prospect-api";
import { cn } from "@/lib/utils";

function Outcome({
  title,
  tone,
  focusOnMount,
  children,
}: Readonly<{
  title: string;
  tone: "ready" | "neutral";
  focusOnMount: boolean;
  children: ReactNode;
}>) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  useEffect(() => {
    if (focusOnMount) headingRef.current?.focus();
  }, [focusOnMount]);

  return (
    <section
      aria-labelledby={headingId}
      className={cn(
        "rounded border p-4 sm:px-6",
        tone === "ready" ? "border-emerald-300 bg-emerald-50" : "border-slate-300 bg-slate-50",
      )}
    >
      <h2 id={headingId} ref={headingRef} tabIndex={-1} className={typeStyles.heading}>
        {title}
      </h2>
      <div className="mt-1 flex flex-col gap-0.5">{children}</div>
    </section>
  );
}

/** The decision's outcome, shown in the same top slot the checkpoint occupied. */
export function ReviewOutcome({ run, decided }: Readonly<{ run: ProspectRun; decided: boolean }>) {
  if (run.status === "completed" && run.verdict === "fit") {
    return (
      <Outcome title="Communications sent" tone="ready" focusOnMount={decided}>
        {run.outreach ? (
          <p className="text-sm">{`“${run.outreach.subject}” was approved.`}</p>
        ) : null}
      </Outcome>
    );
  }
  if (run.status === "rejected") {
    return (
      <Outcome title="Draft rejected" tone="neutral" focusOnMount={decided}>
        <p className="text-sm">No message was sent. Your decision was recorded.</p>
      </Outcome>
    );
  }
  if (run.status === "completed") {
    return <p className={typeStyles.utility}>No outreach was drafted for this outcome.</p>;
  }
  return null;
}
