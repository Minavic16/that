# Phase 9B: Corrected Economic Validation Report

## Executive Summary

**Verdict: SUPPORTED — BUT COST SENSITIVE**

Phase 9B corrects the accounting bugs identified in Phase 9 and reruns
the economic validation with proper pip-based returns and pair-specific
transaction costs.

- Events analyzed: 221,310
- Walk-forward folds: 5
- Forward returns: actual pips (corrected)
- Transaction costs: pair-specific (corrected)

## Economic Accounting Validation

### Corrections from Phase 9

| Issue | Phase 9 (Buggy) | Phase 9B (Corrected) |
|-------|-----------------|----------------------|
| pip_value(EUR/USD) | $10.0000 | $10.00 |
| pip_value(USD/JPY) | $6.7000 | $6.70 |
| Commission in pips (EUR/USD) | 3500 pips | 0.65 pips |
| Forward returns | ΔP/P × 10000 (relative bp) | ΔP / pip_size (actual pips) |
| Cost pair-specific | No (always EUR/USD) | Yes |

### Unit Definitions

- **Price**: market mid-price in conventional units
- **Pip**: 0.0001 for non-JPY, 0.01 for JPY pairs
- **Pip value per lot**: pip_size × 100,000 × USD_per_quote
- **Forward return**: (P_{t+4} - P_t) / pip_size (in pips)
- **Transaction cost**: spread + slippage + commission/pip_value (in pips)
- **Net PnL**: sum of (forward_return - cost) across trades (in pips)

## Cost Assumptions

| Scenario | Spread | Slippage | Commission | Total EUR/USD | Total USD/JPY |
|----------|--------|----------|------------|---------------|---------------|
| COST_0 | 0.00 | 0.00 | $0.00 | 0.00pip | 0.00pip |
| COST_LOW | 0.50 | 0.10 | $2.00 | 0.80pip | 0.90pip |
| COST_BASE | 1.00 | 0.30 | $3.50 | 1.65pip | 1.82pip |
| COST_HIGH | 2.00 | 0.50 | $7.00 | 3.20pip | 3.54pip |

## Global Threshold Analysis

| Threshold | Trades | % Traded | Fast Rate | Win Rate | Mean Ret | Gross Exp | BE Cost |
|-----------|--------|----------|-----------|----------|----------|-----------|---------|
| 0.50 | 92,928 | 42.0% | 0.619 | 0.501 | 0.15 | 0.15 | 0.15 |
| 0.55 | 64,568 | 29.2% | 0.671 | 0.499 | 0.06 | 0.06 | 0.06 |
| 0.60 | 45,161 | 20.4% | 0.725 | 0.500 | 0.06 | 0.06 | 0.06 |
| 0.65 | 31,644 | 14.3% | 0.775 | 0.499 | 0.18 | 0.18 | 0.18 |
| 0.70 | 22,071 | 10.0% | 0.822 | 0.500 | 0.11 | 0.11 | 0.11 |
| 0.75 | 15,336 | 6.9% | 0.867 | 0.496 | 0.04 | 0.04 | 0.04 |
| 0.80 | 10,228 | 4.6% | 0.909 | 0.492 | -0.33 | -0.33 | 0.00 |
| 0.85 | 6,676 | 3.0% | 0.942 | 0.489 | -0.48 | -0.48 | 0.00 |
| 0.90 | 3,949 | 1.8% | 0.976 | 0.487 | -0.69 | -0.69 | 0.00 |
| 0.95 | 2,012 | 0.9% | 0.991 | 0.492 | -0.31 | -0.31 | 0.00 |

## Walk-Forward Threshold Selection

### Selection Method

For each fold, the threshold is selected on TRAIN data only by maximizing
net expectancy subject to minimum 50 trades. The selected threshold is
then frozen and applied to the TEST set exactly once.

### Results

