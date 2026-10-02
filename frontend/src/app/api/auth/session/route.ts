import { NextResponse } from "next/server";

import { SESSION_COOKIE, authResponseHeaders, currentSession } from "@/server/auth-session";
import { correlationId } from "@/server/logging";

export async function GET(request?: Request) {
  const requestId = correlationId(request?.headers.get("x-correlation-id"));
  const responseHeaders = { ...authResponseHeaders, "x-correlation-id": requestId };
  const user = await currentSession(requestId);
  if (!user) {
    const response = NextResponse.json(
      { error: "unauthorized" },
      { status: 401, headers: responseHeaders },
    );
    response.cookies.delete(SESSION_COOKIE);
    return response;
  }
  return NextResponse.json({ user }, { headers: responseHeaders });
}
