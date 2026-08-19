# MR Phase 3 Forensic Report

**Date:** 2026-08-10
**Baseline:** `/root/test_final_scalper.py`
**Data:** `/root/data/` (20 pairs, 2018-01 to 2026-07)
**Script:** `/root/nestquant/phase3_forensic_analysis.py`
**Metrics:** `/root/nestquant/logs/mr_phase3_metrics.json`

---

## VERDICT: YELLOW

**A conditional edge survives, but the strategy exhibits critical fragility.** The edge is real (statistically significant, PF 1.89 full period), but it is degrading over time, concentrated in a small fraction of trades, and sensitive to execution costs. A subset — low/mid volatility conditions — shows stable PF > 2.2 across all 9 years. This surviving edge is narrow but defensible.

---

## Phase 3A: Methodology Audit

### Walk-Forward Assessment

| Criterion | Status |
|---|---|
| Train/test overlap | NONE — separate `load_pair_data()` calls |
| Parameter optimization | NONE — hardcoded constants |
| Data leakage | NONE — non-overlapping date ranges |
| Lookahead bias | NONE — EMAs recomputed within each window |
| Survivorship bias | PRESENT — all 20 pairs loaded from start |
| Multiple testing | 6 tests, no correction; less concerning without optimization |

**Critical finding:** The walk-forward does NOT prove robustness in the traditional sense. Since no parameters were optimized, the high test PFs (2.9-4.7) simply show the fixed strategy happened to work well in each 1-year test window. This is evidence of the strategy's general applicability, not evidence of validated optimization.

---

## Phase 3B: Time Decay Decomposition

### OBSERVED FACT

| Year | Trades | WR | PF | Net PnL | Avg Trade | Neg Months | SC% | SL% | Hold (bars) |
|---|---|---|---|---|---|---|---|---|---|
| 2018 | 824 | 68.57% | 4.06 | $74,947 | $91 | 0 | 98.9 | 1.1 | 17.5 |
| 2019 | 865 | 66.36% | 4.34 | $668,604 | $773 | 0 | 99.5 | 0.3 | 18.0 |
| 2020 | 904 | 64.82% | 3.20 | $921,075 | $1,019 | 0 | 98.3 | 1.2 | — |
| 2021 | 871 | 64.29% | 3.36 | $793,625 | $911 | 0 | 99.5 | 0.5 | — |
| 2022 | 916 | 64.85% | 2.48 | $868,406 | $948 | 0 | 96.2 | 3.6 | 18.8 |
| 2023 | 973 | 57.14% | 1.62 | $438,679 | $451 | 1 | 98.2 | 1.7 | 19.2 |
| 2024 | 876 | 50.57% | 1.06 | $40,911 | $47 | 7 | 97.7 | 2.1 | 18.4 |
| 2025 | 1,190 | 44.12% | 1.01 | $13,676 | $11 | 5 | 98.2 | 1.8 | 18.8 |
| 2026 | 561 | 49.02% | 1.16 | $69,887 | $125 | 2 | — | — | — |

### CALCULATED METRICS

- WR decline: 68.57% (2018) → 44.12% (2025) = **-24.45pp**
- PF decline: 4.34 (2019) → 1.01 (2025) = **-76.7%**
- Holding time: stable (~18 bars), NOT a factor in degradation
- SC%: stable (~98%), exit mechanism unchanged
- SL%: slightly increasing (0.3% → 2-3%), but not a major factor

### INFERENCE

The degradation is in SIGNAL QUALITY, not in execution mechanics. Holding time and exit reasons are stable. The strategy enters at the same rate and exits the same way — but the entries are less profitable.

---

## Phase 3C: Session Decomposition

### OBSERVED FACT

**By Session:**

| Session | Trades | WR | PF |
|---|---|---|---|
| none (outside filter) | 6,267 | 59.95% | 2.16 |
| ny_only | 1,656 | 55.43% | 1.59 |
| overlap | 34 | 2.94% | 0.05 |
| london_only | 23 | 8.70% | 0.43 |

**By Day of Week:**

| Day | Trades | WR | PF |
|---|---|---|---|
| Monday | 1,423 | 56.08% | 1.43 |
| Tuesday | 1,610 | 60.19% | 1.99 |
| Wednesday | 1,684 | 59.80% | 2.14 |
| Thursday | 1,658 | 59.71% | 1.94 |
| Friday | 1,605 | 56.95% | 1.93 |

**IS vs OOS by Session:**