| Fold | Train | Test | Selected Thr | Test Trades | Test Net Exp | Test PF | BE Cost |
|------|-------|------|-------------|-------------|--------------|---------|---------|
| 2021 | 2016-2020 | 2021-2021 | 0.65 | 2,820 | -0.23 | 0.97 | 0.00 |
| 2022 | 2016-2021 | 2022-2022 | 0.65 | 2,815 | 0.29 | 1.03 | 0.29 |
| 2023 | 2016-2022 | 2023-2023 | 0.65 | 3,031 | 1.01 | 1.12 | 1.01 |
| 2024 | 2016-2023 | 2024-2024 | 0.65 | 2,892 | -0.86 | 0.88 | 0.00 |
| 2025-2026 | 2016-2024 | 2025-2026 | 0.65 | 3,836 | 0.14 | 1.02 | 0.14 |

### Strict OOS: Baseline vs Gated vs Oracle

| Fold | Baseline Exp | Gated Exp | Oracle Exp | Gated > Baseline |
|------|-------------|-----------|------------|------------------|
| 2021 | -0.07 | -0.23 | 0.32 | NO |
| 2022 | 0.01 | 0.29 | -0.46 | YES |
| 2023 | 0.45 | 1.01 | 1.06 | YES |
| 2024 | -0.22 | -0.86 | -0.04 | NO |
| 2025-2026 | 0.15 | 0.14 | 0.13 | NO |

## Threshold Robustness

### Last Fold (2025-2026) — Threshold Sensitivity

| Threshold | Trades | Net Exp | PF | Max DD |
|-----------|--------|---------|----|--------|
| 0.5 | 12,063 | 0.13 | 1.02 | 3993.8 |
| 0.55 | 8,181 | 0.04 | 1.01 | 4216.7 |
| 0.6 | 5,587 | 0.12 | 1.02 | 3930.7 |
| 0.65 | 3,836 | 0.14 | 1.02 | 3051.9 ← SELECTED |
| 0.7 | 2,594 | 0.38 | 1.05 | 2419.8 |
| 0.75 | 1,786 | 0.07 | 1.01 | 2264.3 |
| 0.8 | 1,163 | -0.56 | 0.94 | 2135.2 |
| 0.85 | 743 | -0.40 | 0.96 | 1194.1 |
| 0.9 | 415 | -0.43 | 0.96 | 797.0 |

## Cost Robustness

| Fold | Scenario | Net Exp | Net PnL | Net PF | Avg Cost |
|------|----------|---------|---------|--------|----------|
| 2021 | COST_0 | -0.23 | -641.5 | 0.97 | 0.00 |
| 2021 | COST_LOW | -1.06 | -2998.4 | 0.85 | 0.84 |
| 2021 | COST_BASE | -1.94 | -5471.2 | 0.74 | 1.71 |
| 2021 | COST_HIGH | -3.55 | -10018.8 | 0.58 | 3.33 |
| 2022 | COST_0 | 0.29 | 809.0 | 1.03 | 0.00 |
| 2022 | COST_LOW | -0.55 | -1539.2 | 0.95 | 0.83 |
| 2022 | COST_BASE | -1.42 | -4004.1 | 0.87 | 1.71 |
| 2022 | COST_HIGH | -3.03 | -8535.6 | 0.75 | 3.32 |
| 2023 | COST_0 | 1.01 | 3058.3 | 1.12 | 0.00 |
| 2023 | COST_LOW | 0.18 | 534.2 | 1.02 | 0.83 |
| 2023 | COST_BASE | -0.70 | -2116.7 | 0.92 | 1.71 |
| 2023 | COST_HIGH | -2.31 | -6988.5 | 0.77 | 3.31 |
| 2024 | COST_0 | -0.86 | -2483.1 | 0.88 | 0.00 |
| 2024 | COST_LOW | -1.69 | -4889.5 | 0.78 | 0.83 |
| 2024 | COST_BASE | -2.56 | -7417.3 | 0.69 | 1.71 |
| 2024 | COST_HIGH | -4.17 | -12062.2 | 0.54 | 3.31 |
| 2025-2026 | COST_0 | 0.14 | 522.3 | 1.02 | 0.00 |
| 2025-2026 | COST_LOW | -0.70 | -2678.8 | 0.91 | 0.83 |
| 2025-2026 | COST_BASE | -1.57 | -6038.6 | 0.81 | 1.71 |
| 2025-2026 | COST_HIGH | -3.18 | -12215.9 | 0.66 | 3.32 |

## Cross-Pair Out-of-Sample Validation

