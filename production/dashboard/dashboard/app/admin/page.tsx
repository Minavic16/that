"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface Session {
  authenticated: boolean;
  username: string;
  role: string;
}

interface HealthData {
  status: string;
  uptime_seconds: number;
  bars_processed: number;
  signals_emitted: number;
  kill_switch_active: boolean;
  data_stale: boolean;
  avg_latency_ms: number;
  p95_latency_ms: number;
  gaps_detected: number;
  integrity_violations: number;
  execution_mode: string;
  mt5_connected: boolean;
  orders_submitted: number;
  orders_blocked: number;
  open_positions: number;
  equity: number;
  balance: number;
  peak_equity: number;
  starting_capital: number;
  total_pnl: number;
  daily_pnl: number;
  total_return_pct: number;
  current_drawdown_pct: number;
  max_drawdown_pct: number;
  max_drawdown_limit_pct: number;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  risk_per_trade_pct: number;
  runner_health: string;
  last_evaluation: string | null;
  notes: string[];
  margin_used: number;
  free_margin: number;
  leverage: number;
  margin_level: number;
  currency: string;
  account_name: string;
  account_server: string;
  account_login: number;
}

interface Signal {
  signal_id?: string;
  timestamp?: string;
  symbol?: string;
  direction?: string;
  strategy_params?: Record<string, unknown>;
  swing_level?: number;
  signal_bar_close?: number;
  expected_entry?: number;
  expected_sl?: number;
  expected_tp?: number;
  atr_at_signal?: number;
  spread_at_signal?: number;
  generation_latency_ms?: number;
  policy_version?: string;
  broker_timestamp?: string;
  receipt_timestamp?: string;
  bid?: number;
  ask?: number;
  live_spread?: number;
}

