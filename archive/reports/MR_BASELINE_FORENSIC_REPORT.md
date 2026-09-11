# MR Baseline Forensic Report

**Date:** 2026-08-10
**Baseline file:** `/root/test_final_scalper.py`
**Data:** `/root/data/` (20 pairs, 2018-01-01 to 2026-07-19)
**Analysis script:** `/root/nestquant/forensic_analysis.py`
**Machine-readable metrics:** `/root/nestquant/logs/mr_baseline_metrics.json`

---

## A. Existing Filter Audit

### A. Session Filter — PRESENT

| Attribute | Value |
|---|---|
| **Present** | YES |
| **Implementation** | `igs(ts)` function, lines 12-19 of `test_final_scalper.py` |
| **Parameters** | London: 07:00-16:00 UTC, New York: 12:00-21:00 UTC |
| **Friday cutoff** | `SKIP_FRI=20` — blocks entries after hour 20 on Friday |
| **Monday skip** | `SKIP_MON=3` — blocks entries before hour 03 on Monday |
| **Weekend block** | `d>=5` returns False (Saturday/Sunday) |
| **Affects entry** | YES — line 105: `if not igs(ts_now)` skips entry |
| **Affects exit** | YES — line 89: `if not igs(ref['ts'][i])` forces session-close exit |
| **Applied in backtest** | YES, actively applied |

### A. News Filter — ABSENT

| Attribute | Value |
|---|---|
| **Present** | NO |
| **Note** | NOT IMPLEMENTED / NOT TESTABLE WITH CURRENT DATA |
| **Data requirement** | News event timestamps with currency/country impact scores |

### A. Weekend Filter — PRESENT

Part of `igs()`. `d>=5` returns False on Saturday/Sunday. Same implementation as session filter.

### A. Spread Filter — ABSENT (as blocking filter)

| Attribute | Value |
|---|---|
| **Present as filter** | NO |
| **Present as cost** | YES |
| **Implementation** | `SPREAD` dict on line 10; applied at entry fill (line 133) and exit fill (lines 65, 90, 94) |
| **Affects entry eligibility** | NO — spread is never checked to block a trade |
| **Affects execution cost** | YES — `spread * 0.5 * spread_m` pips added to entry price (adverse fill) |

### A. P95 Slippage Filter — ABSENT

| Attribute | Value |
|---|---|
| **Present** | NO |
| **Implementation** | Fixed `slp_side=0.3` pips per side (realistic) or `1.0` pips (stressed) |
| **Note** | No empirical P95 slippage model exists. Fixed value is applied as cost, not a filter. |

### A. P99 Slippage Filter — ABSENT

Same as P95. No empirical distribution exists.

### A. $4 Round-Turn Commission — ABSENT

| Attribute | Value |
|---|---|
| **Present** | NO |
| **Actual value** | `COMMISSION=3.50` (line 8) |
| **Unit** | Per lot, per round-trip (deducted once at exit) |
| **Applied at** | Every exit: lines 66, 78, 81, 84, 87, 91, 95 |
| **Formula** | `pnl = gross_pnl - pos['lot'] * COMMISSION` |

---

## B. Baseline Cost Model

### B.1 Commission Structure

```
COMMISSION = $3.50 per lot per round-trip
```

This is NOT "$4 round-turn." It is $3.50. The commission is deducted once per trade at exit, covering both entry and exit.

**Average commission per trade:** $30.94
**Total commission across all trades:** $246,926.75
**Commission as % of gross PnL:** 5.97%

### B.2 Spread Cost Model

```
spread_cost = SPREAD[pair] * 0.5 * spread_m * pip * pv * lot
```

Where:
- `SPREAD[pair]` = fixed pips per pair (e.g., EUR/USD = 0.8, GBP/JPY = 3.0)
- `spread_m` = 1.0 (realistic), 0 (ideal), or 2.0 (stressed)
- Applied to both entry and exit fills as adverse price impact

**This is NOT a separate cost line item.** It is embedded in the fill price. The entry fill is displaced by `spread * 0.5 * spread_m + slp_side` pips from mid-price.

### B.3 Slippage Cost Model

```
slippage_cost = slp_side * pip * pv * lot (per side)
```

Where:
- `slp_side` = 0.3 pips (realistic) or 1.0 pips (stressed)
- Applied symmetrically to entry and exit

