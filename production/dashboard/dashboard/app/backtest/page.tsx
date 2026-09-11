"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface PairMetrics {
  n_trades: number;
  win_rate: number;
  profit_factor: number;
  avg_pnl_pips_expectancy: number;
  total_net_pnl_pips: number;
  max_dd_r: number;
  max_loss_streak: number;
  losing_months: number;
  exit_reason_mix: Record<string, number>;
}

interface PairData {
  metrics_b: PairMetrics;
  diff: { affected_pct: number };
}

interface AggregateMetrics {
  n_trades: number;
  win_rate: number;
  profit_factor: number;
  avg_pnl_pips_expectancy: number;
  total_net_pnl_pips: number;
  max_dd_r: number;
  max_loss_streak: number;
  losing_months: number;
}

interface S6CData {
  experiment_id: string;
  config: Record<string, unknown>;
  aggregate: { metrics_B: AggregateMetrics };
  per_pair: Record<string, PairData>;
}

export default function BacktestPage() {
  const router = useRouter();
  const [data, setData] = useState<S6CData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const meRes = await fetch("/api/auth/me");
        if (!meRes.ok) { router.push("/login"); return; }
        const res = await fetch("/api/backtest?experiment=s6c");
        if (res.ok) {
          const d = await res.json();
          setData(d.data);
        }
      } catch { /* ignore */ }
      setLoading(false);
    }
    load();
  }, [router]);

  if (loading) return <div className="flex-1 flex items-center justify-center"><p className="text-zinc-500">Loading...</p></div>;

  const pairs = data?.per_pair ? Object.entries(data.per_pair).sort(
    (a, b) => (b[1].metrics_b?.profit_factor || 0) - (a[1].metrics_b?.profit_factor || 0)
  ) : [];

  const agg = data?.aggregate?.metrics_B;

  return (
    <div className="flex-1 flex flex-col pb-20">
      <header className="px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-bold">Backtest Results</h1>
          <button onClick={() => router.back()} className="text-sm text-zinc-500">Back</button>
        </div>
      </header>

      <main className="flex-1 px-4 py-4 max-w-lg mx-auto w-full space-y-4">
        {data && (
          <>
            <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
              <h2 className="text-sm font-medium text-zinc-400 mb-1">{data.experiment_id} — Variant B (Frozen)</h2>
              <p className="text-xs text-zinc-600 mb-3">Causal swing breakout, 4h, 20 FX pairs, 2016-2026</p>
              {agg && (
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div><p className="text-zinc-500 text-xs">Trades</p><p className="font-mono text-lg">{agg.n_trades?.toLocaleString()}</p></div>
                  <div><p className="text-zinc-500 text-xs">Win Rate</p><p className="font-mono text-lg">{(agg.win_rate * 100).toFixed(1)}%</p></div>
                  <div><p className="text-zinc-500 text-xs">Profit Factor</p><p className="font-mono text-lg">{agg.profit_factor?.toFixed(3)}</p></div>
                  <div><p className="text-zinc-500 text-xs">Expectancy</p><p className="font-mono text-lg text-emerald-400">+{agg.avg_pnl_pips_expectancy?.toFixed(2)} pip</p></div>
                  <div><p className="text-zinc-500 text-xs">Total PnL</p><p className="font-mono text-lg text-emerald-400">+{agg.total_net_pnl_pips?.toLocaleString()} pip</p></div>
                  <div><p className="text-zinc-500 text-xs">Max DD</p><p className="font-mono text-lg text-amber-400">{agg.max_dd_r?.toFixed(1)}R</p></div>
                  <div><p className="text-zinc-500 text-xs">Max Loss Streak</p><p className="font-mono">{agg.max_loss_streak}</p></div>
                  <div><p className="text-zinc-500 text-xs">Losing Months</p><p className="font-mono">{agg.losing_months}</p></div>
                </div>
              )}
            </div>

            {data.config && (
              <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
                <h2 className="text-sm font-medium text-zinc-400 mb-2">Config</h2>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  {Object.entries(data.config).map(([k, v]) => (
                    <div key={k}>
                      <span className="text-zinc-600">{k}: </span>
                      <span className="font-mono text-zinc-300">{String(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {pairs.length > 0 && (
              <div className="bg-zinc-900 rounded-xl p-4 border border-zinc-800">
                <h2 className="text-sm font-medium text-zinc-400 mb-3">Per-Pair Breakdown (Variant B)</h2>
                <div className="space-y-2">
                  {pairs.map(([pair, p]) => {
                    const m = p.metrics_b;
                    if (!m) return null;
                    return (
                      <div key={pair} className="text-sm py-1.5 border-b border-zinc-800 last:border-0">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs w-20">{pair}</span>
                          <div className="flex gap-3 text-xs">
                            <span className="text-zinc-500">n={m.n_trades}</span>
                            <span className={m.win_rate > 0.36 ? "text-emerald-400" : "text-zinc-400"}>{(m.win_rate * 100).toFixed(1)}%</span>
                            <span className={m.profit_factor > 1.5 ? "text-emerald-400" : "text-amber-400"}>PF {m.profit_factor?.toFixed(2)}</span>
                            <span className="text-emerald-400">+{m.avg_pnl_pips_expectancy?.toFixed(1)}</span>
                          </div>
                        </div>
                        <div className="flex gap-3 text-xs text-zinc-600 mt-0.5">
                          <span>PnL +{m.total_net_pnl_pips?.toFixed(0)}</span>
                          <span>DD {m.max_dd_r?.toFixed(1)}R</span>
                          <span>streak {m.max_loss_streak}</span>
                          {m.exit_reason_mix && (
                            <span>SL={m.exit_reason_mix.SL} TP={m.exit_reason_mix.TP} MH={m.exit_reason_mix.MH}</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        )}

        {!data && !loading && (
          <div className="text-center py-12 text-zinc-600 text-sm">No data available</div>
        )}
      </main>

      <nav className="fixed bottom-0 inset-x-0 bg-zinc-900 border-t border-zinc-800 flex justify-around py-2 px-4">
        <button onClick={() => router.push("/admin")} className="text-xs text-zinc-500">Overview</button>
        <button onClick={() => router.push("/backtest")} className="text-xs text-zinc-100 font-medium">Backtest</button>
        <button onClick={() => router.push("/execute")} className="text-xs text-zinc-500">Execute</button>
      </nav>
    </div>
  );
}
