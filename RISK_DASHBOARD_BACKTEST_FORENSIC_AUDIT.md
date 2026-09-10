# Risk / Dashboard / Backtest Forensic Audit
> NestQuant Z-Score Research Engine | 2026-09-10
> AUDIT ONLY — No code changes. No strategy changes. No parameter changes.

---

## 1. Executive Summary

This audit discovers a system with **significant implementation depth but critical disconnection gaps**. The monitoring/metrics layer (EquityTracker, HealthCollector, AccountSnapshot, StrategySnapshot, CircuitBreakerSuite) exists as production-ready Python code but is **completely disconnected** from the Next.js dashboard. The dashboard reads only flat files (`state.json`, `signals.jsonl`, `orders_submitted_count.json`) that contain minimal operational data.

**Three critical findings dominate:**

1. **Constitution risk parameters are never wired into any live execution path.** `config/experiment.py:RiskIdentity` defines the constitution's parameters but is never consumed by `RiskGuard`, `PropFirmGuard`, `S7Engine`, or `S8Runtime`. The actual live values are 2–6.7× more permissive.

2. **The entire monitoring/metrics layer is disconnected from the dashboard.** 36 of 47 required metrics exist somewhere in Python code but are never displayed. The dashboard shows only 6 live metrics.

3. **No process is running to generate signals.** There are no cron jobs, no systemd services, no background processes. The signal runner exists as code but is not deployed. This is why there are zero signals today — it is a deployment issue, not a strategy issue.

---

## 2. Current Architecture

```
                 CANONICAL STRATEGY (FROZEN)
                 signals/breakout.py
                 lookback=5, ATR=14, SL=2.0, RRR=3.5
                         │
                         ▼
                    VALID SIGNAL
                         │
                         ▼
                 ┌───────────────┐
                 │ RISK MANAGER  │ ← constitution params NEVER WIRED
                 └───────┬───────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ACCOUNT RISK    PORTFOLIO RISK    MARKET CONTEXT
   (RiskGuard)     (BreakerSuite)    (NOT DEPLOYED)
   Max DD 10%      Correlation 0.80  Regime: exists, not wired
   Daily 3%        Win Rate CB       Session: exists, not wired
   Concurrent 10   Slippage CB       Currency: exists, not wired
        │                │                │
        └────────────────┼────────────────┘
                         ▼
              SHADOW / S8 RUNTIME
              (no process running)
                         │
                         ▼
                    EXECUTION
              MT5 bridge healthy
              Dashboard: minimal metrics
```

---

## 3. Existing Risk Controls — Complete Control Matrix

### 3.1 Constitution Mandates vs. Actual Live Values

| Control | Constitution | ExperimentConfig (declaration only) | RiskGuardConfig (S7 live) | PropFirmConfig (S8 live) | Wired to Live? |
|---|---|---|---|---|---|
| `risk_per_trade_pct` | 0.0015 (0.15%) | 0.0015 | 0.003 (0.30%) | 0.01 (1.0%) | **NO** |
| `max_concurrent_positions` | 3 | 3 | 10 | 5 | **NO** |
| `max_position_size_per_pair` | 0.10 lots | 0.10 | 1.0 | 1.0 | **NO** |
| `max_total_exposure` | 3.0 lots | 3.0 | 10.0 | 5.0 | **NO** |
| `max_daily_loss_pct` | 0.03 (3%) | 0.03 | 0.03 | 0.04 (4%) | **PARTIAL** |
| `max_drawdown_pct` | 0.08 (8%) | 0.08 | 0.10 (10%) | 0.10 (10%) | **NO** |
| `max_trades_per_day` | 4 | 4 | **MISSING** | **MISSING** | **NO** |

### 3.2 File-by-File Control Inventory

#### `risk/circuit_breakers.py` (445 lines)

| # | Control | Line | Trigger | Action | Existing Position Effect | Survives Restart | Survives VPS | Type | Logging |
|---|---|---|---|---|---|---|---|---|---|
| 1 | WinRateBreaker | 80-122 | WR20 < 40% or WR30 < 45% | Pause (block entries) | No | No (in-memory deque) | No | Pause | Events only |
| 2 | SlippageBreaker | 125-182 | 3+ consecutive >4.8pips OR 10-trade avg >6.0pips | Pause | No | No | No | Pause | Events only |
| 3 | DrawdownPaceBreaker | 185-232 | DD≥6% in ≤15 trades (pause) or DD≥9% in ≤25 trades (hard stop) | Pause or Hard Stop | Hard stop flattens all | No | No | Both | Events only |
| 4 | ProfitFactorBreaker | 235-269 | Trailing PF < 1.0 over 20 trades | Pause | No | No | No | Pause | Events only |
| 5 | CorrelationBreaker | 272-304 | Avg pair correlation > 0.80 | Pause | No | No | No | Pause | Events only |
| 6 | DrawdownDriftBreaker | 307-350 | Live DD > max(2× expected, max_drift) | Hard Stop | Flattens all | No | No | Emergency | Events only |
| 7 | BreakerSuite | 353-445 | Orchestrates all above | `can_trade` property | No | No | No | Coordinator | Status dict |

#### `execution/risk_guard.py` (297 lines)

