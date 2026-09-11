# S8.5 PREFLIGHT REPORT — NestQuant Controlled Activation Audit

---

## 1. STRATEGY FIDELITY

### Research Configuration (S0-S6 backtests)

| Parameter | Research Value | Source |
|-----------|---------------|--------|
| ATR_SL_MULT | **2.0** | `config.py:42`, all `phase_s*_*.py` |
| RRR (TP) | **3.5** | `config.py:44`, all `phase_s*_*.py` |
| Lookback | 5 | Hardcoded in all scripts |
| ATR period | 14 | Hardcoded |
| Breakeven ratio | 0.8 | `config.py:46` |
| Max hold days | 7 | Research scripts |
| Timeframe | **4h** | Research scripts |
| Pair | EUR/USD | Primary |
| Entry | Swing break confirmed at bar close | Strategy logic |
| SL | entry ± ATR_SL_MULT × ATR | Strategy logic |
| TP | entry ± SL_distance × RRR | Strategy logic |
| Trailing stop | Swing-based (from research) | backtest_portfolio.py |
| Session filter | 07:00-21:00 UTC | config/settings.py |

### Current Live/BreakoutSignal Configuration

| Parameter | Live Value | Source |
|-----------|-----------|--------|
| ATR_SL_MULT | **3.0** | `config/settings.py:321` (imported by `signals/breakout.py:9`) |
| RRR (TP) | **2.0** (hardcoded `* 2.0`) | `signals/breakout.py:72,78` |
| Lookback | 5 | Hardcoded |
| ATR period | 14 | Hardcoded |
| Breakeven ratio | N/A | **Not implemented** in BreakoutSignal |
| Max hold days | N/A | **Not implemented** in BreakoutSignal |
| Timeframe | H4 (default in S8Runtime) | `execution/s8_runtime.py` |
| Entry | Swing break confirmed at bar close | Same |
| SL | entry ± ATR_SL_MULT × ATR | Same formula, different multiplier |
| TP | entry ± SL_distance × 2.0 | **Hardcoded 2.0**, not configurable |
| Trailing stop | N/A | **Not implemented** |
| Session filter | N/A | **Not implemented** |

### Experiment Identity (config/experiment.py)

| Parameter | Experiment Value | Status |
|-----------|-----------------|--------|
| atr_sl_multiplier | 2.0 | **Correct** (matches research) |
| rrr | 3.5 | **Correct** (matches research) |
| breakeven_ratio | 0.8 | **Correct** (matches research) |
| timeframe | "4h" | **Correct** |

### Matches / Mismatches

| Parameter | Status | Severity |
|-----------|--------|----------|
| ATR_SL_MULT: research=2.0, live=3.0 | **MISMATCH** | **CRITICAL** |
| RRR: research=3.5, live=2.0 | **MISMATCH** | **CRITICAL** |
| TP hardcoded `* 2.0` vs configurable RRR | **MISMATCH** | **CRITICAL** |
| Breakeven: research=0.8, live=not implemented | **MISSING** | HIGH |
| Max hold: research=7d, live=not implemented | **MISSING** | HIGH |
| Trailing stop: research=swing-based, live=none | **MISSING** | HIGH |
| Session filter: research=07-21 UTC, live=none | **MISSING** | MEDIUM |
| Macro EMA filter: research=configurable, live=none | **MISSING** | LOW |

**The live system would trade with parameters that have never been validated by research.**

---

## 2. DATA FIDELITY

### Status: MOSTLY OK, WITH ISSUES

**What works:**
- Pair mapping: `EUR/USD` -> `EURUSD` via `pair.replace("/", "")` ✅
- Timeframe mapping: Bridge `get_timeframe()` handles `"H4"` -> `mt5.TIMEFRAME_H4` ✅
- Timestamp handling: Bridge converts epoch->ISO, client parses both ISO and epoch ✅
- OHLCV validation: OHLCV.validate() checks H≥L, H≥O, H≥C, L≤O, L≤C, positive prices ✅
- Timezone: Timestamps are timezone-aware (UTC) after parsing ✅
- Candle caching: Deduplication by timestamp, max_cache_size trim ✅

**Issues:**

