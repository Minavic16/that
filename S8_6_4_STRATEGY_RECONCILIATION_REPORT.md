# S8.6.4 — Strategy Reconciliation Report

**Date:** 2026-09-04
**Status:** Complete
**Gate:** CONDITIONAL GREEN

---

## Summary

Production strategy code has been reconciled with historically validated Variant A.
Trade management modules (breakeven, max hold, trailing stop) have been implemented
as a separate `strategy/trade_management/` package. 29 parity tests verify behavioral
equivalence with research simulation code.

---

## 1. Forensic Extraction (Step 1)

### Event Ordering Verified

```
Per-bar evaluation (LONG):
1. SL check:    if low <= sl → EXIT at sl (reason: "SL")
2. TP check:    if high >= tp → EXIT at tp (reason: "TP")
3. MH check:    if bars >= 42 → EXIT at close (reason: "MH")
4. IF no exit:
   4a. Trailing: new_sl = prev_swing_low; if new_sl > sl → sl = new_sl
   4b. Breakeven: if sl < entry and profit >= 0.8R → sl = entry
5. HOLD
```

Same for SHORT with direction inverted.

### Key Behaviors Confirmed

| Behavior | Research Source | Verified |
|----------|----------------|----------|
| SL/TP mutually exclusive per bar | elif chain | ✓ |
| Max hold exits at CLOSE | phase_s0 line 146 | ✓ |
| Trailing uses prev bar swing (i-1) | phase_s0 line 152 | ✓ |
| Breakeven guard (sl vs entry) | phase_s0 line 156 | ✓ |
| Trailing before breakeven | same else-block | ✓ |
| Risk fixed at entry | risk = abs(entry-sl)/pip | ✓ |

---

## 2. Canonical Strategy Specification (Step 2)

### Variant A — Historically Validated

```
Signal:
  lookback = 5
  atr_period = 14
  atr_multiplier = 2.0
  rrr = 3.5

Trade Management:
  breakeven_enabled = True
  breakeven_ratio = 0.8
  max_hold_days = 7
  max_hold_bars = 42 (7 * 6 bars/day)
  trailing_enabled = True
  trailing_type = "swing_based"

Timeframe: 4h
Entry: next bar open
```

---

## 3. Implementation (Step 3-4)

### New Modules Created

```
strategy/
├── __init__.py
└── trade_management/
    ├── __init__.py
    ├── breakeven.py      — BreakevenConfig, BreakevenManager
    ├── max_hold.py        — MaxHoldConfig, MaxHoldManager
    ├── trailing_stop.py   — TrailingStopConfig, TrailingStopManager
    └── manager.py         — TradeLifecycleManager (orchestrator)
```

### Design Principles

1. **Separate from signal generation** — `signals/breakout.py` remains unchanged
2. **Pure functions** — no side effects, no broker calls
3. **Configurable** — all parameters overridable via config dataclasses
4. **Documented** — each module includes research source line references

---

## 4. Parity Tests (Step 7)

29 tests verifying behavioral equivalence:

| Component | Tests | Status |
|-----------|-------|--------|
| BreakevenManager | 7 | ✓ |
| MaxHoldManager | 5 | ✓ |
| TrailingStopManager | 6 | ✓ |
| TradeLifecycleManager | 7 | ✓ |
| NaN detection | 4 | ✓ |

### Critical Parity Scenarios Tested

- SL exits before TP (priority)
- TP exits before MH (priority)
- MH exits at close (not SL/TP level)
- Trailing updates SL before breakeven evaluates
- Breakeven guard prevents re-triggering
- NaN swing levels are skipped
- Risk=0 disables all management
- Disabled configs produce no changes

---

## 5. Config Identity Fix (Step 5)

### Before (phantom parameters)

```python
StrategyIdentity.parameters = {
    "lookback": 5,
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,
    "rrr": 3.5,
    "max_hold_days": 7,      # NOT in breakout.py
    "breakeven_ratio": 0.8,   # NOT in breakout.py
}
```

### After (honest parameters)

```python
StrategyIdentity.parameters = {
    "lookback": 5,
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,
    "rrr": 3.5,
    "breakeven_ratio": 0.8,
    "breakeven_enabled": True,
    "max_hold_days": 7,
    "max_hold_bars": 42,
    "trailing_enabled": True,
    "trailing_type": "swing_based",
}
```

---

## 6. Integration Audit (Step 8)

### What Was NOT Changed

- `signals/breakout.py` — unchanged (signal generation only)
- `execution/contracts.py` — unchanged
- `execution/adapter.py` — unchanged
- `execution/orchestration.py` — unchanged
- `execution/s7_engine.py` — unchanged
- `risk/circuit_breakers.py` — unchanged

### What Would Be Required for Production

To deploy Variant A in production, the following would be needed:

1. **Wire `TradeLifecycleManager` into `S8Runtime`** — evaluate on each bar tick
2. **Provide swing levels to `MarketUpdate`** — signal generator must output swing lows/highs
3. **Track `bars_held`** — position tracker must count bars since entry
4. **Implement SL modification** — broker adapter must support `OrderModify` calls

These are NOT implemented yet. Current state is **parity-verified modules only**.

---

## 7. Test Results

```
test_trade_management_parity.py    29 passed
test_monitoring.py                 65 passed
test_circuit_breakers.py           22 passed
test_risk_guard.py                 43 passed
test_s7_engine.py                  22 passed
                                  ──────
Total (core)                      181 passed
```

---

## 8. What This Does NOT Solve

1. **No backtest re-run** — raw data unavailable, cannot verify trade-level parity at population level
2. **No circuit breaker calibration** — CB thresholds still provisional (from S8.6.1)
3. **No trade outcome feedback** — C7 gap remains
4. **No live deployment** — modules exist but are not wired into execution pipeline
5. **No population match** — even with trade management modules, we cannot prove population-level parity without raw OHLCV data

---

## 9. Gate Decision

**CONDITIONAL GREEN**

- ✅ Trade management modules implemented
- ✅ 29 parity tests pass
- ✅ Forensic spec documented
- ✅ Config identity fixed
- ⚠️ Population-level parity unverifiable (no raw data)
- ⚠️ Modules not wired into execution pipeline
- ⚠️ CB calibration still provisional

### Conditions for Full GREEN

1. Raw OHLCV data becomes available → run full backtest with trade management
2. Modules wired into S8Runtime → verify broker SL modification works
3. CB thresholds recalibrated on S6A population

---

## 10. Files Modified/Created

### Created
- `strategy/__init__.py`
- `strategy/trade_management/__init__.py`
- `strategy/trade_management/breakeven.py`
- `strategy/trade_management/max_hold.py`
- `strategy/trade_management/trailing_stop.py`
- `strategy/trade_management/manager.py`
- `tests/test_trade_management_parity.py`
- `S8_6_4_STRATEGY_FORENSIC_SPEC.md`
- `S8_6_4_STRATEGY_RECONCILIATION_REPORT.md`

### Modified
- `config/experiment.py` — StrategyIdentity parameters updated

### Unchanged
- `signals/breakout.py`
- `execution/*`
- `risk/*`
- `monitoring/*`