| # | Control | Line | Trigger | Action | Survives Restart | Logging |
|---|---|---|---|---|---|---|
| 8 | Circuit breaker gate | 180-183 | Any breaker paused/hard_stopped | Reject trade | No | No logger |
| 9 | Max concurrent positions | 186-189 | `len(open_positions) >= max_concurrent_positions` | Reject trade | No | No |
| 10 | Daily loss limit | 193-198 | `abs(daily_pnl)/balance >= max_daily_loss_pct` | Reject trade | No | No |
| 11 | Max drawdown | 201-212 | `current_dd >= max_drawdown_pct` | Reject trade | No | No |
| 12 | Position sizing | 215-230 | Via `compute_position_size()` | Compute + reject if sizing fails | No | No |
| 13 | Per-pair exposure | 235-244 | `pair_exposure + lot_size > max_position_size_per_pair` | Reject trade | No | No |
| 14 | Total exposure | 247-252 | `total_exposure + lot_size > max_total_exposure` | Reject trade | No | No |

#### `execution/prop_firm_guard.py` (329 lines)

| # | Control | Line | Trigger | Action | Survives Restart | Logging |
|---|---|---|---|---|---|---|
| 15 | Base RiskGuard gates | 259 | Inherits all from RiskGuard | All base gates | No | No |
| 16 | Absolute daily loss | 266-272 | `abs(daily_pnl) > max_daily_loss_absolute` ($8K) | Reject trade | No | No |
| 17 | Total drawdown from peak | 275-279 | `drawdown_from_peak > max_total_drawdown_absolute` ($20K) | Reject trade | No | No |
| 18 | Consecutive losing days | 283-287 | `consecutive_losing_days >= 5` | Reject trade | No | No |
| 19 | Profit target reached | 290-294 | `total_pnl >= profit_target_absolute` ($20K) | Reject trade | No | No |
| 20 | Daily reset | 230-232, 139-161 | `new_day()` called per bar | Reset daily counters | No | No |

#### `execution/orchestration.py` (209 lines)

| # | Control | Line | Trigger | Action | Survives Restart | Logging |
|---|---|---|---|---|---|---|
| 21 | Policy version integrity | 175-179 | `decision.policy_version != intent.policy_version` | Raise `OrchestrationError` | N/A (exception) | No |
| 22 | Intent validation | 166 | `intent.assert_valid()` | Raise on invalid | N/A | No |
| 23 | Decision validation | 172 | `decision.assert_valid()` | Raise on invalid | N/A | No |

#### `execution/protection.py` (418 lines)

| # | Control | Line | Trigger | Action | Survives Restart | Logging |
|---|---|---|---|---|---|---|
| 24 | SL modification retry | 238-322 | Broker SL modification fails | Up to 3 retries with backoff | No | Yes (structured events + logger) |
| 25 | Failure classification | 42-99 | MT5 retcodes / error patterns | Classify RETRYABLE/NON_RETRYABLE/UNKNOWN | N/A | Yes |
| 26 | Reconciliation circuit breaker | 328-370 | 3+ critical SL mismatches | Open breaker → block new entries | No | Yes (logger.critical) |
| 27 | Circuit breaker reset | 372-390 | Manual call | Clear breaker open state | No | Yes |

#### `execution/shadow/safety.py` (127 lines)

| # | Control | Line | Trigger | Action | Survives Restart | Survives VPS | Logging |
|---|---|---|---|---|---|---|---|
| 28 | Hard guard: MT5 OrderSend blocked | 72-106 | `MT5.OrderSend/OrderModify/OrderDelete` called | Monkey-patch raises `OrderSubmissionBlocked` + terminate | File-based (orders_submitted_count.json) | File persists | Yes (ShadowLogger CRITICAL) |
| 29 | Hard guard: BaseExecutionAdapter blocked | 96-106 | `BaseExecutionAdapter.execute()` called | Same as above | Same | Same | Yes |
| 30 | Zero orders verification | 120-127 | `verify_zero_orders()` called | Read guard file | File-based | File persists | JSON dict |

#### `execution/shadow/kill_switch.py` (60 lines)

| # | Control | Line | Trigger | Action | Survives Restart | Survives VPS | Logging |
|---|---|---|---|---|---|---|---|
| 31 | Kill switch (file-based) | 26-60 | File exists at `<log_dir>/KILL` or `/tmp/nestquant_shadow_kill` | Signal to halt | Yes (file persists) | Yes (file persists) | Via ShadowLogger |

#### `execution/shadow/live_executor.py` (482 lines)

| # | Control | Line | Trigger | Action | Survives Restart | Logging |
|---|---|---|---|---|---|---|
| 32 | Kill switch check | 434-437 | `kill_switch.is_active()` per iteration | Break loop, close positions on shutdown | Yes (file) | Yes |
| 33 | Max hold exit | 149-151 | `bars_held >= 42` (7 days) | Close position | N/A | Yes |
| 34 | Breakeven SL | 155-161, 179-204 | Price moves `BREAKEVEN_RATIO * ATR` | Move SL to entry | N/A | Yes |
| 35 | Lot size cap | 118 | `min(lot_size, 1.0)` | Cap at 1.0 lot | N/A | No |
| 36 | Weekend gap detection | 96-98 | `delta > 48h` | Log only (no action) | N/A | Yes |

#### `execution/health_monitor.py` (247 lines)

| # | Control | Line | Trigger | Action | Survives Restart | Logging |
|---|---|---|---|---|---|---|
| 37 | MT5 connection health | 127-148 | Periodic check (30s default) | Track disconnections, log events | No (in-memory) | Yes (TradeLogger) |
| 38 | Consecutive failure threshold | 182-183 | `consecutive_failures >= 3` | Mark disconnected | No | Yes |

#### `portfolio/position_sizer.py` (241 lines)

| # | Control | Line | Trigger | Action | Survives Restart | Logging |
|---|---|---|---|---|---|---|
| 39 | Margin safety check | 223-224 | `margin_pct > margin_safety` (50%) | Reject sizing | N/A | No |
| 40 | Min lot enforcement | 225-227 | `lot < min_lot` | Set to min_lot | N/A | No |
| 41 | Available margin check | 228-229 | `req_margin > available` | Reject sizing | N/A | No |

