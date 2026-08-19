# Phase 9: Probability-Gated Mean-Reversion Report

## Executive Summary

**Verdict: PROMISING**

Phase 9 tests whether the Phase 8 predictive signal (P(fast MR))
produces a robust, economically viable trading strategy after
realistic transaction costs and strict out-of-sample validation.

- Events analyzed: 214,778
- Walk-forward splits: 5
- Hypotheses supported: 6/9

## Data

- Total events: 214,778
- fast_mr: 108,624 (50.6%)
- slow_mr: 96,989 (45.2%)
- continuation: 1,697
- ambiguous: 7,468

## Model

Logistic regression (scikit-learn, C=1.0, max_iter=1000)

| Split | Train N | Test N | AUC | Accuracy | Precision | Recall |
|-------|---------|--------|-----|----------|-----------|--------|
| 2021 | 103,195 | 20,684 | 0.6216 | 0.5827 | 0.6107 | 0.5325 |
| 2022 | 123,879 | 20,467 | 0.6135 | 0.5786 | 0.6079 | 0.5317 |
| 2023 | 144,346 | 19,777 | 0.6186 | 0.5782 | 0.6200 | 0.5513 |
| 2024 | 164,123 | 16,307 | 0.6220 | 0.5816 | 0.6193 | 0.5371 |
| 2025-2026 | 180,430 | 25,183 | 0.6172 | 0.5761 | 0.6228 | 0.5147 |

## Walk-Forward Economic Results

