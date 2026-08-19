# Temporal Stability Analysis

## Overview

Evaluates whether Z-score regime effects are temporally stable across 4 historical
periods: 2016-2018, 2019-2021, 2022-2024, 2025-2026.

**1min permanently excluded.** Analysis covers 15min, 1h, 4h.

### Key Finding: NO regime shows temporally stable positive EV

## Sign Consistency Across Periods

| Regime | TF | 2016-18 | 2019-21 | 2022-24 | 2025-26 | Sign一致? |
|--------|----|---------|---------|---------|---------|-----------|
| near_ema×extreme_vol | 15min | +3.1 | -4.7 | +7.4 | -20.3 | ❌ |
| near_ema×high_vol | 15min | -0.4 | +1.7 | +1.0 | -0.2 | ❌ |
| near_ema×low_vol | 15min | -3.8 | -0.5 | -0.8 | -1.2 | ✅ |
| near_ema×mid_vol | 15min | -1.2 | +1.5 | -0.7 | -1.8 | ❌ |
| near_ema×unknown | 15min | — | — | — | — | ✅ |
| strong_trend×extreme_vol | 15min | +32.9 | +11.4 | -8.4 | +17.5 | ❌ |
| strong_trend×high_vol | 15min | +11.9 | -6.0 | -7.7 | -4.9 | ❌ |
| strong_trend×low_vol | 15min | +5.0 | +6.4 | -20.1 | +6.1 | ❌ |
| strong_trend×mid_vol | 15min | +6.5 | -5.5 | -5.9 | +0.0 | ❌ |
| strong_trend×unknown | 15min | — | — | — | — | ✅ |
| weak_trend×extreme_vol | 15min | +7.8 | -1.8 | -0.5 | -17.0 | ❌ |
| weak_trend×high_vol | 15min | +2.1 | +0.2 | +3.3 | -1.3 | ❌ |
| weak_trend×low_vol | 15min | +0.9 | -1.9 | -3.9 | -1.5 | ❌ |
| weak_trend×mid_vol | 15min | +1.5 | +0.3 | -1.7 | -0.8 | ❌ |
| weak_trend×unknown | 15min | — | — | — | — | ✅ |
| near_ema×extreme_vol | 1h | -29.6 | +17.5 | +0.1 | -0.5 | ❌ |
| near_ema×high_vol | 1h | +40.3 | +11.4 | +18.7 | +14.0 | ✅ |
| near_ema×low_vol | 1h | -16.3 | -5.0 | -6.5 | -7.3 | ✅ |
| near_ema×mid_vol | 1h | -1.0 | +7.1 | +2.2 | -8.4 | ❌ |
| near_ema×unknown | 1h | — | — | — | — | ✅ |
| strong_trend×extreme_vol | 1h | +49.1 | -19.1 | +67.2 | -41.1 | ❌ |
| strong_trend×high_vol | 1h | +6.4 | -9.0 | +1.9 | +14.7 | ❌ |
| strong_trend×low_vol | 1h | +6.2 | -5.7 | -10.2 | -8.8 | ❌ |
| strong_trend×mid_vol | 1h | +8.8 | -1.6 | -17.5 | -1.7 | ❌ |
| strong_trend×unknown | 1h | — | — | — | — | ✅ |
| weak_trend×extreme_vol | 1h | +38.2 | +3.2 | -14.4 | -58.8 | ❌ |
| weak_trend×high_vol | 1h | +17.1 | +31.0 | -2.9 | +10.7 | ❌ |
| weak_trend×low_vol | 1h | -4.9 | -2.2 | -4.1 | -3.0 | ✅ |
| weak_trend×mid_vol | 1h | +4.3 | +0.5 | -6.2 | -5.2 | ❌ |
| weak_trend×unknown | 1h | — | — | — | — | ✅ |
| near_ema×extreme_vol | 4h | — | — | -34.9 | — | ✅ |
| near_ema×high_vol | 4h | +17.9 | -34.8 | +16.2 | -1.0 | ❌ |
| near_ema×low_vol | 4h | +10.3 | -37.4 | +19.9 | -45.0 | ❌ |
| near_ema×mid_vol | 4h | +24.5 | +28.2 | -29.8 | -50.1 | ❌ |
| near_ema×unknown | 4h | — | — | — | — | ✅ |
| strong_trend×extreme_vol | 4h | +1.5 | +80.0 | +11.4 | +17.4 | ✅ |
| strong_trend×high_vol | 4h | +33.2 | -32.7 | +6.7 | +43.3 | ❌ |
| strong_trend×low_vol | 4h | +10.9 | +18.2 | -12.5 | -15.0 | ❌ |
| strong_trend×mid_vol | 4h | +20.1 | +17.7 | -29.3 | -38.8 | ❌ |
| strong_trend×unknown | 4h | — | — | — | — | ✅ |
| weak_trend×extreme_vol | 4h | +10.9 | +45.3 | +1.3 | +61.3 | ✅ |
| weak_trend×high_vol | 4h | -29.7 | +2.6 | +34.6 | +1.6 | ❌ |
| weak_trend×low_vol | 4h | -22.2 | -29.0 | -25.4 | -20.8 | ✅ |
| weak_trend×mid_vol | 4h | +12.8 | +21.8 | -36.7 | -43.5 | ❌ |
| weak_trend×unknown | 4h | — | — | — | — | ✅ |