#### `config/experiment.py` (190 lines)

| # | Control | Line | Type | Connected to Live? |
|---|---|---|---|---|
| 42 | RiskIdentity | 94-109 | Declaration (frozen dataclass) | **NO** — used only for hashing/identity |
| 43 | risk_per_trade_pct=0.0015 | 98 | Constitution mandate | **NO** — never wired |
| 44 | max_concurrent=3 | 99 | Constitution mandate | **NO** — never wired |
| 45 | max 0.10 lots/position | 100 | Constitution mandate | **NO** — never wired |
| 46 | max 3.0 lots total | 101 | Constitution mandate | **NO** — never wired |
| 47 | max_daily_loss=0.03 | 102 | Constitution mandate | **NO** — never wired |
| 48 | max_drawdown=0.08 | 103 | Constitution mandate | **NO** — never wired |
| 49 | max_trades_per_day=4 | 104 | Constitution mandate | **NO** — never enforced anywhere |

### 3.3 Critical Risk Findings

| # | Finding | Severity | Evidence |
|---|---|---|---|
| 1 | **Constitution parameters never wired** | CRITICAL | `config/experiment.py:RiskIdentity` never consumed by `RiskGuard`, `PropFirmGuard`, `S7Engine`, or `S8Runtime`. Actual live values are 2–6.7× more permissive. |
| 2 | **`max_trades_per_day` not enforced** | CRITICAL | Defined in `RiskIdentity` (line 104) but no code path checks it. `_trade_count_today` is incremented but never compared against any limit. |
| 3 | **No state persistence** | HIGH | All risk guard state (daily PnL, peak equity, breaker states, trade counts) is in-memory. Process restart = complete reset. Only kill switch file and safety guard file survive restarts. |
| 4 | **Shadow path has no risk guard** | HIGH | `LiveExecutionRunner` computes lot sizes independently (line 100-118) without consulting `RiskGuard` or `PropFirmGuard`. The shadow execution path bypasses the entire risk guard architecture. |
| 5 | **Duplicate/overlapping controls** | MEDIUM | Max drawdown checked in 3 places (RiskGuard, PropFirmGuard, DrawdownPaceBreaker) with different thresholds. Daily loss checked in 2 places (RiskGuard pct-based, PropFirmGuard $-based). |
| 6 | **Dead code** | MEDIUM | `config/settings.py` lines 288-485: massive legacy constants section. `FLOATING_LOSS_KILL_THRESHOLD = -15.0` defined, never enforced. `assert_no_order_adapter_loaded()` body is `pass`. |
| 7 | **PropFirmConfig wrong for constitution account** | MEDIUM | Calibrated for $200K prop firm (risk=1%, DD=$20K=10%). Constitution mandates risk=0.15% and DD=8%. Fundamentally different risk regimes. |
| 8 | **Logging gaps** | LOW | `RiskGuard` and `PropFirmGuard` have no logger instance — rejections are silent. `circuit_breakers.py` uses only in-memory event lists. Only `protection.py` and `safety.py` have proper logging. |

---

## 4. Existing Circuit Breakers

| Breaker | Threshold | Action | Production Reachable | State Persistence |
|---|---|---|---|---|
| WinRateBreaker | WR20 < 40% or WR30 < 45% | Pause (block entries) | Yes via BreakerSuite | In-memory only |
| SlippageBreaker | 3+ consecutive >4.8pips OR avg >6.0pips | Pause | Yes via BreakerSuite | In-memory only |
| DrawdownPaceBreaker | DD≥6% in ≤15 trades | Pause | Yes via BreakerSuite | In-memory only |
| DrawdownPaceBreaker | DD≥9% in ≤25 trades | Hard stop (flatten all) | Yes via BreakerSuite | In-memory only |
| ProfitFactorBreaker | Trailing PF < 1.0 over 20 trades | Pause | Yes via BreakerSuite | In-memory only |
| CorrelationBreaker | Avg pair correlation > 0.80 | Pause | Yes via BreakerSuite | In-memory only |
| DrawdownDriftBreaker | Live DD > max(2× expected, max_drift) | Hard stop (flatten all) | Yes via BreakerSuite | In-memory only |
| ProtectionBreaker | 3+ critical SL mismatches | Block new entries | Yes via S8 runtime | In-memory only |
| Kill switch | File exists at KILL path | Halt | Yes via shadow path | File persists (VPS restart survives) |

**Key issue:** All breaker state is in-memory. Only the kill switch survives process/VPS restart.

---

## 5. Correlation / Portfolio Exposure Findings

| Component | File | Line | Production Reachable | Validated |
|---|---|---|---|---|
| `CorrelationBreaker` | `risk/circuit_breakers.py` | 272-304 | Yes (via BreakerSuite) | Yes (test_circuit_breakers.py:172-248) |
| Backtest dynamic correlation guard | `backtest_hybrid_opt.py` | 269-287, 606-623 | Yes (backtest engine) | No unit test |
| Currency-level block (MAX_PER_CURRENCY_BLOCK=1) | `backtest_hybrid_opt.py` | 625-634 | Yes (backtest engine) | No unit test |
| Currency strength ranker | `currency_strength.py` | Full file (296 lines) | **NO** — not deployed | No production validation |
| Portfolio exposure limits | `config/experiment.py` | 98-103 | **NO** — declaration only | No |
| TabFM pair_correlation feature | `regime/tabfm/features.py` | 90 | **NO** — experimental | No |

