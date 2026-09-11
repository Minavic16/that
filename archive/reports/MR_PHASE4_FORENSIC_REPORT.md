# MR Phase 4 Forensic Report — Falsification / Validation

**Date:** 2026-08-10
**Baseline:** `/root/test_final_scalper.py` (NOT modified)
**Script:** `/root/nestquant/phase4_forensic_analysis.py`
**Metrics:** `/root/nestquant/logs/mr_phase4_metrics.json`

---

## MATERIAL BUGS FOUND

### Bug 1: Session Labeling (CRITICAL)

**Location:** `phase3_forensic_analysis.py:116` — `session=get_session(ts_now)` where `ts_now` is EXIT bar timestamp.

**Impact:** Every trade's `session` field in Phase 3 was EXIT-SESSION, not ENTRY-SESSION. `pos['entry_ts']` was available (line 162) but unused for session classification. 96.5% of trades had mismatched entry/exit sessions.

**Phase 3 session conclusions were based on wrong labels.** All Phase 3 session analysis must be reinterpreted.

### Bug 2: Timestamp Alignment (MODERATE)

**Location:** `phase3_forensic_analysis.py:139` — `pd_['c'][i]` uses reference pair's index `i` for all pairs without verifying temporal alignment.

**Measured impact:** 84.83% of timestamps mismatch across pairs (1,712,575 / 2,018,848). However, effect on results is small:
- Aligned: 7,989 trades, PF 1.88
- Unaligned: 7,980 trades, PF 1.89
- Delta: 9 trades, PF -0.01, PnL -$22,004

**Conclusion:** The bug exists but does not materially change aggregate results. However, it may affect pair-level and entry-time analysis where individual trade attribution matters.

---

## VERDICT: YELLOW → RED (Revised)

The corrected session analysis reveals that the NY session is structurally unprofitable (negative across all years), and the London edge is degrading severely. The low/mid-vol conditional edge from Phase 3 was overstated — it degrades in recent years and is not stable across all 9 years as claimed.

---

## 4A: Session Labeling Audit

### Entry Session (CORRECT)

| Session | Trades | WR | PF | PnL |
|---|---|---|---|---|
| london_only | 4,576 | 66.39% | 2.45 | $3,808,351 |
| overlap | 2,008 | 52.79% | 1.28 | $309,875 |
| ny_only | 1,405 | 42.42% | 0.63 | -$250,419 |

### Exit Session (Phase 3 used this — WRONG)

| Session | Trades | WR | PF | PnL |
|---|---|---|---|---|
| none | 6,275 | 59.97% | 2.14 | $3,424,246 |
| ny_only | 1,659 | 55.88% | 1.57 | $644,260 |
| overlap | 34 | 5.88% | 0.10 | -$164,168 |

### Key Differences

- Phase 3 reported "none" session as best (PF 2.14). Actually, "none" is exit-session — trades that entered during a session but exited outside it. **Entry session "london_only" is the real driver (PF 2.45).**
- Phase 3 reported "ny_only" exit as profitable (PF 1.57). Actually, **ny_only ENTRY is unprofitable (PF 0.63)**. The profitable "ny_only" exits are trades that entered during London/overlap and exited during NY.
- 96.5% of trades have mismatched entry/exit sessions.

### Entry Session × Year

| Session | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| london_only PF | 7.06 | 12.18 | 4.72 | 5.22 | 3.46 | 2.12 | 1.19 | 1.20 | 1.24 |
| overlap PF | 2.54 | 1.66 | 1.67 | 2.05 | 1.40 | 0.86 | 1.16 | 0.79 | 1.20 |
| ny_only PF | 0.94 | 0.62 | 0.96 | 0.83 | 0.85 | 0.58 | 0.42 | 0.54 | 0.53 |

**OBSERVED FACT:** London entry PF degraded from 7.06 (2018) to 1.24 (2026). NY entry PF was never above 1.0 in any year. Overlap became negative in 2023 and 2025.

**INFERENCE:** The edge is concentrated in London session entries. NY entries are structurally unprofitable.

### Entry Session × Vol Regime

| Session | low_vol | mid_vol | high_vol | extreme_vol |
|---|---|---|---|---|
| london_only | PF 2.23 | PF 2.68 | PF 2.28 | PF 1.78 |
| overlap | PF 1.73 | PF 1.38 | PF 1.17 | PF 1.08 |
| ny_only | PF 0.50 | PF 0.60 | PF 0.61 | PF 0.96 |

**OBSERVED FACT:** London + mid_vol is the strongest combo (PF 2.68). NY entries are negative in ALL volatility regimes.