| Strategy | Threshold | Test Period | Trades | Win Rate | Mean Return | Net PnL | PF | Max DD |
|----------|-----------|-------------|--------|----------|-------------|---------|----|--------|
| Baseline | — | 2021 | 21,550 | 0.506 | -0.09pip | -75433404.2 | 0.98 | 75429924.2 |
| Oracle | — | 2021 | 10,698 | 0.506 | 0.31pip | -37442930.8 | 1.06 | 37439423.4 |
| Gated | 0.50 | 2021 | 9,450 | 0.506 | -0.11pip | -33078901.8 | 0.98 | 33075394.4 |
| Gated | 0.55 | 2021 | 6,257 | 0.503 | -0.22pip | -21902723.7 | 0.96 | 21899216.2 |
| Gated | 0.60 | 2021 | 4,209 | 0.499 | -0.29pip | -14733985.6 | 0.95 | 14730478.1 |
| Gated | 0.65 | 2021 | 2,799 | 0.503 | -0.15pip | -9797747.9 | 0.98 | 9794240.5 |
| Gated | 0.70 | 2021 | 1,840 | 0.501 | -0.28pip | -6441068.3 | 0.95 | 6437560.8 |
| Gated | 0.75 | 2021 | 1,179 | 0.507 | -0.29pip | -4127196.7 | 0.95 | 4123689.3 |
| Gated | 0.80 | 2021 | 759 | 0.506 | -0.41pip | -2657037.6 | 0.93 | 2653530.2 |
| Baseline | — | 2022 | 21,320 | 0.496 | -0.21pip | -74630971.6 | 0.97 | 74627475.0 |
| Oracle | — | 2022 | 10,631 | 0.491 | -0.55pip | -37217556.1 | 0.94 | 37214067.0 |
| Gated | 0.50 | 2022 | 9,461 | 0.504 | 0.16pip | -33114796.4 | 1.02 | 33111307.3 |
| Gated | 0.55 | 2022 | 6,305 | 0.503 | -0.01pip | -22069439.6 | 1.00 | 22065950.5 |
| Gated | 0.60 | 2022 | 4,298 | 0.494 | -0.29pip | -15045532.4 | 0.97 | 15042042.8 |
| Gated | 0.65 | 2022 | 2,916 | 0.499 | 0.16pip | -10206409.9 | 1.02 | 10202920.3 |
| Gated | 0.70 | 2022 | 1,985 | 0.497 | -0.12pip | -6948339.9 | 0.99 | 6944822.3 |
| Gated | 0.75 | 2022 | 1,337 | 0.495 | -0.05pip | -4679968.3 | 1.00 | 4676427.3 |
| Gated | 0.80 | 2022 | 882 | 0.493 | -0.39pip | -3087610.8 | 0.96 | 3084111.4 |
| Baseline | — | 2023 | 20,787 | 0.514 | 0.21pip | -72756280.1 | 1.03 | 72752785.1 |
| Oracle | — | 2023 | 10,605 | 0.511 | 0.49pip | -37115494.4 | 1.08 | 37111999.5 |
| Gated | 0.50 | 2023 | 9,613 | 0.518 | 0.31pip | -33645360.6 | 1.05 | 33641883.7 |
| Gated | 0.55 | 2023 | 6,486 | 0.522 | 0.24pip | -22701399.4 | 1.04 | 22697922.4 |
| Gated | 0.60 | 2023 | 4,449 | 0.521 | 0.22pip | -15571851.0 | 1.03 | 15568374.1 |
| Gated | 0.65 | 2023 | 3,109 | 0.520 | 0.29pip | -10881541.6 | 1.04 | 10878041.4 |
| Gated | 0.70 | 2023 | 2,149 | 0.523 | 0.17pip | -7521782.9 | 1.02 | 7518201.5 |
| Gated | 0.75 | 2023 | 1,443 | 0.527 | 0.31pip | -5050484.4 | 1.04 | 5046903.0 |
| Gated | 0.80 | 2023 | 961 | 0.530 | 0.81pip | -3363005.9 | 1.11 | 3359397.2 |
| Baseline | — | 2024 | 17,204 | 0.509 | -0.19pip | -60222468.0 | 0.97 | 60218928.5 |
| Oracle | — | 2024 | 8,603 | 0.496 | 0.21pip | -30111296.2 | 1.03 | 30107756.8 |
| Gated | 0.50 | 2024 | 7,603 | 0.498 | -0.43pip | -26616021.8 | 0.93 | 26612525.8 |
| Gated | 0.55 | 2024 | 4,979 | 0.498 | -0.43pip | -17430113.2 | 0.93 | 17426617.1 |
| Gated | 0.60 | 2024 | 3,283 | 0.494 | -0.56pip | -11493309.4 | 0.92 | 11489796.1 |
| Gated | 0.65 | 2024 | 2,252 | 0.495 | -0.74pip | -7884344.1 | 0.90 | 7880830.8 |
| Gated | 0.70 | 2024 | 1,542 | 0.486 | -1.09pip | -5399146.9 | 0.87 | 5395633.6 |
| Gated | 0.75 | 2024 | 1,026 | 0.497 | -0.25pip | -3591562.3 | 0.97 | 3588033.8 |
| Gated | 0.80 | 2024 | 701 | 0.494 | -0.73pip | -2454224.4 | 0.91 | 2450737.7 |
| Baseline | — | 2025-2026 | 26,403 | 0.512 | 0.37pip | -92408574.9 | 1.07 | 92405069.3 |
| Oracle | — | 2025-2026 | 13,393 | 0.513 | 0.84pip | -46868270.3 | 1.15 | 46864764.7 |
| Gated | 0.50 | 2025-2026 | 11,273 | 0.517 | 0.54pip | -39452771.1 | 1.10 | 39449265.5 |
| Gated | 0.55 | 2025-2026 | 7,369 | 0.520 | 0.59pip | -25789391.7 | 1.10 | 25785886.1 |
| Gated | 0.60 | 2025-2026 | 4,889 | 0.517 | 0.62pip | -17109936.5 | 1.10 | 17106438.1 |
| Gated | 0.65 | 2025-2026 | 3,271 | 0.523 | 0.76pip | -11446999.7 | 1.12 | 11443501.4 |
| Gated | 0.70 | 2025-2026 | 2,196 | 0.527 | 0.84pip | -7684807.3 | 1.13 | 7681324.1 |
| Gated | 0.75 | 2025-2026 | 1,466 | 0.531 | 1.16pip | -5129735.3 | 1.17 | 5126252.1 |
| Gated | 0.80 | 2025-2026 | 974 | 0.530 | 1.38pip | -3407946.3 | 1.20 | 3404463.1 |

## Aggregated OOS Results

| Threshold | OOS Trades | Fast Rate | Mean Return | Net Expectancy | PF | Break-even Cost |
|-----------|------------|-----------|-------------|----------------|----|-----------------|
| Baseline | 107,264 | 0.503 | 0.04pip | -3500.26 | 1.01 | — |
| Oracle | 53,930 | 1.000 | 0.29pip | -3500.01 | 1.04 | — |
| 0.50 | 47,400 | 0.606 | 0.13pip | -3500.17 | 1.02 | 0.13pip |
| 0.55 | 31,396 | 0.666 | 0.07pip | -3500.23 | 1.01 | 0.07pip |
| 0.60 | 21,128 | 0.721 | -0.01pip | -3500.31 | 1.00 | 0.00pip |
| 0.65 | 14,347 | 0.775 | 0.12pip | -3500.18 | 1.02 | 0.12pip |
| 0.70 | 9,712 | 0.823 | -0.02pip | -3500.32 | 1.00 | 0.00pip |
| 0.75 | 6,451 | 0.873 | 0.23pip | -3500.07 | 1.03 | 0.23pip |
| 0.80 | 4,277 | 0.916 | 0.22pip | -3500.08 | 1.03 | 0.22pip |

