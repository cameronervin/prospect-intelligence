import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { replace, refresh } = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh }) }));

import { SessionActivity } from "./session-activity";

describe("SessionActivity", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    replace.mockReset();
    refresh.mockReset();
  });

  it("refreshes on first visible activity and throttles failed attempts", async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetcher);
    render(<SessionActivity />);

    fireEvent.pointerDown(window);
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    fireEvent.keyDown(window, { key: "A" });

    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("returns to login when refresh reports an expired session", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 })),
    );
    render(<SessionActivity />);

    fireEvent.focus(window);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(refresh).toHaveBeenCalledOnce();
  });
});
