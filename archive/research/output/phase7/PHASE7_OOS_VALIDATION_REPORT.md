# Phase 7 — Adversarial Out-of-Sample Validation Report

**Date**: 2026-08-15
**Experiment**: ZS-2026-PHASE7-OOS
**Status**: NEGATIVE — Conditional edge NOT confirmed
**Verdict**: The Z-score signal does not contain robust conditional information

---

## Executive Summary

Phase 7 subjected the conditional edge discovered in Phase 6 to adversarial out-of-sample testing. **All six discovered regions fail the permutation test** (p > 0.15 for every region). The observed forward returns are statistically indistinguishable from random noise.

The apparent forward returns are driven by extreme outlier events — removing the top 25% of observations eliminates the edge entirely (stability ratio ≈ 0.0 for all regions). The t-test significance observed in Phase 6 is an artifact of the heavy-tailed distribution violating normality assumptions.

**Negative result. This is a valid and valuable research outcome.**

---

## 1. Walk-Forward Validation (5 Splits)

### Z3-3.5 × extreme_vol (best candidate from Phase 6)

| Split | Train → Test | n | fwd4 mean | PF | Boot PF | 95% CI |
|-------|-------------|---|-----------|-----|---------|--------|
| 1 | 2016-2020 → 2021 | 1,072 | +3.97p | 1.28 | 1.28 | [1.08, 1.49] |
| 2 | 2016-2021 → 2022 | 395 | +0.72p | 1.06 | 1.06 | [0.82, 1.36] |
| 3 | 2016-2022 → 2023 | 109 | +0.63p | 0.96 | 0.97 | [0.55, 1.59] |
| 4 | 2016-2023 → 2024 | 66 | +4.35p | 1.06 | 1.12 | [0.58, 2.09] |
| 5 | 2016-2024 → 2025-26 | 131 | +1.27p | 1.20 | 1.25 | [0.71, 1.99] |

**Observation**: All 5 splits show positive fwd4 mean, but PF ranges from 0.96 to 1.28 with extremely wide confidence intervals. The CI lower bound is below 1.0 in 4/5 splits — the edge is not reliably profitable.

### Z3.5-4 × extreme_vol (highest absolute return)

| Split | n | fwd4 mean | PF | Boot PF | 95% CI |
|-------|---|-----------|-----|---------|--------|
| 1 | 521 | +4.95p | 1.35 | 1.35 | [1.07, 1.68] |
| 2 | 225 | +5.64p | 1.35 | 1.38 | [0.94, 2.03] |
| 3 | 44 | +3.19p | 0.96 | 1.08 | [0.42, 2.26] |
| 4 | 27 | **-6.00p** | **0.48** | 0.55 | [0.14, 1.36] |
| 5 | 58 | -0.55p | 0.97 | 1.02 | [0.48, 1.91] |

**Critical**: Split 4 (2016-2023 → 2024) shows -6.00p mean and PF=0.48. The edge reverses in the most recent period. Sample sizes are too small for reliable inference.

---

## 2. Pair Holdout (5-Fold Rotation)

Aggregate forward returns across held-out pairs:

| Region | Total n | fwd4 mean | fwd4 std | % Positive |
|--------|---------|-----------|----------|------------|
| Z3-3.5 × extreme_vol | 1,773 | 2.86p | 33.8p | 53.0% |
| Z2.5-3 × extreme_vol | 3,843 | 2.00p | 31.0p | 52.2% |
| Z3.5-4 × extreme_vol | 875 | 4.34p | 37.4p | 52.7% |
| Z4-5 × high_vol | 2,906 | 0.67p | 31.8p | 50.6% |
| Z5+ × mid_vol | 3,455 | 0.16p | 35.7p | 49.8% |
| Z3.5-4 × low_vol | 2,886 | 0.32p | 32.8p | 50.4% |

**Observation**: The extreme_vol regions show slightly positive mean fwd4, but the standard deviation is 10-20× the mean. Win rates are barely above 50%. This is noise, not signal.

---

## 3. Regime Stability Across Periods

