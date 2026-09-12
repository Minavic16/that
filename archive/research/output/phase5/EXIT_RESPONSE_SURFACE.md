# Phase 5 — Exit Response Surface

**Date:** 2026-08-14  
**Strategy:** Z-Score Mean Reversion (30min, 20 FX pairs, 2016-01-01 to 2026-07-19)  
**Purpose:** Map the complete exit response surface. Do NOT optimize. Map.

---

## 0. Key Answers

| Question | Answer |
|----------|--------|
| **A. Does Z-score contain a genuine short-horizon predictive edge?** | Yes, but very weak. PF=1.05 at 4 bars (2h), barely surviving costs. |
| **B. What is the natural time horizon over which that edge decays?** | 3–16 bars (1.5–8 hours). Edge plateaus at ~4 bars, decays after ~16. |
| **C. Does the signal require wide adverse excursion before successful reversion?** | Yes. 67% of eventual winners exceed 3 ATR before becoming profitable. |
| **D. Are continuation trades predictable before they become catastrophic?** | Partially. Z≥5 trades have PF=1.44 (best segment), but continuation trades in Z 3-4 are the worst. |
| **E. Is time-based exit more appropriate than Z-based exit?** | Yes. ALL Z-exit thresholds (0.25–3.0) produce PF=0.42–0.74, far worse than time exits (PF=1.03–1.06). |
| **F. Is the optimal trade lifecycle regime-dependent?** | Yes. NY session PF=1.26 vs London PF=1.00. High vol PF=1.19 vs low vol PF=1.07. |
| **G. Is PF≈1.55 at 4 bars a broad structural region or an isolated peak?** | Neither. The PF≈1.55 was an artifact of the previous engine's assumptions. The corrected PF is 1.05 — a broad, shallow region. |
| **H. What is the maximum robust performance envelope BEFORE optimization?** | PF=1.05 at 4 bars, CI=[0.99, 1.13]. The edge is not statistically significant at 95% confidence. |

---

## 1. Time-Exit Response Surface

### 1.1 Full Surface

| Bars | Hours | WR | PF | Net P&L | Median | Avg Win | Avg Loss | SL Hits | TP Hits | TE Hits |
|------|-------|----|----|---------|--------|---------|----------|---------|---------|---------|
| 1 | 0.5 | 0.0% | 0.00 | -$2,505 | -$0.36 | $0.00 | -$0.39 | 0 | 0 | 6374 |
| 2 | 1.0 | 50.5% | 0.98 | -$181 | $0.03 | $3.01 | -$3.12 | 51 | 6 | 6317 |
| **3** | **1.5** | **51.5%** | **1.03** | **$370** | $0.16 | $4.14 | -$4.28 | 154 | 15 | 6205 |
| **4** | **2.0** | **52.0%** | **1.05** | **$865** | $0.25 | $5.08 | -$5.22 | 282 | 31 | 6061 |
| **5** | **2.5** | **51.3%** | **1.06** | **$1,136** | $0.22 | $5.85 | -$5.81 | 415 | 47 | 5912 |
| 6 | 3.0 | 51.4% | 1.03 | $561 | $0.22 | $6.27 | -$6.45 | 544 | 62 | 5768 |
| **8** | **4.0** | **51.0%** | **1.04** | **$905** | $0.25 | $7.40 | -$7.41 | 790 | 109 | 5475 |
| 10 | 5.0 | 50.5% | 1.02 | $581 | $0.12 | $8.20 | -$8.18 | 999 | 164 | 5211 |
| **12** | **6.0** | **49.7%** | **1.04** | **$1,048** | -$0.08 | $9.18 | -$8.75 | 1197 | 233 | 4944 |
| **16** | **8.0** | **48.9%** | **1.03** | **$1,090** | -$0.28 | $10.69 | -$9.91 | 1528 | 372 | 4474 |
| 20 | 10.0 | 47.5% | 1.01 | $417 | -$0.92 | $11.87 | -$10.60 | 1783 | 470 | 4121 |
| 24 | 12.0 | 46.6% | 1.01 | $458 | -$1.25 | $12.88 | -$11.11 | 2009 | 567 | 3798 |
| 32 | 16.0 | 45.5% | 1.01 | $243 | -$2.30 | $14.53 | -$12.05 | 2333 | 735 | 3306 |
| 40 | 20.0 | 43.8% | 1.01 | $272 | -$4.00 | $16.48 | -$12.77 | 2662 | 897 | 2815 |
| 48 | 24.0 | 42.4% | 0.99 | -$337 | -$6.65 | $18.14 | -$13.43 | 2974 | 1091 | 2309 |
| 64 | 32.0 | 40.1% | 0.98 | -$874 | -$13.75 | $20.78 | -$14.12 | 3345 | 1364 | 1665 |

