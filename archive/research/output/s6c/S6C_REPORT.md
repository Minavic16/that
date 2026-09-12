# S6C-2026-001: Causal Swing Lookahead Quantification

- Git commit: `0a0377bc7d4dd223cd820cb854637478f2697e3a`
- Pairs loaded: 20 | missing: ['USD/CAD', 'EUR/JPY', 'EUR/NZD', 'GBP/CHF', 'GBP/NZD', 'CHF/JPY', 'AUD/NZD', 'NZD/CAD']
- Config: frozen S6 (lookback=5, atr=14, slmult=2.0, rrr=3.5), base costs, flat risk

| Metric | A research | B causal |
|---|---|---|
| Signals affected | 0.05% delayed/lost | unconfirmed usage: 0 |
| Trades | 15319 | 16014 |
| Win rate | 0.3567 | 0.3615 |
| Profit factor | 2.0068 | 1.9527 |
| Expectancy (pip/trade) | 18.4316 | 17.4844 |
| Total net pnl (pip) | 282354.02 | 279994.38 |
| Max DD (R) | 19.5 | 18.03 |

See JSON for per-pair and period breakdowns.

## Findings

1. **Reproduction fidelity.** Variant A (imported, unmodified research code) on
   reacquired Dukascopy H4 data reproduces the published S6 baseline essentially
   exactly (WR 35.67% vs 35.7%, PF 2.0068 vs 2.01, expectancy +18.43 vs +18.44
   pip/trade, 8 losing months). Data and pipeline are faithful.

2. **Entry signals are structurally immune.** A swing at bar j with
   j+lookback >= decision bar i cannot be crossed by close[i], because
   confirmation requires the swing extreme to dominate through bar j+lookback.
   Empirically: 0 of 19,087 research signals referenced an unconfirmed swing;
   99.95% of variant-A signals reproduce identically under the causal series
   (0 delayed, 9 lost = 0.05%).

3. **Residual impact flows through trade management.** The effective swing
   series differs on ~32% of bars; entries are unaffected (self-limiting
   condition), but trailing-stop levels differ during trades. Causal variant:
   +695 trades (+4.5%), PF -2.7%, expectancy -5.1%, win rate +0.48pp,
   max DD improves 19.5R -> 18.03R, losing months 8 -> 11. Total net pnl is
   nearly unchanged (282,354 vs 279,994 pip).

4. **Verdict.** The original S6 conclusion SURVIVES strictly causal execution.
   The S3 causality test's reasoning was flawed but its conclusion was
   directionally correct for entries; it missed the smaller trailing-stop effect.

## Causal signal definition required for live (if S7 proceeds)

- Swing detection: centered window [j-5, j+5] on H4 highs/lows (identical rule).
- Availability: a swing detected at bar j may be USED only from the close of
  bar j+lookback (equivalent to `indicators/swing.py` `.shift(lookback)`).
- Signal at close of bar i: BUY if close[i-1] <= last_available_swing_high < close[i];
  SELL if close[i-1] >= last_available_swing_low > close[i].
- Entry next bar open; SL = entry -/+ 2.0 * ATR(14); TP = 3.5R; move SL to
  breakeven when price covers 0.8R; trail SL/TP levels with last AVAILABLE
  swing low/high only; exit after 42 bars if neither hit.