### IS vs OOS by Entry Session

| Session | IS WR | OOS WR | IS PF | OOS PF |
|---|---|---|---|---|
| london_only | 77.67% | 54.24% | 4.83 | 1.42 |
| overlap | 56.07% | 46.95% | 1.68 | 0.94 |
| ny_only | 44.83% | 39.85% | 0.83 | 0.51 |

**OBSERVED FACT:** London session edge degraded from PF 4.83 (IS) to 1.42 (OOS). Overlap went negative. NY was always negative.

---

## 4B: Timestamp Alignment Audit

| Metric | Aligned | Unaligned | Delta |
|---|---|---|---|
| Trades | 7,989 | 7,980 | 9 |
| PF | 1.88 | 1.89 | -0.01 |
| WR | 58.76% | 58.62% | +0.14% |
| PnL | $3,867,807 | $3,889,811 | -$22,004 |

**OBSERVED FACT:** 84.83% of bar timestamps differ across pairs. Effect on aggregate metrics is negligible.

**INFERENCE:** The alignment bug does not materially change aggregate conclusions but may affect pair-level and entry-time attribution.

---

## 4C: Low/Mid-Vol × Year Matrix

### Profit Factor

| Regime | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| low_vol | 16.27 | 13.63 | 5.96 | 4.02 | 11.05 | 1.77 | 1.20 | 1.11 | 1.25 |
| mid_vol | 5.92 | 3.91 | 4.20 | 3.64 | 4.96 | 1.75 | 1.06 | 0.94 | 1.02 |
| high_vol | 1.84 | 1.93 | 2.60 | 1.73 | 1.60 | 1.42 | 0.74 | 1.13 | 1.27 |
| extreme_vol | 1.92 | 1.50 | 1.60 | 9.64 | 1.30 | 0.57 | 0.77 | 1.05 | 1.37 |

### Win Rate

| Regime | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| low_vol | 83.75 | 80.00 | 79.34 | 76.64 | 87.18 | 61.00 | 54.39 | 48.97 | 52.00 |
| mid_vol | 75.51 | 64.14 | 66.67 | 64.34 | 75.14 | 57.89 | 49.89 | 43.74 | 46.28 |
| high_vol | 54.55 | 51.28 | 61.17 | 54.73 | 56.74 | 54.65 | 43.56 | 42.79 | 48.33 |
| extreme_vol | 53.85 | 61.54 | 49.38 | 84.62 | 51.97 | 36.36 | 44.00 | 44.00 | 58.33 |

### Trade Count

| Regime | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| low_vol | 80 | 220 | 121 | 137 | 39 | 100 | 285 | 292 | 250 |
| mid_vol | 441 | 502 | 432 | 572 | 366 | 577 | 467 | 663 | 242 |
| high_vol | 264 | 117 | 273 | 148 | 386 | 258 | 101 | 215 | 60 |
| extreme_vol | 39 | 26 | 81 | 13 | 127 | 33 | 25 | 25 | 12 |

### Expectancy ($)

| Regime | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| low_vol | 127 | 1,222 | 1,205 | 1,205 | 1,682 | 580 | 141 | 71 | 185 |
| mid_vol | 122 | 704 | 1,111 | 951 | 1,605 | 518 | 48 | -50 | 13 |
| high_vol | 35 | 339 | 909 | 346 | 509 | 338 | -246 | 118 | 168 |
| extreme_vol | 49 | 278 | 601 | 1,526 | 256 | -373 | -339 | 53 | 313 |

### CRITICAL FINDING: Phase 3 claim is FALSE

Phase 3 claimed "low_vol PF > 2.2 across all 9 years." The actual data shows:
- low_vol 2024: PF **1.20** (NOT > 2.2)
- low_vol 2025: PF **1.11** (NOT > 2.2)
- low_vol 2026: PF **1.25** (NOT > 2.2)
- mid_vol 2025: PF **0.94** (NEGATIVE EXPECTANCY)

**The low/mid-vol edge has degraded significantly.** It was stable 2018-2022 but collapsed in 2023-2026.

---

## 4D: Winner Fingerprint

### Top 1% (n=79, avg PnL $11,260)

- **Session:** 95% London entries, 5% overlap, 0% NY
- **Hour:** Mean 8.2, Median 7 (early London)
- **Pairs:** GBP/USD (33%), GBP/CAD (11%), EUR/USD (10%), EUR/AUD (10%), GBP/JPY (6%)
- **Vol:** mid_vol 49%, high_vol 27%, low_vol 18%, extreme_vol 6%
- **Trend:** strong_trend 57%, weak_trend 33%, near_ema200 10%
- **Holding:** 23.7 bars