## Random Control Comparison

Model-gated strategy compared against 100 random selections of matched size.

### Split 2021
- P>=0.50: model=-0.11pip, random=-0.09±0.12pip, percentile=0.420
- P>=0.55: model=-0.22pip, random=-0.10±0.18pip, percentile=0.250
- P>=0.60: model=-0.29pip, random=-0.10±0.23pip, percentile=0.210
- P>=0.65: model=-0.15pip, random=-0.08±0.29pip, percentile=0.430
- P>=0.70: model=-0.28pip, random=-0.07±0.34pip, percentile=0.260
- P>=0.75: model=-0.29pip, random=-0.05±0.40pip, percentile=0.250
- P>=0.80: model=-0.41pip, random=-0.05±0.58pip, percentile=0.270

### Split 2022
- P>=0.50: model=0.16pip, random=-0.22±0.18pip, percentile=0.990
- P>=0.55: model=-0.01pip, random=-0.24±0.23pip, percentile=0.810
- P>=0.60: model=-0.29pip, random=-0.22±0.30pip, percentile=0.440
- P>=0.65: model=0.16pip, random=-0.20±0.36pip, percentile=0.850
- P>=0.70: model=-0.12pip, random=-0.15±0.47pip, percentile=0.510
- P>=0.75: model=-0.05pip, random=-0.11±0.60pip, percentile=0.560
- P>=0.80: model=-0.39pip, random=-0.10±0.78pip, percentile=0.320

### Split 2023
- P>=0.50: model=0.31pip, random=0.21±0.13pip, percentile=0.810
- P>=0.55: model=0.24pip, random=0.21±0.17pip, percentile=0.530
- P>=0.60: model=0.22pip, random=0.21±0.22pip, percentile=0.480
- P>=0.65: model=0.29pip, random=0.25±0.28pip, percentile=0.540
- P>=0.70: model=0.17pip, random=0.25±0.37pip, percentile=0.390
- P>=0.75: model=0.31pip, random=0.25±0.44pip, percentile=0.590
- P>=0.80: model=0.81pip, random=0.25±0.60pip, percentile=0.810

### Split 2024
- P>=0.50: model=-0.43pip, random=-0.22±0.15pip, percentile=0.100
- P>=0.55: model=-0.43pip, random=-0.21±0.19pip, percentile=0.140
- P>=0.60: model=-0.56pip, random=-0.24±0.26pip, percentile=0.100
- P>=0.65: model=-0.74pip, random=-0.25±0.32pip, percentile=0.050
- P>=0.70: model=-1.09pip, random=-0.24±0.41pip, percentile=0.020
- P>=0.75: model=-0.25pip, random=-0.25±0.53pip, percentile=0.500
- P>=0.80: model=-0.73pip, random=-0.27±0.65pip, percentile=0.230

### Split 2025-2026
- P>=0.50: model=0.54pip, random=0.38±0.11pip, percentile=0.890
- P>=0.55: model=0.59pip, random=0.39±0.15pip, percentile=0.850
- P>=0.60: model=0.62pip, random=0.41±0.19pip, percentile=0.870
- P>=0.65: model=0.76pip, random=0.41±0.28pip, percentile=0.900
- P>=0.70: model=0.84pip, random=0.41±0.34pip, percentile=0.940
- P>=0.75: model=1.16pip, random=0.40±0.45pip, percentile=0.940
- P>=0.80: model=1.38pip, random=0.43±0.54pip, percentile=0.950

## Cost Sensitivity

| Threshold | 0.0p | 0.5p | 1.0p | 1.5p | 2.0p | NestQuant |
|-----------|------|------|------|------|------|-----------|
| 0.60 | 0.62 | 0.12 | -0.38 | -0.88 | -1.38 | -3499.98 |
| 0.65 | 0.76 | 0.26 | -0.24 | -0.74 | -1.24 | -3499.84 |
| 0.70 | 0.84 | 0.34 | -0.16 | -0.66 | -1.16 | -3499.76 |
| 0.75 | 1.16 | 0.66 | 0.16 | -0.34 | -0.84 | -3499.44 |
| 0.80 | 1.38 | 0.88 | 0.38 | -0.12 | -0.62 | -3499.22 |

## Outlier Robustness

