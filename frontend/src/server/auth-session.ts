import { cookies } from "next/headers";

import { SESSION_COOKIE } from "@/features/auth/constants";
import { BackendSessionSchema, BackendTokenSchema } from "@/features/auth/schemas";
import { backendBaseUrl } from "@/server/env";

export const sessionCookieOptions = {
  httpOnly: true,
  sameSite: "strict" as const,
  path: "/",
  secure: process.env.NODE_ENV !== "development",
};

export async function backendAuth(path: string, token?: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  if (token) headers.set("authorization", `Bearer ${token}`);
  return fetch(new URL(`/api/v1/auth/${path}`, backendBaseUrl()), {
    ...init,
    headers,
    cache: "no-store",
  });
}

export async function currentToken() {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

export async function currentSession() {
  const token = await currentToken();
  if (!token) return undefined;
  const localMockSession =
    process.env.PLAYWRIGHT_MOCK_SESSION === "true" &&
    new URL(backendBaseUrl()).hostname === "127.0.0.1";
  if (localMockSession && token === "playwright-mock-session") {
    return {
      subject: "usr_alex_morgan",
      email: "alex.morgan@example.test",
      display_name: "Alex Morgan",
      tenant_id: "tenant-demo",
      rep_id: "alex-morgan",
      roles: ["sales_rep"],
    };
  }
  try {
    const response = await backendAuth("me", token);
    if (!response.ok) return undefined;
    return BackendSessionSchema.parse(await response.json()).user;
  } catch {
    return undefined;
  }
}

export { BackendTokenSchema };
export { SESSION_COOKIE };
