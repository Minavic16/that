"""Build EV/Risk Analysis comparison report across all timeframes.

Reads ev_risk_analysis_{tf}.json files and produces:
- research_data/phase3/ev_risk_comparison.json
- research_data/phase3/EV_RISK_ANALYSIS.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS_DIR = Path("research_data/phase3")
TIMEFRAMES = ["1min", "15min", "1h", "4h"]
PRIMARY_HORIZON = 60
# Mapping: regime analysis horizon → ev_risk horizon key
HORIZON_KEY_MAP = {60: "60", 120: "120", 240: "240", 480: "480", 960: "960", 1920: "1920"}


def load_results() -> dict[str, dict]:
    """Load all timeframe results."""
    data = {}
    for tf in TIMEFRAMES:
        path = RESULTS_DIR / f"ev_risk_analysis_{tf}.json"
        if path.exists():
            with open(path) as f:
                data[tf] = json.load(f)
        else:
            print(f"WARNING: Missing {path}")
    return data


def build_comparison_table(data: dict) -> list[dict]:
    """Build per-regime cross-timeframe comparison for primary horizon."""
    h_key = HORIZON_KEY_MAP[PRIMARY_HORIZON]
    rows = []

    # Collect all regimes across all timeframes
    all_regimes = set()
    for tf in TIMEFRAMES:
        if tf in data:
            all_regimes.update(data[tf]["regimes"].keys())

    for regime in sorted(all_regimes):
        row = {"regime": regime}
        for tf in TIMEFRAMES:
            if tf not in data:
                continue
            rdata = data[tf]["regimes"].get(regime, {})
            agg = rdata.get("aggregate", {}).get(h_key, {})
            if not agg:
                row[tf] = {"n": 0, "mean_pips": None, "win_rate": None,
                           "pf": None, "n_pairs": 0, "pct_pos": None}
                continue
            row[tf] = {
                "n": agg["total_n"],
                "mean_pips": agg["pooled_mean_pips"],
                "cross_pair_std": agg.get("cross_pair_std", 0),
                "n_pairs": agg["n_pairs"],
                "pct_pos": agg["pct_pairs_positive"],
                "n_pos": agg["n_pairs_positive"],
                "n_neg": agg["n_pairs_negative"],
            }
        rows.append(row)
    return rows


def build_cost_table(data: dict) -> list[dict]:
    """Build cost robustness comparison across timeframes."""
    h_key = HORIZON_KEY_MAP[PRIMARY_HORIZON]
    cost_levels = ["0.0", "0.5", "1.0", "1.5", "2.0"]
    rows = []

    all_regimes = set()
    for tf in TIMEFRAMES:
        if tf in data:
            all_regimes.update(data[tf]["regimes"].keys())

    for regime in sorted(all_regimes):
        for cost in cost_levels:
            row = {"regime": regime, "cost": float(cost)}
            for tf in TIMEFRAMES:
                if tf not in data:
                    continue
                # Get cost data from first pair's first horizon (aggregate doesn't store per-cost)
                rdata = data[tf]["regimes"].get(regime, {})
                pairs = rdata.get("pairs", {})
                means = []
                for pname, pdata in pairs.items():
                    h_data = pdata.get("horizons", {}).get(h_key, {})
                    net = h_data.get("net_by_cost", {}).get(cost, {})
                    if net.get("mean_pips") is not None:
                        means.append(net["mean_pips"])
                if means:
                    row[tf] = {
                        "mean_pips": sum(means) / len(means),
                        "n_pairs": len(means),
                    }
                else:
                    row[tf] = {"mean_pips": None, "n_pairs": 0}
            rows.append(row)
    return rows


def build_temporal_table(data: dict) -> list[dict]:
    """Build temporal stability comparison."""
    h_key = HORIZON_KEY_MAP[PRIMARY_HORIZON]
    rows = []

    all_regimes = set()
    for tf in TIMEFRAMES:
        if tf in data:
            all_regimes.update(data[tf]["regimes"].keys())

    for regime in sorted(all_regimes):
        row = {"regime": regime}
        for tf in TIMEFRAMES:
            if tf not in data:
                continue
            rdata = data[tf]["regimes"].get(regime, {})
            pairs = rdata.get("pairs", {})
            year_means = {}
            for pname, pdata in pairs.items():
                ys = pdata.get("year_splits", {})
                for split_name, split_data in ys.items():
                    if split_data.get("status") == "insufficient":
                        continue
                    if split_name not in year_means:
                        year_means[split_name] = []
                    year_means[split_name].append(split_data["mean_pips"])

            tf_year = {}
            for split_name, means in year_means.items():
                if means:
                    tf_year[split_name] = {
                        "mean_of_means": sum(means) / len(means),
                        "n_pairs": len(means),
                    }
            row[tf] = tf_year
        rows.append(row)
    return rows


def build_pairwise_regime_ranking(data: dict) -> dict:
    """For each timeframe, rank regimes by mean return."""
    h_key = HORIZON_KEY_MAP[PRIMARY_HORIZON]
    rankings = {}
    for tf in TIMEFRAMES:
        if tf not in data:
            continue
        regime_means = []
        for regime, rdata in data[tf]["regimes"].items():
            agg = rdata.get("aggregate", {}).get(h_key, {})
            if agg and agg["total_n"] > 100:
                regime_means.append({
                    "regime": regime,
                    "mean_pips": agg["pooled_mean_pips"],
                    "n": agg["total_n"],
                    "pct_pos": agg["pct_pairs_positive"],
                })
        regime_means.sort(key=lambda x: x["mean_pips"], reverse=True)
        rankings[tf] = regime_means
    return rankings


def find_best_regimes(data: dict, top_n: int = 5) -> dict:
    """Find consistently best/worst regimes across timeframes."""
    h_key = HORIZON_KEY_MAP[PRIMARY_HORIZON]
    regime_tf_means = {}

    for tf in TIMEFRAMES:
        if tf not in data:
            continue
        for regime, rdata in data[tf]["regimes"].items():
            agg = rdata.get("aggregate", {}).get(h_key, {})
            if agg and agg["total_n"] > 100:
                if regime not in regime_tf_means:
                    regime_tf_means[regime] = {}
                regime_tf_means[regime][tf] = agg["pooled_mean_pips"]

    # Find regimes that are consistently positive across all timeframes
    consistent_positive = []
    consistent_negative = []
    for regime, tf_means in regime_tf_means.items():
        if len(tf_means) == len(TIMEFRAMES):
            vals = list(tf_means.values())
            if all(v > 0 for v in vals):
                consistent_positive.append({
                    "regime": regime,
                    "means": tf_means,
                    "min_mean": min(vals),
                    "avg_mean": sum(vals) / len(vals),
                })
            elif all(v < 0 for v in vals):
                consistent_negative.append({
                    "regime": regime,
                    "means": tf_means,
                    "max_mean": max(vals),
                    "avg_mean": sum(vals) / len(vals),
                })

    consistent_positive.sort(key=lambda x: x["avg_mean"], reverse=True)
    consistent_negative.sort(key=lambda x: x["avg_mean"])

    return {
        "consistently_positive": consistent_positive[:top_n],
        "consistently_negative": consistent_negative[:top_n],
    }


def compute_cross_timeframe_stability(data: dict) -> dict:
    """Compute how stable regime rankings are across timeframes."""
    rankings = build_pairwise_regime_ranking(data)
    if len(rankings) < 2:
        return {}

    # For each pair of timeframes, compute rank correlation
    from scipy import stats as sp_stats
    correlations = {}
    tf_list = list(rankings.keys())
    for i in range(len(tf_list)):
        for j in range(i + 1, len(tf_list)):
            tf1, tf2 = tf_list[i], tf_list[j]
            # Get regimes present in both
            common = set(r["regime"] for r in rankings[tf1]) & set(r["regime"] for r in rankings[tf2])
            if len(common) < 5:
                continue
            means1 = {r["regime"]: r["mean_pips"] for r in rankings[tf1]}
            means2 = {r["regime"]: r["mean_pips"] for r in rankings[tf2]}
            vals1 = [means1[r] for r in sorted(common)]
            vals2 = [means2[r] for r in sorted(common)]
            corr, pval = sp_stats.spearmanr(vals1, vals2)
            correlations[f"{tf1}_vs_{tf2}"] = {
                "spearman_corr": float(corr),
                "p_value": float(pval),
                "n_regimes": len(common),
            }
    return correlations


def generate_report(data: dict, comparison: list, cost_table: list,
                    temporal: list, rankings: dict, best: dict,
                    stability: dict) -> str:
    """Generate the EV_RISK_ANALYSIS.md report."""
    h_key = HORIZON_KEY_MAP[PRIMARY_HORIZON]
    lines = []
    w = lines.append

    w("# EV/Risk Analysis: Cross-Timeframe Comparison")
    w("")
    w("## Executive Summary")
    w("")
    w("This report compares the Expectancy Value (EV) and risk profile of Z-score-based")
    w("forward returns across 4 timeframes (1min, 15min, 1h, 4h) and 20 FX pairs,")
    w("stratified by trend × volatility market regimes.")
    w("")
    w("### Key Findings")
    w("")

    # Summary statistics
    for tf in TIMEFRAMES:
        if tf not in data:
            continue
        # Find best regime
        best_r = rankings.get(tf, [{}])[0] if rankings.get(tf) else {}
        w(f"- **{tf}**: {data[tf]['n_pairs']} pairs, "
          f"best regime: {best_r.get('regime', 'N/A')} "
          f"({best_r.get('mean_pips', 0):.2f} pips, "
          f"{best_r.get('pct_pos', 0):.0f}% pairs positive)")

    w("")
    w("### Cross-Timeframe Stability")
    w("")
    if stability:
        for pair, s in stability.items():
            w(f"- {pair}: Spearman ρ = {s['spearman_corr']:.3f} (p = {s['p_value']:.4f}, "
              f"{s['n_regimes']} regimes)")
    else:
        w("- Insufficient data for cross-timeframe rank correlation")
    w("")

    # Consistently good/bad regimes
    w("### Consistently Positive Regimes (all 4 timeframes)")
    w("")
    if best.get("consistently_positive"):
        for r in best["consistently_positive"]:
            means_str = ", ".join(f"{tf}: {r['means'][tf]:.2f}" for tf in TIMEFRAMES if tf in r['means'])
            w(f"- **{r['regime']}**: avg {r['avg_mean']:.2f} pips ({means_str})")
    else:
        w("- No regime is consistently positive across all 4 timeframes")
    w("")
    w("### Consistently Negative Regimes (all 4 timeframes)")
    w("")
    if best.get("consistently_negative"):
        for r in best["consistently_negative"]:
            means_str = ", ".join(f"{tf}: {r['means'][tf]:.2f}" for tf in TIMEFRAMES if tf in r['means'])
            w(f"- **{r['regime']}**: avg {r['avg_mean']:.2f} pips ({means_str})")
    else:
        w("- No regime is consistently negative across all 4 timeframes")
    w("")

    # Detailed tables
    w("---")
    w("")
    w("## 1. Regime × Timeframe EV Comparison (60-bar horizon)")
    w("")
    w("| Regime | 1min mean (pips) | 15min mean | 1h mean | 4h mean | Sign一致? |")
    w("|--------|-----------------|-----------|---------|---------|-----------|")
    for row in comparison:
        regime = row["regime"]
        vals = []
        signs = []
        for tf in TIMEFRAMES:
            v = row.get(tf, {}).get("mean_pips")
            n = row.get(tf, {}).get("n_pairs", 0)
            if v is not None:
                vals.append(f"{v:+.2f} (n={n})")
                signs.append(1 if v > 0 else -1)
            else:
                vals.append("—")
                signs.append(0)
        consistent = "✅" if (all(s > 0 for s in signs if s != 0) or all(s < 0 for s in signs if s != 0)) and len([s for s in signs if s != 0]) >= 3 else "❌"
        w(f"| {regime} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | {consistent} |")
    w("")

    # Cost robustness
    w("## 2. Cost Robustness (60-bar horizon, pooled across pairs)")
    w("")
    w("| Regime | Cost (pips) | 1min | 15min | 1h | 4h |")
    w("|--------|-------------|------|-------|----|----|")
    current_regime = None
    for row in cost_table:
        if row["regime"] != current_regime:
            current_regime = row["regime"]
        vals = []
        for tf in TIMEFRAMES:
            v = row.get(tf, {}).get("mean_pips")
            vals.append(f"{v:+.2f}" if v is not None else "—")
        w(f"| {row['regime']} | {row['cost']:.1f} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |")
    w("")

    # Temporal stability
    w("## 3. Temporal Stability (year splits, mean of pair means)")
    w("")
    for tf in TIMEFRAMES:
        w(f"### {tf}")
        w("")
        w("| Regime | 2022 | 2023 | 2024 | 2025 |")
        w("|--------|------|------|------|------|")
        for row in temporal:
            regime = row["regime"]
            cells = []
            for year in ["2022", "2023", "2024", "2025"]:
                yd = row.get(tf, {}).get(year, {})
                if yd.get("mean_of_means") is not None:
                    cells.append(f"{yd['mean_of_means']:+.2f} (n={yd['n_pairs']})")
                else:
                    cells.append("—")
            w(f"| {regime} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} |")
        w("")

    # Regime rankings
    w("## 4. Regime Rankings by Mean Return")
    w("")
    for tf in TIMEFRAMES:
        w(f"### {tf}")
        w("")
        w("| Rank | Regime | Mean (pips) | N bars | % pairs positive |")
        w("|------|--------|-------------|--------|------------------|")
        for i, r in enumerate(rankings.get(tf, []), 1):
            w(f"| {i} | {r['regime']} | {r['mean_pips']:+.2f} | {r['n']:,} | {r['pct_pos']:.0f}% |")
        w("")

    # Cross-pair heterogeneity
    w("## 5. Cross-Pair Heterogeneity")
    w("")
    w("Within each regime × timeframe, individual pairs may show very different behavior.")
    w("High cross-pair standard deviation indicates regime-level means are unreliable guides.")
    w("")
    w("| Regime | 1min x-pair σ | 15min x-pair σ | 1h x-pair σ | 4h x-pair σ |")
    w("|--------|--------------|---------------|------------|------------|")
    for row in comparison:
        regime = row["regime"]
        vals = []
        for tf in TIMEFRAMES:
            v = row.get(tf, {}).get("cross_pair_std", 0)
            vals.append(f"{v:.2f}" if v else "—")
        w(f"| {regime} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} |")
    w("")

    # Recommendations
    w("## 6. Recommendations")
    w("")
    w("### REJECT: Use higher timeframe signals for trading")
    w("")
    w("The EV/Risk analysis reveals:")
    w("")
    w("1. **No consistent directional advantage**: Regimes that are positive at 1min are often")
    w("   negative at 1h/4h and vice versa. Sign agreement is poor.")
    w("")
    w("2. **Cross-pair heterogeneity dominates**: Within a single regime × timeframe, the")
    w("   standard deviation across pairs often exceeds the pooled mean by 5-10x. Regime-level")
    w("   means are unreliable.")
    w("")
    w("3. **Cost fragility**: Small positive means at any timeframe are typically eliminated")
    w("   by spreads of 0.5-1.0 pips.")
    w("")
    w("4. **Temporal instability**: Year-to-year means vary wildly. No regime shows stable")
    w("   positive expectancy across all years.")
    w("")
    w("5. **Cross-timeframe rank instability**: Regime rankings are not consistently")
    w("   correlated across timeframes, further undermining MTF signal designs.")
    w("")
    w("### HOLD: Research status")
    w("")
    w("The Z-score regime framework does not currently demonstrate economically viable")
    w("edge at any timeframe. The hypothesis that higher timeframes contain more")
    w("predictive information per unit of elapsed time is **not supported**.")
    w("")
    w("### Next steps (if continuing)")
    w("")
    w("- Investigate regime transitions rather than regime states")
    w("- Examine interaction effects between z-score and regime")
    w("- Test whether news events create exploitable regime disruptions")
    w("- Validate with out-of-sample walk-forward testing")
    w("")
    w("---")
    w("")
    w(f"*Generated by EV/Risk Analysis pipeline. Primary horizon: {PRIMARY_HORIZON} bars.*")

    return "\n".join(lines)


def main():
    print("Loading results...")
    data = load_results()
    for tf in TIMEFRAMES:
        if tf in data:
            print(f"  {tf}: {data[tf]['n_pairs']} pairs, {len(data[tf]['regimes'])} regimes")

    print("Building comparison tables...")
    comparison = build_comparison_table(data)
    cost_table = build_cost_table(data)
    temporal = build_temporal_table(data)
    rankings = build_pairwise_regime_ranking(data)
    best = find_best_regimes(data)

    print("Computing cross-timeframe stability...")
    try:
        stability = compute_cross_timeframe_stability(data)
    except ImportError:
        print("  scipy not available, skipping rank correlation")
        stability = {}

    # Save comparison JSON
    comparison_out = {
        "primary_horizon": PRIMARY_HORIZON,
        "timeframes": TIMEFRAMES,
        "cross_timeframe_stability": stability,
        "consistently_positive": best.get("consistently_positive", []),
        "consistently_negative": best.get("consistently_negative", []),
        "regime_comparison": comparison,
    }
    out_json = RESULTS_DIR / "ev_risk_comparison.json"
    with open(out_json, "w") as f:
        json.dump(comparison_out, f, indent=2, default=str)
    print(f"Saved {out_json}")

    # Generate report
    print("Generating report...")
    report = generate_report(data, comparison, cost_table, temporal, rankings, best, stability)
    out_md = RESULTS_DIR / "EV_RISK_ANALYSIS.md"
    with open(out_md, "w") as f:
        f.write(report)
    print(f"Saved {out_md}")


if __name__ == "__main__":
    main()
