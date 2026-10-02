import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReviewCheckpoint } from "@/components/console/review-checkpoint";

const accountDraft = {
  subject: "A regional freight conversation",
  body: "Hi Priya,\n\nI’m Alex, and I work with an asset-based carrier. Atlas Foods’ regional expansion may create a useful lane opportunity.\n\nWould a short conversation next week be useful?",
};

describe("ReviewCheckpoint outreach editor", () => {
  it("shows the account-specific multiline draft in a practical editor", () => {
    render(
      <ReviewCheckpoint
        accountName="Atlas Foods"
        outreach={accountDraft}
        toolCallId="review-1"
        onDecision={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Review the outreach to Atlas Foods" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Message")).toHaveValue(accountDraft.body);
    expect(screen.getByLabelText("Message")).toHaveAttribute("rows", "8");
  });

  it("submits paragraph breaks exactly as the rep entered them", async () => {
    const onDecision = vi.fn().mockResolvedValue(undefined);
    const editedBody =
      "Hi Priya,\n\nAtlas Foods may have a useful regional lane opportunity.\n\nWould Tuesday work for a short conversation?";
    render(
      <ReviewCheckpoint
        accountName="Atlas Foods"
        outreach={accountDraft}
        toolCallId="review-1"
        onDecision={onDecision}
        onRefresh={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Message"), { target: { value: editedBody } });
    fireEvent.click(screen.getByRole("button", { name: "Submit edit" }));

    await waitFor(() =>
      expect(onDecision).toHaveBeenCalledWith({
        decision: "edit",
        subject: accountDraft.subject,
        body: editedBody,
        tool_call_id: "review-1",
      }),
    );
  });
});
