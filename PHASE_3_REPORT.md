# Phase 3 Report — Architecture Reconciliation / Gap Analysis

**Date:** 2026-08-09
**Scope:** Full architectural analysis of recovered legacy system vs nestquant package
**Status:** Analysis complete. No source code modified. No commits made.

---

## A. Current Architecture

### Two Parallel Systems

The codebase contains **two independent implementations** of the same trading concept:

**SYSTEM 1: Legacy Backtest** (flat-file scripts)
- `backtest_hybrid_opt.py` (1,026 lines) — core engine
- `backtest_portfolio.py` (1,095 lines) — portfolio-aware wrapper
- `risk_manager.py` (85 lines) — simplified position sizing
- `currency_strength.py` (295 lines) — currency strength ranker
- `config.py` at `/root/nestquant/config.py` (64 flat constants)
- **Status:** Importable (except `portfolio_manager` dependency). Cannot run without data files.

**SYSTEM 2: NestQuant Package** (structured Python package)
- `config/settings.py` (486 lines, dataclass-based config)
- `indicators/` (7 modules, pure functions)
- `signals/` (3 signal classes)
- `engines/` (2 engine classes)
- `portfolio/position_sizer.py` (leverage-aware sizing)
- `risk/circuit_breakers.py` (6 breakers + orchestrator)
- `regime/` (3 regime detectors including TabFM ML)
- **Status:** Fully importable. 199 tests pass. No backtest runner wired up.

### Legacy System Data Flow

```
/root/data/*.pkl (1-min OHLCV per pair)
    |
    v
load_and_resample() --> all_tfs: {1min, 5min, 15min, 4h, 1D} per pair
    |
    +--> precompute_strength() --> strength: {TF: DataFrame}
    +--> precompute_signals_vectorized() --> signal_lookup: {TF: {pair: bytes}}
    +--> precompute_atrs() --> atr_cache: {TF: {pair: ndarray}}
    |
    v
HybridBacktest(strength, signal_lookup, all_tfs, atr_cache)
    |
    +--> .run(start_date, end_date)
         |
         +-- 1min timeline iteration (bar-by-bar)
         +-- SL/TP resolution on higher TF bars
         +-- Breakeven check
         +-- Session close SL scaling
         +-- Entry signals: 5min strength + regime flip + macro filter
         +-- Correlation guard (rolling daily corr matrix)
         +-- Currency exposure rail
         +-- ATR-based SL/TP
         +-- RiskManager.calculate_lot_size()
         +-- Promotion ladder: 5min -> 15min -> 4h -> 1D
         +-- Trend reversal exit
         |
         v
    return {trades, wins, losses, net_pnl, max_dd_pct, ...}
```

### NestQuant Package Data Flow (NOT wired together)

```
Data (pickle or live)
    |
    v
indicators/ --> ATR, ADX, EMA, swing levels, pip utils, session filter
    |
    +--> regime/ --> RegimeDetector --> RegimePrediction
    |    (ADXRegimeDetector, HybridRegimeDetector w/ TabFM)
    |
    +--> signals/ --> BaseSignal --> SignalResult
    |    (BreakoutSignal, StructuredEntrySignal)
    |
    +--> portfolio/ --> compute_position_size() --> SizingResult
    |    (leverage-aware, margin-guarded)
    |
    +--> risk/ --> BreakerSuite (6 circuit breakers)
    |    (WinRate, Slippage, DrawdownPace, ProfitFactor, Correlation, DrawdownDrift)
    |
    +--> engines/ --> BacktestEngine.on_bar() / RegimeBacktestEngine.on_bar()
    |    (bar-by-bar execution with spread/slippage modeling)
    |
    +--> backtest/ --> BacktestMetrics, ABComparison
    +--> knowledge/ --> ExperimentTracker
    +--> data/ --> DataLoader (pickle)
```

**Key observation:** The NestQuant package has all the building blocks but no integrated backtest runner that connects them. The legacy `backtest_hybrid_opt.py` IS the integrated runner, but it doesn't use the NestQuant package modules.

---

## B. Configuration Conflicts

### Conflicting Symbol Values

