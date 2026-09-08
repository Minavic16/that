import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/rbac";

const MT5_URL = process.env.MT5_API_URL || "http://127.0.0.1:5001";

export const GET = withAuth(async (req: NextRequest) => {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const res = await fetch(`${MT5_URL}/health`, {
      signal: controller.signal,
      cache: "no-store",
    });
    clearTimeout(timeout);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "MT5 unreachable";
    return NextResponse.json(
      { mt5_connected: false, status: "unreachable", error: msg },
      { status: 502 }
    );
  }
});
