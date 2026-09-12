# Phase 9C: Strategy Reconstruction Document

**Date:** 2026-08-15
**Status:** RECONSTRUCTION COMPLETE — awaiting economic validation

---

## 1. Executive Summary

The NestQuant currency-strength trend-following strategy ("System B") is a
multi-timeframe trend-following system built on the hypothesis that currencies
have measurable relative strength and that trading the strongest currency
against the weakest produces a persistent directional edge.

This document reconstructs the strategy from source code. The strategy is
NOT a simple "EUR/USD goes up" prediction. It is a cross-sectional currency
strength decomposition followed by a multi-layered entry/exit framework.

---

## 2. Currency Universe

### 2.1 Eight Major Currencies

```
USD  United States Dollar
EUR  Euro
GBP  British Pound
JPY  Japanese Yen
CHF  Swiss Franc
CAD  Canadian Dollar
AUD  Australian Dollar
NZD  New Zealand Dollar
```

### 2.2 Pair Universe

**Legacy config (config.py) — 12 pairs:**
```
EUR/USD, USD/JPY, AUD/USD, GBP/USD, USD/CAD, USD/CHF,
NZD/USD, EUR/NZD, AUD/NZD, GBP/NZD, EUR/JPY, GBP/JPY
```

**New config (config/settings.py) — 28 pairs:**
```
All 28 unique pairs from 8 currencies (8C2 = 28)
```

**Tradeable pairs (used for actual entries) — 7 pairs:**
```
EUR/USD, GBP/USD, USD/JPY, AUD/USD,
NZD/USD, EUR/JPY, GBP/JPY
```

### 2.3 Universe Asymmetry

**Critical observation:** The 8 currencies do NOT participate symmetrically.

- USD appears in 5 of 7 tradeable pairs (EUR/USD, GBP/USD, USD/JPY, AUD/USD, NZD/USD)
- JPY appears in 3 of 7 tradeable pairs (USD/JPY, EUR/JPY, GBP/JPY)
- EUR appears in 3 of 7 tradeable pairs (EUR/USD, EUR/JPY, GBP/JPY is GBP)
- GBP appears in 3 of 7 tradeable pairs (GBP/USD, GBP/JPY, EUR/GBP is EUR)
- AUD appears in 2 of 7 tradeable pairs (AUD/USD, NZD/USD is NZD)
- NZD appears in 1 of 7 tradeable pairs (NZD/USD)
- CHF appears in 0 of 7 tradeable pairs
- CAD appears in 0 of 7 tradeable pairs

**This means:**
- CHF and CAD have NO representation in the tradeable universe
- Their strength is computed but never directly traded
- USD/JPY, EUR/USD, GBP/USD dominate the tradeable universe
- The "strongest vs weakest" signal is heavily biased toward USD and JPY

### 2.4 Pair Orientation

All pairs are quoted as BASE/QUOTE. A rising price means BASE strengthens
relative to QUOTE. This orientation is critical for correct strength
decomposition.

---

## 3. Currency Strength Calculation

### 3.1 Core Algorithm (`currency_strength.py`)

```python
# For each pair (BASE/QUOTE):
weighted_roc = Σ(ROC(close, period) × weight) for each (period, weight) in lookbacks

# Decompose into currency contributions:
contributions[BASE]  += weighted_roc      # BASE benefits when price rises
contributions[QUOTE] += -weighted_roc     # QUOTE suffers when price rises

# Average across all pairs containing each currency:
raw_strength[currency] = mean(contributions[currency])

# Normalize with rolling z-score:
z = (raw - rolling_mean) / rolling_std
strength[currency] = tanh(z) × 100  # Squash to [-100, +100]
```

### 3.2 Lookback Configuration

**Legacy config (config.py):**
```python
STRENGTH_LOOKBACKS = [(10, 0.40), (20, 0.30), (40, 0.20), (80, 0.10)]
STRENGTH_NORMALIZE_WINDOW = 200
```

**New config (config/settings.py):**
```python
STRENGTH_LOOKBACKS = [(5, 0.50), (10, 0.30), (20, 0.20)]
STRENGTH_NORMALIZE_WINDOW = 100
```

### 3.3 Mathematical Properties

**Input:** Close prices at 5min/15min/4h/1D timeframes
**Output:** DataFrame index=datetime, columns=currencies, values ∈ [-100, +100]

**Key properties:**
1. Positive score = strong currency, Negative = weak
2. Scores are **relative** (z-score normalized across history)
3. Rolling normalization avoids look-ahead bias
4. Tanh squashing bounds extreme values
5. Multi-period ROC reduces whipsaw vs single lookback

### 3.4 Example Calculation

At time t, with EUR/USD = 1.1000:

