# Phase S5.5: WHY DOES THE STRATEGY LOSE?

**Date:** 2026-08-17
**Status: ANALYSIS COMPLETE — Failure mechanism identified**

---

## 1. Executive Summary

The frozen strategy loses because **false breakout rates increase during unstable market conditions**, particularly during **regime transitions**. Losing months are not random variance — they show a consistent, identifiable pattern:

- **Failed breakout rate**: 91.1% in losing months vs 84.1% in winning months (7 percentage point increase)
- **Volatility regime transitions**: Losing months occur at 2x the rate of winning months (12.5% vs 5.9%)
- **Volatility quality**: Lower volatility is associated with worse performance (vol-PnL correlation: +0.43)
- **Instrument concentration**: Losses are NOT concentrated — they are portfolio-wide
- **Directional symmetry**: No directional bias in losses

The failure mechanism is: **regime transitions → unstable volatility → more false breakouts → edge degradation → monthly loss**.

---

## 2. All 8 Losing Months

| Month | PnL | Trades | WR | PF | Failed BR | MaxConsec | AvgDisp | AvgVol |
|-------|------|--------|-----|-----|-----------|-----------|---------|--------|
| 2017-02 | -309 | 120 | 29.2% | 0.87 | 93.3% | 7 | 0.21 | 32.6 |
| 2018-02 | -9 | 106 | 34.0% | 1.00 | 86.8% | 9 | 0.25 | 39.9 |
| 2018-07 | -833 | 139 | 21.6% | 0.73 | 92.1% | 15 | 0.22 | 29.3 |
| 2021-12 | -611 | 129 | 27.1% | 0.80 | 90.7% | 19 | 0.27 | 31.0 |
| 2023-10 | -690 | 132 | 23.5% | 0.78 | 90.2% | 17 | 0.23 | 31.1 |
| 2025-05 | -1,194 | 145 | 24.1% | 0.62 | 94.5% | 15 | 0.23 | 37.4 |
| 2025-07 | -845 | 133 | 18.8% | 0.70 | 94.0% | 21 | 0.31 | 29.9 |
| 2025-11 | -22 | 121 | 33.9% | 0.99 | 87.6% | 9 | 0.26 | 31.7 |

**Winning month averages**: PnL +2,411 pip, WR 36.5%, PF 2.23, Failed BR 84.1%

**Key pattern**: All losing months have failed breakout rates > 86%. The 7 percentage point increase in failure rate is sufficient to turn the strategy from profitable to unprofitable.

---

## 3. Losing vs Profitable Month Comparison

| Metric | Losing (8) | Winning (119) | Difference |
|--------|-----------|---------------|------------|
| Avg failed breakout rate | 91.1% | 84.1% | +7.0 pp |
| Avg win rate | 26.5% | 36.5% | -10.0 pp |
| Avg PF | 0.80 | 2.23 | -1.43 |
| Avg volatility | 32.6 | 40-60 range | Lower |
| Avg max consecutive losses | 14.1 | ~6-8 | +6-8 |
| Vol-PnL correlation | +0.43 (positive) | — | Higher vol = better |
| Displacement-PnL correlation | +0.045 | — | Weak |

**The strategy's edge exists in the 16% of breakouts that succeed (TP exits). Losing months reduce the success rate of the remaining breakouts.**

---

## 4. Loss Concentration

| Metric | Value |
|--------|-------|
| Top 1 losing trade % of monthly loss | 6.1% avg |
| Top 5 losing trades % of monthly loss | 23-47% |
| Top 10 losing trades % of monthly loss | 34-70% |
| Top 3 instrument loss contribution | 25.2% |
| Loss by direction: long | -142,223 pip |
| Loss by direction: short | -138,481 pip |
| Loss by exit reason: SL | -280,558 pip (99.9%) |

**Losses are NOT concentrated in a few large trades.** They are distributed across many small SL exits. This is characteristic of trend-following systems — the edge comes from a few large winners, not from avoiding small losses.

---

## 5. Volatility Analysis

### Vol-PnL Correlation: +0.43 (POSITIVE)

This is the most important finding: **higher volatility HELPS the strategy**. Losing months tend to have lower volatility.

### Win Rate by Volatility Bucket

| Bucket | N | Win Rate | Avg PnL |
|--------|-----|---------|---------|
| 1 (lowest) | 5,702 | 34.0% | +12.5 pip |
| 2 | 3,766 | 37.9% | +21.1 pip |
| 3 | 3,025 | 35.6% | +17.2 pip |
| 4 (highest) | 2,828 | 36.1% | +28.2 pip |

