# Phase 3 — Regime Analysis Report

**Date:** 2026-08-12
**Experiment ID:** ZS-2026-PHASE3-REGIME
**Data:** 20 FX pairs, minute OHLCV, 2016-01-03 to 2026-07-17 (~78.5M bars total)
**Regime classification:** Causal Fenwick-tree streaming percentiles, EMA trend + ATR volatility
**Statistical inference:** Newey-West HAC standard errors

---

## 1. Executive Summary

Z-score mean-reversion is **regime-dependent**. The strongest mean-reversion occurs in weak_trend regimes (especially weak_trend×high_vol), with gross edges 3x larger than the average. However, even the best regime cannot overcome realistic transaction costs.

**Key finding:** Regime classification improves signal quality but does not change the fundamental conclusion — the edge is too small for standalone trading.

---

## 2. Regime Classification

### 2.1 Regime Definitions

| Dimension | Categories | Method |
|---|---|---|
| **Trend** | near_ema, weak_trend, strong_trend | Distance from EMA(200) as % of price |
| **Volatility** | low_vol, mid_vol, high_vol, extreme_vol | Streaming percentile of ATR(14) |

**Trend thresholds:**
- near_ema: |price - EMA| / EMA ≤ 0.2%
- weak_trend: 0.2% < |price - EMA| / EMA < 0.8%
- strong_trend: |price - EMA| / EMA ≥ 0.8%

**Volatility percentiles:** low ≤ 25th, mid 25-75th, high 75-95th, extreme ≥ 95th

### 2.2 Regime Distribution (Aggregate, All 20 Pairs)

| Regime | Bars | % |
|---|---|---|
| near_ema × mid_vol | 37,387,827 | 47.6% |
| near_ema × low_vol | 24,736,241 | 31.5% |
| near_ema × high_vol | 10,316,723 | 13.1% |
| weak_trend × high_vol | 1,899,608 | 2.4% |
| near_ema × extreme_vol | 1,704,784 | 2.2% |
| weak_trend × extreme_vol | 1,194,465 | 1.5% |
| weak_trend × mid_vol | 1,156,618 | 1.5% |
| strong_trend × extreme_vol | 55,265 | 0.1% |
| weak_trend × low_vol | 52,888 | 0.1% |
| strong_trend × high_vol | 1,934 | 0.0% |

**Observation:** 92.2% of bars are in near_ema regimes. Only 7.8% are in weak_trend or strong_trend. Strong_trend is extremely rare (0.1%).

---

## 3. Z-Score Mean Reversion by Regime

### 3.1 Aggregate Results (h=60, all 20 pairs)

| Regime | N_obs | Mean Return | Long (z<-1) | Short (z>1) |
|---|---|---|---|---|
| near_ema × mid_vol | 37,387,793 | +0.000005 | +0.000028 | -0.000021 |
| near_ema × low_vol | 24,735,075 | -0.000018 | +0.000003 | -0.000038 |
| near_ema × high_vol | 10,316,723 | +0.000018 | +0.000041 | -0.000010 |
| weak_trend × high_vol | 1,899,608 | +0.000019 | +0.000099 | -0.000058 |
| weak_trend × mid_vol | 1,156,618 | +0.000003 | +0.000036 | -0.000044 |
| weak_trend × low_vol | 52,753 | -0.000053 | +0.000176 | -0.000170 |

**Key observations:**
1. Long Z-scores (z<-1) always produce positive mean returns — mean-reversion holds in all regimes
2. Short Z-scores (z>1) always produce negative mean returns — consistent direction
3. **weak_trend × high_vol has 3x stronger mean-reversion** than near_ema × mid_vol
4. weak_trend × low_vol has the strongest absolute signal but smallest sample size

### 3.2 Horizon Dependence

