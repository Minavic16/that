# NestQuant Codebase Forensic Audit
> Generated: 2026-09-09 | Branch: master | Commit: d898669
> **Status: AUDIT ONLY — NO CODE CHANGES UNTIL REVIEWED & APPROVED**

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Three-Config Problem](#2-three-config-problem)
3. [Full Module Classification](#3-full-module-classification)
4. [Canonical Strategy Audit](#4-canonical-strategy-audit)
5. [Dependency Violations](#5-dependency-violations)
6. [Target Architecture](#6-target-architecture)
7. [Migration Plan (Phases A–H)](#7-migration-plan-phases-a-h)
8. [Risk Assessment](#8-risk-assessment)
9. [Immutable Files](#9-immutable-files)
10. [Git Strategy](#10-git-strategy)

---

## 1. Executive Summary

The NestQuant codebase has grown organically across 10+ research phases. It contains **three conflicting configurations**, **four strategy families** mixed together, and **~40% dead/research code** alongside the production execution pipeline.

### Key Findings

| Finding | Severity | Status |
|---------|----------|--------|
| Three-configuration ambiguity (breakout.py / experiment.py / settings.py) | **CRITICAL** | Documented but not yet resolved |
| `config/settings.py` ATR/RRR mismatch with canonical breakout | **HIGH** | settings.py has ATR=3.0/RRR=2.0; breakout.py has 2.0/3.5 |
| `signals/structured_entry.py` imports from `config.settings` (wrong ATR/RRR) | **HIGH** | Uses ATR=3.0/RRR=2.0 instead of canonical 2.0/3.5 |
| Root `config.py` is dead GFT legacy code (not imported by production) | **MEDIUM** | Safe to archive |
| `zscore/` package imported by production `costs/model.py` and `data_validation/validate.py` | **MEDIUM** | Contracts used; zscore engine not used by execution |
| `regime/` package NOT imported by any production code | **LOW** | Research-only, safe to archive |
| `backtest/` and `engines/` packages NOT imported by execution pipeline | **LOW** | Research-only backtesting, safe to archive |
| 35 research scripts in `scripts/` — not imported by production | **LOW** | Safe to archive |

### Codebase Statistics

| Metric | Count |
|--------|-------|
| Python source files (non-test) | 167 |
| Test files | 72 |
| TypeScript/JS files | ~76 |
| Research scripts | 44 |
| Root-level legacy .py files | 16 |
| Research data JSON files | ~56 |
| Markdown reports | ~101 |

---

## 2. Three-Config Problem

There are **three separate configurations** that define strategy parameters. Only one is correct.

### Config A: `signals/breakout.py` (CANONICAL — Source of Truth)
```python
RESEARCH_DEFAULTS = {
    "lookback": 5,
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,   # ← 2.0
    "rrr": 3.5,                  # ← 3.5
}
# ABSENT: breakeven, max_hold, trailing_stop, session_filter, macro_filter
```

### Config B: `config/experiment.py` (EXPERIMENT — adds BE/MH)
```python
StrategyIdentity.parameters = {
    "lookback": 5,
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,   # ← 2.0 matches canonical
    "rrr": 3.5,                  # ← 3.5 matches canonical
    "breakeven_ratio": 0.8,      # ← NOT in breakout.py
    "breakeven_enabled": True,   # ← NOT in breakout.py
    "max_hold_days": 7,          # ← NOT in breakout.py
    "max_hold_bars": 42,         # ← NOT in breakout.py
    "trailing_enabled": True,    # ← NOT in breakout.py
}
```

### Config C: `config/settings.py` (LEGACY — WRONG ATR/RRR)
```python
class StrategyConfig:
    atr_sl_multiplier: float = 3.0   # ← 3.0 (WRONG, canonical is 2.0)
    rrr: float = 2.0                  # ← 2.0 (WRONG, canonical is 3.5)
    breakeven_ratio: float = 1.5      # ← 1.5 (different from experiment's 0.8)
```

### Config D: Root `config.py` (DEAD GFT LEGACY)
```python
ATR_SL_MULTIPLIER = 2.0   # ← 2.0 matches canonical
RRR = 3.5                  # ← 3.5 matches canonical
CORRELATION_THRESHOLD = 0.50  # ← from old MR+TF strategy
# NOT imported by any production code
```

### Impact Analysis

| Consumer | Which Config It Uses | Correct? |
|----------|---------------------|----------|
| `signals/breakout.py` | Own RESEARCH_DEFAULTS | ✅ YES |
| `signals/structured_entry.py` | `config/settings.py` (ATR=3.0, RRR=2.0) | ❌ NO |
| `execution/shadow/signal_generator.py` | Own frozen params (2.0/3.5) | ✅ YES |
| `config/experiment.py` | Own StrategyIdentity (2.0/3.5 + BE/MH) | ⚠️ Partial |
| `backtest_hybrid_opt.py` | Root `config.py` (2.0/3.5 + correlation) | ❌ MR+TF |
| `scripts/phase_s0_*.py` | Root `config.py` (ALL_PAIRS) | ⚠️ Research only |

---

## 3. Full Module Classification

### Legend
- **CANONICAL** — Source of truth. Never modify without explicit approval. Immutable.
- **PRODUCTION** — Active in live trading path. Changes require causality test.
- **RESEARCH** — Used for backtesting/analysis. Not in live path. Safe to archive.
- **LEGACY** — Dead code. Not imported by anything active. Safe to archive.
- **EXPERIMENTAL** — In transition. May become production or may be archived.

---

### 3.1 CANONICAL (Immutable — Never Change Without Approval)

| File | Lines | Purpose |
|------|-------|---------|
| `signals/breakout.py` | 103 | **Signal source of truth** — 5-bar swing + 14 ATR + SL×2.0 + RRR×3.5 |
| `signals/base.py` | ~40 | BaseSignal abstract class + SignalResult dataclass |
| `monitoring/canonical_identity.py` | 206 | **Identity definition** — documents params + absent features + population mismatch |
| `execution/shadow/safety.py` | ~150 | **3-layer hard guard** — MT5 patch + adapter patch + audit trail |
| `indicators/atr.py` | ~30 | ATR calculation |
| `indicators/swing.py` | ~60 | Swing high/low detection |
| `indicators/ema.py` | ~20 | EMA calculation |
| `indicators/adx.py` | ~40 | ADX calculation |
| `indicators/pip.py` | ~15 | Pip value calculation |
| `indicators/resampler.py` | ~30 | Timeframe resampling |
| `indicators/session.py` | ~40 | Session time filter |

### 3.2 PRODUCTION (Active in Live Trading Path)

| File | Lines | Purpose | Depends On |
|------|-------|---------|------------|
| `execution/shadow/signal_generator.py` | ~200 | Shadow signal generation with frozen params | breakout.py, safety.py |
| `execution/shadow/live_runner.py` | ~500 | Shadow runner — bar processing, kill switch, state | signal_generator, safety |
| `execution/shadow/kill_switch.py` | ~100 | File-based kill switch | — |
| `execution/shadow/state.py` | ~80 | Shadow state persistence | — |
| `execution/shadow/health.py` | ~60 | Shadow health monitoring | — |
| `execution/shadow/logger.py` | ~80 | Shadow structured logging | — |
| `execution/shadow/live_adapter.py` | ~180 | Read-only market data adapter | data/loader |
| `execution/shadow/live_executor.py` | ~200 | Trade execution via WineFlask | contracts, health, kill_switch |
| `execution/shadow/wine_flask_adapter.py` | ~150 | WineFlask bridge adapter | mt5_client |
| `execution/s8_runtime.py` | ~500 | DRY_RUN/EXPERIMENTAL_LIVE runtime | adapter, orchestration |
| `execution/orchestration.py` | ~400 | 10-layer defense-in-depth | contracts, risk_guard |
| `execution/risk_guard.py` | ~300 | 7-gate risk guard | contracts, position_sizer, circuit_breakers |
| `execution/prop_firm_guard.py` | ~200 | +4 prop firm gates | — |
| `execution/mt5_adapter.py` | ~300 | MT5 execution adapter | adapter, contracts, mt5_client |
| `execution/mt5_client.py` | ~200 | MT5 bridge HTTP client | — |
| `execution/contracts.py` | ~150 | TradeIntent, RiskDecision, OrderRequest, ExecutionResult | — |
| `execution/adapter.py` | ~100 | BaseExecutionAdapter | contracts |
| `execution/base.py` | ~80 | BaseExecutor, OrderResult | — |
| `execution/data_feed.py` | ~300 | MT5 data feed polling | mt5_client, contracts |
| `execution/health_monitor.py` | ~200 | Infrastructure health monitoring | mt5_client, trade_logger |
| `execution/trade_logger.py` | ~200 | Append-only structured trade log | — |
| `execution/protection.py` | ~100 | Legacy protection (unused, kept for compat) | — |
| `execution/s7_engine.py` | ~300 | S7 engine (legacy, kept for compat) | adapter, orchestration |
| `risk/circuit_breakers.py` | ~400 | 6 circuit breakers (WinRate, DD, PF, Slippage, Correlation, Gap) | — |
| `portfolio/position_sizer.py` | ~100 | Position sizing calculations | — |
| `data/loader.py` | ~150 | Data loading (OHLCV from MT5) | config/settings |
| `data/acquisition.py` | ~80 | Data acquisition utilities | — |
| `notifications/bus.py` | ~60 | EventBus | — |
| `notifications/channels.py` | ~40 | Notification channel base | — |
| `notifications/policy.py` | ~80 | Notification policy | — |
| `notifications/dedup.py` | ~40 | Deduplication | — |
| `notifications/events.py` | ~30 | Event types | — |
| `notifications/wiring.py` | ~50 | Notification wiring | — |
| `notifications/signal_notifier.py` | ~80 | Telegram signal alerts | bus, policy |
| `notifications/telegram_bot.py` | ~100 | Telegram bot integration | — |
| `monitoring/server.py` | ~200 | Monitoring HTTP server | — |
| `monitoring/models.py` | ~80 | Monitoring data models | — |
| `monitoring/health_collector.py` | ~100 | Health data collection | — |
| `monitoring/latency_probe.py` | ~60 | Latency measurement | — |
| `monitoring/slippage.py` | ~60 | Slippage tracking | — |
| `monitoring/spread_collector.py` | ~60 | Spread data collection | — |
| `monitoring/percentiles.py` | ~40 | Percentile calculations | — |
| `monitoring/equity_tracker.py` | ~80 | Equity curve tracking | — |
| `monitoring/decision.py` | ~60 | Decision logging | — |
| `monitoring/data_schema.py` | ~80 | Data schema definitions | — |
| `monitoring/models.py` | ~80 | Monitoring models | — |
| `config/experiment.py` | 190 | Experiment identity + config hash | — |
| `config/policies/` | ~300 | Policy loader + models + validator | — |
| `utils/logging.py` | ~40 | Structured logging | — |
| `utils/time_utils.py` | ~30 | Time utilities | config/settings |
| `costs/model.py` | 111 | Cost model (uses zscore.contracts) | zscore.contracts |
| `data_validation/validate.py` | 78 | Data validation (uses zscore.contracts) | zscore.contracts |
| `__init__.py` | 10 | Package root | config/settings |

### 3.3 ZSCORE PACKAGE (Shared Contracts — Mixed Use)

The `zscore/` package is used by BOTH production and research. Production only uses **contracts** (data classes), not the zscore engine.

| File | Lines | Used By Production? | Used By Research? |
|------|-------|--------------------|--------------------|
| `zscore/contracts.py` | ~200 | ✅ costs/model.py, data_validation/validate.py | ✅ All research scripts |
| `zscore/features.py` | ~100 | ❌ | ✅ tests, research |
| `zscore/regime.py` | ~150 | ❌ | ✅ tests, research |
| `zscore/signals.py` | ~100 | ❌ | ✅ tests |
| `zscore/zscore.py` | ~200 | ❌ | ✅ All research scripts |

**Decision needed**: Extract `zscore/contracts.py` into a standalone `contracts/` package, or keep as-is?

### 3.4 RESEARCH (Backtesting/Analysis — Not in Live Path)

| File | Lines | Purpose |
|------|-------|---------|
| `engines/backtest_engine.py` | ~200 | Backtest engine |
| `engines/base_engine.py` | ~100 | Base engine class |
| `engines/regime_backtest_engine.py` | ~200 | Regime-aware backtest |
| `backtest/metrics.py` | ~150 | Backtest metrics calculation |
| `backtest/comparison.py` | ~100 | Strategy comparison (imports regime/) |
| `regime/base.py` | ~60 | Regime detector base |
| `regime/adx_regime.py` | ~80 | ADX regime detector |
| `regime/hybrid.py` | ~100 | Hybrid regime detector |
| `regime/labels.py` | ~40 | Regime label definitions |
| `regime/tabfm/` | ~500 | TabFM ML regime model |
| `research/experiment.py` | ~100 | Research experiment tracking |
| `research/phase3_research.py` | ~200 | Phase 3 research (imports zscore) |
| `analytics/research_analysis.py` | ~100 | Research analysis utilities |
| `knowledge/experiment_tracker.py` | ~150 | Experiment tracking |

### 3.5 LEGACY (Dead Code — Safe to Archive)

| File | Lines | Why Dead |
|------|-------|----------|
| Root `config.py` | 100 | Only imported by root-level legacy files + scripts. NOT by production. |
| Root `logger.py` | 20 | Shadow runner uses its own ShadowLogger. Not imported by production. |
| Root `risk_manager.py` | 80 | Only imported by root-level legacy files. |
| Root `currency_strength.py` | 300 | Only imported by root-level legacy files. |
| Root `forensic_analysis.py` | 800 | Standalone analysis script. |
| Root `phase2_forensic_analysis.py` | 600 | Phase 2 analysis. |
| Root `phase3_forensic_analysis.py` | 1000 | Phase 3 analysis. |
| Root `phase4_forensic_analysis.py` | 1400 | Phase 4 analysis. |
| Root `phase5_forensic_analysis.py` | 1400 | Phase 5 analysis. |
| Root `debug_breakout.py` | 120 | Debug script. |
| Root `backtest_hybrid_opt.py` | 1200 | MR+TF backtest (NOT breakout). |
| Root `backtest_portfolio.py` | 1300 | Portfolio backtest (MR+TF). |
| Root `backtest_gft_crisis.py` | 300 | GFT crisis backtest. |
| Root `oos_validation.py` | 300 | OOS validation (MR+TF). |
| Root `zero_costs_test.py` | 80 | Zero-cost test. |
| `config/settings.py` | 495 | **CONFLICTING** config (ATR=3.0, RRR=2.0). Used by structured_entry.py only. |
| `signals/structured_entry.py` | 113 | MR+TF signal (NOT breakout). Imports wrong config. |

### 3.6 SCRIPTS (Research Phase Scripts — 44 Files)

All scripts in `scripts/` are research phase scripts. None are imported by production code.

**Phase 3–12 Research Scripts (18 files):**
- `phase7_oos_validation.py` through `phase12_regime_validation.py`

**S0–S6 Breakout Research Scripts (12 files):**
- `phase_s0_breakout_reassessment.py` through `phase_s6_adaptive_risk.py`

**Specialized Analysis Scripts (8 files):**
- `cross_timeframe_agreement.py`, `elapsed_time_analysis.py`, `ev_risk_analysis.py`, `exit_forensics.py`, `exit_surface.py`, `temporal_stability_analysis.py`, `signal_discovery.py`, `zscore_mr_backtest.py`

**Operational Scripts (6 files):**
- `run_live_shadow.py`, `run_shadow.py`, `run_live_executor.py`, `s7_dry_run.py`, `s7_dry_run_standalone.py`, `s8_runner.py`

**Build/Report Scripts (4 files):**
- `build_ev_risk_report.py`, `build_stability_reports.py`, `check_shadow_health.py`, `validate_shadow_fidelity.py`

**Data Scripts (2 files):**
- `download_fx_data.py`, `compare_timeframes.py`, `cost_sensitivity.py`

**Other Research (2 files):**
- `phase_hg1_holy_grail.py`, `phase_m1_carry.py`, `phase_m1_structural_discovery.py`

### 3.7 TESTS (72 Files)

| Directory | Files | Purpose |
|-----------|-------|---------|
| `tests/` (root) | 34 | Production + integration tests |
| `tests/regression/` | 26 | Regression tests for each research phase |
| `tests/smoke/` | 1 | End-to-end smoke test |
| `tests/unit/` | 5 | Unit tests for zscore package |
| `tests/integration/` | 0 (empty) | — |

**Known Failures (22):**
- `test_mt5_adapter.py` — 16 failures (mock broker tests)
- `test_s7_engine.py` — 3 failures
- `test_risk_guard.py` — 1 failure
- `test_signal_discovery.py` — 1 failure
- `test_s85_remediation.py` — 1 failure

### 3.8 DASHBOARD (TypeScript/Next.js)

| File | Purpose |
|------|---------|
| `dashboard/app/admin/page.tsx` | Admin dashboard (30s data poll) |
| `dashboard/app/page.tsx` | User dashboard |
| `dashboard/app/api/health/route.ts` | Health API |
| `dashboard/app/api/auth/login/route.ts` | Auth (`.trim()` fix applied) |
| `dashboard/lib/auth.ts` | JWT + bcrypt |
| `dashboard/lib/db.ts` | sql.js SQLite |
| `dashboard/components/*.tsx` | Dashboard UI components |

---

## 4. Canonical Strategy Audit

### 4.1 Source of Truth

The canonical strategy is defined in `signals/breakout.py`:

```python
# signals/breakout.py — THE source of truth
RESEARCH_DEFAULTS = {
    "lookback": 5,        # 5-bar swing detection
    "atr_period": 14,     # 14-period ATR
    "atr_sl_multiplier": 2.0,  # Stop loss = 2.0 × ATR
    "rrr": 3.5,           # Take profit = 3.5 × SL distance
}
```

**Explicitly ABSENT from canonical strategy:**
- Breakeven logic
- Max hold days
- Trailing stop
- Session filter
- Macro EMA filter
- News filter
- Regime filter
- Correlation filter

### 4.2 Three-Config Conflict Matrix

| Parameter | `breakout.py` (Canonical) | `experiment.py` (Exp) | `settings.py` (Legacy) | Root `config.py` (Dead) |
|-----------|--------------------------|----------------------|----------------------|------------------------|
| `atr_sl_multiplier` | **2.0** | 2.0 ✅ | 3.0 ❌ | 2.0 ✅ |
| `rrr` | **3.5** | 3.5 ✅ | 2.0 ❌ | 3.5 ✅ |
| `atr_period` | **14** | 14 ✅ | 14 ✅ | 14 ✅ |
| `lookback` | **5** | 5 ✅ | — | — |
| `breakeven_ratio` | **ABSENT** | 0.8 ⚠️ | 1.5 ⚠️ | 0.8 ⚠️ |
| `max_hold_days` | **ABSENT** | 7 ⚠️ | — | 7 ⚠️ |
| `trailing_stop` | **ABSENT** | True ⚠️ | — | True ⚠️ |
| `correlation` | **ABSENT** | — | enabled ⚠️ | 0.50 ⚠️ |
| `session_filter` | **ABSENT** | — | — | — |

### 4.3 Who Uses What

| Consumer | Config Source | Parameters Used | Correct? |
|----------|--------------|-----------------|----------|
| `signals/breakout.py` | Own RESEARCH_DEFAULTS | 2.0/3.5 | ✅ |
| `signals/structured_entry.py` | `config/settings.py` | 3.0/2.0 | ❌ **WRONG** |
| `execution/shadow/signal_generator.py` | Own frozen dict | 2.0/3.5 + BE/MH | ⚠️ Has extras |
| `config/experiment.py` | Own StrategyIdentity | 2.0/3.5 + BE/MH | ⚠️ Has extras |
| `backtest_hybrid_opt.py` | Root `config.py` | 2.0/3.5 + correlation | ❌ MR+TF |

### 4.4 Research Population Mismatch

All known research populations (S0, S5.5, S6A) include breakeven and max_hold in their backtests, but the deployed code does NOT have these features. **No research population exactly matches the deployed strategy.**

| Population | Trades | WR | PF | Has BE/MH | Matches Deployed? |
|-----------|--------|-----|-----|-----------|-------------------|
| S0 | 1,002 | 73.0% | 5.32 | Yes | ❌ NO |
| S5.5 | 15,321 | 35.9% | 2.14 | Yes | ❌ NO |
| S6A | 15,321 | 35.7% | 2.01 | Yes | ❌ NO |

---

## 5. Dependency Violations

### 5.1 Critical Violations

| Violation | Severity | Details |
|-----------|----------|---------|
| `signals/structured_entry.py` imports `ATR_SL_MULTIPLIER=3.0, RRR=2.0` from `config/settings.py` | **HIGH** | Uses wrong parameters (canonical is 2.0/3.5) |
| `signals/__init__.py` exports `StructuredEntrySignal` alongside `BreakoutSignal` | **MEDIUM** | MR+TF signal exported as if it were canonical |
| `costs/model.py` imports from `zscore.contracts` | **MEDIUM** | Production depends on zscore package for contracts only |
| `data_validation/validate.py` imports from `zscore.contracts` | **MEDIUM** | Production depends on zscore package for contracts only |

### 5.2 Structural Violations

| Violation | Severity | Details |
|-----------|----------|---------|
| Root `config.py` shadows `config/` package in Python path | **MEDIUM** | `import config` could resolve to either depending on sys.path |
| `config/__init__.py` re-exports from `nestquant.config.settings` | **LOW** | Creates confusion about which config is active |
| 16 root-level .py files create namespace pollution | **LOW** | `config.py`, `logger.py`, `risk_manager.py` etc. |
| `signals/__init__.py` exports both BreakoutSignal and StructuredEntrySignal | **MEDIUM** | Suggests both are equally valid |

### 5.3 Research → Production Leaks (None Found ✅)

No research code is imported by production execution path. This is clean.

### 5.4 Production → Research Leaks (None Found ✅)

No production code imports from `regime/`, `engines/`, `backtest/`, `research/`, or `analytics/`. This is clean.

---

## 6. Target Architecture

### 6.1 Proposed Directory Structure

```
that/
├── signals/
│   ├── __init__.py          # ONLY exports BreakoutSignal
│   ├── base.py              # BaseSignal, SignalResult (CANONICAL)
│   └── breakout.py          # CANONICAL signal (NEVER CHANGE)
│
├── execution/
│   ├── shadow/              # Shadow trading pipeline (PRODUCTION)
│   │   ├── signal_generator.py
│   │   ├── live_runner.py
│   │   ├── safety.py        # CANONICAL hard guard
│   │   ├── kill_switch.py
│   │   ├── state.py
│   │   ├── health.py
│   │   ├── logger.py
│   │   ├── live_adapter.py
│   │   ├── live_executor.py
│   │   └── wine_flask_adapter.py
│   ├── s8_runtime.py        # DRY_RUN/LIVE runtime
│   ├── orchestration.py     # 10-layer defense
│   ├── risk_guard.py        # 7-gate risk
│   ├── prop_firm_guard.py   # +4 prop gates
│   ├── mt5_adapter.py       # MT5 adapter
│   ├── mt5_client.py        # Bridge HTTP client
│   ├── contracts.py         # Data contracts
│   ├── adapter.py           # Base adapter
│   ├── base.py              # Base executor
│   ├── data_feed.py         # Data feed
│   ├── health_monitor.py    # Health monitoring
│   ├── trade_logger.py      # Trade logging
│   └── protection.py        # Legacy protection
│
├── risk/
│   └── circuit_breakers.py  # 6 breakers
│
├── portfolio/
│   └── position_sizer.py    # Position sizing
│
├── indicators/              # Technical indicators (CANONICAL)
│   ├── atr.py
│   ├── swing.py
│   ├── ema.py
│   ├── adx.py
│   ├── pip.py
│   ├── resampler.py
│   └── session.py
│
├── monitoring/              # Dashboard data + monitoring
│   ├── canonical_identity.py  # CANONICAL identity
│   ├── server.py
│   ├── models.py
│   ├── health_collector.py
│   ├── latency_probe.py
│   ├── slippage.py
│   ├── spread_collector.py
│   ├── percentiles.py
│   ├── equity_tracker.py
│   ├── decision.py
│   ├── data_schema.py
│   └── architecture.py
│
├── notifications/           # Telegram + EventBus
│   ├── bus.py
│   ├── channels.py
│   ├── policy.py
│   ├── dedup.py
│   ├── events.py
│   ├── wiring.py
│   ├── signal_notifier.py
│   └── telegram_bot.py
│
├── data/                    # Data loading
│   ├── loader.py
│   └── acquisition.py
│
├── config/
│   ├── __init__.py          # Clean re-exports
│   ├── experiment.py        # Experiment identity
│   └── policies/            # Policy engine
│
├── costs/
│   └── model.py             # Cost model (needs contracts extraction)
│
├── data_validation/
│   └── validate.py          # Data validation (needs contracts extraction)
│
├── utils/
│   ├── logging.py
│   └── time_utils.py
│
├── contracts/               # NEW: Extracted from zscore/
│   ├── __init__.py
│   └── market.py            # MarketData, CostModel, CostBreakdown, etc.
│
├── tests/                   # Tests (72 files)
│   ├── test_dashboard_data_dynamic.py
│   ├── test_*.py
│   ├── regression/
│   ├── smoke/
│   └── unit/
│
├── scripts/                 # ARCHIVED: Research scripts (44 files)
│   └── archived/            # Moved here during migration
│
├── dashboard/               # Next.js dashboard (TypeScript)
│
├── archive/                 # NEW: All legacy/research code
│   ├── legacy/              # Root-level dead .py files
│   │   ├── config.py
│   │   ├── logger.py
│   │   ├── risk_manager.py
│   │   ├── currency_strength.py
│   │   ├── forensic_analysis.py
│   │   ├── phase[2-5]_forensic_analysis.py
│   │   ├── debug_breakout.py
│   │   ├── backtest_hybrid_opt.py
│   │   ├── backtest_portfolio.py
│   │   ├── backtest_gft_crisis.py
│   │   ├── oos_validation.py
│   │   └── zero_costs_test.py
│   ├── research/             # Research packages
│   │   ├── regime/
│   │   ├── zscore/
│   │   ├── engines/
│   │   ├── backtest/
│   │   ├── research/
│   │   ├── analytics/
│   │   └── knowledge/
│   ├── config_settings.py    # config/settings.py (conflicting ATR/RRR)
│   ├── structured_entry.py   # signals/structured_entry.py (MR+TF)
│   └── scripts/              # All 44 research scripts
│
├── __init__.py              # Package root
└── config.py                # ARCHIVED (was root config.py)
```

### 6.2 Contracts Extraction Plan

The `zscore/contracts.py` contains data classes used by production (`costs/model.py`, `data_validation/validate.py`). Extract into standalone `contracts/` package:

```python
# contracts/market.py — Extracted from zscore/contracts.py
# Contains: MarketData, ValidatedMarketData, ValidationReport,
#           CostModel, CostBreakdown, FeatureSet, RegimeState,
#           Signal, ZScoreObservation, InstrumentMetadata
```

Then update:
- `costs/model.py`: `from zscore.contracts import` → `from contracts.market import`
- `data_validation/validate.py`: `from zscore.contracts import` → `from contracts.market import`
- `tests/conftest.py`: `from zscore.contracts import` → `from contracts.market import`
- `tests/unit/test_signals.py`: `from zscore.contracts import` → `from contracts.market import`
- `tests/smoke/test_end_to_end.py`: `from zscore.contracts import` → `from contracts.market import`

---

## 7. Migration Plan (Phases A–H)

### Phase A: Extract Contracts (Low Risk)
**Goal**: Break production dependency on `zscore/` package.

1. Create `contracts/__init__.py` and `contracts/market.py`
2. Copy data classes from `zscore/contracts.py` → `contracts/market.py`
3. Update 5 production/test files to import from `contracts.market`
4. Keep `zscore/contracts.py` as a re-export shim (backward compat for archived research)
5. Run tests: `python -m pytest tests/ -x`
6. **Commit**: `refactor(contracts): extract market contracts from zscore package`

### Phase B: Archive Root-Level Legacy (Low Risk)
**Goal**: Remove 16 dead .py files from root directory.

1. Create `archive/legacy/` directory
2. Move: `config.py`, `logger.py`, `risk_manager.py`, `currency_strength.py`, `forensic_analysis.py`, `phase[2-5]_forensic_analysis.py`, `debug_breakout.py`, `backtest_hybrid_opt.py`, `backtest_portfolio.py`, `backtest_gft_crisis.py`, `oos_validation.py`, `zero_costs_test.py`
3. Verify no production imports break: `python -c "from nestquant.execution.shadow.live_runner import ShadowLiveRunner"`
4. Run tests: `python -m pytest tests/ -x`
5. **Commit**: `refactor(archive): move 16 legacy root-level files to archive/legacy/`

### Phase C: Archive Research Packages (Medium Risk)
**Goal**: Move non-production packages to `archive/research/`.

1. Create `archive/research/` directory
2. Move: `regime/`, `engines/`, `backtest/`, `research/`, `analytics/`, `knowledge/`
3. Update `tests/regression/` test imports to use archive paths (or skip)
4. Verify production imports: `python -c "from nestquant.execution.shadow.live_runner import ShadowLiveRunner"`
5. Run production tests only: `python -m pytest tests/ -x --ignore=tests/regression`
6. **Commit**: `refactor(archive): move regime/engines/backtest/research/analytics/knowledge to archive/research/`

### Phase D: Archive MR+TF Signal + Conflicting Config (Medium Risk)
**Goal**: Remove structured_entry.py and config/settings.py from production.

1. Create `archive/legacy/` additions
2. Move: `signals/structured_entry.py` → `archive/legacy/structured_entry.py`
3. Move: `config/settings.py` → `archive/legacy/config_settings.py`
4. Update `signals/__init__.py` to remove `StructuredEntrySignal` export
5. Update `config/__init__.py` to NOT re-export from settings
6. Verify: `python -c "from nestquant.signals.breakout import BreakoutSignal"`
7. Run tests: `python -m pytest tests/ -x`
8. **Commit**: `refactor(archive): remove MR+TF structured_entry and conflicting config/settings`

### Phase E: Archive Research Scripts (Low Risk)
**Goal**: Move 44 research scripts to archive.

1. Create `archive/scripts/` directory
2. Move all `scripts/*.py` → `archive/scripts/`
3. No production imports affected
4. **Commit**: `refactor(archive): move 44 research scripts to archive/scripts/`

### Phase F: Clean Config Package (Medium Risk)
**Goal**: Simplify config/ to only what production needs.

1. Update `config/__init__.py` to export only:
   - `ExperimentConfig`, `StrategyIdentity`, `RiskIdentity`, `UniverseIdentity`
   - `get_config()` (from settings, if still needed)
2. Remove legacy re-exports (`ALL_PAIRS`, `TRADEABLE_PAIRS`, etc.)
3. Verify: `python -c "from nestquant.config.experiment import ExperimentConfig"`
4. Run tests: `python -m pytest tests/ -x`
5. **Commit**: `refactor(config): clean config package to production-only exports`

### Phase G: Fix Structured Entry (If Keeping)
**Goal**: If structured_entry.py is needed, fix its config dependency.

1. Update `signals/structured_entry.py` to use canonical params (2.0/3.5) instead of `config/settings.py`
2. Or remove it entirely if not needed
3. **Commit**: `fix(signals): align structured_entry with canonical parameters`

### Phase H: Verification + Documentation (Low Risk)
**Goal**: Final verification and update documentation.

1. Run full test suite: `python -m pytest tests/ -v`
2. Verify all production imports: `python -c "from nestquant.execution.shadow.live_runner import ShadowLiveRunner"`
3. Update `NESTQUANT_TECHNICAL_SYSTEM_REPORT_PRE_LIVE.md`
4. Update `CODEBASE_MANIFEST.md` with final state
5. **Commit**: `docs(audit): finalize codebase restructuring documentation`

---

## 8. Risk Assessment

### 8.1 What Can Break

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Extracting contracts breaks zscore research tests | Medium | Low | Keep re-export shim in zscore/contracts.py |
| Archiving regime/ breaks regression tests | High | Low | Skip regression tests or update imports |
| Removing config/settings.py breaks structured_entry.py | High | Low | Archive structured_entry.py too |
| Python path confusion between root config.py and config/ package | Medium | Medium | Archive root config.py first |
| Dashboard imports break | Low | High | Dashboard is TypeScript, unaffected |
| Shadow runner imports break | Low | Critical | Test after each phase |
| MT5 bridge connection breaks | Low | Critical | No bridge code changes |

### 8.2 What Cannot Break

- `signals/breakout.py` — CANONICAL, never modify
- `execution/shadow/safety.py` — CANONICAL hard guard
- `monitoring/canonical_identity.py` — CANONICAL identity
- `execution/shadow/live_runner.py` — Active production runner
- `execution/shadow/signal_generator.py` — Active signal generation
- `execution/s8_runtime.py` — Active DRY_RUN/LIVE runtime
- `execution/orchestration.py` — Active defense-in-depth
- `execution/risk_guard.py` — Active risk guard
- `execution/mt5_adapter.py` — Active MT5 adapter
- `execution/mt5_client.py` — Active bridge client
- Dashboard TypeScript code — Separate stack

### 8.3 Rollback Plan

Each phase is a separate Git commit. If anything breaks:
```bash
git revert <commit-hash>
```

---

## 9. Immutable Files

These files must NEVER be modified without explicit user approval and a documented reason:

| File | Reason |
|------|--------|
| `signals/breakout.py` | Canonical signal source of truth |
| `signals/base.py` | Base class for all signals |
| `execution/shadow/safety.py` | 3-layer hard guard — safety-critical |
| `monitoring/canonical_identity.py` | Identity definition — documents what IS and ISN'T deployed |
| `risk/circuit_breakers.py` | Circuit breakers — safety-critical |
| `execution/contracts.py` | Data contracts — shared interface |
| `config/experiment.py` | Experiment identity — reproducibility |
| `execution/shadow/kill_switch.py` | Kill switch — safety-critical |
| `.env` / `.env.production` | Credentials (never commit) |
| `users.json` | Dashboard credentials (never commit) |

---

## 10. Git Strategy

### Branch Strategy
```
master (current) ──► audit/restructure (feature branch) ──► master (merge after review)
```

### Commit Sequence
```
Phase A: refactor(contracts): extract market contracts from zscore package
Phase B: refactor(archive): move 16 legacy root-level files to archive/legacy/
Phase C: refactor(archive): move regime/engines/backtest/research to archive/research/
Phase D: refactor(archive): remove MR+TF structured_entry and conflicting config
Phase E: refactor(archive): move 44 research scripts to archive/scripts/
Phase F: refactor(config): clean config package to production-only exports
Phase G: fix(signals): align structured_entry with canonical parameters (if kept)
Phase H: docs(audit): finalize codebase restructuring documentation
```

### Pre-Merge Checklist
- [ ] All production tests pass: `python -m pytest tests/ -x --ignore=tests/regression`
- [ ] Shadow runner imports cleanly
- [ ] Dashboard unaffected (TypeScript)
- [ ] MT5 bridge connection verified
- [ ] No secrets in commits
- [ ] User review and approval

---

## Appendix A: Complete File Inventory

### Root-Level Files (16)
| File | Size | Classification |
|------|------|---------------|
| `__init__.py` | 224B | PRODUCTION |
| `config.py` | 2.9KB | LEGACY |
| `logger.py` | 865B | LEGACY |
| `risk_manager.py` | 2.6KB | LEGACY |
| `currency_strength.py` | 12KB | LEGACY |
| `forensic_analysis.py` | 31KB | LEGACY |
| `phase2_forensic_analysis.py` | 23KB | LEGACY |
| `phase3_forensic_analysis.py` | 39KB | LEGACY |
| `phase4_forensic_analysis.py` | 56KB | LEGACY |
| `phase5_forensic_analysis.py` | 54KB | LEGACY |
| `debug_breakout.py` | 4.8KB | LEGACY |
| `backtest_hybrid_opt.py` | 49KB | LEGACY |
| `backtest_portfolio.py` | 52KB | LEGACY |
| `backtest_gft_crisis.py` | 11KB | LEGACY |
| `oos_validation.py` | 11KB | LEGACY |
| `zero_costs_test.py` | 2.9KB | LEGACY |

### Python Packages (31)
| Package | Files | Classification |
|---------|-------|---------------|
| `signals/` | 3 | CANONICAL + LEGACY (structured_entry) |
| `execution/` | 14 | PRODUCTION |
| `execution/shadow/` | 10 | PRODUCTION |
| `risk/` | 1 | PRODUCTION |
| `portfolio/` | 1 | PRODUCTION |
| `indicators/` | 7 | CANONICAL |
| `monitoring/` | 13 | PRODUCTION |
| `notifications/` | 8 | PRODUCTION |
| `data/` | 3 | PRODUCTION |
| `config/` | 1 + policies/3 | PRODUCTION |
| `costs/` | 1 | PRODUCTION |
| `data_validation/` | 1 | PRODUCTION |
| `utils/` | 2 | PRODUCTION |
| `zscore/` | 5 | SHARED (contracts = production, rest = research) |
| `regime/` | 5 + tabfm/5 | RESEARCH |
| `engines/` | 3 | RESEARCH |
| `backtest/` | 2 | RESEARCH |
| `research/` | 2 | RESEARCH |
| `analytics/` | 1 | RESEARCH |
| `knowledge/` | 1 | RESEARCH |

---

*This audit is a READ-ONLY analysis. No code has been modified. All proposed changes require user review and approval before execution.*
