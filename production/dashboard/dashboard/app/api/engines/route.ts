import { NextRequest, NextResponse } from "next/server";
import { withAuth } from "@/lib/rbac";
import { readFileSync, existsSync, readdirSync } from "fs";
import { join } from "path";

const MT5_URL = process.env.MT5_API_URL || "http://127.0.0.1:5001";
const LOG_DIR = "/root/nestquant/logs/shadow_live";
const STATE_FILE = join(LOG_DIR, "state.json");
const KILL_FILE = join(LOG_DIR, "KILL");
const SIGNALS_FILE = join(LOG_DIR, "signals.jsonl");
const BARS_FILE = join(LOG_DIR, "bars.jsonl");
const INFRA_FILE = join(LOG_DIR, "infrastructure.jsonl");
const BREAKER_FILE = join(LOG_DIR, "breaker_state.json");
const METRICS_FILE = join(LOG_DIR, "metrics.json");
const GUARD_FILE = "/root/nestquant/orders_submitted_count.json";

function readJson(path: string): Record<string, unknown> | null {
  try {
    if (existsSync(path)) {
      return JSON.parse(readFileSync(path, "utf8"));
    }
  } catch { /* ignore */ }
  return null;
}

function tailJsonl(path: string, count: number): Record<string, unknown>[] {
  try {
    if (!existsSync(path)) return [];
    const lines = readFileSync(path, "utf8").trim().split("\n").filter(Boolean);
    return lines.slice(-count).map(l => JSON.parse(l));
  } catch { return []; }
}

function fileAge(path: string): number | null {
  try {
    if (!existsSync(path)) return null;
    const stat = require("fs").statSync(path);
    return (Date.now() - stat.mtimeMs) / 1000;
  } catch { return null; }
}