### 1.2 Structure of the Surface

```
PF
1.06 |          * (5 bars)
1.05 |     * (4 bars)
1.04 |  * (3)              * (8)     * (12)
1.03 |                    * (16)
1.02 |                              * (10)
1.01 |                                        * (20)(24)(32)(40)
1.00 |
0.99 |                                                  * (48)
0.98 |* (2)                                                        * (64)
     +--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+
       1  2  3  4  5  6  8  10 12 16 20 24 32 40 48 64  bars
```

**The surface is BROAD and SHALLOW.** There is no sharp peak. The region 3–16 bars all produce PF=1.03–1.06. The 4-bar point is NOT statistically different from 3, 5, 6, 8, 12, or 16 bars.

### 1.3 Statistical Significance

| Horizon | PF | Bootstrap 95% CI |
|---------|----|------------------|
| 4 bars | 1.05 | [0.99, 1.13] |
| 8 bars | 1.04 | [0.97, 1.11] |
| 16 bars | 1.03 | [0.97, 1.10] |

The 4-bar CI barely excludes 1.0 (lower bound 0.99). The 8-bar and 16-bar CIs include 1.0. **The edge is not statistically significant at 95% confidence for any horizon.**

---

## 2. MAE/MFE Surface

### 2.1 Winners vs Losers (4-bar reference)

| Metric | Winners (n=3,313) | Losers (n=3,061) | Ratio |
|--------|-------------------|------------------|-------|
| MAE (pips) | 79.1 | 99.6 | 1.26x |
| MFE (pips) | 100.6 | 79.3 | 0.79x |
| MAE (ATR) | 7.19 | 9.02 | 1.25x |
| MFE (ATR) | 9.06 | 7.39 | 0.82x |

**Key Finding:** The difference between winners and losers is SMALL. Winners have 20p less MAE and 21p more MFE. This is not the dramatic asymmetry the previous analysis suggested.

### 2.2 ATR Exceedance — How Many Winners Survive?

| ATR Threshold | Winners Exceed | Losers Exceed |
|---------------|----------------|---------------|
| 0.5 ATR | 91.6% | 99.7% |
| 1.0 ATR | 85.0% | 97.8% |
| 1.5 ATR | 79.6% | 94.7% |
| 2.0 ATR | 75.6% | 90.7% |
| 2.5 ATR | 71.2% | 86.8% |
| **3.0 ATR** | **67.2%** | **82.5%** |
| 4.0 ATR | 58.6% | 73.2% |
| 5.0 ATR | 51.6% | 64.4% |

**Critical Finding:** 67% of eventual winners exceed 3 ATR before becoming profitable. This means:
1. The 3 ATR stop IS too wide — but NOT because it "lets losers run"
2. Rather, even winners need to go through 3+ ATR of adverse excursion
3. Tighter stops (1-2 ATR) would stop out 75-85% of winners
4. The signal requires patience — winners MUST survive significant drawdown

### 2.3 By Category

| Category | Count | MAE (pips) | MFE (pips) | MAE (ATR) | MFE (ATR) |
|----------|-------|------------|------------|-----------|-----------|
| Mean-Reverting | 6,063 | 86.5 | 87.2 | 7.8 | 7.9 |
| Continuation | 311 | 138.4 | 39.5 | 12.5 | 3.6 |

Continuation trades have 1.6x the MAE and 0.45x the MFE of MR trades. The signal DOES distinguish between the two — but only after the fact.

---

## 3. Exit-Timing / Information Decay

### 3.1 MR Capture Rate

| Bars | MR Captured | CONT Identified | Remaining MFE |
|------|-------------|-----------------|---------------|
| 1 | 16.2% | 12.4% | 28.7p |
| 2 | 30.3% | 8.0% | 29.4p |
| 4 | 51.5% | 3.5% | 30.5p |
| 8 | 74.5% | 3.5% | 32.6p |
| 16 | 85.5% | 1.0% | 36.4p |
| 32 | 82.9% | 3.5% | 45.1p |

**The natural information horizon is 4–8 bars.** By 4 bars, 51.5% of MR is captured. By 8 bars, 74.5%. After 8 bars, the marginal gain is small.

