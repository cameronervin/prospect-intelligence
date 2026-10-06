"use client";

import { useId, useState } from "react";

import { linkButton, typeStyles } from "@/components/ui/styles";
import type { Evidence, SourceCoverage as Coverage } from "@/lib/prospect-api";

import {
  coverageStatusLabel,
  formatRetrievedDate,
  formatRetrievedTimestamp,
  visibleEvidenceClaim,
  visibleSourceLabel,
  visibleSourceModeLabel,
} from "./format";
import { StatusPill, type StatusTone } from "./status-pill";

const statusTone: Record<Coverage["status"], StatusTone> = {
  complete: "ready",
  degraded: "degraded",
  unavailable: "danger",
};

function CoverageRow({ item }: Readonly<{ item: Coverage }>) {
  const mode = item.mode ? visibleSourceModeLabel(item.mode) : "Mode not reported";

  return (
    <li className="flex flex-wrap items-start gap-x-4 gap-y-1 border-b border-slate-200 py-2 last:border-b-0">
      <span className="min-w-0 flex-1 text-sm font-medium">{visibleSourceLabel(item.source)}</span>
      <StatusPill tone={statusTone[item.status]}>{coverageStatusLabel[item.status]}</StatusPill>
      {mode || item.detail ? (
        <span className={`${typeStyles.utility} w-full`}>
          {mode ? <span>{mode}</span> : null}
          {mode && item.detail ? " · " : null}
          {item.detail ? <span>{item.detail}</span> : null}
        </span>
      ) : null}
    </li>
  );
}

function RunEvidence({ evidence }: Readonly<{ evidence: Evidence[] }>) {
  const headingId = useId();
  const grouped = new Map<string, Evidence[]>();
  for (const item of evidence) {
    const items = grouped.get(item.source) ?? [];
    items.push(item);
    grouped.set(item.source, items);
  }

  if (evidence.length === 0) return null;

  return (
    <section aria-labelledby={headingId} className="mt-4 border-t border-slate-200 pt-4">
      <h3 id={headingId} className={typeStyles.section}>
        Run evidence
      </h3>
      <div className="mt-1 flex flex-col gap-3">
        {[...grouped.entries()].map(([source, items]) => (
          <div key={source} role="group" aria-label={visibleSourceLabel(source)}>
            <h4 className="text-sm font-semibold">{visibleSourceLabel(source)}</h4>
            <ul>
              {items.map((item) => {
                const metadata = [
                  visibleSourceModeLabel(item.mode),
                  `Retrieved ${formatRetrievedDate(item.retrieved_at)}`,
                ].filter((value): value is string => Boolean(value));
                return (
                  <li
                    key={item.citation_id}
                    className="flex flex-col gap-0.5 border-b border-slate-200 py-2 last:border-b-0"
                  >
                    <span className="text-sm">{visibleEvidenceClaim(item.claim)}</span>
                    <span
                      className={typeStyles.utility}
                      title={formatRetrievedTimestamp(item.retrieved_at)}
                    >
                      {metadata.join(" · ")}
                    </span>
                    <span className={`${typeStyles.utility} break-all text-slate-500`}>
                      {`${item.citation_id} · ${item.source_version} · ${item.evidence_location} · ${item.endpoint_or_artifact}`}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Problem sources stay visible; complete sources collapse behind one control. */
export function SourceCoverage({
  coverage,
  evidence = [],
}: Readonly<{ coverage: Coverage[]; evidence?: Evidence[] }>) {
  const [showAll, setShowAll] = useState(false);
  const listId = useId();
  const headingId = useId();
  if (coverage.length === 0 && evidence.length === 0) return null;

  const problems = coverage.filter((item) => item.status !== "complete");
  const complete = coverage.filter((item) => item.status === "complete");
  const visible = showAll ? [...problems, ...complete] : problems;

  return (
    <section aria-labelledby={headingId} className="border-t border-slate-200 pt-4">
      {coverage.length > 0 ? (
        <>
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
        </>
      ) : (
        <h3 id={headingId} className="sr-only">
          Research evidence
        </h3>
      )}
      <RunEvidence evidence={evidence} />
    </section>
  );
}