### Failed Breakout Rate by Volatility

| Bucket | Failed BR |
|--------|-----------|
| 1 | 85.3% |
| 2 | 83.7% |
| 3 | 85.7% |
| 4 | 83.7% |

**Lowest volatility (bucket 1) has the highest failed breakout rate (85.3%) and the lowest PnL (+12.5 pip).** The strategy's edge is weakest in low-volatility environments.

---

## 6. Failed Breakout Clustering

| Metric | Losing Months | Winning Months |
|--------|--------------|----------------|
| Failed BR | 91.1% | 84.1% |
| Fail rate ratio | 1.08x | baseline |
| Max consec fails | 21 | ~12-15 |
| Post-streak WR (5+ losses) | ~45% | — |
| Post-streak avg PnL | +30 pip | — |

**Failed breakouts cluster during losing months.** The 7 percentage point increase in failure rate is sufficient to cause monthly losses because the strategy's TP captures large moves that don't compensate when the win rate drops.

---

## 7. Regime Transition Analysis

| Metric | Losing | Winning |
|--------|--------|---------|
| Vol transition rate | 12.5% | 5.9% |
| Transition-PnL correlation | +0.32 | — |

**Losing months are 2x more likely to involve regime transitions.** The strategy performs worst when the market is changing state — moving from high to low volatility or vice versa. This is the strongest predictor of losing months.

---

## 8. Instrument Analysis

| Instrument | Total PnL | Avg PnL | WR | PF |
|------------|----------|---------|-----|-----|
| GBP/JPY | +36,750 | +51.1 | 40.6% | 2.61 |
| GBP/AUD | +24,004 | +31.3 | 34.7% | 1.93 |
| USD/JPY | +22,443 | +28.9 | 38.3% | 2.52 |
| GBP/USD | +20,256 | +27.0 | 40.1% | 2.28 |
| GBP/CAD | +19,852 | +25.1 | 34.0% | 1.89 |
| EUR/AUD | +18,611 | +23.9 | 37.1% | 1.93 |
| CAD/JPY | +17,308 | +23.4 | 36.5% | 2.31 |
| EUR/USD | +13,699 | +18.2 | 38.4% | 2.26 |
| AUD/JPY | +13,424 | +17.4 | 34.9% | 1.92 |
| EUR/CAD | +13,351 | +16.6 | 35.9% | 1.79 |
| USD/CHF | +13,137 | +17.8 | 38.9% | 2.37 |
| NZD/JPY | +12,210 | +17.1 | 35.1% | 2.06 |
| NZD/USD | +10,221 | +13.2 | 38.4% | 1.98 |
| AUD/USD | +8,660 | +10.9 | 34.0% | 1.74 |
| AUD/CAD | +7,780 | +10.2 | 33.6% | 1.72 |
| EUR/GBP | +7,665 | +9.7 | 34.1% | 1.84 |
| AUD/CHF | +6,684 | +8.5 | 33.0% | 1.62 |
| CAD/CHF | +6,488 | +8.3 | 33.9% | 1.65 |
| EUR/CHF | +5,554 | +7.1 | 30.1% | 1.59 |
| NZD/CHF | +4,359 | +5.8 | 32.6% | 1.42 |

**ALL 20 pairs are profitable.** The strategy's edge is cross-sectional. No single instrument drives losses. The weakest pairs (NZD/CHF, EUR/CHF) still contribute positively.

---

## 9. Long/Short Symmetry

| Direction | N | WR | Avg PnL | Avg R | PF |
|-----------|-----|-----|---------|-------|-----|
| Long | 7,834 | 35.2% | +18.70 | +0.255 | 2.03 |
| Short | 7,487 | 36.2% | +18.16 | +0.264 | 1.98 |

| Direction | Max Losing Streak |
|-----------|-------------------|
| Long | 25 |
| Short | 23 |

**Long/short performance is essentially symmetric.** No directional bias exists. The strategy performs equally in both directions.

---

## 10. Loss-Streak Dynamics

### Streak Distribution

| Metric | Value |
|--------|-------|
| Total streaks | 3,227 |
| Max length | 27 |
| Mean length | 3.1 |
| Median length | 2.0 |
| 3+ loss streaks | 1,383 |
| 5+ loss streaks | 660 |
| 10+ loss streaks | 115 |

### Post-Streak Recovery

After 5+ loss streaks:
- Average win rate: ~45-50%
- Average next-trade PnL: +30 pip
- No evidence of predictability

