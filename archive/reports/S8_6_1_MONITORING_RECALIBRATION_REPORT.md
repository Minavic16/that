# S8.6.1 — Monitoring Baseline Correction and Statistical Recalibration

**Date:** 2026-09-04
**Author:** Automated forensic analysis
**Status:** Complete — Gate Decision: YELLOW
**Predecessor:** S8.6 Review Addendum

---

## 1. Executive Summary

S8.6 monitoring conclusions were calibrated against the **wrong strategy population**. This report establishes the correct statistical baseline for the deployed strategy.

### Key Findings

1. **Three inconsistent configurations exist** in the codebase. The deployed code (`breakout.py`) does NOT implement breakeven or max_hold, but `ExperimentConfig` declares them. The `config/settings.py` has entirely different parameters.

2. **S6A is the correct baseline** (15,321 trades, WR=35.7%, PF=2.01). S0 (1,002 trades, WR=73.0%) includes breakeven/max_hold features that are NOT in the deployed code.

3. **WinRateBreaker at 40% triggers ~56% of the time** on S6A data. The 40% threshold is ABOVE the strategy's mean WR (36.1%). This is not a false positive — it means the threshold is calibrated for a different strategy.

4. **Monte Carlo DD values are invalid.** S6H shows P99 DD of 0.24R vs historical 19.61R — an 82x discrepancy. Do not use MC values for monitoring.

5. **No trade-level data exists** for the S6A population. All analysis uses monthly aggregates with simulation-based approximations.

6. **Six of seven circuit breakers cannot be calibrated** with available data.

### Gate Decision: YELLOW

Baseline partially established. S6A is identified as correct population. But critical data gaps remain:
- No trade-level S6A records
- No live slippage/latency/spread data
- WinRateBreaker thresholds are provably wrong
- Monte Carlo projections are unreliable

**Do not proceed to C7. Do not modify circuit breaker thresholds without review.**

---

## 2. Canonical Deployed Strategy Identity

### 2.1 What Actually Runs

| Component | Source | Value |
|-----------|--------|-------|
| Entry logic | `signals/breakout.py` | Break above swing high / below swing low |
| ATR period | `RESEARCH_DEFAULTS` | 14 |
| ATR SL multiplier | `RESEARCH_DEFAULTS` | 2.0 |
| Risk-reward ratio | `RESEARCH_DEFAULTS` | 3.5 |
| Lookback | `RESEARCH_DEFAULTS` | 5 |
| Breakeven logic | **NOT IMPLEMENTED** | — |
| Trailing stop | **NOT IMPLEMENTED** | — |
| Max hold period | **NOT IMPLEMENTED** | — |
| Session filter | **NOT IMPLEMENTED** | — |
| Macro filter | **NOT IMPLEMENTED** | — |

### 2.2 Three Inconsistent Configurations

| Parameter | `breakout.py` | `ExperimentConfig` | `config/settings.py` |
|-----------|--------------|-------------------|---------------------|
| ATR SL mult | 2.0 | 2.0 | **3.0** |
| RRR | 3.5 | 3.5 | **2.0** |
| Breakeven | None | 0.8 | **1.5** |
| Max hold | None | 7 days | None |
| Macro filter | None | None | **True** |
| Risk/trade | — | 0.15% | **3%** |
| Timeframe | — | 4h | **1h** |

**CRITICAL: `config/settings.py` contains a legacy configuration with different ATR, RRR, breakeven, and risk parameters. This must not be confused with the deployed strategy.**

### 2.3 Which Research Population Matches?

| Population | Trades | WR | PF | breakeven | max_hold | Matches Deployed? |
|-----------|--------|-----|-----|-----------|----------|-------------------|
| S0 | 1,002 | 73.0% | 5.32 | 0.8 | 7d | **NO** |
| S6A | 15,321 | 35.7% | 2.01 | None | None | **CLOSEST** |
| S5.5 | 15,321 | 35.9% (monthly) | 2.14 (monthly) | None | None | **YES** (same trades as S6A) |

**S6A/S5.5 is the correct baseline.** It shares the same breakout logic without breakeven/max_hold.

### 2.4 Remaining Mismatches

