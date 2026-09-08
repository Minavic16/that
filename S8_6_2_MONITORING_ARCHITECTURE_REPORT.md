# S8.6.2 — Monitoring Architecture Consolidation

**Date:** 2026-09-04
**Status:** Complete — Gate Decision: YELLOW
**Predecessor:** S8.6.1 Monitoring Recalibration
**Code Changes:** 3 new modules added, 0 existing modules modified

---

## 1. Executive Summary

S8.6.2 consolidates the monitoring architecture around the correct deployed strategy identity, separates hard safety from statistical monitors, and establishes the framework for future calibration.

### Critical Discovery During This Phase

**S6A also uses breakeven/max_hold.** Both `phase_s5_5_failure_analysis.py` and `phase_s6_adaptive_risk.py` hardcode `MAX_HOLD_DAYS=7` and `BREAKEVEN_RATIO=0.8`. This means:

- S0: uses BE/MH → 1,002 trades, WR=73%
- S6A: uses BE/MH → 15,321 trades, WR=35.7%
- Deployed `breakout.py`: does NOT use either → **NO matching historical population**

This was not caught in S8.6.1 because the scripts declare these parameters but the connection to the backtest engine was not inspected at the function level.

### What Was Built

| Module | Purpose |
|--------|---------|
| `monitoring/architecture.py` | Layer 3: MetricState, classify_percentile, MonitoringClassification |
| `monitoring/decision.py` | Layer 4: HardSafetyLimits, DecisionEngine, Decision hierarchy |
| `monitoring/canonical_identity.py` | Canonical strategy identity, population mismatch documentation |
| `monitoring/data_schema.py` | TradeObservation, EquitySnapshot, ExecutionQuality schemas |

### What Was Fixed

- P95 DD calculation bug: Values were negative, P95=-164 (mildest), P5=-951 (worst). Report had direction inverted.

### Gate Decision: YELLOW

The architecture is correct and the identity is resolved. But:
- No historical population exactly matches deployment
- No trade-level data exists for any population
- Raw OHLCV data (`/root/data`) is not available for re-runs
- All thresholds remain provisional

---

## 2. Canonical Deployed Strategy Identity

### 2.1 What Actually Runs (`signals/breakout.py`)

```
Name: breakout
Version: 1.0.0
Code path: signals/breakout.py
Parameters:
  lookback: 5
  atr_period: 14
  atr_sl_multiplier: 2.0
  rrr: 3.5
Absent features (EXPLICITLY NOT IMPLEMENTED):
  breakeven_ratio
  max_hold_days
  trailing_stop
  session_filter
  macro_ema_filter
  news_filter
  regime_filter
Timeframe: 4h
Instruments: EUR/USD, GBP/USD, USD/JPY, AUD/USD, NZD/USD, EUR/JPY, GBP/JPY
Config hash: bddcffbe2ece8b76
```

### 2.2 Three Inconsistencies Resolved

| Source | ATR SL | RRR | Breakeven | Max Hold | Status |
|--------|--------|-----|-----------|----------|--------|
| `breakout.py` | 2.0 | 3.5 | None | None | **CANONICAL** |
| `ExperimentConfig` | 2.0 | 3.5 | 0.8 | 7d | MISMATCH (phantom params) |
| `config/settings.py` | 3.0 | 2.0 | 1.5 | None | MISMATCH (legacy) |

**The canonical identity is `breakout.py` — the actual code.**

### 2.3 Config Hash Gap

`ExperimentConfig.config_hash()` includes `max_hold_days=7` and `breakeven_ratio=0.8` even though these are NOT in `breakout.py`. Two runs with different breakeven logic would produce the same hash.

**Recommendation**: `StrategyIdentity.parameters` must match `breakout.py` exactly. Remove phantom parameters.

---

## 3. Population Mismatch Analysis

### 3.1 All Known Populations

| Population | Trades | WR | PF | BE | MH | Matches Deployed? |
|-----------|--------|-----|-----|-----|-----|-------------------|
| S0 | 1,002 | 73.0% | 5.32 | Yes | Yes | **NO** |
| S6A | 15,321 | 35.7% | 2.01 | Yes | Yes | **NO** |
| S5.5 | 15,321 | 35.9% | 2.14 | Yes | Yes | **NO** |

### 3.2 Evidence

- `scripts/phase_s6_adaptive_risk.py` line 33: `MAX_HOLD_DAYS = 7`
- `scripts/phase_s6_adaptive_risk.py` line 34: `BREAKEVEN_RATIO = 0.8`
- `scripts/phase_s6_adaptive_risk.py` line 148: `max_hold_days=MAX_HOLD_DAYS`
- `scripts/phase_s6_adaptive_risk.py` line 224: `breakeven_ratio=BREAKEVEN_RATIO`
- Same pattern in `phase_s5_5_failure_analysis.py`

### 3.3 Conclusion

**NO historical population exactly matches the deployed strategy.**

S6A/S5.5 is the closest available (same breakout logic, same ATR/RRR/lookback) but uses breakeven/max_hold that are NOT in the deployed code. A re-run of the backtest with BE/MH disabled is required for exact calibration.