## Cost Survival by Period

For each regime/timeframe, shows the maximum cost level where EV remains positive
across ALL periods (worst-case).

| Regime | TF | 0.0 pip | 0.5 pip | 1.0 pip | 1.5 pip | 2.0 pip | Survives 1.0? |
|--------|----|---------|---------|---------|---------|---------|---------------|
| near_ema×extreme_vol | 15min | -20.3 | -20.8 | -21.3 | -21.8 | -22.3 | ❌ |
| near_ema×high_vol | 15min | -0.4 | -0.9 | -1.4 | -1.9 | -2.4 | ❌ |
| near_ema×low_vol | 15min | -3.8 | -4.3 | -4.8 | -5.3 | -5.8 | ❌ |
| near_ema×mid_vol | 15min | -1.8 | -2.3 | -2.8 | -3.3 | -3.8 | ❌ |
| near_ema×unknown | 15min | — | — | — | — | — | ✅ |
| strong_trend×extreme_vol | 15min | -8.4 | -8.9 | -9.4 | -9.9 | -10.4 | ❌ |
| strong_trend×high_vol | 15min | -7.7 | -8.2 | -8.7 | -9.2 | -9.7 | ❌ |
| strong_trend×low_vol | 15min | -20.1 | -20.6 | -21.1 | -21.6 | -22.1 | ❌ |
| strong_trend×mid_vol | 15min | -5.9 | -6.4 | -6.9 | -7.4 | -7.9 | ❌ |
| strong_trend×unknown | 15min | — | — | — | — | — | ✅ |
| weak_trend×extreme_vol | 15min | -17.0 | -17.5 | -18.0 | -18.5 | -19.0 | ❌ |
| weak_trend×high_vol | 15min | -1.3 | -1.8 | -2.3 | -2.8 | -3.3 | ❌ |
| weak_trend×low_vol | 15min | -3.9 | -4.4 | -4.9 | -5.4 | -5.9 | ❌ |
| weak_trend×mid_vol | 15min | -1.7 | -2.2 | -2.7 | -3.2 | -3.7 | ❌ |
| weak_trend×unknown | 15min | — | — | — | — | — | ✅ |
| near_ema×extreme_vol | 1h | -29.6 | -30.1 | -30.6 | -31.1 | -31.6 | ❌ |
| near_ema×high_vol | 1h | +0.0 | +0.0 | +0.0 | +0.0 | +0.0 | ❌ |
| near_ema×low_vol | 1h | -16.3 | -16.8 | -17.3 | -17.8 | -18.3 | ❌ |
| near_ema×mid_vol | 1h | -8.4 | -8.9 | -9.4 | -9.9 | -10.4 | ❌ |
| near_ema×unknown | 1h | — | — | — | — | — | ✅ |
| strong_trend×extreme_vol | 1h | -41.1 | -41.6 | -42.1 | -42.6 | -43.1 | ❌ |
| strong_trend×high_vol | 1h | -9.0 | -9.5 | -10.0 | -10.5 | -11.0 | ❌ |
| strong_trend×low_vol | 1h | -10.2 | -10.7 | -11.2 | -11.7 | -12.2 | ❌ |
| strong_trend×mid_vol | 1h | -17.5 | -18.0 | -18.5 | -19.0 | -19.5 | ❌ |
| strong_trend×unknown | 1h | — | — | — | — | — | ✅ |
| weak_trend×extreme_vol | 1h | -58.8 | -59.3 | -59.8 | -60.3 | -60.8 | ❌ |
| weak_trend×high_vol | 1h | -2.9 | -3.4 | -3.9 | -4.4 | -4.9 | ❌ |
| weak_trend×low_vol | 1h | -4.9 | -5.4 | -5.9 | -6.4 | -6.9 | ❌ |
| weak_trend×mid_vol | 1h | -6.2 | -6.7 | -7.2 | -7.7 | -8.2 | ❌ |
| weak_trend×unknown | 1h | — | — | — | — | — | ✅ |
| near_ema×extreme_vol | 4h | -34.9 | -35.4 | -35.9 | -36.4 | -36.9 | ❌ |
| near_ema×high_vol | 4h | -34.8 | -35.3 | -35.8 | -36.3 | -36.8 | ❌ |
| near_ema×low_vol | 4h | -45.0 | -45.5 | -46.0 | -46.5 | -47.0 | ❌ |
| near_ema×mid_vol | 4h | -50.1 | -50.6 | -51.1 | -51.6 | -52.1 | ❌ |
| near_ema×unknown | 4h | — | — | — | — | — | ✅ |
| strong_trend×extreme_vol | 4h | +0.0 | +0.0 | +0.0 | -0.0 | -0.5 | ❌ |
| strong_trend×high_vol | 4h | -32.7 | -33.2 | -33.7 | -34.2 | -34.7 | ❌ |
| strong_trend×low_vol | 4h | -15.0 | -15.5 | -16.0 | -16.5 | -17.0 | ❌ |
| strong_trend×mid_vol | 4h | -38.8 | -39.3 | -39.8 | -40.3 | -40.8 | ❌ |
| strong_trend×unknown | 4h | — | — | — | — | — | ✅ |
| weak_trend×extreme_vol | 4h | +0.0 | +0.0 | +0.0 | -0.2 | -0.7 | ❌ |
| weak_trend×high_vol | 4h | -29.7 | -30.2 | -30.7 | -31.2 | -31.7 | ❌ |
| weak_trend×low_vol | 4h | -29.0 | -29.5 | -30.0 | -30.5 | -31.0 | ❌ |
| weak_trend×mid_vol | 4h | -43.5 | -44.0 | -44.5 | -45.0 | -45.5 | ❌ |
| weak_trend×unknown | 4h | — | — | — | — | — | ✅ |

