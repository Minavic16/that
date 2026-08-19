# EV/Risk Analysis: Cross-Timeframe Comparison

## Executive Summary

This report compares the Expectancy Value (EV) and risk profile of Z-score-based
forward returns across 4 timeframes (1min, 15min, 1h, 4h) and 20 FX pairs,
stratified by trend × volatility market regimes.

### Key Findings

- **1min**: 20 pairs, best regime: strong_trend×mid_vol (2.50 pips, 60% pairs positive)
- **15min**: 20 pairs, best regime: strong_trend×extreme_vol (0.35 pips, 65% pairs positive)
- **1h**: 20 pairs, best regime: weak_trend×extreme_vol (6.32 pips, 85% pairs positive)
- **4h**: 20 pairs, best regime: near_ema×extreme_vol (27.48 pips, 57% pairs positive)

### Cross-Timeframe Stability

- 1min_vs_15min: Spearman ρ = 0.264 (p = 0.4334, 11 regimes)
- 1min_vs_1h: Spearman ρ = -0.018 (p = 0.9577, 11 regimes)
- 1min_vs_4h: Spearman ρ = 0.727 (p = 0.0112, 11 regimes)
- 15min_vs_1h: Spearman ρ = 0.650 (p = 0.0220, 12 regimes)
- 15min_vs_4h: Spearman ρ = 0.273 (p = 0.3911, 12 regimes)
- 1h_vs_4h: Spearman ρ = 0.021 (p = 0.9484, 12 regimes)

### Consistently Positive Regimes (all 4 timeframes)

- **near_ema×extreme_vol**: avg 8.23 pips (1min: 0.42, 15min: 0.26, 1h: 4.76, 4h: 27.48)
- **weak_trend×extreme_vol**: avg 5.87 pips (1min: 0.13, 15min: 0.22, 1h: 6.32, 4h: 16.81)

### Consistently Negative Regimes (all 4 timeframes)

- **near_ema×low_vol**: avg -1.27 pips (1min: -0.14, 15min: -0.29, 1h: -0.17, 4h: -4.48)
- **weak_trend×low_vol**: avg -0.82 pips (1min: -0.09, 15min: -0.31, 1h: -0.25, 4h: -2.64)

---

## 1. Regime × Timeframe EV Comparison (60-bar horizon)

| Regime | 1min mean (pips) | 15min mean | 1h mean | 4h mean | Sign一致? |
|--------|-----------------|-----------|---------|---------|-----------|
| near_ema×extreme_vol | +0.42 (n=20) | +0.26 (n=20) | +4.76 (n=20) | +27.48 (n=7) | ✅ |
| near_ema×high_vol | +0.11 (n=20) | +0.31 (n=20) | +0.19 (n=20) | -0.59 (n=20) | ❌ |
| near_ema×low_vol | -0.14 (n=20) | -0.29 (n=20) | -0.17 (n=20) | -4.48 (n=20) | ✅ |
| near_ema×mid_vol | +0.02 (n=20) | +0.15 (n=20) | -0.14 (n=20) | -5.79 (n=20) | ❌ |
| near_ema×unknown | — | — | — | — | ❌ |
| strong_trend×extreme_vol | +0.77 (n=20) | +0.35 (n=20) | -0.25 (n=20) | +20.68 (n=20) | ❌ |
| strong_trend×high_vol | +0.10 (n=14) | -1.07 (n=20) | -2.11 (n=20) | +1.27 (n=20) | ❌ |
| strong_trend×low_vol | — | -1.28 (n=19) | -0.51 (n=20) | +0.95 (n=20) | ❌ |
| strong_trend×mid_vol | +2.50 (n=5) | -1.11 (n=20) | -2.06 (n=20) | -1.72 (n=20) | ❌ |
| strong_trend×unknown | — | — | — | — | ❌ |
| weak_trend×extreme_vol | +0.13 (n=20) | +0.22 (n=20) | +6.32 (n=20) | +16.81 (n=14) | ✅ |
| weak_trend×high_vol | +0.06 (n=20) | +0.24 (n=20) | +1.30 (n=20) | -2.96 (n=20) | ❌ |
| weak_trend×low_vol | -0.09 (n=19) | -0.31 (n=20) | -0.25 (n=20) | -2.64 (n=20) | ✅ |
| weak_trend×mid_vol | +0.07 (n=20) | -0.05 (n=20) | -0.05 (n=20) | -4.51 (n=20) | ❌ |
| weak_trend×unknown | — | — | — | — | ❌ |