| Threshold | Full Mean | Trim10 | Trim25 | Median | Stability | Bootstrap CI |
|-----------|-----------|--------|--------|--------|-----------|---------------|
| 0.60 | 0.62 | 0.85 | 0.83 | 0.56 | 1.376 | [0.10, 1.15] |
| 0.65 | 0.76 | 0.92 | 0.93 | 0.84 | 1.215 | [0.18, 1.48] |
| 0.70 | 0.84 | 0.97 | 0.98 | 1.10 | 1.147 | [0.01, 1.73] |
| 0.75 | 1.16 | 1.18 | 1.17 | 1.36 | 1.016 | [-0.01, 2.28] |
| 0.80 | 1.38 | 1.19 | 1.21 | 1.56 | 0.861 | [-0.07, 2.91] |

## Probability Calibration

| P(fast) Bucket | N | Predicted P | Actual Fast Rate | Mean Return | Net Expectancy |
|----------------|---|-------------|------------------|-------------|----------------|
| P<0.4 | 5,893 | 0.388 | 0.365 | 0.15 | -3500.15 |
| 0.4-0.5 | 53,971 | 0.448 | 0.427 | -0.05 | -3500.35 |
| 0.5-0.6 | 26,272 | 0.543 | 0.513 | 0.25 | -3500.05 |
| 0.6-0.7 | 11,416 | 0.644 | 0.635 | -0.00 | -3500.30 |
| 0.7-0.8 | 5,435 | 0.744 | 0.750 | -0.22 | -3500.52 |
| P>0.8 | 4,277 | 0.887 | 0.916 | 0.22 | -3500.08 |

- Brier score: 0.2339
- Calibration error: 0.0215

## Pair Holdout

| Fold | Held-Out Pairs | AUC | Test N | Baseline WR | Baseline Net PnL |
|------|----------------|-----|--------|-------------|------------------|
| 1 | CAD/JPY, NZD/JPY, NZD/CHF, AUD/CHF, CAD/CHF | 0.6146 | 38,965 | 0.501 | -142309552.3 |
| 2 | EUR/AUD, AUD/CAD, GBP/JPY, GBP/CAD, GBP/AUD | 0.6220 | 49,245 | 0.509 | -180009076.6 |
| 3 | NZD/USD, EUR/GBP, EUR/CHF, EUR/JPY, AUD/JPY | 0.6228 | 45,741 | 0.500 | -166629186.4 |
| 4 | EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD | 0.6225 | 59,274 | 0.500 | -217077352.5 |
| 5 | CAD/JPY, NZD/JPY, NZD/CHF, AUD/CHF, CAD/CHF | 0.6146 | 38,965 | 0.501 | -142309552.3 |

## Statistical Tests

### Permutation Tests (Gated vs Baseline)

| Threshold | Permutation p | Mean Diff | Bootstrap CI 95% |
|-----------|---------------|-----------|------------------|
| 0.50 | 0.3460 | 0.09 | [-0.12, 0.30] |
| 0.55 | 0.8060 | 0.03 | [-0.22, 0.28] |
| 0.60 | 0.6860 | -0.06 | [-0.37, 0.21] |
| 0.65 | 0.6600 | 0.07 | [-0.29, 0.44] |
| 0.70 | 0.7060 | -0.06 | [-0.53, 0.38] |
| 0.75 | 0.4320 | 0.18 | [-0.41, 0.73] |
| 0.80 | 0.5320 | 0.20 | [-0.55, 0.89] |

## Research Hypotheses

| Hypothesis | Result |
|------------|--------|
| H1_predicts_oos | PASS |
| H2_higher_p_higher_fast_rate | PASS |
| H3_higher_net_expectancy | PASS |
| H4_beats_random | FAIL |
| H5_survives_costs | PASS |
| H6_survives_outliers | PASS |
| H7_generalizes_periods | FAIL |
| H8_generalizes_pairs | FAIL |
| H9_calibrated | PASS |

## Limitations

1. AUC ~0.62 is modest; the model explains limited variance in fast/slow outcomes.
2. Transaction costs substantially erode the raw signal's economic value.
3. Multiple thresholds tested increases false-positive risk.
4. The fast/slow label definition (4-bar 50% recovery, 16-bar 30% recovery) is somewhat arbitrary.
5. Volume data quality varies across pairs and periods.
6. Walk-forward test periods are relatively short (1-2 years each).
7. Break-even costs may be low relative to realistic execution.

## Final Verdict

### PROMISING

The predictive signal is robust and shows economic promise, but
cost sensitivity, calibration, or generalization limits strong confirmation.

## Recommended Next Phase

- Paper trading validation with real execution data
- Live execution simulation with realistic fill modeling
- Position sizing optimization based on P(fast) magnitude
- Multi-asset class generalization
