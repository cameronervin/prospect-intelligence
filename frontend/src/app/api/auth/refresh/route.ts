import { NextResponse } from "next/server";

import {
  BackendTokenSchema,
  SESSION_COOKIE,
  authResponseHeaders,
  backendAuth,
  currentToken,
  sessionCookieOptions,
} from "@/server/auth-session";

export async function POST() {
  const token = await currentToken();
  if (!token) {
    return NextResponse.json(
      { error: "unauthorized" },
      { status: 401, headers: authResponseHeaders },
    );
  }
  try {
    const backend = await backendAuth("refresh", token, { method: "POST" });
    if (!backend.ok) {
      if (backend.status >= 500) {
        return NextResponse.json(
          { error: "service_unavailable" },
          { status: 503, headers: authResponseHeaders },
        );
      }
      const response = NextResponse.json(
        { error: "unauthorized" },
        { status: 401, headers: authResponseHeaders },
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
      { headers: authResponseHeaders },
    );
    response.cookies.set(SESSION_COOKIE, session.access_token, {
      ...sessionCookieOptions,
      expires: new Date(session.expires_at),
    });
    return response;
  } catch {
    return NextResponse.json(
      { error: "service_unavailable" },
      { status: 503, headers: authResponseHeaders },
    );
  }
}
