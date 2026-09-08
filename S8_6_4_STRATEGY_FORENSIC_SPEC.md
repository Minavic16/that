# S8.6.4 — Strategy Forensic Trade Lifecycle Specification

**Date:** 2026-09-04
**Status:** Complete
**Source:** Line-by-line trace of research simulation engines

---

## 1. Event Ordering (Research-Proven)

### Per-Bar Evaluation Sequence (LONG)

```
1. SL check:    if low <= sl_price → EXIT at sl_price (reason: "SL")
2. TP check:    if high >= tp_price → EXIT at tp_price (reason: "TP")
3. MH check:    if bars_held >= 42 → EXIT at close (reason: "MH")
4. IF no exit:
   4a. Trailing: new_sl = prev_swing_low; if new_sl > sl → sl = new_sl
   4b. Breakeven: if sl < entry and (close - entry)/pip >= 0.8 * risk → sl = entry
5. HOLD (next bar)
```

### Per-Bar Evaluation Sequence (SHORT)

```
1. SL check:    if high >= sl_price → EXIT at sl_price (reason: "SL")
2. TP check:    if low <= tp_price → EXIT at tp_price (reason: "TP")
3. MH check:    if bars_held >= 42 → EXIT at close (reason: "MH")
4. IF no exit:
   4a. Trailing: new_sl = prev_swing_high; if new_sl < sl → sl = new_sl
   4b. Breakeven: if sl > entry and (entry - close)/pip >= 0.8 * risk → sl = entry
5. HOLD (next bar)
```

### Key Observations

1. **SL and TP are mutually exclusive per bar** — if SL triggers, TP is never checked (elif chain)
2. **Max hold uses CLOSE as exit price** — not SL or TP level
3. **Trailing and breakeven execute in the SAME else-block** — only when NO exit occurred
4. **Trailing evaluates BEFORE breakeven** — breakeven sees the already-trailing-updated SL
5. **Breakeven guard**: `sl < entry` (LONG) or `sl > entry` (SHORT) — prevents re-triggering after SL already at entry
6. **Trailing uses PREVIOUS bar's swing** (`i-1`) — avoids lookahead bias
7. **Breakeven uses CURRENT bar's close** — for profit measurement
8. **Risk is computed at entry**: `risk = abs(entry - sl) / pip` — fixed for the trade's life

---

## 2. Entry Logic

```
Entry price = open of the bar AFTER signal bar
Stop distance = atr_multiplier * atr_at_signal_bar
SL = entry - stop_dist (LONG) or entry + stop_dist (SHORT)
TP = entry + risk * rrr * pip (LONG) or entry - risk * rrr * pip (SHORT)
```

- Entry is at next bar's open (signal delay = 0 bars in S5.5/S6)
- ATR is from the SIGNAL bar, not the entry bar
- Minimum stop distance: 1 pip (enforced in research)

---

## 3. Breakeven Logic

```
Trigger: profit_pips >= trigger_r * risk_pips
  LONG:  (close - entry) / pip >= 0.8 * risk
  SHORT: (entry - close) / pip >= 0.8 * risk

Action: sl_price = entry_price (move SL to breakeven)

Guard: sl must not already be at/beyond entry
  LONG:  sl_price < entry_price
  SHORT: sl_price > entry_price
```

- Breakeven is a ONE-TIME move (guard prevents re-triggering)
- Uses CLOSE price for measurement (not high/low)
- Executes AFTER trailing stop update on same bar

---

## 4. Trailing Stop Logic

```
LONG:
  new_sl = prev_bar_swing_low[i-1]
  if not isnan(new_sl) and new_sl > current_sl:
    sl = new_sl

SHORT:
  new_sl = prev_bar_swing_high[i-1]
  if not isnan(new_sl) and new_sl < current_sl:
    sl = new_sl
```

- Uses PREVIOUS bar's confirmed swing level (not current bar)
- Only moves SL tighter (never loosens)
- Swing levels are from the signal generator's swing detection
- NaN swing levels are skipped (no movement)

---

## 5. Max Hold Logic

```
max_bars = max_hold_days * bars_per_day = 7 * 6 = 42
if bars_held >= max_bars:
  exit_price = close
  exit_reason = "MH"
```

- Exit at CLOSE of the bar when limit is reached
- bars_held = current_bar_index - entry_bar_index
- bar 42 means 42 bars have elapsed since entry
- Exit reason is "MH" (max hold)

---

## 6. Exit Reason Hierarchy

| Priority | Exit Reason | Price | Condition |
|----------|------------|-------|-----------|
| 1 | SL | sl_price | low <= sl (LONG) or high >= sl (SHORT) |
| 2 | TP | tp_price | high >= tp (LONG) or low <= tp (SHORT) |
| 3 | MH | close | bars_held >= 42 |

Only ONE exit per bar. SL takes priority over TP. TP takes priority over MH.

---

## 7. PnL Calculation

```
LONG:  pnl_pips = (exit_price - entry_price) / pip - total_cost
SHORT: pnl_pips = (entry_price - exit_price) / pip - total_cost
R = pnl_pips / risk_pips
```

- total_cost = (spread/2 + slippage + commission/10) * 2
- R is the risk-normalized return

---

## 8. Trade Record Fields

Each completed trade records:
- pair, direction, entry_idx, exit_idx
- entry_time, exit_time
- entry_price, exit_price
- pnl_pips, r (R-multiple)
- exit_reason (SL/TP/MH)
- hold_bars, risk_pips
- mfe_pips (maximum favorable excursion)
- mae_pips (maximum adverse excursion)
- displacement_atr, atr_at_entry, vol_at_entry