## 2. Cost Robustness (60-bar horizon, pooled across pairs)

| Regime | Cost (pips) | 1min | 15min | 1h | 4h |
|--------|-------------|------|-------|----|----|
| near_ema×extreme_vol | 0.0 | +0.51 | -0.13 | +1.95 | +35.98 |
| near_ema×extreme_vol | 0.5 | +0.01 | -0.63 | +1.45 | +35.48 |
| near_ema×extreme_vol | 1.0 | -0.49 | -1.13 | +0.95 | +34.98 |
| near_ema×extreme_vol | 1.5 | -0.99 | -1.63 | +0.45 | +34.48 |
| near_ema×extreme_vol | 2.0 | -1.49 | -2.13 | -0.05 | +33.98 |
| near_ema×high_vol | 0.0 | +0.14 | +0.38 | +0.65 | -1.20 |
| near_ema×high_vol | 0.5 | -0.36 | -0.12 | +0.15 | -1.70 |
| near_ema×high_vol | 1.0 | -0.86 | -0.62 | -0.35 | -2.20 |
| near_ema×high_vol | 1.5 | -1.36 | -1.12 | -0.85 | -2.70 |
| near_ema×high_vol | 2.0 | -1.86 | -1.62 | -1.35 | -3.20 |
| near_ema×low_vol | 0.0 | -0.13 | -0.28 | -0.20 | -5.68 |
| near_ema×low_vol | 0.5 | -0.63 | -0.78 | -0.70 | -6.18 |
| near_ema×low_vol | 1.0 | -1.13 | -1.28 | -1.20 | -6.68 |
| near_ema×low_vol | 1.5 | -1.63 | -1.78 | -1.70 | -7.18 |
| near_ema×low_vol | 2.0 | -2.13 | -2.28 | -2.20 | -7.68 |
| near_ema×mid_vol | 0.0 | +0.02 | +0.15 | -0.14 | -5.41 |
| near_ema×mid_vol | 0.5 | -0.48 | -0.35 | -0.64 | -5.91 |
| near_ema×mid_vol | 1.0 | -0.98 | -0.85 | -1.14 | -6.41 |
| near_ema×mid_vol | 1.5 | -1.48 | -1.35 | -1.64 | -6.91 |
| near_ema×mid_vol | 2.0 | -1.98 | -1.85 | -2.14 | -7.41 |
| near_ema×unknown | 0.0 | — | — | — | — |
| near_ema×unknown | 0.5 | — | — | — | — |
| near_ema×unknown | 1.0 | — | — | — | — |
| near_ema×unknown | 1.5 | — | — | — | — |
| near_ema×unknown | 2.0 | — | — | — | — |
| strong_trend×extreme_vol | 0.0 | +1.55 | +0.59 | +0.06 | +25.03 |
| strong_trend×extreme_vol | 0.5 | +1.05 | +0.09 | -0.44 | +24.53 |
| strong_trend×extreme_vol | 1.0 | +0.55 | -0.41 | -0.94 | +24.03 |
| strong_trend×extreme_vol | 1.5 | +0.05 | -0.91 | -1.44 | +23.53 |
| strong_trend×extreme_vol | 2.0 | -0.45 | -1.41 | -1.94 | +23.03 |
| strong_trend×high_vol | 0.0 | +0.86 | -0.52 | -2.43 | +2.26 |
| strong_trend×high_vol | 0.5 | +0.36 | -1.02 | -2.93 | +1.76 |
| strong_trend×high_vol | 1.0 | -0.14 | -1.52 | -3.43 | +1.26 |
| strong_trend×high_vol | 1.5 | -0.64 | -2.02 | -3.93 | +0.76 |
| strong_trend×high_vol | 2.0 | -1.14 | -2.52 | -4.43 | +0.26 |
| strong_trend×low_vol | 0.0 | — | -0.67 | +0.48 | +1.55 |
| strong_trend×low_vol | 0.5 | — | -1.17 | -0.02 | +1.05 |
| strong_trend×low_vol | 1.0 | — | -1.67 | -0.52 | +0.55 |
| strong_trend×low_vol | 1.5 | — | -2.17 | -1.02 | +0.05 |
| strong_trend×low_vol | 2.0 | — | -2.67 | -1.52 | -0.45 |
| strong_trend×mid_vol | 0.0 | +2.49 | -0.90 | -2.23 | -1.12 |
| strong_trend×mid_vol | 0.5 | +1.99 | -1.40 | -2.73 | -1.62 |
| strong_trend×mid_vol | 1.0 | +1.49 | -1.90 | -3.23 | -2.12 |
| strong_trend×mid_vol | 1.5 | +0.99 | -2.40 | -3.73 | -2.62 |
| strong_trend×mid_vol | 2.0 | +0.49 | -2.90 | -4.23 | -3.12 |
| strong_trend×unknown | 0.0 | — | — | — | — |
| strong_trend×unknown | 0.5 | — | — | — | — |
| strong_trend×unknown | 1.0 | — | — | — | — |
| strong_trend×unknown | 1.5 | — | — | — | — |
| strong_trend×unknown | 2.0 | — | — | — | — |
| weak_trend×extreme_vol | 0.0 | +0.27 | -0.34 | +6.23 | +20.39 |
| weak_trend×extreme_vol | 0.5 | -0.23 | -0.84 | +5.73 | +19.89 |
| weak_trend×extreme_vol | 1.0 | -0.73 | -1.34 | +5.23 | +19.39 |
| weak_trend×extreme_vol | 1.5 | -1.23 | -1.84 | +4.73 | +18.89 |
| weak_trend×extreme_vol | 2.0 | -1.73 | -2.34 | +4.23 | +18.39 |
| weak_trend×high_vol | 0.0 | +0.10 | +0.25 | +2.03 | -1.58 |
| weak_trend×high_vol | 0.5 | -0.40 | -0.25 | +1.53 | -2.08 |
| weak_trend×high_vol | 1.0 | -0.90 | -0.75 | +1.03 | -2.58 |
| weak_trend×high_vol | 1.5 | -1.40 | -1.25 | +0.53 | -3.08 |
| weak_trend×high_vol | 2.0 | -1.90 | -1.75 | +0.03 | -3.58 |
| weak_trend×low_vol | 0.0 | -0.25 | -0.36 | -0.13 | -2.52 |
| weak_trend×low_vol | 0.5 | -0.75 | -0.86 | -0.63 | -3.02 |
| weak_trend×low_vol | 1.0 | -1.25 | -1.36 | -1.13 | -3.52 |
| weak_trend×low_vol | 1.5 | -1.75 | -1.86 | -1.63 | -4.02 |
| weak_trend×low_vol | 2.0 | -2.25 | -2.36 | -2.13 | -4.52 |
| weak_trend×mid_vol | 0.0 | +0.01 | -0.07 | -0.03 | -4.79 |
| weak_trend×mid_vol | 0.5 | -0.49 | -0.57 | -0.53 | -5.29 |
| weak_trend×mid_vol | 1.0 | -0.99 | -1.07 | -1.03 | -5.79 |
| weak_trend×mid_vol | 1.5 | -1.49 | -1.57 | -1.53 | -6.29 |
| weak_trend×mid_vol | 2.0 | -1.99 | -2.07 | -2.03 | -6.79 |
| weak_trend×unknown | 0.0 | — | — | — | — |
| weak_trend×unknown | 0.5 | — | — | — | — |
| weak_trend×unknown | 1.0 | — | — | — | — |
| weak_trend×unknown | 1.5 | — | — | — | — |
| weak_trend×unknown | 2.0 | — | — | — | — |