| Regime | h=5 | h=15 | h=30 | h=60 | h=120 | h=240 |
|---|---|---|---|---|---|---|
| near_ema × mid_vol | +0.00 | +0.02 | +0.02 | +0.03 | +0.03 | +0.03 |
| weak_trend × high_vol | +0.04 | +0.06 | +0.07 | +0.10 | +0.12 | +0.14 |
| weak_trend × low_vol | +0.02 | +0.08 | +0.14 | +0.18 | +0.21 | +0.26 |

(Long Z-score mean returns, in basis points × 100)

**Observation:** Mean-reversion **increases with horizon** in weak_trend regimes, suggesting the effect is not just short-term noise but a genuine structural tendency.

---

## 4. Cost Sensitivity Analysis (Per Regime)

### 4.1 Aggregate Gross Edge (|z| > 2, all horizons combined)

| Regime | N trades | Gross Edge (pips) | HAC SE | Break-even Cost |
|---|---|---|---|---|
| weak_trend × high_vol | 1,251,093 | **+0.947** | 0.045 | 0.95 pips |
| weak_trend × low_vol | 34,224 | +0.836 | 0.165 | 0.84 pips |
| weak_trend × mid_vol | 807,450 | +0.548 | 0.043 | 0.55 pips |
| near_ema × high_vol | 4,964,280 | +0.312 | 0.014 | 0.31 pips |
| near_ema × mid_vol | 18,456,575 | +0.303 | 0.006 | 0.30 pips |
| near_ema × low_vol | 11,880,158 | +0.242 | 0.006 | 0.24 pips |
| strong_trend × high_vol | 681 | +0.123 | 0.030 | 0.12 pips |

### 4.2 Net Expectancy After Costs (weak_trend × high_vol, best regime)

| Spread | Slippage | Total Cost | Expectancy | Hit Rate | z-stat | Significant? |
|---|---|---|---|---|---|---|
| 0.5 | 0.0 | 0.5 | +0.447 | 35.9% | +10.0 | Yes (+) |
| 1.0 | 0.0 | 1.0 | -0.053 | 34.0% | -1.2 | No |
| 1.0 | 0.3 | 1.3 | -0.353 | 33.4% | -7.9 | Yes (-) |
| 1.5 | 0.0 | 1.5 | -0.553 | 33.1% | -12.4 | Yes (-) |
| 2.0 | 0.0 | 2.0 | -1.053 | 32.4% | -23.7 | Yes (-) |

**Observation:** The best regime (weak_trend×high_vol) breaks even at ~0.95 pips total cost. With realistic costs (1.0+ pip spread), the strategy has negative expectancy even in the most favorable regime.

### 4.3 Net Expectancy After Costs (near_ema × mid_vol, most common regime)

| Spread | Slippage | Total Cost | Expectancy | Hit Rate | z-stat | Significant? |
|---|---|---|---|---|---|---|
| 0.5 | 0.0 | 0.5 | -0.197 | 38.1% | -30.8 | Yes (-) |
| 1.0 | 0.0 | 1.0 | -0.697 | 36.7% | -109.3 | Yes (-) |
| 1.0 | 0.3 | 1.3 | -0.997 | 35.7% | -156.4 | Yes (-) |
| 2.0 | 0.0 | 2.0 | -1.697 | 33.6% | -266.2 | Yes (-) |

**Observation:** The most common regime (92% of bars) has negative expectancy at ALL cost levels.

---

## 5. Statistical Inference

### 5.1 HAC-Robust Standard Errors

Newey-West HAC standard errors were used to account for autocorrelation in minute-level returns. With 4 × (N/100)^(2/9) lags, the HAC SEs are:

| Regime | Raw SE | HAC SE | HAC/Raw ratio |
|---|---|---|---|
| near_ema × mid_vol | 0.003 | 0.006 | 2.0x |
| weak_trend × high_vol | 0.022 | 0.045 | 2.0x |

**Observation:** HAC SEs are ~2x larger than naive SEs, reflecting significant autocorrelation in minute-level returns. Using naive SEs would overstate statistical significance.

