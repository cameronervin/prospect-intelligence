import { NextResponse } from "next/server";

import {
  BackendTokenSchema,
  SESSION_COOKIE,
  authResponseHeaders,
  backendAuth,
  currentToken,
  sessionCookieOptions,
} from "@/server/auth-session";
import { correlationId, serverLog } from "@/server/logging";

export async function POST(request?: Request) {
  const requestId = correlationId(request?.headers.get("x-correlation-id"));
  const responseHeaders = { ...authResponseHeaders, "x-correlation-id": requestId };
  const token = await currentToken();
  if (!token) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401, headers: responseHeaders });
  }
  try {
    const backend = await backendAuth("refresh", token, {
      method: "POST",
      headers: { "x-correlation-id": requestId },
    });
    if (!backend.ok) {
      if (backend.status >= 500) {
        serverLog("warning", "backend_auth_dependency_failed", {
          correlation_id: requestId,
          operation: "refresh",
          status_code: backend.status,
        });
        return NextResponse.json(
          { error: "service_unavailable" },
          { status: 503, headers: responseHeaders },
        );
      }
      const response = NextResponse.json(
        { error: "unauthorized" },
        { status: 401, headers: responseHeaders },
      );
      response.cookies.delete(SESSION_COOKIE);
      return response;
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
      operation: "refresh",
      error_type: caught instanceof Error ? caught.name : "UnknownError",
    });
    return NextResponse.json(
      { error: "service_unavailable" },
      { status: 503, headers: responseHeaders },
    );
  }
}