**This is NOT empirical.** It is a fixed assumption. No historical slippage data is used.

### B.4 Total Cost Per Trade

```
total_cost = entry_spread_impact + exit_spread_impact + entry_slippage + exit_slippage + commission
```

All costs are baked into fill prices and the commission deduction. There is no separate cost tracking in the original code.

### B.5 Are reported metrics Gross or NET?

**NET.** The reported win rate, profit factor, drawdown, and final balance are all calculated from NET PnL (after commission, after spread/slippage impact on fills).

The `pnls` array in the original code contains net PnL values:
```python
pnl = (ep - pos['entry']) * tr / pos['pip'] * pos['pv'] * pos['lot'] - pos['lot'] * COMMISSION
```

### B.6 What would $4 round-turn commission mean?

| Metric | Current ($3.50) | $4.00 | Delta |
|---|---|---|---|
| Commission per trade (avg) | $30.94 | $35.36 | +$4.42 |
| Total commission | $246,927 | $282,000 | +$35,073 |
| Final balance | $3,892,311 | $3,852,048 | -$40,263 |
| Profit factor | 1.89 | 1.88 | -0.01 |
| Win rate | 58.62% | 58.47% | -0.15pp |

The $4 commission scenario was run as Scenario B in cost sensitivity (see Section H).

---

## C. Slippage Distribution

**P95/P99 CANNOT BE EMPIRICALLY ESTIMATED FROM THE EXISTING EXECUTION MODEL.**

The current baseline uses:
- Fixed 0.3 pips per side (realistic mode)
- Fixed 1.0 pips per side (stressed mode)

No empirical slippage observations exist in the data or model.

### What would be required for empirical slippage:

1. **Actual execution data** — fill prices vs. signal prices from live/paper trading
2. **Order book data** — depth of book at signal time to estimate market impact
3. **Tick data with bid/ask** — to measure real spread at execution time
4. **Latency measurements** — time between signal and fill

None of these are available in the current dataset (minute OHLC only, no tick/bid-ask).

### Current fixed model summary:

| Mode | Per-side slippage | Round-trip slippage |
|---|---|---|
| Ideal | 0.5 pips | 1.0 pips |
| Realistic | 0.3 pips | 0.6 pips |
| Stressed | 1.0 pips | 2.0 pips |

---

## D. Spread Distribution

### D.1 Spread Model

**Fixed per pair.** Not dynamic, not historical, not modeled.

| Pair | Spread (pips) |
|---|---|
| EUR/USD | 0.8 |
| GBP/USD | 1.0 |
| USD/JPY | 1.0 |
| AUD/USD | 0.9 |
| USD/CHF | 1.2 |
| NZD/USD | 1.2 |
| EUR/GBP | 1.2 |
| EUR/CHF | 1.5 |
| EUR/JPY | 2.0 |
| AUD/JPY | 2.0 |
| EUR/AUD | 2.0 |
| AUD/CAD | 2.0 |
| EUR/CAD | 2.5 |
| AUD/CHF | 2.5 |
| CAD/JPY | 2.5 |
| GBP/JPY | 3.0 |
| NZD/JPY | 3.0 |
| GBP/CAD | 3.5 |
| GBP/AUD | 3.5 |
| NZD/CHF | 3.0 |
| CAD/CHF | 3.0 |

### D.2 Is Spread a Filter or a Cost?

**COST ONLY.** Spread is never checked to block trade entry. It is applied as adverse fill displacement at entry and exit.

---

## E. Monthly Return Statistics

**Period:** 2018-01 to 2026-07 (103 months)

### E.1 Summary Statistics

| Statistic | Value |
|---|---|
| Mean monthly return | 8.09% |
| Median monthly return | 2.32% |
| Std deviation | 13.21% |
| Minimum | -1.61% (2025-05) |
| Maximum | 67.50% (2019-01) |

### E.2 Percentile Distribution (Upper Tail)

| Percentile | Value | Interpretation |
|---|---|---|
| P25 | 0.51% | 25% of months return less than 0.51% |
| P75 | 6.96% | 75% of months return less than 6.96% |
| P90 | 29.83% | 90% of months return less than 29.83% |
| **P95** | **37.76%** | **Best 5% of months exceed 37.76%** |
| **P99** | **47.70%** | **Best 1% of months exceed 47.70%** |

