# MONITORING_DATA_INVENTORY — NestQuant S8 Evidence Assessment

**Date:** 2026-09-04
**Purpose:** Determine how much evidence exists to set statistically defensible monitoring thresholds

---

## 1. EXECUTIVE SUMMARY

**We have almost no measured data.** Every monitoring threshold in the current system is arbitrary. The backtest research provides strong statistical evidence for the strategy's edge (PF=5.25, WR=72.7%, 1002 trades, p=0.0), but the trade-level data for the exact deployed strategy (breakout H4, ATR=2.0, RRR=3.5) is **aggregated only** — no individual trade records exist with entry/exit prices and P&L.

The good news: the bridge exposes live bid/ask, spread, positions, and deal history endpoints. A passive monitoring collector can begin collecting real spread, latency, and slippage data immediately.

**Key finding:** The WinRateBreaker is calibrated to trigger at 40% WR over 20 trades, but the strategy's baseline win rate is 36%. This breaker would trigger during **normal operation**.

| Domain | Evidence Available | Can Calculate Thresholds Now? | Missing Data | Next Action |
|--------|-------------------|-------------------------------|-------------|-------------|
| Drawdown | STRONG (backtest) | YES — from S0/S5/S6 | Intraday DD not captured | Use backtest percentiles as starting point |
| Consecutive Losses | STRONG (backtest) | YES — from S5_5 monthly data | Trade-level streaks (not monthly) | Use monthly max_consec_losses |
| Slippage | NONE | NO | Zero measured data | Begin live collection immediately |
| Latency | NONE | NO | Zero instrumentation | Add timing to mt5_client.py + bridge |
| Spread | ASSUMED ONLY | PARTIALLY — can collect live | No historical tick data | Begin live sampling; 200+ obs needed |
| Execution Failures | NONE | NO | No live trade logs | Begin logging after first live trade |

---

## 2. DRAWDOWN EVIDENCE

### Source 1: S0 Breakout Results

File: `research_data/simple_strategies/S0_breakout_results.json`
Strategy: Swing breakout, H4, ATR_SL_MULT=2.0, RRR=3.5, lookback=5, breakeven=0.8, max_hold=7d

| Metric | Value |
|--------|-------|
| Total trades | 1,002 (2016-2026, 20 pairs) |
| Max drawdown (pips) | 522.47 (with costs) |
| Max DD range (9 param variants) | 295 - 522 pips |
| Permutation p-value | 0.0 |

Year-by-year max DD (pips): 2016=443, 2017=326, 2018=116, 2019=150, 2020=143, 2021=85, 2022=350, 2023=362, 2024=136, 2025=263, 2026=191(YTD)

### Source 2: S5_5 Monthly Statistics (127 months, 15,321 trades)

| Metric | Value |
|--------|-------|
| Monthly max DD median | -417.8 pips |
| Monthly max DD worst 5% | -995.8 to -2086.3 pips |
| Monthly max DD best 5% | -135.4 to -149.1 pips |
| Losing months | 8 out of 127 (6.3%) |
| Worst monthly PnL | -$1,193.87 |
| Consecutive losing months | 1 (never 2 in a row) |
| Max consecutive losses per month | min=5, median=8, P90=14, P95=16, P99=19, max=21 |

### Source 3: S6 Risk-Scaled Drawdown

| Risk/trade | Max DD% | Prob>5%DD | Prob>8%DD | Prob>10%DD |
|-----------|---------|-----------|-----------|------------|
| 0.25% | 4.39% | 20.1% | 6.9% | 0.5% |
| 0.50% | 8.78% | 98.5% | 95.5% | 21.0% |
| 0.75% | 13.17% | — | — | — |
| 1.00% | 17.56% | 99.8% | 98.3% | 98.3% |

### Source 4: S6 Monte Carlo (10,000 sims)

| Risk | Median Max DD | P95 Max DD | P99 Max DD |
|------|--------------|-----------|-----------|
| 0.25% | $119.44 | $219.21 | $238.88 |
| 0.50% | $238.88 | $440.51 | $477.77 |
| 1.00% | $477.77 | $881.02 | $955.54 |

### Source 5: S6 Consecutive Loss Streaks

| Metric | Value |
|--------|-------|
| Max loss streak (baseline) | 17 trades |
| Max loss streak (all variants) | 16-26 trades |
| Max DD R-value (baseline) | 19.61R |
| Max DD duration (baseline) | 205 bars |
| Max DD duration (with circuit breakers) | 619 bars (WORSE — CBs increase DD) |

---

## 3. SLIPPAGE EVIDENCE

**FACT: Zero empirical slippage data exists anywhere.**

Every slippage number is an assumption:

