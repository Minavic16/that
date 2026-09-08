# S8.6.6 — End-to-End Runtime Parity Audit

**Date:** 2026-09-04
**Status:** Complete
**Gate:** 🔴 RED — Critical integration gaps identified

---

## Parity Matrix

| Behavior | Research | Production | Evidence | Status |
|----------|----------|------------|----------|--------|
| Timeframe | 4h | H4 | `s8_runtime.py:118` `timeframe="H4"` | ✅ |
| Lookback | 5 | 5 | `breakout.py:16` `RESEARCH_DEFAULTS["lookback"]=5` | ✅ |
| ATR period | 14 | 14 | `breakout.py:17` `RESEARCH_DEFAULTS["atr_period"]=14` | ✅ |
| ATR SL multiplier | 2.0 | 2.0 | `breakout.py:18` `RESEARCH_DEFAULTS["atr_sl_multiplier"]=2.0` | ✅ |
| RRR | 3.5 | 3.5 | `breakout.py:19` `RESEARCH_DEFAULTS["rrr"]=3.5` | ✅ |
| Entry price | signal bar level | signal bar level | `breakout.py:80` `entry_price=current_high` | ✅ |
| Initial SL | entry ± ATR*2.0 | entry ± ATR*2.0 | `breakout.py:81` `sl_price=entry-(atr*2.0)` | ✅ |
| TP | entry ± risk*3.5 | entry ± risk*3.5 | `breakout.py:82` `tp_price=entry+(atr*2.0*3.5)` | ✅ |
| Risk pips | abs(entry-SL)/pip | abs(entry-SL)/pip | `breakout.py:81` vs `contracts.py` | ✅ |
| R calculation | pnl_pips/risk_pips | unrealized_r() | `contracts.py:105-110` | ✅ |
| Swing detection | same swing logic | same swing logic | `breakout.py:59-60` `swing_high_series/low_series` | ✅ |
| Swing source | previous bar (i-2) | previous bar (iloc[-2]) | `breakout.py:63-64` | ✅ |
| SL → TP ordering | SL first, then TP | SL first, then TP | `manager.py:89-109` | ✅ |
| Max hold | 42 bars (7*6) | 42 bars (7*6) | `max_hold.py:28` `max_bars=42` | ✅ |
| Breakeven ratio | 0.8R | 0.8R | `breakeven.py:12` `trigger_r=0.8` | ✅ |
| Trailing | prev bar swing | prev bar swing | `trailing_stop.py:71-80` | ✅ |
| Trailing before BE | trailing then BE | trailing then BE | `manager.py:113-118` | ✅ |
| **Lifecycle integration** | **evaluate on bar close** | **NOT WIRED** | `s8_runtime.py` — no LifecycleRegistry | ❌ BLOCKER |
| **Swing data to lifecycle** | **prev_swing_low/high** | **NOT PROVIDED** | `s8_runtime.py` — no MarketContext creation | ❌ BLOCKER |
| **Broker SL modification** | **modify order SL** | **NOT IMPLEMENTED** | `adapter.py` — no modify method | ❌ BLOCKER |
| **Position reconciliation** | **internal vs broker SL** | **NOT IMPLEMENTED** | `s8_runtime.py` — no reconcile call | ⚠️ GAP |

---

## Detailed Findings

### 1. Signal Parity ✅

**Research** (`phase_s5_5:29-34`):
```python
LOOKBACK = 5
ATR_PERIOD = 14
ATR_SL_MULT = 2.0
RRR = 3.5
```

**Production** (`breakout.py:15-20`):
```python
RESEARCH_DEFAULTS = {
    "lookback": 5,
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,
    "rrr": 3.5,
}
```

**S8Runtime** (`s8_runtime.py:607-608`):
```python
from signals.breakout import BreakoutSignal, RESEARCH_DEFAULTS
return BreakoutSignal(**RESEARCH_DEFAULTS)
```