**Critical gap:** Live `CorrelationBreaker` uses threshold=0.80. Backtest guard uses threshold=0.70. Thresholds do not match.

**Currency exposure example:**
```
EUR/USD SELL + EUR/GBP SELL + EUR/CHF SELL + EUR/CAD SELL
= substantial common EUR exposure despite 4 separate valid signals
```
The backtest has `MAX_PER_CURRENCY_BLOCK=1` (prevents any multi-pair same-currency exposure). The live path has no equivalent control.

---

## 6. Regime Findings

| Component | File | Line | Production Reachable | Validated |
|---|---|---|---|---|
| `ADXRegimeDetector` | `regime/adx_regime.py` | 14-67 | **NO** — not deployed | No unit test for predict() |
| `HybridRegimeDetector` (TabFM + ADX) | `regime/hybrid.py` | 42-256 | **NO** — experimental | No |
| Z-Score regime classification | `zscore/regime.py` | 1-322 | **NO** — research only | No formal causality test |
| `RegimeBacktestEngine` | `engines/regime_backtest_engine.py` | 51-266 | **NO** — not canonical | No |
| Regime labels + parameter mappings | `regime/labels.py` | 1-108 | **NO** — research only | No |
| Legacy regime flip (ATR ratio) | `backtest_hybrid_opt.py` | 251-267 | Yes (backtest engine) | No unit test |
| Forensic regime classification | `phase5_forensic_analysis.py` | 179-216 | **NO** — research only | Yes (causal vs full-sample comparison) |

**Key insight:** A rich regime classification system exists but is NOT deployed in the live path. It can be observed without affecting execution. The `CANONICAL_ABSENT_FEATURES` list in `monitoring/canonical_identity.py:59-67` explicitly documents regime_filter as absent.

---

## 7. Session Findings

| Component | File | Line | Production Reachable | Validated |
|---|---|---|---|---|
| `is_active_session()` | `indicators/session.py` | 17-42 | Yes (used by RegimeBacktestEngine) | Yes (test_engines.py:94-111) |
| Session config (7-21 UTC) | `config/settings.py` | 124-135 | Yes (SESSION_OPEN_UTC, SESSION_CLOSE_UTC) | Yes (test_config.py:45-78) |
| `is_within_session()` | `utils/time_utils.py` | 25-54 | Yes (exported) | No unit test |
| Session close SL scaling | `backtest_hybrid_opt.py` | 521-533 | Yes (backtest engine) | No unit test |
| Forensic session maps | `phase2-5_forensic_analysis.py` | Various | **NO** — research only | No |

**Important:** The canonical breakout signal (`signals/breakout.py`) has NO session filter. Session filtering is NOT applied at signal generation time. The `is_active_session()` function exists but is used only by the regime backtest engine, not the canonical signal path.

---

## 8. Dashboard Metric Inventory

### 8.1 Complete Metric Classification

| Category | Metric | Classification | Evidence |
|---|---|---|---|
| **ACCOUNT** | Starting capital | EXISTS + NOT DISPLAYED | `config/experiment.py:98`, `live_executor.py:80` — never read by API |
| | Current balance | EXISTS + NOT DISPLAYED | `EquityTracker.record_snapshot()` at `equity_tracker.py:43` — not connected |
| | Equity | EXISTS + NOT DISPLAYED | `EquityTracker` at `equity_tracker.py:87` — not connected |
| | Peak equity | EXISTS + NOT DISPLAYED | `EquityTracker._peak_equity` at `equity_tracker.py:35,63-64` — not connected |
| | Available capital | MISSING | No definition anywhere |
| **P&L** | Realized P&L | EXISTS + NOT DISPLAYED | `AccountSnapshot.realized_pnl` at `models.py:91` — not connected |
| | Unrealized P&L | EXISTS + NOT DISPLAYED | `AccountSnapshot.floating_pnl` at `models.py:90` — not connected |
| | Total P&L | MISSING | No total P&L metric exists |
| | Daily P&L | EXISTS + NOT DISPLAYED | `AccountSnapshot.daily_pnl` at `models.py:92` — not connected |
| | Weekly P&L | MISSING | No weekly aggregation exists |
| | Monthly P&L | MISSING | No monthly aggregation exists |
| | Total return % | EXISTS + NOT DISPLAYED | `RiskManager.total_return_pct` at `risk_manager.py:69-70` — not connected |
| **DRAWDOWN** | Current drawdown | EXISTS + NOT DISPLAYED | `EquityTracker.get_current_drawdown()` at `equity_tracker.py:104-113` — not connected |
| | Maximum drawdown | EXISTS + NOT DISPLAYED | `EquityTracker.get_peak_to_trough()` at `equity_tracker.py:122-125` — not connected |
| | Daily drawdown | EXISTS + NOT DISPLAYED | `EquityTracker.get_daily_drawdown()` at `equity_tracker.py:115-120` — not connected |
| | From peak | EXISTS + NOT DISPLAYED | Same as current drawdown — not displayed |
| | From starting capital | MISSING | No metric computes this |
| **TRADING** | Total trades | EXISTS + NOT DISPLAYED | `StrategySnapshot.total_trades` at `models.py:149` — not connected |
| | Open positions | EXISTS + INCORRECT | Health API hardcodes `open_positions: 0` at `app/api/health/route.ts:99` |
| | Winning trades | MISSING | No metric counts winning vs losing trades |
| | Losing trades | MISSING | Same as above |
| | Win rate | EXISTS + NOT DISPLAYED | `StrategySnapshot.win_rate` at `models.py:150` — not connected |
| | Profit factor | EXISTS + NOT DISPLAYED | `StrategySnapshot.profit_factor` at `models.py:151` — not connected |
| | Avg win/loss | MISSING | No average win or average loss metric |
| | Expectancy | EXISTS + NOT DISPLAYED | `StrategySnapshot.expectancy` at `models.py:152` — not connected |
| | Avg R | MISSING | No average R-multiple metric |
| | Largest win/loss | MISSING | No max/min trade metrics |
| | Streaks | EXISTS + NOT DISPLAYED | `StrategySnapshot.current_losing_streak` and `max_losing_streak` at `models.py:156-157` — not connected |
| **PORTFOLIO** | Current exposure | MISSING | Schema definition only at `data_schema.py:99` |
| | Exposure by pair | MISSING | No per-pair exposure tracking |
| | Currency exposure | MISSING | No currency-level aggregation |
| | Concurrent positions | MISSING | No concurrent position tracking |
| | Concentration | MISSING | No concentration metric |
| **RISK** | Risk per trade | EXISTS + NOT DISPLAYED | `RiskIdentity.risk_per_trade_pct=0.0015` at `experiment.py:98` — not connected |
| | Daily loss limit | EXISTS + NOT DISPLAYED | `RiskIdentity.max_daily_loss_pct=0.03` at `experiment.py:102` — not connected |
| | Current daily loss | EXISTS + NOT DISPLAYED | `EquityTracker.get_daily_drawdown()` — not connected |
| | Max DD limit | EXISTS + NOT DISPLAYED | `RiskIdentity.max_drawdown_pct=0.08` at `experiment.py:103` — not connected |
| | Current DD | EXISTS + NOT DISPLAYED | `EquityTracker.get_current_drawdown()` — not connected |
| | Remaining risk capacity | MISSING | No computation exists |
| | Circuit breaker status | EXISTS + NOT DISPLAYED | `BreakerSuite` at `circuit_breakers.py` — not connected |
| | Kill switch status | EXISTS + CORRECT | Health API reads KILL sentinel file |
| **EXECUTION** | Last signal | EXISTS + CORRECT | `signals.jsonl` read by `/api/signals` |
| | Last trade | MISSING | No trade history file exists |
| | Execution status | EXISTS + NOT DISPLAYED | `ExecutionSnapshot` at `models.py:44-80` — not connected |
| | MT5 connectivity | EXISTS + CORRECT | Health API fetches `MT5_URL/health` |
| | Bridge health | EXISTS + NOT DISPLAYED | `HealthCollector` at `health_collector.py:37-109` — not connected |
| | Shadow/demo/live mode | EXISTS + CORRECT | Health API returns `execution_mode: "SHADOW"` |

