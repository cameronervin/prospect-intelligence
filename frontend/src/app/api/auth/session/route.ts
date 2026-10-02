import { NextResponse } from "next/server";

import { SESSION_COOKIE, authResponseHeaders, currentSession } from "@/server/auth-session";

export async function GET() {
  const user = await currentSession();
  if (!user) {
    const response = NextResponse.json(
      { error: "unauthorized" },
      { status: 401, headers: authResponseHeaders },
    );
    response.cookies.delete(SESSION_COOKIE);
    return response;
  }
  return NextResponse.json({ user }, { headers: authResponseHeaders });
}