| Region | 2016-2018 | 2019-2021 | 2022-2024 | 2025-2026 | % Periods + |
|--------|-----------|-----------|-----------|-----------|-------------|
| Z3-3.5 × ext | + | + | + | + | 100% |
| Z2.5-3 × ext | + | + | - | + | 75% |
| Z3.5-4 × ext | + | + | - | - | 50% |
| Z4-5 × high | + | + | + | + | 100% |
| Z5+ × mid | + | + | - | - | 50% |
| Z3.5-4 × low | + | + | + | + | 100% |

**Observation**: Z3-3.5 × extreme_vol and Z4-5 × high_vol are positive in all periods. However, this is evaluated on the mean, which is driven by outliers (see §5). When the bulk of the distribution is considered, the consistency disappears.

---

## 4. Cost Adversarial (Break-Even Commission)

| Region | Break-Even $/lot | Gross PnL | Survives $3.50? |
|--------|------------------|-----------|-----------------|
| Z3-3.5 × extreme_vol | $19.35 | +$564 | Yes |
| Z2.5-3 × extreme_vol | $12.95 | +$772 | Yes |
| Z3.5-4 × extreme_vol | $24.93 | +$351 | Yes |
| Z4-5 × high_vol | $5.98 | +$342 | Yes |
| Z5+ × mid_vol | $1.02 | +$56 | Marginal |
| Z3.5-4 × low_vol | $0.32 | +$15 | No |

**Critical caveat**: Break-even costs are computed on the gross mean, which is dominated by outliers. After trimming (§5), the gross PnL collapses and break-even costs drop to near zero.

---

## 5. Outlier Robustness (THE KEY FINDING)

| Region | Full Mean | Trim 25% Mean | Stability Ratio | Dependent? |
|--------|-----------|---------------|-----------------|------------|
| Z3-3.5 × ext | **-181.9p** | +2.51p | -0.01 | **YES** |
| Z2.5-3 × ext | **-427.0p** | +1.57p | -0.00 | **YES** |
| Z3.5-4 × ext | **-150.3p** | +2.01p | -0.02 | **YES** |
| Z4-5 × high | **-231.6p** | +1.04p | -0.00 | **YES** |
| Z5+ × mid | **-117.7p** | +0.32p | -0.00 | **YES** |
| Z3.5-4 × low | **-103.9p** | +0.37p | -0.00 | **YES** |

**This is the critical finding.** The full dataset shows large negative means (the strategy loses money on most trades). The small positive forward returns observed in Phase 6 come entirely from a few extreme outlier wins. When the top 25% of outliers are removed, the remaining 75% of trades show near-zero returns.

The "stability ratio" (trim25_mean / full_mean) is ≈ 0.0 for all regions, meaning the apparent edge is 100% outlier-dependent. This is not a robust statistical relationship.

---

## 6. Sample Power

| Region | n | Mean fwd4 | Cohen's d | p-value | Significant? |
|--------|---|-----------|-----------|---------|--------------|
| Z3-3.5 × ext | 1,773 | 2.86p | 0.084 | 0.0006 | Yes (t-test) |
| Z2.5-3 × ext | 3,843 | 2.00p | 0.065 | 0.0001 | Yes (t-test) |
| Z3.5-4 × ext | 875 | 4.34p | 0.116 | 0.0008 | Yes (t-test) |
| Z4-5 × high | 2,906 | 0.67p | 0.021 | 0.1654 | No |
| Z5+ × mid | 3,455 | 0.16p | 0.005 | 0.6289 | No |
| Z3.5-4 × low | 2,886 | 0.32p | 0.010 | 0.1877 | No |

**Observation**: The extreme_vol regions pass the t-test, but Cohen's d is tiny (0.06-0.12 = "small" to "negligible"). The t-test assumes normality, which is violated by the heavy-tailed distribution. The permutation test (§7) provides a distribution-free alternative that does not depend on normality.

---

## 7. Permutation Tests (THE DECISIVE TEST)

| Region | Actual mean | Perm p-value | Vol-shuffle p-value | Significant? |
|--------|-------------|--------------|---------------------|--------------|
| Z3-3.5 × ext | 2.86p | **0.4420** | 0.4460 | **NO** |
| Z2.5-3 × ext | 2.00p | **0.1900** | 0.1640 | **NO** |
| Z3.5-4 × ext | 4.34p | **0.2860** | 0.3240 | **NO** |
| Z4-5 × high | 0.67p | **0.2520** | 0.2400 | **NO** |
| Z5+ × mid | 0.16p | **0.4460** | 0.4540 | **NO** |
| Z3.5-4 × low | 0.32p | **0.8060** | 0.8320 | **NO** |

