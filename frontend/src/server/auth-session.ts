import { cookies } from "next/headers";

import { SESSION_COOKIE } from "@/features/auth/constants";
import { BackendSessionSchema, BackendTokenSchema } from "@/features/auth/schemas";
import { backendBaseUrl } from "@/server/env";
import { serverLog } from "@/server/logging";

export const sessionCookieOptions = {
  httpOnly: true,
  sameSite: "strict" as const,
  path: "/",
  secure: process.env.NODE_ENV !== "development",
};

export const authResponseHeaders = {
  "Cache-Control": "no-store, max-age=0",
  Pragma: "no-cache",
} as const;

export async function backendAuth(path: string, token?: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  if (token) headers.set("authorization", `Bearer ${token}`);
  return fetch(new URL(`/api/v1/auth/${path}`, backendBaseUrl()), {
    ...init,
    headers,
    cache: "no-store",
    redirect: "manual",
  });
}

export async function currentToken() {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

export async function currentSession(correlationId?: string) {
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
    const response = await backendAuth("me", token, {
      headers: correlationId ? { "x-correlation-id": correlationId } : undefined,
    });
    if (!response.ok) {
      if (response.status >= 500) {
        serverLog("warning", "backend_auth_dependency_failed", {
          correlation_id: correlationId,
          operation: "session",
          status_code: response.status,
        });
      }
      return undefined;
    }
    return BackendSessionSchema.parse(await response.json()).user;
  } catch (caught) {
    serverLog("error", "backend_auth_proxy_failed", {
      correlation_id: correlationId,
      operation: "session",
      error_type: caught instanceof Error ? caught.name : "UnknownError",
    });
    return undefined;
  }
}

export { BackendTokenSchema };
export { SESSION_COOKIE };