### 3.4 Data Availability for Re-Run

- Raw OHLCV data: `/root/data/*.pkl` — **NOT AVAILABLE** on current system
- Backtest scripts: `scripts/phase_s6_adaptive_risk.py` — available, would need modification
- Re-run feasibility: Requires data restoration + parameter change (disable BE/MH)

---

## 4. P95 DD Bug Fix

### 4.1 The Error

S8.6.1 reported:
- P95 monthly max DD = 164 pips
- Median monthly max DD = 418 pips

This is mathematically impossible (P95 >= median always for any distribution).

### 4.2 Root Cause

Monthly `max_dd` values are **negative** (standard DD convention):
- Min: -2,086 pips (worst month)
- Max: -135 pips (mildest month)

Percentiles of negative values:
- P5 = -951 pips (WORST 5% of months)
- P50 = -418 pips (median)
- P95 = -164 pips (MILDEST 5% of months)

### 4.3 Corrected Values

| Percentile | Value | Interpretation |
|-----------|-------|----------------|
| P5 | -951 pips | Worst 5% of months |
| P25 | -582 pips | |
| P50 | -418 pips | Median month |
| P75 | -285 pips | |
| P95 | -164 pips | Mildest 5% of months |

**The report had the direction inverted. P95 is the MILDEST drawdown, not the most severe.**

---

## 5. Four-Layer Monitoring Architecture

### 5.1 Architecture Overview

```
Layer 4: Decision Engine
    ┌─────────────────────────────────────┐
    │  Hard Safety → HALT                 │
    │  Infrastructure → HALT              │
    │  Multiple extremes → REDUCE         │
    │  Single extreme → INVESTIGATE       │
    │  Warnings → MONITOR                 │
    │  Normal → ALLOW                     │
    └─────────────────────────────────────┘
                    ↑
Layer 3: Monitoring Classification
    ┌─────────────────────────────────────┐
    │  NORMAL / ELEVATED / WARNING /      │
    │  EXTREME                            │
    │  Direction-aware (high=bad vs       │
    │  low=bad)                           │
    └─────────────────────────────────────┘
                    ↑
Layer 2: Statistical Engine
    ┌─────────────────────────────────────┐
    │  Distributions, percentiles,        │
    │  rolling stats, z-scores, CI        │
    └─────────────────────────────────────┘
                    ↑
Layer 1: Observation
    ┌─────────────────────────────────────┐
    │  Raw facts: spread, slippage,       │
    │  latency, PnL, R-multiple, DD,      │
    │  equity, timestamps                 │
    └─────────────────────────────────────┘
```

### 5.2 Decision Hierarchy

| Priority | Source | Action | Bypass? |
|----------|--------|--------|---------|
| 1 | Hard safety (DD, daily loss) | HALT | Bypasses all statistical classification |
| 2 | Infrastructure failure | HALT | Bypasses all statistical classification |
| 3 | ≥2 extreme statistical anomalies | REDUCE_RISK | — |
| 4 | 1 extreme statistical anomaly | INVESTIGATE | — |
| 5 | ≥2 warning-level anomalies | MONITOR | — |
| 6 | 1 warning-level anomaly | MONITOR | — |
| 7 | All normal | ALLOW | — |

### 5.3 Key Design Principle

**Statistical anomalies alone should NOT trigger hard halts.**

A P95 spread event is unusual. It does not automatically mean STOP THE STRATEGY.

But: P99 spread, persistent for multiple observations, during order execution, might justify blocking entries.

The decision engine requires **multiple concurrent anomalies** or **hard safety breaches** to escalate beyond MONITOR.

### 5.4 Direction-Aware Classification

| Metric | Direction | NORMAL | ELEVATED | WARNING | EXTREME |
|--------|-----------|--------|----------|---------|---------|
| Slippage | HIGH_IS_BAD | < P75 | P75-P90 | P90-P95 | > P95 |
| Spread | HIGH_IS_BAD | < P75 | P75-P90 | P90-P95 | > P95 |
| Latency | HIGH_IS_BAD | < P75 | P75-P90 | P90-P95 | > P95 |
| Win rate | LOW_IS_BAD | > P25 | P10-P25 | P5-P10 | < P5 |
| EV | LOW_IS_BAD | > P25 | P10-P25 | P5-P10 | < P5 |
| Profit factor | LOW_IS_BAD | > P25 | P10-P25 | P5-P10 | < P5 |

---

## 6. R-Normalization

### 6.1 Why R-Units

R is strategy-native. A 10R drawdown means the same thing regardless of risk level:
- At 0.10% risk: 10R = 1% of account
- At 0.25% risk: 10R = 2.5% of account
- At 0.50% risk: 10R = 5% of account

Account percentage does not have this property.

### 6.2 Two Simultaneous Views

**Strategy Health View** (R-native):
- Current DD in R
- EV in R
- Loss streaks
- DD episodes
- Win rate
- Profit factor

**Prop Survival View** (account-%):
- Current DD %
- Daily loss %
- Maximum DD limit
- Position size limits

**These should never be confused.**

### 6.3 R-Based Monitoring Thresholds (Provisional)

