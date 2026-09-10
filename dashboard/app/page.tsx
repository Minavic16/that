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
  execution_mode: string;
  mt5_connected: boolean;
  open_positions: number;
  orders_submitted: number;
  equity: number;
  balance: number;
  peak_equity: number;
  starting_capital: number;
  total_pnl: number;
  daily_pnl: number;
  total_return_pct: number;
  current_drawdown_pct: number;
  max_drawdown_pct: number;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  risk_per_trade_pct: number;
  max_drawdown_limit_pct: number;
  runner_health: string;
  last_evaluation: string | null;
  notes: string[];
}

interface ZeroOrders {
  orders_submitted: number;
  blocked_attempts: number;
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${ok ? "bg-emerald-400" : "bg-red-400"}`}
    />
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [zeroOrders, setZeroOrders] = useState<ZeroOrders | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string>("");
  const [currentTime, setCurrentTime] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const meRes = await fetch("/api/auth/me");
        if (!meRes.ok) {
          router.push("/login");
          return;
        }
        const me = await meRes.json();
        setSession(me);

        if (me.role === "admin") {
          router.push("/admin");
          return;
        }

        const [healthRes, statusRes] = await Promise.all([
          fetch("/api/health"),
          fetch("/api/status"),
        ]);

        if (healthRes.ok) setHealth(await healthRes.json());
        if (statusRes.ok) {
          const s = await statusRes.json();
          setZeroOrders(s.zero_orders);
        }

        setLastUpdate(new Date().toLocaleTimeString());
      } catch {
        // ignore
      }
      setLoading(false);
    }
    load();
  }, [router]);

  useEffect(() => {
    if (!session || session.role === "admin") return;
    const interval = setInterval(async () => {
      try {
        const [healthRes, statusRes] = await Promise.all([
          fetch("/api/health"),
          fetch("/api/status"),
        ]);
        if (healthRes.ok) setHealth(await healthRes.json());
        if (statusRes.ok) {
          const s = await statusRes.json();
          setZeroOrders(s.zero_orders);
        }
        setLastUpdate(new Date().toLocaleTimeString());
      } catch {
        // ignore
      }
    }, 30000);
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

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-zinc-500">Loading...</p>
      </div>
    );
  }

  if (!session || session.role === "admin") return null;

  const isHealthy = health?.status === "HEALTHY";

  return (
    <div className="flex-1 flex flex-col pb-20">
      <header className="px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold">NestQuant</h1>
          <button
            onClick={handleLogout}
            className="text-sm text-zinc-500 hover:text-zinc-300"
          >
            Sign out
          </button>
        </div>
        <div className="flex items-center justify-between mt-0.5">
          <p className="text-xs text-zinc-600">
            {session.username} &middot; Shadow Observer
          </p>
          <p className="text-xs text-zinc-600 font-mono">{currentTime || "-"}</p>
        </div>
      </header>

      <main className="flex-1 px-4 py-4 space-y-4 max-w-lg mx-auto w-full">
        {/* System Status */}
        <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
          <div className="flex items-center gap-2 mb-3">
            <StatusDot ok={isHealthy} />
            <span className="font-medium text-sm">
              {health?.status || "Unknown"}
            </span>
            {health?.data_stale && (
              <span className="text-xs text-amber-400 ml-auto">Stale</span>
            )}
            <span className={`text-xs px-2 py-0.5 rounded ml-auto ${health?.execution_mode === "SHADOW" ? "bg-amber-900 text-amber-300" : health?.execution_mode === "LIVE" ? "bg-red-900 text-red-300" : "bg-zinc-800 text-zinc-400"}`}>
              {health?.execution_mode || "UNKNOWN"}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-zinc-500 text-xs">Uptime</p>
              <p className="font-mono">
                {health
                  ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m`
                  : "-"}
              </p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">MT5</p>
              <p className="font-mono">
                {health?.mt5_connected ? (
                  <span className="text-emerald-400">Connected</span>
                ) : (
                  <span className="text-red-400">Disconnected</span>
                )}
              </p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Bars Processed</p>
              <p className="font-mono">{health?.bars_processed ?? "-"}</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Signals Emitted</p>
              <p className="font-mono">{health?.signals_emitted ?? "-"}</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Open Positions</p>
              <p className="font-mono">{health?.open_positions ?? 0}</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Kill Switch</p>
              <p className="font-mono">
                {health?.kill_switch_active ? (
                  <span className="text-red-400">ACTIVE</span>
                ) : (
                  <span className="text-emerald-400">off</span>
                )}
              </p>
            </div>
          </div>
        </div>

        {/* Account Overview */}
        <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
          <h2 className="text-sm font-medium mb-3">Account</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-zinc-500 text-xs">Equity</p>
              <p className="font-mono text-lg">${(health?.equity ?? 0).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Balance</p>
              <p className="font-mono">${(health?.balance ?? 0).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Starting Capital</p>
              <p className="font-mono">${(health?.starting_capital ?? 0).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Peak Equity</p>
              <p className="font-mono">${(health?.peak_equity ?? 0).toLocaleString()}</p>
            </div>
          </div>
        </div>

        {/* P&L */}
        <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
          <h2 className="text-sm font-medium mb-3">Profit & Loss</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-zinc-500 text-xs">Total P&L</p>
              <p className={`font-mono ${(health?.total_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                ${(health?.total_pnl ?? 0).toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Daily P&L</p>
              <p className={`font-mono ${(health?.daily_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                ${(health?.daily_pnl ?? 0).toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Total Return</p>
              <p className={`font-mono ${(health?.total_return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {(health?.total_return_pct ?? 0).toFixed(2)}%
              </p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Open P&L</p>
              <p className="font-mono">${(health?.open_positions ?? 0) > 0 ? "—" : "0"}</p>
            </div>
          </div>
        </div>

        {/* Drawdown */}
        <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
          <h2 className="text-sm font-medium mb-3">Drawdown</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-zinc-500 text-xs">Current DD</p>
              <p className="font-mono text-amber-400">{(health?.current_drawdown_pct ?? 0).toFixed(2)}%</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Max DD</p>
              <p className="font-mono text-amber-400">{(health?.max_drawdown_pct ?? 0).toFixed(2)}%</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">DD Limit</p>
              <p className="font-mono">{(health?.max_drawdown_limit_pct ?? 8).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">DD Remaining</p>
              <p className="font-mono">{Math.max(0, (health?.max_drawdown_limit_pct ?? 8) - (health?.current_drawdown_pct ?? 0)).toFixed(2)}%</p>
            </div>
          </div>
        </div>

        {/* Trading */}
        <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
          <h2 className="text-sm font-medium mb-3">Trading</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-zinc-500 text-xs">Total Trades</p>
              <p className="font-mono">{health?.total_trades ?? 0}</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Win Rate</p>
              <p className="font-mono">{(health?.win_rate ?? 0).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Profit Factor</p>
              <p className="font-mono">{(health?.profit_factor ?? 0).toFixed(3)}</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Risk/Trade</p>
              <p className="font-mono">{((health?.risk_per_trade_pct ?? 0.0015) * 100).toFixed(2)}%</p>
            </div>
          </div>
        </div>

        {health?.notes && health.notes.length > 0 && (
          <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
            <h2 className="text-sm font-medium mb-2">Notes</h2>
            <ul className="space-y-1">
              {health.notes.slice(0, 5).map((note, i) => (
                <li key={i} className="text-xs text-zinc-500 font-mono">
                  {note}
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="text-xs text-zinc-700 text-center">
          Last updated: {lastUpdate} &middot; {currentTime}
        </p>
      </main>

      <nav className="fixed bottom-0 inset-x-0 bg-zinc-900 border-t border-zinc-800 flex justify-around py-2 px-4">
        <span className="text-xs text-zinc-100 font-medium">Dashboard</span>
      </nav>
    </div>
  );
}
