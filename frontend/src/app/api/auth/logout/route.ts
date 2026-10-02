import { NextResponse } from "next/server";

import { SESSION_COOKIE, authResponseHeaders } from "@/server/auth-session";
import { correlationId } from "@/server/logging";

export async function POST(request?: Request) {
  const requestId = correlationId(request?.headers.get("x-correlation-id"));
  const response = NextResponse.json(
    { ok: true },
    { headers: { ...authResponseHeaders, "x-correlation-id": requestId } },
  );
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
