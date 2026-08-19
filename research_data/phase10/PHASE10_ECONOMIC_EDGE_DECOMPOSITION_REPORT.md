# Phase 10: Economic Edge Decomposition Report

## Executive Summary

**Classification: A. NO SIGNAL**

- Gross edge: 0.08 pip
- Net edge (after costs): -1.57 pip
- Median break-even cost: 0.67 pip
- AUC: 0.6245
- Permutation p-value: 0.4780

## Implementation Audit

- pip_value(EUR/USD): $10.00
- pip_value(USD/JPY): $6.70
- Forward returns: actual pips
- Cost pair-specific: Yes
- Status: CORRECTED

## Edge Distribution

### By Outcome Class

| Class | N | Mean | Median | Win Rate | Mean Win | Mean Loss | Payoff |
|-------|---|------|--------|----------|----------|-----------|--------|
| fast_mr | 56,944 | 0.20 | 0.10 | 0.501 | 14.87 | -14.59 | 1.02 |
| slow_mr | 53,272 | -0.07 | 0.20 | 0.505 | 13.30 | -13.79 | 0.96 |

## Edge Concentration

Top 3 pairs contribute: 205.2% of total PnL

### By Year

| Year | N | Total PnL | Mean Return |
|------|---|-----------|-------------|
| 2021 | 21,578 | -1455 | -0.07 |
| 2022 | 21,090 | 303 | 0.01 |
| 2023 | 20,839 | 9475 | 0.45 |
| 2024 | 20,450 | -4586 | -0.22 |
| 2025 | 19,593 | 6250 | 0.32 |
| 2026 | 10,780 | -1678 | -0.16 |

## Cost Breakpoint Analysis

| Metric | Value |
|--------|-------|
| Mean break-even | 0.68 pip |
| Median break-even | 0.67 pip |
| 25th percentile | 0.54 pip |
| 75th percentile | 0.90 pip |
| Min | 0.17 pip |
| Max | 1.19 pip |

## Expectancy Decomposition (P>=0.65)

| Component | Value |
|-----------|-------|
| N trades | 15,394 |
| P(win) | 0.505 |
| P(loss) | 0.492 |
| Avg win | 15.88 pip |
| Avg loss | -16.14 pip |
| Win contribution | 8.018 |
| Loss contribution | 7.936 |
| E[R] | 0.082 |

## Signal Monotonicity

| Decile | N | Mean Pred P | Actual Fast Rate | Mean Return | Net Exp (1pip cost) |
|--------|---|-------------|------------------|-------------|---------------------|
| 1 | 11,433 | 0.386 | 0.372 | 0.20 | -1.45 |
| 2 | 11,433 | 0.407 | 0.389 | -0.02 | -1.67 |
| 3 | 11,433 | 0.423 | 0.408 | 0.06 | -1.59 |
| 4 | 11,433 | 0.441 | 0.421 | 0.17 | -1.48 |
| 5 | 11,433 | 0.463 | 0.443 | -0.21 | -1.86 |
| 6 | 11,433 | 0.488 | 0.468 | 0.09 | -1.56 |
| 7 | 11,433 | 0.521 | 0.493 | 0.22 | -1.43 |
| 8 | 11,433 | 0.567 | 0.543 | 0.27 | -1.38 |
| 9 | 11,433 | 0.638 | 0.628 | -0.17 | -1.82 |
| 10 | 11,433 | 0.801 | 0.815 | 0.12 | -1.53 |

## Cross-Pair Economic Heterogeneity

| Pair | N | Mean Return | Win Rate | BE Cost | PF | Max DD |
|------|---|-------------|----------|---------|----|--------|
| USD/JPY | 5,543 | 1.19 | 0.542 | 1.19 | 1.14 | 2216.1 |
| GBP/JPY | 5,766 | 0.99 | 0.532 | 0.99 | 1.08 | 2365.2 |
| GBP/AUD | 5,106 | 0.87 | 0.498 | 0.87 | 1.09 | 1938.9 |
| CAD/JPY | 6,056 | 0.68 | 0.528 | 0.68 | 1.10 | 1442.7 |
| EUR/AUD | 5,084 | 0.66 | 0.498 | 0.66 | 1.07 | 1514.7 |
| GBP/CAD | 7,576 | 0.63 | 0.509 | 0.63 | 1.07 | 2077.5 |
| EUR/USD | 7,045 | 0.27 | 0.506 | 0.27 | 1.04 | 2485.5 |
| GBP/USD | 7,101 | 0.17 | 0.503 | 0.17 | 1.02 | 3322.8 |
| EUR/GBP | 7,324 | -0.04 | 0.487 | 0.00 | 0.99 | 1345.2 |
| EUR/CAD | 7,644 | -0.05 | 0.497 | 0.00 | 0.99 | 2187.2 |
| AUD/CAD | 5,336 | -0.26 | 0.503 | 0.00 | 0.95 | 2329.7 |
| AUD/USD | 5,383 | -0.31 | 0.501 | 0.00 | 0.94 | 3158.5 |
| EUR/CHF | 6,985 | -0.34 | 0.488 | 0.00 | 0.93 | 2684.6 |
| AUD/JPY | 4,906 | -0.40 | 0.511 | 0.00 | 0.95 | 4384.7 |
| NZD/CHF | 5,022 | -0.41 | 0.489 | 0.00 | 0.90 | 2496.7 |
| USD/CHF | 7,021 | -0.44 | 0.495 | 0.00 | 0.93 | 3544.9 |
| NZD/USD | 5,456 | -0.55 | 0.490 | 0.00 | 0.90 | 4059.8 |
| AUD/CHF | 5,168 | -0.73 | 0.486 | 0.00 | 0.84 | 4324.6 |
| NZD/JPY | 4,808 | -0.78 | 0.499 | 0.00 | 0.88 | 5135.2 |

