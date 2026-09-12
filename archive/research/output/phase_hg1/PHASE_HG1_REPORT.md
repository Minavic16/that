# Phase HG-1: Holy Grail / ICSA Framework Validation

## Classification: A. NO STRUCTURAL SUPPORT — KILL THE FRAMEWORK

## Executive Summary

The ICSA framework was tested across five controlled experiments on 2016-2026 FX data (20 pairs, 5-minute bars). The critical finding:

**The MFE right tail exists in the market, but ICSA does not exploit it better than random entry.**

- MFE ≥ +5R: ICSA = 5.4%, Random = 6.1%, Trend = 6.1%
- MFE ≥ +10R: ICSA = 0.4%, Random = 0.4%, Trend = 0.4%
- Permutation p = 0.050 (borderline, but ICSA is worse than random)

The framework's structural ingredients are not present. The right-tail distribution is a property of market volatility, not ICSA signal quality.

---

## Experiment HG-1A: ICSA Signal Structure

**Universe**: 8 G10 currencies (USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD)
**Entry TF**: 5-minute bars (788K bars, 2016-2026)
**Strength formula**: Multi-period ROC (5, 10, 20 bar) with rolling z-score normalization
**Signal**: BUY when base strength > 0 AND quote strength < 0; SELL when base < 0 AND quote > 0
**Cooldown**: 1 day minimum between same-pair signals
**Divergence threshold**: 5.0 (on [-100, +100] scale)

**Results**:
- 42,274 ICSA signals (21,692 BUY, 20,582 SELL)
- Average divergence: 110.88 (strong divergence)
- 32,913 valid trade paths computed

---

## Experiment HG-1B: Currency Divergence Entry

The entry mechanism is straightforward: BUY when base is strengthening and quote is weakening, SELL when base is weakening and quote is strengthening. No filters, no optimization.

---

## Experiment HG-1C: Price-Path Distribution (MOST IMPORTANT)

For each ICSA signal, the subsequent price path was tracked over 6 days (288 bars of 5min data). MAE and MFE were computed in R-multiples (1R = 3 ATR initial stop).

### MFE Distribution

| Metric | Value |
|--------|-------|
| N trades | 32,913 |
| Mean MFE | 1.887R |
| Median MFE | 1.436R |
| P90 MFE | 3.998R |
| P99 MFE | 7.939R |
| Skewness | 1.87 |
| Kurtosis | 5.12 |

### Reach Probabilities

| R-threshold | ICSA | Trend | Random |
|-------------|------|-------|--------|
| ≥ +1R | 63.7% | 65.1% | 65.3% |
| ≥ +2R | 35.9% | 37.5% | 37.8% |
| ≥ +3R | 19.0% | 20.1% | 20.4% |
| ≥ +5R | 5.4% | 6.1% | 6.1% |
| ≥ +10R | 0.4% | 0.4% | 0.4% |
| ≥ +20R | 0.0% | 0.0% | 0.0% |

### Right-Tail Concentration

| Top % of trades | % of total MFE |
|-----------------|---------------|
| Top 1% | 5.5% |
| Top 5% | 18.6% |
| Top 10% | 30.6% |

### MAE Distribution

| Metric | Value |
|--------|-------|
| Mean MAE | 1.862R |
| Median MAE | 1.414R |

**Interpretation**: The MFE right tail is thin. A Holy Grail system requires the top 1% of trades to generate 20-50% of total profit. Here, the top 1% generates only 5.5%. The distribution is approximately symmetric between MAE and MFE, suggesting no directional edge.

---

## Experiment HG-1D: Timeframe Management Test

| Management | N | Win Rate | Avg R | PF | Max DD |
|------------|---|----------|-------|-----|--------|
| M0_entry_only | 32,913 | 48.8% | -0.001 | 0.99 | 8.2R |
| M1_to_15m | 32,913 | 49.4% | -0.002 | 0.98 | 8.3R |
| M2_to_1h | 32,913 | 49.8% | 0.000 | 1.00 | 8.3R |
| M3_to_4h | 32,913 | 49.9% | +0.012 | 1.04 | 8.1R |
| M4_to_1d | 32,913 | 50.7% | +0.028 | 1.03 | 8.3R |

**Interpretation**: The management ladder provides negligible improvement. M4 (hold to 1D) has the highest avg R (+0.028R) but it's economically insignificant. The difference between M0 and M4 is 0.029R per trade — far too small to overcome transaction costs.

---

## Experiment HG-1E: ATR Stop Structure