| Source | Value | Status |
|--------|-------|--------|
| config.py | 0.1 pips | Assumed |
| config/settings.py | 0.1 pips | Assumed |
| S0-S6 scripts | 0.1 pips | Assumed |
| Z-Score scripts | 0.3 pips | Assumed |
| Forensic analysis (realistic) | 0.3 pips | Assumed |
| Forensic analysis (stressed) | 1.0 pips | Assumed |
| MR forensic report | "P95/P99 CANNOT BE EMPIRICALLY ESTIMATED" | Acknowledged |

Code CAN measure but DOES NOT:
- `mt5_adapter.py:246-257` calculates `slippage_pips = abs(fill_price - request.entry_price) / pip`
- `s7_engine.py:304` hardcodes `spread_at_submission=0.0`
- `s7_engine.py:305` hardcodes `execution_latency_ms=0.0`
- No trade log files exist with populated slippage data

Circuit breaker slippage thresholds (ARBITRARY):
- Consecutive slippage: 4.8 pips after 3 trades
- 10-trade average: 6.0 pips

---

## 4. LATENCY EVIDENCE

**FACT: Zero timing instrumentation exists.**

| Component | Status |
|-----------|--------|
| mt5_client.py (HTTP transport) | Zero timing calls |
| mt5_bridge-local (Flask) | Zero request timing |
| s7_engine.py | Hardcodes latency=0.0 |
| s8_runtime.py | Only metrics logging interval |
| orchestration.py | No stage timing |
| data_feed.py | No fetch timing |
| health_monitor.py | No health check timing |

Timestamps that DO exist (local clock only):
- Signal generation: `datetime.now(UTC)` in trade_logger.py
- Order submission: `datetime.now(UTC)` in trade_logger.py
- Fill recording: `datetime.now(UTC)` in trade_logger.py
- Exit recording: `datetime.now(UTC)` in trade_logger.py

Missing: HTTP round-trip, MT5 execution time, signal-to-fill delay, pipeline stage breakdown, bridge processing time

---

## 5. SPREAD EVIDENCE

**FACT: All spread numbers are assumed. No historical tick data exists.**

Three inconsistent spread tables:

| Source | EUR/USD | GBP/USD | Status |
|--------|---------|---------|--------|
| S0-S6 (ECN) | 0.2 pips | 0.3 pips | Used in validated research |
| config/settings.py (Exness) | 0.8 pips | 1.0 pips | "Standard account" |
| costs/model.py (retail) | 1.0 pips | 1.6 pips | Cost model |

Bridge CAN provide:
- `/symbol_info_tick/<sym>` → bid, ask (live spread)
- `/symbol_info/<sym>` → spread (MT5 integer spread)
- `/fetch_data_pos` → OHLCV + spread field

Does NOT exist: spread time series, percentile distributions, spread-by-session analysis

---

## 6. CIRCUIT BREAKER EVIDENCE

**FACT: Every threshold is arbitrary. None backtest-validated.**

| Breaker | Threshold | Problem |
|---------|-----------|---------|
| WinRateBreaker (20-trade) | 40% WR | **Baseline WR=36% — triggers on NORMAL behavior** |
| WinRateBreaker (30-trade) | 45% WR | Same |
| SlippageBreaker (consecutive) | 4.8 pips | No measured data |
| SlippageBreaker (10-trade avg) | 6.0 pips | No measured data |
| DrawdownPaceBreaker (soft) | 6.0% | S6 shows 4-18% DD normal at 0.5-1% risk |
| DrawdownPaceBreaker (hard) | 9.0% | Would trigger at 0.5% risk (8.78% observed) |
| ProfitFactorBreaker | PF<1.0 | Reasonable but unvalidated |
| CorrelationBreaker | >0.80 | Cross-pair avg corr=0.14 (S6I) |

Conflicts:
- `config/settings.py` CircuitBreakerConfig has DIFFERENT values than circuit_breakers.py defaults
- `dd_pace_soft_trades`: settings=5, breaker=15
- `dd_pace_hard_dd`: settings=8.5%, breaker=9.0%

Dead code (defined but never enforced):
- `max_single_trade_loss_pct = 0.30%`
- `max_daily_profit_pct_of_total = 50%`
- `floating_loss_kill_threshold = -$15.0`
- `warning_threshold_seconds = 300.0`
- `enable_hard_stops = False`

---

## 7. HISTORICAL DATASETS

| Dataset | Records | Strategy | Trade-Level? |
|---------|---------|----------|-------------|
| **S0 Breakout** | 1,002 (aggregated) | **DEPLOYED** | **NO** |
| S1-S6 Validation | 15,321 (aggregated) | Same | NO |
| S5_5 Monthly | 127 months | Same | Monthly only |
| S6 Monte Carlo | 10,000 sims | Same | Sim-level only |
| Phase 4 Z-Score | 74,755 | Z-Score MR (DIFFERENT) | YES but wrong strategy |
| Phase 11 | 114,330 | Prob-gated MR | Partial |