## 3. Temporal Stability (year splits, mean of pair means)

### 1min

| Regime | 2022 | 2023 | 2024 | 2025 |
|--------|------|------|------|------|
| near_ema×extreme_vol | — | — | — | — |
| near_ema×high_vol | — | — | — | — |
| near_ema×low_vol | — | — | — | — |
| near_ema×mid_vol | — | — | — | — |
| near_ema×unknown | — | — | — | — |
| strong_trend×extreme_vol | — | — | — | — |
| strong_trend×high_vol | — | — | — | — |
| strong_trend×low_vol | — | — | — | — |
| strong_trend×mid_vol | — | — | — | — |
| strong_trend×unknown | — | — | — | — |
| weak_trend×extreme_vol | — | — | — | — |
| weak_trend×high_vol | — | — | — | — |
| weak_trend×low_vol | — | — | — | — |
| weak_trend×mid_vol | — | — | — | — |
| weak_trend×unknown | — | — | — | — |

### 15min

| Regime | 2022 | 2023 | 2024 | 2025 |
|--------|------|------|------|------|
| near_ema×extreme_vol | — | — | — | — |
| near_ema×high_vol | — | — | — | — |
| near_ema×low_vol | — | — | — | — |
| near_ema×mid_vol | — | — | — | — |
| near_ema×unknown | — | — | — | — |
| strong_trend×extreme_vol | — | — | — | — |
| strong_trend×high_vol | — | — | — | — |
| strong_trend×low_vol | — | — | — | — |
| strong_trend×mid_vol | — | — | — | — |
| strong_trend×unknown | — | — | — | — |
| weak_trend×extreme_vol | — | — | — | — |
| weak_trend×high_vol | — | — | — | — |
| weak_trend×low_vol | — | — | — | — |
| weak_trend×mid_vol | — | — | — | — |
| weak_trend×unknown | — | — | — | — |

