"use client";

import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import {
  alertStyle,
  buttonStyles,
  fieldLabel,
  fieldStyle,
  largeButton,
  typeStyles,
} from "@/components/ui/styles";
import {
  describeReviewFailure,
  refreshFailure,
  type ReviewFailure,
  type ReviewFocusTarget,
} from "@/features/prospect-intelligence/review/failure-policy";
import type { RunReview } from "@/lib/prospect-api";
import { cn } from "@/lib/utils";

type Draft = { subject: string; body: string };
export { describeReviewFailure };
export type Failure = ReviewFailure;

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
  const [failure, setFailure] = useState<ReviewFailure>();
  const focusTarget = useRef<ReviewFocusTarget | "reject" | "confirm">(undefined);
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
    onError: (error: unknown) => ReviewFailure,
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
    <div className="grid rounded border border-orange-600 bg-white lg:grid-cols-5">
      <section aria-labelledby={headingId} className="flex flex-col gap-4 p-4 sm:p-6 lg:col-span-3">
        <div>
          <h2 id={headingId} className={typeStyles.heading}>
            {confirmingReject ? "Reject this draft?" : `Review the outreach to ${accountName}`}
          </h2>
          <p className="mt-1 text-sm text-slate-700">
            Approve or edit either field to correct the agent.
          </p>
        </div>

        <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
          {failure ? (
            <div role="alert" ref={alertRef} tabIndex={-1} className={alertStyle}>
              <p className="font-semibold">{failure.title}</p>
              <p id={failureId} className={typeStyles.utility}>
                {failure.message}
              </p>
              {failure.retry || failure.refresh || (failure.restore && edited) ? (
                <div className="mt-1.5 flex flex-wrap gap-2">
                  {failure.retry ? (
                    <button
                      ref={retryRef}
                      type="button"
                      className={buttonStyles.secondary}
                      aria-disabled={pending}
                      onClick={() => {
                        if (!pending && failure.retry) void submit(failure.retry, true);
                      }}
                    >
                      {pending ? "Retrying…" : "Retry decision"}
                    </button>
                  ) : null}
                  {failure.restore && edited ? (
                    <button type="button" className={buttonStyles.secondary} onClick={restore}>
                      Restore original draft
                    </button>
                  ) : null}
                  {failure.refresh ? (
                    <button
                      ref={refreshRef}
                      type="button"
                      className={buttonStyles.secondary}
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
            <label htmlFor={`${ids}-subject`} className={fieldLabel}>
              Subject
            </label>
            <input
              id={`${ids}-subject`}
              ref={subjectRef}
              className={fieldStyle}
              value={draft.subject}
              maxLength={200}
              readOnly={Boolean(failure?.final)}
              aria-invalid={fieldsInvalid || undefined}
              aria-describedby={fieldsInvalid ? failureId : undefined}
              onChange={(event) => change({ ...draft, subject: event.target.value })}
            />
          </div>
          <div>
            <label htmlFor={`${ids}-body`} className={fieldLabel}>
              Message
            </label>
            <textarea
              id={`${ids}-body`}
              className={`${fieldStyle} resize-y`}
              rows={8}
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
                  className={buttonStyles.danger}
                  aria-describedby={rejectNoteId}
                  disabled={locked}
                  onClick={() => void submit({ decision: "reject", tool_call_id: toolCallId })}
                >
                  {pending ? "Recording decision…" : "Reject draft"}
                </button>
                <button
                  type="button"
                  className={buttonStyles.secondary}
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
              <button
                type="submit"
                className={cn(buttonStyles.review, largeButton)}
                disabled={locked}
              >
                {pending ? "Recording decision…" : edited ? "Submit edit" : "Approve send"}
              </button>
              <button
                ref={rejectRef}
                type="button"
                className={cn(buttonStyles.secondary, largeButton)}
                disabled={locked}
                onClick={() => {
                  setFailure(undefined);
                  setConfirmingReject(true);
                  focusTarget.current = "confirm";
                }}
              >
                Reject
              </button>
            </div>
          )}
        </form>
      </section>
      {rationale ? (
        <div className="rounded-b border-t border-orange-200 bg-orange-50 p-4 sm:p-6 lg:col-span-2 lg:rounded-r lg:rounded-bl-none lg:border-t-0 lg:border-l">
          {rationale}
        </div>
      ) : null}
    </div>
  );
}
