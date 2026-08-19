# Phase S4: Walk-Forward Validation + Parameter Sensitivity

**Date:** 2026-08-17
**Status: S4 PASSED — Edge is temporally stable, parameter-robust, and crisis-surviving**

---

## 1. Objective

Test whether the confirmed edge survives temporal variation, parameter perturbation, regime changes, and stress scenarios.

## 2. S4-A: Walk-Forward Rolling Out-of-Sample

17 rolling windows (2-year train, 6-month test, 6-month roll).

| Metric | Value |
|--------|-------|
| Windows | 17 |
| Positive | **17/17 (100%)** |
| Avg test PnL | +17.26 pip |
| Std test PnL | 6.87 pip |
| Min test PnL | +7.22 pip |
| Max test PnL | +31.21 pip |
| Avg retention | 97.0% |

**Every single test window is positive.** Worst window (+7.22 pip) still clears costs comfortably. Best window (COVID H1 2020) returned +31.21 pip.

## 3. S4-B: Parameter Neighborhood Sensitivity

All 5 parameters tested at ±20% and ±40% from frozen value.

| Parameter | CV | Positive/Total | Robust? |
|-----------|-----|----------------|---------|
| lookback | 0.013 | 5/5 | YES |
| sl_mult | 0.048 | 5/5 | YES |
| rrr | 0.010 | 5/5 | YES |
| max_hold_days | 0.022 | 5/5 | YES |
| breakeven_ratio | 0.029 | 5/5 | YES |

**All 25 parameter variants are profitable.** CV < 0.05 for all parameters. The edge is not fragile or over-fitted to specific parameter values.

## 4. S4-C: Regime-Conditioned Holdout

| Regime | Trades | WR | Avg PnL | PF |
|--------|--------|-----|---------|-----|
| Trending | 2,412 | 34.2% | +15.58 | 1.74 |
| Ranging | 12,909 | 35.9% | +18.97 | 2.07 |
| High Vol | 2,497 | 39.6% | +30.19 | 2.43 |
| Low Vol | 12,824 | 34.9% | +16.15 | 1.91 |

- All 4 regimes are profitable
- High volatility is the sweet spot (+30.19 pip, PF=2.43)
- Ranging markets dominate trade count (85% of trades)
- Trending is weakest but still positive (+15.58 pip)

## 5. S4-D: Stress Scenario Testing

| Period | Trades | WR | Avg PnL | PF |
|--------|--------|-----|---------|-----|
| COVID crash 2020 | 253 | 43.1% | +52.00 | 2.62 |
| Rate hike 2022 | 1,185 | 36.7% | +29.95 | 2.33 |
| Banking crisis 2023 | 332 | 36.4% | +17.46 | 1.93 |
| Volatility H1 2024 | 659 | 36.9% | +14.83 | 2.19 |
| Stable 2019 | 1,394 | 36.9% | +12.57 | 1.83 |
| Low vol 2017 | 1,432 | 38.6% | +20.67 | 2.15 |
| **COVID + severe costs** | **253** | **41.9%** | **+50.35** | **2.52** |

**All stress scenarios profitable.** COVID crash was the best period (+52 pip). Even under severe costs (2x spread, 0.4 pip slippage, $7 commission), COVID period retained +50.35 pip.

## 6. Cumulative Research Status

```
S0: Initial result           → Breakout looks profitable (1,002 trades, PF=5.32)
S1: Structural interrogation → Edge is robust, not an artifact (13/13 experiments)
S2: Mechanism identification → Volatility-adjusted displacement (17/17 tests)
S3: Independent validation  → Survives independent implementation + costs (15/15 tests)
S4: Walk-forward + stress    → Temporally stable, parameter-robust, crisis-surviving (30/30 tests)
```

**Total tests passing: 1115/1115**

## 7. Research Status

```
Status: S4 PASSED — Walk-forward robust, parameter-insensitive, crisis-surviving.
Edge confirmed across: 17 time windows, 25 parameter variants, 4 regimes, 6 stress periods.
```

## 8. Files

- Script: `scripts/phase_s4_walk_forward_sensitivity.py`
- Results: `research_data/simple_strategies/S4_walk_forward_sensitivity.json`
- Tests: `tests/regression/test_phase_s4_sensitivity.py` (30 tests, all pass)
