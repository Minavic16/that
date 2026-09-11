# S8.6.7.B — Fill-Aware Execution Geometry Integration

**Date:** 2026-09-04
**Status:** Complete
**Gate:** 🟢 GREEN (parity chain complete)

---

## Summary

The entry/fill risk geometry divergence from S8.6.7.A has been resolved.
Production now builds all trade geometry from the ACTUAL broker fill price,
matching the research engine's behavior. A 5-pip shifted-fill test proves
that the divergence propagates correctly through every downstream component.

---

## What Changed

### 1. TradeGeometry — fill-aware construction

**`strategy/lifecycle/contracts.py`** — new dataclass:

```python
@dataclass(frozen=True)
class TradeGeometry:
    entry_price: float      # from fill, NOT signal
    stop_loss: float        # from fill
    take_profit: float      # from fill
    risk_pips: float        # from fill
    pip_size: float
    direction: int
    stop_distance: float    # ATR * multiplier (fixed)

    @classmethod
    def from_fill(cls, fill_price, stop_distance, rrr, pip_size, direction):
        """Build geometry from ACTUAL broker fill."""
```

Key property: `from_fill()` is the ONLY way to create TradeGeometry.
Signal-level prices must NOT be used directly.

### 2. RiskReconciliation — expected vs actual

**`strategy/lifecycle/contracts.py`** — new dataclass:

```python
@dataclass(frozen=True)
class RiskReconciliation:
    expected_entry: float
    actual_entry: float
    entry_deviation_pips: float
    within_tolerance: bool
    severity: str  # "OK" or "CRITICAL"
```

Built from expected entry vs actual fill. Detects deviations exceeding
a configurable tolerance (default 5 pips).

### 3. S8Runtime — fill-aware signal processing

**`execution/s8_runtime.py`** — `_process_signal()` rewritten:

```
Before:
    Signal → Intent → Execute → Register signal geometry

After:
    Signal → Intent → Execute → Get fill_price
        → TradeGeometry.from_fill(fill_price, stop_distance, ...)
        → RiskReconciliation(expected, actual, ...)
        → Register fill-based geometry
```

### 4. No SL/TP in initial order

The order is sent with ATR-derived stop distance, not absolute SL/TP.
After fill, geometry is recalculated from the actual fill price.

---

## Shifted-Fill Test

**`tests/test_fill_aware_geometry.py`** — 12 tests proving:

### test_5pip_shift_long_lifecycle

```
Signal level: 1.10000
Broker fill:  1.10050  (5 pips higher)
ATR:          0.00100
stop_distance: 0.00200

Expected geometry:
  Entry: 1.10050 (fill)
  SL:    1.09850 (fill - 20 pips)
  TP:    1.10750 (fill + 70 pips)
  Risk:  20 pips (fixed distance)

Lifecycle behavior:
  Bar 1: trailing (prev_swing_low=1.0990 > SL=1.09850)
  Bar 2: breakeven (profit=17 pips >= 16 pips threshold)
          SL → 1.10050 (FILL price, not signal level)
```

### test_geometry_preserves_risk_distance

```
Fill 1.10000 → SL 1.09800, risk 20 pips
Fill 1.10050 → SL 1.09850, risk 20 pips
Same risk, different reference.
```

### test_unrealized_r_uses_fill_reference

```
R uses fill price as entry, NOT signal level.
+10 pips from fill = 0.5R
NOT +15 pips from signal level = 0.75R
```

---

## Updated Parity Matrix

| Behavior | Status |
|----------|--------|
| 4H timeframe | ✅ |
| Lookback = 5 | ✅ |
| ATR = 14 | ✅ |
| ATR SL = 2.0 | ✅ |
| RRR = 3.5 | ✅ |
| Entry at fill price | ✅ FIXED |
| SL/TP from fill | ✅ FIXED |
| Fixed initial risk | ✅ |
| Trailing (prev swing) | ✅ |
| BE = 0.8R (from fill) | ✅ FIXED |
| Max hold = 42 bars | ✅ |
| SL → TP → MH ordering | ✅ |
| R calculation (from fill) | ✅ FIXED |
| Lifecycle integration | ✅ |
| Swing data to lifecycle | ✅ |
| Broker SL modification | ✅ (dry-run) |
| Fill-aware geometry | ✅ FIXED |
| Risk reconciliation | ✅ |

---

## Test Results

```
test_fill_aware_geometry.py     12 passed
test_e2e_runtime_replay.py       4 passed
test_lifecycle_integration.py   23 passed
test_trade_management_parity.py 29 passed
                                ──────
Total (lifecycle)               68 passed
```

---

## Gate Decision

**🟢 GREEN**

The entry/fill risk geometry divergence has been resolved. Production now
builds all trade geometry from the actual broker fill price, matching the
research engine's behavior. The shifted-fill test proves that a 5-pip
deviation propagates correctly through breakeven, trailing, and R calculation.

### Remaining items for production deployment

1. MT5 adapter `modify_position_stop()` for live (not dry-run)
2. Live position reconciliation
3. Monitoring integration for lifecycle events

---

## Files Created/Modified

### Created
- `tests/test_fill_aware_geometry.py`
- `S8_6_7B_FILL_AWARE_GEOMETRY_REPORT.md`

### Modified
- `strategy/lifecycle/contracts.py` — TradeGeometry, RiskReconciliation
- `strategy/lifecycle/__init__.py` — Updated exports
- `execution/s8_runtime.py` — fill-aware signal processing

### Unchanged
- `signals/breakout.py`
- `execution/orchestration.py`
- `risk/*`
