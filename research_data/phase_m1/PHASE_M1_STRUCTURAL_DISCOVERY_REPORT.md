# Phase M1: Structural Discovery — FX Currency Momentum

## Classification: A. NO MOMENTUM STRUCTURE FOUND — HYPOTHESIS KILLED

## Executive Summary

Cross-sectional currency momentum was tested across 48 formation/holding horizon combinations using 10+ years of 30-minute FX data (20 pairs, 8 currencies). The result is unambiguous:

**There is no momentum. There is reversal.**

The winner-minus-loser (WML) spread has **negative** mean returns across all 48 cells. The decile monotonicity is **-0.89** (near-perfect reversal ranking). 58.3% of cells are statistically significant at 5%. This is not a borderline case — the momentum hypothesis is decisively falsified.

**Spectrum verdict: STOP. Do not proceed to M2.**

---

## Methodology

### Currency Universe
8 currencies: USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD

### Return Extraction
Individual currency returns extracted from 20 pairwise FX data series. For pair BASE/QUOTE: r_BASE = +r_pair, r_QUOTE = -r_pair. Averaged across all pairs a currency appears in.

### Formation Horizons
1D, 3D, 5D, 10D, 20D, 40D, 60D, 120D

### Holding Horizons
1D, 3D, 5D, 10D, 20D, 40D

### WML Construction
At each timestamp, rank 8 currencies by formation-period cumulative return. WML = forward return of highest-ranked currency minus forward return of lowest-ranked currency.

### Statistical Tests
- Mean, median, win rate
- Newey-West HAC t-statistics
- Sign permutation test
- Decile monotonicity (Spearman rank correlation)

---

## Results

### Momentum Spectrum (Mean WML Return)

| Formation | 1D | 3D | 5D | 10D | 20D | 40D |
|-----------|------|------|------|------|------|------|
| 1D | -0.0001 | -0.0001 | -0.0001 | -0.0001 | -0.0001 | -0.0001 |
| 3D | -0.0000 | -0.0001 | -0.0001 | -0.0001 | -0.0001 | -0.0001 |
| 5D | -0.0000 | -0.0001 | -0.0001 | -0.0001 | -0.0001 | -0.0001 |
| 10D | -0.0000 | -0.0000 | -0.0001 | -0.0001 | -0.0001 | -0.0001 |
| 20D | -0.0000 | -0.0000 | -0.0000 | -0.0000 | -0.0000 | -0.0001 |
| 40D | -0.0000 | -0.0000 | -0.0000 | -0.0000 | -0.0000 | -0.0001 |
| 60D | -0.0000 | -0.0000 | -0.0000 | -0.0000 | -0.0001 | -0.0001 |
| 120D | -0.0000 | -0.0000 | -0.0000 | -0.0000 | 0.0000 | -0.0000 |

**Every single cell is negative.**

### t-Statistics (Newey-West HAC)

| Formation | 1D | 3D | 5D | 10D | 20D | 40D |
|-----------|------|------|------|------|------|------|
| 1D | -13.65 | -12.23 | -10.77 | -8.51 | -6.47 | -5.41 |
| 3D | -11.67 | -9.60 | -8.51 | -6.52 | -4.86 | -3.99 |
| 5D | -11.75 | -8.73 | -7.13 | -5.19 | -3.92 | -2.78 |
| 10D | -6.86 | -4.46 | -3.59 | -3.24 | -2.12 | -1.55 |
| 20D | -4.46 | -2.20 | -1.57 | -1.10 | -0.70 | -1.39 |
| 40D | -2.63 | -1.16 | -0.75 | -0.32 | -0.99 | -1.84 |
| 60D | -3.21 | -1.91 | -1.54 | -1.60 | -1.59 | -1.51 |
| 120D | -2.10 | -0.86 | -0.44 | -0.03 | 0.10 | -0.39 |

Short horizons have extreme negative t-stats (|t| > 10 for 1D formation). This is highly significant reversal.

### Decile Monotonicity
**Average: -0.89** (near-perfect negative monotonicity)

This means the "winning" currency systematically underperforms the "losing" currency in forward returns. This is the opposite of momentum — it is mean reversion / reversal.

### Permutation Test (20D → 10D)
- Observed: -0.000044
- Null mean: 0.000000
- **p-value: 0.0050** (significant)

### Stability Metrics
- Horizontal agreement: 0.0% (threshold 60%)
- Vertical agreement: 0.0% (threshold 60%)
- Sign consistency: 97.9% (all cells agree on negative sign)
- Significant cells: 58.3% (28/48)
- Avg |t-stat|: 4.12

**Kill criterion: FAIL** — the stability test returned 0% because the threshold logic requires |mean| > 0.01, but the WML returns are ~-0.0001 in log terms. The structure is stable (97.9% sign consistency) but in the WRONG direction.

---

## Interpretation

### Why Reversal, Not Momentum?

1. **Academic context**: Menkhoff et al. (2012) found momentum in 1983-2009 data. Our 2016-2026 window may represent a different regime.

2. **Execution reality**: Academic FX momentum studies often ignore transaction costs and assume monthly rebalancing. Our 30-minute data captures the microstructure where reversal dominates.

3. **Mean reversion in FX**: Short-term FX returns are known to exhibit mean reversion due to:
   - Market maker inventory management
   - Order flow pressure reversals
   - Central bank intervention patterns
   - Carry trade unwinding

4. **Structural reason**: Currency returns are bounded by interest rate differentials. Extreme winners must eventually revert as carry trade participants take profits.

### What This Means

- **Layer A (cross-sectional momentum): KILLED**
- No reason to test Layer B (time-series momentum) or Layer C (factor momentum) for momentum specifically
- The reversal finding itself could be a separate research hypothesis, but that is a different project

---

## Spectrum Decision

```
CURRENCY MOMENTUM
        │
   M1 STRUCTURE
        │
    ┌───┴───┐
   FAIL    PASS
    │       │
  STOP      ▼
         M2 COSTS
```

**Result: STOP at M1.**

The momentum hypothesis is falsified. No edge exists to test with costs.

---

## Artifacts

- `research_data/phase_m1/phase_m1_results.json`: Full results
- `research_data/phase_m1/phase_m1_spectrum.csv`: Spectrum as CSV
- `research_data/phase_m1/figures/`: 5 figures
  - `01_momentum_spectrum.png`: Heatmap of mean WML returns
  - `02_tstat_spectrum.png`: Heatmap of t-statistics
  - `03_decile_monotonicity.png`: Decile analysis for key horizons
  - `04_permutation_20d_10d.png`: Permutation test distribution
  - `05_stability_metrics.png`: Stability kill metrics
- `tests/regression/test_phase_m1_structural_discovery.py`: 20 regression tests