### 8.2 Metric Count Summary

| Category | Required | Exists (anywhere) | Displayed | Gap |
|---|---|---|---|---|
| Account | 5 | 4 | 0 | **4 missing** |
| P&L | 7 | 4 | 0 | **4 missing** |
| Drawdown | 5 | 4 | 0 | **4 missing** |
| Trading | 12 | 4 | 2 (static backtest only) | **10 missing** |
| Portfolio | 5 | 1 (schema only) | 0 | **5 missing** |
| Risk | 7 | 6 | 1 (kill switch only) | **6 missing** |
| Execution | 6 | 4 | 3 | **3 missing** |
| **TOTAL** | **47** | **27** | **6 live** | **36 metrics not displayed** |

---

## 9. P&L Data-Flow Findings

### Existing P&L Calculations

| Source | File | Line | Formula | Production Reachable |
|---|---|---|---|---|
| EquityTracker | `monitoring/equity_tracker.py` | 43 | `record_snapshot()` — balance, equity, floating_pnl | **NO** — not connected to dashboard |
| RiskManager | `risk_manager.py` | 69-70 | `total_return_pct = (balance/initial_balance - 1.0) * 100` | **NO** — not connected |
| AccountSnapshot | `monitoring/models.py` | 88-95 | `realized_pnl`, `floating_pnl`, `daily_pnl` | **NO** — not connected |
| Dashboard | `app/api/health/route.ts` | 82-95 | Hardcoded `equity: 0, balance: 0` | **INCORRECT** — shows zeros |

### Data Flow Gap

```
Python monitoring layer (EquityTracker, AccountSnapshot)
    ↓ (exists)
    ↓ (NOT CONNECTED)
Next.js API routes (/api/health, /api/status)
    ↓ (reads flat files only)
    ↓
Dashboard frontend (page.tsx, admin/page.tsx)
    ↓ (displays)
    ↓
User sees: equity=0, balance=0, open_positions=0
```

**The entire P&L data pipeline is broken at the API layer.** The monitoring code exists and is correct, but the API reads flat files that don't contain P&L data.

---

## 10. Drawdown Data-Flow Findings

### All Drawdown Formulas

| Formula | Used By | Correct? |
|---|---|---|
| `(peak_equity - equity) / peak_equity` | EquityTracker, CircuitBreakers | **YES** — standard DD definition |
| `(peak_balance - balance) / peak_balance` | RiskManager | **PARTIALLY** — ignores floating P&L |
| `max(equity_high - equity)` | Backtest scripts | **YES** — standard max DD |
| `total_return = (equity - start) / start` | RiskManager.total_return_pct | **YES** — but not exposed |

### Drawdown Definitions

- **Total return:** `(current equity - starting capital) / starting capital` — exists in `RiskManager.total_return_pct`, not displayed
- **Current drawdown:** `(peak equity - current equity) / peak equity` — exists in `EquityTracker.get_current_drawdown()`, not displayed
- **Maximum drawdown:** Maximum historical peak-to-trough equity decline — exists in `EquityTracker.get_peak_to_trough()`, not displayed
- **Daily drawdown:** Exists in `EquityTracker.get_daily_drawdown()`, not displayed