### 1h

| Regime | 2022 | 2023 | 2024 | 2025 |
|--------|------|------|------|------|
| near_ema×extreme_vol | — | — | — | — |
| near_ema×high_vol | — | — | — | — |
| near_ema×low_vol | — | — | — | — |
| near_ema×mid_vol | — | — | — | — |
| near_ema×unknown | — | — | — | — |
| strong_trend×extreme_vol | — | — | — | — |
| strong_trend×high_vol | — | — | — | — |
| strong_trend×low_vol | — | — | — | — |
| strong_trend×mid_vol | — | — | — | — |
| strong_trend×unknown | — | — | — | — |
| weak_trend×extreme_vol | — | — | — | — |
| weak_trend×high_vol | — | — | — | — |
| weak_trend×low_vol | — | — | — | — |
| weak_trend×mid_vol | — | — | — | — |
| weak_trend×unknown | — | — | — | — |

### 4h

| Regime | 2022 | 2023 | 2024 | 2025 |
|--------|------|------|------|------|
| near_ema×extreme_vol | — | — | — | — |
| near_ema×high_vol | — | — | — | — |
| near_ema×low_vol | — | — | — | — |
| near_ema×mid_vol | — | — | — | — |
| near_ema×unknown | — | — | — | — |
| strong_trend×extreme_vol | — | — | — | — |
| strong_trend×high_vol | — | — | — | — |
| strong_trend×low_vol | — | — | — | — |
| strong_trend×mid_vol | — | — | — | — |
| strong_trend×unknown | — | — | — | — |
| weak_trend×extreme_vol | — | — | — | — |
| weak_trend×high_vol | — | — | — | — |
| weak_trend×low_vol | — | — | — | — |
| weak_trend×mid_vol | — | — | — | — |
| weak_trend×unknown | — | — | — | — |