### 3.2 The Decay Curve

```
MR Captured %
100 |
 90 |                              * (16)
 80 |                    * (8)                 * (32)
 70 |
 60 |
 50 |          * (4)
 40 |
 30 |     * (2)
 20 |* (1)
  0 +--+--+--+--+--+--+--+--+
    1  2  4  8  16 32  bars
```

The curve follows approximately: `captured ≈ 1 - exp(-bar/5)`. The half-life is ~3.5 bars (1.75 hours).

---

## 4. Z-Exit Surface

| Z Threshold | WR | PF | Net P&L | Avg Bars |
|-------------|----|----|---------|----------|
| Z > 0.25 | 38.1% | 0.42 | -$23,214 | 9.7 |
| Z > 0.50 | 39.1% | 0.43 | -$20,463 | 8.3 |
| Z > 0.75 | 40.6% | 0.46 | -$17,444 | 6.8 |
| Z > 1.00 | 42.7% | 0.48 | -$14,801 | 5.5 |
| Z > 1.25 | 44.5% | 0.52 | -$12,107 | 4.4 |
| Z > 1.50 | 45.1% | 0.54 | -$10,031 | 3.5 |
| Z > 2.00 | 45.5% | 0.60 | -$6,636 | 2.2 |
| Z > 2.50 | 46.9% | 0.67 | -$4,351 | 1.5 |
| Z > 3.00 | 47.9% | 0.74 | -$3,083 | 1.2 |

**ALL Z-exit thresholds are catastrophic.** The best (Z>3.0) still produces PF=0.74. Z-based exits systematically destroy value because:
1. They exit when Z moves back toward 0, which is often premature
2. They don't account for the time dimension of mean-reversion
3. They create a negative skew: early exits cap gains while SL exits allow full losses

**Time-based exits are 40-60% better than Z-based exits at every threshold.**

---

## 5. Stop-Loss Surface

| ATR Mult | WR | PF | Net P&L | Winners Stopped | CONT Caught |
|----------|----|----|---------|-----------------|-------------|
| 0.50x | 4.5% | 0.97 | -$563 | 95.6% | 93.0% |
| 0.75x | 6.5% | 1.00 | -$117 | 93.5% | 92.5% |
| **1.00x** | **8.8%** | **1.03** | **$943** | **91.2%** | **90.5%** |
| 1.25x | 10.8% | 1.02 | $564 | 89.0% | 89.6% |
| 1.50x | 13.0% | 1.00 | -$103 | 86.8% | 87.1% |
| 2.00x | 16.7% | 0.98 | -$1,089 | 82.8% | 83.6% |
| 2.50x | 20.5% | 0.96 | -$2,847 | 78.6% | 83.1% |
| **3.00x** | **23.8%** | **0.95** | **-$3,563** | **74.4%** | **79.6%** |
| 4.00x | 30.3% | 0.99 | -$1,148 | 65.4% | 70.6% |
| 5.00x | 35.4% | 1.00 | $380 | 57.6% | 64.2% |

**The SL surface is very flat.** No clear optimum. Key observations:
1. 1.0x ATR is marginally best (PF=1.03), but stops out 91% of winners
2. Tighter stops (< 1.0x) stop out >90% of winners
3. Wider stops (> 3.0x) let too many continuation trades run
4. The 3.0x ATR stop is NOT "too wide" in a meaningful sense — the entire surface is flat
5. The real issue is not SL width but signal strength

---

## 6. Session/overnight Effect

| Variant | WR | PF | Net P&L |
|---------|----|----|---------|
| Forced session exit (50 bars) | 42.4% | 1.00 | -$173 |
| No forced exit (200 bars) | 34.5% | 1.00 | -$1,262 |
| Conditional on Z (≥4 hold longer) | 41.9% | 1.00 | $269 |
| Conditional on vol | 39.5% | 1.00 | -$733 |
| Conditional on session (overlap hold) | 40.3% | 1.00 | -$979 |

**Session close is NOT the problem.** All variants produce PF≈1.00. The forced session exit is actually the best variant (smallest loss). Overnight holding does NOT help.

---

## 7. Regime Conditioning

### 7.1 By Z-Score Magnitude

| Z Range | 4-bar PF | 4-bar P&L | 8-bar PF | 8-bar P&L |
|---------|----------|-----------|----------|-----------|
| 2–3 | 1.06 | $642 | 1.07 | $1,023 |
| 3–4 | 0.98 | -$92 | 0.93 | -$435 |
| 4–5 | 1.04 | $53 | 1.08 | $136 |
| **5+** | **1.44** | **$262** | **1.21** | **$181** |