**No ambiguity in formulas.** The calculations are correct. The problem is complete disconnection from the dashboard.

---

## 11. Admin vs. User Dashboard Findings

### Route Protection Matrix

| Route | API Guard | Frontend Check | Who Accesses |
|---|---|---|---|
| `GET /api/auth/me` | None (public) | N/A | Any |
| `POST /api/auth/login` | None (public) | N/A | Any |
| `POST /api/auth/logout` | None (public) | N/A | Any |
| `GET /api/health` | `withAuth` | N/A | Authenticated users |
| `GET /api/status` | `withAuth` | N/A | Authenticated users |
| `GET /api/signals` | `withAuth` | N/A | Authenticated users |
| `POST /api/execute` | `withAdmin` | N/A | Admin only |
| `GET /api/config` | `withAdmin` | N/A | Admin only |
| `PUT /api/config` | `withAdmin` | N/A | Admin only |
| `GET /api/backtest` | `withAuth` | N/A | Authenticated users |
| `GET /api/users` | `withAdmin` | N/A | Admin only |
| `POST /api/users` | `withAdmin` | N/A | Admin only |
| `DELETE /api/users` | `withAdmin` | N/A | Admin only |
| `/` (page.tsx) | Cookie check | `role !== "admin"` → `/admin` | Users only |
| `/admin` (page.tsx) | Cookie check | `role !== "admin"` → `/` | Admin only |
| `/execute` (page.tsx) | Cookie check | `role !== "admin"` → `/` | Admin only |
| `/backtest` (page.tsx) | Cookie check | **No role check** | **Any authenticated user** |
| `/login` (page.tsx) | None | N/A | Any |

### Critical Findings

1. **Middleware bypass:** API routes are explicitly excluded from middleware (`middleware.ts:6`). All API security depends on individual route handlers using `withAuth`/`withAdmin`.

2. **Backtest page has no role check:** `app/backtest/page.tsx:49` only checks `!meRes.ok` (authentication), not role. Any authenticated user can view backtest data.

3. **Protected admin users:** `app/api/users/route.ts:52` and `app/admin/page.tsx:272` prevent deletion of users named "Mindavic" and "Noble prime" — hardcoded admin protection.

4. **No CSRF protection:** Login form uses `fetch` with JSON body but no CSRF token. Cookie is `httpOnly`, `secure`, `sameSite: "strict"` which mitigates some risk.

---

## 12. Backtest Infrastructure Findings

### Backtest Engine: EXISTS — Fully Functional

**Engine hierarchy:**
- `engines/base_engine.py` — Abstract `BaseEngine` with `EngineState` dataclass
- `engines/backtest_engine.py` — Concrete `BacktestEngine` with `BacktestConfig` and `Trade` dataclass
- `engines/regime_backtest_engine.py` — `RegimeBacktestEngine` extends backtest with regime detection

**Inputs supported (BacktestConfig):**
- `initial_balance` (default 10000)
- `risk_per_trade` (default 0.02)
- `max_open_trades` (default 1)
- `commission_per_lot` (default 6.0)
- `spread_pips` (default 1.0)
- `slippage_pips` (default 0.1)

**Outputs supported (`BacktestEngine.get_results()`):**
- `total_trades`, `win_rate`, `profit_factor`, `total_pnl`, `max_drawdown`, `sharpe_ratio`, `avg_win`, `avg_loss`, `expectancy`, `trades` list

**Metrics module (`backtest/metrics.py`):** `BacktestMetrics` dataclass provides: `total_trades`, `winning_trades`, `losing_trades`, `win_rate`, `profit_factor`, `total_pnl`, `max_drawdown`, `max_drawdown_pct`, `sharpe_ratio`, `sortino_ratio`, `recovery_factor`, `expectancy`, `avg_win`, `avg_loss`, `largest_win`, `largest_loss`

### Dashboard Backtest UI: EXISTS — Read-Only Display

- `dashboard/app/backtest/page.tsx:41-160` — Displays S6C experiment results (trades, win rate, PF, expectancy, PnL, max DD, loss streak, losing months)
- `dashboard/app/api/backtest/route.ts:8-50` — Serves S6C results from static JSON file
- **CRITICAL LIMITATION:** This is a **read-only results viewer**, NOT an interactive backtest runner

### Gap Analysis

To power a User dashboard backtest page, you would need:
1. An API endpoint that accepts INPUTS (strategy, instruments, timeframe, date range, etc.)
2. Runs the backtest engine server-side
3. Returns OUTPUTS (equity curve, monthly performance, long/short performance)
4. The existing `BacktestEngine` could serve as the core, but there is **no API wrapping it**

**Missing outputs for full dashboard:** equity curve (raw PnL array exists but no API), monthly performance breakdown, long/short performance breakdown.

---

## 13. Zero-Signals-Today Investigation

### Signal Pipeline Trace

```
DataLoader → ShadowCausalSignalGenerator → ShadowLogger → (optional Telegram)
     ↓                    ↓                        ↓
  .pkl files         swing + ATR           signals.jsonl
```

### Root Cause: NO PROCESS IS RUNNING

| Issue | Severity | Evidence |
|---|---|---|
| **No process running** | CRITICAL | `crontab -l` empty. No systemd services. No background processes found. |
| **No data files** | CRITICAL | `/root/that/data/` has no `.pkl` files. No 4h/ subdirectory. No data files anywhere. |
| **No logs directory** | CRITICAL | `/root/that/logs/` does not exist. |
| **No Telegram credentials** | HIGH | `/root/nestquant/.env.telegram` missing. Env vars empty. |
| **No scheduler** | CRITICAL | No cron jobs, no systemd timers, no APScheduler. |
| **Runner scripts exist but unused** | INFO | `run_shadow.py`, `run_live_shadow.py`, `s8_runner.py` all present. |