| Issue | Detail | Severity |
|-------|--------|----------|
| **ATR calculation mismatch** | LiveDataFeed.get_atr() uses **SMA** (sum/N). BreakoutSignal uses **Wilder's EMA** (alpha=1/N). Results diverge. | **HIGH** |
| **No missing-bar handling** | If MT5 has a gap (e.g., holiday), LiveDataFeed returns whatever MT5 gives. No gap detection or warning. | MEDIUM |
| **Spread data ignored** | OHLCV.spread is captured but not used for slippage estimation or signal filtering. | LOW |
| **No duplicate-bar prevention** | Cache deduplication exists, but no warning if duplicate timestamps arrive from MT5 (would indicate bridge/data issues). | LOW |

---

## 3. EXECUTION WIRING

### Status: BROKEN CONSTRUCTOR — WILL NOT START

The intended production path:

```
LiveDataFeed -> BreakoutSignal -> IntentFactory -> S8Runtime -> PropFirmGuard -> RiskGuard -> MT5ExecutionAdapter -> MT5Client -> MT5 Bridge -> MT5
```

**Critical finding in s8_runtime.py initialize() (line 202):**

```python
self._engine = S7Engine(
    config=S7Config(),
    risk_guard=self._prop_guard,   # <- S7Engine.__init__ does NOT accept this
    adapter=None,                   # <- S7Engine.__init__ does NOT accept this
)
```

`S7Engine.__init__` only accepts `config`. It creates its own `RiskGuard`, `MT5ExecutionAdapter`, and `ExecutionCoordinator` internally. The `risk_guard` and `adapter` kwargs will raise `TypeError` at runtime.

**S8Runtime will crash on initialization.** The system cannot start.

**Additional wiring gaps:**

| Gap | Detail |
|-----|--------|
| `_get_strategy_signal()` is a placeholder | Always returns `None`. No BreakoutSignal wired. |
| No trade outcome feedback | `S7Engine.execute()` never calls `PropFirmGuard.record_trade_result()`. Circuit breakers never receive results. Daily PnL never updates. |
| PropFirmGuard not injected into S7Engine | S7Engine creates its own `RiskGuard`, not the `PropFirmGuard`. |
| `--dry-run` flag ignored | Parsed but never passed to runtime. No distinction between dry-run and live. |

---

## 4. RISK CONFIGURATION

### Current Values (PropFirmConfig defaults)

| Parameter | Current Value | Dollar Amount on $200K |
|-----------|--------------|----------------------|
| Risk per trade | 1.0% | $2,000 |
| Max daily loss (prop) | 4.0% | $8,000 |
| Max total drawdown (prop) | 10.0% | $20,000 |
| Max concurrent positions | 5 | -- |
| Max per-pair exposure | 1.0 lot | -- |
| Max total exposure | 5.0 lots | -- |
| Max trades per day | not configured | -- |
| Max consecutive losing days | 5 | -- |

### Recommended Experimental Values

| Parameter | Recommended | Dollar Amount on $200K | Rationale |
|-----------|------------|----------------------|-----------|
| **Risk per trade** | **0.10%** | **$200** | 10x reduction. Information collection, not profit. |
| **Experimental daily loss** | **0.50%** | **$1,000** | 8x tighter than prop firm limit. Early warning. |
| **Experimental total drawdown** | **1.00%** | **$2,000** | 10x tighter than prop firm limit. |
| Max concurrent positions | 2 | -- | Conservative for initial validation |
| Max per-pair exposure | 0.05 lots | -- | Minilot for EUR/USD |
| Max total exposure | 0.10 lots | -- | Two concurrent positions max |
| Max trades per day | 2 | -- | Prevent overtrading |
| Max consecutive losing days | 3 | -- | Early stop for regime detection |

### Prop-Firm Hard Limits (absolute ceilings — never exceed)

| Parameter | Prop Firm Limit |
|-----------|----------------|
| Daily loss | $8,000 (4%) |
| Total drawdown | $20,000 (10%) |
| Profit target | $20,000 (10%) |

---

## 5. SAFETY

### Dry-Run Protection: **NOT IMPLEMENTED**

- `--dry-run` flag is parsed in `s8_runner.py` but never passed to `S8Runtime` or `RuntimeConfig`.
- No `dry_run` field exists on `RuntimeConfig`.
- No check in `_process_pair()` or `execute()` prevents real orders when in dry-run mode.
- Running `s8_runner.py` without `--dry-run` has identical behavior to running with it.

### Live Activation Protection: **NOT IMPLEMENTED**

