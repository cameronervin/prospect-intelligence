"use client";

import { useId, useState } from "react";

import { linkButton, typeStyles } from "@/components/ui/styles";
import type { SourceCoverage as Coverage } from "@/lib/prospect-api";

import { coverageStatusLabel, sourceModeLabel } from "./format";
import { StatusPill, type StatusTone } from "./status-pill";

const statusTone: Record<Coverage["status"], StatusTone> = {
  complete: "ready",
  degraded: "degraded",
  unavailable: "danger",
};

function CoverageRow({ item }: Readonly<{ item: Coverage }>) {
  return (
    <li className="flex flex-wrap items-start gap-x-4 gap-y-1 border-b border-slate-200 py-2 last:border-b-0">
      <span className="min-w-0 flex-1 text-sm font-medium">{item.source}</span>
      <StatusPill tone={statusTone[item.status]}>{coverageStatusLabel[item.status]}</StatusPill>
      <span className={`${typeStyles.utility} w-full`}>
        <span>{item.mode ? sourceModeLabel[item.mode] : "Mode not reported"}</span>
        {item.detail ? (
          <>
            {" · "}
            <span>{item.detail}</span>
          </>
        ) : null}
      </span>
    </li>
  );
}

/** Problem sources stay visible; complete sources collapse behind one control. */
export function SourceCoverage({ coverage }: Readonly<{ coverage: Coverage[] }>) {
  const [showAll, setShowAll] = useState(false);
  const listId = useId();
  const headingId = useId();
  if (coverage.length === 0) return null;

  const problems = coverage.filter((item) => item.status !== "complete");
  const complete = coverage.filter((item) => item.status === "complete");
  const visible = showAll ? [...problems, ...complete] : problems;

  return (
    <section aria-labelledby={headingId} className="border-t border-slate-200 pt-4">
      <div className="flex flex-wrap items-center gap-x-3">
        <h3 id={headingId} className={typeStyles.section}>
          Sources
        </h3>
        <span className={typeStyles.utility}>
          {problems.length === 0
            ? `All ${coverage.length} complete`
            : `${complete.length} of ${coverage.length} complete`}
        </span>
        {complete.length > 0 ? (
          <button
            type="button"
            className={`${linkButton} ml-auto`}
            aria-expanded={showAll}
            aria-controls={listId}
            onClick={() => setShowAll((value) => !value)}
          >
            {showAll ? "Hide complete sources" : `Show all ${coverage.length} sources`}
          </button>
        ) : null}
      </div>
      <ul id={listId} className="mt-1">
        {visible.map((item) => (
          <CoverageRow key={item.source} item={item} />
        ))}
      </ul>
    </section>
  );
}
