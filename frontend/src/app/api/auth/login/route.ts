import { NextResponse } from "next/server";
import { z } from "zod";

import {
  BackendTokenSchema,
  SESSION_COOKIE,
  authResponseHeaders,
  backendAuth,
  sessionCookieOptions,
} from "@/server/auth-session";

const Credentials = z.object({ email: z.email(), password: z.string().min(1).max(256) });

export async function POST(request: Request) {
  const parsed = Credentials.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      { error: "invalid_credentials" },
      { status: 401, headers: authResponseHeaders },
    );
  }
  try {
    const backend = await backendAuth("token", undefined, {
      method: "POST",
      body: JSON.stringify(parsed.data),
    });
    if (!backend.ok) {
      return NextResponse.json(
        { error: backend.status === 401 ? "invalid_credentials" : "service_unavailable" },
        { status: backend.status === 401 ? 401 : 503, headers: authResponseHeaders },
      );
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