- There is no `--mode` or `--live` flag.
- There is no environment variable check (`NESTQUANT_LIVE=true`).
- There is no explicit activation step before real orders can be placed.
- Any run of `s8_runner.py` will attempt real execution (if strategy were wired).

### Kill Switch: **NOT IMPLEMENTED**

- Health monitor records disconnections but takes no action.
- `S7Engine.execute()` does not check health before trading.
- Circuit breakers exist in `RiskGuard.evaluate()` but never receive trade results (dead code).
- No automatic halt on repeated execution failures.
- No automatic halt on abnormal slippage.
- No automatic halt on invalid strategy output.

### Position Sync on Shutdown: **NOT IMPLEMENTED**

- `stop()` only sets `_should_stop = True`.
- No `close_all_positions()` call.
- No emergency flatten.
- Existing positions are left at the broker when runtime stops.

### Existing positions vs new trades: **CORRECTLY SEPARATED**

- `close_all_positions()` exists in `MT5Client` but is never called.
- Stopping the runtime does NOT close positions (correct behavior per AGENTS.md: "STOP NEW TRADES != CLOSE EXISTING POSITIONS").

---

## 6. OBSERVABILITY

### What IS Logged

| Record Type | Logged By | Status |
|-------------|-----------|--------|
| Signal | `TradeLogger.log_signal()` | ✅ Called from S8Runtime |
| Order | `TradeLogger.create_order()` | ⚠️ Called but with hardcoded volume=0, latency=0, spread=0 |
| Infrastructure events | `TradeLogger.log_infrastructure_event()` | ✅ On rejection/error |

### What IS NOT Logged (Gaps)

| Record Type | Status | Impact |
|-------------|--------|--------|
| **Fill** | `create_fill()` **never called** | No fill price, no slippage measurement, no commission tracking |
| **Exit** | `create_exit()` **never called** | No realized PnL, no hold duration, no exit reason |
| **Bar** | `log_bar()` **never called** | No bar-level audit trail |
| **Equity snapshot** | Not logged with trades | Cannot reconstruct account state at trade time |
| **Risk decision** | Not logged | Cannot trace why a trade was approved/rejected |
| **Commission/swap** | Not captured in ExecutionResult | Cannot calculate true net PnL |

### Trade Lifecycle Traceability

```
Signal -> ✅ SignalRecord
Intent -> ⚠️ (no record, only in-memory)
Risk Decision -> ❌ Not logged
Order -> ⚠️ OrderRecord (volume=0, latency=0)
Fill -> ❌ FillRecord never created
Position -> ❌ No position record
Exit -> ❌ ExitRecord never created
Realized PnL -> ❌ Not logged
```

**A trade cannot be traced end-to-end.** Signal -> fill -> exit -> PnL chain is broken.

---

## 7. BLOCKERS

### CRITICAL (Must fix before any live order)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| C1 | **ATR_SL_MULT mismatch** — research used 2.0, live uses 3.0 | `signals/breakout.py:9` imports from `config/settings.py:321` | Strategy trades with unvalidated parameters. Different risk profile than research. |
| C2 | **RRR mismatch** — research used 3.5, live hardcodes 2.0 | `signals/breakout.py:72,78` | TP at 2R instead of 3.5R. Different expectancy profile. |
| C3 | **S8Runtime constructor crash** — `S7Engine()` called with invalid kwargs | `execution/s8_runtime.py:202-206` | Runtime cannot initialize. System will not start. |
| C4 | **Strategy not wired** — `_get_strategy_signal()` returns None | `execution/s8_runtime.py:322` | No trades will ever be generated. |
| C5 | **PropFirmGuard not injected** — S7Engine creates its own RiskGuard, not PropFirmGuard | `execution/s8_runtime.py:202-206` | Prop-firm safety limits never enforced. |
| C6 | **No dry-run mode** — `--dry-run` flag is ignored | `scripts/s8_runner.py:75-78` | Cannot test without risking real money. |
| C7 | **No trade outcome feedback** — circuit breakers never receive results | `execution/s7_engine.py:203-227` | Circuit breakers are dead code. |

