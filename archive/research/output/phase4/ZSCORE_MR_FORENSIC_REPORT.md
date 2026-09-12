# Z-Score Mean-Reversion Strategy — Forensic Report

**Date:** 2026-08-14
**Strategy:** Z-Score MR (causal rolling Z-score with session filter)
**Data:** 20 FX pairs, 2016-01-01 to 2026-07-19, 30min bars
**Config:** Z_entry=2.2, Z_exit=0.5, Lookback=20, Risk=0.6%, ATR_SL=3.0x, RR=2.0
**Commission:** $3.50/lot/RT | **Slippage:** 0.3 pips | **Session:** London 07-16, NY 12-21 UTC

---

## 1. Executive Summary

The Z-score mean-reversion strategy is a **break-even/slightly negative** system with high trade frequency and extreme tail risk.

| Metric | Value |
|---|---|
| Trades | 74,775 |
| Win Rate | 59.02% |
| Profit Factor | 0.98 |
| Net P&L | -$2,013 |
| Avg P&L/trade | -$0.03 |
| Median P&L/trade | +$0.63 |
| Max Drawdown | **91.95%** |
| Z-entry range | [-41.43, +34.74] |

**Key finding:** The strategy has a positive win rate (59%) but losses are larger than wins ($3.75 vs $2.56). The "edge" is entirely consumed by the asymmetric loss distribution.

---

## 2. Trade-Level Statistics

### 2.1 Exit Distribution
| Exit | Count | % | Description |
|---|---|---|---|
| ZE (Z-score exit) | 42,799 | 57.2% | Mean reversion target hit |
| SC (session close) | 16,049 | 21.5% | Forced exit at session boundary |
| SL (stop loss) | 14,249 | 19.1% | ATR-based stop hit |
| DL (daily limit) | 1,271 | 1.7% | 5% daily loss limit |
| TP (take profit) | 387 | 0.5% | RR-based TP hit |

**Critical observation:** Only 0.5% of trades hit TP. The 2:1 RR target is almost never reached. The strategy exits primarily via Z-score return to mean (57%) or session close (22%).

### 2.2 P&L Distribution
- **Avg Win:** +$2.56
- **Avg Loss:** -$3.75
- **Win/Loss ratio:** 0.68 (losses are 47% larger than wins)
- **Median P&L:** +$0.63 (positive — most trades are small winners)
- **Mean P&L:** -$0.03 (negative — a few large losses drag the average)

The distribution is **negatively skewed**: many small wins, fewer but larger losses.

---

## 3. Z-Score Magnitude Binning

| |Z| Range | Trades | Win Rate | PF | Net P&L | Avg P&L |
|---|---|---|---|---|---|---|
| 2-3 | 46,307 | 60.4% | 0.99 | -$761 | -$0.02 |
| 3-4 | 17,971 | 57.6% | 0.96 | -$1,316 | -$0.07 |
| 4-5 | 5,730 | 55.6% | 0.93 | -$701 | -$0.12 |
| 5-6 | 2,306 | 55.9% | **1.09** | **+$360** | **+$0.16** |
| ≥6 | 2,441 | 55.0% | **1.09** | **+$405** | **+$0.17** |

### Critical Finding
**Extreme Z-scores (|Z|≥5) are the ONLY profitable segment.** The strategy bleeds most in the moderate Z-score range (3-5). This is the opposite of what a "catastrophic event" narrative would suggest.

The "one extreme event around Z≈6" that erased accumulated profit is **not what the data shows**. Instead:
- 74,775 trades at PF=0.98 produce cumulative losses
- Extreme Z-score trades are profitable but too few to offset the bleed
- The catastrophic drawdown (91.95%) comes from cumulative compounding losses, not a single event

---

## 4. Per-Period Breakdown

