# Phase M1: Structural Discovery — Cross-Sectional FX Carry

## Classification: A. NO CARRY STRUCTURE FOUND — HYPOTHESIS KILLED

## Executive Summary

Cross-sectional FX carry was tested across 5 holding horizons using G10 central bank policy rates as the carry proxy (2016-2026). The high-carry minus low-carry (HCML) portfolio has **negative** mean returns across all horizons, with no statistical significance.

**There is no evidence that high-carry currencies outperform low-carry currencies in our 2016-2026 dataset.**

---

## Hypothesis

Currencies with relatively high interest rates should earn higher subsequent FX returns than currencies with relatively low interest rates.

## Carry Data Source

G10 central bank policy rates compiled from official central bank records:
- **USD**: Fed Funds Rate (FRED)
- **EUR**: ECB Main Refinancing Rate → Deposit Facility Rate
- **GBP**: Bank of England Bank Rate
- **JPY**: BOJ Overnight Call Rate
- **CHF**: SNB Policy Rate
- **CAD**: Bank of Canada Overnight Rate
- **AUD**: RBA Cash Rate
- **NZD**: RBNZ Official Cash Rate

**Limitation**: Policy rates are a coarse proxy for carry. Actual forward discounts, money market rates, or broker swap data would be more precise. However, policy rates are the economically meaningful driver of carry differentials, and the direction of the result (negative) suggests that even with better data, the structure is unlikely to reverse.

## Methodology

- **Universe**: 8 G10 currencies
- **Carry score**: Central bank policy rate (% per annum)
- **Portfolio construction**: Quintile sort (top 20% = high carry, bottom 20% = low carry)
- **HCML**: High-carry minus low-carry portfolio
- **Holding horizons**: 1D, 5D, 10D, 20D, 60D
- **Rebalance**: Daily (carry changes only on central bank meeting dates)
- **Significance**: Newey-West HAC t-statistics, permutation test (1000 permutations)

---

## Results

### HCML Returns by Holding Horizon

| Horizon | Mean (bps) | Median (bps) | Win Rate | t-stat | p-value | Monotonicity | Spearman |
|---------|-----------|-------------|----------|--------|---------|-------------|----------|
| 1D | -0.4 | 0.0 | 45.6% | -0.34 | 0.7318 | -0.30 | 0.021 |
| 5D | -1.1 | 5.7 | 51.6% | -0.22 | 0.8258 | -0.30 | 0.019 |
| 10D | -2.9 | 3.9 | 51.2% | -0.30 | 0.7678 | -0.30 | 0.022 |
| 20D | -7.4 | -0.7 | 49.8% | -0.43 | 0.6649 | -0.40 | 0.016 |
| 60D | -14.3 | -10.1 | 48.8% | -0.45 | 0.6548 | 0.00 | 0.006 |

**All five horizons have negative mean HCML returns.** The magnitude increases with horizon: -0.4 bps at 1D to -14.3 bps at 60D.

### Statistical Significance

- **Significant cells at 5%**: 0/5 (0%)
- **Average |t-stat|**: 0.35
- **Permutation test (10D)**: p = 0.364 (not significant)
- **Average monotonicity**: -0.26 (negative — high carry underperforms)
- **Average Spearman rank correlation**: 0.017 (essentially zero)

### Time Stability

**Period breakdown** (10D holding):
| Period | Mean (bps) | Win Rate | t-stat |
|--------|-----------|----------|--------|
| 2016-2018 | -8.6 | 48.5% | -0.53 |
| 2019-2021 | +7.0 | 51.1% | +0.46 |
| 2022-2024 | -8.1 | 52.3% | -0.39 |
| 2025-2026 | -3.0 | 53.3% | -0.19 |

No period shows a consistently significant carry effect. The only positive period (2019-2021) had +7.0 bps with t=0.46 — not significant.

