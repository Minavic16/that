"""Equal-elapsed-time forward-return comparison across timeframes.

Computes forward returns at elapsed-time-equivalent horizons across
1min, 15min, 1h, and 4h data. For example:

    ~1 hour:   1M=60 bars, 15M=4 bars, 1H=1 bar, 4H=1 bar (fractional)
    ~4 hours:  1M=240 bars, 15M=16 bars, 1H=4 bars, 4H=1 bar
    ~24 hours: 1M=1440 bars, 15M=96 bars, 1H=24 bars, 4H=6 bars
    ~48 hours: 1M=2880 bars, 15M=192 bars, 1H=48 bars, 4H=12 bars

This isolates: "Does a higher timeframe contain more predictive information
per unit of elapsed market time?" from "Does a higher timeframe produce
larger returns per bar?"

All computations are strictly causal. Forward returns use only
close[t+h] - close[t], never touching future data in feature construction.
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd


from nestquant.research.shared.zscore.regime import classify_regime_chunked
from nestquant.research.shared.zscore.zscore import _zscore_causal_core

DATA_DIR = Path("/root/data")
RESULTS_DIR = Path("research/output/phase3")

PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF",
    "EUR/GBP", "EUR/CHF", "EUR/CAD", "EUR/AUD", "GBP/JPY",
    "GBP/CAD", "GBP/AUD", "AUD/JPY", "AUD/CAD", "AUD/CHF",
    "NZD/USD", "NZD/JPY", "NZD/CHF", "CAD/JPY", "CAD/CHF",
]

# Elapsed-time targets in minutes
ELAPSED_TARGETS = {
    "1h": 60,
    "4h": 240,
    "24h": 1440,
    "48h": 2880,
}

# Bars per calendar minute for each timeframe
BARS_PER_MINUTE = {
    "1min": 1.0,
    "15min": 1.0 / 15.0,
    "1h": 1.0 / 60.0,
    "4h": 1.0 / 240.0,
}

# Maximum usable bars per timeframe (limited by data length minus lookback)
MAX_BARS = {
    "1min": 3_900_000,
    "15min": 260_000,
    "1h": 65_000,
    "4h": 17_000,
}


def load_pair(pair: str, timeframe: str) -> pd.DataFrame | None:
    pair_file = pair.replace("/", "_")
    tf_dir = DATA_DIR / timeframe
    tf_path = tf_dir / f"{pair_file}.pkl"
    if tf_path.exists():
        with open(tf_path, "rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict):
            return data.get(pair)
        return data
    flat_path = DATA_DIR / f"{pair_file}.pkl"
    if flat_path.exists():
        with open(flat_path, "rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict):
            return data.get(pair)
        return data
    return None


def compute_forward_returns(close: np.ndarray, horizon_bars: int) -> np.ndarray:
    """Causal forward return: (close[t+h] - close[t]) / close[t]."""
    n = len(close)
    fr = np.full(n, np.nan)
    if n > horizon_bars:
        fr[:n - horizon_bars] = (
            (close[horizon_bars:] - close[:n - horizon_bars]) / close[:n - horizon_bars]
        )
    return fr


def compute_regime_labels(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                          timestamps: pd.DatetimeIndex, pair: str) -> list[str]:
    """Compute regime labels using causal chunked classification."""
    try:
        regimes = classify_regime_chunked(
            close, high, low, timestamps, pair,
            chunk_size=1000, ema_span=200, atr_period=14,
        )
        return [f"{r.trend}×{r.volatility}" for r in regimes]
    except Exception:
        return ["unknown"] * len(close)


def bars_for_elapsed(tf: str, elapsed_minutes: float) -> int:
    """How many bars of this timeframe approximate the given elapsed time?"""
    return max(1, int(round(BARS_PER_MINUTE[tf] * elapsed_minutes)))


def run_elapsed_time_analysis(lookback: int = 20) -> dict:
    """Run forward-return analysis at equal-elapsed-time horizons."""
    results = {}

    for tf in ["1min", "15min", "1h", "4h"]:
        print(f"\n{'='*60}")
        print(f"  Timeframe: {tf}")
        print(f"{'='*60}")

        tf_results = {}
        t0 = time.time()

        for pair in PAIRS:
            df = load_pair(pair, tf)
            if df is None or len(df) < lookback + 100:
                continue

            close = df["close"].values.astype(np.float64)
            high = df["high"].values.astype(np.float64)
            low = df["low"].values.astype(np.float64)
            ts = df.index
            n = len(close)

            # Compute Z-scores (causal)
            z_scores, _, _ = _zscore_causal_core(close, lookback)

            # Compute regimes (causal)
            regime_labels = compute_regime_labels(close, high, low, ts, pair)

            pair_data = {
                "n_bars": n,
                "pair": pair,
                "timeframe": tf,
                "regimes": {},
            }

            for target_name, elapsed_min in ELAPSED_TARGETS.items():
                h_bars = bars_for_elapsed(tf, elapsed_min)
                max_h = n - lookback - 1
                if h_bars > max_h:
                    # Horizon exceeds available data
                    pair_data["regimes"][target_name] = {
                        "horizon_bars": h_bars,
                        "elapsed_minutes": elapsed_min,
                        "status": "insufficient_data",
                        "max_available_bars": max_h,
                    }
                    continue

                # Causal forward returns
                fr = compute_forward_returns(close, h_bars)

                # Regime-grouped statistics
                regime_stats = {}
                for regime in set(regime_labels):
                    mask = np.array([r == regime for r in regime_labels])
                    # Only use bars where both z-score and forward return are valid
                    valid = mask & np.isfinite(z_scores) & np.isfinite(fr)
                    n_valid = int(valid.sum())
                    if n_valid < 30:
                        continue

                    fr_valid = fr[valid]
                    z_valid = z_scores[valid]

                    mean_fr = float(np.mean(fr_valid))
                    std_fr = float(np.std(fr_valid, ddof=1))
                    se_fr = std_fr / np.sqrt(n_valid)
                    ci_lower = mean_fr - 1.96 * se_fr
                    ci_upper = mean_fr + 1.96 * se_fr
                    positive_freq = float(np.mean(fr_valid > 0) * 100)

                    # Convert to pips (approximate: 1 pip = 0.0001 for most pairs)
                    pip = 0.01 if "JPY" in pair else 0.0001

                    # Z-score direction splits
                    long_mask = valid & (z_scores < -1.0)
                    short_mask = valid & (z_scores > 1.0)
                    n_long = int(long_mask.sum())
                    n_short = int(short_mask.sum())

                    regime_stats[regime] = {
                        "n": n_valid,
                        "horizon_bars": h_bars,
                        "elapsed_minutes": elapsed_min,
                        "mean_return": mean_fr,
                        "mean_return_pips": mean_fr / pip,
                        "std_return": std_fr,
                        "std_return_pips": std_fr / pip,
                        "se_pips": se_fr / pip,
                        "ci_lower_pips": ci_lower / pip,
                        "ci_upper_pips": ci_upper / pip,
                        "positive_freq_pct": positive_freq,
                        "median_return": float(np.median(fr_valid)),
                        "median_pips": float(np.median(fr_valid)) / pip,
                        "n_long_zscore": n_long,
                        "n_short_zscore": n_short,
                        "mean_long_pips": float(np.mean(fr[long_mask])) / pip if n_long > 0 else None,
                        "mean_short_pips": float(np.mean(fr[short_mask])) / pip if n_short > 0 else None,
                    }

                pair_data["regimes"][target_name] = {
                    "horizon_bars": h_bars,
                    "elapsed_minutes": elapsed_min,
                    "status": "ok",
                    "regimes": regime_stats,
                }

            tf_results[pair] = pair_data

        elapsed = time.time() - t0
        print(f"  Processed {len(tf_results)} pairs in {elapsed:.1f}s")

        # Aggregate across pairs
        agg = aggregate_across_pairs(tf_results)
        results[tf] = {"pair_results": tf_results, "aggregate": agg}

    return results


def aggregate_across_pairs(tf_results: dict) -> dict:
    """Aggregate regime statistics across all pairs."""
    agg = {}
    for target_name in ELAPSED_TARGETS:
        regime_totals = {}
        for pair, pdata in tf_results.items():
            target_data = pdata["regimes"].get(target_name, {})
            if target_data.get("status") != "ok":
                continue
            for regime, stats in target_data.get("regimes", {}).items():
                if regime not in regime_totals:
                    regime_totals[regime] = {
                        "n_total": 0,
                        "sum_mean_pips": 0.0,
                        "sum_var_pips2": 0.0,
                        "pair_count": 0,
                        "pairs_positive": 0,
                    }
                rt = regime_totals[regime]
                rt["n_total"] += stats["n"]
                rt["sum_mean_pips"] += stats["mean_return_pips"] * stats["n"]
                rt["sum_var_pips2"] += (stats["std_return_pips"] ** 2) * stats["n"]
                rt["pair_count"] += 1
                if stats["mean_return_pips"] > 0:
                    rt["pairs_positive"] += 1

        # Compute pooled statistics
        agg_regimes = {}
        for regime, rt in regime_totals.items():
            n = rt["n_total"]
            if n == 0:
                continue
            pooled_mean = rt["sum_mean_pips"] / n
            pooled_var = rt["sum_var_pips2"] / n - pooled_mean ** 2
            pooled_std = max(0.0, pooled_var) ** 0.5
            pooled_se = pooled_std / n ** 0.5 if n > 0 else 0.0

            agg_regimes[regime] = {
                "n": n,
                "pooled_mean_pips": pooled_mean,
                "pooled_std_pips": pooled_std,
                "pooled_se_pips": pooled_se,
                "ci_lower_pips": pooled_mean - 1.96 * pooled_se,
                "ci_upper_pips": pooled_mean + 1.96 * pooled_se,
                "pair_count": rt["pair_count"],
                "pairs_positive": rt["pairs_positive"],
                "pairs_negative": rt["pair_count"] - rt["pairs_positive"],
            }

        agg[target_name] = agg_regimes

    return agg


if __name__ == "__main__":
    t0 = time.time()
    results = run_elapsed_time_analysis()
    elapsed = time.time() - t0
    print(f"\nTotal elapsed-time analysis: {elapsed:.0f}s")

    out_path = RESULTS_DIR / "elapsed_time_comparison.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Saved to {out_path}")

    # Print summary
    print("\n" + "=" * 80)
    print("  EQUAL-ELAPSED-TIME COMPARISON SUMMARY")
    print("=" * 80)
    for tf in ["1min", "15min", "1h", "4h"]:
        print(f"\n--- {tf} ---")
        for target_name, elapsed_min in ELAPSED_TARGETS.items():
            agg = results[tf]["aggregate"].get(target_name, {})
            if not agg:
                print(f"  {target_name}: no data")
                continue
            print(f"  {target_name} ({elapsed_min}min):")
            for regime in sorted(agg.keys()):
                r = agg[regime]
                print(f"    {regime:30s}  n={r['n']:>10,}  mean={r['pooled_mean_pips']:>+8.3f}pips  "
                      f"SE={r['pooled_se_pips']:>6.3f}  CI=[{r['ci_lower_pips']:>+8.3f},{r['ci_upper_pips']:>+8.3f}]  "
                      f"pairs={r['pair_count']} +{r['pairs_positive']}/-{r['pairs_negative']}")