| Period | Trades | Win Rate | PF | Net P&L |
|---|---|---|---|---|
| 2016-2018 | 21,798 | 59.4% | 0.98 | -$1,321 |
| 2019-2021 | 21,397 | 59.0% | 0.98 | -$578 |
| 2022-2024 | 20,577 | 58.1% | 0.98 | -$319 |
| 2025-2026 | 10,983 | 60.0% | **1.02** | **+$204** |

**The strategy is consistently negative across all periods except the most recent (2025-2026).** The recent positive performance may be regime-dependent rather than a structural edge.

---

## 5. Tail-Risk Analysis

### 5.1 Extreme Z-Score Trades (|Z| ≥ 5)
- **Count:** 4,747 trades (6.3% of total)
- **Worst single trade:** NZD/USD Z=-5.60, P&L=$-17.50 (daily limit exit)
- **Best single trade:** AUD/CHF Z=-5.99, P&L=$+26.81 (take profit)
- **Mean P&L of extreme trades:** ~$0.16 (positive)

### 5.2 Maximum Drawdown
- **91.95%** — the strategy nearly wiped the account
- This is not from a single Z≈6 event but from cumulative compounding losses
- With 74,775 trades at PF=0.98, the law of large numbers guarantees negative expected value

### 5.3 Z-Score Extremes Observed
- **Minimum Z:** -41.43 (extreme overshoot)
- **Maximum Z:** +34.74 (extreme overshoot)
- These extreme values indicate the rolling Z-score can reach very large values during sustained trends

---

## 6. ATR-Normalized Exposure

| Metric | Value |
|---|---|
| Mean SL/ATR ratio | 3.03 |
| Median SL/ATR ratio | 3.03 |
| Std | 0.02 |
| P25-P75 | 3.02-3.04 |

The SL is consistently placed at 3.0x ATR, confirming the ATR_SL_MULT=3.0 parameter is applied correctly. The tight distribution (std=0.02) shows the SL placement is highly consistent.

---

## 7. Bootstrap Robustness (2,000 iterations)

| Metric | Mean | 95% CI |
|---|---|---|
| Win Rate | 59.01% | [58.67%, 59.36%] |
| Profit Factor | 0.982 | [0.963, 1.002] |
| Mean Trade | -$0.027 | [-$0.058, +$0.003] |

**The profit factor CI straddles 1.0** — we cannot reject the null hypothesis that the strategy is break-even. The mean trade CI includes zero. The strategy has no statistically significant edge.

---

## 8. Root Cause Analysis

### Why the strategy fails:
1. **Asymmetric P&L:** Avg loss ($3.75) is 47% larger than avg win ($2.56)
2. **Low TP hit rate:** Only 0.5% of trades hit the 2:1 RR target
3. **High trade frequency:** 74,775 trades amplify small negative expectancy
4. **Session close forced exits:** 21.5% of trades are forcibly closed, preventing mean reversion from completing
5. **SL placement too wide:** 3.0x ATR SL allows large losses before stopping out

### Why extreme Z-scores are profitable:
- Extreme Z-scores (|Z|≥5) represent genuine mean-reversion opportunities
- But they are rare (6.3% of trades) and cannot offset the systematic bleed from moderate Z-scores
- The strategy enters too early (at |Z|=2.2) before mean reversion is confirmed

---

## 9. Recommendations

1. **Do not deploy this strategy as-is** — it has no statistically significant edge
2. **Consider raising Z_entry threshold** — entering at |Z|≥4 or |Z|≥5 would capture only the profitable segment
3. **Reduce trade frequency** — fewer trades at higher conviction would improve expectancy
4. **Re-evaluate SL placement** — 3.0x ATR may be too wide; consider tighter stops
5. **Session close exits are costly** — 21.5% of trades are forced closed, often at a loss

---

## 10. Data Files

- Full results: `research_data/phase4/zscore_mr_backtest.json`
- Trade log: `research_data/phase4/zscore_mr_trades.json`
- Backtest script: `scripts/zscore_mr_backtest.py`

---

*Report generated 2026-08-14. Strategy is causal — no lookahead used.*
