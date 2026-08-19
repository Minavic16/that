# Phase 3 — Final Consistency Audit

**Date:** 2026-08-12
**Auditor:** Automated consistency audit
**Scope:** PHASE_3_ZSCORE_RESEARCH_REPORT.md vs underlying JSON data and source code
**Data files:** phase3_core.json, phase3_results.json, all_pairs_summary.json, regime_analysis.json, cost_sensitivity.json

---

## Executive Summary

The Phase 3 report's **core conclusions are correct**: Z-score mean-reversion is a real but small statistical phenomenon that does not survive realistic transaction costs. However, the audit found **3 material errors** in the report text and **1 corrupted data file** that need correction.

| Category | Status |
|----------|--------|
| Core conclusions | **CORRECT** — Z-score mean-reversion exists but is unprofitable after costs |
| Z-score distribution (Table 1) | **CORRECT** — values match phase3_core.json |
| Forward returns (Table 2) | **CORRECT** — values match phase3_core.json |
| Binned analysis (Table 3) | **PARTIALLY INCORRECT** — monotonicity claim is false for 3/5 displayed pairs |
| All-pairs table (Table 4) | **CORRECT** — bars, correlations, and gross edges verified |
| Temporal stability (Table 5) | **CORRECT** — all 11 years match exactly |
| Cost sensitivity (Table 6) | **CORRECT** — net expectancy math verified |
| Regime analysis | **CORRECT** — aggregate edges match cost_sensitivity.json |
| HAC implementation | **CORRECT** — standard Newey-West with Bartlett kernel |
| Multiple testing | **CORRECT** — all correlations survive BH FDR correction |

---

## AUDIT 1: Z-Score Distribution Discrepancy

### Finding: phase3_results.json is CORRUPTED

`phase3_results.json` contains impossible values:
```
EUR/USD z_distribution.mean = -1,927,378.96
EUR/USD z_distribution.std  = 3,729,141,141.16
EUR/USD pct_below_neg2 = 8.30%
```

These are clearly corrupted (Z-scores with mean of -1.9 million and std of 3.7 billion). The `phase3_core.json` file has correct values:
```
EUR/USD z_dist.mean = 0.0066
EUR/USD z_dist.std  = 1.2888
EUR/USD pct_lt_neg2 = 5.20%
```

**Report status:** The report correctly uses values from `phase3_core.json`. No numbers in the report are affected by this corruption.

**Action required:** `phase3_results.json` should be regenerated or deleted. It is not referenced by any script (`grep` found no imports).

### Source of discrepancy

`characterize_zscore_distribution()` in `phase3_research.py:115-140` uses `np.std(valid)` (ddof=0, population std). The `phase3_core.json` also uses this definition. The report's "~1.29" average is approximately correct.

---

## AUDIT 2: Verify Every '20 Pairs' Claim

### Finding: CONFIRMED

| File | Pair Count | Status |
|------|-----------|--------|
| all_pairs_summary.json | 20 | ✅ |
| regime_analysis.json total_pairs | 20 | ✅ |
| regime_analysis.json pair_results | 20 | ✅ |
| cost_sensitivity.json pair_results | 20 | ✅ |

All 20 pairs match across all files:
```
EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CHF,
EUR/GBP, EUR/CHF, EUR/CAD, EUR/AUD, GBP/JPY,
GBP/CAD, GBP/AUD, AUD/JPY, AUD/CAD, AUD/CHF,
NZD/USD, NZD/JPY, NZD/CHF, CAD/JPY, CAD/CHF
```

---

## AUDIT 3: Verify Temporal-Stability Claims

### Finding: CONFIRMED

Report Table 5 (EUR/USD yearly) matches `phase3_core.json` exactly for all 11 years:

| Year | Report corr | JSON corr | Report mean | JSON mean | Status |
|------|------------|-----------|-------------|-----------|--------|
| 2016 | -0.0152 | -0.015161 | -4.49e-6 | -4.49e-6 | ✅ |
| 2017 | -0.0172 | -0.017177 | +2.17e-5 | +2.173e-5 | ✅ |
| 2018 | -0.0187 | -0.018707 | -7.08e-6 | -7.08e-6 | ✅ |
| 2019 | -0.0189 | -0.018874 | -3.28e-6 | -3.28e-6 | ✅ |
| 2020 | -0.0170 | -0.017035 | +1.45e-5 | +1.452e-5 | ✅ |
| 2021 | -0.0131 | -0.013065 | -1.16e-5 | -1.158e-5 | ✅ |
| 2022 | -0.0125 | -0.012513 | -9.02e-6 | -9.02e-6 | ✅ |
| 2023 | -0.0202 | -0.020193 | +5.65e-6 | +5.65e-6 | ✅ |
| 2024 | -0.0108 | -0.010778 | -1.00e-5 | -1.004e-5 | ✅ |
| 2025 | -0.0172 | -0.017221 | +2.09e-5 | +2.088e-5 | ✅ |
| 2026 | -0.0228 | -0.022774 | -7.57e-6 | -7.57e-6 | ✅ |

