# S8.6 REVIEW ADDENDUM — Forensic Audit

**Date:** 2026-09-04
**Audit Type:** Independent forensic review of S8.6 monitoring system
**Status:** CRITICAL DISCREPANCIES FOUND

---

## 1. CONFIRMED FINDINGS

### 1.1 Percentile Framework (CONFIRMED SOUND)

| Aspect | Status | Evidence |
|--------|--------|----------|
| MIN_SAMPLES enforcement | ✅ Correct | P50=10, P75=20, P90=30, P95=40, P99=100 |
| Bootstrap CI | ✅ Implemented | 1000 resamples, 95% CI |
| INSUFFICIENT labeling | ✅ Works | Labels appear when n < min_required |
| Empty data handling | ✅ Correct | Returns NaN, not zero |
| classify_value | ✅ Correct | Uses sufficient percentiles, falls back to inf |
| No universal threshold | ✅ Confirmed | Descriptive indicators only |

**Evidence population:** Unit tests (11 tests), code review of `monitoring/percentiles.py`.

### 1.2 EV Stability Implementation (CONFIRMED COMPLETE)

All requested metrics are implemented:

| Required | Implemented | Location |
|----------|------------|----------|
| mean trade return | ✅ | CoreEVMetrics.mean_return |
| mean R | ✅ | CoreEVMetrics.expectancy_r |
| expectancy | ✅ | CoreEVMetrics.mean_return |
| median return | ✅ | CoreEVMetrics.median_return |
| variance | ✅ | CoreEVMetrics.variance |
| standard deviation | ✅ | CoreEVMetrics.std |
| downside deviation | ✅ | CoreEVMetrics.downside_deviation |
| coefficient of variation | ✅ | CoreEVMetrics.coefficient_of_variation |
| rolling EV | ✅ | RollingWindow.ev |
| rolling variance | ✅ | RollingWindow.variance |
| rolling standard deviation | ✅ | RollingWindow.std |
| rolling win rate | ✅ | RollingWindow.win_rate |
| rolling profit factor | ✅ | RollingWindow.profit_factor |
| EV percentiles | ✅ | trade_return_distribution |
| rolling EV percentiles | ✅ | rolling_ev_distribution |
| sample count | ✅ | CoreEVMetrics.count, RollingWindow.trade_count |

**No universal threshold is implied.** Stability indicators are descriptive (positive_ev_pct, degradation_from_baseline, rolling_ev_std).

**Evidence population:** Unit tests (10 tests), code review of `monitoring/ev_stability.py`.

### 1.3 DD Clustering Implementation (CONFIRMED COMPLETE)

| Required | Implemented | Location |
|----------|------------|----------|
| episode start | ✅ | DDEpisode.start_idx |
| episode end | ✅ | DDEpisode.trough_idx |
| maximum depth | ✅ | DDEpisode.depth, depth_pct |
| duration | ✅ | DDEpisode.duration |
| number of trades | ✅ | DDEpisode.trades_during_dd |
| number of losses | ✅ | DDEpisode.losses_during_dd |
| recovery duration | ✅ | DDEpisode.recovery_time |
| time between episodes | ✅ | spacing_distribution |
| episodes per 100 trades | ✅ | episodes_per_100_trades |
| rolling clustered episodes | ✅ | max_clustered_in_window |
| probability within N trades | ✅ | cluster_probability_50/100 |
| random baseline comparison | ✅ | compute_random_baseline (shuffled returns) |

**Evidence population:** Unit tests (11 tests), code review of `monitoring/dd_clustering.py`.

### 1.4 Slippage/Latency/Spread/Equity/Health Collectors (CONFIRMED IMPLEMENTED)

All collectors exist and are functional:
- `SlippageTracker`: entry/exit measurement, JPY-aware, percentiles
- `LatencyTracker`: HTTP round-trip, per-component, percentiles
- `SpreadCollector`: bid/ask sampling, JSONL output, background thread
- `EquityTracker`: peak tracking, DD computation, daily PnL
- `HealthCollector`: bridge health, consecutive failures, uptime

**Evidence:** Unit tests (14 tests across 5 modules).

---

## 2. CORRECTED FINDINGS

### 2.1 CRITICAL: Strategy Identity Reconciliation

**The S8.6 report conflates two different strategy configurations.**

