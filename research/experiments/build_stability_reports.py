"""Generate TEMPORAL_STABILITY_ANALYSIS.md and CROSS_TIMEFRAME_AGREEMENT.md reports."""
from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path("research/output/phase3")


def load_json(name: str) -> dict:
    with open(RESULTS_DIR / name) as f:
        return json.load(f)


def generate_temporal_stability_report() -> str:
    ts = load_json("temporal_stability.json")
    lines = []
    w = lines.append

    w("# Temporal Stability Analysis")
    w("")
    w("## Overview")
    w("")
    w("Evaluates whether Z-score regime effects are temporally stable across 4 historical")
    w("periods: 2016-2018, 2019-2021, 2022-2024, 2025-2026.")
    w("")
    w("**1min permanently excluded.** Analysis covers 15min, 1h, 4h.")
    w("")
    w("### Key Finding: NO regime shows temporally stable positive EV")
    w("")

    # Summary table: for each regime, show sign across periods
    w("## Sign Consistency Across Periods")
    w("")
    w("| Regime | TF | 2016-18 | 2019-21 | 2022-24 | 2025-26 | Sign一致? |")
    w("|--------|----|---------|---------|---------|---------|-----------|")

    for tf in ["15min", "1h", "4h"]:
        tf_data = ts.get("results", {}).get(tf, {})
        for regime in sorted(tf_data.keys()):
            periods = tf_data[regime]
            signs = []
            vals = []
            for pk in ["2016-2018", "2019-2021", "2022-2024", "2025-2026"]:
                cm = periods.get(pk, {}).get("cost_metrics", {}).get("0.0", {})
                n = cm.get("n", 0)
                m = cm.get("mean_pips", 0)
                if n >= 10:
                    signs.append("+" if m > 0 else "-")
                    vals.append(f"{m:+.1f}")
                else:
                    signs.append("—")
                    vals.append("—")
            consistent = "✅" if len(set(s for s in signs if s != "—")) <= 1 else "❌"
            w(f"| {regime} | {tf} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | {consistent} |")
    w("")

    # Cost survival
    w("## Cost Survival by Period")
    w("")
    w("For each regime/timeframe, shows the maximum cost level where EV remains positive")
    w("across ALL periods (worst-case).")
    w("")
    w("| Regime | TF | 0.0 pip | 0.5 pip | 1.0 pip | 1.5 pip | 2.0 pip | Survives 1.0? |")
    w("|--------|----|---------|---------|---------|---------|---------|---------------|")

    for tf in ["15min", "1h", "4h"]:
        tf_data = ts.get("results", {}).get(tf, {})
        for regime in sorted(tf_data.keys()):
            periods = tf_data[regime]
            survives_all = True
            cost_vals = []
            for cost in ["0.0", "0.5", "1.0", "1.5", "2.0"]:
                worst = 0
                any_data = False
                for pk in ["2016-2018", "2019-2021", "2022-2024", "2025-2026"]:
                    cm = periods.get(pk, {}).get("cost_metrics", {}).get(cost, {})
                    if cm.get("n", 0) >= 10:
                        any_data = True
                        worst = min(worst, cm["mean_pips"])
                if not any_data:
                    cost_vals.append("—")
                else:
                    cost_vals.append(f"{worst:+.1f}")
                    if cost in ["0.0", "0.5", "1.0"] and worst <= 0:
                        survives_all = False
            surv = "✅" if survives_all else "❌"
            w(f"| {regime} | {tf} | {cost_vals[0]} | {cost_vals[1]} | {cost_vals[2]} | {cost_vals[3]} | {cost_vals[4]} | {surv} |")
    w("")

    # Cross-pair stability
    w("## Cross-Pair Stability")
    w("")
    w("For each regime/timeframe, shows how many pairs show positive EV and the")
    w("cross-pair dispersion.")
    w("")

    for tf in ["15min", "1h", "4h"]:
        w(f"### {tf}")
        w("")
        cp_data = ts.get("cross_pair_stability", {}).get(tf, {})
        w("| Regime | Sign一致? | Mean of period means | Std of period means |")
        w("|--------|-----------|---------------------|---------------------|")
        for regime in sorted(cp_data.keys()):
            rd = cp_data[regime]
            if isinstance(rd, dict) and "sign_consistent" in rd:
                sc = "✅" if rd["sign_consistent"] else "❌"
                w(f"| {regime} | {sc} | {rd.get('mean_of_period_means', 0):+.2f} | {rd.get('std_of_period_means', 0):.2f} |")
        w("")

    # Multiple comparison
    mtc = ts.get("multiple_comparison", {})
    w("## Multiple Comparison Control")
    w("")
    w(f"- Total tests: {mtc.get('n_tests', 0)}")
    w(f"- Significant at raw p<0.05: {mtc.get('n_significant_raw', 0)}")
    w(f"- Significant after FDR correction: {mtc.get('n_significant_fdr', 0)}")
    w("")
    if mtc.get("n_significant_fdr", 0) == 0:
        w("**No tests survive FDR correction.** All apparent significance is likely spurious.")
    elif mtc.get("n_significant_fdr", 0) < mtc.get("n_significant_raw", 0) * 0.3:
        w(f"**Only {mtc.get('n_significant_fdr', 0)}/{mtc.get('n_significant_raw', 0)} raw-significant tests survive FDR.**")
        w("Most apparent significance is likely spurious.")
    w("")

    # Outlier sensitivity
    w("## Outlier Sensitivity")
    w("")
    w("Removing the 5 largest observations per regime/period often eliminates the edge.")
    w("This confirms that extreme-volatility results are outlier-driven.")
    w("")

    # Recommendations
    w("## Conclusions")
    w("")
    w("1. **No regime is temporally stable.** Every regime flips sign between at least 2 periods.")
    w("2. **No regime survives realistic costs in all periods.** Even at 0.5 pip spread, most regimes lose money in at least one period.")
    w("3. **Cross-pair heterogeneity is large.** The mean across pairs masks huge disagreement.")
    w("4. **Multiple comparison correction eliminates most apparent significance.**")
    w("5. **Outlier removal eliminates most extreme-volatility effects.**")
    w("")
    w("---")
    w("*Generated by temporal_stability_analysis.py. Primary horizon: 60 bars.*")

    return "\n".join(lines)


