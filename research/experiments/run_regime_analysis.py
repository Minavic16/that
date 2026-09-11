"""Run regime analysis on all 20 pairs and save results.

Usage:
    cd /root/nestquant && .venv/bin/python -u scripts/run_regime_analysis.py --timeframe 1h
    cd /root/nestquant && .venv/bin/python -u scripts/run_regime_analysis.py --timeframe 4h
    cd /root/nestquant && .venv/bin/python -u scripts/run_regime_analysis.py --timeframe 1min
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from collections import Counter

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.phase3_research import (
    prepare_pair,
    regime_analysis,
    characterize_zscore_distribution,
    DEFAULT_HORIZONS,
)

RESULTS_DIR = Path("/root/nestquant/research_data/phase3")

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF",
    "EUR/GBP", "EUR/CHF", "EUR/CAD", "EUR/AUD", "GBP/JPY",
    "GBP/CAD", "GBP/AUD", "AUD/JPY", "AUD/CAD", "AUD/CHF",
    "NZD/USD", "NZD/JPY", "NZD/CHF", "CAD/JPY", "CAD/CHF",
]


def run_regime_analysis(timeframe: str = "1h", lookback: int = 20) -> dict:
    all_results = {}
    regime_counts_global: Counter = Counter()

    for i, pair in enumerate(PAIRS):
        print(f"[{i + 1}/{len(PAIRS)}] Processing {pair}...", flush=True)
        t0 = time.time()
        data = prepare_pair(pair, timeframe=timeframe, lookback=lookback)
        if data is None:
            print(f"  SKIP: could not load {pair}", flush=True)
            continue
        elapsed = time.time() - t0

        n = len(data.close)
        regime_dist = Counter(
            f"{t}×{v}" for t, v in zip(data.regime_trend, data.regime_vol)
        )
        regime_counts_global.update(regime_dist)

        zscore_stats = characterize_zscore_distribution(data.z_scores)
        print(f"  {n:,} bars, {elapsed:.1f}s", flush=True)
        print(f"  Z-score: mean={zscore_stats.get('mean', 0):.4f}, "
              f"std={zscore_stats.get('std', 0):.4f}", flush=True)
        print(f"  Regimes: {dict(regime_dist.most_common(5))}", flush=True)

        pair_regime = {}
        for horizon in data.horizons:
            ra = regime_analysis(data, horizon=horizon)
            pair_regime[f"h{horizon}"] = ra

        all_results[pair] = {
            "n_bars": n,
            "timeframe": timeframe,
            "processing_time_s": round(elapsed, 1),
            "zscore_stats": zscore_stats,
            "regime_distribution": dict(regime_dist),
            "regime_analysis": pair_regime,
        }

    total_regimes = sum(regime_counts_global.values())
    avg_distribution = {
        k: {"count": v, "pct": round(v / total_regimes * 100, 2)}
        for k, v in sorted(regime_counts_global.items(), key=lambda x: -x[1])
    }

    return {
        "timeframe": timeframe,
        "lookback": lookback,
        "horizons": DEFAULT_HORIZONS,
        "pair_results": all_results,
        "aggregate_regime_distribution": avg_distribution,
        "total_pairs": len(all_results),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run regime analysis")
    parser.add_argument("--timeframe", default="1h",
                        choices=["1min", "5min", "15min", "30min", "1h", "4h"],
                        help="Data timeframe (default: 1h)")
    parser.add_argument("--lookback", type=int, default=20,
                        help="Z-score lookback in bars (default: 20)")
    args = parser.parse_args()

    t0 = time.time()
    results = run_regime_analysis(timeframe=args.timeframe, lookback=args.lookback)
    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.0f}s ({elapsed / 60:.1f}min)", flush=True)
    print(f"Pairs processed: {results['total_pairs']}", flush=True)

    out_path = RESULTS_DIR / f"regime_analysis_{args.timeframe}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved to {out_path}", flush=True)