| Population | Trades | WR | PF | Max DD | breakeven | max_hold | Source |
|-----------|--------|-----|-----|--------|-----------|----------|--------|
| S0 | 1,002 | 73.0% | 5.32 | 520 pips | 0.8 | 7d | S0_breakout_results.json |
| S6A | 15,321 | 35.7% | 2.01 | 1,805 pips | NONE | NONE | S6_adaptive_risk_challenge.json |
| S5.5 | 15,321 | 35.9% (monthly avg) | 2.14 | 469 pips (monthly) | NONE | NONE | S5_5_failure_analysis.json |

**The deployed strategy (breakout.py) does NOT implement breakeven or max_hold.**
Verified by code inspection: `signals/breakout.py` contains no reference to `breakeven` or `max_hold`.

**Therefore:**
- S0's 73% WR is **NOT** the baseline for the deployed strategy
- S6A's 35.7% WR **IS** the correct baseline
- The S8.6 report uses the **wrong baseline** throughout

**Evidence:** Code inspection of `signals/breakout.py`, `S0_breakout_results.json`, `S6_adaptive_risk_challenge.json`.

### 2.2 CRITICAL: Trade Count Discrepancy

| Dataset | Trade Count | Aggregation | Notes |
|---------|------------|-------------|-------|
| S0 | 1,002 | Per-trade | Filtered by breakeven+max_hold |
| S6A | 15,321 | Per-trade | Unfiltered |
| S5.5 | 15,321 | Monthly (127 months) | Same trades as S6A |
| Phase 4 Z-Score | 74,755 | Per-trade | DIFFERENT strategy |
| S8.6 DD clustering test | 1,002 | Synthetic | Random data, not S0 |

**The 1,002 vs 15,321 discrepancy is because S0 filters trades via breakeven/max_hold.**
These are subsets of the same underlying trade stream, not independent datasets.

### 2.3 CORRECTED: Monthly WR vs Trade-Level WR

The S8.6 report states "Monthly WR: mean=35.9%". This is:
- The average of 127 monthly win rates
- Each monthly WR is computed from 61-145 trades within that month
- It is NOT a12-month rolling average of trade-level WR

**The 12-month rolling average of monthly WRs (used in CB calibration) is a DIFFERENT metric than what the live WinRateBreaker monitors (20-trade rolling trade-level WR).**

---

## 3. DISCREPANCIES

### 3.1 CRITICAL: Circuit Breaker Calibration Mismatch

| Aspect | S8.6 Report | Live System | Match? |
|--------|-------------|-------------|--------|
| Window size | 12 months | 20 trades | ❌ NO |
| Metric | Monthly WR (aggregate) | Trade-level WR | ❌ NO |
| Threshold | 40% | 40% | ✅ Same |
| Population | S5.5 monthly stats | Trade-level returns | ❌ NO |
| Conclusion | "0 triggers = correct" | Would trigger ~56% of time | ❌ WRONG |

**Simulation evidence:** With S6A baseline (35.7% WR), a 20-trade rolling window produces WR < 40% approximately 55.8% of the time (8,537 / 15,301 windows).

**The S8.6 conclusion that WinRateBreaker is "correctly calibrated" is wrong.** It tested the wrong metric against the wrong threshold.

### 3.2 CRITICAL: DD Clustering on Synthetic Data

The S8.6 report states "Episodes detected: 109 (out of 1002 trades)".
This was computed on a **random synthetic equity curve**:
```python
equity = np.cumsum(np.concatenate([
    np.array([100000.0]),
    np.random.RandomState(42).normal(66.5, 100, 1002),
]))
```

**109 episodes from random data is expected behavior (every dip is an episode).**
This does NOT represent actual strategy drawdown behavior.
The test is a smoke test, not a meaningful analysis.

### 3.3 CRITICAL: EV Stability Wrong Population

The S8.6 report analyzes S0 returns (1,002 trades, 73% WR).
The deployed strategy matches S6A (15,321 trades, 35.7% WR).

**EV stability conclusions are for the FILTERED population, not the DEPLOYED population.**

| Metric | S0 (filtered) | S6A (deployed) |
|--------|---------------|----------------|
| Mean return | 66.5 pips | 18.4 pips |
| Win rate | 73.0% | 35.7% |
| Profit factor | 5.32 | 2.01 |
| Max DD | 520 pips | 1,805 pips |

### 3.4 SUSPICIOUS: Monte Carlo Dollar Values

S6H Monte Carlo values at 0.25% risk on $200K:
- Median DD: $119.44 (0.06% of account, 0.24R)
- P95 DD: $219.21 (0.11% of account, 0.44R)
- Median Return: $24,800.46