All correlations consistently negative across all years. No year shows reversal.

---

## AUDIT 4: Verify Binned Monotonicity Claims

### Finding: INCORRECT — 3 pairs violate mean-return monotonicity

The report states (line 69): *"The relationship between Z-score magnitude and forward returns is **monotonically increasing** across all predefined bins"*

This is **false** for 3 of the 5 displayed pairs. The `>3` bin breaks monotonicity:

#### EUR/USD (displayed in report)
```
Bin 2..3: mean = -2.50e-5
Bin  >3:  mean = -2.44e-5  ← LESS negative, breaks monotonicity
```

#### USD/CHF (displayed in report)
```
Bin 2..3: mean = -3.67e-5
Bin  >3:  mean = -3.38e-5  ← LESS negative, breaks monotonicity
```

#### USD/JPY (displayed in report)
```
Bin 2..3:    mean = -1.42e-5
Bin  >3:     mean = +8.02e-6  ← POSITIVE, completely breaks pattern
```

**Hit rates ARE monotonic** for all pairs. Only mean returns violate monotonicity.

**Root cause:** The `>3` bin has very few observations (12,679–15,688) compared to the `2..3` bin (189,421–191,604). The extreme tail has higher variance and fewer samples, making the mean estimate noisy. For USD/JPY, the `>3` bin mean is actually positive, suggesting the extreme overbought condition may have different dynamics.

**Action required:** The report should qualify the monotonicity claim. The relationship is "approximately monotonic" with violations at the extreme `>3` tail. The `>3` bin anomaly for USD/JPY deserves explicit mention.

---

## AUDIT 5: Audit Cost-Sensitivity Hit-Rate Calculations

### Finding: METHODOLOGY CORRECT, specific hit rates unverifiable without re-running

The cost sensitivity table (Table 6) shows EUR/USD net expectancy at various cost levels. The **net expectancy math is correct**:

| Spread | Commission | Slippage | Total Cost | Report Net | Computed Net | Status |
|--------|-----------|----------|------------|------------|--------------|--------|
| 0.5 | $0 | 0.0 | 0.50 | -0.235 | -0.235 | ✅ |
| 0.5 | $0 | 0.3 | 0.80 | -0.535 | -0.535 | ✅ |
| 1.0 | $0 | 0.0 | 1.00 | -0.735 | -0.735 | ✅ |
| 1.0 | $3.50 | 0.3 | 1.65 | -1.385 | -1.385 | ✅ |
| 1.5 | $3.50 | 0.5 | 2.35 | -2.085 | -2.085 | ✅ |
| 2.0 | $7.00 | 1.0 | 3.70 | -3.435 | -3.435 | ✅ |

Commission conversion: $3.50 / ($10/pip) = 0.35 pips for EUR/USD standard lot.

The **hit rates** in Table 6 are not saved to any JSON file and cannot be verified without re-running `phase3_research.py::cost_sensitivity()`. However, the methodology (net return = return_pips - cost_pips, hit_rate = mean(net > 0)) is correct.

---

## AUDIT 6: Audit 'All Horizons Combined' Regime Gross-Edge Pooling

### Finding: CORRECT

The `cost_sensitivity.py` script pools extreme Z-score returns across all pairs and horizons (60, 120, 240) per regime, then computes HAC standard errors. The aggregate results in `cost_sensitivity.json` match the report's claims:

| Regime | JSON mean (pips) | Report claim | Status |
|--------|-----------------|--------------|--------|
| near_ema×mid_vol | 0.3032 | "+0.30 pips" | ✅ |
| weak_trend×high_vol | 0.9474 | "+0.95 pips" | ✅ |

The 3x ratio (0.9474 / 0.3032 = 3.12x) matches the report's "3x stronger" claim.

**Note:** The report compares specific sub-regimes (near_ema×mid_vol vs weak_trend×high_vol), not aggregates across all volatility levels. This is a valid comparison but should be noted.

---

## AUDIT 7: Verify HAC Implementation Details

### Finding: CORRECT

The Newey-West HAC implementation in `cost_sensitivity.py:48-77`:

```python
max_lags = int(4 * (n / 100) ** (2/9))  # Andrews (1991) bandwidth
weight = 1.0 - lag / (max_lags + 1)      # Bartlett kernel
variance = gamma_0 + 2 * sum(weight * gamma_lag)
SE = sqrt(max(variance, 0) / n)
```

This is the standard Newey-West estimator with:
- **Bandwidth selection:** Andrews (1991) automatic bandwidth `4*(n/100)^(2/9)`
- **Kernel:** Bartlett (triangular) kernel with weights `1 - lag/(L+1)`
- **Variance truncation:** `max(variance, 0)` prevents negative variance

Verification with iid normal data shows HAC SE converges to naive SE (ratio ~0.95-0.99), confirming correct implementation.

---

## AUDIT 8: Verify Multiple-Testing Claims