**Critical: The deployed strategy has NO individual trade records.**

---

## 8. LIVE MT5 MEASUREMENT CAPABILITY

### Infrastructure Matrix

| Metric | Measured? | Data Source | Code Change |
|--------|----------|-------------|-------------|
| Requested order price | YES | ExecutionResult | No |
| Actual fill price | YES | ExecutionResult | No |
| Entry slippage | CALCULATED | mt5_adapter.py | **Log it** |
| Exit slippage | NO | — | Add to exit path |
| HTTP latency | NO | — | **mt5_client.py** |
| End-to-end latency | NO | — | **s7_engine.py** |
| Bid | NO (during execution) | Bridge has endpoint | Fetch before order |
| Ask | NO (during execution) | Bridge has endpoint | Fetch before order |
| Spread | NO | Bridge has endpoint | Fetch before order |
| Spread percentile | NO | — | Build from live data |
| Account equity | NO | **/get_account MISSING** | Add bridge endpoint |
| Realized PnL | NO | /get_deal_from_ticket exists | Wire to close |
| Unrealized PnL | YES | /get_positions | No |
| Daily drawdown | NO | — | Need equity snapshots |
| Peak-to-trough DD | NO | — | Need equity snapshots |
| Consecutive losses | NO | — | Wire record_trade_result() |
| Execution failure rate | NO | — | Begin logging |
| Bridge health failures | YES | HealthMonitor | No |
| MT5 connection failures | YES | HealthMonitor | No |

### Bridge Endpoints for Passive Monitoring

| Endpoint | Data | Use |
|----------|------|-----|
| `/health` | status, mt5_connected | Liveness |
| `/last_error` | error_code, error_message | Error detection |
| `/symbol_info_tick/<sym>` | bid, ask, volume, time | Spread, tick sampling |
| `/symbol_info/<sym>` | spread, point, digits | Symbol config |
| `/get_positions` | profit, swap, price_current | Position monitoring |
| `/positions_total` | count | Position count |
| `/fetch_data_pos` | OHLCV + spread | Historical spread |
| `/get_deal_from_ticket` | profit, commission | Trade PnL |
| `/history_deals_get` | All deals by date | Bulk history |

**CRITICAL GAP:** `/get_account` returns 404. No live balance/equity.

---

## 9. MISSING DATA

| # | Missing | Impact | How to Obtain |
|---|---------|--------|--------------|
| 1 | Trade-level records (breakout) | No return distribution | Re-run S0 with logging or begin live |
| 2 | Measured slippage distribution | No slippage thresholds | Live collection: ~200+ trades |
| 3 | Measured latency distribution | No latency alerts | Add timing, ~500+ observations |
| 4 | Live spread distribution | No spread alerts | Poll tick endpoint ~1 week |
| 5 | Intraday equity snapshots | No intraday DD | Poll positions periodically |
| 6 | Account equity endpoint | No daily P&L tracking | Add /get_account to bridge |
| 7 | Live trade log output | No execution quality | Enable trade_logger |
| 8 | Clock synchronization | Timestamp accuracy | NTP check on VPS |

---

## 10. STATISTICAL READINESS

| Domain | Evidence | Ready? | Minimum Data Needed |
|--------|----------|--------|-------------------|
| Drawdown (trade-close) | STRONG | YES | Have: S0, S5_5, S6 Monte Carlo |
| Drawdown (intraday) | NONE | NO | Equity snapshots every N min |
| Consecutive losses (monthly) | STRONG | YES | Have: S5_5 (127 months) |
| Consecutive losses (trade-level) | NONE | NO | Trade records for breakout |
| Slippage | ZERO | NO | ~200+ live trades |
| Latency | ZERO | NO | ~500+ measurements after instrumentation |
| Spread | ASSUMED | PARTIAL | Can collect live; ~200+ observations |
| Execution failures | NONE | NO | Live trade logs |

---

## 11. PROPOSED DATA COLLECTION PLAN

### Phase 1: Passive Collection (no trading required)

| Collector | Endpoint | Interval | Storage |
|-----------|----------|----------|---------|
| Spread sampler | `/symbol_info_tick/EURUSD` | Every 30s | JSONL time series |
| Bridge health | `/health` | Every 30s | JSONL time series |
| Position snapshot | `/get_positions` | Every 60s | JSONL time series |
| Latency probe | `/symbol_info_tick/EURUSD` | Every 30s | Round-trip time |

### Phase 2: Execution-Time Collection (requires trades)

