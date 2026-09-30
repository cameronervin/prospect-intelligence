import { ProspectApiError, type RunReview } from "../api/client";

export type ReviewFocusTarget = "subject" | "retry" | "refresh" | "alert";

export type ReviewFailure = {
  title: string;
  message: string;
  focus: ReviewFocusTarget;
  retry?: RunReview;
  refresh?: boolean;
  restore?: boolean;
  final?: boolean;
};

/** Map typed API failures to actionable copy; server messages are never shown verbatim. */
export function describeReviewFailure(error: unknown, review: RunReview): ReviewFailure {
  const code = error instanceof ProspectApiError ? error.code : undefined;
  if (code === "conflict" && review.decision === "edit") {
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

export const refreshFailure: ReviewFailure = {
  title: "The run couldn't be refreshed",
  message: "Check your connection and try again. Nothing was sent.",
  focus: "refresh",
  refresh: true,
};
