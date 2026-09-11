"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface ExecutionStatus {
  mode: string;
  running: boolean;
  kill_switch: boolean;
  orders_submitted: number;
  orders_filled: number;
  orders_rejected: number;
  positions_closed: number;
  open_positions: number;
}

export default function ExecutePage() {
  const router = useRouter();
  const [status, setStatus] = useState<ExecutionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const meRes = await fetch("/api/auth/me");
        if (!meRes.ok) { router.push("/login"); return; }
        const me = await meRes.json();
        if (me.role !== "admin") { router.push("/"); return; }
        await refreshStatus();
      } catch { router.push("/login"); }
      setLoading(false);
    }
    load();
  }, [router]);

  async function refreshStatus() {
    try {
      const res = await fetch("/api/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "status" }),
      });
      if (res.ok) {
        const d = await res.json();
        setStatus({
          mode: d.kill_switch ? "STOPPED" : "SHADOW",
          running: !d.kill_switch,
          kill_switch: d.kill_switch,
          orders_submitted: 0,
          orders_filled: 0,
          orders_rejected: 0,
          positions_closed: 0,
          open_positions: 0,
        });
      }
    } catch { /* ignore */ }
  }

  useEffect(() => {
    if (!status?.running) return;
    const interval = setInterval(refreshStatus, 10000);
    return () => clearInterval(interval);
  }, [status?.running]);

  async function handleStart(enableExecution: boolean) {
    setStarting(true);
    try {
      const res = await fetch("/api/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "start", enable_execution: enableExecution }),
      });
      if (res.ok) {
        const d = await res.json();
        setStatus(prev => prev ? { ...prev, mode: d.mode, running: true } : null);
      }
    } catch { /* ignore */ }
    setStarting(false);
  }

  async function handleStop() {
    try {
      await fetch("/api/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "stop" }),
      });
      setStatus(prev => prev ? { ...prev, running: false, kill_switch: true } : null);
    } catch { /* ignore */ }
  }

  if (loading) return <div className="flex-1 flex items-center justify-center"><p className="text-zinc-500">Loading...</p></div>;

  return (
    <div className="flex-1 flex flex-col pb-20">
      <header className="px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold">Live Execution</h1>
          <button onClick={() => router.back()} className="text-sm text-zinc-500">Back</button>
        </div>
      </header>

      <main className="flex-1 px-4 py-4 max-w-lg mx-auto w-full space-y-4">
        <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
          <div className="flex items-center gap-2 mb-3">
            <span className={`inline-block w-2 h-2 rounded-full ${status?.running ? "bg-emerald-400" : "bg-zinc-600"}`} />
            <span className="font-medium text-sm">{status?.mode || "UNKNOWN"}</span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><p className="text-zinc-500 text-xs">Orders Submitted</p><p className="font-mono">{status?.orders_submitted ?? 0}</p></div>
            <div><p className="text-zinc-500 text-xs">Filled</p><p className="font-mono text-emerald-400">{status?.orders_filled ?? 0}</p></div>
            <div><p className="text-zinc-500 text-xs">Rejected</p><p className="font-mono text-amber-400">{status?.orders_rejected ?? 0}</p></div>
            <div><p className="text-zinc-500 text-xs">Positions Closed</p><p className="font-mono">{status?.positions_closed ?? 0}</p></div>
          </div>
        </div>

        <div className="space-y-2">
          <button
            onClick={() => handleStart(false)}
            disabled={starting || status?.running}
            className="w-full py-3 bg-zinc-800 text-zinc-300 font-medium rounded-lg border border-zinc-700 disabled:opacity-40 text-sm"
          >
            {starting ? "Starting..." : "Start Shadow Mode"}
          </button>

          <button
            onClick={() => handleStart(true)}
            disabled={starting || status?.running}
            className="w-full py-3 bg-amber-900/50 text-amber-300 font-medium rounded-lg border border-amber-700 disabled:opacity-40 text-sm"
          >
            {starting ? "Starting..." : "Start LIVE Execution"}
          </button>

          <button
            onClick={handleStop}
            disabled={!status?.running}
            className="w-full py-3 bg-red-900/50 text-red-300 font-medium rounded-lg border border-red-700 disabled:opacity-40 text-sm"
          >
            Stop (Kill Switch)
          </button>
        </div>

        <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
          <h2 className="text-sm font-medium text-zinc-400 mb-2">Pipeline</h2>
          <div className="space-y-1 text-xs text-zinc-500 font-mono">
            <p>Signal Generator → TradeIntent</p>
            <p>Risk Evaluator → RiskDecision</p>
            <p>OrderRequest → WineFlaskExecutionAdapter</p>
            <p>MT5 Bridge → MetaTrader5</p>
            <p className="text-zinc-600">magic={20260831} risk=0.30%</p>
          </div>
        </div>
      </main>

      <nav className="fixed bottom-0 inset-x-0 bg-zinc-900 border-t border-zinc-800 flex justify-around py-2 px-4">
        <button onClick={() => router.push("/admin")} className="text-xs text-zinc-500">Overview</button>
        <button onClick={() => router.push("/backtest")} className="text-xs text-zinc-500">Backtest</button>
        <button onClick={() => router.push("/execute")} className="text-xs text-zinc-100 font-medium">Execute</button>
      </nav>
    </div>
  );
}