**These values seem inconsistent with S6A max DD of 1,805 pips (19.61R).**
At 0.25% risk, 19.61R = $9,805. But MC shows P99 DD = $239 (0.48R).

**Possible explanations:**
1. MC simulation uses a different trade distribution than S6A
2. MC values are normalized differently
3. MC simulation has a bug

**These values should NOT be used as live risk thresholds without verification.**

### 3.5 MINOR: Dashboard Classification

The S8.6 report classifies the dashboard as "Complete" (✅ PASS).
**Actual status: Structural only.** The server imports and has endpoints, but:
- No data providers are wired
- All endpoints return empty/zero
- The HTML dashboard exists but has no live data
- The server has never been started with real data

**Classification should be: Structural implementation only, not operational.**

---

## 4. EXACT EVIDENCE POPULATIONS

### 4.1 Strategy Baselines

| Metric | Correct Baseline | Source | Population |
|--------|-----------------|--------|------------|
| Win rate | 35.7% | S6A | 15,321 trades, no breakeven/max_hold |
| Profit factor | 2.01 | S6A | Same |
| Max DD | 1,805 pips | S6A | Same |
| t-statistic | 25.35 | S6A | Same |
| Monthly WR | 35.9% (avg) | S5.5 | 127 months, same trades |
| Monthly PF | 2.14 (avg) | S5.5 | Same |
| Monthly Max DD | 469 pips (avg) | S5.5 | Same |
| Max consec losses | 17 trades | S6A | Same |
| Consec loss P95 | 16/month | S5.5 | Monthly level |

### 4.2 S0 (NOT the deployed baseline)

| Metric | Value | Notes |
|--------|-------|-------|
| Trades | 1,002 | FILTERED by breakeven=0.8, max_hold=7d |
| WR | 73.0% | Inflated by early breakeven exits |
| PF | 5.32 | Inflated by same |
| Max DD | 520 pips | Reduced by same |

**S0 results do NOT apply to the deployed strategy.**

### 4.3 What S8.6 Actually Analyzed

| Analysis | Population Used | Correct Population | Match? |
|----------|----------------|-------------------|--------|
| EV stability | S0 (1,002 trades) | S6A (15,321 trades) | ❌ |
| DD clustering | Synthetic random | S0 or S6A equity | ❌ |
| CB calibration | S5.5 monthly WR | Trade-level returns | ❌ |
| Percentiles | S5.5 monthly stats | Trade-level stats | ⚠️ Partial |

---

## 5. EV STABILITY FINDINGS

### 5.1 Implementation Assessment

**All required metrics are implemented correctly.** The EVStabilityAnalyzer computes:
- Core: mean, median, variance, std, downside deviation, CV, skewness, kurtosis, win rate, expectancy R
- Rolling: EV, variance, std, win rate, profit factor per window
- Distribution: trade return percentiles, rolling EV percentiles
- Stability: positive_ev_pct, degradation, rolling_ev_std

**No universal threshold is implied.** The system is descriptive, not prescriptive.

### 5.2 Data Quality Assessment

**The S8.6 analysis used the WRONG population.** EV stability was analyzed on S0 (filtered) instead of S6A (deployed). The conclusions about EV stability are not valid for the live system.

### 5.3 Recommendations

To properly assess EV stability for the deployed strategy:
1. Run EVStabilityAnalyzer on S6A trade-level returns (if available)
2. Or begin collecting live trade returns after C7 is fixed
3. Do not use S0 returns for monitoring thresholds

---

## 6. DD CLUSTERING FINDINGS

### 6.1 Implementation Assessment

**The implementation is complete and correct.** DDClusterAnalyzer:
- Detects episodes with start, trough, recovery
- Computes depth, duration, recovery time, losses during DD
- Analyzes spacing between episodes
- Compares with shuffled random baseline
- Uses CV > 1.2 heuristic for clustering detection

### 6.2 Data Quality Assessment

**The S8.6 analysis ran on SYNTHETIC data, not real equity curves.** The 109 episodes are meaningless because they come from random noise.

### 6.3 Recommendations

To properly assess DD clustering:
1. Run DDClusterAnalyzer on actual S6A equity curve (reconstruct from monthly PnL)
2. Or begin collecting live equity snapshots after infrastructure is wired
3. Do not use synthetic data for monitoring conclusions

---

## 7. CIRCUIT BREAKER FINDINGS

### 7.1 WinRateBreaker

