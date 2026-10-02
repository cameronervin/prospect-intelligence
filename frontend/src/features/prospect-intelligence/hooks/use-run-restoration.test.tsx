import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProspectApiError, type ProspectClient } from "@/features/prospect-intelligence/api/client";
import type { Account, ProspectRun } from "@/features/prospect-intelligence/api/schemas";
import { useRunRestoration } from "@/features/prospect-intelligence/hooks/use-run-restoration";
import { ACTIVE_RUN_STORAGE_KEY } from "@/features/prospect-intelligence/run/constants";

const account: Account = {
  id: "acme-foods",
  name: "Acme Foods",
  relationship: "Prospect",
  industry: "Food distribution",
  location: "Dallas, TX",
};

afterEach(() => window.sessionStorage.clear());

describe("useRunRestoration", () => {
  it.each(["no_fit", "needs_more_data"] as const)(
    "clears a stored completed %s run instead of restoring it",
    async (verdict) => {
      const run = {
        id: `${verdict}-run`,
        account: { id: account.id, name: account.name },
        status: "completed",
        stage: verdict === "no_fit" ? "No network fit found" : "More freight evidence needed",
        progress_percent: 100,
        steps: [],
        source_coverage: [],
        evidence: [],
        verdict,
        brief: null,
        outreach: null,
        pending_review: null,
      } satisfies ProspectRun;
      window.sessionStorage.setItem(`${ACTIVE_RUN_STORAGE_KEY}:test-user`, run.id);
      const show = vi.fn();
      const api: ProspectClient = {
        listAccounts: vi.fn(),
        startRun: vi.fn(),
        getRun: vi.fn().mockResolvedValue(run),
        reviewRun: vi.fn(),
      };

      const { result } = renderHook(() =>
        useRunRestoration({
          accounts: { kind: "ready", accounts: [account] },
          api,
          show,
          selectAccount: vi.fn(),
        }),
      );

      await waitFor(() =>
        expect(
          window.sessionStorage.getItem(`${ACTIVE_RUN_STORAGE_KEY}:test-user`),
        ).toBeNull(),
      );
      expect(result.current.restoring).toBe(false);
      expect(show).not.toHaveBeenCalled();
    },
  );

  it("clears an authoritative stale run id instead of permanently locking navigation", async () => {
    window.sessionStorage.setItem(ACTIVE_RUN_STORAGE_KEY, "missing-run");
    const api: ProspectClient = {
      listAccounts: vi.fn(),
      startRun: vi.fn(),
      getRun: vi
        .fn()
        .mockRejectedValue(
          new ProspectApiError("Run not found", { code: "not_found", retryable: false }),
        ),
      reviewRun: vi.fn(),
    };

    const { result } = renderHook(() =>
      useRunRestoration({
        accounts: { kind: "ready", accounts: [account] },
        api,
        show: vi.fn(),
        selectAccount: vi.fn(),
      }),
    );

    await waitFor(() => expect(result.current.restoring).toBe(false));
    expect(result.current.restoreFailed).toBe(false);
    expect(window.sessionStorage.getItem(ACTIVE_RUN_STORAGE_KEY)).toBeNull();
  });
});