**Extreme Z-scores (5+) have the best edge (PF=1.44).** But this is a small sample. Z 3-4 is the worst segment (PF=0.93–0.98).

### 7.2 By Volatility Regime

| Regime | 4-bar PF | 4-bar P&L | 8-bar PF | 8-bar P&L |
|--------|----------|-----------|----------|-----------|
| low_vol | 1.07 | $278 | 1.00 | $16 |
| mid_vol | 1.00 | $6 | 1.05 | $600 |
| high_vol | 1.19 | $526 | 1.08 | $308 |
| extreme_vol | 1.08 | $54 | 0.98 | -$20 |

**High-vol regimes have the strongest edge (PF=1.19).** Low-vol and extreme-vol are weaker.

### 7.3 By Session

| Session | 4-bar PF | 4-bar P&L | 8-bar PF | 8-bar P&L |
|---------|----------|-----------|----------|-----------|
| **NY only** | **1.26** | **$995** | **1.19** | **$1,110** |
| London only | 1.00 | -$35 | 0.99 | -$118 |
| Overlap | 0.97 | -$95 | 0.98 | -$87 |

**NY session has the strongest edge (PF=1.26).** London and overlap sessions have no edge.

### 7.4 By Pair

| Pair | 4-bar PF | 4-bar P&L | 8-bar PF | 8-bar P&L |
|------|----------|-----------|----------|-----------|
| **AUD/CHF** | **1.56** | **$292** | **1.47** | **$339** |
| **NZD/CHF** | **1.46** | **$253** | **1.43** | **$337** |
| **AUD/CAD** | **1.51** | **$271** | **1.41** | **$334** |
| AUD/USD | 1.41 | $311 | 1.07 | $82 |
| NZD/JPY | 1.41 | $191 | 1.54 | $387 |
| GBP/AUD | 1.27 | $176 | 1.21 | $206 |
| USD/CHF | 1.08 | $85 | 1.13 | $189 |
| EUR/GBP | 1.03 | $38 | 1.12 | $190 |
| GBP/CAD | 1.07 | $68 | 1.16 | $220 |
| CAD/CHF | 1.07 | $35 | 1.07 | $64 |
| EUR/AUD | 1.03 | $30 | 1.07 | $82 |
| GBP/JPY | 0.98 | -$16 | 0.78 | -$270 |
| AUD/JPY | 0.95 | -$36 | 0.91 | -$97 |
| NZD/USD | 0.94 | -$47 | 1.21 | $231 |
| EUR/CHF | 0.96 | -$40 | 0.77 | -$348 |
| EUR/USD | 0.91 | -$125 | 0.91 | -$177 |
| GBP/USD | 0.87 | -$153 | 0.79 | -$384 |
| USD/JPY | 0.80 | -$226 | 0.81 | -$306 |
| CAD/JPY | 0.74 | -$242 | 0.86 | -$174 |

**High cross-pair dispersion.** Best pair (AUD/CHF PF=1.56) vs worst (CAD/JPY PF=0.74). The edge is pair-dependent.

---

## 8. Robustness

### 8.1 By Period

| Period | 4-bar PF | 4-bar P&L | 8-bar PF | 8-bar P&L |
|--------|----------|-----------|----------|-----------|
| 2016-2018 | 1.11 | $493 | 1.03 | $217 |
| 2019-2021 | 1.14 | $656 | 1.14 | $924 |
| 2022-2024 | 1.00 | -$3 | 0.99 | -$44 |
| 2025-2026 | 0.89 | -$281 | 0.95 | -$192 |

**The edge is DECADE-DEPENDENT.** It existed in 2016-2021 (PF=1.11-1.14) but disappeared in 2022-2026 (PF=0.89-1.00). This is the single most important robustness finding.

### 8.2 Cross-Pair Dispersion

- **Median 4-bar PF:** 1.03
- **Best pair:** AUD/CHF (PF=1.56)
- **Worst pair:** CAD/JPY (PF=0.74)
- **Interquartile range:** 0.94–1.41

### 8.3 Bootstrap CI

| Horizon | PF | 95% CI | Includes 1.0? |
|---------|----|--------|---------------|
| 4 bars | 1.05 | [0.99, 1.13] | Borderline (0.99) |
| 8 bars | 1.04 | [0.97, 1.11] | Yes |
| 16 bars | 1.03 | [0.97, 1.10] | Yes |