| Aspect | Deployed | S6A Baseline | Status |
|--------|----------|-------------|--------|
| Entry logic | Swing breakout | Swing breakout | ✅ Match |
| ATR SL mult | 2.0 | 2.0 | ✅ Match |
| RRR | 3.5 | 3.5 | ✅ Match |
| Lookback | 5 | 5 | ✅ Match |
| Breakeven | Not implemented | Not in S6A | ✅ Match |
| Max hold | Not implemented | Not in S6A | ✅ Match |
| Timeframe | Not specified in code | 4h (S0) or 1h (settings) | ⚠️ AMBIGUOUS |
| Instruments | 7 pairs (settings) | Not specified in S6A | ⚠️ UNKNOWN |
| Transaction costs | Not modeled | Not modeled in S6A | ✅ Match |
| Risk level | Not in signal code | 0.15% (ExperimentConfig) | ⚠️ Separate concern |

---

## 3. Configuration Mismatch Analysis

### 3.1 StrategyIdentity Includes Phantom Parameters

`StrategyIdentity` (in `config/experiment.py`) declares:
```python
parameters = {
    "lookback": 5,
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,
    "rrr": 3.5,
    "max_hold_days": 7,      # NOT in breakout.py
    "breakeven_ratio": 0.8,   # NOT in breakout.py
}
```

The `config_hash()` includes these phantom parameters. Two identical live runs would produce the same hash even if breakeven/max_hold logic were added or removed, because the hash comes from `StrategyIdentity`, not from the actual signal code.

### 3.2 Config Hash Is Not Sufficient

The config hash covers:
- ✅ Strategy name and version
- ✅ Strategy parameters (including phantom ones)
- ✅ Risk parameters
- ✅ Universe

The config hash does NOT cover:
- ❌ Actual signal implementation (breakeven/max_hold exist in hash but not in code)
- ❌ Data source
- ❌ Data timeframe (ambiguous between 1h and 4h)
- ❌ Session filters
- ❌ Execution assumptions

### 3.3 Recommended Canonical Identity Structure

```
strategy_id: "breakout-v1.0"
strategy_version: "1.0.0"
experiment_id: "S8-XXXXXXXXXXXX"
config_hash: <SHA256 of all below>
data_period: "2016-01-01 to 2025-12-31"
instrument_universe: ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "NZD/USD", "EUR/JPY", "GBP/JPY"]
timeframe: "4h"  # MUST be specified
signal_config:
  lookback: 5
  atr_period: 14
  atr_sl_multiplier: 2.0
  rrr: 3.5
  breakeven: false  # EXPLICITLY stated
  max_hold: false   # EXPLICITLY stated
risk_config:
  risk_per_trade_pct: 0.0015
  max_drawdown_pct: 0.08
execution_config:
  spread_model: "fixed"
  slippage_model: "none"
  commission: 0
```

---

## 4. Data Lineage and Integrity

### 4.1 Dataset Inventory

| Dataset | File | Experiment | Trades | Level | Sequential | Matches Deploy |
|---------|------|-----------|--------|-------|------------|----------------|
| S0 | `S0_breakout_results.json` | S0 | 1,002 | Aggregate | No | **NO** (has BE/MH) |
| S6A | `S6_adaptive_risk_challenge.json` | S6A | 15,321 | Aggregate | No | **YES** |
| S5.5 | `S5_5_failure_analysis.json` | S5.5 | 15,321 | Monthly | No | **YES** |
| S6H | `S6_adaptive_risk_challenge.json` | S6H | 10k sims | MC results | No | **NO** (invalid DD) |

### 4.2 Data Quality Issues

1. **No trade-level records exist** for any population. All analysis uses aggregates.
2. **S6A is aggregate-only**: `n=15321`, `win_rate=0.3567`, `avg_r=0.2591`, but no individual trade PnLs.
3. **S5.5 has monthly granularity**: 127 months with per-month WR, PnL, DD, avg_r.
4. **Sequential ordering is lost** in both S6A and S5.5. Cannot reconstruct exact trade sequence.
5. **S6H Monte Carlo values are invalid**: P99 DD = 0.24R vs historical 19.61R.

### 4.3 What Data Would Be Needed

To properly calibrate monitoring thresholds, we need:
- **Trade-level PnL sequence** for S6A (or equivalent live trades)
- **Trade timestamps** for session analysis
- **Entry/exit prices** for slippage measurement
- **Bid/ask at execution** for spread analysis