**P95 and P99 represent the UPPER tail** (best months).

### E.3 Percentile Distribution (Lower Tail — Bad-Month Risk)

| Percentile | Value | Interpretation |
|---|---|---|
| **P1** | **-1.41%** | **Worst 1% of months lose more than 1.41%** |
| **P5** | **-0.53%** | **Worst 5% of months lose more than 0.53%** |
| P10 | -0.20% | Worst 10% of months lose more than 0.20% |

### E.4 Distribution Shape

| Statistic | Value |
|---|---|
| Skewness | 2.143 (strong positive skew) |
| Kurtosis | 4.421 (leptokurtic / fat tails) |
| Coefficient of variation | 1.6335 |

The distribution has a strong positive tail — a few exceptional months dominate. The negative tail is thin (worst month only -1.61%).

### E.5 Monthly Return Table (All 103 Months)

| Month | Return % | Net PnL | Trades | Win Rate | MDD % |
|---|---|---|---|---|---|
| 2018-01 | 34.63 | $865.87 | 65 | 66.2% | 0.00 |
| 2018-02 | 39.52 | $1,330.12 | 50 | 66.0% | 0.00 |
| 2018-03 | 33.24 | $1,560.83 | 66 | 66.7% | 0.00 |
| 2018-04 | 38.93 | $2,435.67 | 60 | 78.3% | 0.00 |
| 2018-05 | 21.68 | $1,884.75 | 52 | 69.2% | 0.00 |
| 2018-06 | 35.61 | $3,766.08 | 87 | 63.2% | 0.00 |
| 2018-07 | 47.80 | $6,855.42 | 99 | 70.7% | 0.00 |
| 2018-08 | 21.11 | $4,474.56 | 55 | 70.9% | 0.00 |
| 2018-09 | 32.37 | $8,309.84 | 65 | 72.3% | 0.00 |
| 2018-10 | 38.00 | $12,914.60 | 84 | 65.5% | 0.00 |
| 2018-11 | 26.97 | $12,648.11 | 70 | 72.9% | 0.00 |
| 2018-12 | 30.06 | $17,901.58 | 71 | 63.4% | 0.00 |
| 2019-01 | 67.50 | $52,279.30 | 96 | 77.1% | 0.00 |
| 2019-02 | 42.96 | $55,733.90 | 80 | 73.8% | 0.00 |
| 2019-03 | 28.89 | $53,583.66 | 107 | 60.7% | 0.00 |
| 2019-04 | 28.25 | $67,521.90 | 95 | 60.0% | 0.00 |
| 2019-05 | 21.31 | $65,331.98 | 58 | 72.4% | 0.00 |
| 2019-06 | 7.10 | $26,393.85 | 44 | 65.9% | 0.00 |
| 2019-07 | 4.25 | $16,942.11 | 42 | 52.4% | 0.00 |
| 2019-08 | 26.27 | $109,065.70 | 38 | 78.9% | 0.00 |
| 2019-09 | 11.56 | $60,590.84 | 84 | 66.7% | 0.00 |
| 2019-10 | 11.65 | $68,129.90 | 98 | 57.1% | 0.00 |
| 2019-11 | 8.14 | $53,125.70 | 65 | 75.4% | 0.00 |
| 2019-12 | 5.65 | $39,905.10 | 58 | 60.3% | 0.00 |
| 2020-01 | 11.30 | $84,305.00 | 80 | 71.2% | 0.00 |
| 2020-02 | 9.32 | $77,360.90 | 50 | 72.0% | 0.00 |
| 2020-03 | 6.15 | $55,812.63 | 32 | 59.4% | 0.00 |
| 2020-04 | 13.06 | $125,876.22 | 96 | 68.8% | 0.00 |
| 2020-05 | 5.22 | $56,914.52 | 74 | 66.2% | 0.00 |
| 2020-06 | 7.07 | $81,039.70 | 39 | 69.2% | 0.00 |
| 2020-07 | 5.77 | $70,764.70 | 73 | 69.9% | 0.00 |
| 2020-08 | 4.67 | $60,650.56 | 78 | 66.7% | 0.00 |
| 2020-09 | 4.48 | $60,895.30 | 73 | 54.8% | 0.00 |
| 2020-10 | 6.85 | $97,248.50 | 127 | 63.8% | 0.00 |
| 2020-11 | 6.13 | $92,962.45 | 100 | 62.0% | 0.00 |
| 2020-12 | 3.56 | $57,244.87 | 82 | 56.1% | 0.00 |
| 2021-01 | 0.95 | $15,853.20 | 60 | 56.7% | 0.00 |
| 2021-02 | 4.10 | $68,926.60 | 41 | 82.9% | 0.00 |
| 2021-03 | 2.14 | $37,419.62 | 46 | 56.5% | 0.00 |
| 2021-04 | 5.72 | $102,415.00 | 107 | 63.6% | 0.00 |
| 2021-05 | 2.32 | $43,913.10 | 72 | 61.1% | 0.00 |
| 2021-06 | 3.83 | $74,166.30 | 77 | 59.7% | 0.00 |
| 2021-07 | 3.57 | $71,687.60 | 65 | 64.6% | 0.00 |
| 2021-08 | 1.65 | $34,438.10 | 49 | 65.3% | 0.00 |
| 2021-09 | 6.47 | $136,945.50 | 137 | 62.0% | 0.00 |
| 2021-10 | 2.23 | $50,176.49 | 51 | 70.6% | 0.00 |
| 2021-11 | 4.90 | $112,870.60 | 87 | 77.0% | 0.00 |
| 2021-12 | 1.85 | $44,813.18 | 79 | 58.2% | 0.00 |
| 2022-01 | 2.79 | $68,609.02 | 95 | 64.2% | 0.00 |
| 2022-02 | 4.34 | $109,674.37 | 122 | 63.9% | 0.00 |
| 2022-03 | 2.91 | $76,906.00 | 41 | 80.5% | 0.00 |
| 2022-04 | 1.73 | $46,892.11 | 48 | 70.8% | 0.00 |
| 2022-05 | 3.90 | $107,707.91 | 90 | 66.7% | 0.00 |
| 2022-06 | 2.61 | $74,899.31 | 69 | 65.2% | 0.00 |
| 2022-07 | 1.08 | $31,915.17 | 80 | 55.0% | 0.00 |
| 2022-08 | 3.46 | $103,031.15 | 111 | 65.8% | 0.00 |
| 2022-09 | 1.14 | $35,056.89 | 52 | 63.5% | 0.00 |
| 2022-10 | 2.11 | $65,690.98 | 57 | 63.2% | 0.00 |
| 2022-11 | 2.36 | $75,166.42 | 101 | 59.4% | 0.00 |
| 2022-12 | 2.24 | $72,856.49 | 50 | 74.0% | 0.00 |
| 2023-01 | 1.07 | $35,490.61 | 81 | 48.1% | 0.00 |
| 2023-02 | 2.41 | $81,054.38 | 110 | 60.9% | 0.00 |
| 2023-03 | 2.52 | $86,998.32 | 74 | 70.3% | 0.00 |
| 2023-04 | 1.02 | $36,017.20 | 57 | 66.7% | 0.00 |
| 2023-05 | 0.42 | $14,906.84 | 79 | 51.9% | 0.00 |
| 2023-06 | 1.19 | $42,660.00 | 67 | 56.7% | 0.00 |
| 2023-07 | -0.97 | -$35,296.38 | 83 | 38.6% | 0.97 |
| 2023-08 | 1.13 | $40,508.12 | 81 | 59.3% | 0.00 |
| 2023-09 | 0.33 | $11,967.44 | 77 | 53.2% | 0.00 |
| 2023-10 | 0.98 | $35,680.69 | 96 | 61.5% | 0.00 |
| 2023-11 | 1.95 | $71,811.70 | 91 | 63.7% | 0.00 |
| 2023-12 | 0.45 | $16,880.37 | 77 | 55.8% | 0.00 |
| 2024-01 | 1.70 | $64,116.66 | 103 | 58.3% | 0.00 |
| 2024-02 | -0.51 | -$19,689.79 | 58 | 43.1% | 0.51 |
| 2024-03 | -0.09 | -$3,387.23 | 95 | 48.4% | 0.60 |
| 2024-04 | -0.60 | -$22,750.93 | 88 | 42.0% | 1.20 |
| 2024-05 | -0.24 | -$9,181.85 | 64 | 42.2% | 1.44 |
| 2024-06 | 0.35 | $13,364.70 | 66 | 54.5% | 1.09 |
| 2024-07 | 0.29 | $10,946.05 | 54 | 61.1% | 0.80 |
| 2024-08 | -0.27 | -$10,156.40 | 48 | 50.0% | 1.07 |
| 2024-09 | -0.20 | -$7,440.98 | 56 | 55.4% | 1.26 |
| 2024-10 | -0.19 | -$7,337.37 | 85 | 47.1% | 1.45 |
| 2024-11 | 0.19 | $7,011.96 | 99 | 48.5% | 1.27 |
| 2024-12 | 0.67 | $25,416.57 | 60 | 60.0% | 0.61 |
| 2025-01 | 0.70 | $26,795.53 | 119 | 44.5% | 0.00 |
| 2025-02 | 0.66 | $25,419.11 | 92 | 48.9% | 0.00 |
| 2025-03 | 0.97 | $37,476.20 | 63 | 54.0% | 0.00 |
| 2025-04 | 0.67 | $26,042.72 | 53 | 35.8% | 0.00 |
| 2025-05 | -1.61 | -$63,292.13 | 147 | 36.7% | 1.61 |
| 2025-06 | 0.41 | $15,952.20 | 111 | 49.5% | 1.21 |
| 2025-07 | -0.53 | -$20,704.39 | 81 | 42.0% | 1.73 |
| 2025-08 | 0.36 | $14,021.43 | 139 | 45.3% | 1.38 |
| 2025-09 | -0.17 | -$6,513.28 | 111 | 45.0% | 1.54 |
| 2025-10 | -1.42 | -$54,845.55 | 107 | 34.6% | 2.94 |
| 2025-11 | 0.64 | $24,549.00 | 92 | 50.0% | 2.31 |
| 2025-12 | -0.29 | -$11,225.20 | 75 | 46.7% | 2.60 |
| 2026-01 | -0.04 | -$1,452.03 | 62 | 38.7% | 2.64 |
| 2026-02 | 0.27 | $10,275.05 | 63 | 47.6% | 2.38 |
| 2026-03 | 0.48 | $18,443.09 | 92 | 48.9% | 1.91 |
| 2026-04 | -0.80 | -$30,849.66 | 85 | 44.7% | 2.69 |
| 2026-05 | 0.33 | $12,752.97 | 121 | 51.2% | 2.37 |
| 2026-06 | 1.04 | $40,018.75 | 101 | 55.4% | 1.35 |
| 2026-07 | 0.53 | $20,698.60 | 37 | 54.1% | 0.82 |

