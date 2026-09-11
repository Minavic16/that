import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/rbac";
import { readFileSync, existsSync, appendFileSync } from "fs";
import { join } from "path";

const LOG_DIR = "/root/nestquant/logs/shadow_live";
const API_LOG = join(LOG_DIR, "api_access.log");

function logAccess(endpoint: string, user: string, limit: number, count: number) {
  try {
    const ts = new Date().toISOString();
    appendFileSync(API_LOG, JSON.stringify({ ts, endpoint, user, limit, count }) + "\n");
  } catch { /* ignore */ }
}

export const GET = withAuth(async (req: NextRequest) => {
  try {
    const url = new URL(req.url);
    const limit = Math.min(parseInt(url.searchParams.get("limit") || "50"), 200);

    const signalsFile = join(LOG_DIR, "signals.jsonl");
    if (!existsSync(signalsFile)) {
      logAccess("signals", "unknown", limit, 0);
      return NextResponse.json({ signals: [], total: 0 });
    }

    const lines = readFileSync(signalsFile, "utf8").trim().split("\n").filter(Boolean);
    const signals = lines.slice(-limit).map((l) => {
      try { return JSON.parse(l); } catch { return null; }
    }).filter(Boolean);

    logAccess("signals", "authenticated", limit, signals.length);
    return NextResponse.json({ signals, total: lines.length });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
});