| Stop | N | Stop-Out | +5R | Med MAE | Med MFE |
|------|---|----------|-----|---------|---------|
| 0.5 ATR | 8,227 | 98% | 87% | 18.88 | 19.84 |
| 1.0 ATR | 8,227 | 95% | 74% | 9.44 | 9.92 |
| 2.0 ATR | 8,227 | 89% | 50% | 4.72 | 4.96 |
| 3.0 ATR | 8,227 | 83% | 32% | 3.15 | 3.31 |
| 5.0 ATR | 8,227 | 72% | 12% | 1.89 | 1.99 |

**Note**: MAE/MFE are maximum excursions along the path, NOT terminal outcomes. A trade can experience 5R favorable excursion but still close at breakeven if price reverses.

**Interpretation**: The ATR multiples scale the excursion measurement. All stops show similar underlying path behavior — the MFE/MAE ratio is approximately constant across stop distances. No specific ATR multiple provides special separation of noise from signal.

---

## Critical Control: ICSA vs Trend vs Random

| Signal | N | Avg MFE | +5R | +10R | Avg MAE |
|--------|---|---------|-----|------|---------|
| ICSA | 32,913 | 1.887R | 5.4% | 0.4% | 1.862R |
| TREND | 13,681 | 1.956R | 6.1% | 0.4% | 1.870R |
| RANDOM | 13,681 | 1.978R | 6.1% | 0.4% | 1.864R |

**ICSA performs WORSE than random on every metric.** The currency-strength decomposition does not add information beyond what random entry provides.

### Permutation Test

- Observed mean MFE: 1.887R
- Null mean (shuffled): 1.874R ± 0.008R
- p-value: 0.050

The ICSA MFE is barely distinguishable from the null. And the null is constructed by shuffling directions, not by using truly random entries — so the comparison to the RANDOM control group is the more meaningful test.

---

## Time Stability

| Period | N | Avg MFE | +5R |
|--------|---|---------|-----|
| 2016-2018 | 9,321 | 1.943R | 5.9% |
| 2019-2021 | 9,375 | 1.924R | 5.6% |
| 2022-2024 | 9,370 | 1.785R | 4.9% |
| 2025-2026 | 4,847 | 1.906R | 5.3% |

The MFE distribution is stable across periods — but this is expected since it's measuring market volatility, not ICSA signal quality.

---

## Interpretation

### Why the Framework Fails

1. **ICSA adds no information**: The currency-strength decomposition does not improve MFE over random entry. The right-tail distribution is a property of FX market volatility over 6-day windows, not of the ICSA signal.

2. **MFE ≈ MAE**: The MFE distribution (mean 1.887R) is nearly identical to the MAE distribution (mean 1.862R). This means the signal has no directional edge — the path goes up and down with equal probability.

3. **Management adds negligible value**: The timeframe ladder improves avg R by only 0.029R per trade from M0 to M4. This is not the structural benefit the framework claims.

4. **Right tail is thin**: Only 5.4% of trades reach +5R, and the top 1% of trades generates only 5.5% of total MFE. A Holy Grail system needs fat tails.

5. **Market volatility, not signal quality**: The MFE distribution is driven by 6-day FX volatility, which is similar for ICSA, trend, and random entries.

### What This Means

The Holy Grail / ICSA framework does not contain the structural ingredients required for a small-risk, large-winner trend-following system. The framework is killed at HG-1.

---

## What Survived vs What Failed

| Component | Status |
|-----------|--------|
| ICSA signal structure | EXISTS (42K signals) |
| MFE right tail | EXISTS in market (5.4% reach +5R) |
| ICSA beats random | **FAILED** (random is better) |
| Timeframe scaling helps | **FAILED** (0.029R improvement) |
| ATR stop structure | NEUTRAL (all stops equivalent) |
| Right-tail concentration | **FAILED** (thin tails) |

---

## Artifacts

- `research_data/phase_hg1/phase_hg1_results.json`: Full results
- `research_data/phase_hg1/figures/`: 6 figures
  - `01_mfe_distribution.png`: MFE histogram
  - `02_mae_vs_mfe.png`: MAE vs MFE scatter
  - `03_atr_stop_analysis.png`: ATR stop analysis
  - `04_management_comparison.png`: Timeframe management
  - `05_control_comparison.png`: ICSA vs Trend vs Random
  - `06_year_by_year_mfe.png`: Year-by-year MFE
- `tests/regression/test_phase_hg1.py`: Regression tests