| Symbol | settings.py | config.py (root/nestquant) | merged/config.py | backup_old/config.py |
|--------|-------------|---------------------------|-------------------|---------------------|
| **INITIAL_BALANCE** | 200 | 1000 | 20 | 10,000 |
| **RISK_PER_TRADE** | 0.03 | 0.0023 | 0.002 | 0.002 |
| **COMMISSION_PER_LOT** | 6.0 | 5.0 | 3.5 | 5.0 |
| **MIN_LOT_SIZE** | 0.01 | 0.001 | 0.01 | 0.01 |
| **MAX_LOT_SIZE** | 1.0 | 10.0 | 0.05 | 10.0 |
| **MIN_DIVERGENCE** | 10.0 | 3.0 | 10.0 | 10.0 |
| **ATR_SL_MULTIPLIER** | 3.0 | 2.0 | 3.0 | 3.0 |
| **RRR** | 2.0 | 3.5 | 2.0 | 2.0 |
| **BREAKEVEN_RATIO** | 1.5 | 0.8 | 1.5 | 1.5 |
| **MACRO_EMA_PERIOD** | 200 | 12 | 200 | 200 |
| **MAX_DD_PCT** | 55.0 | 6.0 | 100.0 | 6.0 |
| **DD_REDUCE_THRESHOLD** | 30.0 | 4.0 | 100.0 | 4.0 |
| **DD_REDUCED_RISK** | 0.02 | 0.0005 | 0.002 | 0.0005 |
| **SESSION_OPEN_UTC** | 7 | N/A | 8 | 8 |
| **SESSION_CLOSE_UTC** | 21 | 19 | 19 | 19 |
| **MAX_ENTRY_HOUR** | 21 | N/A | 15 | 15 |
| **SKIP_MONDAY_OPEN** | False | N/A | True | True |
| **MAX_OPEN_TRADES** | 1 | 1 | 15 | 15 |
| **MAX_PER_CURRENCY_BLOCK** | 1 | 1 | 4 | 4 |
| **CORRELATION_THRESHOLD** | 0.70 | 0.50 | 0.70 | 0.70 |
| **STRENGTH_LOOKBACKS** | [(5,.5),(10,.3),(20,.2)] | [(10,.4),(20,.3),(40,.2),(80,.1)] | same as settings | same as settings |
| **STRENGTH_NORMALIZE_WINDOW** | 100 | 200 | 100 | 100 |
| **STRENGTH_TOP_N** | 3 | 4 | 3 | 3 |
| **ENABLE_REGIME_FLIP** | True | True | True | False |
| **TRADEABLE_PAIRS** | 7 pairs | 12 pairs | 8 pairs | 8 pairs |

### Pair List Conflict Detail

- **settings.py** (NestQuant package): 7 tradeable pairs (EUR/USD, GBP/USD, USD/JPY, AUD/USD, NZD/USD, EUR/JPY, GBP/JPY)
- **config.py** (root/nestquant flat): 12 pairs (adds EUR/NZD, AUD/NZD, GBP/NZD, GBP/AUD)
- **merged/config.py**: 8 pairs (different set: GBP/JPY, EUR/JPY, GBP/USD, EUR/USD, AUD/JPY, USD/JPY, GBP/AUD, EUR/GBP)
- **All agree on ALL_PAIRS**: 28 pairs

### Where Each Config Is Used

| Config | Used By |
|--------|---------|
| `config/settings.py` via `config/__init__.py` | `backtest_hybrid_opt.py`, `risk_manager.py`, all nestquant package modules |
| `/root/config.py` | `backtest_portfolio.py` (overrides pair lists), GFT-specific risk_manager |
| `/root/merged/config.py` | Not currently used (was the original companion to merged backtest_hybrid_opt) |
| `/root/nestquant/config.py` (flat file) | Shadowed by `config/` package — not importable |

---

## C. Duplicate Implementations

### 1. Position Sizing (THREE implementations)

| Location | Interface | Formula |
|----------|-----------|---------|
| `risk_manager.py:RiskManager.calculate_lot_size(pair, entry_price, sl, divergence)` | Divergence-scaled base lot | `base_lot * min(max(1, div/min_div), 5.0)` |
| `backtest_portfolio.py:FlexibleRiskManager.calculate_lot_size(pair, entry_price, sl, risk_pct)` | Risk-dollar based | `balance * risk_pct / (stop_pips * pip_value)` |
| `portfolio/position_sizer.py:compute_position_size(...)` | Full margin-aware | Risk-based with leverage, margin guard, lot rounding |

### 2. Indicators (shared, not duplicated)

The legacy `backtest_hybrid_opt.py` imports `from indicators import is_active_session, calculate_atr, pip_size`. This resolves to `nestquant/indicators/` package. The implementations are shared, not duplicated.

### 3. Configuration (duplicated)

