"use client";

import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import { ProspectApiError, type RunReview } from "@/lib/prospect-api";

type Draft = { subject: string; body: string };
type FocusTarget = "subject" | "retry" | "refresh" | "alert";

export type Failure = {
  title: string;
  message: string;
  focus: FocusTarget;
  retry?: RunReview;
  refresh?: boolean;
  restore?: boolean;
  final?: boolean;
};

/** Map typed API failures to actionable copy; server messages are never shown verbatim. */
export function describeReviewFailure(error: unknown, review: RunReview): Failure {
  const code = error instanceof ProspectApiError ? error.code : undefined;
  if (code === "conflict" && review.decision === "edit") {
    // A 409 on an edit is usually unsafe copy, but can also mean the run was decided elsewhere.
    return {
      title: "This edit can't be sent",
      message:
        "Customer copy must match an approved template and can't include internal numbers or sources. Your draft is kept below. If this run was already decided elsewhere, refresh it.",
      focus: "subject",
      restore: true,
      refresh: true,
    };
  }
  if (code === "conflict") {
    return {
      title: "This run already has a different decision",
      message: "Refresh to see its current state. Nothing new was sent.",
      focus: "refresh",
      refresh: true,
    };
  }
  if (code === "validation_error" && review.decision === "edit") {
    return {
      title: "Check the subject and message",
      message: "Both are required and must stay within the length limit. Your draft is kept below.",
      focus: "subject",
      restore: true,
    };
  }
  if (code === "not_found") {
    return {
      title: "This run is no longer available",
      message: "It may have been removed or belongs to another rep. Nothing was sent.",
      focus: "alert",
      final: true,
    };
  }
  if (code === "validation_error") {
    return {
      title: "This decision couldn't be recorded",
      message: "Refresh the run and try again. Nothing was sent.",
      focus: "refresh",
      refresh: true,
    };
  }
  return {
    title: "Your decision wasn't recorded",
    message:
      "The review service is temporarily unavailable. Nothing was sent, and your draft is unchanged.",
    focus: "retry",
    retry: review,
  };
}

const refreshFailure: Failure = {
  title: "The run couldn't be refreshed",
  message: "Check your connection and try again. Nothing was sent.",
  focus: "refresh",
  refresh: true,
};

/**
 * The human-review checkpoint: the page's primary task while a decision is pending.
 * `rationale` renders beside the editor inside the same frame.
 */