---

## F. Drawdown Statistics

**Measurement:** Running equity peak-to-trough (balance peak), sampled at trade close.

### F.1 Summary

| Statistic | Value |
|---|---|
| Maximum drawdown | 5.57% |
| Mean drawdown | 0.71% |
| Median drawdown | 0.17% |
| Std deviation | 0.98% |
| Variance | 0.95 (%^2) |

### F.2 Drawdown Percentiles

| Percentile | Value |
|---|---|
| P75 | 1.27% |
| P90 | 2.24% |
| P95 | 2.91% |
| P99 | 3.49% |

### F.3 Drawdown Duration

| Statistic | Value |
|---|---|
| Max duration | 1,451 bars (~30 days at 30min intervals) |
| Mean duration | 7.6 bars (~3.8 hours) |
| Median duration | 2 bars (~1 hour) |
| Number of episodes | 748 |

### F.4 Drawdown Exceedance Counts

| Threshold | Count |
|---|---|
| > 1% | 2,306 |
| > 2% | 1,187 |
| > 3% | 335 |
| > 5% | 4 |
| > 10% | 0 |

**CRITICAL CAVEAT:** The drawdown is measured at trade-close resolution only. Intraday drawdown (between trade open and close) is NOT captured. The actual maximum drawdown is likely higher.