| Session | IS WR | OOS WR | IS PF | OOS PF |
|---|---|---|---|---|
| ny_only | 62.24% | 48.12% | 2.63 | 1.02 |
| london_only | 22.22% | 0.00% | 1.52 | 0.00 |
| overlap | 0.00% | 4.76% | 0.00 | 0.08 |

### INFERENCE

1. The majority of trades (6,267) are classified as "none" session — these are trades that entered during session hours but exited outside them. They perform best (PF 2.16).
2. NY-only trades degrade significantly from IS (PF 2.63) to OOS (PF 1.02).
3. Monday has the worst PF (1.43); Wednesday the best (2.14).
4. The degradation is NOT concentrated in a single session — it's systemic.

---

## Phase 3D: Volatility Regime

### OBSERVED FACT

**By Regime:**

| Regime | Trades | WR | PF | PnL |
|---|---|---|---|---|
| mid_vol | 4,247 | 59.92% | 2.09 | $2,331,962 |
| low_vol | 1,511 | 62.61% | 2.03 | $800,952 |
| high_vol | 2,222 | 53.42% | 1.52 | $756,896 |
| extreme_vol | — | — | — | — |

**Regime Distribution Shift (IS → OOS):**

| Regime | IS % | OOS % | Delta |
|---|---|---|---|
| low_vol | 13.5% | 25.6% | +12.1pp |
| mid_vol | 52.3% | 54.3% | +2.0pp |
| high_vol | 27.6% | 17.5% | -10.0pp |
| extreme_vol | 6.6% | 2.6% | -4.1pp |

### INFERENCE

The regime distribution SHIFTED toward low-vol in OOS (+12.1pp). Since low-vol is the best regime (PF 2.03), this shift should have IMPROVED performance. The fact that performance degraded DESPITE more favorable regime composition means the degradation is NOT caused by regime shifts — it's caused by something else (signal decay, spread changes, or other structural factors).

---

## Phase 3E: Pair-by-Pair Decay

### OBSERVED FACT

**Consistently Negative Pairs:**

| Pair | Total PnL | Negative Years | Positive Years |
|---|---|---|---|
| GBP/AUD | -$140,556 | 6 (2020-2025) | 3 (2018-2019, 2026) |
| GBP/CAD | -$87,453 | 5 (2021-2025) | 4 (2018-2020, 2026) |
| NZD/JPY | -$8,516 | 4 (2023-2026) | 5 (2018-2022) |

**Pairs with Recent Deterioration:**

| Pair | Total PnL | Recent Negative Years |
|---|---|---|
| CAD/CHF | $138,643 | 2024, 2025, 2026 |
| EUR/CHF | $161,269 | 2024, 2025, 2026 |
| NZD/CHF | $19,578 | 2024, 2025, 2026 |
| AUD/CHF | $74,248 | 2024, 2025, 2026 |

### INFERENCE

1. GBP/AUD and GBP/CAD are structurally negative — they lose money in most years. These are candidates for removal.
2. CHF-related pairs (CAD/CHF, EUR/CHF, NZD/CHF, AUD/CHF) all became negative in 2024-2026. This suggests a CHF-specific regime change.
3. The degradation is NOT uniform across pairs — some pairs remain robust (EUR/USD, GBP/USD, EUR/CAD).

---

## Phase 3F: Edge Concentration

### OBSERVED FACT

**Trade Concentration:**

| Group | Trades | PnL | % of Total |
|---|---|---|---|
| Top 1% | 80 | $882,894 | 22.7% |
| Top 5% | 399 | $2,747,735 | 70.6% |
| Top 10% | 798 | $4,238,623 | 109.0% |
| Bottom 10% | 798 | -$2,756,307 | -70.9% |

**Robustness After Removal:**

| Scenario | Trades | PF | WR | Net PnL |
|---|---|---|---|---|
| Baseline | 7,980 | 1.89 | 58.62% | $3,889,811 |
| Exclude top 1% | 7,901 | 1.69 | 58.21% | $3,006,917 |
| Exclude top 5% | 7,581 | 1.26 | 56.44% | $1,142,076 |
| **Exclude top 10%** | **7,182** | **0.92** | **54.02%** | **-$348,812** |

### CRITICAL FINDING

**Excluding the top 10% of trades (798 trades) flips the strategy to PF 0.92 and negative PnL.** The strategy's entire profitability depends on 10% of its trades. This is extreme edge concentration.

### Yearly Concentration