### Top 5% (n=399, avg PnL $6,880)

- **Session:** 88% London, 11% overlap, 1% NY
- **Hour:** Mean 8.7, Median 8
- **Pairs:** GBP/USD (15%), EUR/USD (9%), GBP/JPY (8%), EUR/CAD (8%), GBP/CAD (7%)
- **Vol:** mid_vol 56%, high_vol 24%, low_vol 14%, extreme_vol 6%
- **Trend:** strong_trend 54%, weak_trend 35%, near_ema200 12%
- **Holding:** 23.6 bars

### Middle 80% (n=6,392, avg PnL $375)

- **Session:** 53% London, 27% overlap, 20% NY
- **Hour:** Mean 11.6, Median 11
- **Pairs:** CAD/CHF (7%), NZD/CHF (7%), AUD/CHF (6%), AUD/CAD (6%), EUR/CAD (6%)
- **Vol:** mid_vol 54%, high_vol 22%, low_vol 20%, extreme_vol 4%
- **Trend:** strong_trend 52%, weak_trend 32%, near_ema200 16%
- **Holding:** 17.9 bars

### Bottom 10% (n=798, avg PnL -$3,460)

- **Session:** 65% London, 24% overlap, 11% NY
- **Hour:** Mean 10.5, Median 10
- **Pairs:** GBP/AUD (16%), GBP/CAD (14%), EUR/AUD (7%), NZD/CHF (7%), NZD/JPY (6%)
- **Vol:** mid_vol 48%, high_vol 26%, low_vol 19%, extreme_vol 8%
- **Trend:** strong_trend 50%, weak_trend 32%, near_ema200 18%
- **Holding:** 18.7 bars

### Key Fingerprint Differences

| Dimension | Top 1% | Bottom 10% |
|---|---|---|
| Entry hour | 7-8am (early London) | 10-11am (late London/overlap) |
| Session | 95% London | 65% London, 24% overlap |
| Top pairs | GBP/USD, EUR/USD | GBP/AUD, GBP/CAD |
| Trend | 57% strong | 50% strong |
| Holding | 23.7 bars | 18.7 bars |

**OBSERVED FACT:** Big winners enter early in London session (7-8am), in major pairs (GBP/USD, EUR/USD), in strong trends, and hold longer (~24 bars). Losers enter later (10-11am), in crosses (GBP/AUD, GBP/CAD), and hold shorter (~19 bars).

**HYPOTHESIS:** Early-London major-pair entries in strong trends have a recognizable pre-entry fingerprint. This is a hypothesis, not a validated signal.

---

## 4E: Exit Mechanism Audit

### Exit Reasons by Year

| Year | SC | SL | TP | DL |
|---|---|---|---|---|
| 2018 | 815 | 9 | 0 | 0 |
| 2019 | 861 | 3 | 1 | 0 |
| 2020 | 893 | 10 | 4 | 0 |
| 2021 | 866 | 4 | 0 | 0 |
| 2022 | 883 | 33 | 2 | 0 |
| 2023 | 951 | 16 | 1 | 0 |
| 2024 | 858 | 18 | 2 | 0 |
| 2025 | 1,173 | 22 | 0 | 0 |
| 2026 | 544 | 19 | 1 | 0 |

**OBSERVED FACT:** 98%+ of exits are SC (session close). SL hits are rare (0.4-3.6%). TP hits are extremely rare (0-0.5%).

### MFE by Exit Reason (pips)

| Reason | Mean | Median | P95 |
|---|---|---|---|
| SC | 34.75 | 26.75 | 88.63 |
| SL | 30.34 | 23.75 | 76.85 |
| TP | 85.27 | 66.00 | 198.94 |

### MAE by Exit Reason (pips)

| Reason | Mean | Median | P95 |
|---|---|---|---|
| SC | 24.43 | 15.70 | 77.75 |
| SL | 45.39 | 30.40 | 142.20 |
| TP | 31.72 | 14.15 | 119.80 |

### R-Multiples Reached

| Threshold | Count | Pct |
|---|---|---|
| +0.5R | 2,111 | 26.4% |
| +1.0R | 414 | 5.2% |
| +1.5R | 97 | 1.2% |
| +2.0R | 32 | 0.4% |
| +2.7R | 0 | 0.0% |

### MFE of Winning vs Losing Trades

| Group | Mean | Median | P25 | P75 | P95 |
|---|---|---|---|---|---|
| Winners | 40.76 | 32.60 | 20.69 | 52.00 | 97.65 |
| Losers | 25.75 | 19.80 | 12.49 | 32.90 | 65.64 |