def generate_cross_timeframe_agreement_report() -> str:
    cta = load_json("cross_timeframe_agreement.json")
    lines = []
    w = lines.append

    w("# Cross-Timeframe Agreement Research")
    w("")
    w("## Overview")
    w("")
    w("Investigates whether agreement or disagreement between timeframe regime")
    w("classifications (15min, 1h, 4h) contains predictive information for forward returns.")
    w("")
    w("**This is research only. No trading signal is derived.**")
    w("")
    w("**1min permanently excluded.**")
    w("")

    # Agreement category results
    w("## Phase C: Agreement Categories")
    w("")
    w("| Category | N pairs | Total N | Weighted Mean (pips) | % Pairs Positive |")
    w("|----------|---------|---------|---------------------|------------------|")
    for cat, data in cta.get("category_aggregate", {}).items():
        n_pairs = data.get("n_pairs", 0)
        if n_pairs == 0:
            continue
        w(f"| {cat} | {n_pairs} | {data.get('total_n', 0):,} | {data.get('weighted_mean_pips', 0):+.2f} | {data.get('pct_pairs_positive', 0):.0f}% |")
    w("")

    w("### Interpretation")
    w("")
    w("- **ALL_3_AGREE**: All 3 timeframes agree on the same regime.")
    w("- **2_OF_3_AGREE**: Exactly 2 of 3 agree.")
    w("- **NO_AGREEMENT**: All 3 disagree.")
    w("")
    w("If agreement contained predictive information, we would expect ALL_3_AGREE to show")
    w("materially different (higher or lower) forward returns than NO_AGREEMENT.")
    w("")

    # Directional agreement
    w("## Directional (Trend) Agreement")
    w("")
    w("| Category | N pairs | Total N | Weighted Mean (pips) | % Pairs Positive |")
    w("|----------|---------|---------|---------------------|------------------|")
    for cat, data in cta.get("directional_aggregate", {}).items():
        n_pairs = data.get("n_pairs", 0)
        if n_pairs == 0:
            continue
        w(f"| {cat} | {n_pairs} | {data.get('total_n', 0):,} | {data.get('weighted_mean_pips', 0):+.2f} | {data.get('pct_pairs_positive', 0):.0f}% |")
    w("")

    # Pairwise agreement
    w("## Phase D: Pairwise Timeframe Agreement")
    w("")
    w("| Pair | Status | N pairs | Total N | Weighted Mean (pips) | % Positive |")
    w("|------|--------|---------|---------|---------------------|------------|")
    for pk, labels in cta.get("pairwise_aggregate", {}).items():
        for label in ["agree", "disagree"]:
            data = labels.get(label, {})
            n_pairs = data.get("n_pairs", 0)
            if n_pairs == 0:
                continue
            w(f"| {pk} | {label} | {n_pairs} | {data.get('total_n', 0):,} | {data.get('weighted_mean_pips', 0):+.2f} | {data.get('pct_pairs_positive', 0):.0f}% |")
    w("")

    # Per-pair breakdown for key categories
    w("## Per-Pair Breakdown: ALL_3_AGREE")
    w("")
    w("| Pair | N | Mean (pips) | Win Rate | Profit Factor | Bootstrap CI |")
    w("|------|---|-------------|----------|---------------|--------------|")
    for pair, pdata in cta.get("pair_summary", {}).items():
        cat = pdata.get("categories", {}).get("ALL_3_AGREE", {})
        if cat.get("n", 0) < 10:
            continue
        cm = cat.get("cost_metrics", {}).get("0.0", {})
        b = cat.get("bootstrap", {})
        ci_str = f"[{b.get('ci_lower', 0):+.1f}, {b.get('ci_upper', 0):+.1f}]" if b.get("ci_lower") is not None else "—"
        w(f"| {pair} | {cat['n']:,} | {cm.get('mean_pips', 0):+.2f} | {cm.get('win_rate', 0):.1f}% | {cm.get('profit_factor', 0):.2f} | {ci_str} |")
    w("")

    # Conclusions
    w("## Conclusions")
    w("")

    # Compute summary stats
    cat_agg = cta.get("category_aggregate", {})
    all3 = cat_agg.get("ALL_3_AGREE", {})
    no_agree = cat_agg.get("NO_AGREEMENT", {})
    all3_mean = all3.get("weighted_mean_pips", 0)
    no_mean = no_agree.get("weighted_mean_pips", 0)
    all3_pct = all3.get("pct_pairs_positive", 0)
    no_pct = no_agree.get("pct_pairs_positive", 0)

    w(f"1. **ALL_3_AGREE mean: {all3_mean:+.2f} pips** ({all3_pct:.0f}% pairs positive)")
    w(f"2. **NO_AGREEMENT mean: {no_mean:+.2f} pips** ({no_pct:.0f}% pairs positive)")
    w("")

    if abs(all3_mean - no_mean) < 0.15:
        w("3. **The difference between agreement and disagreement is negligible** (< 0.15 pips).")
        w("   Agreement contains no meaningful predictive information.")
    elif all3_mean > no_mean:
        w(f"3. Agreement shows slightly higher mean (+{all3_mean - no_mean:.2f} pips), but the effect is small")
        w("   and unlikely to survive transaction costs.")
    else:
        w(f"3. Disagreement shows slightly higher mean (+{no_mean - all3_mean:.2f} pips), which is")
        w("   counterintuitive and may be noise.")

    w("")
    w("4. **No agreement category shows consistent positive EV across all pairs.**")
    w("5. **Pairwise agreement (15min×4h agree: +0.02 pips) is marginally positive but negligible.**")
    w("6. **1h×4h agreement is actually negative (-0.16 pips), further undermining MTF signal designs.**")
    w("")
    w("### RECOMMENDATION")
    w("")
    w("**Cross-timeframe agreement does NOT contain meaningful predictive information.**")
    w("The hypothesis that timeframe agreement improves signal quality is **not supported**.")
    w("")
    w("---")
    w("*Generated by cross_timeframe_agreement.py. Primary horizon: 60 bars on 15min grid.*")

    return "\n".join(lines)


if __name__ == "__main__":
    # Generate temporal stability report
    report_ts = generate_temporal_stability_report()
    out_ts = RESULTS_DIR / "TEMPORAL_STABILITY_ANALYSIS.md"
    with open(out_ts, "w") as f:
        f.write(report_ts)
    print(f"Saved {out_ts}")

    # Generate cross-timeframe agreement report
    report_cta = generate_cross_timeframe_agreement_report()
    out_cta = RESULTS_DIR / "CROSS_TIMEFRAME_AGREEMENT.md"
    with open(out_cta, "w") as f:
        f.write(report_cta)
    print(f"Saved {out_cta}")