---

## 5. Win Rate Distribution Analysis

### 5.1 Method

Since trade-level S6A data does not exist, we simulate trade sequences from S5.5 monthly statistics:
- 127 months, each with `n_trades` and `win_rate`
- Generate random trade sequences per month
- Compute rolling WR windows across the concatenated sequence
- Single seed (reproducible, but within-month sequencing is randomized)

### 5.2 Results

| Window | Mean WR | Std | P5 | P10 | P25 | P50 | P75 | P90 | P95 | Below 40% |
|--------|---------|-----|-----|-----|-----|-----|-----|-----|-----|-----------|
| 10-trade | 36.1% | 16.1% | 10% | 20% | 20% | 40% | 50% | 60% | 60% | 48.9% |
| **20-trade** | **36.1%** | **12.0%** | **15%** | **20%** | **25%** | **35%** | **45%** | **50%** | **55%** | **56.1%** |
| 30-trade | 36.1% | 10.3% | 20% | 23% | 30% | 37% | 43% | 50% | 53% | 60.4% |
| 50-trade | 36.1% | 8.6% | 22% | 26% | 30% | 36% | 42% | 48% | 50% | 65.4% |

### 5.3 Current Breaker Assessment

**WinRateBreaker (20-trade, 40% threshold):**
- The 40% threshold is **above** the strategy mean WR (36.1%)
- 56.1% of 20-trade windows fall below 40%
- This means the breaker triggers MORE THAN HALF THE TIME during normal operation
- This is NOT a false positive — the threshold is simply set above the strategy's normal performance
- **VERDICT: Invalidly calibrated. Must be recalibrated.**

**WinRateBreaker (30-trade, 45% threshold):**
- 45% is even further above the mean
- 84.7% of 30-trade windows fall below 45%
- **VERDICT: Invalidly calibrated. Must be recalibrated.**

### 5.4 Candidate Thresholds (20-trade window)

| Level | Threshold | Est. Trigger Rate | Purpose |
|-------|-----------|-------------------|---------|
| Monitoring | 30% | ~25% | Track normal variance |
| Warning | 25% | ~10% | Early attention signal |
| Investigation | 20% | ~5% | Review strategy health |
| Trading halt | 15% | ~1% | Emergency stop entries |

**These are provisional estimates from simulated data.** Actual calibration requires trade-level records or live collection.

---

## 6. Expectancy Stability Analysis

### 6.1 Monthly Expectancy (from S5.5)

| Metric | Value |
|--------|-------|
| Mean monthly avg_r | 0.2642 |
| Std monthly avg_r | 0.1995 |
| Min monthly avg_r | -0.1437 |
| P5 monthly avg_r | 0.0045 |
| P50 monthly avg_r | 0.2271 |
| P95 monthly avg_r | 0.6843 |
| Negative months (avg_r) | 6/127 (4.7%) |
| Negative months (PnL) | 8/127 (6.3%) |

### 6.2 Key Observations

1. **Strategy has positive lifetime expectancy**: avg_r = 0.2591 across 15,321 trades.
2. **Monthly expectancy is mostly positive**: 95.3% of months have positive avg_r.
3. **But monthly variance is high**: std/mean (CV) = 0.76. This is moderate-to-high variability.
4. **Worst month**: avg_r = -0.1437 (mild negative), PnL = -1,194 pips.
5. **The edge is real but volatile**: A single month can be negative, but the strategy recovers.

### 6.3 Trade-Level Rolling EV (Simulated)

| Window | Mean EV | Std | % Windows with EV < 0 |
|--------|---------|-----|----------------------|
| 20-trade | -0.379 | 0.308 | 88.9% |
| 30-trade | -0.379 | 0.287 | 90.3% |
| 50-trade | -0.379 | 0.264 | 92.1% |
| 100-trade | -0.379 | 0.232 | 93.4% |

**NOTE: The simulated trade-level EV is negative because the simulation model is approximate. The actual S6A lifetime avg_r is +0.2591 (positive). The simulation loses within-month sequencing and R-multiple distribution. Do not use these simulated rolling EV values for monitoring thresholds.**

### 6.4 Stability Assessment

