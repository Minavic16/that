"""Temporal Stability Analysis — Phase 3c.

Phase A: Per-period metrics across all 4 timeframes, per regime.
Phase B: Cross-pair temporal stability for promising regimes.
Phase E: Multiple comparison control.
Phase F: Outlier removal stability checks.

All computations strictly causal. No lookahead.
"""
from __future__ import annotations

import gc
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


from nestquant.research.shared.zscore.zscore import _zscore_causal_core
from nestquant.research.shared.zscore.regime import classify_regime_chunked

RESULTS_DIR = Path("research/output/phase3")
PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF",
    "EUR/GBP", "EUR/CHF", "EUR/CAD", "EUR/AUD", "GBP/JPY",
    "GBP/CAD", "GBP/AUD", "AUD/JPY", "AUD/CAD", "AUD/CHF",
    "NZD/USD", "NZD/JPY", "NZD/CHF", "CAD/JPY", "CAD/CHF",
]
TIMEFRAMES = ["15min", "1h", "4h"]  # 1min permanently excluded
LOOKBACK = 20
HORIZONS = [5, 15, 30, 60, 120, 240]
PRIMARY_HORIZON = 60
COST_LEVELS = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
OUTLIER_COSTS = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
YEAR_SPLITS = {
    "2016-2018": (2016, 2018),
    "2019-2021": (2019, 2021),
    "2022-2024": (2022, 2024),
    "2025-2026": (2025, 2026),
}
N_BOOTSTRAP = 200


def load_pair(pair: str, timeframe: str) -> pd.DataFrame | None:
    """Load pair data with subdirectory-first resolution."""
    pair_file = pair.replace("/", "_")
    data_dir = Path("/root/data")
    tf_dir = data_dir / timeframe
    flat_path = data_dir / f"{pair_file}.pkl"
    tf_path = tf_dir / f"{pair_file}.pkl"

    try:
        if tf_path.exists():
            data = pd.read_pickle(tf_path)
        elif flat_path.exists():
            data = pd.read_pickle(flat_path)
        else:
            return None
    except Exception:
        return None

    if isinstance(data, dict):
        data = data.get(pair)
        if data is None:
            return None
    return data