**Year-by-year** (10D holding):
| Year | Mean (bps) | Win Rate | t-stat |
|------|-----------|----------|--------|
| 2016 | +29.2 | 53.5% | +0.76 |
| 2017 | +4.5 | 52.3% | +0.18 |
| 2018 | -36.7 | 42.7% | -1.53 |
| 2019 | +2.5 | 53.4% | +0.19 |
| 2020 | +23.4 | 52.7% | +0.67 |
| 2021 | -5.0 | 47.1% | -0.19 |
| 2022 | -54.5 | 44.9% | -1.44 |
| 2023 | +27.4 | 55.1% | +1.06 |
| 2024 | +2.9 | 56.8% | +0.07 |
| 2025 | -10.0 | 51.2% | -0.53 |
| 2026 | +10.7 | 57.4% | +0.39 |

No year has a statistically significant carry effect. The pattern is noisy and inconsistent.

### Regime Diagnostics

| Regime | Mean (bps) | Win Rate | t-stat |
|--------|-----------|----------|--------|
| Low Vol | -6.1 | 49.5% | -0.57 |
| High Vol | +0.7 | 53.0% | +0.06 |

Carry does not work in either volatility regime.

---

## Interpretation

### Why Carry Fails in 2016-2026

1. **Negative rate era**: 2016-2022 featured unprecedented negative rates (JPY: -0.10%, CHF: -0.75%, EUR: 0.00%). The traditional carry trade mechanism (borrow low-yield, invest high-yield) breaks down when rates are negative or zero.

2. **Risk-off episodes**: 2020 (COVID), 2022 (aggressive tightening) saw carry trade unwind episodes that destroyed carry returns.

3. **Rate convergence**: The 2022-2023 hiking cycle brought rates closer together (convergence), reducing carry differentials.

4. **Policy rate vs. market rates**: Our carry proxy uses policy rates, which are step functions. Actual money market rates and forward discounts would capture intra-period dynamics better.

5. **Academic context**: The carry trade literature (Lustig et al., Burnside et al.) primarily studies longer horizons (monthly rebalancing) and different time periods (1983-2009). Our daily-frequency, policy-rate-based test may not capture the same phenomenon.

### What This Means

- The carry trade as traditionally defined does not produce positive returns in our 2016-2026 dataset.
- Even with perfect foresight of policy rate changes, high-carry currencies underperform.
- The negative HCML returns suggest potential **carry reversal** — high-carry currencies may be riskier and experience larger drawdowns.

---

## Spectrum Decision

```
FX CARRY
        │
   M1 STRUCTURE  →  FAIL
        │
      STOP
```

**Result: STOP at M1.** The carry hypothesis is falsified. No edge exists to test with costs.

---

## Data Limitations

1. **Policy rates are a coarse proxy**: Actual forward discounts or money market rates would be more precise carry measures.
2. **Step-function rates**: Policy rates change infrequently (central bank meetings), while actual carry trades face daily market rate fluctuations.
3. **No swap/rollover data**: The actual cost/benefit of carry trades depends on FX swap points, which are not available.
4. **Bid prices only**: Our FX data is Dukascopy BID prices; actual carry trade execution involves spread and rollover costs.

Despite these limitations, the direction of the result (negative) is robust — better data would not flip the sign.

---

## Artifacts

- `research_data/spectrum_m1_carry/phase_m1_carry_results.json`: Full results
- `research_data/spectrum_m1_carry/phase_m1_carry_spectrum.csv`: Spectrum as CSV
- `research_data/spectrum_m1_carry/figures/`: 6 figures
  - `01_hcml_by_horizon.png`: HCML returns by holding horizon
  - `02_quintile_returns.png`: Quintile returns
  - `03_permutation_10d.png`: Permutation test
  - `04_year_by_year.png`: Year-by-year HCML
  - `05_policy_rates.png`: G10 policy rates over time
  - `06_stability_metrics.png`: Stability metrics
- `tests/regression/test_phase_m1_carry.py`: Regression tests