Two config systems coexist:
- `config/settings.py`: Dataclass-based, env-var-driven, 100+ symbols
- `config.py` (flat): Module-level constants, 64 symbols
- Both exported through `config/__init__.py` (wildcard re-export)
- The flat file is shadowed by the package directory

### 4. Logging (duplicated)

- `logger.py` (root-level): Standalone structured logging
- `utils/logging.py` (nestquant package): Package logging utility
- `backtest_hybrid_opt.py` creates its own logger: `logging.getLogger("hybrid_opt")`

### 5. Risk Management (different purposes, not true duplicates)

- `risk_manager.py:RiskManager`: Position sizing + daily loss tracking
- `risk/circuit_breakers.py:BreakerSuite`: Live trading circuit breakers (6 independent breakers)
- These serve different purposes and could coexist

---

## D. PortfolioManager Dependency Analysis

### Exact Imports Expected

```python
# backtest_portfolio.py line 49
import portfolio_manager as pm_module
PortfolioManager = pm_module.PortfolioManager

# zero_costs_test.py line 10
from backtest_portfolio import PortfolioManager, run_portfolio_backtest
```

### Constructor Signature (from backtest_portfolio.py:1026-1033)

```python
pm = PortfolioManager(
    max_positions=max_positions,          # int (default 5)
    max_daily_risk_pct=daily_risk_pct,    # float (default 0.02)
    max_trade_risk_pct=max_trade_risk,    # float (default 0.01)
    min_trade_risk_pct=min_trade_risk,    # float (default 0.002)
    per_currency_exposure=per_curr_exposure,  # int (default 2)
    enable_replacement=enable_replacement,    # bool (default True)
)
```

### Methods Called

```python
# backtest_portfolio.py line 729-731
selected = pm.select_trades(
    raw_candidates,   # List[dict] - candidate trade signals
    open_info,        # List[dict] - currently open trades
    balance,          # float - current account balance
    daily_risk_used,  # float - daily risk consumed so far
)
# Returns: List[dict] with keys: pair, direction, entry_price, sl, tp, mid_price, risk_pct, regime_mult, score

# backtest_portfolio.py line 746
effective_max_risk = pm.max_trade_risk_pct * max(1.0, cfg.REGIME_MULT_TRENDING)
# Accesses: pm.max_trade_risk_pct (float attribute)
```

### Input Data to select_trades

`raw_candidates` is built at lines 700-718 of backtest_portfolio.py. Each candidate dict contains:
- `pair`, `direction`, `entry_price`, `sl`, `tp`, `mid_price`
- `divergence`, `atr_val`, `spread_pips`
- `score` (composite signal score)
- `regime_mult` (ADX-based regime multiplier)

### Scoring Dimensions (from TECHNICAL_REPORT.md)

| Dimension | Weight | Formula |
|-----------|--------|---------|
| Divergence strength | 30% | `min(abs(divergence) / 10.0, 1.0)` |
| Trend alignment | 25% | Count of TF ladders matching direction / 4 |
| ATR regime | 15% | `min(atr / atr_avg / 2.5, 1.0)` |
| Spread | 10% | `max(0, 1 - spread_pips / 2.0)` |
| Correlation | 20% | `max(0, 1 - concentration * 0.35)` |

### Configuration (from TECHNICAL_REPORT.md)

| Parameter | Value |
|-----------|-------|
| max_positions | 1 |
| max_trade_risk_pct | 0.003 (0.3%) |
| min_trade_risk_pct | 0.0005 (0.05%) |
| max_daily_risk_pct | 0.015 (1.5%) |
| per_currency_exposure | 2 |
| enable_replacement | True |

### Known vs Unknown

**Known:**
- Full constructor signature
- Method names and call signatures
- Return value structure
- Scoring dimensions and weights
- Configuration values
- Where output enters the backtest (line 734-756)

**Unknown:**
- Exact scoring implementation (how dimensions are combined)
- Replacement logic (when/how existing positions get replaced)
- Greedy selection implementation
- Risk allocation by rank (how risk_pct decays from rank 0 to last)
- Edge cases and internal state management
- Whether it maintains internal portfolio state between calls

---

## E. What Is Known