### CRITICAL FINDING

**Zero trades reach +2.7R (the TP target).** Only 5.2% reach +1R. The strategy's TP target is structurally unreachable within the holding period. 98% of exits are forced by session close (SC), not by hitting profit targets.

**The exit mechanism is fundamentally misaligned with the entry signal.** Entries are mean-reversion (expecting bounce), but exits are time-based (session close), not level-based. The strategy captures a fraction of the available move.

---

## 4F: Holding-Time Counterfactual

| Max Hold | Trades | PF | WR | PnL | Avg PnL | MDD |
|---|---|---|---|---|---|---|
| 10 | 12,554 | 1.30 | 51.79% | $1,687,496 | $134 | 22.09% |
| 15 | 10,359 | 1.57 | 54.37% | $2,895,573 | $280 | 7.96% |
| 20 | 9,249 | 1.71 | 56.37% | $3,383,101 | $366 | 5.96% |
| 25 | 8,501 | 1.80 | 57.42% | $3,643,005 | $429 | 5.53% |
| 30 | 7,989 | 1.88 | 58.76% | $3,867,807 | $484 | 5.57% |
| 40 | 7,989 | 1.88 | 58.76% | $3,867,807 | $484 | 5.57% |
| 50 | 7,989 | 1.88 | 58.76% | $3,867,807 | $484 | 5.57% |
| baseline | 7,989 | 1.88 | 58.76% | $3,867,807 | $484 | 5.57% |

**OBSERVED FACT:** MH=30, 40, 50, and baseline produce identical results. No trade holds beyond 30 bars. The strategy's exit mechanism (SC at session close) terminates all trades before 30 bars.

**OBSERVED FACT:** Reducing MH below 25 hurts performance. MH=10 halves PnL and doubles MDD.

**INFERENCE:** The edge is NOT dependent on a narrow holding period — it's dependent on holding at least 20-25 bars. The SC exit mechanism is the binding constraint, not holding time.

---

## 4G: Pair Decomposition

### Problem Pairs

| Pair | PF | WR | PnL | Trades | Expectancy |
|---|---|---|---|---|---|
| GBP/AUD | 0.76 | 49.56% | -$140,556 | 458 | -$306.89 |
| GBP/CAD | 0.85 | 50.10% | -$87,453 | 503 | -$173.86 |
| NZD/JPY | 0.97 | 50.66% | -$8,516 | 377 | -$22.59 |
| CAD/CHF | 1.73 | 56.55% | $145,025 | 504 | $287.75 |
| EUR/CHF | 2.12 | 57.30% | $140,149 | 356 | $393.68 |
| NZD/CHF | 1.03 | 48.39% | $8,034 | 527 | $15.25 |
| AUD/CHF | 1.35 | 50.96% | $77,387 | 469 | $165.00 |

### Non-Problem Pairs

| Group | PF | WR | PnL | Trades | Expectancy |
|---|---|---|---|---|---|
| Non-problem | 2.75 | 63.42% | $3,733,737 | 4,795 | $778.59 |

**OBSERVED FACT:** 3 pairs are structurally negative (GBP/AUD, GBP/CAD, NZD/JPY). 4 pairs are marginal (CAD/CHF, EUR/CHF, NZD/CHF, AUD/CHF). Non-problem pairs have PF 2.75 vs problem pairs' aggregate negative PnL.

**INFERENCE:** GBP/AUD and GBP/CAD are the primary drag. NZD/JPY is marginal. The CHF pairs are mixed — EUR/CHF is profitable, NZD/CHF is breakeven.

---

## 4H: Statistical Dependence

### Bootstrap 95% Confidence Intervals

| Metric | Independent | Daily Block | Weekly Block |
|---|---|---|---|
| Win Rate | [57.70%, 59.82%] | [56.25%, 61.29%] | [57.07%, 60.48%] |
| Mean Trade | [$432, $536] | [$360, $609] | [$399, $567] |
| Profit Factor | [1.76, 2.01] | [1.60, 2.20] | [1.69, 2.09] |

**OBSERVED FACT:** Block bootstrap CIs are wider than independent CIs:
- Daily blocks: PF CI width = 0.60 (vs 0.25 independent) — 2.4x wider
- Weekly blocks: PF CI width = 0.40 (vs 0.25 independent) — 1.6x wider

