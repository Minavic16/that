import { NextRequest, NextResponse } from "next/server";
import { getSession, SessionPayload } from "./auth";

export type { SessionPayload };

export function withAuth(
  handler: (req: NextRequest, session: SessionPayload) => Promise<NextResponse>
) {
  return async (req: NextRequest) => {
    const session = await getSession();
    if (!session) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    }
    return handler(req, session);
  };
}

export function withAdmin(
  handler: (req: NextRequest, session: SessionPayload) => Promise<NextResponse>
) {
  return async (req: NextRequest) => {
    const session = await getSession();
    if (!session) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    }
    if (session.role !== "admin") {
      return NextResponse.json({ error: "forbidden" }, { status: 403 });
    }
    return handler(req, session);
  };
}
