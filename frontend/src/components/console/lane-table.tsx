"use client";

import { Fragment, useId, useState } from "react";

import type { Evidence, Lane } from "@/lib/prospect-api";

import {
  formatCurrency,
  formatMiles,
  formatNumber,
  formatRetrievedDate,
  formatRetrievedTimestamp,
  formatScore,
  sourceModeLabel,
} from "./format";

function EvidenceItem({ item }: Readonly<{ item: Evidence }>) {
  return (
    <li className="border-line flex flex-col gap-0.5 border-b py-2 last:border-b-0">
      <span className="text-sm">{item.claim}</span>
      <span className="type-utility" title={formatRetrievedTimestamp(item.retrieved_at)}>
        {`${item.source} · ${sourceModeLabel[item.mode]} · Retrieved ${formatRetrievedDate(item.retrieved_at)}`}
      </span>
      <span className="type-utility text-foreground-faint break-all">
        {`${item.source_version} · ${item.evidence_location} · ${item.endpoint_or_artifact}`}
      </span>
    </li>
  );
}

function LaneDetails({ lane }: Readonly<{ lane: Lane }>) {
  const facts: [string, string, string?][] = [
    ["Backhaul fill", formatScore(lane.backhaul_fill)],
    ["Density", formatScore(lane.density)],
    ["Equipment match", formatScore(lane.equipment_match)],
    ["Shipper volume", `${formatNumber(lane.shipper_loads_per_week)} / wk`],
    ["Matched loads", `${formatNumber(lane.matched_loads_per_week)} / wk`, "sm:hidden"],
    ["Modeled revenue", formatCurrency(lane.modeled_annual_revenue), "sm:hidden"],
    ["Modeled deadhead avoided", formatMiles(lane.deadhead_miles_avoided)],
  ];
  return (
    <div className="flex flex-col gap-2 pb-4">
      <dl className="flex flex-wrap gap-x-6 gap-y-1">
        {facts.map(([label, value, className]) => (
          <div key={label} className={`flex gap-1.5 ${className ?? ""}`}>
            <dt className="type-utility">{label}</dt>
            <dd className="text-xs font-semibold tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      {lane.evidence.length > 0 ? (
        <ul aria-label="Evidence" className="border-line border-t">
          {lane.evidence.map((item) => (
            <EvidenceItem
              key={`${item.source}-${item.evidence_location}-${item.claim}`}
              item={item}
            />
          ))}
        </ul>
      ) : (
        <p className="type-utility">No evidence items were returned for this lane.</p>
      )}
    </div>
  );
}

/** The lane manifest: route, fit, volume and value first; the rest opens under the row. */
export function LaneTable({ lanes }: Readonly<{ lanes: Lane[] }>) {
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(() => new Set([0]));
  const baseId = useId();

  function toggle(index: number) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <section className="flex flex-col gap-1">
      <h3 id={`${baseId}-heading`} className="type-section">
        Top lanes
      </h3>
      <table
        aria-labelledby={`${baseId}-heading`}
        className="w-full border-collapse text-sm [&>tbody>tr:last-child]:border-b-0"
      >
        <thead>
          <tr className="border-line-strong border-b">
            <th scope="col" className="th text-left">
              Lane
            </th>
            <th scope="col" className="th text-right">
              Fit
            </th>
            <th scope="col" className="th hidden text-right sm:table-cell">
              Matched loads
            </th>
            <th scope="col" className="th hidden text-right sm:table-cell">
              Modeled revenue
            </th>
            <th scope="col" className="th w-10">
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {lanes.map((lane, index) => {
            const name = `${lane.origin} → ${lane.destination}`;
            const open = expanded.has(index);
            const detailsId = `${baseId}-lane-${index}`;
            return (
              <Fragment key={name}>
                <tr className={open ? "" : "border-line border-b"}>
                  <th scope="row" className="py-3 pr-3 text-left font-semibold">
                    {name}
                  </th>
                  <td className="py-3 pl-3 text-right font-semibold tabular-nums">
                    {formatScore(lane.fit_score)}
                  </td>
                  <td className="hidden py-3 pl-3 text-right tabular-nums sm:table-cell">
                    {`${formatNumber(lane.matched_loads_per_week)} / wk`}
                  </td>
                  <td className="hidden py-3 pl-3 text-right tabular-nums sm:table-cell">
                    {formatCurrency(lane.modeled_annual_revenue)}
                  </td>
                  <td className="py-1 text-right">
                    <button
                      type="button"
                      className="btn-icon"
                      aria-expanded={open}
                      aria-controls={open ? detailsId : undefined}
                      aria-label={`Details for ${name}`}
                      onClick={() => toggle(index)}
                    >
                      <span aria-hidden="true" className="text-base leading-none">
                        {open ? "▾" : "▸"}
                      </span>
                    </button>
                  </td>
                </tr>
                {open ? (
                  <tr id={detailsId} className="border-line border-b">
                    <td colSpan={5}>
                      <LaneDetails lane={lane} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
