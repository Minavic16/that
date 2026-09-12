"""Load all timeframe research outputs and produce a rigorous comparison.

This script loads the cost sensitivity and regime analysis JSONs for all
four timeframes and produces detailed statistical comparisons.

Do NOT modify production signal logic. This is research/analysis only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


RESULTS_DIR = Path("research/output/phase3")

TIMEFRAMES = ["1min", "15min", "1h", "4h"]

# Typical retail FX cost assumptions (pips)
COST_ASSUMPTIONS = [0.5, 1.0, 1.5, 2.0, 3.0]


def load_json(filename: str) -> dict:
    path = RESULTS_DIR / filename
    with open(path) as f:
        return json.load(f)


def cost_adjusted_expectancy(mean_pips: float, cost_pips: float) -> float:
    return mean_pips - cost_pips


def analysis_summary() -> dict:
    """Produce a comprehensive multi-timeframe comparison."""
    summary = {}

    # Load cost sensitivity for all timeframes
    cost_data = {}
    for tf in TIMEFRAMES:
        cost_data[tf] = load_json(f"cost_sensitivity_{tf}.json")

    # Load regime analysis for all timeframes
    regime_data = {}
    for tf in TIMEFRAMES:
        regime_data[tf] = load_json(f"regime_analysis_{tf}.json")

    # Load elapsed-time comparison
    elapsed_data = load_json("elapsed_time_comparison.json")

    # ── Per-regime comparison ─────────────────────────────────────────────
    all_regimes = set()
    for tf in TIMEFRAMES:
        all_regimes.update(cost_data[tf]["aggregate"].keys())

    regime_comparison = {}
    for regime in sorted(all_regimes):
        rc = {}
        for tf in TIMEFRAMES:
            agg = cost_data[tf]["aggregate"].get(regime, {})
            if not agg:
                rc[tf] = {"status": "missing"}
                continue

            n = agg["n_extreme"]
            mean = agg["mean_return_pips"]
            se = agg["hac_se_pips"]
            be = agg["breakeven_cost_pips"]

            # CI
            ci_lower = mean - 1.96 * se
            ci_upper = mean + 1.96 * se

            # Cost-adjusted scenarios
            scenarios = {}
            for s in agg.get("scenarios", []):
                cost = s["cost_pips"]
                scenarios[f"spread{cost:.1f}"] = {
                    "net_mean": s["expectancy_pips"],
                    "hit_rate": s["hit_rate"],
                    "z_stat": s["z_stat"],
                    "significant": s["significant_5pct"] == "True",
                }

            # Find break-even cost: max cost where net_mean > 0
            breakeven = None
            for s in agg.get("scenarios", []):
                if s["expectancy_pips"] > 0:
                    breakeven = s["cost_pips"]
            # Check if even lowest cost is unprofitable
            if agg.get("scenarios") and agg["scenarios"][0]["expectancy_pips"] <= 0:
                breakeven = 0.0

            rc[tf] = {
                "n": n,
                "mean_pips": mean,
                "hac_se_pips": se,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
                "breakeven_cost_pips": be,
                "max_profitable_cost": breakeven,
                "scenarios": scenarios,
            }

        regime_comparison[regime] = rc

    # ── Equal-elapsed-time comparison ─────────────────────────────────────
    elapsed_comparison = {}
    for target in ["1h", "4h", "24h", "48h"]:
        tc = {}
        for tf in TIMEFRAMES:
            tf_agg = elapsed_data.get(tf, {}).get("aggregate", {}).get(target, {})
            tc[tf] = {}
            for regime, stats in tf_agg.items():
                tc[tf][regime] = {
                    "n": stats["n"],
                    "mean_pips": stats["pooled_mean_pips"],
                    "se_pips": stats["pooled_se_pips"],
                    "ci_lower": stats["ci_lower_pips"],
                    "ci_upper": stats["ci_upper_pips"],
                    "pairs": stats["pair_count"],
                    "pairs_positive": stats["pairs_positive"],
                    "pairs_negative": stats["pairs_negative"],
                }
        elapsed_comparison[target] = tc

    # ── Dataset size comparison ───────────────────────────────────────────
    dataset_size = {}
    for tf in TIMEFRAMES:
        total_bars = 0
        pair_bars = []
        for pair, pdata in regime_data[tf]["pair_results"].items():
            n = pdata["n_bars"]
            total_bars += n
            pair_bars.append(n)
        dataset_size[tf] = {
            "total_bars": total_bars,
            "bars_per_pair_mean": np.mean(pair_bars),
            "bars_per_pair_median": np.median(pair_bars),
            "bars_per_pair_min": min(pair_bars),
            "bars_per_pair_max": max(pair_bars),
        }

    # ── Cross-pair consistency for key regimes ────────────────────────────
    key_regimes = ["strong_trend×mid_vol", "strong_trend×high_vol",
                   "near_ema×low_vol", "weak_trend×mid_vol"]
    cross_pair = {}
    for regime in key_regimes:
        cp = {}
        for tf in TIMEFRAMES:
            pair_means = []
            for pair, pdata in regime_data[tf]["pair_results"].items():
                h60 = pdata.get("regime_analysis", {}).get("h60", {})
                r = h60.get(regime, {})
                if r and r.get("n", 0) > 0:
                    pair_means.append({
                        "pair": pair,
                        "mean_pips": r.get("mean_return_all", 0),
                        "n": r.get("n", 0),
                    })
            if pair_means:
                means = [p["mean_pips"] for p in pair_means]
                cp[tf] = {
                    "n_pairs": len(pair_means),
                    "mean_of_means": float(np.mean(means)),
                    "std_of_means": float(np.std(means, ddof=1)) if len(means) > 1 else 0,
                    "min_pair": min(pair_means, key=lambda x: x["mean_pips"]),
                    "max_pair": max(pair_means, key=lambda x: x["mean_pips"]),
                    "n_positive": sum(1 for m in means if m > 0),
                    "n_negative": sum(1 for m in means if m < 0),
                }
        cross_pair[regime] = cp

    # ── Regime distribution across timeframes ─────────────────────────────
    regime_dist = {}
    for tf in TIMEFRAMES:
        rd = regime_data[tf].get("aggregate_regime_distribution", {})
        total = sum(v["count"] for v in rd.values()) if rd else 1
        regime_dist[tf] = {
            k: {"count": v["count"], "pct": v["pct"]}
            for k, v in sorted(rd.items(), key=lambda x: -x[1]["pct"])
        }

    return {
        "dataset_size": dataset_size,
        "regime_comparison": regime_comparison,
        "elapsed_time_comparison": elapsed_comparison,
        "cross_pair_consistency": cross_pair,
        "regime_distribution": regime_dist,
    }


def print_comparison(summary: dict) -> None:
    """Print a formatted comparison table."""
    print("=" * 120)
    print("  DATASET SIZE COMPARISON")
    print("=" * 120)
    print(f"  {'Timeframe':<10s} {'Total Bars':>14s} {'Mean/Pair':>12s} {'Median/Pair':>12s} {'Min':>10s} {'Max':>10s}")
    for tf in TIMEFRAMES:
        ds = summary["dataset_size"][tf]
        print(f"  {tf:<10s} {ds['total_bars']:>14,} {ds['bars_per_pair_mean']:>12,.0f} "
              f"{ds['bars_per_pair_median']:>12,.0f} {ds['bars_per_pair_min']:>10,} {ds['bars_per_pair_max']:>10,}")

    print("\n" + "=" * 120)
    print("  REGIME-LEVEL COMPARISON (60-bar forward return, in pips)")
    print("=" * 120)
    header = f"  {'Regime':<30s}"
    for tf in TIMEFRAMES:
        header += f" {'n':>10s} {'Mean':>8s} {'SE':>7s} {'CI Low':>8s} {'CI Hi':>8s} {'BE$':>5s}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for regime, tf_data in summary["regime_comparison"].items():
        row = f"  {regime:<30s}"
        for tf in TIMEFRAMES:
            d = tf_data.get(tf, {})
            if d.get("status") == "missing":
                row += f" {'---':>10s} {'---':>8s} {'---':>7s} {'---':>8s} {'---':>8s} {'---':>5s}"
            else:
                be_str = f"{d['max_profitable_cost']:.1f}" if d['max_profitable_cost'] is not None else "0.0"
                row += (f" {d['n']:>10,} {d['mean_pips']:>+8.3f} {d['hac_se_pips']:>7.3f} "
                        f"{d['ci_lower']:>+8.3f} {d['ci_upper']:>+8.3f} {be_str:>5s}")
        print(row)

    print("\n" + "=" * 120)
    print("  EQUAL-ELAPSED-TIME: ~1h FORWARD RETURN (in pips)")
    print("=" * 120)
    target = "1h"
    print(f"  {'Regime':<30s}", end="")
    for tf in TIMEFRAMES:
        print(f" {tf:>12s} {'SE':>8s} {'CI Low':>9s} {'CI Hi':>9s} {'Pairs+':>7s}", end="")
    print()
    print("  " + "-" * 100)

    # Get all regimes from elapsed data
    all_elapsed_regimes = set()
    for tf in TIMEFRAMES:
        all_elapsed_regimes.update(summary["elapsed_time_comparison"].get(target, {}).get(tf, {}).keys())

    for regime in sorted(all_elapsed_regimes):
        row = f"  {regime:<30s}"
        for tf in TIMEFRAMES:
            d = summary["elapsed_time_comparison"].get(target, {}).get(tf, {}).get(regime, {})
            if d:
                row += (f" {d['mean_pips']:>+12.3f} {d['se_pips']:>8.3f} "
                        f"{d['ci_lower']:>+9.3f} {d['ci_upper']:>+9.3f} {d['pairs_positive']:>4d}/{d['pairs']:<2d}")
            else:
                row += f" {'---':>12s} {'---':>8s} {'---':>9s} {'---':>9s} {'---':>7s}"
        print(row)

    print("\n" + "=" * 120)
    print("  CROSS-PAIR CONSISTENCY (mean of per-pair means, in pips)")
    print("=" * 120)
    for regime, tf_data in summary["cross_pair_consistency"].items():
        print(f"\n  {regime}:")
        for tf in TIMEFRAMES:
            d = tf_data.get(tf, {})
            if d:
                print(f"    {tf:>5s}: mean={d['mean_of_means']:>+8.4f}  std={d['std_of_means']:>7.4f}  "
                      f"min={d['min_pair']['pair']}({d['min_pair']['mean_pips']:>+7.3f})  "
                      f"max={d['max_pair']['pair']}({d['max_pair']['mean_pips']:>+7.3f})  "
                      f"+{d['n_positive']}/-{d['n_negative']}")


if __name__ == "__main__":
    summary = analysis_summary()

    out_path = RESULTS_DIR / "timeframe_comparison.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Saved to {out_path}")

    print_comparison(summary)
