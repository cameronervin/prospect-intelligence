import { NextResponse } from "next/server";
import { z } from "zod";

import {
  BackendTokenSchema,
  SESSION_COOKIE,
  authResponseHeaders,
  backendAuth,
  sessionCookieOptions,
} from "@/server/auth-session";
import { correlationId, serverLog } from "@/server/logging";

const Credentials = z.object({ email: z.email(), password: z.string().min(1).max(256) });

export async function POST(request: Request) {
  const requestId = correlationId(request.headers.get("x-correlation-id"));
  const responseHeaders = { ...authResponseHeaders, "x-correlation-id": requestId };
  const parsed = Credentials.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid_credentials" },
      { status: 401, headers: responseHeaders },
    );
  }
  try {
    const backend = await backendAuth("token", undefined, {
      method: "POST",
      body: JSON.stringify(parsed.data),
      headers: { "x-correlation-id": requestId },
    });
    if (!backend.ok) {
      if (backend.status >= 500) {
        serverLog("warning", "backend_auth_dependency_failed", {
          correlation_id: requestId,
          operation: "login",
          status_code: backend.status,
        });
      }
      return NextResponse.json(
        { error: backend.status === 401 ? "invalid_credentials" : "service_unavailable" },
        { status: backend.status === 401 ? 401 : 503, headers: responseHeaders },
      );
    }
    const session = BackendTokenSchema.parse(await backend.json());
    const response = NextResponse.json(
      {
        user: session.user,
        expires_at: session.expires_at,
        absolute_expires_at: session.absolute_expires_at,
      },
      { headers: responseHeaders },
    );
    response.cookies.set(SESSION_COOKIE, session.access_token, {
      ...sessionCookieOptions,
      expires: new Date(session.expires_at),
    });
    return response;
  } catch (caught) {
    serverLog("error", "backend_auth_proxy_failed", {
      correlation_id: requestId,
      operation: "login",
      error_type: caught instanceof Error ? caught.name : "UnknownError",
    });
    return NextResponse.json(
      { error: "service_unavailable" },
      { status: 503, headers: responseHeaders },
    );
  }
}