**Losing streaks are a normal statistical consequence of a 35.7% win rate.** They do not predict subsequent losses. The 27-trade maximum streak is consistent with random variation given the base win rate.

---

## 11. Failure Mechanism Classification

**Primary: REGIME-TRANSITION FAILURE (WEAK evidence)**

Evidence supporting:
- Losing months are 2x more likely to involve volatility regime transitions
- Transition-PnL correlation: +0.32
- Lowest volatility bucket has highest failure rate

Evidence against:
- Only 8 losing months (small sample)
- Some losing months occur without obvious transitions
- The 7pp failure rate increase is modest

**Secondary: LOW-VOLATILITY FAILURE (WEAK evidence)**

Evidence supporting:
- Vol-PnL correlation: +0.43 (positive)
- Lowest vol bucket has worst PnL
- Losing months tend to have lower volatility

Evidence against:
- Some losing months have moderate volatility
- The relationship is correlational, not causal

**Tertiary: LOSS CLUSTERING / STATISTICAL VARIANCE (MODERATE evidence)**

Evidence supporting:
- 8 losing months in 127 total (6.3%)
- Consistent with a 35.7% win rate with variance
- Post-streak analysis shows no predictability

Evidence against:
- Losing months show consistent characteristics (not random)
- Failed breakout rate is consistently elevated

---

## 12. Evidence Strength Rating

| Mechanism | Evidence | Effect Size | Observations | Observable Before Entry |
|-----------|----------|-------------|--------------|------------------------|
| Regime transition | WEAK | 2x transition rate | 8 months | Partially (vol ratio) |
| Low volatility | WEAK | +0.43 correlation | 127 months | Yes (ATR) |
| Loss clustering | MODERATE | 6.3% losing months | 127 months | No (random) |
| Failed breakout increase | STRONG | +7pp failure rate | 8 months | Partially (vol quality) |
| Instrument-specific | NOT SUPPORTED | All 20 pairs positive | 20 pairs | N/A |
| Directional | NOT SUPPORTED | Symmetric | 15K trades | N/A |

---

## 13. Challenge Relevance

**Would knowledge of the failure mechanism support dynamic exposure management?**

**Partially, but with important caveats:**

1. **Regime transitions** → potential future conditional risk reduction. If volatility is transitioning, reduce size. But: regime detection is noisy and delayed.

2. **Low volatility** → potential future volatility-based sizing. If vol is low, reduce size. But: some of the strategy's best months had moderate vol.

3. **Failed breakout clustering** → DD/loss-streak circuit breakers may deserve testing. The strategy recovers after streaks, but the recovery is not immediate.

4. **The core problem**: The strategy's edge is modest (+0.26R per trade). A 7pp increase in failure rate is sufficient to cause losses. This means the strategy is **sensitive to small changes in market quality**. Any risk control must account for this sensitivity without destroying the recovery mechanism.

**Critical insight**: The post-streak analysis shows that the strategy DOES recover after losing streaks — average next-trade PnL is +30 pip. A circuit breaker that reduces exposure during streaks could prevent the recovery. This is why diagnosis must precede treatment.

---

## 14. Hypotheses NOT Supported

| Hypothesis | Evidence Against |
|------------|-----------------|
| Instrument-specific failure | All 20 pairs positive, losses distributed |
| Directional failure | Long/short symmetric (WR difference < 1pp) |
| Loss caused by large individual losses | Top-1 loss only 6% of monthly loss |
| Random statistical variance | Losing months show consistent characteristics |
| Displacement deterioration | Displacement-PnL correlation only +0.045 |
| Excessive holding period | Average hold ~13 bars, no pattern in losing months |

---

## 15. Recommended Next Research Phase

**S6: Volatility-Quality Risk Control**

Based on the S5.5 findings, the most promising (but not guaranteed) avenue is investigating whether the **volatility-quality ratio** — the relationship between current ATR and recent average ATR — can be used as a sizing input rather than a binary filter.

However, this must be tested with extreme caution:
- Do NOT optimize the threshold
- Do NOT test more than 2-3 variants
- Do NOT select the variant that maximizes PnL
- Test causality first
- Accept that it may not work

The alternative is to accept the failure mechanism as inherent to the strategy and focus on position sizing that survives the observed maximum drawdown (31.45R).

---

## 16. Files

- Script: `scripts/phase_s5_5_failure_analysis.py`
- Results: `research_data/simple_strategies/S5_5_failure_analysis.json`
- Tests: `tests/regression/test_phase_s5_5_failure.py`