| Aspect | Finding |
|--------|---------|
| S8.6 conclusion | "0/127 triggers = correctly calibrated" |
| Actual behavior | Would trigger ~56% of time on S6A data |
| Root cause | S8.6 tested monthly WR (12-month window) instead of trade-level WR (20-trade window) |
| Verdict | **INCORRECTLY CALIBRATED** for deployed strategy |

### 7.2 ProfitFactorBreaker

| Aspect | Finding |
|--------|---------|
| S8.6 conclusion | "0/127 triggers = correct" |
| Threshold | PF < 1.0 over 20 trades |
| S6A baseline PF | 2.01 |
| Assessment | Reasonable threshold; PF < 1.0 over 20 trades would indicate genuine deterioration |
| Verdict | **APPROPRIATELY CALIBRATED** (but never tested in production due to C7 gap) |

### 7.3 DrawdownPaceBreaker

| Aspect | Finding |
|--------|---------|
| Soft threshold | 6.0% DD in 15 trades |
| Hard threshold | 9.0% DD in 25 trades |
| S6A max DD | 1,805 pips = 19.61R |
| Assessment | At 0.5% risk, 9% DD = 18R. S6A shows 19.61R max DD. Threshold would trigger during normal max DD events. |
| Verdict | **NEEDS RECALIBRATION** to account for risk level |

### 7.4 SlippageBreaker

| Aspect | Finding |
|--------|---------|
| Consecutive threshold | 4.8 pips after 3 trades |
| Avg threshold | 6.0 pips over 10 trades |
| Empirical data | ZERO measured slippage data |
| Verdict | **UNVALIDATED** — arbitrary thresholds with no empirical basis |

### 7.5 Critical Gap: C7 Feedback

**None of the circuit breakers can function** because `record_trade_result()` is never called after execution. The breakers exist in code but receive no data. This is the #1 priority before live trading.

---

## 8. DASHBOARD STATUS

| Aspect | S8.6 Claim | Actual |
|--------|-----------|--------|
| Status | "Complete" | Structural only |
| Server | ✅ Imports | ✅ True |
| Endpoints | 11 API endpoints | ✅ True |
| HTML dashboard | Self-contained | ✅ True |
| Data providers | Not mentioned | ❌ None wired |
| Live data | Not mentioned | ❌ None |
| Operational | Implied | ❌ Never started with data |

**Classification: A (structural implementation only).**

The dashboard infrastructure is well-designed (dependency injection via providers, stdlib HTTP server, auto-refresh HTML). But it has never displayed real monitoring data.

---

## 9. DATA STILL MISSING

| # | Missing | Impact | Priority |
|---|---------|--------|----------|
| 1 | Trade-level returns for deployed strategy | Cannot compute real EV, WR, PF | CRITICAL |
| 2 | Measured slippage data | Cannot set slippage thresholds | HIGH |
| 3 | Measured latency data | Cannot set latency thresholds | HIGH |
| 4 | Live equity snapshots | Cannot track real DD | HIGH |
| 5 | Trade result feedback (C7) | Breakers cannot function | CRITICAL |
| 6 | Execution timing (I1) | No latency measurement | HIGH |
| 7 | Fill/exit records (I2) | Incomplete audit trail | MEDIUM |
| 8 | Position PnL (I3) | Cannot compute real returns | HIGH |
| 9 | Bridge /get_account (I4) | No live balance | MEDIUM |

---

## 10. METRICS RELIABILITY ASSESSMENT

### Statistically Reliable (from research data)

| Metric | Value | Source | Confidence |
|--------|-------|--------|------------|
| S6A WR | 35.7% | 15,321 trades | HIGH |
| S6A PF | 2.01 | 15,321 trades | HIGH |
| S6A max DD | 1,805 pips | 15,321 trades | HIGH |
| Monthly WR distribution | P50=35.5%, P95=44.5% | 127 months | HIGH |
| Monthly PF distribution | P50=1.97, P95=4.16 | 127 months | HIGH |
| Max consec losses | 17 trades | 15,321 trades | HIGH |
| Consec losses P95 | 16/month | 127 months | HIGH |
| Risk-scaled DD | 4.4%-17.6% | Monte Carlo | MEDIUM |
| MC DD percentiles | $119-$956 | 10k sims | LOW (normalization unclear) |

### Not Yet Reliable (no live data)