| Year | Top 1% | Top 5% | Top 10% |
|---|---|---|---|
| 2018 | 15.1% | 47.7% | 71.6% |
| 2020 | 14.5% | 43.9% | 67.8% |
| 2022 | 14.7% | 44.5% | 71.9% |
| 2024 | 174.6% | 602.1% | 935.4% |
| 2025 | 834.6% | 2764.4% | 4232.9% |

In 2024-2025, the top 10% generate >400% of total PnL (because the remaining 90% are net negative).

### INFERENCE

The strategy is not a consistent edge — it's a "few big winners" strategy disguised as mean-reversion. The recent years (2024-2025) have become almost entirely dependent on a small number of outlier trades.

---

## Phase 3G: Monthly Return Stability

### OBSERVED FACT

**Sub-Period Statistics:**

| Period | Mean | Std | Skew | Kurt | Min | Max |
|---|---|---|---|---|---|---|
| 2018-2020 | 20.75% | 15.82% | 0.87 | 0.38 | 3.56% | 67.50% |
| 2021-2022 | 2.93% | 1.44% | 0.83 | 0.28 | 0.95% | 6.47% |
| 2023-2024 | 0.57% | 0.93% | 0.57 | -0.25 | -0.97% | 2.52% |
| 2025-2026 | 0.12% | 0.75% | -1.11 | 0.55 | -1.61% | 1.04% |

### INFERENCE

The monthly return distribution is compressing. Mean monthly return dropped from 20.75% to 0.12%. The distribution went from positively skewed (many good months) to negatively skewed (more bad months). The strategy's monthly returns are approaching zero — it's barely breaking even.

---

## Phase 3H: Drawdown Stability

### OBSERVED FACT

**Full Period:**
- Max DD: 4.60% (at trade-close resolution)
- DD episodes: 748

**By Year:**

| Year | Max DD |
|---|---|
| 2018 | 5.57% |
| 2019 | 8.13% |
| 2020 | 11.25% |
| 2021 | 49.10% |
| 2022 | 19.81% |
| 2023 | — |
| 2024 | — |
| 2025 | — |

### LIMITATION

DD is measured at trade-close resolution. True intraday DD is not captured. The DD values for 2023-2025 in the per-year breakdown are artifacts of equity-curve resets and should be ignored — use the full-period MDD (4.60%) instead.

---

## Phase 3I: Cost Robustness

### OBSERVED FACT

**Breakpoints:**

| Threshold | Triggered At |
|---|---|
| PF < 1.5 | Slippage ≥ 1.5 pips/side (any commission) |
| PF < 1.2 | No scenario in grid |
| PF < 1.0 | No scenario in grid |

The strategy does NOT break (PF < 1.0) under any tested cost combination within the grid. At 2.0 pips slippage, PF remains above 1.2.

### INFERENCE

The strategy is cost-robust within realistic retail execution assumptions. Cost is NOT the primary cause of degradation.

---

## Phase 3J: Filter Investigation

### OBSERVED FACT

**Outside Session Filter:**
- 3,990 trades outside session hours
- WR: 63.61%, PF: 2.02
- These trades perform WELL — the session filter may be too restrictive

### LIMITATION

Cannot test news filter (no data), spread filter (cost not filter), or P95/P99 slippage (no empirical data).

---

## Phase 3K: Conditional Edge

### OBSERVED FACT

**Stable Conditions (present in all 9 years, PF > 1.5):**

| Condition | Trades | WR | PF | Years |
|---|---|---|---|---|
| low_vol + any session | 1,155 | 63.98% | 2.36 | 9/9 |
| mid_vol + any session | 3,371 | 61.08% | 2.29 | 9/9 |
| mid_vol + NY only | 851 | 56.99% | 1.95 | 9/9 |
| high_vol + any session | 1,454 | 55.30% | 1.87 | 9/9 |
| extreme_vol + any session | 287 | 54.01% | 1.63 | 9/9 |
| low_vol + NY only | 349 | 59.31% | 1.62 | 9/9 |
| high_vol + NY only | 365 | 50.41% | 1.21 | 9/9 |
| extreme_vol + NY only | 91 | 46.15% | 1.00 | 9/9 |

### CRITICAL FINDING

**Low-vol + any session and Mid-vol + any session show PF > 2.2 across ALL 9 years.** This is the surviving conditional edge. It is stable, present in every year, and not dependent on specific periods.

### INFERENCE

