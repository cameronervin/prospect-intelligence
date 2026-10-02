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
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fetcher = vi.fn<typeof fetch>().mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          finish = () => resolve(Response.json({ user: {} }));
        }),
    );
    vi.stubGlobal("fetch", fetcher);
    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "prospect-demo" } });
    fireEvent.submit(screen.getByRole("button", { name: "Enter" }).closest("form")!);

    expect(screen.getByRole("button", { name: "Checking access…" })).toBeDisabled();
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("/api/auth/login");
    expect(new URL(String(url), "http://localhost").search).toBe("");
    expect(init).toMatchObject({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        email: "alex.morgan@example.test",
        password: "prospect-demo",
      }),
    });
    expect(new Headers(init?.headers).get("location")).toBeNull();
    expect(log).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
    finish();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  it("shows one generic credential error and restores focus", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({}, { status: 401 })));
    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.submit(screen.getByRole("button", { name: "Enter" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    await waitFor(() => expect(screen.getByLabelText("Email")).toHaveFocus());
  });

  it("distinguishes temporary service unavailability", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "prospect-demo" } });
    fireEvent.submit(screen.getByRole("button", { name: "Enter" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("temporarily unavailable");
  });
});