interface User {
  username: string;
  role: string;
  created_at: string;
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${ok ? "bg-emerald-400" : "bg-red-400"}`}
    />
  );
}

function EngineCard({ title, status, items }: { title: string; status: string; items: { label: string; value: string }[] }) {
  const isOk = status === "RUNNING" || status === "CONNECTED" || status === "ACTIVE" || status === "READY" || status === "HEALTHY";
  return (
    <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
      <div className="flex items-center gap-2 mb-3">
        <StatusDot ok={isOk} />
        <span className="text-sm font-medium">{title}</span>
        <span className={`text-xs ml-auto ${isOk ? "text-emerald-400" : status === "STOPPED" || status === "DISCONNECTED" || status === "BLOCKED" ? "text-red-400" : "text-amber-400"}`}>{status}</span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        {items.map((item) => (
          <div key={item.label}>
            <p className="text-zinc-500 text-[10px]">{item.label}</p>
            <p className="font-mono text-zinc-300 truncate">{item.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

interface EngineData {
  health: { state: string; reasons: string[]; timestamp: string };
  strategy: { name: string; timeframe: string; last_evaluation: string | null; last_signal: string | null; data_fresh: boolean; bars_processed: number; signals_emitted: number; [k: string]: unknown };
  runner: { status: string; pid: number | null; uptime_seconds: number; last_heartbeat: string | null; signals_today: number; pairs_tracked: number };
  risk: { status: string; risk_per_trade_pct: number; max_concurrent_positions: number; current_positions: number; max_daily_loss_pct: number; current_daily_loss: number; max_drawdown_pct: number; current_drawdown: number; max_trades_per_day: number; trades_today: number; kill_switch: boolean };
  circuit_breakers: { statuses: Record<string, { paused: boolean; reason?: string }>; any_paused: boolean };
  execution: { mode: string; last_execution: string | null; orders_today: number; rejected: number; execution_latency_ms: number };
  mt5: { connected: boolean; status: string; account: Record<string, unknown> | null };
  lifecycle: { positions_tracked: number; breakeven_enabled: boolean; trailing_enabled: boolean; max_hold_days: number; last_lifecycle_action: string | null };
  telegram: { connected: boolean; bot: string; last_notification: string | null; last_notification_status: string };
  signals: { recent: Array<Record<string, unknown>>; total: number };
  infrastructure: { gaps_detected: number; integrity_violations: number; recent_events: Array<Record<string, unknown>> };
}

type Tab = "overview" | "engines" | "signals" | "users" | "config";

export default function AdminPage() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [health, setHealth] = useState<HealthData | null>(null);
  const [engines, setEngines] = useState<EngineData | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [config, setConfig] = useState<Record<string, string>>({});
  const [lastUpdate, setLastUpdate] = useState("");
  const [currentTime, setCurrentTime] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const meRes = await fetch("/api/auth/me");
        if (!meRes.ok) { router.push("/login"); return; }
        const me = await meRes.json();
        setSession(me);
        if (me.role !== "admin") { router.push("/"); return; }
        await refreshAll();
      } catch { router.push("/login"); }
      setLoading(false);
    }
    load();
  }, [router]);

  async function refreshAll() {
    try {
      const [hRes, sRes, uRes, cRes, eRes] = await Promise.all([
        fetch("/api/health"),
        fetch("/api/signals?limit=50"),
        fetch("/api/users"),
        fetch("/api/config"),
        fetch("/api/engines"),
      ]);
      if (hRes.ok) setHealth(await hRes.json());
      if (eRes.ok) setEngines(await eRes.json());
      if (sRes.ok) {
        const d = await sRes.json();
        setSignals(d.signals || []);
      }
      if (uRes.ok) {
        const d = await uRes.json();
        setUsers(d.users || []);
      }
      if (cRes.ok) {
        const d = await cRes.json();
        setConfig(d.config || {});
      }
      setLastUpdate(new Date().toLocaleTimeString());
    } catch { /* ignore */ }
  }

  useEffect(() => {
    if (!session || session.role !== "admin") return;
    const interval = setInterval(refreshAll, 30000);
    return () => clearInterval(interval);
  }, [session]);

  useEffect(() => {
    function updateTime() {
      setCurrentTime(new Date().toLocaleString());
    }
    updateTime();
    const timeInterval = setInterval(updateTime, 1000);
    return () => clearInterval(timeInterval);
  }, []);

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  async function handleAddUser(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    const username = fd.get("username") as string;
    const password = fd.get("password") as string;
    const role = fd.get("role") as string;

    const res = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, role }),
    });
    if (res.ok) {
      form.reset();
      await refreshAll();
    }
  }

  async function handleDeleteUser(username: string) {
    if (!confirm(`Delete ${username}?`)) return;
    await fetch(`/api/users?username=${encodeURIComponent(username)}`, { method: "DELETE" });
    await refreshAll();
  }

  if (loading) return <div className="flex-1 flex items-center justify-center"><p className="text-zinc-500">Loading...</p></div>;
  if (!session || session.role !== "admin") return null;

  const isHealthy = health?.status === "HEALTHY";
  const engineState = engines?.health?.state || "UNKNOWN";

  return (
    <div className="flex-1 flex flex-col pb-20">
      <header className="px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold">NestQuant Admin</h1>
          <button onClick={handleLogout} className="text-sm text-zinc-500 hover:text-zinc-300">Sign out</button>
        </div>
        <div className="flex items-center justify-between mt-0.5">
          <p className="text-xs text-zinc-600">{session.username} &middot; Admin</p>
          <div className="flex items-center gap-2">
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${engineState === "GREEN" ? "bg-emerald-900 text-emerald-300" : engineState === "AMBER" ? "bg-amber-900 text-amber-300" : engineState === "RED" ? "bg-red-900 text-red-300" : "bg-zinc-800 text-zinc-400"}`}>
              {engineState}
            </span>
            <p className="text-xs text-zinc-600 font-mono">{currentTime || "-"}</p>
          </div>
        </div>
      </header>

      <main className="flex-1 px-4 py-4 max-w-lg mx-auto w-full">
        {tab === "overview" && (
          <div className="space-y-4">
            {/* System Status */}
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <div className="flex items-center gap-2 mb-3">
                <StatusDot ok={isHealthy} />
                <span className="font-medium text-sm">{health?.status || "Unknown"}</span>
                {health?.data_stale && <span className="text-xs text-amber-400 ml-auto">Stale</span>}
                <span className={`text-xs px-2 py-0.5 rounded ml-auto ${health?.execution_mode === "SHADOW" ? "bg-amber-900 text-amber-300" : health?.execution_mode === "LIVE" ? "bg-red-900 text-red-300" : "bg-zinc-800 text-zinc-400"}`}>
                  {health?.execution_mode || "UNKNOWN"}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-zinc-500 text-xs">Uptime</p><p className="font-mono">{health ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m` : "-"}</p></div>
                <div><p className="text-zinc-500 text-xs">MT5</p><p className="font-mono">{health?.mt5_connected ? <span className="text-emerald-400">Connected</span> : <span className="text-red-400">Disconnected</span>}</p></div>
                <div><p className="text-zinc-500 text-xs">Runner</p><p className="font-mono">{health?.runner_health || "unknown"}</p></div>
                <div><p className="text-zinc-500 text-xs">Kill Switch</p><p className="font-mono">{health?.kill_switch_active ? <span className="text-red-400">ACTIVE</span> : <span className="text-emerald-400">off</span>}</p></div>
                <div><p className="text-zinc-500 text-xs">Bars Processed</p><p className="font-mono">{health?.bars_processed ?? "-"}</p></div>
                <div><p className="text-zinc-500 text-xs">Signals Emitted</p><p className="font-mono">{health?.signals_emitted ?? "-"}</p></div>
                <div><p className="text-zinc-500 text-xs">Orders Submitted</p><p className="font-mono">{health?.orders_submitted ?? 0}</p></div>
                <div><p className="text-zinc-500 text-xs">Orders Blocked</p><p className="font-mono">{health?.orders_blocked ?? 0}</p></div>
              </div>
            </div>

            {/* Account */}
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium">Account</h2>
                {health?.account_login ? <span className="text-[10px] text-zinc-600 font-mono">#{health.account_login} {health.account_name} · {health.account_server}</span> : null}
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-zinc-500 text-xs">Equity</p><p className="font-mono text-lg">{health?.currency || "$"}{(health?.equity ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p></div>
                <div><p className="text-zinc-500 text-xs">Balance</p><p className="font-mono">{health?.currency || "$"}{(health?.balance ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p></div>
                <div><p className="text-zinc-500 text-xs">Starting Capital</p><p className="font-mono">{health?.currency || "$"}{(health?.starting_capital ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p></div>
                <div><p className="text-zinc-500 text-xs">Peak Equity</p><p className="font-mono">{health?.currency || "$"}{(health?.peak_equity ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p></div>
                <div><p className="text-zinc-500 text-xs">Free Margin</p><p className="font-mono">{health?.currency || "$"}{(health?.free_margin ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p></div>
                <div><p className="text-zinc-500 text-xs">Leverage</p><p className="font-mono">{health?.leverage ? `${health.leverage}x` : "-"}</p></div>
              </div>
            </div>

            {/* P&L */}
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <h2 className="text-sm font-medium mb-3">Profit & Loss</h2>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-zinc-500 text-xs">Total P&L</p><p className={`font-mono ${(health?.total_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>{health?.currency || "$"}{(health?.total_pnl ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p></div>
                <div><p className="text-zinc-500 text-xs">Daily P&L</p><p className={`font-mono ${(health?.daily_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>{health?.currency || "$"}{(health?.daily_pnl ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p></div>
                <div><p className="text-zinc-500 text-xs">Total Return</p><p className={`font-mono ${(health?.total_return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>{(health?.total_return_pct ?? 0).toFixed(2)}%</p></div>
                <div><p className="text-zinc-500 text-xs">Open Positions</p><p className="font-mono">{health?.open_positions ?? 0}</p></div>
              </div>
            </div>

            {/* Drawdown */}
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <h2 className="text-sm font-medium mb-3">Drawdown</h2>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-zinc-500 text-xs">Current DD</p><p className="font-mono text-amber-400">{(health?.current_drawdown_pct ?? 0).toFixed(2)}%</p></div>
                <div><p className="text-zinc-500 text-xs">Max DD</p><p className="font-mono text-amber-400">{(health?.max_drawdown_pct ?? 0).toFixed(2)}%</p></div>
                <div><p className="text-zinc-500 text-xs">DD Limit</p><p className="font-mono">{(health?.max_drawdown_limit_pct ?? 8).toFixed(1)}%</p></div>
                <div><p className="text-zinc-500 text-xs">DD Remaining</p><p className="font-mono">{Math.max(0, (health?.max_drawdown_limit_pct ?? 8) - (health?.current_drawdown_pct ?? 0)).toFixed(2)}%</p></div>
              </div>
            </div>

            {/* Trading */}
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <h2 className="text-sm font-medium mb-3">Trading</h2>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-zinc-500 text-xs">Total Trades</p><p className="font-mono">{health?.total_trades ?? 0}</p></div>
                <div><p className="text-zinc-500 text-xs">Win Rate</p><p className="font-mono">{(health?.win_rate ?? 0).toFixed(1)}%</p></div>
                <div><p className="text-zinc-500 text-xs">Profit Factor</p><p className="font-mono">{(health?.profit_factor ?? 0).toFixed(3)}</p></div>
                <div><p className="text-zinc-500 text-xs">Risk/Trade</p><p className="font-mono">{((health?.risk_per_trade_pct ?? 0.0015) * 100).toFixed(2)}%</p></div>
              </div>
            </div>

            {health?.notes && health.notes.length > 0 && (
              <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
                <h2 className="text-sm font-medium mb-2">Notes</h2>
                <ul className="space-y-1">{health.notes.slice(0, 10).map((n, i) => <li key={i} className="text-xs text-zinc-500 font-mono">{n}</li>)}</ul>
              </div>
            )}
          </div>
        )}

        {tab === "signals" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm text-zinc-500">{signals.length} recent signals</p>
              <p className="text-xs text-zinc-600 font-mono">{currentTime || "-"}</p>
            </div>
            {signals.length === 0 && <p className="text-sm text-zinc-600 text-center py-8">No signals yet</p>}
            {signals.map((s, i) => (
              <div key={s.signal_id || i} className="bg-zinc-900 rounded-lg p-3 border border-zinc-800 text-sm">
                <div className="flex justify-between">
                  <span className="font-mono">{s.symbol || "-"}</span>
                  <span className={`font-medium ${s.direction === "BUY" ? "text-emerald-400" : "text-red-400"}`}>{s.direction || "-"}</span>
                </div>
                <div className="flex justify-between text-xs text-zinc-500 mt-1">
                  <span>entry={s.expected_entry?.toFixed(5) ?? "-"}</span>
                  <span>atr={s.atr_at_signal?.toFixed(5) ?? "-"}</span>
                  <span>{s.generation_latency_ms?.toFixed(1) ?? "-"}ms</span>
                </div>
                <div className="flex justify-between text-xs text-zinc-600 mt-1">
                  <span>SL={s.expected_sl?.toFixed(5) ?? "-"}</span>
                  <span>TP={s.expected_tp?.toFixed(5) ?? "-"}</span>
                  <span>{s.broker_timestamp ? new Date(s.broker_timestamp).toLocaleString() : (s.timestamp ? new Date(s.timestamp).toLocaleString() : "-")}</span>
                </div>
                {s.signal_id && (
                  <div className="text-[10px] text-zinc-700 mt-1 font-mono truncate">{s.signal_id}</div>
                )}
              </div>
            ))}
          </div>
        )}

        {tab === "users" && (
          <div className="space-y-4">
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <h2 className="text-sm font-medium mb-3">Add User</h2>
              <form onSubmit={handleAddUser} className="space-y-2">
                <input name="username" placeholder="Username" required className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-100 placeholder-zinc-600" />
                <input name="password" type="password" placeholder="Password" required className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-100 placeholder-zinc-600" />
                <select name="role" className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-100">
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
                <button type="submit" className="w-full py-2 bg-zinc-100 text-zinc-900 font-medium rounded-lg text-sm">Add User</button>
              </form>
            </div>

            <div className="space-y-2">
              {users.map((u) => (
                <div key={u.username} className="bg-zinc-900 rounded-lg p-3 border border-zinc-800 flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium">{u.username}</span>
                    <span className={`ml-2 text-xs px-2 py-0.5 rounded ${u.role === "admin" ? "bg-zinc-700 text-zinc-300" : "bg-zinc-800 text-zinc-500"}`}>{u.role}</span>
                  </div>
                  {u.username !== "Mindavic" && u.username !== "Noble prime" && (
                    <button onClick={() => handleDeleteUser(u.username)} className="text-xs text-red-400 hover:text-red-300">Delete</button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === "engines" && (
          <div className="space-y-3">
            {/* Health State Banner */}
            <div className={`rounded-xl p-4 border ${engineState === "GREEN" ? "bg-emerald-950 border-emerald-800" : engineState === "AMBER" ? "bg-amber-950 border-amber-800" : "bg-red-950 border-red-800"}`}>
              <div className="flex items-center gap-2">
                <StatusDot ok={engineState === "GREEN"} />
                <span className={`font-medium text-sm ${engineState === "GREEN" ? "text-emerald-300" : engineState === "AMBER" ? "text-amber-300" : "text-red-300"}`}>
                  System: {engineState}
                </span>
              </div>
              {engines?.health.reasons && engines.health.reasons.length > 0 && (
                <ul className="mt-2 space-y-0.5">
                  {engines.health.reasons.map((r, i) => <li key={i} className="text-xs text-zinc-400">- {r}</li>)}
                </ul>
              )}
            </div>

            {/* Strategy Engine */}
            <EngineCard
              title="Strategy Engine"
              status={engines?.strategy.data_fresh ? "RUNNING" : "DEGRADED"}
              items={[
                { label: "Strategy", value: engines?.strategy.name || "N/A" },
                { label: "Timeframe", value: engines?.strategy.timeframe || "N/A" },
                { label: "Last Evaluation", value: engines?.strategy.last_evaluation || "Never" },
                { label: "Last Signal", value: engines?.strategy.last_signal || "None" },
                { label: "Bars Processed", value: String(engines?.strategy.bars_processed ?? 0) },
                { label: "Signals Emitted", value: String(engines?.strategy.signals_emitted ?? 0) },
              ]}
            />

            {/* Signal Runner */}
            <EngineCard
              title="Signal Runner"
              status={engines?.runner.status === "RUNNING" ? "RUNNING" : "STOPPED"}
              items={[
                { label: "PID", value: engines?.runner.pid ? String(engines.runner.pid) : "N/A" },
                { label: "Uptime", value: engines?.runner.uptime_seconds ? `${Math.floor(engines.runner.uptime_seconds / 3600)}h ${Math.floor((engines.runner.uptime_seconds % 3600) / 60)}m` : "N/A" },
                { label: "Last Heartbeat", value: engines?.runner.last_heartbeat ? new Date(engines.runner.last_heartbeat).toLocaleTimeString() : "Never" },
                { label: "Signals Today", value: String(engines?.runner.signals_today ?? 0) },
                { label: "Pairs Tracked", value: String(engines?.runner.pairs_tracked ?? 0) },
              ]}
            />

            {/* Risk Manager */}
            <EngineCard
              title="Risk Manager"
              status={engines?.risk.kill_switch ? "BLOCKED" : "ACTIVE"}
              items={[
                { label: "Risk/Trade", value: `${((engines?.risk.risk_per_trade_pct ?? 0.0015) * 100).toFixed(2)}%` },
                { label: "Max Positions", value: String(engines?.risk.max_concurrent_positions ?? 3) },
                { label: "Current Positions", value: String(engines?.risk.current_positions ?? 0) },
                { label: "Daily Loss", value: `${(engines?.risk.current_daily_loss ?? 0).toFixed(2)}% / ${engines?.risk.max_daily_loss_pct ?? 3}%` },
                { label: "Drawdown", value: `${(engines?.risk.current_drawdown ?? 0).toFixed(2)}% / ${engines?.risk.max_drawdown_pct ?? 8}%` },
                { label: "Trades Today", value: `${engines?.risk.trades_today ?? 0} / ${engines?.risk.max_trades_per_day ?? 4}` },
                { label: "Kill Switch", value: engines?.risk.kill_switch ? "ACTIVE" : "OFF" },
              ]}
            />

            {/* Circuit Breakers */}
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <div className="flex items-center gap-2 mb-3">
                <StatusDot ok={!engines?.circuit_breakers.any_paused} />
                <span className="text-sm font-medium">Circuit Breakers</span>
                {engines?.circuit_breakers.any_paused && <span className="text-xs text-red-400 ml-auto">PAUSED</span>}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {["winrate", "slippage", "drawdown_pace", "profit_factor", "correlation", "drawdown_drift"].map(name => {
                  const b = engines?.circuit_breakers.statuses?.[name];
                  const paused = b?.paused || false;
                  return (
                    <div key={name} className="flex items-center justify-between">
                      <span className="text-zinc-400 capitalize">{name.replace(/_/g, " ")}</span>
                      <span className={paused ? "text-red-400" : "text-emerald-400"}>{paused ? "PAUSED" : "CLEAR"}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Execution Engine */}
            <EngineCard
              title="Execution Engine"
              status="READY"
              items={[
                { label: "Mode", value: engines?.execution.mode || "SHADOW" },
                { label: "Last Execution", value: engines?.execution.last_execution || "None" },
                { label: "Orders Today", value: String(engines?.execution.orders_today ?? 0) },
                { label: "Rejected", value: String(engines?.execution.rejected ?? 0) },
              ]}
            />

            {/* MT5 Bridge */}
            <EngineCard
              title="MT5 Bridge"
              status={engines?.mt5.connected ? "CONNECTED" : "DISCONNECTED"}
              items={[
                { label: "Account", value: engines?.mt5.account ? `#${engines.mt5.account.login} ${engines.mt5.account.name}` : "N/A" },
                { label: "Server", value: (engines?.mt5.account?.server as string) || "N/A" },
                { label: "Balance", value: engines?.mt5.account ? `${engines.mt5.account.currency}${(engines.mt5.account.balance as number)?.toLocaleString()}` : "N/A" },
                { label: "Equity", value: engines?.mt5.account ? `${engines.mt5.account.currency}${(engines.mt5.account.equity as number)?.toLocaleString()}` : "N/A" },
                { label: "Free Margin", value: engines?.mt5.account ? `${engines.mt5.account.currency}${(engines.mt5.account.free_margin as number)?.toLocaleString()}` : "N/A" },
                { label: "Leverage", value: engines?.mt5.account ? `${engines.mt5.account.leverage}x` : "N/A" },
              ]}
            />

            {/* Lifecycle Manager */}
            <EngineCard
              title="Lifecycle Manager"
              status="RUNNING"
              items={[
                { label: "Positions Tracked", value: String(engines?.lifecycle.positions_tracked ?? 0) },
                { label: "Breakeven", value: engines?.lifecycle.breakeven_enabled ? "YES" : "NO" },
                { label: "Trailing", value: engines?.lifecycle.trailing_enabled ? "YES" : "NO" },
                { label: "Max Hold", value: `${engines?.lifecycle.max_hold_days ?? 7} days` },
                { label: "Last Action", value: engines?.lifecycle.last_lifecycle_action || "None" },
              ]}
            />

            {/* Telegram */}
            <EngineCard
              title="Telegram"
              status={engines?.telegram.connected ? "CONNECTED" : "NOT CONFIGURED"}
              items={[
                { label: "Bot", value: engines?.telegram.bot || "N/A" },
                { label: "Last Notification", value: engines?.telegram.last_notification || "None" },
                { label: "Status", value: engines?.telegram.last_notification_status || "UNKNOWN" },
              ]}
            />

            {/* Infrastructure */}
            <EngineCard
              title="Infrastructure"
              status={engines?.infrastructure.gaps_detected === 0 ? "HEALTHY" : "DEGRADED"}
              items={[
                { label: "Gaps Detected", value: String(engines?.infrastructure.gaps_detected ?? 0) },
                { label: "Integrity Violations", value: String(engines?.infrastructure.integrity_violations ?? 0) },
              ]}
            />

            {/* Signal Monitor */}
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <h2 className="text-sm font-medium mb-3">Signal Monitor</h2>
              {engines?.signals.recent && engines.signals.recent.length > 0 ? (
                <div className="space-y-2">
                  {engines.signals.recent.map((s, i) => (
                    <div key={i} className="bg-zinc-800 rounded-lg p-2 text-xs font-mono">
                      <div className="flex justify-between">
                        <span className="text-zinc-300">{s.symbol as string || "-"}</span>
                        <span className={s.direction === "BUY" ? "text-emerald-400" : "text-red-400"}>{s.direction as string || "-"}</span>
                      </div>
                      <div className="flex justify-between text-zinc-500 mt-0.5">
                        <span>Entry {(s.entry as number)?.toFixed(5) || "-"}</span>
                        <span>SL {(s.sl as number)?.toFixed(5) || "-"}</span>
                        <span>TP {(s.tp as number)?.toFixed(5) || "-"}</span>
                      </div>
                      <div className="flex justify-between text-zinc-600 mt-0.5">
                        <span>{s.risk_decision as string || "ALLOWED"}</span>
                        <span>{s.execution_status as string || "SHADOW"}</span>
                        <span>{s.timestamp ? new Date(s.timestamp as string).toLocaleTimeString() : "-"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-zinc-600 text-center py-4">No signals yet</p>
              )}
            </div>
          </div>
        )}

        {tab === "config" && (
          <div className="space-y-3">
            <p className="text-sm text-zinc-500">Strategy configuration (read-only)</p>
            {Object.entries(config).map(([k, v]) => (
              <div key={k} className="bg-zinc-900 rounded-lg p-3 border border-zinc-800 flex justify-between text-sm">
                <span className="text-zinc-400">{k}</span>
                <span className="font-mono">{v}</span>
              </div>
            ))}
          </div>
        )}

        <p className="text-xs text-zinc-700 text-center mt-4">Last updated: {lastUpdate} &middot; {currentTime}</p>
      </main>

      <nav className="fixed bottom-0 inset-x-0 bg-zinc-900 border-t border-zinc-800 flex justify-around py-2 px-4">
        <button onClick={() => setTab("overview")} className={`text-xs ${tab === "overview" ? "text-zinc-100 font-medium" : "text-zinc-500"}`}>Overview</button>
        <button onClick={() => setTab("engines")} className={`text-xs ${tab === "engines" ? "text-zinc-100 font-medium" : "text-zinc-500"}`}>Engines</button>
        <button onClick={() => setTab("signals")} className={`text-xs ${tab === "signals" ? "text-zinc-100 font-medium" : "text-zinc-500"}`}>Signals</button>
        <button onClick={() => router.push("/backtest")} className="text-xs text-zinc-500">Backtest</button>
        <button onClick={() => setTab("users")} className={`text-xs ${tab === "users" ? "text-zinc-100 font-medium" : "text-zinc-500"}`}>Users</button>
        <button onClick={() => setTab("config")} className={`text-xs ${tab === "config" ? "text-zinc-100 font-medium" : "text-zinc-500"}`}>Config</button>
      </nav>
    </div>
  );
}