```
ROC(10) = (1.1000 - 1.0950) / 1.0950 × 100 = +0.457%
weighted = 0.457 × 0.40 + ROC(20) × 0.30 + ROC(40) × 0.20 + ROC(80) × 0.10

contributions["EUR"] += weighted_roc  (EUR strengthens)
contributions["USD"] += -weighted_roc  (USD weakens)
```

### 3.5 Known Issues

1. **Currency pair asymmetry**: CHF and CAD have strength computed but never traded
2. **Weighting sensitivity**: Different lookback weights produce different strength
3. **Normalization window**: 200 bars vs 100 bars changes score magnitude
4. **Missing pairs**: Strength computation uses ALL available pairs, but signal
   generation only uses tradeable pairs — potential information leakage

---

## 4. Signal Generation

### 4.1 Currency Ranking

```python
ranked = strength_df.iloc[bar_idx].sort_values(ascending=False)
# Result: [strongest, ..., weakest]
# Example: [GBP(+82), EUR(+61), USD(+31), ..., JPY(-87)]
```

### 4.2 Strongest vs Weakest Selection

```python
top_n = 4  # Top 4 and bottom 4 currencies
bottom_threshold = 8 - 4 = 4  # Index >= 4 = bottom N

# BUY signal:
#   base_rank < 4 (base is in top 4 strongest)
#   quote_rank >= 4 (quote is in bottom 4 weakest)
#   divergence >= 3.0

# SELL signal:
#   base_rank >= 4 (base is in bottom 4 weakest)
#   quote_rank < 4 (quote is in top 4 strongest)
#   divergence <= -3.0
```

### 4.3 Signal Interpretation

A BUY signal for EUR/USD means:
- EUR is among the 4 strongest currencies
- USD is among the 4 weakest currencies
- The strength gap between EUR and USD exceeds 3.0 points

**Economic hypothesis:** Currencies have persistent relative strength, and
the strongest-vs-weakest relationship reverts to the mean or trends further.

---

## 5. Entry Logic (Multi-Layer Filter Stack)

Entry requires ALL of the following:

### 5.1 Signal Check
- Pre-computed byte array: B (BUY), S (SELL), N (NONE)
- Based on currency strength ranking at current 5min bar

### 5.2 Divergence Check
```python
divergence = strength[base] - strength[quote]
if abs(divergence) < MIN_DIVERGENCE:  # MIN_DIVERGENCE = 3.0 (legacy) or 10.0 (new)
    skip  # Signal too weak
```

### 5.3 Macro Filter (4H EMA-200)
```python
# Pre-compute: 4H EMA-200 for each pair
ema200 = df_4h["close"].ewm(span=200).mean()
macro_bullish = df_4h["close"] > ema200  # True = uptrend

# At entry:
if direction == "BUY" and not macro_bullish[current_5m_bar]:
    skip  # Macro trend contradicts entry
if direction == "SELL" and macro_bullish[current_5m_bar]:
    skip
```

### 5.4 Regime Flip (Crisis Detection)
```python
# Pre-compute: 4H ATR vs its rolling average
atr4 = calculate_atr(df_4h, 14)
atr_avg = atr4.rolling(20).mean()
crisis = atr4 > atr_avg * 2.0  # ATR > 2× average = crisis

# At entry:
if crisis[current_5m_bar]:
    direction = SELL if direction == BUY else BUY  # Flip direction
```

### 5.5 Session Filter
```python
# Active window: 08:00-19:00 UTC (legacy) or 07:00-21:00 UTC (new)
# Skip weekends, Friday after 17:00
if not is_active_session(bar_time):
    skip
```

### 5.6 Max Entry Hour
```python
if bar_time.hour >= MAX_ENTRY_HOUR:  # Default: 21
    skip  # No new entries late in the day
```

### 5.7 Max Open Trades
```python
if len(open_trades) >= MAX_OPEN_TRADES:  # Default: 1
    skip
```

### 5.8 Opposing Direction Check
```python
if pair in active_directions:
    if active_directions[pair] != direction:
        skip  # Opposing trade on same pair
    if BLOCK_SAME_DIRECTION_REENTRY:
        skip  # Same-direction stacking blocked
```

### 5.9 Correlation Guard
```python
# Rolling 20-day correlation between tradeable pairs
# Block if |r| > 0.50 AND same direction
if abs(corr_matrix[pair1, pair2]) > 0.50 and same_direction:
    skip
```

### 5.10 Currency Block
```python
# No more than MAX_PER_CURRENCY_BLOCK (1) trades per currency
if currency_count[base] >= 1 or currency_count[quote] >= 1:
    skip
```