### 8.4 Outlier Sensitivity (4-bar)

| Variant | Avg Trade |
|---------|-----------|
| Full | $0.14 |
| Trim 1% | $0.04 |
| Trim 5% | $0.10 |

Removing outliers makes the edge smaller but doesn't eliminate it.

### 8.5 Cost Sensitivity

| Horizon | $0 Cost | $3.50 Cost | $7.00 Cost | $15.00 Cost |
|---------|---------|------------|------------|-------------|
| 4 bars | PF=1.15 | PF=1.05 | PF=0.96 | PF=0.78 |
| 8 bars | PF=1.11 | PF=1.04 | PF=0.98 | PF=0.85 |
| 16 bars | PF=1.09 | PF=1.04 | PF=0.99 | PF=0.90 |
| 32 bars | PF=1.03 | PF=0.99 | PF=0.96 | PF=0.89 |

**The strategy breaks even at $3.50/lot/RT commission.** At $7.00 (realistic for small accounts), PF<1.0 for all horizons.

---

## 9. Multiple-Comparison Warning

This analysis evaluated:
- 16 time horizons
- 9 Z-exit thresholds  
- 10 SL levels
- 5 session variants
- 4 Z bins × 16 horizons = 64 regime-time combinations
- 4 vol regimes × 16 horizons = 64 combinations
- 3 sessions × 16 horizons = 48 combinations
- 19 pairs × 4 horizons = 76 pair-time combinations

**Total configurations evaluated: ~300+**

Under the null hypothesis of no edge, we would expect ~15 configurations to show PF>1.05 at the 5% level. The fact that we observe some configurations with PF>1.1 is NOT evidence of a genuine edge — it may be data mining.

**The ONLY statistically defensible finding is:**
1. The time-exit surface is broad and flat (3-16 bars all PF=1.03-1.06)
2. Z-exits are systematically worse than time exits
3. The edge is decade-dependent (existed 2016-2021, faded 2022+)
4. The edge barely survives realistic transaction costs

**NOT statistically defensible:**
- "4 bars is optimal" (not different from 3, 5, 6, 8, 12, 16)
- "AUD/CHF is the best pair" (could be noise)
- "NY session is best" (could be noise)
- "High vol is best" (could be noise)

---

## 10. Conclusions

### The Signal Has Marginal Predictive Power

The Z-score signal DOES contain a genuine short-horizon predictive edge. The time-exit surface shows PF>1.0 for horizons 3-40 bars. The information decay curve shows 51.5% of MR captured by 4 bars, 74.5% by 8 bars. This is not noise — it's a consistent structural pattern.

### But The Edge Is Too Small To Trade

1. **PF=1.05 at 4 bars** — this is the best point, and it's barely above break-even
2. **Bootstrap CI includes 1.0** — not statistically significant
3. **Edge is decade-dependent** — existed 2016-2021, faded 2022+
4. **Edge breaks even at $3.50/lot/RT** — realistic costs eat the entire edge
5. **High cross-pair dispersion** — edge is pair-dependent, not universal

### The Exit Architecture Is Not The Primary Problem

The previous analysis blamed the exit architecture. This is incorrect. The REAL problem is:
1. The signal itself is very weak (PF=1.05 before costs)
2. The signal is regime-dependent (works in some periods/pairs/sessions, not others)
3. Transaction costs are too high relative to the signal strength

Changing the exit architecture (time exit, tighter SL, etc.) cannot fix a weak signal. The maximum improvement from exit optimization is PF=1.06 (at 5 bars) — a 1% improvement over the current PF=0.98.

### What Would Be Needed For A Viable Strategy

To make the Z-score MR strategy viable, you would need:
1. A stronger entry signal (not just Z>2.2)
2. Regime filtering (only trade in high-vol, NY session, Z≥5)
3. Lower transaction costs (ECN broker, larger lot sizes)
4. Pair selection (focus on AUD/NZD crosses, avoid JPY pairs)
5. Walk-forward validation across multiple decades

Without these improvements, the Z-score MR strategy is a break-even system with negative expectancy after costs.

---

## Appendix: Data Files

- `research_data/phase5/exit_surface.json` — Full machine-readable results
- `research_data/phase5/EXIT_FORENSICS_REPORT.md` — Previous exit forensics
- `research_data/phase5/PROGRESS.md` — Progress tracking
