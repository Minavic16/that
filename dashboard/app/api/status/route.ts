import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/rbac";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const LOG_DIR = "/root/nestquant/logs/shadow_live";

export const GET = withAuth(async (req: NextRequest) => {
  try {
    const stateFile = join(LOG_DIR, "state.json");
    let state: Record<string, unknown> = {};
    if (existsSync(stateFile)) {
      state = JSON.parse(readFileSync(stateFile, "utf8"));
    }

    const zeroFile = "/root/nestquant/orders_submitted_count.json";
    let zeroOrders = { orders_submitted: 0, blocked_attempts: 0 };
    if (existsSync(zeroFile)) {
      zeroOrders = JSON.parse(readFileSync(zeroFile, "utf8"));
    }

    let lastSignals: unknown[] = [];
    const signalsFile = join(LOG_DIR, "signals.jsonl");
    if (existsSync(signalsFile)) {
      const lines = readFileSync(signalsFile, "utf8").trim().split("\n").filter(Boolean);
      lastSignals = lines.slice(-20).map((l) => {
        try { return JSON.parse(l); } catch { return null; }
      }).filter(Boolean);
    }

    let lastBars: unknown[] = [];
    const barsFile = join(LOG_DIR, "bars.jsonl");
    if (existsSync(barsFile)) {
      const lines = readFileSync(barsFile, "utf8").trim().split("\n").filter(Boolean);
      lastBars = lines.slice(-10).map((l) => {
        try { return JSON.parse(l); } catch { return null; }
      }).filter(Boolean);
    }

    return NextResponse.json({
      state,
      zero_orders: zeroOrders,
      recent_signals: lastSignals,
      recent_bars: lastBars,
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
});
