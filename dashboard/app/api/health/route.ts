import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/rbac";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const MT5_URL = process.env.MT5_API_URL || "http://127.0.0.1:5001";
const LOG_DIR = "/root/nestquant/logs/shadow_live";
const METRICS_FILE = join(LOG_DIR, "metrics.json");

export const GET = withAuth(async (req: NextRequest) => {
  try {
    // Read aggregated metrics (from Python monitoring layer)
    let metrics: Record<string, unknown> | null = null;
    if (existsSync(METRICS_FILE)) {
      try { metrics = JSON.parse(readFileSync(METRICS_FILE, "utf8")); } catch { /* ignore */ }
    }

    // Fetch MT5 health + account info
    let mt5: Record<string, unknown> = { mt5_connected: false, status: "unreachable" };
    let mt5Account: Record<string, unknown> = {};
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

    // Fetch account info from MT5 bridge
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      const res = await fetch(`${MT5_URL}/account`, {
        signal: controller.signal,
        cache: "no-store",
      });
      clearTimeout(timeout);
      if (res.ok) mt5Account = await res.json();
    } catch { /* account endpoint unreachable */ }

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

    // Use metrics from Python monitoring layer if available
    const account = (metrics?.account || {}) as Record<string, unknown>;
    const pnl = (metrics?.pnl || {}) as Record<string, unknown>;
    const dd = (metrics?.drawdown || {}) as Record<string, unknown>;
    const trading = (metrics?.trading || {}) as Record<string, unknown>;
    const risk = (metrics?.risk || {}) as Record<string, unknown>;
    const execution = (metrics?.execution || {}) as Record<string, unknown>;

    return NextResponse.json({
      status: metrics?.health_status === "RED" ? "ERROR" : mt5.status === "healthy" ? "HEALTHY" : "DEGRADED",
      uptime_seconds: uptimeSeconds,
      bars_processed: barsProcessed,
      signals_emitted: signalsEmitted,
      kill_switch_active: killSwitchActive || (risk.kill_switch_active as boolean),
      data_stale: !execution.data_freshness,
      avg_latency_ms: 0,
      p95_latency_ms: 0,
      gaps_detected: gapsDetected,
      integrity_violations: integrityViolations,
      execution_mode: (execution.execution_mode as string) || "SHADOW",
      mt5_connected: mt5.mt5_connected || (execution.mt5_connected as boolean),
      orders_submitted: zeroOrders.orders_submitted,
      orders_blocked: zeroOrders.blocked_attempts,
      open_positions: (trading.open_positions as number) || 0,

      // Real account metrics — prefer live MT5 data, fallback to Python metrics
      equity: (mt5Account.equity as number) || (account.current_equity as number) || 0,
      balance: (mt5Account.balance as number) || (account.current_balance as number) || 0,
      peak_equity: (account.peak_equity as number) || (mt5Account.equity as number) || 0,
      starting_capital: (account.starting_capital as number) || (mt5Account.balance as number) || 0,

      // P&L
      total_pnl: (mt5Account.profit as number) || (pnl.total_pnl as number) || 0,
      daily_pnl: (pnl.daily_pnl as number) || 0,
      total_return_pct: (pnl.total_return_pct as number) || 0,

      // Margin
      margin_used: (mt5Account.margin as number) || 0,
      free_margin: (mt5Account.free_margin as number) || 0,
      leverage: (mt5Account.leverage as number) || 0,
      margin_level: (mt5Account.margin_level as number) || 0,

      // Drawdown
      current_drawdown_pct: (dd.current_drawdown_pct as number) || 0,
      max_drawdown_pct: (dd.maximum_drawdown_pct as number) || 0,

      // Trading
      total_trades: (trading.total_trades as number) || 0,
      win_rate: (trading.win_rate as number) || 0,
      profit_factor: (trading.profit_factor as number) || 0,

      // Risk
      risk_per_trade_pct: (risk.risk_per_trade_pct as number) || 0,
      max_drawdown_limit_pct: (risk.max_drawdown_limit_pct as number) || 0,

      // Runner
      runner_health: (execution.runner_health as string) || "unknown",
      last_evaluation: (execution.last_evaluation as string) || null,

      notes: [],
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg, status: "ERROR" }, { status: 500 });
  }
});