- **True edge exists**: Lifetime avg_r = +0.2591, PF = 2.01
- **Monthly consistency**: 94% of months are profitable
- **Rolling window behavior**: Cannot be precisely determined without trade-level data
- **Recommendation**: Begin collecting trade-level returns live to enable proper rolling EV analysis

---

## 7. Drawdown Distribution

### 7.1 From Monthly PnL (Reconstructed Equity Curve)

| Metric | Value |
|--------|-------|
| Max DD (monthly) | 1,194 pips |
| Mean DD (when in DD) | 541 pips |
| DD Episodes | 7 |
| Avg episode depth | 524 pips |
| Avg episode duration | 1.3 months |
| Max episode depth | 1,194 pips |
| Max episode duration | 3 months |

### 7.2 From S6A Lifetime

| Metric | Value |
|--------|-------|
| Max DD (pips) | 1,805 |
| Max DD (R) | 19.61 |
| Max DD Duration | 205 bars |
| Max Loss Streak | 17 trades |

### 7.3 Within-Month DD

| Metric | Value |
|--------|-------|
| Mean monthly max DD | 469 pips |
| Std monthly max DD | 279 pips |
| P50 monthly max DD | 418 pips |
| P95 monthly max DD | 164 pips |

### 7.4 Loss Streak Distribution (from S5.5)

| Metric | Value |
|--------|-------|
| Total streaks | 3,227 |
| Max length | 27 |
| Mean length | 3.1 |
| Median length | 2.0 |
| Streaks ≥ 3 | 1,383 |
| Streaks ≥ 5 | 660 |
| Streaks ≥ 10 | 115 |

---

## 8. Drawdown Clustering Analysis

### 8.1 Monthly Return Autocorrelation

| Lag | Autocorrelation | Interpretation |
|-----|----------------|----------------|
| 1 | 0.118 | Weak positive |
| 2 | 0.036 | Negligible |
| 3 | -0.0003 | None |

**Lag-1 autocorrelation of 0.118 suggests weak momentum in monthly returns.** This is not strong enough to indicate regime clustering, but it is nonzero.

### 8.2 Runs Test

| Metric | Value |
|--------|-------|
| Positive months | 119 |
| Negative months | 8 |
| Observed runs | 17 |
| Expected runs | 16.0 |
| Z-score | 0.78 |
| Interpretation | **Random** (p > 0.05) |

**The sequence of positive/negative months is consistent with random variation.** No evidence of clustering at the monthly level.

### 8.3 Conditional Loss Probability

After 1 consecutive loss: 0% chance of another (only 8 negative months total — too few for meaningful conditional analysis).

### 8.4 DD Episode Inter-Arrival

| Metric | Value |
|--------|-------|
| Mean inter-arrival | 17.2 months |
| Std inter-arrival | 12.5 months |
| Min | 4 months |
| Max | 41 months |
| Median | 16 months |

**DD episodes are spaced approximately 1-2 years apart on average.**

### 8.5 Clustering Assessment

- **Monthly level**: No significant clustering (runs test p > 0.05)
- **Weak lag-1 autocorrelation**: 0.118 (not significant at 95% CI for n=127)
- **DD episodes are infrequent**: ~7 episodes over 127 months
- **Conclusion**: Evidence does NOT support strong clustering. Monthly returns appear approximately IID for practical monitoring purposes.

---

## 9. Risk-Scaled Drawdown Analysis

### 9.1 Historical Observed (Category A)

| Metric | Value |
|--------|-------|
| Max DD | 1,805 pips = 19.61R |
| Max DD Duration | 205 bars |
| Max Loss Streak | 17 trades |

### 9.2 Monte Carlo Projected (Category B) — UNRELIABLE

| Risk | Median DD | P99 DD | DD as % of $200K |
|------|-----------|--------|-------------------|
| 0.25% | $119 (0.24R) | $239 (0.48R) | 0.12% |
| 0.50% | $239 (0.24R) | $478 (0.48R) | 0.24% |
| 1.00% | $478 (0.24R) | $956 (0.48R) | 0.48% |

**CRITICAL: MC P99 DD is 0.48R vs historical 19.61R. The MC simulation produces DD values 40x smaller than observed. These values MUST NOT be used for monitoring thresholds.**