### 5.11 ATR-Based Position Sizing
```python
atr_val = atr_5min[current_bar]
sl_distance = ATR_SL_MULTIPLIER × atr_val  # Default: 2.0
entry_price = mid_price ± spread_cost
sl = mid_price ∓ sl_distance
tp = mid_price ± (sl_distance × RRR)  # RRR = 3.5

lot_size = risk_mgr.calculate_lot_size(pair, entry, sl, divergence)
```

---

## 6. Exit Logic

### 6.1 Stop Loss (SL)
- Set at entry: `entry_price ∓ ATR_SL_MULTIPLIER × ATR`
- Default ATR_SL_MULTIPLIER = 2.0

### 6.2 Take Profit (TP)
- Set at entry: `entry_price ± ATR_SL_MULTIPLIER × ATR × RRR`
- Default RRR = 3.5

### 6.3 Breakeven
```python
risk_distance = abs(entry_price - original_sl)
if profit >= BREAKEVEN_RATIO × risk_distance:  # BREAKEVEN_RATIO = 0.8
    sl = entry_price  # Move SL to breakeven
```

### 6.4 Session Close SL
```python
# 30 minutes before session close, move SL to breakeven
if hour >= (SESSION_CLOSE - 1) and minute >= (60 - 30):
    sl = entry_price  # Gap protection
```

### 6.5 Trend Reversal Exit (Level >= 1)
```python
# For promoted trades, check if trend still intact on active timeframe
if not trend_intact(active_tf, pair, direction):
    close at market  # "trend_reversal" exit
```

### 6.6 Recovery Exit
```python
# When floating profit >= 50% of accumulated loss, close to recover
if floating_pnl >= 0 and floating_pnl >= recovery_pnl × 0.5:
    close at market  # "recovery_exit"
```

### 6.7 Promotion Ladder
When TP is hit, the trade is promoted to the next timeframe:
```
Level 0 (5min) → Level 1 (15min) → Level 2 (4H) → Level 3 (1D)
```
- SL moves to entry (breakeven)
- New TP set at current price + RRR × next-timeframe ATR
- If trend no longer intact on next TF, trade closes at TP

---

## 7. Risk Management

### 7.1 Position Sizing
```python
risk_per_trade = 0.0023  # 0.23% of balance
# or
risk_per_trade = 0.03    # 3% of balance (new config)
```

### 7.2 Max Concurrent Positions
```python
MAX_OPEN_TRADES = 1  # Legacy
MAX_CONCURRENT_POSITIONS = 2  # New config
```

### 7.3 Currency Concentration
```python
MAX_PER_CURRENCY_BLOCK = 1  # Max 1 trade per currency
```

### 7.4 Drawdown Limits
```python
MAX_DD_PCT = 55.0          # 55% max drawdown
DD_REDUCE_THRESHOLD = 30.0  # Reduce risk at 30% DD
DD_REDUCED_RISK = 0.02      # 2% risk in reduced mode
```

### 7.5 Daily Loss Limit
```python
MAX_DAILY_LOSS_PCT = 0.03  # 3% daily loss limit
```

---

## 8. Cost Model

### 8.1 Spread (Legacy config)
```python
SPREAD_PIPS = {
    'EUR/USD': 0.2, 'GBP/USD': 0.3, 'USD/JPY': 0.2,
    'USD/CHF': 0.3, 'USD/CAD': 0.3, 'AUD/USD': 0.3,
    'NZD/USD': 0.3, 'EUR/NZD': 0.5, 'AUD/NZD': 0.5,
    'GBP/NZD': 0.5, 'EUR/JPY': 0.3, 'GBP/JPY': 0.3,
}
```

### 8.2 Spread (New config — Exness Standard)
```python
SPREAD_PIPS = {
    "EUR/USD": 0.8, "GBP/USD": 1.0, "USD/JPY": 1.0,
    "USD/CHF": 1.2, "USD/CAD": 1.4, "AUD/USD": 0.9,
    "NZD/USD": 1.2, "EUR/JPY": 1.6, "GBP/JPY": 2.0,
}
```

### 8.3 Slippage
```python
SLIPPAGE_PIPS = 0.1
```

### 8.4 Commission
```python
COMMISSION_PER_LOT = 5.0  # Legacy
COMMISSION_PER_LOT = 6.0  # New config
```

### 8.5 Total Cost Calculation
```python
spread_cost = (spread_pips / 2 + slippage_pips) × pip_size(pair)
entry_price = mid_price + spread_cost  # For BUY
entry_price = mid_price - spread_cost  # For SELL
```

---

## 9. Timeframe Structure

### 9.1 Timeframe Ladder
```python
B_TF_LADDER = ["1min", "5min", "15min", "4h", "1D"]
B_TF_LABELS = ["1M", "5M", "15M", "4H", "1D"]
```

