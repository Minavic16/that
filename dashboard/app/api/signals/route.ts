import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/rbac";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const LOG_DIR = "/root/nestquant/logs/shadow_live";

export const GET = withAuth(async (req: NextRequest) => {
  try {
    const url = new URL(req.url);
    const limit = Math.min(parseInt(url.searchParams.get("limit") || "50"), 200);

    const signalsFile = join(LOG_DIR, "signals.jsonl");
    if (!existsSync(signalsFile)) {
      return NextResponse.json({ signals: [], total: 0 });
    }

    const lines = readFileSync(signalsFile, "utf8").trim().split("\n").filter(Boolean);
    const signals = lines.slice(-limit).map((l) => {
      try { return JSON.parse(l); } catch { return null; }
    }).filter(Boolean);

    return NextResponse.json({ signals, total: lines.length });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
});
