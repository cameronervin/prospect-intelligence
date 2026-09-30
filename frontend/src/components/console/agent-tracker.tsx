"use client";

import { useEffect, useId, useState } from "react";

import type { RunStep } from "@/lib/prospect-api";
import { cn } from "@/lib/utils";

import { StatusPill, type StatusTone } from "./status-pill";

const statusLabel: Record<RunStep["status"], string> = {
  pending: "Pending",
  running: "Running",
  complete: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

const statusTone: Record<RunStep["status"], StatusTone> = {
  pending: "neutral",
  running: "active",
  complete: "ready",
  failed: "danger",
  skipped: "neutral",
};

const activityTime = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  timeZoneName: "short",
});

function parse(value: string | null | undefined): number | undefined {
  if (!value) return undefined;
  const time = Date.parse(value);
  return Number.isNaN(time) ? undefined : time;
}

export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function stepElapsed(step: RunStep, now: number): string {
  const started = parse(step.started_at);
  if (started === undefined) return "—";
  const finished = parse(step.finished_at);
  if (step.status === "running") return formatElapsed(now - started);
  return finished === undefined ? "—" : formatElapsed(finished - started);
}

/** A 1s clock that only ticks while some step is running. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const tick = () => setNow(Date.now());
    // Resync immediately so a step that just started never shows a stale clock.
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [active]);
  return now;
}

function StepRow({ step, index, now }: Readonly<{ step: RunStep; index: number; now: number }>) {
  // null until the rep chooses; the running step is open by default.
  const [choice, setChoice] = useState<boolean | null>(null);
  const activityId = useId();
  const open = step.activity.length > 0 && (choice ?? step.status === "running");
  const idle = step.status === "pending" || step.status === "skipped";
  const label =
    step.key === "review" && step.status === "running"
      ? "Waiting on you"
      : statusLabel[step.status];

  return (
    <li
      aria-label={`Step ${index + 1}: ${step.label}, ${label}`}
      className="border-line border-b py-3 last:border-b-0"
    >
      <div className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto_3rem] items-center gap-x-3">
        <span
          aria-hidden="true"
          className={cn(
            "grid size-6 place-items-center rounded-full text-xs font-semibold tabular-nums",
            step.status === "running"
              ? "bg-background text-foreground ring-foreground ring-2 ring-inset"
              : step.status === "complete"
                ? "bg-ready-soft text-ready"
                : "bg-surface text-foreground-faint ring-line-strong ring-1 ring-inset",
          )}
        >
          {index + 1}
        </span>
        <span className="flex min-w-0 flex-wrap items-center gap-x-2">
          <span
            className={cn("text-[0.9375rem]", idle ? "text-foreground-faint" : "font-semibold")}
          >
            {step.label}
          </span>
          {step.activity.length > 0 ? (
            <button
              type="button"
              className="btn-link type-utility"
              aria-label={`${step.activity.length} source ${step.activity.length === 1 ? "call" : "calls"} for ${step.label}`}
              aria-expanded={open}
              aria-controls={open ? activityId : undefined}
              onClick={() => setChoice(!open)}
            >
              {`${step.activity.length} source ${step.activity.length === 1 ? "call" : "calls"}`}
            </button>
          ) : null}
        </span>
        <StatusPill
          tone={
            step.key === "review" && step.status === "running" ? "review" : statusTone[step.status]
          }
        >
          {label}
        </StatusPill>
        <span
          data-elapsed
          aria-hidden={step.status === "running" || undefined}
          className="type-utility text-right tabular-nums"
        >
          {stepElapsed(step, now)}
        </span>
      </div>
      {open ? (
        <ol id={activityId} className="border-line-strong mt-2 ml-9 border-l pl-3">
          {step.activity.map((item, position) => (
            <li
              key={`${item.at}-${item.source}-${position}`}
              className="grid grid-cols-[5.5rem_minmax(0,1fr)_auto] items-center gap-x-3 py-1 text-sm"
            >
              <span className="type-utility tabular-nums">
                {activityTime.format(new Date(item.at))}
              </span>
              <span>{item.source}</span>
              <StatusPill tone={item.outcome === "ok" ? "ready" : "degraded"}>
                {item.outcome === "ok" ? "OK" : "Unavailable"}
              </StatusPill>
            </li>
          ))}
        </ol>
      ) : null}
    </li>
  );
}

/** Live specialist progress: which agent is working and what it has looked at so far. */
export function AgentTracker({ steps }: Readonly<{ steps: RunStep[] }>) {
  const headingId = useId();
  const now = useNow(steps.some((step) => step.status === "running"));
  return (
    <section
      aria-labelledby={headingId}
      className="border-line-strong rounded-md border px-4 pt-3 pb-1 sm:px-6"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pb-1">
        <h2 id={headingId} className="type-heading">
          Agent progress
        </h2>
        <p className="type-utility">
          The orchestrator delegates to four specialists, then pauses for your review.
        </p>
      </div>
      <ol>
        {steps.map((step, index) => (
          <StepRow key={step.key} step={step} index={index} now={now} />
        ))}
      </ol>
    </section>
  );
}

/** One-line record of a finished run that expands back into the full tracker. */
export function AgentRunSummary({ steps }: Readonly<{ steps: RunStep[] }>) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  if (steps.length === 0) return null;

  const agentSteps = steps.filter((step) => step.key !== "review");
  const done = agentSteps.filter((step) => step.status === "complete").length;
  const failed = agentSteps.filter((step) => step.status === "failed").length;
  const counted =
    done === agentSteps.length
      ? `${done} ${done === 1 ? "step" : "steps"}`
      : `${done} of ${agentSteps.length} steps`;
  const starts = agentSteps.map((step) => parse(step.started_at)).filter((t) => t !== undefined);
  const ends = agentSteps.map((step) => parse(step.finished_at)).filter((t) => t !== undefined);
  const duration =
    starts.length > 0 && ends.length > 0
      ? formatElapsed(Math.max(...ends) - Math.min(...starts))
      : "—";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-3">
        <span className="type-utility tabular-nums">{`Agent run · ${counted}${failed > 0 ? ` · ${failed} failed` : ""} · ${duration}`}</span>
        <button
          type="button"
          className="btn-link type-utility"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide steps" : "View steps"}
        </button>
      </div>
      {open ? (
        <div id={panelId}>
          <AgentTracker steps={steps} />
        </div>
      ) : null}
    </div>
  );
}