| Metric | Threshold | Action | Source | Confidence |
|--------|-----------|--------|--------|------------|
| DD soft warning | 10R | MONITOR | S6A max DD=19.61R | LOW |
| DD hard halt | 20R | HALT | S6A max DD=19.61R | LOW |
| DD investigation | 15R | INVESTIGATE | Between warning and halt | LOW |

**These are provisional. Actual thresholds require live data.**

---

## 7. Hard Safety Limits (Separate from Statistical Monitors)

| Limit | Value | Action | Source |
|-------|-------|--------|--------|
| Max DD | 10% of initial | HALT | Prop-firm typical |
| Daily loss | 5% of equity | HALT | Prop-firm typical |
| Max open trades | 3 | BLOCK entries | Risk config |
| Max total exposure | 1.0 lots | BLOCK entries | Risk config |

**These are NOT statistical monitors. They are hard safety limits that bypass all classification.**

---

## 8. Data Schema for Future Calibration

### 8.1 Required Collection (Layer 1)

| Schema | Collection Trigger | Storage |
|--------|-------------------|---------|
| `TradeObservation` | Every trade close | JSONL |
| `EquitySnapshot` | Every hour | JSONL |
| `ExecutionQuality` | Every fill | JSONL |

### 8.2 Minimum Sample Sizes

| Metric | Min Samples | Collection Method |
|--------|-------------|-------------------|
| Win rate | 200 trades | Trade logs |
| EV | 200 trades | Trade logs |
| Slippage | 200 fills | Execution logs |
| Spread | 200 observations | Bridge tick data |
| Latency | 500 probes | HTTP probes |
| DD depth | 30 episodes | Equity tracking |
| Loss streaks | 100 streaks | Trade logs |

### 8.3 Provisional Thresholds (S8.6.1 Calibrated)

| Metric | Source | Confidence | Note |
|--------|--------|------------|------|
| WR 20t monitoring | 30% | LOW | Simulated from monthly data |
| WR 20t warning | 25% | LOW | Simulated |
| WR 20t investigation | 20% | LOW | Simulated |
| WR 20t halt | 15% | LOW | Simulated |
| PF threshold | 1.0 | MEDIUM | S6A lifetime PF=2.01 |
| DD soft warning | 10R | LOW | S6A max DD=19.61R |
| DD hard halt | 20R | LOW | S6A max DD=19.61R |

---

## 9. What Changed (Code)

| File | Change | Reason |
|------|--------|--------|
| `monitoring/architecture.py` | **Created** | Layer 3: MetricState, classify_percentile |
| `monitoring/decision.py` | **Created** | Layer 4: HardSafetyLimits, DecisionEngine |
| `monitoring/canonical_identity.py` | **Created** | Canonical strategy identity, population mismatch |
| `monitoring/data_schema.py` | **Created** | Data schemas for future calibration |
| `monitoring/__init__.py` | **Updated** | Export new modules |

**No existing modules were modified. No circuit breaker thresholds were changed.**

---

## 10. Test Results

**739/739 tests pass.** All new modules import and function correctly.

Verification:
- `CanonicalStrategyIdentity().summary()` produces correct output
- `classify_percentile()` correctly classifies metrics with direction
- `DecisionEngine.decide()` correctly escalates from ALLOW → MONITOR → INVESTIGATE → REDUCE → HALT
- `HardSafetyLimits.check()` correctly triggers HALT on safety breaches
- Population mismatch assessment correctly identifies all three populations as MISMATCH

---

## 11. Gate Decision

### S8.6.2 ARCHITECTURE CONSOLIDATION: **YELLOW**

**YELLOW** — Architecture consolidated, identity resolved, but no exact baseline exists.

**Rationale:**
- ✅ Four-layer architecture defined and implemented
- ✅ Canonical strategy identity established
- ✅ Three-config ambiguity resolved
- ✅ Hard safety separated from statistical monitors
- ✅ R-normalization framework established
- ✅ Data schema for future calibration defined
- ✅ P95 DD bug fixed
- ✅ Population mismatch documented
- ✅ 739/739 tests pass
- ⚠️ NO historical population exactly matches deployment (all use BE/MH)
- ⚠️ No trade-level data exists
- ⚠️ All thresholds remain provisional
- ⚠️ Raw data unavailable for re-run
- ❌ Cannot calibrate precise thresholds without trade-level data

---

## 12. Recommended Next Steps

### Immediate

1. **Resolve BE/MH discrepancy**: Either implement breakeven/max_hold in `breakout.py` (making S6A the correct baseline) OR remove them from `StrategyIdentity` and re-run backtest
2. **Restore raw data**: `/root/data/*.pkl` is needed for re-runs
3. **Begin passive data collection**: Wire spread, latency, equity collection

### Then

4. **S8.7**: Live monitoring data collection
5. **S8.8**: C7 trade feedback wiring (only after breaker recalibration)

### Not Yet

6. Do NOT modify circuit breaker thresholds without live data
7. Do NOT proceed to C7 until BE/MH discrepancy is resolved
8. Do NOT enable live trading until thresholds are calibrated

---

*End of S8.6.2 Monitoring Architecture Consolidation*
