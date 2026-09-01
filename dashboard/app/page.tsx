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
        <p className="text-xs text-zinc-600 mt-0.5">
          {session.username} &middot; Shadow Observer
        </p>
      </header>

      <main className="flex-1 px-4 py-4 space-y-4 max-w-lg mx-auto w-full">
        <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
          <div className="flex items-center gap-2 mb-3">
            <StatusDot ok={isHealthy} />
            <span className="font-medium text-sm">
              {health?.status || "Unknown"}
            </span>
            {health?.data_stale && (
              <span className="text-xs text-amber-400 ml-auto">Stale</span>
            )}
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
              <p className="text-zinc-500 text-xs">Bars Processed</p>
              <p className="font-mono">{health?.bars_processed ?? "-"}</p>
            </div>
            <div>
              <p className="text-zinc-500 text-xs">Signals Emitted</p>
              <p className="font-mono">{health?.signals_emitted ?? "-"}</p>
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

        <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
          <h2 className="text-sm font-medium mb-2">Zero Orders Guard</h2>
          <div className="flex items-center gap-3">
            <StatusDot ok={(zeroOrders?.orders_submitted ?? 0) === 0} />
            <span className="font-mono text-sm">
              {zeroOrders?.orders_submitted ?? 0} / {zeroOrders?.blocked_attempts ?? 0}
            </span>
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
          Last updated: {lastUpdate}
        </p>
      </main>

      <nav className="fixed bottom-0 inset-x-0 bg-zinc-900 border-t border-zinc-800 flex justify-around py-2 px-4">
        <span className="text-xs text-zinc-100 font-medium">Dashboard</span>
      </nav>
    </div>
  );
}
