import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/rbac";
import { readFileSync, existsSync, appendFileSync } from "fs";
import { join } from "path";

const LOG_DIR = "/root/that/logs/shadow_live";
const API_LOG = join(LOG_DIR, "api_access.log");
const METRICS_FILE = join(LOG_DIR, "metrics.json");

function logAccess(endpoint: string, user: string) {
  try {
    const ts = new Date().toISOString();
    appendFileSync(API_LOG, JSON.stringify({ ts, endpoint, user }) + "\n");
  } catch { /* ignore */ }
}

export const GET = withAuth(async (req: NextRequest) => {
  try {
    const stateFile = join(LOG_DIR, "state.json");
    let state: Record<string, unknown> = {};
    if (existsSync(stateFile)) {
      state = JSON.parse(readFileSync(stateFile, "utf8"));
    }

    const zeroFile = "/root/that/orders_submitted_count.json";
    let zeroOrders = { orders_submitted: 0, blocked_attempts: 0 };
    if (existsSync(zeroFile)) {
      zeroOrders = JSON.parse(readFileSync(zeroFile, "utf8"));
    }

    // Read aggregated metrics
    let metrics: Record<string, unknown> | null = null;
    if (existsSync(METRICS_FILE)) {
      try { metrics = JSON.parse(readFileSync(METRICS_FILE, "utf8")); } catch { /* ignore */ }
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

    // Read circuit breaker status
    let breakerStatus: Record<string, unknown> | null = null;
    const breakerFile = join(LOG_DIR, "breaker_state.json");
    if (existsSync(breakerFile)) {
      try { breakerStatus = JSON.parse(readFileSync(breakerFile, "utf8")); } catch { /* ignore */ }
    }

    logAccess("status", "authenticated");
    return NextResponse.json({
      state,
      zero_orders: zeroOrders,
      recent_signals: lastSignals,
      recent_bars: lastBars,
      metrics,
      circuit_breakers: breakerStatus,
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
});
