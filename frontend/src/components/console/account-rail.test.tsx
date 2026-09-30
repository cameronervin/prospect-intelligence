import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountRail, type AccountsState } from "@/components/console/account-rail";
import type { Account } from "@/lib/prospect-api";

function accounts(count: number): Account[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `account-${index + 1}`,
    name: `Account ${index + 1}`,
    relationship: "Prospect" as const,
    industry: "Distribution",
    location: "Dallas, TX",
  }));
}

function renderRail(
  state: AccountsState,
  overrides: Partial<React.ComponentProps<typeof AccountRail>> = {},
) {
  const props: React.ComponentProps<typeof AccountRail> = {
    state,
    page: 1,
    locked: false,
    starting: false,
    startError: false,
    onSelect: vi.fn(),
    onPageChange: vi.fn(),
    onStart: vi.fn(),
    onRetry: vi.fn(),
    onReload: vi.fn(),
    ...overrides,
  };
  const view = render(<AccountRail {...props} />);
  return { ...view, props };
}

describe("AccountRail loading and pagination", () => {
  it("shows five hidden motion-safe row skeletons with one concise status", () => {
    const { container } = renderRail({ kind: "loading" });

    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent("Loading accounts…");
    const rows = container.querySelectorAll('[data-skeleton="account-row"]');
    expect(rows).toHaveLength(5);
    for (const row of rows) {
      expect(row).toHaveAttribute("aria-hidden", "true");
      expect(row.className).toContain("motion-safe:animate-pulse");
    }
  });

  it("shows the visible range and controlled page navigation for more than five accounts", () => {
    const items = accounts(7);
    const onPageChange = vi.fn();
    renderRail(
      { kind: "ready", accounts: items },
      { page: 1, onPageChange, selectedId: items[0]?.id },
    );

    expect(screen.getByText("1–5 of 7 assigned")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Account pages" })).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Page 1 of 2")).toHaveAttribute("aria-atomic", "true");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Account 5/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Account 6/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("moves focus to the first account after a controlled page change", () => {
    const items = accounts(7);
    function Harness() {
      const [page, setPage] = useState(1);
      return (
        <AccountRail
          state={{ kind: "ready", accounts: items }}
          page={page}
          locked={false}
          starting={false}
          startError={false}
          onSelect={vi.fn()}
          onPageChange={setPage}
          onStart={vi.fn()}
          onRetry={vi.fn()}
          onReload={vi.fn()}
        />
      );
    }
    render(<Harness />);

    const next = screen.getByRole("button", { name: "Next" });
    next.focus();
    fireEvent.click(next);

    expect(screen.getByRole("button", { name: /Account 6/ })).toHaveFocus();
  });

  it("renders the final page and locks pagination with the account controls", () => {
    const items = accounts(7);
    renderRail({ kind: "ready", accounts: items }, { page: 2, locked: true });

    expect(screen.getByText("6–7 of 7 assigned")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Account 5/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Account 6/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("omits pagination when all assigned accounts fit on one page", () => {
    renderRail({ kind: "ready", accounts: accounts(5) });

    expect(screen.getByText("5 assigned")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Account pages" })).not.toBeInTheDocument();
  });

  it("does not enable Run for a selection that is absent from the ready response", () => {
    renderRail({ kind: "ready", accounts: accounts(2) }, { selectedId: "removed-account" });

    expect(screen.getByRole("button", { name: "Run prospect agent" })).toBeDisabled();
  });
});
