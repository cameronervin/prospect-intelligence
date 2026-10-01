import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "./login-form";

const replace = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh }) }));

describe("LoginForm", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    replace.mockReset();
    refresh.mockReset();
  });

  it("submits password-manager-compatible credentials and shows progress", async () => {
    let finish!: () => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = () => resolve(Response.json({ user: {} }));
          }),
      ),
    );
    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "prospect-demo" } });
    fireEvent.submit(
      screen.getByRole("button", { name: "Enter dispatch console" }).closest("form")!,
    );

    expect(screen.getByRole("button", { name: "Checking access…" })).toBeDisabled();
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    finish();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  it("shows one generic credential error and restores focus", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({}, { status: 401 })));
    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.submit(
      screen.getByRole("button", { name: "Enter dispatch console" }).closest("form")!,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    await waitFor(() => expect(screen.getByLabelText("Email")).toHaveFocus());
  });

  it("distinguishes temporary service unavailability", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "prospect-demo" } });
    fireEvent.submit(
      screen.getByRole("button", { name: "Enter dispatch console" }).closest("form")!,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
  });
});