def pip_value(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001


def compute_pair_data(pair: str, timeframe: str) -> dict | None:
    """Load pair, compute Z-scores, regimes, and forward returns."""
    df = load_pair(pair, timeframe)
    if df is None or len(df) < LOOKBACK + max(HORIZONS) + 10:
        return None

    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    ts = df.index
    n = len(close)
    del df

    z_scores, _, _ = _zscore_causal_core(close, LOOKBACK)

    try:
        regimes = classify_regime_chunked(
            close, high, low, ts, pair,
            chunk_size=1000, ema_span=200, atr_period=14,
        )
        regime_labels = np.array([f"{r.trend}×{r.volatility}" for r in regimes])
        del regimes
    except Exception:
        regime_labels = np.array(["unknown"] * n)

    years = np.array([t.year for t in ts])
    months = np.array([t.month for t in ts])

    forward_returns = {}
    for h in HORIZONS:
        fr = np.full(n, np.nan)
        if n > h:
            fr[:n - h] = (close[h:] - close[:n - h]) / close[:n - h]
        forward_returns[h] = fr
    del close, high, low

    valid_mask = np.isfinite(z_scores) & (regime_labels != "unknown")
    del z_scores

    return {
        "pair": pair,
        "timeframe": timeframe,
        "n_bars": n,
        "regime_labels": regime_labels,
        "years": years,
        "months": months,
        "forward_returns": forward_returns,
        "valid_mask": valid_mask,
        "timestamps": ts,
    }


def compute_metrics(returns_pips: np.ndarray, cost_pips: float = 0.0) -> dict:
    """Compute comprehensive metrics from per-trade returns (pips)."""
    n = len(returns_pips)
    if n == 0:
        return {"n": 0}

    net = returns_pips - cost_pips
    net_valid = net[np.isfinite(net)]
    n_valid = len(net_valid)
    if n_valid == 0:
        return {"n": 0}

    mean_gross = float(np.mean(returns_pips))
    mean_net = float(np.mean(net_valid))
    std_net = float(np.std(net_valid, ddof=1)) if n_valid > 1 else 0.0
    se_net = std_net / np.sqrt(n_valid) if n_valid > 0 else 0.0

    median = float(np.median(net_valid))

    wins = net_valid[net_valid > 0]
    losses = net_valid[net_valid < 0]
    win_rate = len(wins) / n_valid * 100 if n_valid > 0 else 0.0
    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
    gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = abs(float(np.sum(losses))) if len(losses) > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Drawdown
    cum = np.cumsum(net_valid)
    running_max = np.maximum.accumulate(cum)
    drawdowns = cum - running_max
    max_dd = float(np.min(drawdowns))

    # Sharpe/Sortino (annualize based on primary horizon bars per day)
    sharpe = (mean_net / std_net * np.sqrt(252)) if std_net > 0 and n_valid > 10 else None
    downside = net_valid[net_valid < 0]
    downside_dev = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sortino = (mean_net / downside_dev * np.sqrt(252)) if downside_dev > 0 and n_valid > 10 else None

    ci_lower = mean_net - 1.96 * se_net
    ci_upper = mean_net + 1.96 * se_net

    return {
        "n": n_valid,
        "mean_gross_pips": mean_gross,
        "mean_net_pips": mean_net,
        "std_pips": std_net,
        "se_pips": se_net,
        "ci_lower_pips": ci_lower,
        "ci_upper_pips": ci_upper,
        "median_pips": median,
        "win_rate": win_rate,
        "avg_win_pips": avg_win,
        "avg_loss_pips": avg_loss,
        "gross_profit_pips": gross_profit,
        "gross_loss_pips": gross_loss,
        "profit_factor": profit_factor,
        "max_drawdown_pips": max_dd,
        "sharpe": sharpe,
        "sortino": sortino,
    }


def bootstrap_ci(data: np.ndarray, n_boot: int = N_BOOTSTRAP, alpha: float = 0.05) -> dict:
    """Bootstrap confidence interval for the mean."""
    n = len(data)
    if n < 10:
        return {"mean": float(np.mean(data)) if n > 0 else 0.0,
                "ci_lower": None, "ci_upper": None}

    rng = np.random.default_rng(42)
    boot_means = np.array([
        float(np.mean(rng.choice(data, size=n, replace=True)))
        for _ in range(n_boot)
    ])
    return {
        "mean": float(np.mean(data)),
        "ci_lower": float(np.percentile(boot_means, alpha * 100)),
        "ci_upper": float(np.percentile(boot_means, (1 - alpha) * 100)),
    }


def outlier_sensitivity(returns_pips: np.ndarray) -> dict:
    """Recalculate metrics after removing extreme observations."""
    n = len(returns_pips)
    if n < 10:
        return {}

    results = {}
    mf = compute_metrics(returns_pips)
    results["full"] = {"n": mf["n"], "mean_pips": mf["mean_net_pips"],
                        "profit_factor": mf["profit_factor"]}

    idx_largest = np.argmax(returns_pips)
    trimmed_1 = np.delete(returns_pips, idx_largest)
    m = compute_metrics(trimmed_1)
    results["remove_largest_1"] = {"n": m["n"], "mean_pips": m["mean_net_pips"],
                                    "profit_factor": m["profit_factor"]}

    if n > 15:
        top5_idx = np.argsort(returns_pips)[::-1][:5]
        trim_mask = np.ones(n, dtype=bool)
        trim_mask[top5_idx] = False
        m5 = compute_metrics(returns_pips[trim_mask])
        results["remove_largest_5"] = {"n": m5["n"], "mean_pips": m5["mean_net_pips"],
                                        "profit_factor": m5["profit_factor"]}

    if n > 100:
        p99 = np.percentile(returns_pips, 99)
        trimmed_1pct = returns_pips[returns_pips <= p99]
        m1p = compute_metrics(trimmed_1pct)
        results["remove_largest_1pct"] = {"n": m1p["n"], "mean_pips": m1p["mean_net_pips"],
                                           "profit_factor": m1p["profit_factor"]}

    return results


def run_temporal_stability(timeframes: list[str] | None = None) -> tuple[dict, dict]:
    """Run Phase A: per-period metrics across timeframes.

    Args:
        timeframes: Subset of TIMEFRAMES to process. None = all.
    """
    tfs = timeframes or TIMEFRAMES
    print(f"\n{'='*60}")
    print(f"  TEMPORAL STABILITY ANALYSIS: {', '.join(tfs)}")
    print(f"{'='*60}")

    # Results structure: results[timeframe][regime][period] = metrics
    results: dict[str, dict[str, dict[str, dict]]] = {
        tf: {} for tf in TIMEFRAMES
    }
    # Cross-pair data: cross_pair[timeframe][regime][period][pair] = metrics
    cross_pair: dict[str, dict[str, dict[str, dict]]] = {
        tf: {} for tf in TIMEFRAMES
    }

    for tf in tfs:
        print(f"\n  --- {tf} ---")
        tf_t0 = time.time()
        pair_count = 0

        for i, pair in enumerate(PAIRS):
            t0 = time.time()
            pd_data = compute_pair_data(pair, tf)
            elapsed = time.time() - t0
            if pd_data is None:
                print(f"    [{i+1}/{len(PAIRS)}] {pair}: SKIP ({elapsed:.1f}s)")
                continue
            print(f"    [{i+1}/{len(PAIRS)}] {pair}: {pd_data['n_bars']:,} bars ({elapsed:.1f}s)")

            valid_mask = pd_data["valid_mask"]
            regime_labels = pd_data["regime_labels"]
            forward_returns = pd_data["forward_returns"]
            years = pd_data["years"]
            pip = pip_value(pair)

            pair_regimes = sorted(set(regime_labels[valid_mask]))

            for regime in pair_regimes:
                if regime not in results[tf]:
                    results[tf][regime] = {}
                    cross_pair[tf][regime] = {}
                if regime not in cross_pair[tf]:
                    cross_pair[tf][regime] = {}

                mask = valid_mask & (regime_labels == regime)
                n_total = int(mask.sum())
                if n_total < 30:
                    continue

                for period_name, (y_start, y_end) in YEAR_SPLITS.items():
                    ymask = (years >= y_start) & (years <= y_end) & mask
                    n_period = int(ymask.sum())
                    if n_period < 30:
                        continue

                    fr = forward_returns[PRIMARY_HORIZON][ymask]
                    valid = np.isfinite(fr)
                    fr_pips = fr[valid] / pip
                    if len(fr_pips) < 10:
                        continue

                    # Metrics at each cost level
                    cost_metrics = {}
                    for cost in COST_LEVELS:
                        m = compute_metrics(fr_pips, cost_pips=cost)
                        cost_metrics[str(cost)] = {
                            "mean_pips": m["mean_net_pips"],
                            "median_pips": m["median_pips"],
                            "win_rate": m["win_rate"],
                            "avg_win_pips": m["avg_win_pips"],
                            "avg_loss_pips": m["avg_loss_pips"],
                            "profit_factor": m["profit_factor"],
                            "sharpe": m["sharpe"],
                            "sortino": m["sortino"],
                            "max_drawdown_pips": m["max_drawdown_pips"],
                            "ci_lower_pips": m["ci_lower_pips"],
                            "ci_upper_pips": m["ci_upper_pips"],
                            "n": m["n"],
                        }

                    boot = bootstrap_ci(fr_pips)
                    outlier = outlier_sensitivity(fr_pips)

                    period_key = f"{y_start}-{y_end}"
                    if period_key not in results[tf][regime]:
                        results[tf][regime][period_key] = {}
                    results[tf][regime][period_key] = {
                        "cost_metrics": cost_metrics,
                        "bootstrap": boot,
                        "outlier_sensitivity": outlier,
                    }

                    # Cross-pair data
                    if period_key not in cross_pair[tf][regime]:
                        cross_pair[tf][regime][period_key] = {}
                    cross_pair[tf][regime][period_key][pair] = {
                        "n": len(fr_pips),
                        "mean_pips": cost_metrics["0.0"]["mean_pips"],
                        "median_pips": cost_metrics["0.0"]["median_pips"],
                        "win_rate": cost_metrics["0.0"]["win_rate"],
                        "profit_factor": cost_metrics["0.0"]["profit_factor"],
                    }

            pair_count += 1
            del pd_data, regime_labels, valid_mask, forward_returns, years
            gc.collect()

        print(f"  {tf}: {pair_count} pairs in {time.time()-tf_t0:.0f}s")

    return results, cross_pair


def compute_stability_metrics(results: dict) -> dict:
    """Phase A report: sign consistency, positive-EV %, cost survival."""
    stability = {}
    for tf in TIMEFRAMES:
        stability[tf] = {}
        for regime, periods in results[tf].items():
            period_keys = sorted(periods.keys())
            if len(period_keys) < 2:
                continue

            # Per-cost analysis
            cost_stability = {}
            for cost in COST_LEVELS:
                means = []
                positive_count = 0
                total_count = 0
                for pk in period_keys:
                    cm = periods[pk].get("cost_metrics", {}).get(str(cost), {})
                    if cm.get("n", 0) >= 10:
                        means.append(cm["mean_pips"])
                        total_count += 1
                        if cm["mean_pips"] > 0:
                            positive_count += 1

                if total_count >= 2:
                    cost_stability[str(cost)] = {
                        "n_periods": total_count,
                        "signs": [1 if m > 0 else -1 for m in means],
                        "sign_consistent": all(m > 0 for m in means) or all(m < 0 for m in means),
                        "n_positive_periods": positive_count,
                        "pct_positive_periods": positive_count / total_count * 100,
                        "mean_of_means": float(np.mean(means)),
                        "std_of_means": float(np.std(means, ddof=1)) if len(means) > 1 else 0.0,
                        "min_mean": float(np.min(means)),
                        "max_mean": float(np.max(means)),
                    }

            # Bootstrap stability
            boot_means = []
            boot_ci_contains_zero = []
            for pk in period_keys:
                b = periods[pk].get("bootstrap", {})
                if b.get("ci_lower") is not None:
                    boot_means.append(b["mean"])
                    boot_ci_contains_zero.append(b["ci_lower"] <= 0 <= b["ci_upper"])

            # Outlier sensitivity
            outlier_full_means = []
            outlier_trimmed_means = []
            for pk in period_keys:
                os = periods[pk].get("outlier_sensitivity", {})
                if os.get("full", {}).get("n", 0) >= 10:
                    outlier_full_means.append(os["full"]["mean_pips"])
                if os.get("remove_largest_5", {}).get("n", 0) >= 10:
                    outlier_trimmed_means.append(os["remove_largest_5"]["mean_pips"])

            stability[tf][regime] = {
                "cost_stability": cost_stability,
                "bootstrap_means": boot_means,
                "bootstrap_ci_contains_zero": boot_ci_contains_zero,
                "bootstrap_sign_consistent": (all(m > 0 for m in boot_means) or
                                              all(m < 0 for m in boot_means)) if boot_means else None,
                "outlier_full_means": outlier_full_means,
                "outlier_trimmed_means": outlier_trimmed_means,
            }

    return stability


def compute_cross_pair_stability(cross_pair: dict) -> dict:
    """Phase B: cross-pair temporal stability."""
    cp_stability = {}
    for tf in TIMEFRAMES:
        cp_stability[tf] = {}
        for regime, periods in cross_pair[tf].items():
            period_keys = sorted(periods.keys())
            if len(period_keys) < 2:
                continue

            period_analysis = {}
            for pk in period_keys:
                pairs = periods[pk]
                if len(pairs) < 5:
                    continue

                pair_means = [v["mean_pips"] for v in pairs.values()]
                pair_n = [v["n"] for v in pairs.values()]
                total_n = sum(pair_n)
                weighted_mean = sum(m * n for m, n in zip(pair_means, pair_n)) / total_n if total_n > 0 else 0.0

                n_positive = sum(1 for m in pair_means if m > 0)
                n_negative = len(pair_means) - n_positive

                period_analysis[pk] = {
                    "n_pairs": len(pairs),
                    "total_n": total_n,
                    "weighted_mean_pips": weighted_mean,
                    "median_pair_pips": float(np.median(pair_means)),
                    "mean_pair_pips": float(np.mean(pair_means)),
                    "std_pair_pips": float(np.std(pair_means, ddof=1)) if len(pair_means) > 1 else 0.0,
                    "n_pairs_positive": n_positive,
                    "n_pairs_negative": n_negative,
                    "pct_pairs_positive": n_positive / len(pair_means) * 100,
                    "dominant_pair": max(pairs.items(), key=lambda x: abs(x[1]["mean_pips"]))[0],
                    "dominant_pair_mean": max(pairs.values(), key=lambda x: abs(x["mean_pips"]))["mean_pips"],
                }

            # Cross-period stability
            if len(period_analysis) >= 2:
                period_means = [v["weighted_mean_pips"] for v in period_analysis.values()]
                period_pct_pos = [v["pct_pairs_positive"] for v in period_analysis.values()]

                cp_stability[tf][regime] = {
                    "periods": period_analysis,
                    "sign_consistent": all(m > 0 for m in period_means) or all(m < 0 for m in period_means),
                    "pct_positive_all_periods": all(p >= 50 for p in period_pct_pos),
                    "mean_of_period_means": float(np.mean(period_means)),
                    "std_of_period_means": float(np.std(period_means, ddof=1)) if len(period_means) > 1 else 0.0,
                }
            else:
                cp_stability[tf][regime] = {"periods": period_analysis}

    return cp_stability


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR correction."""
    n = len(pvalues)
    if n == 0:
        return []
    indexed = sorted(enumerate(pvalues), key=lambda x: x[1], reverse=True)
    adjusted = [0.0] * n
    for rank, (orig_idx, p) in enumerate(indexed, 1):
        adjusted[orig_idx] = min(p * n / rank, 1.0)
    # Enforce monotonicity
    for i in range(1, n):
        idx_sorted = sorted(range(n), key=lambda j: pvalues[j], reverse=True)
        if adjusted[idx_sorted[i]] > adjusted[idx_sorted[i - 1]]:
            adjusted[idx_sorted[i]] = adjusted[idx_sorted[i - 1]]
    return adjusted


def compute_multiple_comparison_control(results: dict, stability: dict) -> dict:
    """Phase E: multiple comparison control."""
    # Collect all raw p-values from bootstrap CIs
    tests = []
    for tf in TIMEFRAMES:
        for regime, periods in results[tf].items():
            for pk, pdata in periods.items():
                b = pdata.get("bootstrap", {})
                if b.get("ci_lower") is not None and b.get("ci_upper") is not None:
                    # Two-sided test: is the mean significantly different from 0?
                    mean = b["mean"]
                    # Approximate p-value from CI
                    ci_width = (b["ci_upper"] - b["ci_lower"]) / 2 / 1.96
                    if ci_width > 0:
                        z = abs(mean) / ci_width
                        p = 2 * (1 - sp_stats.norm.cdf(z))
                    else:
                        p = 1.0 if mean == 0 else 0.001
                    tests.append({
                        "timeframe": tf,
                        "regime": regime,
                        "period": pk,
                        "mean": mean,
                        "ci_lower": b["ci_lower"],
                        "ci_upper": b["ci_upper"],
                        "raw_pvalue": p,
                    })

    raw_pvalues = [t["raw_pvalue"] for t in tests]
    adjusted_pvalues = benjamini_hochberg(raw_pvalues)

    for i, test in enumerate(tests):
        test["adjusted_pvalue"] = adjusted_pvalues[i]
        test["significant_raw"] = test["raw_pvalue"] < 0.05
        test["significant_fdr"] = test["adjusted_pvalue"] < 0.05

    n_raw_sig = sum(1 for t in tests if t["significant_raw"])
    n_fdr_sig = sum(1 for t in tests if t["significant_fdr"])

    return {
        "n_tests": len(tests),
        "n_significant_raw": n_raw_sig,
        "n_significant_fdr": n_fdr_sig,
        "tests": tests,
    }


def run_analysis(timeframes: list[str] | None = None) -> dict:
    """Run temporal stability analysis.

    Args:
        timeframes: Subset of timeframes. None = all.
    """
    results, cross_pair = run_temporal_stability(timeframes)

    print("\n  Computing stability metrics...")
    stability = compute_stability_metrics(results)
    cp_stability = compute_cross_pair_stability(cross_pair)
    mtc = compute_multiple_comparison_control(results, stability)

    return {
        "results": results,
        "cross_pair": cross_pair,
        "stability": stability,
        "cross_pair_stability": cp_stability,
        "multiple_comparison": mtc,
    }


def save_results(full_results: dict, append_to: dict | None = None) -> dict:
    """Save results to JSON. Optionally merge into existing results."""
    if append_to:
        for key in ["results", "cross_pair", "stability", "cross_pair_stability"]:
            if key in full_results and key in append_to:
                for tf_key, tf_val in full_results[key].items():
                    if tf_key in append_to[key]:
                        append_to[key][tf_key].update(tf_val)
                    else:
                        append_to[key][tf_key] = tf_val
        if "multiple_comparison" in full_results and "multiple_comparison" in append_to:
            append_to["multiple_comparison"]["tests"].extend(
                full_results["multiple_comparison"].get("tests", [])
            )
            mt = append_to["multiple_comparison"]
            mt["n_tests"] = len(mt["tests"])
            mt["n_significant_raw"] = sum(1 for t in mt["tests"] if t.get("significant_raw"))
            mt["n_significant_fdr"] = sum(1 for t in mt["tests"] if t.get("significant_fdr"))
        full_results = append_to

    out = RESULTS_DIR / "temporal_stability.json"
    with open(out, "w") as f:
        json.dump(full_results, f, indent=2, default=str)
    print(f"  Saved to {out}")
    return full_results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Temporal Stability Analysis")
    parser.add_argument("--timeframes", nargs="+",
                        choices=["1min", "15min", "1h", "4h"],
                        help="Timeframes to process (default: all)")
    args = parser.parse_args()

    t0 = time.time()
    full_results = run_analysis(args.timeframes)
    elapsed = time.time() - t0
    save_results(full_results)
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed/60:.1f}min)")
