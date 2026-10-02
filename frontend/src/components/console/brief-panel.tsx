"use client";

import { useId, useState } from "react";

import { linkButton, typeStyles } from "@/components/ui/styles";
import type { Brief, ProspectRun } from "@/lib/prospect-api";
import { cn } from "@/lib/utils";

import {
  formatCompactCurrency,
  formatCompactMiles,
  formatCurrency,
  formatMiles,
  formatScore,
  recommendedActionLabel,
  verdictLabel,
} from "./format";
import { StatusPill } from "./status-pill";

type Verdict = NonNullable<ProspectRun["verdict"]>;

function Figure({
  value,
  exact,
  label,
}: Readonly<{ value: string; exact: string; label: string }>) {
  return (
    <div>
      <data value={exact} title={exact} className={`${typeStyles.figure} block`}>
        <span aria-hidden="true">{value}</span>
        <span className="sr-only">{exact}</span>
      </data>
      <span className={typeStyles.utility}>{label}</span>
    </div>
  );
}

function Figures({ brief }: Readonly<{ brief: Brief }>) {
  return (
    <div className="flex flex-wrap gap-x-8 gap-y-3">
      <Figure
        value={formatCompactCurrency(brief.modeled_annual_revenue)}
        exact={formatCurrency(brief.modeled_annual_revenue)}
        label="Modeled gross revenue / yr"
      />
      <Figure
        value={formatCompactMiles(brief.deadhead_miles_avoided)}
        exact={formatMiles(brief.deadhead_miles_avoided)}
        label="Modeled deadhead avoided / yr"
      />
    </div>
  );
}

function VerdictLine({ brief, verdict }: Readonly<{ brief: Brief; verdict: Verdict }>) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <StatusPill tone={verdict === "fit" ? "ready" : "neutral"}>
        {verdictLabel[verdict]}
      </StatusPill>
      <p className={typeStyles.lead}>{recommendedActionLabel[brief.recommended_next_step_code]}</p>
    </div>
  );
}

/** Compact rationale shown beside the outreach editor while a decision is pending. */
export function WhySummary({
  brief,
  verdict,
  evidenceId,
}: Readonly<{ brief: Brief; verdict: Verdict; evidenceId: string }>) {
  const headingId = useId();
  const lead = brief.lanes[0];
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3.5">
      <h3 id={headingId} className={cn(typeStyles.section, "text-orange-800")}>
        Why this account
      </h3>
      <VerdictLine brief={brief} verdict={verdict} />
      <p className="text-sm leading-6 text-slate-700">{brief.summary}</p>
      <p className="text-sm leading-6">{brief.recommended_next_step}</p>
      {brief.lanes.length > 0 ? <Figures brief={brief} /> : null}
      {lead ? (
        <p className="flex items-baseline justify-between gap-3 border-t border-orange-200 pt-2 text-sm font-semibold">
          <span>{`${lead.origin} → ${lead.destination}`}</span>
          <span className="tabular-nums">{`${formatScore(lead.fit_score)} fit`}</span>
        </p>
      ) : null}
      <a href={`#${evidenceId}`} className={`${linkButton} self-start`}>
        Check lanes and evidence ↓
      </a>
    </section>
  );
}

/** The brief as the page's lead content when no decision is pending. */
export function BriefPanel({
  brief,
  verdict,
  showRecommendedNextStep = true,
}: Readonly<{ brief: Brief; verdict: Verdict; showRecommendedNextStep?: boolean }>) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h3 id={headingId} className="sr-only">
        Verdict
      </h3>
      <VerdictLine brief={brief} verdict={verdict} />
      <p className={cn(typeStyles.body, "max-w-prose text-slate-700")}>{brief.summary}</p>
      {showRecommendedNextStep ? (
        <p className={`${typeStyles.body} max-w-prose`}>{brief.recommended_next_step}</p>
      ) : null}
      {brief.lanes.length > 0 ? <Figures brief={brief} /> : null}
    </section>
  );
}

export function ModelAssumptions() {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <div>
      <button
        type="button"
        className={linkButton}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        Model assumptions
      </button>
      {open ? (
        <div id={panelId} className={`${typeStyles.utility} flex max-w-prose flex-col gap-1 pb-2`}>
          <p>Internal model: estimates, not booked revenue or margin.</p>
          <p>
            Modeled gross revenue = matched loads per week × estimated rate per load × 52 weeks.
          </p>
          <p>
            Modeled deadhead avoided = matched loads per week × the full origin-to-destination lane
            distance × 52 weeks.
          </p>
          <p>Fit = 0.5 × backhaul fill + 0.3 × density + 0.2 × equipment match.</p>
        </div>
      ) : null}
    </div>
  );
}