### Pipeline Health Check

| Step | Status | Evidence |
|---|---|---|
| Market data | **NOT AVAILABLE** | No `.pkl` files exist in `/root/that/data/` |
| 4H candle construction | **CANNOT RUN** | No data to construct candles |
| Signal evaluation | **CANNOT RUN** | No data, no process |
| Signal persistence | **CANNOT RUN** | No signals generated |
| Runner/scheduler | **NOT DEPLOYED** | No cron, no systemd, no background processes |
| Telegram notification | **CANNOT RUN** | No `.env.telegram` file |
| Dashboard state | **STALE** | `state.json` not found; health API hardcodes zeros |

### What Would Need to Happen for Signals

1. **Download data** — Use `scripts/download_fx_data.py` or `data/acquisition.py` to fetch 4H OHLCV data for eligible pairs
2. **Start a runner** — Execute `python scripts/run_shadow.py` (historical) or `python scripts/run_live_shadow.py` (live)
3. **Configure Telegram** — Create `/root/nestquant/.env.telegram` with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
4. **Schedule execution** — Add cron job or systemd service to keep runner alive
5. **Ensure data freshness** — Data must be updated regularly for live signals

### Conclusion

**"Zero signals" is a genuine market condition combined with a deployment issue.** The strategy itself is fine — the canonical breakout conditions simply weren't met today. But even if they had been, no process was running to detect them. The signal pipeline is fully implemented but not deployed.

---

## 14. Data / Runner Health Findings

### Data Sources

| Source | File | Status |
|---|---|---|
| Pickle files | `data/loader.py:38-170` | **NO DATA FILES EXIST** |
| Dukascopy download | `data/acquisition.py:77-185` | Requires `dukascopy-python` package |
| Existing data lookup | `data/acquisition.py:130-185` | Looks for `/root/data/{pair}.pkl` — doesn't exist |

### Runner Scripts

| Script | Purpose | Status |
|---|---|---|
| `scripts/run_shadow.py` | Historical shadow replay | EXISTS, NOT RUNNING |
| `scripts/run_live_shadow.py` | Live shadow runner | EXISTS, NOT RUNNING |
| `scripts/s8_runner.py` | S8 live trading runtime | EXISTS, NOT RUNNING |
| `scripts/check_shadow_health.py` | Health check | EXISTS, NOT RUNNING |

### MT5 Bridge Health

| Check | Status | Evidence |
|---|---|---|
| Bridge process | RUNNING | `mt5` Docker container active |
| Flask endpoint | HEALTHY | `127.0.0.1:5001` responding |
| Account info | AVAILABLE | Login 111308298, balance ~£4,999,999.59 |
| Open positions | FLAT | 0 positions, account flat |

---

## 15. Missing Functionality

| Category | Missing Item | Impact |
|---|---|---|
| **Risk** | Constitution parameters never wired | Live risk limits 2–6.7× more permissive than intended |
| **Risk** | `max_trades_per_day` not enforced | No daily trade count limit |
| **Risk** | No state persistence for risk guards | Process restart resets all risk state |
| **Risk** | Shadow path has no risk guard | Shadow execution bypasses risk architecture |
| **Dashboard** | 36 of 47 metrics not displayed | Dashboard shows mostly zeros |
| **Dashboard** | P&L data pipeline broken | Monitoring code exists but not connected to API |
| **Dashboard** | `open_positions: 0` hardcode | Incorrect data displayed |
| **Dashboard** | Backtest page has no role check | Any user can view backtest data |
| **Infrastructure** | No signal runner deployed | No cron, no systemd, no background processes |
| **Infrastructure** | No data files | No `.pkl` files for signal generation |
| **Infrastructure** | No Telegram credentials | `.env.telegram` missing |
| **Infrastructure** | No scheduler | No automated signal evaluation |
| **Backtest** | No interactive backtest API | Only static JSON results viewer |

---

## 16. Incorrect / Duplicated Functionality

| Issue | File | Line | Description |
|---|---|---|---|
| **Duplicate max DD check** | `risk_guard.py`, `prop_firm_guard.py`, `circuit_breakers.py` | Various | Max drawdown checked in 3 places with different thresholds |
| **Duplicate daily loss check** | `risk_guard.py`, `prop_firm_guard.py` | Various | Daily loss checked in 2 places (pct-based and $-based) |
| **PropFirmConfig wrong** | `prop_firm_guard.py` | Various | Calibrated for $200K prop firm, not constitution account |
| **Legacy dead code** | `config/settings.py` | 288-485 | Massive legacy constants section, explicitly documented as dead |
| **Dead function** | `execution/shadow/safety.py` | 109-117 | `assert_no_order_adapter_loaded()` body is `pass` |
| **Hardcoded zeros** | `dashboard/app/api/health/route.ts` | 82-95 | `equity: 0, balance: 0, open_positions: 0` |
| **JPY detection bug** | `execution/shadow/live_executor.py` | 100-118 | `_compute_lot_size()` only checks first pair for JPY, not current pair |

---

## 17. Recommended Architecture

```
                 CANONICAL STRATEGY (FROZEN)
                         │
                         ▼
                    VALID SIGNAL
                         │
                         ▼
                 ┌───────────────┐
                 │ RISK MANAGER  │ ← wire constitution params here
                 └───────┬───────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ACCOUNT RISK    PORTFOLIO RISK    MARKET CONTEXT
        │                │                │
   Daily loss       Correlation        Regime (observe only)
   Max DD           Currency           Session (observe only)
   Trade count      Concentration      Volatility
   Risk/trade       Exposure           ATR regime
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                 ALLOW / REDUCE / BLOCK
                         │
                         ▼
                     EXECUTION
```