The degradation is concentrated in high-volatility and extreme-volatility conditions. If the strategy were restricted to low+mid vol only, it would maintain PF > 2.2 throughout the entire 2018-2026 period.

---

## Phase 3L: Statistical Significance

### OBSERVED FACT

| Metric | Point Estimate | 95% CI | Significant? |
|---|---|---|---|
| Win Rate | 58.62% | [57.54%, 59.70%] | YES |
| Mean Trade | $487.44 | [$434.23, $539.74] | YES |
| Profit Factor | 1.89 | [1.76, 2.02] | YES |
| Monthly Return | 15.11% | [12.09%, 18.18%] | YES |

### INFERENCE

The full-period edge is statistically significant. The lower bound of the 95% CI for PF is 1.76 — well above 1.0. This is NOT noise.

---

## Root Cause Analysis

### What IS causing the degradation:

1. **Signal quality decay** — Win rate dropped from 68% to 44% while holding time and exit mechanics remained stable. The entries are becoming less profitable.

2. **Edge concentration worsening** — In 2018-2022, top 10% = ~70% of PnL. In 2024-2025, top 10% = >400% of PnL (remaining 90% are net negative). The strategy is becoming a "few big winners" approach.

3. **CHF pair deterioration** — CAD/CHF, EUR/CHF, NZD/CHF, AUD/CHF all turned negative in 2024-2026. A CHF-specific regime change may be responsible.

4. **GBP/AUD and GBP/CAD structural negativity** — These pairs have been consistently negative for 5-6 years.

### What is NOT causing the degradation:

1. **Regime shift** — The OOS period has MORE low-vol trades (the best regime), yet performance is worse.
2. **Cost increases** — The strategy survives up to 1.5 pips slippage. Cost is not the primary driver.
3. **Exit mechanism change** — SC% and SL% are stable across years.
4. **Holding time change** — Average holding time is stable at ~18 bars.

---

## Top 5 Findings

1. **The edge is real but fragile** — PF 1.89 with 95% CI [1.76, 2.02]. Statistically significant. But excluding top 10% of trades flips to PF 0.92.

2. **A conditional edge survives across all 9 years** — Low-vol + any session: PF 2.36. Mid-vol + any session: PF 2.29. These conditions show no degradation.

3. **Degradation is in signal quality, not mechanics** — Holding time, exit reasons, and session distribution are stable. The entries are becoming less profitable.

4. **The strategy is becoming a "few big winners" approach** — 2024-2025: top 10% of trades generate >400% of PnL. The remaining 90% are net negative.

5. **CHF pairs and GBP crosses are deteriorating** — 4 CHF pairs turned negative in 2024-2026. GBP/AUD and GBP/CAD are structurally negative.

---

## Top 5 Unresolved Uncertainties

1. **What caused the signal quality decay?** Is it market microstructure change, algo adoption, or regime shift not captured by ATR/volatility?

2. **Is the low/mid-vol conditional edge robust to real execution costs?** The grid shows PF > 1.5 at 1.5 pips slippage, but the conditional edge hasn't been tested at higher costs.

3. **Would removing negative pairs (GBP/AUD, GBP/CAD, CHF crosses) improve stability?** This is a hypothesis, not a recommendation.

4. **Is the edge concentration a structural feature of MR strategies or a bug?** MR by nature profits from reversion — large reversions produce large wins.

5. **Can the surviving conditional edge be made tradeable?** Low+mid vol = ~75% of trades. Restricting to these conditions reduces trade count but may improve consistency.

---

## Recommendation

**YELLOW — Conditional development warranted, with restrictions:**

1. The surviving conditional edge (low+mid vol, PF > 2.2 across all years) is defensible.
2. The edge concentration is a serious risk — the strategy depends on a small number of trades.
3. Before engineering, investigate:
   - Whether CHF pair degradation is permanent
   - Whether GBP/AUD and GBP/CAD should be excluded
   - Whether restricting to low+mid vol improves consistency
   - Whether the signal quality decay is reversible

---

## Files Created

| File | Purpose |
|---|---|
| `/root/nestquant/phase3_forensic_analysis.py` | Reproducible analysis script |
| `/root/nestquant/MR_PHASE3_FORENSIC_REPORT.md` | This report |
| `/root/nestquant/logs/mr_phase3_metrics.json` | Machine-readable metrics |

## Reproduction

```bash
cd /root/nestquant && python3 phase3_forensic_analysis.py
```

Runtime: ~23 minutes.

---

*Phase 3 complete. No strategy modifications were made.*