### 9.3 Prop-Firm Hard Limits (Category C)

| Limit | Value | $200K Equivalent |
|-------|-------|-----------------|
| Max DD | 10% | $20,000 |
| Daily loss | 5% | $10,000 |

### 9.4 Current Settings (Category D)

| Source | Max DD | Risk/Trade |
|--------|--------|-----------|
| `config/settings.py` | 55% | 3% |
| `ExperimentConfig` | 8% | 0.15% |
| Prop firm typical | 10% | — |

**The legacy `settings.py` max_dd_pct=55% is dangerously high and should not be used.**

### 9.5 Risk-Level Alignment

At 0.15% risk (ExperimentConfig):
- 1R = $300
- Historical max DD = 19.61R = $5,883 = 2.94% of account
- This is within the 8% `ExperimentConfig` limit

At 0.50% risk:
- 1R = $1,000
- Historical max DD = 19.61R = $19,610 = 9.8% of account
- This VIOLATES the 8% limit

**The risk level MUST be set conservatively until live DD data validates the MC projections.**

---

## 10. Circuit Breaker Forensic Calibration

### 10.1 Summary Table

| Breaker | Status | Calibratable | Key Issue |
|---------|--------|-------------|-----------|
| WinRateBreaker (20t) | **RED** | YES | Threshold 40% triggers 56% of time |
| WinRateBreaker (30t) | **RED** | YES | Threshold 45% triggers 85% of time |
| DrawdownPaceBreaker | **YELLOW** | YES | Scale-dependent on risk level |
| SlippageBreaker | **RED** | NO | Zero empirical data |
| ProfitFactorBreaker | **GREEN** | YES | PF<1.0 is reasonable threshold |
| CorrelationBreaker | **YELLOW** | NO | No empirical correlation data |
| DrawdownDriftBreaker | **YELLOW** | YES | Currently disabled |

### 10.2 WinRateBreaker Detailed Calibration

**Current**: `window_20=0.40, window_30=0.45`

**Problem**: Both thresholds are above the strategy mean WR (36.1%). The breaker triggers during NORMAL operation.

**Candidate thresholds** (20-trade window, provisional):

| Level | Threshold | Est. Trigger Rate | Purpose |
|-------|-----------|-------------------|---------|
| Monitoring | 30% | ~25% | Track normal variance |
| Warning | 25% | ~10% | Early attention signal |
| Investigation | 20% | ~5% | Review strategy health |
| Trading halt | 15% | ~1% | Emergency stop entries |

### 10.3 DrawdownPaceBreaker

**Current**: `soft_dd=6%, soft_trades=15, hard_dd=9%, hard_trades=25`

**Problem**: Thresholds are in account %, which scales with risk level.
- At 0.15% risk: 6% DD = 40R (unlikely to hit in 15 trades)
- At 0.50% risk: 6% DD = 12R (possible in 15 trades)
- At 1.00% risk: 6% DD = 6R (likely in 15 trades)

**Recommendation**: Make thresholds configurable per risk level, or express in R-units.

### 10.4 ProfitFactorBreaker

**Current**: `threshold=1.0, window=20`

**Assessment**: Reasonable. PF < 1.0 over 20 trades means the strategy is losing money in that window. With S6A lifetime PF = 2.01, this should rarely trigger during normal operation. **GREEN.**

---

## 11. Live Data Gaps

| Metric | Available | Min Sample | Passive? | Method |
|--------|-----------|-----------|----------|--------|
| Slippage | NO | 200 | NO | Live execution |
| Latency | NO | 500 | YES | Bridge HTTP probe |
| Spread | NO | 200 | YES | Bridge tick data |
| Execution failures | NO | 100 | NO | Trade logs |
| Trade-level returns | NO | 200 | NO | PnL logging |
| Equity snapshots | NO | 1 | YES | Account polling |

**Passive collection (latency, spread, equity) can begin immediately without trading.**
**Active collection (slippage, returns, failures) requires live trade execution.**

---

## 12. What Can Be Calibrated Now

