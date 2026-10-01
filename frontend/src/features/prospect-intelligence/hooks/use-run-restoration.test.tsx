import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProspectApiError, type ProspectClient } from "@/features/prospect-intelligence/api/client";
import type { Account } from "@/features/prospect-intelligence/api/schemas";
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
