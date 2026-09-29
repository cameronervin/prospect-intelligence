import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusPanel } from "@/components/status-panel";

describe("StatusPanel", () => {
  it("announces a ready backend", () => {
    render(<StatusPanel health={{ kind: "ready", checkedAt: "2026-09-28T12:00:00.000Z" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("Foundation ready");
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("explains a degraded backend without exposing an exception", () => {
    render(<StatusPanel health={{ kind: "degraded", checkedAt: "2026-09-28T12:00:00.000Z" }} />);

    expect(screen.getByRole("status")).toHaveTextContent("Backend unavailable");
    expect(screen.getByRole("status")).toHaveTextContent("did not complete successfully");
  });
});