### 9.2 Signal Timeframe
- **Entry signals generated at:** 5min
- **Macro filter:** 4H EMA-200
- **Regime detection:** 4H ATR
- **Correlation:** 1D daily returns
- **Promotion path:** 5min → 15min → 4H → 1D

---

## 10. What is Known vs Inferred vs Unknown

### 10.1 KNOWN (from source code)
- Exact currency strength algorithm (multi-period ROC + z-score + tanh)
- Exact signal generation logic (top-N/bottom-N + divergence threshold)
- Exact entry filter stack (8+ conditions)
- Exact exit logic (SL/TP/breakeven/trend reversal/recovery)
- Exact promotion ladder (5min → 15min → 4H → 1D)
- Exact cost model (spread + slippage + commission)
- Exact risk management (position sizing, max DD, daily loss)

### 10.2 INFERRED (from code patterns)
- The strategy was developed for GFT (prop firm) with $1000 balance
- The 12-pair legacy universe was later expanded to 28 pairs
- The tradeable universe was narrowed to 7 pairs for signal generation
- CHF and CAD are computed but never traded in the tradeable universe

### 10.3 UNKNOWN (not in code)
- Whether the strategy was profitable in live trading
- Why only 7 pairs were selected as tradeable
- Why CHF and CAD were excluded from tradeable pairs
- Whether the promotion ladder was backtested or intuition-based
- The actual live performance record
- Whether the strategy survived walk-forward validation
- Whether the currency-strength hypothesis itself has edge

---

## 11. Core Economic Hypothesis

**The strategy's fundamental claim:**

> "Currencies have measurable relative strength. Trading the strongest
> currency against the weakest produces a persistent, directional,
> economically exploitable trend."

**This is what Phase 9C must test.**

The entire multi-layer filter stack (macro, regime, session, correlation,
promotion) is secondary. The CORE question is:

**Does the strongest-vs-weakest relationship contain economic edge BEFORE
any filters?**

If yes → the filters may improve it.
If no → the filters are masking a weak signal.

---

## 12. Reconstruction Checklist for Phase 9C

| Component | Source File | Status |
|-----------|-------------|--------|
| Currency strength | `currency_strength.py` | ✅ Reconstructed |
| Signal generation | `currency_strength.py` | ✅ Reconstructed |
| Entry filters | `backtest_hybrid_opt.py` | ✅ Reconstructed |
| Exit logic | `backtest_hybrid_opt.py` | ✅ Reconstructed |
| Cost model | `config.py` | ✅ Reconstructed |
| Risk management | `risk_manager.py` | ✅ Reconstructed |
| Session filter | `indicators/session.py` | ✅ Reconstructed |
| Promotion ladder | `backtest_hybrid_opt.py` | ✅ Reconstructed |
| Macro filter | `backtest_hybrid_opt.py` | ✅ Reconstructed |
| Regime flip | `backtest_hybrid_opt.py` | ✅ Reconstructed |
| Correlation guard | `backtest_hybrid_opt.py` | ✅ Reconstructed |

---

## 13. Next Steps

1. Phase 2: Verify currency universe mathematically
2. Phase 3: Reconstruct currency strength with unit tests
3. Phase 4: Test strongest-vs-weakest economic signal
4. Phase 5: Baseline economic test (raw strength, no filters)
5. Phase 6-16: Progressive ablation and validation
6. Phase 17: Final research decision

---

## 14. Known Ambiguities

1. **Two config files** with different parameters:
   - `config.py`: STRENGTH_LOOKBACKS = [(10, 0.40), (20, 0.30), (40, 0.20), (80, 0.10)]
   - `config/settings.py`: STRENGTH_LOOKBACKS = [(5, 0.50), (10, 0.30), (20, 0.20)]
   - **Decision:** Use `config.py` (legacy) for reconstruction, as it matches the original System B

2. **Two different MIN_DIVERGENCE values:**
   - `config.py`: MIN_DIVERGENCE = 3.0
   - `config/settings.py`: MIN_DIVERGENCE = 10.0
   - **Decision:** Test both, but start with 3.0 as it's the original

3. **Tradeable pairs differ:**
   - Legacy: 12 pairs
   - New: 7 pairs (EUR/USD, GBP/USD, USD/JPY, AUD/USD, NZD/USD, EUR/JPY, GBP/JPY)
   - **Decision:** Use the 7 tradeable pairs for signal generation, all 12+ for strength computation

4. **RRR inconsistency:**
   - `config.py`: RRR = 3.5
   - `config/settings.py`: RRR = 2.0
   - **Decision:** Use 3.5 (legacy) as it matches the original

5. **Account balance:**
   - `config.py`: INITIAL_BALANCE = 1000
   - `config/settings.py`: INITIAL_BALANCE = 200
   - **Decision:** Use $1000 (legacy) for consistency with original System B