| Metric | Status | Minimum Data Needed |
|--------|--------|-------------------|
| Execution latency | ZERO measurements | ~500+ after instrumentation |
| Slippage distribution | ZERO measurements | ~200+ live trades |
| Spread distribution | ZERO measurements | ~200+ live observations |
| Live DD tracking | ZERO snapshots | Begin equity polling |
| Trading WR (live) | ZERO trades | Begin live trading |
| Trading PF (live) | ZERO trades | Begin live trading |

---

## 11. IMPLICATIONS FOR C7

### Before implementing C7, these issues must be resolved:

1. **Strategy baseline mismatch**: C7 will wire trade results to breakers. But if the breakers are calibrated against S0 (73% WR) instead of S6A (35.7% WR), they will malfunction.

2. **WinRateBreaker recalibration**: The 40% threshold over 20 trades triggers ~56% of the time on S6A data. Either:
   - Lower the threshold to match S6A distribution (e.g., 25%)
   - Increase the window size (e.g., 50 trades)
   - Accept that the strategy's WR is too low for this breaker design

3. **DD Pace recalibration**: The 9% hard DD threshold matches S6A's max DD (19.61R at 0.5% risk). Needs to be set above the observed max DD distribution.

4. **Slippage breaker**: Cannot be calibrated without empirical data. Should remain dormant until ~200 live trades provide slippage measurements.

5. **Data collection first**: Before C7, begin passive collection (spread, latency, health) to build baseline distributions.

### Recommended C7 implementation sequence:

1. Fix strategy baseline (use S6A, not S0)
2. Recalibrate WinRateBreaker for 35.7% WR baseline
3. Recalibrate DrawdownPaceBreaker for observed DD distribution
4. Wire C7 trade result feedback
5. Verify breakers receive and process trade results
6. Begin live monitoring with corrected thresholds

---

## 12. FILES CHANGED

| File | Change | Reason |
|------|--------|--------|
| S8_6_REVIEW_ADDENDUM.md | Created | This review document |

**No production code was modified during this review.**

---

## 13. TEST SUITE

**215/215 tests pass** (65 monitoring + 150 baseline).
No tests were modified or added during this review.
All pre-existing tests continue to pass.

---

## 14. CONCLUSIONS

### What S8.6 Got Right

1. **Percentile framework** is sound with proper MIN_SAMPLES enforcement
2. **EV stability implementation** is complete with all required metrics
3. **DD clustering implementation** is complete with random baseline comparison
4. **Collector infrastructure** is well-designed (thread-safe, JSONL output, dependency injection)
5. **Dashboard architecture** is clean (stdlib HTTP, provider pattern, auto-refresh)
6. **Research analysis** correctly extracts data from S0-S6 files

### What S8.6 Got Wrong

1. **Strategy identity**: Conflated S0 (filtered, 73% WR) with S6A (deployed config, 35.7% WR)
2. **CB calibration**: Tested wrong metric (monthly WR) against wrong threshold (trade-level 40%)
3. **CB conclusion**: "0 triggers = correctly calibrated" is wrong; would trigger ~56% of time
4. **DD clustering evidence**: Ran on synthetic random data, not actual equity
5. **EV stability population**: Analyzed filtered S0, not deployed S6A
6. **Dashboard status**: Classified as "Complete" when it's structural-only
7. **Monte Carlo values**: Reported without verifying normalization methodology

### Gate Decision (REVISED)

| Gate | Previous | Revised | Notes |
|------|----------|---------|-------|
| Percentile framework | ✅ PASS | ✅ PASS | No change |
| EV stability | ✅ PASS | ⚠️ IMPLEMENTATION ONLY | Implementation correct, but S8.6 analyzed wrong population |
| DD clustering | ✅ PASS | ⚠️ IMPLEMENTATION ONLY | Implementation correct, but S8.6 ran on synthetic data |
| CB calibration | ✅ PASS | ❌ FAIL | Tested wrong metric; WinRateBreaker would trigger ~56% of time |
| Dashboard | ✅ PASS | ⚠️ STRUCTURAL ONLY | Server exists but no data providers wired |
| Research analysis | ✅ PASS | ⚠️ PARTIAL | Data extraction correct, but report used wrong baseline |
| Overall | DRY-RUN READY | ⚠️ CONDITIONAL | Implementation sound, but report conclusions have critical errors |

### C7 Readiness

**C7 is NOT ready to implement** until:
1. WinRateBreaker is recalibrated for S6A baseline (35.7% WR)
2. DrawdownPaceBreaker is recalibrated for observed DD distribution
3. Strategy baseline discrepancy is resolved in documentation
4. The correct evidence population is identified for all monitoring thresholds