export function ReviewCheckpoint({
  accountName,
  outreach,
  toolCallId,
  rationale,
  onDecision,
  onRefresh,
}: Readonly<{
  accountName: string;
  outreach: Draft;
  toolCallId: string;
  rationale?: ReactNode;
  onDecision: (review: RunReview) => Promise<void>;
  onRefresh: () => Promise<void>;
}>) {
  const [draft, setDraft] = useState<Draft>(outreach);
  const [pending, setPending] = useState(false);
  const [confirmingReject, setConfirmingReject] = useState(false);
  const [failure, setFailure] = useState<Failure>();
  const focusTarget = useRef<FocusTarget | "reject" | "confirm">(undefined);
  const inFlight = useRef(false);
  const subjectRef = useRef<HTMLInputElement>(null);
  const retryRef = useRef<HTMLButtonElement>(null);
  const refreshRef = useRef<HTMLButtonElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const rejectRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  const edited = draft.subject !== outreach.subject || draft.body !== outreach.body;
  const ids = useId();
  const headingId = `${ids}-heading`;
  const failureId = `${ids}-failure`;
  const rejectNoteId = `${ids}-reject-note`;
  const fieldsInvalid = failure?.focus === "subject";
  const locked = pending || Boolean(failure?.final);

  // Move focus after the render that follows a response or a mode change.
  useEffect(() => {
    if (!focusTarget.current) return;
    const target = {
      subject: subjectRef,
      retry: retryRef,
      refresh: refreshRef,
      alert: alertRef,
      reject: rejectRef,
      confirm: confirmRef,
    }[focusTarget.current];
    focusTarget.current = undefined;
    target.current?.focus();
  });

  /** Busy work keeps the alert mounted so focus stays on its (now busy) control. */
  async function run(
    work: () => Promise<void>,
    onError: (error: unknown) => Failure,
    keep = false,
  ) {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    if (!keep) setFailure(undefined);
    try {
      await work();
      setFailure(undefined);
    } catch (error) {
      const next = onError(error);
      setConfirmingReject(false);
      setFailure(next);
      focusTarget.current = next.focus;
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  function submit(review: RunReview, keep = false) {
    return run(
      () => onDecision(review),
      (error) => describeReviewFailure(error, review),
      keep,
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (locked) return;
    void submit(
      edited
        ? { decision: "edit", subject: draft.subject, body: draft.body, tool_call_id: toolCallId }
        : { decision: "approve", tool_call_id: toolCallId },
    );
  }

  function change(next: Draft) {
    setDraft(next);
    // A stored retry would resend the old draft; drop it once the rep changes the text.
    if (failure?.retry) setFailure(undefined);
  }

  function restore() {
    setDraft(outreach);
    setFailure(undefined);
    focusTarget.current = "subject";
  }

  return (
    <div className="border-accent bg-background grid rounded-md border lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <section aria-labelledby={headingId} className="flex flex-col gap-4 p-4 sm:p-6">
        <div>
          <h2 id={headingId} className="type-heading">
            {confirmingReject ? "Reject this draft?" : `Review the outreach to ${accountName}`}
          </h2>
          <p className="text-foreground-soft mt-1 text-sm">
            Approve it as written or correct it. Sending is simulated: no email or CRM write.
          </p>
        </div>

        <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
          {failure ? (
            <div role="alert" ref={alertRef} tabIndex={-1} className="alert">
              <p className="font-semibold">{failure.title}</p>
              <p id={failureId} className="type-utility text-foreground-soft">
                {failure.message}
              </p>
              {failure.retry || failure.refresh || (failure.restore && edited) ? (
                <div className="mt-1.5 flex flex-wrap gap-2">
                  {failure.retry ? (
                    <button
                      ref={retryRef}
                      type="button"
                      className="btn-secondary"
                      aria-disabled={pending}
                      onClick={() => {
                        if (!pending && failure.retry) void submit(failure.retry, true);
                      }}
                    >
                      {pending ? "Retrying…" : "Retry decision"}
                    </button>
                  ) : null}
                  {failure.restore && edited ? (
                    <button type="button" className="btn-secondary" onClick={restore}>
                      Restore original draft
                    </button>
                  ) : null}
                  {failure.refresh ? (
                    <button
                      ref={refreshRef}
                      type="button"
                      className="btn-secondary"
                      aria-disabled={pending}
                      onClick={() => {
                        if (!pending) void run(onRefresh, () => refreshFailure, true);
                      }}
                    >
                      Refresh run
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          <div>
            <label htmlFor={`${ids}-subject`} className="field-label">
              Subject
            </label>
            <input
              id={`${ids}-subject`}
              ref={subjectRef}
              className="field"
              value={draft.subject}
              maxLength={200}
              readOnly={Boolean(failure?.final)}
              aria-invalid={fieldsInvalid || undefined}
              aria-describedby={fieldsInvalid ? failureId : undefined}
              onChange={(event) => change({ ...draft, subject: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor={`${ids}-body`} className="field-label">
              Message
            </label>
            <textarea
              id={`${ids}-body`}
              className="field resize-y"
              rows={4}
              value={draft.body}
              maxLength={10000}
              readOnly={Boolean(failure?.final)}
              aria-invalid={fieldsInvalid || undefined}
              aria-describedby={fieldsInvalid ? failureId : undefined}
              onChange={(event) => change({ ...draft, body: event.target.value })}
            />
          </div>

          {confirmingReject ? (
            <div className="flex flex-col gap-3">
              <p id={rejectNoteId} className="text-sm">
                Rejecting is final for this run. No message will be sent.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  ref={confirmRef}
                  type="button"
                  className="btn-danger"
                  aria-describedby={rejectNoteId}
                  disabled={locked}
                  onClick={() => void submit({ decision: "reject", tool_call_id: toolCallId })}
                >
                  {pending ? "Recording decision…" : "Reject draft"}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={pending}
                  onClick={() => {
                    setConfirmingReject(false);
                    focusTarget.current = "reject";
                  }}
                >
                  Keep reviewing
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <button type="submit" className="btn-accent btn-lg" disabled={locked}>
                {pending
                  ? "Recording decision…"
                  : edited
                    ? "Submit edit"
                    : "Approve simulated send"}
              </button>
              <button
                ref={rejectRef}
                type="button"
                className="btn-secondary btn-lg"
                disabled={locked}
                onClick={() => {
                  setFailure(undefined);
                  setConfirmingReject(true);
                  focusTarget.current = "confirm";
                }}
              >
                Reject…
              </button>
              <span className="type-utility">
                {edited
                  ? "Your correction replaces the draft."
                  : "Edit either field to correct it."}
              </span>
            </div>
          )}
        </form>
      </section>
      {rationale ? (
        <div className="bg-accent-soft border-accent-line rounded-b-md border-t p-4 sm:p-6 lg:rounded-r-md lg:rounded-bl-none lg:border-t-0 lg:border-l">
          {rationale}
        </div>
      ) : null}
    </div>
  );
}
