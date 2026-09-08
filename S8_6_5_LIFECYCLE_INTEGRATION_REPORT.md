# S8.6.5 — Production Strategy Lifecycle Integration

**Date:** 2026-09-04
**Status:** Complete
**Gate:** CONDITIONAL GREEN

---

## Summary

Production lifecycle management infrastructure implemented.
23 integration tests verify: market data → lifecycle evaluation → execution intents → broker reconciliation.
Modules are built and tested but NOT wired into S8Runtime.

---

## 1. Architecture

```
Market Data (MarketContext)
         │
    4H Bar Close
         │
         ▼
  LifecycleRegistry
         │
  ┌──────┴──────┐
  │ evaluate_bar │
  └──────┬──────┘
         │
  ┌──────┼──────────────┐
  │      │              │
  ▼      ▼              ▼
EXIT   MOVE_STOP      HOLD
  │      │
  ▼      ▼
Broker  Broker
Close   Modify SL
  │      │
  └──┬───┘
     ▼
State Reconciliation
     │
     ▼
  Monitoring
```

---

## 2. Components Created

### `strategy/lifecycle/contracts.py`

| Dataclass | Purpose |
|-----------|---------|
| `PositionLifecycleState` | Canonical active trade state |
| `MarketContext` | Bar OHLCV + swing levels |
| `LifecycleDecision` | Action + exit info |
| `ModificationResult` | Broker SL modification confirmation |
| `ReconciliationResult` | Internal vs broker SL comparison |

### `strategy/lifecycle/registry.py`

| Class | Purpose |
|-------|---------|
| `LifecycleRegistry` | Manages active positions, coordinates evaluation |
| `LifecycleEvent` | Audit trail of lifecycle decisions |

---

## 3. Key Design Decisions

### risk_pips is IMMUTABLE

```python
risk_pips = abs(entry - initial_sl) / pip
```

This value never changes after entry. Trailing and breakeven move the SL,
but the R denominator remains the initial risk. This matches the research engine exactly.

### Bar-close evaluation only

The lifecycle evaluates once per bar close, not on every tick.
This matches the historical research model (OHLC bars).

### State reconciliation

Every position can be compared against broker-reported SL.
Mismatches produce CRITICAL severity alerts.

### Event audit trail

Every evaluation produces a `LifecycleEvent` with:
- trade_id, timestamp, bar_index
- decision (action + details)
- modification_result (if applicable)
- reconciliation (if applicable)

---

## 4. Test Results

### A. Unit Tests (9)

- PositionLifecycleState creation, risk_pips immutability, unrealized_r
- ModificationResult success/failure/sl_matches
- ReconciliationResult ok/mismatch

### B. Integration Tests (8)

- Hold on quiet bar
- Trailing moves SL up
- Breakeven triggers after trailing
- SL exits position
- TP exits position
- Max hold exits at close (42 bars)
- Multiple positions independent
- Events recorded

### C. Broker Mock Tests (4)

- Successful modification recorded
- Reconciliation OK (SL matches)
- Reconciliation mismatch (CRITICAL)
- Reconciliation missing broker position (CRITICAL)

### D. Deterministic Replay Test (2)

Full lifecycle replay:
```
Bar 0  → ENTRY
Bar 1  → HOLD
Bar 2  → MOVE_STOP (trailing)
Bar 3  → MOVE_STOP (breakeven)
Bar 4  → HOLD
Bar 5  → HOLD
...
Bar 42 → EXIT (max hold at close)
```

SHORT replay: SL exits before TP on same bar.

```
test_lifecycle_integration.py    23 passed
test_trade_management_parity.py  29 passed
test_monitoring.py               65 passed
test_circuit_breakers.py         22 passed
test_risk_guard.py               43 passed
test_s7_engine.py                22 passed
                                ──────
Total (core)                    204 passed
```

---

## 5. What This Enables

1. **Canonical position state** — every active trade has a well-defined lifecycle representation
2. **Event ordering preservation** — SL→TP→MH→Trailing→BE enforced
3. **Broker confirmation contract** — SL modifications must be confirmed
4. **State reconciliation** — internal vs broker SL comparison available
5. **Audit trail** — every lifecycle decision recorded

---

## 6. What This Does NOT Do

1. **NOT wired into S8Runtime** — modules exist but aren't connected to the execution pipeline
2. **NOT providing swing data** — `MarketContext.previous_swing_low/high` must come from signal generator
3. **NOT handling broker SL modification** — `ModificationResult` contract exists but no adapter implements it
4. **NOT handling intrabar ambiguity** — documented but not resolved (see below)

---

## 7. Intrabar Ambiguity Policy

### Documented Policy

> Historical parity mode uses conservative SL-first ordering for bar-level simulation.
> Live execution defers exit ordering to broker event reality.

### Why This Matters

In backtesting, when both SL and TP are touched in the same bar:
- Research assumes SL first (conservative)
- Live broker knows which happened first

This difference is **documented as an execution assumption**, not resolved artificially.

---

## 8. Remaining Integration Gaps

| Gap | Status | Required For |
|-----|--------|-------------|
| Swing data provider | Not implemented | MarketContext population |
| Broker SL modification | Contract exists, no adapter | Production lifecycle |
| S8Runtime wiring | Not done | Live execution |
| Tick-level SL/TP detection | Not implemented | Live execution (optional) |

---

## 9. Gate Decision

**CONDITIONAL GREEN**

- ✅ Lifecycle contracts defined
- ✅ LifecycleRegistry implemented
- ✅ State reconciliation mechanism
- ✅ 23 integration tests pass
- ✅ Deterministic replay verified
- ⚠️ Not wired into S8Runtime
- ⚠️ Swing data provider not implemented
- ⚠️ Broker SL modification not implemented

### Conditions for Full GREEN

1. `MarketContext` populated by signal generator (swing data)
2. `LifecycleRegistry.evaluate_bar()` called on each bar close in S8Runtime
3. `ModificationResult` returned by broker adapter

---

## 10. Files Created

### Created
- `strategy/lifecycle/__init__.py`
- `strategy/lifecycle/contracts.py`
- `strategy/lifecycle/registry.py`
- `tests/test_lifecycle_integration.py`
- `S8_6_5_LIFECYCLE_INTEGRATION_REPORT.md`

### Unchanged
- `strategy/trade_management/*` (from S8.6.4)
- `signals/breakout.py`
- `execution/*`
- `risk/*`
