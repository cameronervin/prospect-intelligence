"use client";

import { useId, useState } from "react";

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
    <li className="border-line grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-0.5 border-b py-2.5 last:border-b-0">
      <span className="text-sm font-medium">{item.source}</span>
      <StatusPill tone={statusTone[item.status]}>{coverageStatusLabel[item.status]}</StatusPill>
      <span className="type-utility col-span-2">
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
    <section aria-labelledby={headingId} className="border-line border-t pt-4">
      <div className="flex flex-wrap items-center gap-x-3">
        <h3 id={headingId} className="type-section">
          Sources
        </h3>
        <span className="type-utility">
          {problems.length === 0
            ? `All ${coverage.length} complete`
            : `${complete.length} of ${coverage.length} complete`}
        </span>
        {complete.length > 0 ? (
          <button
            type="button"
            className="btn-link ml-auto"
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