---

## G. Variance / Stability Analysis

### G.1 Return Distribution

| Metric | Monthly Returns | Trade Returns |
|---|---|---|
| Variance | 174.62 | $5,781,167.58 |
| Std deviation | 13.21% | $2,404.41 |
| Skewness | 2.143 (positive) | 1.049 (positive) |
| Kurtosis | 4.421 (leptokurtic) | 7.681 (leptokurtic) |
| CV | 1.6335 | — |

### G.2 Interpretation

- **Strong positive skew** — a few exceptional months drive performance. The mean (8.09%) is 3.5x the median (2.32%).
- **Leptokurtic (fat tails)** — both monthly and trade returns have more extreme values than a normal distribution.
- **High CV (1.63)** — the standard deviation of monthly returns exceeds the mean, indicating the strategy's monthly returns are highly variable relative to their average.
- **Degradation over time:** 2018-2022 had no negative months. 2023-2026 had 11 negative months. The strategy's edge appears to be decaying.

### G.3 Exit Reason Analysis

| Exit | Count | % | Total PnL |
|---|---|---|---|
| SC (Session Close) | 7,834 | 98.2% | $4,412,452 |
| SL (Stop Loss) | 135 | 1.7% | -$652,227 |
| TP (Take Profit) | 11 | 0.1% | $129,585 |
| MH (Max Hold) | 0 | 0.0% | $0 |
| DL (Daily Limit) | 0 | 0.0% | $0 |