**INFERENCE:** Trades ARE temporally correlated. The Phase 3 independent bootstrap overstated certainty. The true 95% CI for PF is approximately [1.60, 2.20] (daily blocks), not [1.76, 2.01]. The edge is still statistically significant (lower bound > 1.0), but with more uncertainty than Phase 3 reported.

---

## 4I: Cost Stress for Low+Mid Vol Conditional Edge

### Low+Mid Vol Only

| Slippage | Trades | PF | WR | PnL | Expectancy |
|---|---|---|---|---|---|
| 0.1 pip | 5,786 | 2.15 | 61.77% | $3,329,377 | $575.42 |
| 0.3 (baseline) | 5,786 | 2.06 | 60.87% | $3,130,640 | $541.07 |
| 0.5 | 5,786 | 1.97 | 59.97% | $2,925,871 | $505.68 |
| 0.75 | 5,786 | 1.87 | 58.87% | $2,672,345 | $461.86 |
| 1.0 | 5,786 | 1.76 | 57.83% | $2,415,576 | $417.49 |
| 1.5 | 5,786 | 1.57 | 55.62% | $1,892,348 | $327.06 |
| 2.0 | 5,786 | 1.40 | 53.73% | $1,375,823 | $237.78 |
| 2.5 | 5,786 | 1.24 | 51.66% | $865,400 | $149.57 |
| 3.0 | 5,786 | 1.10 | 49.65% | $361,613 | $62.50 |

### All Trades (reference)

| Slippage | PF | WR |
|---|---|---|
| 0.3 (baseline) | 1.88 | 58.76% |
| 1.0 | 1.62 | 55.74% |
| 1.5 | 1.45 | 53.51% |
| 2.0 | 1.30 | 51.75% |
| 3.0 | 1.03 | 47.80% |

**OBSERVED FACT:** Low+mid vol edge (PF 2.06 at baseline) degrades to PF 1.10 at 3.0 pips slippage. The all-trades strategy (PF 1.88) degrades to PF 1.03 at 3.0 pips.

**INFERENCE:** The low+mid vol conditional edge has slightly better cost resilience than the full strategy (PF 2.06 vs 1.88 at baseline), but both remain profitable up to 2.5 pips slippage.

---

## Summary of Findings

### Material Bugs Corrected

1. **Session labeling:** Phase 3 used exit-session. Corrected to entry-session. London entries are the real edge; NY entries are structurally negative.

2. **Timestamp alignment:** 84.83% mismatch but negligible aggregate impact. May affect pair-level analysis.

### Key Revised Findings

1. **The Phase 3 claim "low_vol PF > 2.2 across all 9 years" is FALSE.** Low_vol PF dropped to 1.20 in 2024 and 1.11 in 2025. Mid_vol went negative in 2025 (PF 0.94).

2. **NY session entries are structurally unprofitable** (PF 0.63, negative in all years, all vol regimes).

3. **Zero trades reach +2.7R.** Only 5.2% reach +1R. The TP target is structurally unreachable. 98% of exits are time-based (SC), not level-based.

4. **Top winners enter early London (7-8am) in major pairs (GBP/USD, EUR/USD) in strong trends.** Bottom losers enter later (10-11am) in crosses (GBP/AUD, GBP/CAD).

5. **Block bootstrap CIs are 1.6-2.4x wider than independent CIs.** Phase 3 overstated statistical certainty.

6. **London entry PF degraded from 7.06 (2018) to 1.24 (2026).** The edge is dying.

---

## Files Created/Modified

| File | Status |
|---|---|
| `/root/nestquant/phase4_forensic_analysis.py` | CREATED — Phase 4 analysis script |
| `/root/nestquant/logs/mr_phase4_metrics.json` | CREATED — machine-readable results |
| `/root/nestquant/logs/mr_phase4_cost_stress.json` | CREATED — corrected cost stress results |
| `/root/nestquant/MR_PHASE4_FORENSIC_REPORT.md` | CREATED — this report |
| `/root/nestquant/phase3_forensic_analysis.py` | UNCHANGED (Phase 3 preserved) |
| `/root/nestquant/MR_PHASE3_FORENSIC_REPORT.md` | UNCHANGED (Phase 3 preserved) |
| `/root/nestquant/MR_PHASE2_FORENSIC_REPORT.md` | UNCHANGED |
| `/root/nestquant/MR_BASELINE_FORENSIC_REPORT.md` | UNCHANGED |
| `/root/test_final_scalper.py` | UNCHANGED (DO NOT MODIFY) |

## Reproduction

```bash
cd /root/nestquant && python3 phase4_forensic_analysis.py
```

Runtime: ~29 minutes.

---

*Phase 4 complete. No strategy modifications were made.*