### IMPORTANT (Should fix before controlled activation)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| I1 | **No kill switch** — health failures don't halt trading | `execution/health_monitor.py` | Trades can execute against unhealthy bridge. |
| I2 | **No health check before execution** — `S7Engine.execute()` doesn't verify connection | `execution/s7_engine.py:203` | Orders can fail with stale connection state. |
| I3 | **No live activation gate** — any run can trade | `scripts/s8_runner.py` | Accidental live activation possible. |
| I4 | **ATR SMA vs Wilder's EMA** — LiveDataFeed uses SMA, BreakoutSignal uses Wilder's | `execution/data_feed.py:274` vs `indicators/atr.py:35` | ATR values diverge if LiveDataFeed.get_atr() is used. |
| I5 | **Fill/exit records never created** | `execution/s7_engine.py:294-306` | No trade lifecycle audit trail. |
| I6 | **Order logging hardcoded** — volume=0, latency=0, spread=0 | `execution/s7_engine.py:300-305` | Order records are inaccurate. |

### NON-BLOCKING (Can address during activation)

| # | Issue |
|---|-------|
| N1 | No missing-bar handling in LiveDataFeed |
| N2 | No session time filter in live system |
| N3 | No breakeven stop management |
| N4 | No trailing stop |
| N5 | No max holding period |
| N6 | No equity snapshot in trade records |

---

## 8. MINIMUM CHANGES REQUIRED

### Before ANY live order (must-fix list):

1. **Fix BreakoutSignal parameters** — Either:
   - (a) Change `config/settings.py` ATR_SL_MULTIPLIER to 2.0 and make TP configurable with RRR=3.5, OR
   - (b) Override defaults in BreakoutSignal constructor with research values
   - **Recommendation**: Option (b) — pass research values explicitly without changing shared config

2. **Fix S8Runtime constructor** — Remove invalid kwargs from `S7Engine()` call. Wire PropFirmGuard properly.

3. **Wire BreakoutSignal** — Implement `_get_strategy_signal()` to call BreakoutSignal.generate() with OHLCV DataFrame.

4. **Add `--mode` flag** — Require `--mode experimental-live` for real orders. Default to `dry-run`.

5. **Add kill switch** — Check health and circuit breakers in `S8Runtime._process_pair()` before executing.

6. **Feed trade outcomes to PropFirmGuard** — Call `record_trade_result()` after execution.

---

## 9. ACTIVATION CHECKLIST

Before first real strategy trade, confirm ALL:

- [ ] **C1 fixed**: BreakoutSignal uses ATR_SL_MULT=2.0, RRR=3.5 (research values)
- [ ] **C2 fixed**: TP calculation uses configurable RRR, not hardcoded 2.0
- [ ] **C3 fixed**: S8Runtime initializes without error
- [ ] **C4 fixed**: BreakoutSignal is wired and producing signals from live data
- [ ] **C5 fixed**: PropFirmGuard is the risk guard in the execution path
- [ ] **C6 fixed**: `--mode dry-run` is default; `--mode experimental-live` required for real orders
- [ ] **C7 fixed**: Trade results feed back to PropFirmGuard and circuit breakers
- [ ] **I1 fixed**: Kill switch halts new trades when health fails
- [ ] **I2 fixed**: Health check passes before execution
- [ ] **I3 fixed**: Explicit mode required for live activation
- [ ] **Risk configured**: Risk per trade = 0.10% ($200), daily limit = 0.50% ($1,000), total limit = 1.00% ($2,000)
- [ ] **Experiment ID generated**: `ExperimentConfig` created with correct parameters
- [ ] **Config hash computed**: Full config hash matches research values
- [ ] **EUR/USD verified**: Only pair authorized for initial experiment
- [ ] **H4 timeframe verified**: Matches research
- [ ] **MT5 bridge running**: Container healthy, AutoTrading enabled
- [ ] **Account confirmed**: Demo account with $5M balance, NOT prop firm yet
- [ ] **Dry-run test passed**: Full pipeline executes without real orders
- [ ] **Logging verified**: Signal records written with experiment_id
- [ ] **Operator authorization**: You have explicitly approved this activation

---

## SUMMARY

The system has strong architectural bones — clean contracts, good separation of concerns, proper experiment identity. But there are **7 critical blockers** that must be fixed before any live order. The most dangerous is the parameter mismatch: the live system would trade with ATR_SL_MULT=3.0 / RRR=2.0, while all research was done with 2.0 / 3.5. This is not a minor difference — it fundamentally changes the strategy's risk/reward profile.

**STOPPING HERE per instruction. No live order placed. No code changes committed. Awaiting your authorization to proceed with fixes.**