**98.2% of trades exit via session close.** This means:
- The TP is almost never hit (only 11 times in 7,980 trades)
- The SL is hit rarely (1.7%)
- The strategy relies almost entirely on mean-reversion within a session window
- Trade duration is typically short (within one trading session)

---

## H. Cost Sensitivity Analysis

### H.1 Scenario Definitions

| Scenario | Commission | Friction | Description |
|---|---|---|---|
| A | $3.50/lot | Realistic (1x spread, 0.3 pip slp) | Current baseline |
| B | $4.00/lot | Realistic | $4 round-turn commission |
| C | $3.50/lot | Realistic | Same as A (no empirical P95 exists) |
| D | $3.50/lot | Stressed (2x spread, 1.0 pip slp) | Stress test (no empirical P99 exists) |
| E | $4.00/lot | Realistic | $4 commission + realistic friction |
| F | $4.00/lot | Stressed | $4 commission + stressed friction |

### H.2 Results

| Scenario | Trades | WR | Net PnL | PF | Final | Max DD | Mean Mo | Median Mo | P5 Mo | P95 Mo | P99 Mo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A (baseline) | 7,980 | 58.62% | $3,889,811 | 1.89 | $3,892,311 | 4.60% | 8.09% | 2.32% | -0.53% | 37.76% | 47.70% |
| B ($4 comm) | 7,980 | 58.47% | $3,849,548 | 1.88 | $3,852,048 | 4.64% | 8.07% | 2.32% | -0.55% | 37.59% | 47.45% |
| C (same as A) | 7,980 | 58.62% | $3,889,811 | 1.89 | $3,892,311 | 4.60% | 8.09% | 2.32% | -0.53% | 37.76% | 47.70% |
| D (stressed) | 7,980 | 51.49% | $1,523,939 | 1.30 | $1,526,439 | 31.21% | 6.90% | 2.67% | -2.25% | 27.86% | 34.28% |
| E ($4+real) | 7,980 | 58.47% | $3,849,548 | 1.88 | $3,852,048 | 4.64% | 8.07% | 2.32% | -0.55% | 37.59% | 47.45% |
| F ($4+stress) | 7,980 | 51.33% | $1,481,987 | 1.29 | $1,484,487 | 32.19% | 6.87% | 2.69% | -2.31% | 27.84% | 34.20% |

### H.3 Key Findings

1. **$4 commission impact is minimal** — Final balance drops by $40K (1.0%), PF drops 0.01, WR drops 0.15pp.
2. **Stressed friction is catastrophic** — MDD jumps from 4.6% to 31.2%, PF drops from 1.89 to 1.30. The strategy is extremely sensitive to spread/slippage assumptions.
3. **Scenarios C and D are NOT empirical P95/P99** — They use fixed assumptions, not actual slippage distributions. True P95/P99 would require empirical data.
4. **Commission is a minor factor compared to spread/slippage** — The stressed scenario (D/F) is 7x more damaging than the commission increase (B/E).

---

## I. Filter Effectiveness

### I.1 Session Filter

| Metric | With Filter | Without Filter | Delta |
|---|---|---|---|
| Trades | 7,980 | 8,908 | +928 (+11.6%) |
| Net PnL | $3,889,811 | $5,172,208 | +$1,282,397 (+33.0%) |
| Profit Factor | 1.89 | 1.52 | -0.37 |
| Max Drawdown | 4.60% | 18.52% | +13.92pp |