| Threshold | Source | Confidence | Notes |
|-----------|--------|------------|-------|
| WinRateBreaker → 30% (monitoring) | S5.5 simulation | LOW | Simulated, not trade-level |
| WinRateBreaker → 25% (warning) | S5.5 simulation | LOW | Provisional |
| WinRateBreaker → 20% (investigation) | S5.5 simulation | LOW | Provisional |
| WinRateBreaker → 15% (halt) | S5.5 simulation | LOW | Provisional |
| ProfitFactorBreaker → 1.0 | S6A lifetime PF=2.01 | MEDIUM | Reasonable threshold |
| DrawdownPaceBreaker → R-based | S6A max DD=19.61R | MEDIUM | Convert to R-units |

---

## 13. What Cannot Be Calibrated Yet

| Threshold | Reason | Required Data |
|-----------|--------|---------------|
| SlippageBreaker | Zero empirical data | 200+ live trades |
| CorrelationBreaker | No live correlation matrix | Live multi-pair data |
| WinRateBreaker (precise) | Simulated only | Trade-level S6A records or 200+ live trades |
| DrawdownPaceBreaker (precise) | Risk-level dependent | Live DD history at target risk level |
| Latency thresholds | Zero measurements | 500+ HTTP probes |
| Spread thresholds | Zero measurements | 200+ tick observations |

---

## 14. Recommended Next Steps

### Immediate (Before C7)

1. **Resolve strategy identity**: Decide whether breakeven/max_hold will be implemented. If not, remove them from `StrategyIdentity` parameters.
2. **Fix config/settings.py divergence**: The legacy config has different ATR/RRR/breakeven values. Document or remove.
3. **Begin passive data collection**: Wire spread, latency, and equity collection to the bridge.
4. **Re-run S6A with trade-level logging**: If possible, recover individual trade PnLs from the backtest engine.

### Before Live Trading

5. **Recalibrate WinRateBreaker**: Use live trade data once 200+ trades are collected.
6. **Calibrate DrawdownPaceBreaker in R-units**: Express thresholds relative to risk level.
7. **Validate Monte Carlo methodology**: Investigate why S6H DD values are 40x too small.
8. **Wire C7 trade feedback**: Only after breaker thresholds are recalibrated.

### Ongoing

9. **Collect live trade-level returns** for rolling EV analysis.
10. **Monitor breaker trigger rates**: If any breaker triggers >10% of time, it is miscalibrated.
11. **Quarterly recalibration**: Update thresholds as live data accumulates.

---

## 15. Gate Decision

### S8.6.1 BASELINE CALIBRATION: **YELLOW**

**YELLOW** — baseline partially established but critical data gaps remain.

**Rationale:**
- ✅ S6A identified as correct baseline population
- ✅ Win rate distribution characterized (via simulation)
- ✅ Drawdown distribution characterized
- ✅ Clustering analysis complete (no significant clustering)
- ✅ Circuit breaker forensic audit complete
- ⚠️ No trade-level S6A records exist
- ⚠️ WinRateBreaker thresholds provably wrong
- ⚠️ Monte Carlo projections unreliable
- ⚠️ No live slippage/latency/spread data
- ❌ Six of seven breakers cannot be precisely calibrated

**Do not proceed to C7 until:**
1. WinRateBreaker thresholds are recalibrated (at minimum, to provisional values)
2. Strategy identity discrepancy is resolved
3. Passive data collection is wired

---

## 16. Appendix: Raw Data References

| Analysis | Source File | Method |
|----------|-----------|--------|
| WR distribution | `S5_5_failure_analysis.json` → monthly_stats | Simulated trade sequences |
| Monthly expectancy | `S5_5_failure_analysis.json` → monthly_stats | Direct monthly avg_r |
| Drawdown distribution | `S5_5_failure_analysis.json` → monthly_stats | Reconstructed equity curve |
| DD clustering | `S5_5_failure_analysis.json` → monthly_stats | Autocorrelation, runs test |
| Risk scaling | `S6_adaptive_risk_challenge.json` → S6H | Monte Carlo (UNRELIABLE) |
| S6A lifetime | `S6_adaptive_risk_challenge.json` → S6A | Aggregate stats |
| S0 comparison | `S0_breakout_results.json` | Aggregate stats |
| Breaker config | `risk/circuit_breakers.py` | Code inspection |
| Strategy config | `signals/breakout.py`, `config/experiment.py`, `config/settings.py` | Code inspection |

---

*End of S8.6.1 Monitoring Recalibration Report*