### Finding: CONFIRMED — all correlations survive BH FDR correction

For 5 major pairs at 60-bar horizon, Fisher z-transformation test:

| Pair | r | n | z-statistic | p-value | BH threshold |
|------|---|---|------------|---------|--------------|
| AUD/USD | -0.0152 | 3,924,381 | -30.06 | ≈0 | 0.01 |
| EUR/USD | -0.0159 | 3,928,660 | -31.46 | ≈0 | 0.02 |
| GBP/USD | -0.0128 | 3,929,232 | -25.31 | ≈0 | 0.03 |
| USD/CHF | -0.0203 | 3,908,991 | -40.07 | ≈0 | 0.04 |
| USD/JPY | -0.0069 | 3,927,464 | -13.59 | ≈0 | 0.05 |

All 5 correlations significant at p < 0.05 after Benjamini-Hochberg FDR correction (α=0.05). The report does not explicitly state BH correction, but the results survive it easily.

**Note:** With n ≈ 3.9 million, even tiny correlations (r = -0.007) are highly statistically significant. Statistical significance ≠ economic significance. The report correctly notes the effect is "too weak to overcome realistic transaction costs."

---

## AUDIT 9: Cross-Check Every Reported Number Against JSON

### Table 1 (Z-Score Distribution): ✅ ALL CORRECT
All values in the report match `phase3_core.json` exactly.

### Table 2 (Forward Returns): ✅ ALL CORRECT
All correlation and conditional mean values match `phase3_core.json`.

### Table 3 (Binned Analysis): ⚠️ VALUES CORRECT, MONOTONICITY CLAIM INCORRECT
All individual bin values match `phase3_core.json`. The monotonicity claim is false for 3/5 pairs (see Audit 4).

### Table 4 (All Pairs): ✅ ALL CORRECT
| Metric | Verification |
|--------|-------------|
| Bars | All 20 pairs match (within 100) |
| Correlations | All match to 4 decimal places |
| Gross edges | Computed from `exp_pips_cost_free` field, all match |

Average gross edge: 0.423 pips (computed from JSON: 0.423) ✅

### Table 5 (Temporal Stability): ✅ ALL CORRECT
All 11 years × 5 columns match exactly (see Audit 3).

### Table 6 (Cost Sensitivity): ✅ NET EXPECTANCY CORRECT
All net expectancy values verified by direct computation (see Audit 5).

---

## AUDIT 10: Additional Findings

### 10.1 Breakeven Cost Error

**Report line 159:** *"Breakeven: Cost = 0 pips. The gross edge is 0.265 pips for EUR/USD. Any cost above zero makes the strategy unprofitable."*

**This is incorrect.** The breakeven cost is **0.265 pips**, not 0 pips. The strategy is profitable at any cost below 0.265 pips. The statement "Any cost above zero makes the strategy unprofitable" is false.

The subsequent statement ("Even the most favorable realistic scenario...yields negative expectancy") is correct because 0.5 pips > 0.265 pips.

### 10.2 USD/JPY Extreme Tail Anomaly

The `>3` bin for USD/JPY has a **positive** mean return (+8.02e-6), meaning when Z > 3 (extreme overbought), the forward return is actually positive, not negative. This completely breaks the mean-reversion pattern for this bin. This anomaly is not mentioned in the report.

### 10.3 phase3_results.json Corruption

The file `phase3_results.json` contains corrupted data (Z-score means of -1.9M, std of 3.7B). This file is not referenced by any script and appears to be from a different, broken calculation. It should be regenerated or deleted.

### 10.4 Strong-Trend Regime Scarcity

The regime classifier almost never identifies "strong_trend" regimes on minute data with EMA span=200. For EUR/USD h60, strong_trend×high_vol has only 34 observations, and strong_trend×low_vol has 0. The report does not discuss this, which is appropriate given the negligible sample size.

---

## Summary of Required Corrections

| # | Severity | Issue | Location | Fix |
|---|----------|-------|----------|-----|
| 1 | **HIGH** | phase3_results.json corrupted | research_data/phase3/ | Regenerate or delete |
| 2 | **MEDIUM** | Monotonicity claim is false for 3/5 pairs | Report line 69 | Qualify: "approximately monotonic with violations at extreme tails" |
| 3 | **LOW** | Breakeven cost stated as 0 pips | Report line 159 | Correct to "0.265 pips" |
| 4 | **LOW** | USD/JPY >3 bin anomaly not mentioned | Report Section 3 | Add footnote about extreme tail behavior |

---

## Conclusion

The Phase 3 report's core findings are **valid and well-supported** by the underlying data. The Z-score mean-reversion phenomenon is real, statistically significant, universal across 20 pairs, temporally stable, and economically insufficient to overcome transaction costs. These conclusions are unaffected by the audit findings.

The 3 material errors (monotonicity claim, breakeven statement, corrupted data file) are **presentation issues**, not methodology flaws. The underlying calculations are correct.

**Recommendation:** Apply the 4 corrections listed above and re-issue the report.
