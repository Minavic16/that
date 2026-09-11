# S8.6.7.A — Entry & Fill Risk Geometry Audit

**Date:** 2026-09-04
**Status:** Complete
**Finding:** 🔴 DIVERGENCE — Research and production use different price references for SL/TP/risk geometry

---

## Exact Code Evidence

### Research — S0 (`phase_s0_breakout_reassessment.py:187-196`)

```python
if not in_trade and sig_val != 0 and not np.isnan(atr_[i]) and atr_[i] > 0:
    entry_price = open_[i]              # ← NEXT BAR'S OPEN
    stop_dist = sl_mult * atr_[i]       # ← ATR from signal bar
    sl_price = entry_price - stop_dist  # ← SL anchored to NEXT BAR'S OPEN
    direction = sig_val
    entry_idx = i
    in_trade = True
```

Then risk:
```python
risk = abs(entry_price - sl_price) / pip  # ← risk anchored to NEXT BAR'S OPEN
```

### Research — S5.5 (`phase_s5_5_failure_analysis.py:173-183`)

```python
if pending_signal != 0 and i >= pending_idx + signal_delay_bars:
    if not in_trade and atr_[pending_idx] > 0:
        entry_price = open_[i]                  # ← NEXT BAR'S OPEN
        stop_dist = sl_mult * atr_[pending_idx] # ← ATR from SIGNAL BAR
        sl_price = entry_price - stop_dist      # ← SL anchored to NEXT BAR'S OPEN
        direction = pending_signal
        entry_idx = i
        risk_pips = stop_dist / pip             # ← risk anchored to NEXT BAR'S OPEN
        in_trade = True
```

### Production — `breakout.py:78-82`

```python
if not pd.isna(current_high) and prev_close <= current_high < current_close:
    direction = "BUY"
    entry_price = current_high                  # ← SIGNAL BAR'S SWING HIGH
    sl_price = entry_price - (current_atr * self.atr_sl_multiplier)  # ← SL anchored to SWING HIGH
    tp_price = entry_price + (current_atr * self.atr_sl_multiplier * self.rrr)
```

### Production — `intent_factory.py:125-135`

```python
return TradeIntent(
    entry_price=signal.entry_price,  # ← passes through SWING HIGH
    stop_loss=signal.sl_price,       # ← passes through (anchored to SWING HIGH)
    take_profit=signal.tp_price,     # ← passes through (anchored to SWING HIGH)
    ...
)
```

### Production — `mt5_adapter.py:136-144`

```python
response = self._client.send_order(
    symbol=mt5_symbol,
    direction=direction,
    volume=request.lot_size,
    sl=request.stop_loss,    # ← SL from SWING HIGH reference
    tp=request.take_profit,  # ← TP from SWING HIGH reference
    # entry_price NOT sent to broker
)
```

---

## Price Reference Comparison

| Component | Research | Production |
|-----------|----------|------------|
| Entry reference | `open_[i]` (next bar open) | `current_high` (swing high) |
| SL calculated from | entry reference | entry reference |
| TP calculated from | entry reference | entry reference |
| Risk = abs(entry-SL) | anchored to entry reference | anchored to entry reference |
| R = pnl / risk | anchored to entry reference | anchored to entry reference |
| Breakeven trigger | `(close - entry) / pip >= 0.8 * risk` | same formula, different entry ref |
| Broker fill | N/A (backtest) | Market order (ignores entry_price) |

---

## The Divergence

**Research**: SL, TP, risk, breakeven, R are all anchored to the **actual execution price** (next bar's open).

**Production**: SL, TP, risk, breakeven, R are anchored to the **signal bar's swing level** (breakout level).

### Why this matters — worked example

```
Signal bar:
  swing_high = 1.10000
  ATR = 0.00100

Next bar:
  open = 1.10050  (gapped up 5 pips)
```

**Research**:
```
entry_price = 1.10050  (next bar open)
sl_price    = 1.10050 - 0.00200 = 1.09850
risk        = 20 pips
```

**Production**:
```
entry_price = 1.10000  (swing high)
sl_price    = 1.10000 - 0.00200 = 1.09800
risk        = 20 pips (internal)

Broker fill = 1.10050  (market order)
actual_risk = 25 pips  (fill to SL)
```

**Result**: Production's internal risk (20 pips) ≠ actual broker risk (25 pips).

### Impact

| Effect | Severity |
|--------|----------|
| R-multiple calculation | Diverges when fill ≠ signal level |
| Breakeven trigger | May trigger at wrong price |
| Position sizing | Uses 20 pips risk, actual is 25 pips |
| Monitoring | Reports wrong R for live trades |
| Circuit breakers | May receive wrong R values |
| Trade attribution | Wrong R in trade log |

---

## Root Cause

`breakout.py` sets `entry_price = current_high` (the breakout level), not the actual execution price. This is a **signal-level concept** — "enter here" — but the production adapter sends a **market order** that fills at the broker's price.

The research engine avoids this by computing everything relative to `open_[i]` — the price at which the trade actually enters.

---

## Two Possible Resolutions

### Resolution A — Align with research (recommended)

Change production to use the actual fill price as the reference for SL/TP/risk:

1. Signal generates entry_level (swing high/low) — the breakout point
2. Broker fills at market → returns actual fill_price
3. SL/TP are recalculated relative to actual fill_price
4. Risk = abs(fill_price - SL) / pip

This matches what the research engine does.

### Resolution B — Accept signal-level reference

Keep production as-is, but:
1. Document that R calculations use signal-level reference
2. Accept that live R will differ from backtest R
3. Monitor for divergence

This is simpler but introduces ongoing lineage drift.

---

## Recommended Resolution

**Resolution A** — Align with research.

The change is contained:
- `breakout.py` keeps `entry_price = current_high` as the signal reference
- `intent_factory.py` passes it through as `entry_price`
- `s8_runtime.py` records the actual fill_price from `ExecutionResult`
- `LifecycleRegistry.register_entry()` uses `fill_price` as entry, not signal entry_price
- SL/TP are recalculated: `sl = fill_price ± (atr * 2.0)`

This makes production behavior match research exactly.

---

## Gate Impact

**Entry/fill risk geometry: 🔴 DIVERGENCE**

This is the last remaining piece preventing 🟢 GREEN on the parity matrix.

All other behaviors match. This one divergence affects:
- R calculation
- Breakeven trigger threshold
- Position sizing accuracy
- Trade attribution

**Resolution is contained** — can be fixed in S8.6.7.B without new architecture.

---

## Files Referenced

| File | Lines | Evidence |
|------|-------|----------|
| `scripts/phase_s0_breakout_reassessment.py` | 188 | `entry_price = open_[i]` |
| `scripts/phase_s0_breakout_reassessment.py` | 192 | `sl_price = entry_price - stop_dist` |
| `scripts/phase_s0_breakout_reassessment.py` | 199 | `risk = abs(entry_price - sl_price) / pip` |
| `scripts/phase_s5_5_failure_analysis.py` | 175 | `entry_price = open_[i]` |
| `scripts/phase_s5_5_failure_analysis.py` | 180 | `sl_price = entry_price - stop_dist` |
| `scripts/phase_s5_5_failure_analysis.py` | 183 | `risk_pips = stop_dist / pip` |
| `signals/breakout.py` | 80 | `entry_price = current_high` |
| `signals/breakout.py` | 81 | `sl_price = entry_price - (atr * 2.0)` |
| `execution/intent_factory.py` | 129 | `entry_price=signal.entry_price` |
| `execution/mt5_adapter.py` | 136-144 | entry_price not sent to broker |