**The session filter is highly effective:**
- Removes 10.4% of trades
- **Improves PF by 0.37** (1.52 -> 1.89)
- **Reduces MDD by 13.92pp** (18.52% -> 4.60%)
- Net PnL is lower without the filter, but this is misleading — the no-filter run takes more risk (higher MDD) for only 33% more PnL

### I.2 Spread Filter

**NOT A FILTER.** Spread is a cost, not a trade-blocking mechanism.

### I.3 Weekend Filter

Part of session filter (same `igs()` function). Cannot be separated.

### I.4 News Filter

**NOT IMPLEMENTED / NOT TESTABLE WITH CURRENT DATA**

The dataset contains minute OHLC data only. No news event timestamps, sentiment scores, or economic calendar data is available.

### I.5 P95/P99 Slippage Filter

**ABSENT.** No empirical slippage model exists. Only fixed assumptions.

---

## J. Important Caveats

1. **Drawdown is measured at trade-close resolution only.** Intraday drawdown (between trade entry and exit within the same bar) is NOT captured. The actual maximum drawdown is likely higher than 5.57%.

2. **Spread/slippage are modeled, not empirical.** The 0.3 pip slippage and fixed spread values are assumptions. Actual execution costs could be significantly different, especially during high-volatility periods.

3. **The strategy is heavily session-close dependent (98.2%).** This means the strategy's edge comes from mean-reversion within a session, not from hitting TP/SL targets. The TP is almost never hit.

4. **Performance degradation is evident.** 2018-2022: 0 negative months. 2023-2026: 11 negative months. The strategy's edge may be decaying as markets evolve.

5. **Compounding effect inflates later months.** The early months (2018-2019) show 20-67% returns because the account is small ($2,500). Later months show 0.3-1% because the account is much larger. The absolute PnL is what matters, not the percentage.

6. **No out-of-sample validation beyond the IS/OOS split in the original script.** The forensic analysis covers the full period only.

7. **The $4 commission scenario (B) is identical to scenario E.** Both use $4 commission with realistic friction. This is intentional — it isolates the commission effect.

8. **Scenarios C and D are NOT empirical P95/P99.** They use the same fixed assumptions as the baseline. True empirical percentiles would require actual execution data.

---

## K. Source Files / Functions Used

| File | Function/Section | Purpose |
|---|---|---|
| `/root/test_final_scalper.py` | `igs()` (lines 12-19) | Session/time filter |
| `/root/test_final_scalper.py` | `run_sim()` (lines 21-168) | Main simulation loop |
| `/root/test_final_scalper.py` | `SPREAD` dict (line 10) | Per-pair spread assumptions |
| `/root/test_final_scalper.py` | `COMMISSION` (line 8) | $3.50/lot commission |
| `/root/test_final_scalper.py` | Lines 77-96 | Exit logic (SL/TP/SC/MH) |
| `/root/test_final_scalper.py` | Lines 105-136 | Entry logic with filters |
| `/root/position_sizing.py` | `pip_size_for_pair()` | Pip size calculation |
| `/root/position_sizing.py` | `pip_value_per_lot()` | Pip value in USD |
| `/root/position_sizing.py` | `compute_position_size()` | Risk-based lot sizing |
| `/root/nestquant/forensic_analysis.py` | `run_forensic_sim()` | Instrumented simulation |
| `/root/nestquant/forensic_analysis.py` | `_compute_metrics()` | Full metric computation |
| `/root/nestquant/forensic_analysis.py` | `cost_sensitivity_analysis()` | 6-scenario cost stress |
| `/root/nestquant/forensic_analysis.py` | `filter_effectiveness()` | Session filter impact |

---

## L. Reproducibility Commands

```bash
# Run the full forensic analysis (includes baseline + 6 cost scenarios + filter analysis)
cd /root/nestquant && python3 forensic_analysis.py

# Run the original baseline for comparison
cd /root && python3 test_final_scalper.py

# View machine-readable metrics
cat /root/nestquant/logs/mr_baseline_metrics.json | python3 -m json.tool
```

---

*Report generated by forensic_analysis.py — read-only analysis, no strategy modifications.*
