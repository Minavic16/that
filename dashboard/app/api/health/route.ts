import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/rbac";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const MT5_URL = process.env.MT5_API_URL || "http://127.0.0.1:5001";
const LOG_DIR = "/root/nestquant/logs/shadow_live";

export const GET = withAuth(async (req: NextRequest) => {
  try {
    // Fetch MT5 health
    let mt5: Record<string, unknown> = { mt5_connected: false, status: "unreachable" };
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      const res = await fetch(`${MT5_URL}/health`, {
        signal: controller.signal,
        cache: "no-store",
      });
      clearTimeout(timeout);
      if (res.ok) mt5 = await res.json();
    } catch { /* MT5 unreachable */ }

    // Read shadow runner state
    let state: Record<string, unknown> = {};
    const stateFile = join(LOG_DIR, "state.json");
    if (existsSync(stateFile)) {
      try { state = JSON.parse(readFileSync(stateFile, "utf8")); } catch { /* ignore */ }
    }

    // Read zero orders
    let zeroOrders = { orders_submitted: 0, blocked_attempts: 0 };
    const zeroFile = "/root/nestquant/orders_submitted_count.json";
    if (existsSync(zeroFile)) {
      try { zeroOrders = JSON.parse(readFileSync(zeroFile, "utf8")); } catch { /* ignore */ }
    }

    // Compute uptime from state created_at
    const createdAt = state.created_at as string | undefined;
    let uptimeSeconds = 0;
    if (createdAt) {
      try {
        const start = new Date(createdAt).getTime();
        uptimeSeconds = Math.floor((Date.now() - start) / 1000);
      } catch { /* ignore */ }
    }

    // Read infrastructure for gaps and integrity
    let gapsDetected = 0;
    let integrityViolations = 0;
    const infraFile = join(LOG_DIR, "infrastructure.jsonl");
    if (existsSync(infraFile)) {
      try {
        const lines = readFileSync(infraFile, "utf8").trim().split("\n").filter(Boolean);
        for (const line of lines) {
          const event = JSON.parse(line);
          if (event.event_type === "ERROR") gapsDetected++;
          if (event.event_type === "WARNING") integrityViolations++;
        }
      } catch { /* ignore */ }
    }

    // Count signals
    let signalsEmitted = 0;
    const signalsFile = join(LOG_DIR, "signals.jsonl");
    if (existsSync(signalsFile)) {
      try {
        signalsEmitted = readFileSync(signalsFile, "utf8").trim().split("\n").filter(Boolean).length;
      } catch { /* ignore */ }
    }

    // Count bars processed
    const counters = (state.counters || {}) as Record<string, number>;
    const barsProcessed = counters.bars_processed || 0;

    // Read kill switch state
    let killSwitchActive = false;
    const killFile = join(LOG_DIR, "KILL");
    if (existsSync(killFile)) killSwitchActive = true;

    // Determine execution mode
    const executionMode = "SHADOW"; // Currently always shadow

    return NextResponse.json({
      status: mt5.status === "healthy" ? "HEALTHY" : "DEGRADED",
      uptime_seconds: uptimeSeconds,
      bars_processed: barsProcessed,
      signals_emitted: signalsEmitted,
      kill_switch_active: killSwitchActive,
      data_stale: false,
      avg_latency_ms: 0,
      p95_latency_ms: 0,
      gaps_detected: gapsDetected,
      integrity_violations: integrityViolations,
      execution_mode: executionMode,
      mt5_connected: mt5.mt5_connected,
      orders_submitted: zeroOrders.orders_submitted,
      orders_blocked: zeroOrders.blocked_attempts,
      open_positions: 0,
      notes: [],
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg, status: "ERROR" }, { status: 500 });
  }
});
