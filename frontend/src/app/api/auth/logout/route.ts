import { NextResponse } from "next/server";

import { SESSION_COOKIE, authResponseHeaders } from "@/server/auth-session";

export async function POST() {
  const response = NextResponse.json({ ok: true }, { headers: authResponseHeaders });
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