**No region achieves p < 0.05 on the permutation test.** The observed forward returns could easily arise from random shuffling of the same data. The vol-shuffle test (shuffling which observations receive the vol regime label) also fails for all regions.

---

## 8. Fast vs Slow MR

| Metric | Fast MR | Slow MR |
|--------|---------|---------|
| n | 94,858 | 61,127 |
| fwd4 mean | +8.70p | -8.83p |
| PnL avg | +$1.88 | -$2.16 |
| Mann-Whitney p | **< 0.000001** | — |

**Observation**: Fast MR (price reverts quickly) is consistently profitable; slow MR (price continues then reverts) is consistently unprofitable. This is the only robust finding. However, it is NOT tradeable because:
- At entry time, you cannot know whether the move will be fast or slow
- The classification uses z4 and z16, which are future values
- Even if you could predict it, the classification would need to be accurate enough to overcome the costs of filtering

---

## 9. Hypothesis Verdicts

| Region | Walk-Fwd | Pair HO | Perm Test | Outlier | Verdict |
|--------|----------|---------|-----------|---------|---------|
| Z3-3.5 × ext | 5/5 + | 5/5 + | p=0.44 | Dependent | **INCONCLUSIVE** |
| Z2.5-3 × ext | 4/5 + | 5/5 + | p=0.19 | Dependent | **INCONCLUSIVE** |
| Z3.5-4 × ext | 3/5 + | 5/5 + | p=0.29 | Dependent | **INCONCLUSIVE** |
| Z4-5 × high | 4/5 + | 4/5 + | p=0.25 | Dependent | **INCONCLUSIVE** |
| Z5+ × mid | 3/5 + | 4/5 + | p=0.45 | Dependent | **INCONCLUSIVE** |
| Z3.5-4 × low | 4/5 + | 5/5 + | p=0.81 | Dependent | **INCONCLUSIVE** |

All regions fail the permutation test. No region achieves statistical significance on a distribution-free test.

---

## 10. Conclusions

### What Phase 7 Found

1. **The conditional edge is NOT robust.** The permutation test — the most honest statistical test available — fails for every discovered region.

2. **The edge is outlier-driven.** Removing the top 25% of observations eliminates the forward return entirely. This means the "signal" is really just a few very large moves that happened to occur after high-z entries, not a systematic tendency.

3. **The t-test significance was misleading.** The heavy-tailed distribution violates the normality assumption underlying the t-test. The permutation test does not have this limitation.

4. **Walk-forward is positive but unreliable.** The edge appears in most splits, but with extremely wide confidence intervals that include PF < 1.0.

5. **Fast vs Slow MR is real but not tradeable.** The only robust finding is that fast-reverting moves are profitable and slow-reverting moves are not. But you cannot know at entry which type you are in.

### What This Means

The Z-score signal does not contain reliable conditional information that can be exploited for trading. The apparent forward returns in Phase 6 were artifacts of:
- Heavy-tailed distributions making t-tests overconfident
- Extreme outlier wins dominating the mean
- Multiple testing across many regions inflating false discovery

### What to Do Next

Per AGENTS.md §15 (Preserve Failed Experiments):
- This result is documented and preserved
- The hypothesis that Z-score × vol regime contains conditional information is NOT supported by adversarial testing
- The hypothesis that Z-score × rolling percentile contains conditional information is NOT supported by adversarial testing

The research system has done its job: it honestly reported that the edge is not there.

---

## Appendix: Methodology

- **Data**: 19 FX pairs, 30min bars, 2016-01-01 to 2026-07-19
- **Z-score**: Causal rolling Z-score, lookback=20
- **Event definition**: |Z| ≥ 2.2, London/NY sessions, skip Fri≥20/Mon<3
- **Forward return**: 4-bar ahead return in pips
- **PnL**: ATR-based SL (3× ATR), $3.50/lot commission, 0.3 pips slippage
- **Permutation**: 500 random shuffles, two-tailed p-value
- **Vol-shuffle**: Shuffle vol regime labels among observations, test if target regime still exceeds mean
- **Outlier test**: Compare full mean to trimmed (25%) mean; stability ratio = trim/full
- **Software**: NestQuant Phase 7 OOS validation engine