## Temporal Stability

### 6-Month Rolling Windows

| Period | N | Mean Return | Win Rate | PF | BE Cost |
|--------|---|-------------|----------|----|---------|
| 2021-01-04–2021-07-04 | 11,010 | 0.08 | 0.507 | 1.01 | 0.08 |
| 2021-02-04–2021-08-04 | 10,897 | 0.01 | 0.500 | 1.00 | 0.01 |
| 2021-03-04–2021-09-04 | 10,846 | -0.05 | 0.500 | 0.99 | 0.00 |
| 2021-04-04–2021-10-04 | 10,700 | -0.13 | 0.496 | 0.98 | 0.00 |
| 2021-05-04–2021-11-04 | 10,869 | -0.24 | 0.495 | 0.96 | 0.00 |
| 2021-06-04–2021-12-04 | 10,629 | -0.64 | 0.488 | 0.90 | 0.00 |
| 2021-07-04–2022-01-04 | 10,682 | -0.24 | 0.498 | 0.96 | 0.00 |
| 2021-08-04–2022-02-04 | 10,992 | -0.26 | 0.497 | 0.96 | 0.00 |
| 2021-09-04–2022-03-04 | 10,889 | -0.55 | 0.489 | 0.92 | 0.00 |
| 2021-10-04–2022-04-04 | 11,115 | -0.33 | 0.493 | 0.95 | 0.00 |
| 2021-11-04–2022-05-04 | 10,696 | -0.49 | 0.486 | 0.93 | 0.00 |
| 2021-12-04–2022-06-04 | 10,739 | -0.02 | 0.497 | 1.00 | 0.00 |
| 2022-01-04–2022-07-04 | 10,415 | -0.09 | 0.491 | 0.99 | 0.00 |
| 2022-02-04–2022-08-04 | 10,151 | -0.13 | 0.492 | 0.99 | 0.00 |
| 2022-03-04–2022-09-04 | 10,281 | 0.22 | 0.501 | 1.02 | 0.22 |
| 2022-04-04–2022-10-04 | 9,985 | 0.25 | 0.501 | 1.03 | 0.25 |
| 2022-05-04–2022-11-04 | 10,396 | 0.43 | 0.505 | 1.04 | 0.43 |
| 2022-06-04–2022-12-04 | 10,492 | 0.36 | 0.501 | 1.04 | 0.36 |
| 2022-07-04–2023-01-04 | 10,684 | 0.12 | 0.498 | 1.01 | 0.12 |
| 2022-08-04–2023-02-04 | 10,808 | 0.13 | 0.499 | 1.01 | 0.13 |

## Randomization Controls

| Metric | Value |
|--------|-------|
| Observed expectancy | 0.0822 pip |
| Null mean | 0.0699 pip |
| Null std | 0.1611 pip |
| 95% null CI | [-0.2469, 0.3790] |
| Permutation p | 0.4780 |
| Label-shuffle p | 0.4230 |

## Multiple-Testing Warning

- Estimated tests: ~50
- Bonferroni alpha: 0.0010
- Permutation p: 0.4780
- Significant after Bonferroni: NO

## Classification vs Trading Performance

| Metric | Value |
|--------|-------|
| AUC | 0.6245 |
| Accuracy | 0.5864 |
| Precision | 0.6224 |
| Recall | 0.5071 |
| Fast MR mean return | 0.20 pip |
| Slow MR mean return | -0.07 pip |
| Fast-Slow spread | 0.27 pip |

## Economic Significance Questions

| Question | Answer |
|----------|--------|
| Q1: Predicts direction? | YES |
| Q2: Positive gross expectancy? | YES |
| Q3: Survives costs? | NO |
| Q4: Stable across time? | YES |
| Q5: Stable across pairs? | NO |
| Q6: Concentrated? | YES |
| Q7: Distinguishable from null? | NO |
| Q8: Justify next phase? | YES |

## Final Classification

### A. NO SIGNAL

Classification criteria:
- **A. NO SIGNAL**: AUC < 0.52 or permutation p > 0.20
- **B. PREDICTIVE BUT ECONOMICALLY USELESS**: AUC > 0.55 but net < 0 after costs
- **C. WEAK ECONOMIC EDGE**: net > 0 but < 0.5 pip, break-even < 1.0 pip
- **D. ROBUST ECONOMIC EDGE**: net > 0.5 pip, stable across time/pairs
- **E. STRONG ECONOMIC EDGE**: net > 1.0 pip, stable, high PF

- Gross edge: 0.08 pip
- Net edge: -1.57 pip
- Break-even cost: 0.67 pip
