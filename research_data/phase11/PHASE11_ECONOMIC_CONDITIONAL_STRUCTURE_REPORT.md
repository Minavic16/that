# Phase 11: Economic Conditional Structure Report

## Executive Summary

**Classification: A. NO ECONOMIC STRUCTURE FOUND**
**Research Decision: NO — stop this research branch**

No consistent conditional economic structure found. The signal is predictive (AUC~0.62) but the economic edge is too weak, too concentrated, and too unstable to warrant further investigation.

## Implementation Audit

- pip_value(EUR/USD): $10.00
- pip_value(USD/JPY): $6.70
- Forward returns: actual pips: True
- Cost pair-specific: True
- No look-ahead: True

## Signal Strength × Economic Return

| Bin | N | Mean Pred P | Actual Fast Rate | Mean Return | Net Exp (LOW) | Net Exp (BASE) |
|-----|---|-------------|------------------|-------------|---------------|----------------|
| 0.50-0.55 | 14,685 | 0.523 | 0.495 | 0.36 | -0.48 | -1.36 |
| 0.55-0.60 | 9,954 | 0.573 | 0.552 | 0.03 | -0.80 | -1.68 |
| 0.60-0.65 | 6,812 | 0.623 | 0.615 | -0.32 | -1.15 | -2.03 |
| 0.65-0.70 | 4,773 | 0.674 | 0.668 | 0.05 | -0.78 | -1.66 |
| 0.70-0.75 | 3,336 | 0.724 | 0.721 | 0.26 | -0.58 | -1.46 |
| 0.75-0.80 | 2,461 | 0.773 | 0.787 | 1.10 | 0.27 | -0.61 |
| 0.80-0.85 | 1,709 | 0.824 | 0.847 | -0.09 | -0.93 | -1.80 |
| 0.85-0.90 | 1,275 | 0.874 | 0.905 | -0.42 | -1.26 | -2.13 |
| 0.90-0.95 | 900 | 0.924 | 0.968 | -0.93 | -1.76 | -2.64 |
| 0.95-1.00 | 939 | 0.980 | 0.989 | -1.06 | -1.89 | -2.76 |

## Cost-Breakpoint Distribution

| Metric | Value |
|--------|-------|
| Mean | 0.07 pip |
| Median | 0.10 pip |
| 10th percentile | -21.10 pip |
| 25th percentile | -9.10 pip |
| 75th percentile | 9.50 pip |
| 90th percentile | 21.30 pip |
| % surviving 0.5 pip | 48.7% |
| % surviving 0.75 pip | 48.0% |
| % surviving 1.0 pip | 47.1% |
| % surviving 1.5 pip | 45.6% |
| % surviving 2.0 pip | 44.0% |

## Pair Selection Without Look-Ahead

| Rule | OOS Trades | Mean Return | Net Exp (LOW) | Net Exp (BASE) | PF | Max DD |
|------|-----------|-------------|---------------|----------------|----|--------|
| all_pairs | 15,394 | 0.08 | -0.75 | -1.63 | 1.01 | 3309.9 |
| positive_exp | 8,017 | 0.21 | -0.64 | -1.52 | 1.02 | 2500.8 |
| be_gte_05 | 4,726 | 0.53 | -0.36 | -1.27 | 1.05 | 2607.4 |
| be_gte_075 | 4,479 | 0.54 | -0.34 | -1.26 | 1.05 | 2607.4 |
| be_gte_10 | 3,597 | 0.38 | -0.50 | -1.42 | 1.04 | 1851.7 |

## Regime-Conditional Performance

| Condition | N | Mean Return | Win Rate | PF |
|-----------|---|-------------|----------|----|
| vol_low_vol | 4,928 | -0.31 | 0.483 | 0.93 |
| vol_mid_vol | 5,272 | 0.25 | 0.505 | 1.03 |
| vol_high_vol | 5,194 | 0.29 | 0.526 | 1.03 |
| trend_weak_trend | 5,365 | -0.25 | 0.490 | 0.96 |
| trend_mid_trend | 5,230 | -0.06 | 0.504 | 0.99 |
| trend_strong_trend | 4,799 | 0.60 | 0.523 | 1.06 |
| session_london | 8,191 | 0.17 | 0.508 | 1.02 |
| session_overlap | 6,145 | 0.38 | 0.505 | 1.04 |
| session_new_york | 1,058 | -2.27 | 0.476 | 0.78 |

## Economic vs Classification Information

- Corr(P(fast), return): -0.0020 (p=0.5054)
- Spearman(P(fast), return): 0.0017 (p=0.5546)
- Corr(P(fast), |return|): 0.0578 (p=0.0000)

## Multiple-Testing Control

- Estimated subgroup tests: ~271
- Bonferroni-adjusted alpha: 0.000185

## Final Classification

### A. NO ECONOMIC STRUCTURE FOUND

- Profitable pair×threshold combinations: 7/171
- Research decision: NO — stop this research branch