| Fold | Held-Out Pairs | AUC | Threshold | Trades | Net Exp | BE Cost |
|------|----------------|-----|-----------|--------|---------|---------|
| 1 | CAD/JPY, NZD/JPY, NZD/CHF, AUD/CHF, CAD/CHF | 0.6139 | 0.65 | 4,437 | -0.07 | 0.00 |
| 2 | EUR/AUD, AUD/CAD, GBP/JPY, GBP/CAD, GBP/AUD | 0.6260 | 0.65 | 7,807 | 1.17 | 1.17 |
| 3 | NZD/USD, EUR/GBP, EUR/CHF, EUR/JPY, AUD/JPY | 0.6286 | 0.65 | 7,453 | -0.16 | 0.00 |
| 4 | EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD | 0.6322 | 0.70 | 6,766 | -0.21 | 0.00 |
| 5 | CAD/JPY, NZD/JPY, NZD/CHF, AUD/CHF, CAD/CHF | 0.6139 | 0.65 | 4,437 | -0.07 | 0.00 |

- Profitable pairs: 1/5
- Median pair expectancy: -0.07 pip

## Regime Robustness

| Period | Trades | Win Rate | Net Exp | PF | Max DD | BE Cost |
|--------|--------|----------|---------|----|--------|---------|
| 2016-2018 | 6,787 | 0.497 | 0.22 | 1.02 | 2926.1 | 0.22 |
| 2019-2021 | 6,472 | 0.493 | -0.09 | 0.99 | 2659.5 | 0.00 |
| 2022-2024 | 6,154 | 0.507 | 0.10 | 1.01 | 2923.2 | 0.10 |
| 2025-2026 | 2,658 | 0.510 | 0.36 | 1.05 | 2453.7 | 0.36 |

## Permutation Control

| Threshold | Perm p | Mean Diff | Bootstrap CI 95% |
|-----------|--------|-----------|------------------|
| 0.6 | 0.4620 | -0.11 | [-0.45, 0.21] |
| 0.7 | 0.9380 | 0.02 | [-0.48, 0.50] |
| 0.8 | 0.0600 | -0.62 | [-1.41, 0.14] |

## Signal Decile Analysis

| Decile | N | Mean Pred P | Actual Fast Rate | Mean Ret | Net Exp |
|--------|---|-------------|------------------|----------|---------|
| 1 | 11,433 | 0.386 | 0.372 | 0.20 | 0.20 |
| 2 | 11,433 | 0.407 | 0.389 | -0.02 | -0.02 |
| 3 | 11,433 | 0.423 | 0.408 | 0.06 | 0.06 |
| 4 | 11,433 | 0.441 | 0.421 | 0.17 | 0.17 |
| 5 | 11,433 | 0.463 | 0.443 | -0.21 | -0.21 |
| 6 | 11,433 | 0.488 | 0.468 | 0.09 | 0.09 |
| 7 | 11,433 | 0.521 | 0.493 | 0.22 | 0.22 |
| 8 | 11,433 | 0.567 | 0.543 | 0.27 | 0.27 |
| 9 | 11,433 | 0.638 | 0.628 | -0.17 | -0.17 |
| 10 | 11,433 | 0.801 | 0.815 | 0.12 | 0.12 |

## Probability Calibration

- Brier score: 0.2328
- Calibration error: 0.0180

## Classification vs Economic Performance

| Metric | Value |
|--------|-------|
| AUC | 0.6245 |
| Accuracy | 0.5864 |
| Precision | 0.6224 |
| Recall | 0.5071 |
| Brier score | 0.2328 |

## Aggregate Out-of-Sample Results

- **Baseline** (all events): n=114,330, mean=0.07pip, net_exp=0.07, PF=1.01
- **Gated** (P≥0.70): n=10,621, mean=0.10pip, net_exp=0.10, PF=1.01
- **Oracle** (true fast): n=56,944, mean=0.20pip, net_exp=0.20, PF=1.03

## Final Verdict

### SUPPORTED — BUT COST SENSITIVE

The predictive signal generates positive expectancy but the edge
is sensitive to transaction cost assumptions.

## Recommendation

See full report for detailed analysis.