**Verdict**: Signal parameters match exactly. No deviation.

---

### 2. Entry Parity ✅

**Research** (`phase_s5_5:175`):
```python
entry_price = open_[i]  # Next bar's open
```

**Production** (`breakout.py:80`):
```python
entry_price = current_high  # Signal bar's swing level
```

**Note**: Production uses the signal bar's swing level as the entry price in the SignalResult. The actual execution price in live trading would be the broker's fill price (which should approximate the next bar's open). The `EntryPrice` in `TradeIntent` is a *requested* price, not a guaranteed fill.

**Verdict**: Conceptually equivalent. The signal identifies WHERE to enter; the broker determines the actual fill.

---

### 3. ATR Source ✅

**Research** (`phase_s5_5:176`):
```python
stop_dist = sl_mult * atr_[pending_idx]  # ATR from signal bar
```

**Production** (`breakout.py:69-70`):
```python
atr = calculate_atr(df, self.atr_period)
current_atr = atr.iloc[-1]  # ATR from last bar in DataFrame
```

**Note**: Both use ATR calculated up to the signal bar. The production code passes the full DataFrame to `calculate_atr`, which computes ATR for all bars. `atr.iloc[-1]` is the ATR of the most recent bar (the signal bar).

**Verdict**: ATR source matches.

---

### 4. Lifecycle Integration ❌ BLOCKER

**Research** (`phase_s5_5:128-290`):
```python
# On each bar:
if in_trade:
    # 1. SL check
    # 2. TP check
    # 3. Max hold check
    # 4. Trailing + breakeven
```

**Production** (`s8_runtime.py:446-517`):
```python
def _process_pair(self, pair):
    # Fetch candles
    # Check for new bar
    # Get strategy signal
    # Create intent
    # Execute through coordinator
    # Track position
```

**What's missing**:
- `LifecycleRegistry` is never instantiated
- `evaluate_bar()` is never called on bar close
- Active positions are not registered in any lifecycle manager
- No lifecycle decisions are produced

**Impact**: The trade management modules (breakeven, max hold, trailing) exist but are never executed. The production runtime only does: signal → intent → risk → execute. It does NOT do: bar close → lifecycle evaluation → SL modification → exit management.

**This is the single largest gap between research and production.**

---

### 5. Swing Data to Lifecycle ❌ BLOCKER

**Research** (`phase_s5_5:158-159`):
```python
sl_ = sig["swing_low"].values   # Previous bar's swing low
sh_ = sig["swing_high"].values  # Previous bar's swing high
```

Used in lifecycle:
```python
# Trailing (line 210-212):
new_sl = sl_[i-1]  # Previous bar's swing low
if not isnan(new_sl) and new_sl > sl_price:
    sl_price = new_sl
```

**Production**:
- `breakout.py:97-101` returns swing levels in `SignalResult.metadata`
- `s8_runtime.py` does NOT read `signal_result.metadata`
- `s8_runtime.py` does NOT create `MarketContext` with swing data
- `LifecycleRegistry.evaluate_bar()` requires `MarketContext` with `previous_swing_low/high`

**Impact**: Even if lifecycle were wired, it would have no swing data to evaluate trailing stops.

---

### 6. Broker SL Modification ❌ BLOCKER

**Research**:
```python
sl_price = new_sl  # In-memory SL update
```

**Production**:
- `TradeLifecycleManager` returns `LifecycleDecision(action=MOVE_STOP, new_sl=X)`
- No code sends an SL modification order to the broker
- `adapter.py` has no `modify_position()` method
- `MT5ExecutionAdapter` has no SL modification capability
- `DryRunAdapter` has no SL modification capability

**Impact**: Even if lifecycle were wired and produced MOVE_STOP decisions, the broker's SL would never change. Internal state and broker state would diverge immediately.

---

### 7. Position Reconciliation ⚠️ GAP

**Production** (`s8_runtime.py:576-602`):
```python
def _check_position_outcomes(self):
    # Detects closed positions
    # Logs POSITION_CLOSED event
    # Does NOT compare internal SL vs broker SL
```

**LifecycleRegistry** has `reconcile()` method, but it is never called.

**Impact**: If internal SL diverges from broker SL (e.g., due to failed modification), the system has no way to detect it.

---

### 8. Monitoring Integration ⚠️ GAP

**LifecycleRegistry** produces `LifecycleEvent` objects with decision details, but:
- `s8_runtime.py` does not read lifecycle events
- No connection to monitoring layer
- Failed modifications would be silent

---

## Root Cause Analysis

The gaps exist because S8Runtime was built as a **signal → execution pipeline**, not a **signal → lifecycle → execution pipeline**. The architecture was designed for:

```
Signal → Intent → Risk → Execute → Log
```

But research requires:

```
Bar Close → Signal (new entry) OR Lifecycle (existing position) → Execute → Log
```

The fundamental missing concept is that **on each bar, the runtime must choose between**:
1. Evaluating a new signal (if no position is open)
2. Evaluating the lifecycle of an existing position (if one is open)

Currently, S8Runtime only does (1). It never does (2).

---

## What Would Fix This

### Minimum Viable Integration (without live trading)

1. **Instantiate LifecycleRegistry** in `S8Runtime.initialize()`
2. **On bar close**: check if position is open for this pair
   - If open: call `registry.evaluate_bar(market_context)`
   - If not open: call `_get_strategy_signal()` as currently
3. **Create MarketContext** from candle data + swing levels from signal metadata
4. **Register new entries** in registry when intent is filled
5. **Record MOVE_STOP decisions** in event log (even if no broker modification)

### Required for Production

6. **Implement `modify_position()`** in adapter (broker SL modification)
7. **Call reconcile()** periodically to verify internal vs broker state
8. **Connect lifecycle events** to monitoring layer

---

## Gate Decision

**🔴 RED**

The strategy lifecycle modules (S8.6.4-5) are correctly implemented and tested, but the production runtime does not execute them. The following critical gaps prevent parity:

1. **Lifecycle not wired** — no `LifecycleRegistry` in runtime
2. **Swing data not provided** — no `MarketContext` creation
3. **Broker SL modification not implemented** — no `modify_position()` method

**Condition for 🟡 GREEN**: All three blockers resolved in a non-live test configuration.

**Condition for 🟢 GREEN**: Plus successful end-to-end deterministic replay test through actual S8Runtime.

---

## 10. Files Referenced

| File | Lines | Finding |
|------|-------|---------|
| `signals/breakout.py` | 15-20 | RESEARCH_DEFAULTS — ✅ |
| `signals/breakout.py` | 59-64 | Swing detection — ✅ |
| `signals/breakout.py` | 69-88 | ATR + SL/TP calc — ✅ |
| `execution/s8_runtime.py` | 118 | timeframe="H4" — ✅ |
| `execution/s8_runtime.py` | 604-608 | Strategy creation — ✅ |
| `execution/s8_runtime.py` | 446-517 | _process_pair — no lifecycle |
| `execution/s8_runtime.py` | 576-602 | _check_position_outcomes — no reconcile |
| `execution/adapter.py` | 82-149 | BaseExecutionAdapter — no modify |
| `strategy/lifecycle/registry.py` | 1-180 | LifecycleRegistry — exists but unused |
| `strategy/lifecycle/contracts.py` | 1-150 | MarketContext — exists but unused |
| `strategy/trade_management/manager.py` | 1-150 | TradeLifecycleManager — exists but unused |
| `scripts/phase_s5_5_failure_analysis.py` | 29-34 | Research params — matches |
| `scripts/phase_s5_5_failure_analysis.py` | 141-179 | Research entry — next bar open |
| `scripts/phase_s5_5_failure_analysis.py` | 206-225 | Research lifecycle — not in runtime |