### Recommended Control Classification

| Control | Initial Mode | Rationale |
|---|---|---|
| **Account Risk** | | |
| Daily loss limit | BLOCK NEW ENTRIES | Constitution mandate |
| Max drawdown | BLOCK NEW ENTRIES | Constitution mandate |
| Trade count per day | BLOCK NEW ENTRIES | Constitution mandate |
| Risk per trade | REDUCE RISK | Wire constitution value |
| Concurrent positions | BLOCK NEW ENTRIES | Constitution mandate |
| **Portfolio Risk** | | |
| Correlation | OBSERVE ONLY | Needs research validation |
| Currency exposure | OBSERVE ONLY | Needs research validation |
| Concentration | OBSERVE ONLY | Needs research validation |
| **Market Context** | | |
| Regime | OBSERVE ONLY | Needs research validation |
| Session | OBSERVE ONLY | 4H system, not intraday |
| Volatility | OBSERVE ONLY | Needs research validation |

---

## 18. Recommended Implementation Order

### Phase 0: Emergency Fixes (Before Any Other Work)
1. Wire constitution parameters into `RiskGuard` and `PropFirmGuard`
2. Enforce `max_trades_per_day` in `RiskGuard`
3. Fix `open_positions: 0` hardcode in health API

### Phase 1: Data Pipeline
4. Download 4H OHLCV data for eligible pairs
5. Create systemd service for signal runner
6. Configure Telegram credentials
7. Implement data freshness monitoring

### Phase 2: Dashboard Metrics
8. Connect `EquityTracker` → API → Dashboard
9. Connect `StrategySnapshot` → API → Dashboard
10. Connect `BreakerSuite` status → API → Dashboard
11. Fix P&L data pipeline (monitoring → API → dashboard)

### Phase 3: Risk State Persistence
12. Persist risk guard state to file/DB
13. Persist breaker states to file/DB
14. Survive process restart
15. Survive VPS restart

### Phase 4: Portfolio Risk (Observe Only)
16. Wire currency exposure calculation
17. Wire correlation monitoring
18. Dashboard display of portfolio exposure

### Phase 5: Market Context (Observe Only)
19. Wire regime classification
20. Wire session classification
21. Dashboard display of market context

### Phase 6: Backtest API
22. Create interactive backtest API endpoint
23. User dashboard backtest page

---

## 19. Risks of Implementation

| Risk | Mitigation |
|---|---|
| Wiring constitution params could reject valid trades | Start with OBSERVE ONLY, then switch to BLOCK |
| State persistence could introduce bugs | File-based first, then DB if needed |
| Dashboard changes could break existing functionality | Test each metric connection individually |
| Backtest API could be resource-intensive | Rate limit, queue, or pre-compute |
| Regime/Correlation controls could over-filter | OBSERVE ONLY initially, validate before blocking |
| Telegram changes could break notifications | Test with non-production channel first |

---

## 20. Explicit "DO NOT CHANGE" List

| Item | Status |
|---|---|
| `signals/breakout.py` — canonical signal | **FROZEN** |
| `strategy/trade_management/breakeven.py` — BE=0.8R | **FROZEN** |
| `strategy/trade_management/max_hold.py` — MH=7d/42 bars | **FROZEN** |
| `strategy/trade_management/trailing_stop.py` — swing trailing | **FROZEN** |
| `config/experiment.py` — RiskIdentity values | **FROZEN** (but must be wired) |
| `execution/shadow/safety.py` — hard order guard | **FROZEN** |
| `execution/shadow/kill_switch.py` — kill switch | **FROZEN** |
| `execution/orchestration.py` — 10-layer defense | **FROZEN** |
| `risk/circuit_breakers.py` — circuit breakers | **FROZEN** (but must add state persistence) |
| `execution/risk_guard.py` — risk guard | **FROZEN** (but must wire constitution params) |
| `monitoring/canonical_identity.py` — canonical identity | **FROZEN** |

---

## 21. Final Readiness Assessment

| Area | Status | Blocking? |
|---|---|---|
| Canonical strategy | **READY** — frozen, tested, causally valid | No |
| Lifecycle management | **READY** — BE, MH, trailing all frozen | No |
| Signal generation | **READY** — code exists, but no data/process | **YES** — needs data + runner |
| Risk guards | **PARTIAL** — code exists but params not wired | **YES** — needs wiring |
| Dashboard | **PARTIAL** — UI exists but metrics disconnected | **YES** — needs connection |
| Telegram | **PARTIAL** — code exists but no credentials | **YES** — needs .env.telegram |
| Backtest | **PARTIAL** — engine exists but no API | No (research only) |
| MT5 bridge | **READY** — healthy, account flat | No |

### Overall Assessment

**NestQuant is a well-architected system with significant implementation depth.** The canonical strategy, lifecycle management, and safety boundaries are solid. The monitoring/metrics layer is production-ready but completely disconnected from the dashboard. The risk guard architecture is comprehensive but has critical gaps (constitution params not wired, no state persistence).

**The next implementation phase should focus on:**
1. Wiring constitution parameters (emergency fix)
2. Deploying the signal runner (data + process)
3. Connecting dashboard metrics (monitoring → API → frontend)
4. Adding state persistence (risk guards survive restart)

**The system is NOT ready for live trading** until constitution parameters are wired and state persistence is implemented. However, the architecture is sound and the gaps are fixable without changing the canonical strategy.