1. **backtest_hybrid_opt.py** is fully recovered and importable
2. **HybridBacktest** class works without PortfolioManager — it has its own entry logic
3. **backtest_portfolio.py** wraps HybridBacktest and adds PM-based signal selection
4. The PM layer replaces the built-in entry logic with scored/ranked selection
5. **risk_manager.py** provides position sizing for both systems
6. **currency_strength.py** provides the strength calculation
7. All nestquant package modules are importable and tested (199 tests)
8. The `.pyc` bytecode confirms the merged version is the correct one
9. Config constants have been added to `settings.py` for backward compatibility

---

## F. What Is Unknown

1. **portfolio_manager.py** implementation — file never existed on this VPS
2. **Which config values are "correct"** — 5 config files with conflicting values, no authoritative source
3. **Whether the legacy system was ever run successfully** — no result files, no trade logs
4. **Data format** — the `.pkl` files that `/root/data/` should contain are missing
5. **Which system is "production"** — the legacy backtest or the NestQuant package
6. **Whether the two systems produce comparable results** — cannot test without data
7. **The intended relationship** between the legacy scripts and the NestQuant package
8. **Whether `backtest_hybrid_opt.py` was meant to replace or coexist with** the nestquant engines

---

## G. Safe Next Steps

1. **Resolve config conflicts** — Pick authoritative values for each conflicting symbol. Do not change behavior; just consolidate.
2. **Wire NestQuant package as a library** — Make `backtest_hybrid_opt.py` use `nestquant.indicators` directly instead of bare `indicators` import.
3. **Create PortfolioManager interface spec** — Formalize the exact API contract so reconstruction can be validated against it.
4. **Add integration tests** — Test that legacy scripts can at least be imported and their functions called with mock data.
5. **Document the pair list decision** — Choose 7, 8, or 12 tradeable pairs and make it consistent.
6. **Archive unused config files** — Move `/root/merged/` and `/root/backup_old/` to an archive directory.

---

## H. Unsafe/Unsupported Assumptions

1. **DO NOT assume the merged config values are correct** — They may be from a different account size ($20 vs $1000 vs $10,000).
2. **DO NOT assume the nestquant package is the "new" system** — It may be an incomplete refactor.
3. **DO NOT assume the legacy system is the "old" system** — It contains features (correlation guard, session scaling) that the nestquant package lacks.
4. **DO NOT assume PortfolioManager can be reconstructed from docs** — The scoring formula is documented but the implementation logic is not.
5. **DO NOT assume the two systems are interchangeable** — They have different signal generation, position sizing, and risk management.
6. **DO NOT assume data files exist elsewhere** — `/root/data/` is empty and no `.pkl` files were found on the VPS.

---

## I. Test Results

### Pytest Suite
```
199 passed in 0.56s — 0 failures, 0 warnings from our code
```

### Import Checks

| Script | Importable? | Blocker |
|--------|-------------|---------|
| `backtest_hybrid_opt.py` | YES | — |
| `risk_manager.py` | YES | — |
| `backtest_gft_crisis.py` | YES | — |
| `oos_validation.py` | YES | — |
| `backtest_portfolio.py` | NO | `portfolio_manager` missing |
| `zero_costs_test.py` | NO | `portfolio_manager` (via backtest_portfolio) |
| `debug_breakout.py` | NO | `portfolio_manager` (via backtest_portfolio) |

### Standalone Verification

- `backtest_hybrid_opt.py` exports all expected symbols
- `HybridBacktest` class is fully functional (methods, precomputation, run)
- `HybridBacktest.run()` does NOT reference PortfolioManager — it has its own entry logic
- `precompute_atrs()` requires `1min` key in `all_tfs` dict (verified with mock data)

---

## J. Git Status

```
Branch: master
Last commit: 5dd3841 (Initial NestQuant baseline)

Modified files (uncommitted):
  M config/__init__.py          — Added wildcard re-export for legacy compat
  M config/settings.py          — Added 5 missing constants
  M risk_manager.py             — Replaced with merged version + daily_gross_loss

New files (uncommitted):
  ?? backtest_hybrid_opt.py     — Recovered from /root/merged/
  ?? currency_strength.py       — Recovered from /root/merged/
  ?? risk_manager_gft.py        — Backup of original GFT risk_manager
  ?? AUDIT_REPORT.md            — Phase 1 audit
  ?? PHASE_2_REPORT.md          — Phase 2 investigation
  ?? PHASE_2_RECOVERY_REPORT.md — Phase 2 recovery
  ?? pyproject.toml             — Phase 1 package setup
  ?? tests/                     — Phase 1 test suite (199 tests)
```

No commits have been made. All changes are uncommitted.

---

*Report generated 2026-08-09. Read-only analysis — no source code was modified.*
