# Phase 11: Controlled Filter Ablation — Currency-Strength Hypothesis

## Classification: C. GROSS STRUCTURE EXISTS BUT IS REGIME-DEPENDENT

## Executive Summary

Phase 11 tested whether six pre-registered filters could isolate a cost-resilient
subsample of the currency-strength signal. One filter combination (gap + JPY + session)
showed significant OOS edge at 4h (+1.03 pip net after costs), but the result is
**regime-dependent** — the OOS period (2024-2026) had structurally higher JPY trend
returns than the discovery period (2016-2023).

## Hypotheses Tested

| # | Filter | Hypothesis | OOS Result |
|---|--------|------------|------------|
| 1 | Gap range (D40-D70) | Middle gaps positive, extremes negative | C: OOS negative |
| 2 | JPY crosses | JPY pairs primary source of edge | C: OOS negative |
| 3 | Session (12-16 UTC) | Overlap tighter spreads | C: OOS negative |
| 4 | Trend alignment (EMA200) | Aligned with macro trend | C: OOS negative |
| 5 | Volatility regime (low) | Low-vol better for trends | D: Insufficient data |
| 6 | Currency structure (rank1 vs rank8) | Top-bottom rank stronger | C: OOS negative |

## Combination Results (gap + JPY + session)

| Horizon | Discovery | OOS | OOS p-value |
|---------|-----------|-----|-------------|
| 1h | n=24153, mean=+0.19 pip, net=-1.53 | n=7275, mean=+0.19 pip, net=-1.53 | 0.406 |
| **4h** | **n=24153, mean=+0.35 pip, net=-1.37** | **n=7275, mean=+2.75 pip, net=+1.03** | **<0.0001** |

## Critical Finding: Regime Dependency

The OOS 4h result is **8x larger** than the discovery result:
- Discovery mean: +0.35 pip
- OOS mean: +2.75 pip

### Yearly Breakdown (gap_jpy_session, 4h)

**Discovery (2016-2023):**
| Year | Mean (pip) | Win Rate | N |
|------|-----------|----------|---|
| 2016 | +0.76 | 50.8% | 2676 |
| 2017 | +0.57 | 51.8% | 2841 |
| 2018 | **-2.43** | 48.7% | 2832 |
| 2019 | +0.61 | 53.1% | 3104 |
| 2020 | +1.16 | 52.7% | 2941 |
| 2021 | +0.64 | 52.0% | 2585 |
| 2022 | **-0.13** | 52.8% | 2823 |
| 2023 | +3.27 | 56.8% | 2828 |

**OOS (2024-2026):**
| Year | Mean (pip) | Win Rate | N |
|------|-----------|----------|---|
| 2024 | +0.61 | 52.7% | 2671 |
| 2025 | +3.80 | 56.7% | 2568 |
| 2026 | +2.60 | 58.2% | 1693 |

**Key observations:**
- Discovery: 6/8 years positive, 2/8 negative (2018, 2022)
- OOS: 3/3 years positive, 0/3 negative
- Discovery average: +0.55 pip/year
- OOS average: +2.34 pip/year (4.3x higher)
- 2023 (last discovery year) already shows elevated returns (+3.27)
- 2018 was the only strongly negative year — coincides with JPY weakening

## Interpretation

The gap_jpy_session filter at 4h captures a **genuine but regime-dependent** effect:

1. **The edge exists**: JPY crosses show positive 4h forward returns when filtered
   for middle gap range and session overlap. This is consistent across multiple
   discovery years.

2. **The edge is regime-dependent**: The 2024-2026 period (BOJ rate normalization,
   JPY strengthening) produced structurally higher trend returns than the historical
   average. The discovery-to-OOS magnitude gap (8x) is too large to be explained
   by sampling variation alone.

3. **The edge may not persist**: If the BOJ completes its normalization cycle and
   JPY volatility compresses, the trend effect could weaken or reverse.

## Research Decision

**CONDITIONAL** — The filter identifies a genuine effect, but the OOS magnitude
is inflated by a favorable regime. Before proceeding:

1. Test on a truly independent period (e.g., hold out 2023 as a second OOS)
2. Investigate whether the BOJ policy regime is the causal mechanism
3. Test whether the effect persists in low-vol JPY environments
4. Consider whether the edge is sufficient after realistic per-pair costs
   (JPY pairs: 1.4-3.0 pip round-trip)

## Cost Sensitivity

At current JPY pair costs:
- USD/JPY: 1.4 pip round-trip → net OOS expectancy: +2.75 - 1.4 = +1.35 pip (positive)
- GBP/JPY: 3.0 pip round-trip → net OOS expectancy: +2.75 - 3.0 = -0.25 pip (negative)
- AUD/JPY: 2.0 pip round-trip → net OOS expectancy: +2.75 - 2.0 = +0.75 pip (positive)

The filter is cost-sensitive: only tightest-spread JPY pairs survive.

## Files Generated

- `research_data/phase11/phase11_results.json` — Full results
- `research_data/phase11/phase11_summary.csv` — Summary table
- `PHASE11_FILTER_ABLATION_REPORT.md` — This report
- `scripts/phase11_filter_ablation.py` — Experiment script
- `tests/regression/test_phase11_filter_ablation.py` — Regression tests
