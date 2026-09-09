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
  notes: string[];
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

type Tab = "overview" | "signals" | "users" | "config";

export default function AdminPage() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [health, setHealth] = useState<HealthData | null>(null);
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
      const [hRes, sRes, uRes, cRes] = await Promise.all([
        fetch("/api/health"),
        fetch("/api/signals?limit=50"),
        fetch("/api/users"),
        fetch("/api/config"),
      ]);
      if (hRes.ok) setHealth(await hRes.json());
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

  return (
    <div className="flex-1 flex flex-col pb-20">
      <header className="px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold">NestQuant Admin</h1>
          <button onClick={handleLogout} className="text-sm text-zinc-500 hover:text-zinc-300">Sign out</button>
        </div>
        <div className="flex items-center justify-between mt-0.5">
          <p className="text-xs text-zinc-600">{session.username} &middot; Admin</p>
          <p className="text-xs text-zinc-600 font-mono">{currentTime || "-"}</p>
        </div>
      </header>

      <main className="flex-1 px-4 py-4 max-w-lg mx-auto w-full">
        {tab === "overview" && (
          <div className="space-y-4">
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <div className="flex items-center gap-2 mb-3">
                <StatusDot ok={isHealthy} />
                <span className="font-medium text-sm">{health?.status || "Unknown"}</span>
                {health?.data_stale && <span className="text-xs text-amber-400 ml-auto">Stale</span>}
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-zinc-500 text-xs">Uptime</p><p className="font-mono">{health ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m` : "-"}</p></div>
                <div><p className="text-zinc-500 text-xs">Bars</p><p className="font-mono">{health?.bars_processed ?? "-"}</p></div>
                <div><p className="text-zinc-500 text-xs">Signals</p><p className="font-mono">{health?.signals_emitted ?? "-"}</p></div>
                <div><p className="text-zinc-500 text-xs">Latency p50</p><p className="font-mono">{health?.avg_latency_ms ? `${health.avg_latency_ms.toFixed(1)}ms` : "-"}</p></div>
                <div><p className="text-zinc-500 text-xs">Latency p95</p><p className="font-mono">{health?.p95_latency_ms ? `${health.p95_latency_ms.toFixed(1)}ms` : "-"}</p></div>
                <div><p className="text-zinc-500 text-xs">Gaps</p><p className="font-mono">{health?.gaps_detected ?? "-"}</p></div>
                <div><p className="text-zinc-500 text-xs">Integrity</p><p className="font-mono">{health?.integrity_violations ?? 0}</p></div>
                <div><p className="text-zinc-500 text-xs">Kill Switch</p><p className="font-mono">{health?.kill_switch_active ? <span className="text-red-400">ON</span> : <span className="text-emerald-400">off</span>}</p></div>
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
        <button onClick={() => setTab("signals")} className={`text-xs ${tab === "signals" ? "text-zinc-100 font-medium" : "text-zinc-500"}`}>Signals</button>
        <button onClick={() => router.push("/backtest")} className="text-xs text-zinc-500">Backtest</button>
        <button onClick={() => router.push("/execute")} className="text-xs text-zinc-500">Execute</button>
        <button onClick={() => setTab("users")} className={`text-xs ${tab === "users" ? "text-zinc-100 font-medium" : "text-zinc-500"}`}>Users</button>
        <button onClick={() => setTab("config")} className={`text-xs ${tab === "config" ? "text-zinc-100 font-medium" : "text-zinc-500"}`}>Config</button>
      </nav>
    </div>
  );
}