| Collector | Where | Data |
|-----------|-------|------|
| Slippage logger | s7_engine.py after fill | fill_price - requested_price |
| Latency timer | mt5_client.py around urlopen | time.monotonic delta |
| Spread snapshot | s7_engine.py before order | bid/ask at submission |
| Deal history | Bridge /get_deal_from_ticket | Realized PnL per trade |

### Phase 3: Equity Tracking

| Collector | Source | Data |
|-----------|--------|------|
| Equity snapshot | /get_positions + balance | Total equity every N minutes |
| Daily DD calculator | Equity series | Peak-to-trough intraday |

---

## 12. PERCENTILE FRAMEWORK (NOT THRESHOLDS)

Possible monitoring tiers based on available data:

### Drawdown Velocity (from S5_5 monthly data)

| Tier | Condition | Basis |
|------|-----------|-------|
| NORMAL | Monthly DD < 500 pips | Below median |
| WARNING | Monthly DD 500-1000 pips | Median to P90 |
| ABNORMAL | Monthly DD 1000-2000 pips | P90 to P99 |
| CIRCUIT BREAKER | Monthly DD > 2000 pips | Above P99 |

### Consecutive Losses (from S5_5 monthly data)

| Tier | Condition | Basis |
|------|-----------|-------|
| NORMAL | Max streak < 10 | Below P75 |
| WARNING | Max streak 10-14 | P75 to P90 |
| ABNORMAL | Max streak 15-19 | P90 to P99 |
| CIRCUIT BREAKER | Max streak >= 20 | Above P99 |

### Spread (framework only — needs live data)

| Tier | Condition | Basis |
|------|-----------|-------|
| NORMAL | Below historical P75 | To be determined |
| WARNING | P75-P95 | To be determined |
| ABNORMAL | P95-P99 | To be determined |
| CIRCUIT BREAKER | Above P99 | To be determined |

### Slippage (framework only — needs live data)

| Tier | Condition | Basis |
|------|-----------|-------|
| NORMAL | Below historical P75 | To be determined |
| WARNING | P75-P95 | To be determined |
| ABNORMAL | P95-P99 | To be determined |
| CIRCUIT BREAKER | Above P99 | To be determined |

### Latency (framework only — needs instrumentation)

| Tier | Condition | Basis |
|------|-----------|-------|
| NORMAL | Below P75 | To be determined |
| WARNING | P75-P95 | To be determined |
| ABNORMAL | P95-P99 | To be determined |
| CIRCUIT BREAKER | Above P99 or timeout | To be determined |

---

## 13. CRITICAL CALIBRATION ISSUES

### WinRateBreaker Will Trigger on Normal Behavior

The strategy's baseline win rate is 36% (S6A). The WinRateBreaker pauses at 40% WR over 20 trades. With WR=36%, expect approximately 7-8 wins in 20 trades (35-40% WR) during NORMAL operation. The breaker would trigger frequently, causing unnecessary pauses.

**Recommendation:** Recalibrate based on observed monthly win rate distribution (P5=18.8%, median=36%).

### DrawdownPaceBreaker Conflict with Risk Level

At 0.5% risk per trade, S6 shows max DD=8.78%. The hard DD breaker is set at 9.0%. This means the breaker would trigger at the risk level the strategy is designed to operate at.

**Recommendation:** Set hard DD breaker above P99 of risk-scaled DD distribution.

### Circuit Breakers INCREASE Drawdown in Backtests

S6E results show that circuit breakers (cb1, cb2, cb3) INCREASED max DD from 1804 pips to 2121-2137 pips (+17-19%). They also increased max DD duration from 205 to 619 bars. The breakers are counterproductive.

---

## 14. SUMMARY

### What We HAVE

- Strong backtest evidence for strategy edge (PF=5.25, 1002 trades, p=0.0)
- Monthly PnL distribution (127 months)
- Monthly drawdown distribution (127 months)
- Consecutive loss distribution (monthly level)
- Risk-scaled DD percentiles (Monte Carlo)
- Bridge endpoints for live data collection
- Strategy specification validated S0-S6

### What We LACK

- Trade-level records for the deployed strategy
- ANY measured slippage data
- ANY timing/latency instrumentation
- ANY historical spread distribution
- Live equity/balance endpoint (/get_account missing)
- Live trade log output
- Clock synchronization

### What We Must Do Before Setting Thresholds

1. Begin passive spread collection (immediate, no trading needed)
2. Add timing instrumentation to mt5_client.py and bridge
3. Wire trade result feedback to PropFirmGuard
4. Fix WinRateBreaker calibration
5. Fix DrawdownPaceBreaker to match risk level
6. Collect ~200-500 live observations before finalizing spread/slippage thresholds
7. Add /get_account endpoint to bridge

---

*This report is an investigation, not a recommendation. No thresholds are recommended. Only evidence is presented.*