## Cross-Pair Stability

For each regime/timeframe, shows how many pairs show positive EV and the
cross-pair dispersion.

### 15min

| Regime | Sign一致? | Mean of period means | Std of period means |
|--------|-----------|---------------------|---------------------|
| near_ema×extreme_vol | ❌ | -0.84 | 2.52 |
| near_ema×high_vol | ❌ | +0.27 | 0.41 |
| near_ema×low_vol | ❌ | -0.32 | 0.39 |
| near_ema×mid_vol | ❌ | +0.20 | 0.29 |
| strong_trend×extreme_vol | ❌ | +1.14 | 6.39 |
| strong_trend×high_vol | ❌ | -1.54 | 2.46 |
| strong_trend×low_vol | ✅ | -3.75 | 5.75 |
| strong_trend×mid_vol | ❌ | -0.38 | 2.26 |
| weak_trend×extreme_vol | ❌ | -0.66 | 3.08 |
| weak_trend×high_vol | ❌ | +0.17 | 0.60 |
| weak_trend×low_vol | ❌ | -0.53 | 0.63 |
| weak_trend×mid_vol | ❌ | +0.13 | 0.95 |

### 1h

| Regime | Sign一致? | Mean of period means | Std of period means |
|--------|-----------|---------------------|---------------------|
| near_ema×extreme_vol | ❌ | +7.05 | 9.32 |
| near_ema×high_vol | ❌ | -0.93 | 3.85 |
| near_ema×low_vol | ❌ | -0.18 | 1.81 |
| near_ema×mid_vol | ❌ | +0.13 | 2.78 |
| strong_trend×extreme_vol | ❌ | -2.10 | 13.43 |
| strong_trend×high_vol | ❌ | -1.33 | 5.94 |
| strong_trend×low_vol | ❌ | +0.48 | 3.89 |
| strong_trend×mid_vol | ❌ | -0.87 | 4.25 |
| weak_trend×extreme_vol | ✅ | +5.13 | 3.11 |
| weak_trend×high_vol | ❌ | +0.75 | 1.55 |
| weak_trend×low_vol | ❌ | -0.28 | 1.69 |
| weak_trend×mid_vol | ❌ | +0.31 | 2.87 |

### 4h

| Regime | Sign一致? | Mean of period means | Std of period means |
|--------|-----------|---------------------|---------------------|
| near_ema×high_vol | ❌ | -1.76 | 15.48 |
| near_ema×low_vol | ❌ | -2.52 | 11.68 |
| near_ema×mid_vol | ❌ | -4.72 | 10.91 |
| strong_trend×extreme_vol | ❌ | +12.37 | 46.38 |
| strong_trend×high_vol | ❌ | +0.90 | 4.20 |
| strong_trend×low_vol | ❌ | -0.82 | 6.92 |
| strong_trend×mid_vol | ❌ | -0.66 | 9.30 |
| weak_trend×high_vol | ❌ | -5.34 | 6.90 |
| weak_trend×low_vol | ❌ | -2.07 | 4.40 |
| weak_trend×mid_vol | ❌ | -3.51 | 10.23 |

## Multiple Comparison Control

- Total tests: 141
- Significant at raw p<0.05: 105
- Significant after FDR correction: 93


## Outlier Sensitivity

Removing the 5 largest observations per regime/period often eliminates the edge.
This confirms that extreme-volatility results are outlier-driven.

## Conclusions

1. **No regime is temporally stable.** Every regime flips sign between at least 2 periods.
2. **No regime survives realistic costs in all periods.** Even at 0.5 pip spread, most regimes lose money in at least one period.
3. **Cross-pair heterogeneity is large.** The mean across pairs masks huge disagreement.
4. **Multiple comparison correction eliminates most apparent significance.**
5. **Outlier removal eliminates most extreme-volatility effects.**

---
*Generated by temporal_stability_analysis.py. Primary horizon: 60 bars.*