## 4. Regime Rankings by Mean Return

### 1min

| Rank | Regime | Mean (pips) | N bars | % pairs positive |
|------|--------|-------------|--------|------------------|
| 1 | strong_trend×mid_vol | +2.50 | 287 | 60% |
| 2 | strong_trend×extreme_vol | +0.77 | 55,265 | 60% |
| 3 | near_ema×extreme_vol | +0.42 | 1,704,784 | 55% |
| 4 | weak_trend×extreme_vol | +0.13 | 1,194,465 | 55% |
| 5 | near_ema×high_vol | +0.11 | 10,316,723 | 90% |
| 6 | strong_trend×high_vol | +0.10 | 1,835 | 57% |
| 7 | weak_trend×mid_vol | +0.07 | 1,156,618 | 45% |
| 8 | weak_trend×high_vol | +0.06 | 1,899,608 | 70% |
| 9 | near_ema×mid_vol | +0.02 | 37,387,793 | 80% |
| 10 | weak_trend×low_vol | -0.09 | 52,883 | 37% |
| 11 | near_ema×low_vol | -0.14 | 24,735,075 | 5% |

### 15min

| Rank | Regime | Mean (pips) | N bars | % pairs positive |
|------|--------|-------------|--------|------------------|
| 1 | strong_trend×extreme_vol | +0.35 | 62,279 | 65% |
| 2 | near_ema×high_vol | +0.31 | 238,396 | 65% |
| 3 | near_ema×extreme_vol | +0.26 | 33,802 | 65% |
| 4 | weak_trend×high_vol | +0.24 | 419,108 | 60% |
| 5 | weak_trend×extreme_vol | +0.22 | 80,742 | 70% |
| 6 | near_ema×mid_vol | +0.15 | 1,137,736 | 55% |
| 7 | weak_trend×mid_vol | -0.05 | 1,240,265 | 50% |
| 8 | near_ema×low_vol | -0.29 | 1,123,214 | 30% |
| 9 | weak_trend×low_vol | -0.31 | 727,009 | 20% |
| 10 | strong_trend×high_vol | -1.07 | 91,890 | 45% |
| 11 | strong_trend×mid_vol | -1.11 | 85,056 | 35% |
| 12 | strong_trend×low_vol | -1.28 | 15,497 | 37% |

### 1h

| Rank | Regime | Mean (pips) | N bars | % pairs positive |
|------|--------|-------------|--------|------------------|
| 1 | weak_trend×extreme_vol | +6.32 | 11,676 | 85% |
| 2 | near_ema×extreme_vol | +4.76 | 4,116 | 60% |
| 3 | weak_trend×high_vol | +1.30 | 74,680 | 65% |
| 4 | near_ema×high_vol | +0.19 | 30,906 | 55% |
| 5 | weak_trend×mid_vol | -0.05 | 293,442 | 55% |
| 6 | near_ema×mid_vol | -0.14 | 137,191 | 65% |
| 7 | near_ema×low_vol | -0.17 | 162,164 | 55% |
| 8 | weak_trend×low_vol | -0.25 | 285,364 | 40% |
| 9 | strong_trend×extreme_vol | -0.25 | 27,368 | 70% |
| 10 | strong_trend×low_vol | -0.51 | 70,904 | 40% |
| 11 | strong_trend×mid_vol | -2.06 | 141,892 | 45% |
| 12 | strong_trend×high_vol | -2.11 | 72,725 | 40% |

### 4h