export const GET = withAuth(async (req: NextRequest) => {
  try {
    const state = readJson(STATE_FILE) as Record<string, unknown> | null;
    const metrics = readJson(METRICS_FILE) as Record<string, unknown> | null;
    const breakers = readJson(BREAKER_FILE) as Record<string, unknown> | null;
    const guard = readJson(GUARD_FILE) as Record<string, unknown> | null;
    const killActive = existsSync(KILL_FILE);

    // MT5 bridge health
    let mt5 = { connected: false, status: "unreachable" as string, account: null as Record<string, unknown> | null };
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 5000);
      const res = await fetch(`${MT5_URL}/health`, { signal: ctrl.signal, cache: "no-store" });
      clearTimeout(t);
      if (res.ok) mt5 = { ...mt5, ...(await res.json()), connected: true };
    } catch { /* unreachable */ }
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 10000);
      const res = await fetch(`${MT5_URL}/account`, { signal: ctrl.signal, cache: "no-store" });
      clearTimeout(t);
      if (res.ok) mt5.account = await res.json();
    } catch { /* unreachable */ }

    // Runner process check (systemd)
    let runnerPid: number | null = null;
    let runnerUptime = 0;
    try {
      const { execSync } = require("child_process");
      const pidStr = execSync("pgrep -f 'next-start|run_live_shadow|nestquant-shadow' 2>/dev/null || true", { timeout: 3000 }).toString().trim();
      if (pidStr) {
        runnerPid = parseInt(pidStr.split("\n")[0]);
        const uptimeStr = execSync(`ps -o etimes= -p ${runnerPid} 2>/dev/null || echo 0`, { timeout: 3000 }).toString().trim();
        runnerUptime = parseInt(uptimeStr) || 0;
      }
    } catch { /* ignore */ }

    // Data freshness
    const stateAge = fileAge(STATE_FILE);
    const signalsAge = fileAge(SIGNALS_FILE);
    const barsAge = fileAge(BARS_FILE);
    const dataFresh = stateAge !== null && stateAge < 3600; // < 1 hour

    // Recent signals
    const recentSignals = tailJsonl(SIGNALS_FILE, 10);

    // Infrastructure events
    const infraEvents = tailJsonl(INFRA_FILE, 5);

    // Circuit breakers
    const breakerState = breakers?.breakers as Record<string, Record<string, unknown>> | undefined;
    const breakerStatuses: Record<string, { paused: boolean; reason?: string }> = {};
    if (breakerState) {
      for (const [name, data] of Object.entries(breakerState)) {
        breakerStatuses[name] = {
          paused: (data.paused as boolean) || false,
          reason: (data.pause_reason as string) || undefined,
        };
      }
    }

    // Health state model: GREEN / AMBER / RED
    let healthState: "GREEN" | "AMBER" | "RED" = "GREEN";
    const healthReasons: string[] = [];

    if (killActive) {
      healthState = "RED";
      healthReasons.push("Kill switch active");
    }
    if (!mt5.connected) {
      healthState = "RED";
      healthReasons.push("MT5 disconnected");
    }
    if (!dataFresh) {
      healthState = healthState === "RED" ? "RED" : "AMBER";
      healthReasons.push("Data stale");
    }
    if (!runnerPid) {
      healthState = healthState === "RED" ? "RED" : "AMBER";
      healthReasons.push("Runner not detected");
    }
    const anyBreakerPaused = Object.values(breakerStatuses).some(b => b.paused);
    if (anyBreakerPaused) {
      healthState = healthState === "RED" ? "RED" : "AMBER";
      healthReasons.push("Circuit breaker paused");
    }
    if ((guard?.blocked_attempts as number ?? 0) > 0) {
      healthReasons.push("Orders blocked by safety guard");
    }

    // Strategy info from metrics
    const risk = (metrics?.risk || {}) as Record<string, unknown>;
    const trading = (metrics?.trading || {}) as Record<string, unknown>;
    const account = (metrics?.account || {}) as Record<string, unknown>;
    const pnl = (metrics?.pnl || {}) as Record<string, unknown>;
    const dd = (metrics?.drawdown || {}) as Record<string, unknown>;
    const exec = (metrics?.execution || {}) as Record<string, unknown>;

    // Counters from state
    const counters = (state?.counters || {}) as Record<string, number>;

    // Lifecycle info
    const lastBar = (state?.last_bar || {}) as Record<string, string>;
    const pairsTracked = Object.keys(lastBar).length;

    return NextResponse.json({
      health: {
        state: healthState,
        reasons: healthReasons,
        timestamp: new Date().toISOString(),
      },
      strategy: {
        name: "Canonical Breakout V1",
        timeframe: "4H",
        lookback: 5,
        atr_period: 14,
        atr_sl_multiplier: 2.0,
        rrr: 3.5,
        breakeven_ratio: 0.8,
        max_hold_days: 7,
        max_hold_bars: 42,
        trailing_enabled: true,
        trailing_type: "swing_based",
        last_evaluation: (exec.last_evaluation as string) || null,
        last_signal: (exec.last_signal as string) || null,
        data_fresh: dataFresh,
        bars_processed: (counters.bars_processed as number) || 0,
        signals_emitted: (counters.signals_emitted as number) || 0,
      },
      runner: {
        status: runnerPid ? "RUNNING" : "STOPPED",
        pid: runnerPid,
        uptime_seconds: runnerUptime,
        last_heartbeat: state?.updated_at || null,
        signals_today: (counters.signals_emitted as number) || 0,
        pairs_tracked: pairsTracked,
      },
      risk: {
        status: "ACTIVE",
        risk_per_trade_pct: (risk.risk_per_trade_pct as number) || 0.0015,
        max_concurrent_positions: (risk.max_concurrent_positions as number) || 3,
        current_positions: (trading.open_positions as number) || 0,
        max_daily_loss_pct: 3,
        current_daily_loss: 0,
        max_drawdown_pct: 8,
        current_drawdown: (dd.current_drawdown_pct as number) || 0,
        max_trades_per_day: 4,
        trades_today: 0,
        kill_switch: killActive,
      },
      circuit_breakers: {
        statuses: breakerStatuses,
        any_paused: anyBreakerPaused,
      },
      execution: {
        mode: (exec.execution_mode as string) || "SHADOW",
        last_execution: null,
        orders_today: (guard?.orders_submitted as number) || 0,
        rejected: (guard?.blocked_attempts as number) || 0,
        execution_latency_ms: 0,
      },
      mt5: {
        connected: mt5.connected,
        status: mt5.status,
        account: mt5.account,
      },
      lifecycle: {
        positions_tracked: pairsTracked,
        breakeven_enabled: true,
        trailing_enabled: true,
        max_hold_days: 7,
        last_lifecycle_action: null,
      },
      telegram: {
        connected: !!process.env.TELEGRAM_BOT_TOKEN,
        bot: "@NQTSbot",
        last_notification: null,
        last_notification_status: "UNKNOWN",
      },
      signals: {
        recent: recentSignals.map(s => ({
          timestamp: s.timestamp || s.broker_timestamp,
          symbol: s.symbol || s.pair,
          direction: s.direction,
          entry: s.expected_entry || s.entry_price,
          sl: s.expected_sl || s.sl_price,
          tp: s.expected_tp || s.tp_price,
          risk_decision: "ALLOWED",
          execution_status: "SHADOW",
          signal_id: s.signal_id,
        })),
        total: (counters.signals_emitted as number) || 0,
      },
      infrastructure: {
        gaps_detected: infraEvents.filter(e => e.event_type === "ERROR").length,
        integrity_violations: infraEvents.filter(e => e.event_type === "WARNING").length,
        recent_events: infraEvents.map(e => ({
          type: e.event_type,
          message: e.message,
          timestamp: e.timestamp,
        })),
      },
      timestamp: new Date().toISOString(),
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "unknown error";
    return NextResponse.json({ error: msg, health: { state: "RED", reasons: [msg] } }, { status: 500 });
  }
});