### 5.2 Sample Size Requirements

For weak_trend × high_vol (best regime):
- 1.25M extreme Z-score trades over 10 years
- ~125K per year, ~340 per day
- Even with HAC correction, the mean is highly significant (z > 20)
- The issue is not statistical power — the edge is real but too small for costs

---

## 6. Per-Pair Z-Score Statistics

| Pair | Mean | Std | |z|>3 |
|---|---|---|---|
| EUR/USD | +0.007 | 1.538 | 3.65% |
| GBP/USD | +0.005 | 1.576 | 3.75% |
| USD/JPY | +0.024 | 1.554 | 3.81% |
| AUD/USD | +0.007 | 1.541 | 3.58% |
| USD/CHF | +0.007 | 1.559 | 3.82% |
| EUR/GBP | +0.001 | 1.530 | 3.57% |
| EUR/CHF | +0.010 | 1.546 | 3.72% |
| EUR/CAD | +0.004 | 1.508 | 3.39% |
| EUR/AUD | -0.008 | 1.507 | 3.37% |
| GBP/JPY | +0.022 | 1.526 | 3.58% |
| GBP/CAD | +0.005 | 1.521 | 3.48% |
| GBP/AUD | -0.006 | 1.511 | 3.39% |
| AUD/JPY | +0.024 | 1.522 | 3.51% |
| AUD/CAD | +0.009 | 1.509 | 3.36% |
| AUD/CHF | +0.010 | 1.537 | 3.41% |
| NZD/USD | +0.001 | 1.603 | 3.65% |
| NZD/JPY | +0.016 | 1.526 | 3.49% |
| NZD/CHF | +0.004 | 1.542 | 3.44% |
| CAD/JPY | +0.022 | 1.528 | 3.56% |
| CAD/CHF | +0.010 | 1.523 | 3.45% |

**All 20 pairs:** Mean ~0.01, Std ~1.53, |z|>3 ~3.5%. Distributions are slightly fat-tailed (expected ~0.27% beyond ±3 for normal).

---

## 7. Causality Verification

All computations are strictly causal:
- Z-scores use only data available at decision time (rolling window, no future data)
- Regime classification uses Fenwick tree for exact streaming percentiles (no future data)
- EMA and ATR are computed causally on the full series
- Forward returns are computed by backward-shifted comparison

**12 causality tests pass** (5 Z-score + 7 regime), including:
- Future-data invariance (modify future → past unchanged)
- Chunk-size invariance (different chunk sizes → same labels)
- EMA continuity across chunks
- ATR continuity across chunks

---

## 8. Conclusions

### What IS true:
1. Z-score mean-reversion is **regime-dependent** — strongest in weak_trend regimes
2. weak_trend × high_vol has **3x larger gross edge** than near_ema × mid_vol
3. The effect **increases with horizon** in weak_trend regimes
4. The signal is **statistically highly significant** (z > 20 with HAC correction)
5. Mean-reversion is **universal** across all 20 pairs

### What is NOT true:
1. The edge is **not large enough to overcome costs** — even the best regime breaks even at 0.95 pips
2. The most common regime (92% of bars) has **negative expectancy at all cost levels**
3. Regime classification **does not make the strategy viable** — it improves edge but not enough

### Bottom line:
The Z-score mean-reversion hypothesis is **confirmed as a regime-dependent statistical phenomenon** and **rejected as a standalone trading strategy** under realistic execution assumptions. Regime filtering improves the edge but does not change the fundamental conclusion.

---

## 9. Data Files

- `research_data/phase3/regime_analysis.json` — Per-pair regime breakdown, all horizons
- `research_data/phase3/cost_sensitivity.json` — Per-regime cost sensitivity with HAC inference
- `research_data/phase3/all_pairs_summary.json` — Previous Z-score summary
- `research_data/phase3/phase3_core.json` — Detailed per-pair Z-score results
