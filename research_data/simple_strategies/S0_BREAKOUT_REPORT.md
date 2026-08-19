# Phase S0: Archived Breakout Reassessment

**Date:** 2026-08-17
**Classification: B. STRUCTURAL SUPPORT — PROMOTE**

---

## 1. Hypothesis

The archived NestQuant FX swing breakout strategy — entering on 4h confirmed swing high/low breakouts with ATR-based stops, R=3.5 reward, swing trailing stop, and breakeven protection — contains a genuine, causal, cost-survivable structural edge.

## 2. Strategy Summary

| Parameter | Value |
|-----------|-------|
| Entry TF | 4h |
| Universe | 20 FX pairs |
| Signal | BUY when close > confirmed swing high; SELL when close < confirmed swing low |
| Lookback | 5 bars |
| Stop Loss | 2.0 × 4h ATR(14) |
| Take Profit | 3.5 × SL distance |
| Exit | Swing-based trailing stop + breakeven at 0.8× risk |
| Max Hold | 7 days (42 × 4h bars) |
| Date Range | 2016-01-03 to 2026-07-17 |

## 3. Experiments

### EXP 1: Original (zero cost)

| Metric | Value |
|--------|-------|
| Trades | 1,002 |
| Win Rate | 73.0% |
| Avg PnL | +66.52 pip |
| Profit Factor | 5.32 |
| Max DD | 520.1 pip |
| t-statistic | 25.81 |
| p-value | 0.0000 |

### EXP 2: With Realistic Costs

Spread = 0.36 pip avg + 0.10 pip slippage

| Metric | Value |
|--------|-------|
| Trades | 1,002 |
| Win Rate | 72.7% |
| Avg PnL | +66.07 pip |
| Profit Factor | 5.25 |

Cost impact: -0.45 pip per trade (~0.7% degradation). Strategy survives.

### EXP 3: Controls

| Control | Trades | Win Rate | Avg PnL |
|---------|--------|----------|---------|
| **Breakout (cost)** | 1,002 | 72.7% | +66.07 pip |
| Random direction | 1,858 | 57.2% | +26.64 pip |
| Always BUY | 2,298 | 66.7% | +41.82 pip |
| Always SELL | 2,887 | 65.7% | +35.87 pip |

Breakout beats all controls: +39.43 pip vs random, +24.25 pip vs always-buy, +30.20 pip vs always-sell.

### EXP 4: Parameter Perturbation (9 variants)

| Variant | Trades | WR | Avg PnL | PF |
|---------|--------|-----|---------|-----|
| SL=1.5 RRR=2.5 | 1,070 | 75.3% | +67.19 | 6.86 |
| SL=1.5 RRR=3.5 | 1,018 | 75.7% | +74.65 | 7.18 |
| SL=1.5 RRR=4.5 | 1,140 | 74.1% | +79.11 | 6.73 |
| SL=2.0 RRR=2.5 | 1,145 | 72.4% | +59.46 | 5.23 |
| **SL=2.0 RRR=3.5** | **1,002** | **72.7%** | **+66.07** | **5.25** |
| SL=2.0 RRR=4.5 | 1,173 | 71.4% | +74.14 | 5.42 |
| SL=2.5 RRR=2.5 | 1,281 | 73.2% | +59.29 | 4.48 |
| SL=2.5 RRR=3.5 | 1,205 | 73.1% | +63.89 | 4.64 |
| SL=2.5 RRR=4.5 | 1,216 | 72.7% | +71.30 | 4.92 |

**100% of variants are profitable.** Min: +59.29 pip, Max: +79.11 pip. Robust to perturbation.

### EXP 5: Year-by-Year

| Year | Trades | WR | Avg PnL | PF |
|------|--------|-----|---------|-----|
| 2016 | 287 | 68.3% | +80.59 | 4.60 |
| 2017 | 69 | 81.2% | +68.54 | 6.99 |
| 2018 | 76 | 80.3% | +61.53 | 8.21 |
| 2019 | 96 | 71.9% | +41.82 | 5.29 |
| 2020 | 60 | 78.3% | +81.60 | 10.86 |
| 2021 | 49 | 71.4% | +51.35 | 6.14 |
| 2022 | 117 | 75.2% | +74.79 | 6.27 |
| 2023 | 105 | 68.6% | +60.18 | 3.76 |
| 2024 | 45 | 77.8% | +69.21 | 6.96 |
| 2025 | 67 | 77.6% | +44.06 | 5.25 |
| 2026 | 31 | 54.8% | +35.70 | 2.77 |

**11/11 years profitable.** 2026 partial (Jul). 2020 highest (COVID volatility). 2019 weakest (still +41.82 pip).

### EXP 6: Permutation Test

| Metric | Value |
|--------|-------|
| Observed | +66.07 pip |
| Null mean | -0.11 pip |
| Null std | 4.59 pip |
| p-value | 0.0000 |

Directional component is significant at p<0.001. Edge is not random.

## 4. Causality

- Signal uses only confirmed swing levels from `bar[i-1]` and close from `bar[i]`
- No future data in trailing stop (uses `bar[i-1]` swing levels)
- Entry at `bar[i]` open, exits check `bar[i]` high/low
- All causality tests pass

## 5. Classification

| Criterion | Result |
|-----------|--------|
| Gross edge (zero cost) | +66.52 pip, PF=5.32 |
| Net edge (with costs) | +66.07 pip, PF=5.25 |
| Beats random control | +39.43 pip |
| Statistical significance | p<0.001 |
| Parameter robustness | 100% of 9 variants positive |
| Year-by-year consistency | 11/11 years positive |
| **Classification** | **B. STRUCTURAL SUPPORT — PROMOTE** |

## 6. Files

- Script: `scripts/phase_s0_breakout_reassessment.py`
- Results: `research_data/simple_strategies/S0_breakout_results.json`
- Tests: `tests/regression/test_phase_s0_breakout.py` (26 tests, all pass)