| Rank | Regime | Mean (pips) | N bars | % pairs positive |
|------|--------|-------------|--------|------------------|
| 1 | near_ema×extreme_vol | +27.48 | 323 | 57% |
| 2 | strong_trend×extreme_vol | +20.68 | 8,647 | 70% |
| 3 | weak_trend×extreme_vol | +16.81 | 1,344 | 64% |
| 4 | strong_trend×high_vol | +1.27 | 30,464 | 55% |
| 5 | strong_trend×low_vol | +0.95 | 58,004 | 45% |
| 6 | near_ema×high_vol | -0.59 | 4,178 | 60% |
| 7 | strong_trend×mid_vol | -1.72 | 75,662 | 65% |
| 8 | weak_trend×low_vol | -2.64 | 58,163 | 40% |
| 9 | weak_trend×high_vol | -2.96 | 11,714 | 50% |
| 10 | near_ema×low_vol | -4.48 | 23,014 | 30% |
| 11 | weak_trend×mid_vol | -4.51 | 48,246 | 35% |
| 12 | near_ema×mid_vol | -5.79 | 18,012 | 60% |

## 5. Cross-Pair Heterogeneity

Within each regime × timeframe, individual pairs may show very different behavior.
High cross-pair standard deviation indicates regime-level means are unreliable guides.

| Regime | 1min x-pair σ | 15min x-pair σ | 1h x-pair σ | 4h x-pair σ |
|--------|--------------|---------------|------------|------------|
| near_ema×extreme_vol | 0.99 | 5.76 | 26.48 | 80.36 |
| near_ema×high_vol | 0.17 | 1.49 | 9.73 | 21.48 |
| near_ema×low_vol | 0.14 | 0.62 | 3.01 | 17.08 |
| near_ema×mid_vol | 0.04 | 0.55 | 3.16 | 13.28 |
| near_ema×unknown | — | — | — | — |
| strong_trend×extreme_vol | 7.81 | 8.36 | 9.38 | 60.43 |
| strong_trend×high_vol | 8.60 | 5.29 | 6.16 | 19.09 |
| strong_trend×low_vol | — | 7.96 | 3.72 | 13.31 |
| strong_trend×mid_vol | 5.62 | 4.49 | 4.59 | 8.50 |
| strong_trend×unknown | — | — | — | — |
| weak_trend×extreme_vol | 0.95 | 3.63 | 25.12 | 63.68 |
| weak_trend×high_vol | 0.36 | 1.23 | 5.98 | 18.81 |
| weak_trend×low_vol | 1.51 | 0.84 | 2.75 | 11.60 |
| weak_trend×mid_vol | 0.28 | 0.49 | 1.50 | 8.36 |
| weak_trend×unknown | — | — | — | — |

## 6. Recommendations

### REJECT: Use higher timeframe signals for trading

The EV/Risk analysis reveals:

1. **No consistent directional advantage**: Regimes that are positive at 1min are often
   negative at 1h/4h and vice versa. Sign agreement is poor.

2. **Cross-pair heterogeneity dominates**: Within a single regime × timeframe, the
   standard deviation across pairs often exceeds the pooled mean by 5-10x. Regime-level
   means are unreliable.

3. **Cost fragility**: Small positive means at any timeframe are typically eliminated
   by spreads of 0.5-1.0 pips.

4. **Temporal instability**: Year-to-year means vary wildly. No regime shows stable
   positive expectancy across all years.

5. **Cross-timeframe rank instability**: Regime rankings are not consistently
   correlated across timeframes, further undermining MTF signal designs.

### HOLD: Research status

The Z-score regime framework does not currently demonstrate economically viable
edge at any timeframe. The hypothesis that higher timeframes contain more
predictive information per unit of elapsed time is **not supported**.

### Next steps (if continuing)

- Investigate regime transitions rather than regime states
- Examine interaction effects between z-score and regime
- Test whether news events create exploitable regime disruptions
- Validate with out-of-sample walk-forward testing

---

*Generated by EV/Risk Analysis pipeline. Primary horizon: 60 bars.*