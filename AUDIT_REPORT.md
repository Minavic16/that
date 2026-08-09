# NestQuant — Full Codebase Audit Report

**Date:** 2026-08-09
**Auditor:** opencode (automated read-only audit)
**Scope:** All Python modules, tests, config, backtest engine, risk/circuit-breaker, position sizing, signal interfaces

---

## 1. What Is Already Implemented

### `nestquant` Python Package (importable when `/root` is on `sys.path`)

| Module | Status | Details |
|--------|--------|---------|
| **indicators/** | Complete | ADX, ATR, EMA, pip utils, resampler, session filter, swing detection — 7 files, all importable |
| **signals/** | Complete | `BaseSignal` ABC, `BreakoutSignal`, `StructuredEntrySignal` — all importable |
| **regime/** | Complete | `RegimeDetector` ABC, `ADXRegimeDetector`, `HybridRegimeDetector` (TabFM+ADX), labels, regime params |
| **regime/tabfm/** | Partially complete | Model wrapper (placeholder random Dirichlet inference, not real PyTorch), 45-feature engineering pipeline, rule-based labeler, predictor — all importable, but no trained model exists |
| **risk/** | Complete | 6 circuit breakers (WinRate, Slippage, DrawdownPace, ProfitFactor, Correlation, DrawdownDrift) orchestrated by `BreakerSuite` — 445 lines, all importable |
| **engines/** | Complete | `BaseEngine` ABC, `BacktestEngine` (trade sim with spread/slippage/SL-TP), `RegimeBacktestEngine` — all importable |
| **portfolio/** | Complete | Leverage-aware position sizing with margin guard, cross-rate pip-value conversion — all importable |
| **execution/** | Stub only | `BaseExecutor` ABC + `OrderResult` dataclass — no concrete broker implementations |
| **backtest/** | Complete | `BacktestMetrics` dataclass, `ABComparison` framework for regime method comparison |
| **config/** | Complete | Dataclass-based `NestQuantConfig` (pydantic-style), singleton pattern, 486 lines |
| **data/** | Complete | `DataLoader` for pickle-based OHLCV data |
| **knowledge/** | Complete | `ExperimentTracker` for tracking params/metrics/artifacts |
| **utils/** | Complete | Logger setup, trading time utilities |

### Legacy Scripts (NOT part of the package)

| File | Status | Details |
|------|--------|---------|
| `backtest_portfolio.py` (1095 lines) | **Broken** | Main portfolio-aware backtest. Cannot import — depends on `backtest_hybrid_opt` (missing) and `portfolio_manager` (missing) |
| `backtest_gft_crisis.py` (308 lines) | **Broken** | Monte Carlo crisis backtest. Same missing dependencies |
| `oos_validation.py` (281 lines) | **Broken** | IS/OOS validation. Same missing dependencies |
| `zero_costs_test.py` (76 lines) | **Broken** | Zero-cost test. Same missing dependencies |
| `debug_breakout.py` (127 lines) | **Broken** | Debug script. Same missing dependencies |
| `config.py` (109 lines, root) | Works standalone | Flat-constant GFT config |
| `risk_manager.py` (110 lines, root) | **Broken** | Imports `FLOATING_LOSS_KILL_THRESHOLD` from `config.py` but that constant doesn't exist there |
| `logger.py` (28 lines) | Works standalone | Structured logging |

---

## 2. What Is Missing

### Critical Missing Files

1. **`backtest_hybrid_opt.py`** — Referenced by 5 legacy scripts. Contains `load_and_resample`, `precompute_strength`, `precompute_signals_vectorized`, `precompute_atrs`, `HybridBacktest`, `B_TF_LADDER`, `is_active_session`, and many constants. This is the core legacy engine.
2. **`portfolio_manager.py`** — Referenced by `backtest_portfolio.py`. Contains `PortfolioManager` class for signal scoring/ranking/allocation.
3. **`/root/config.py` `FLOATING_LOSS_KILL_THRESHOLD`** — Referenced by `risk_manager.py` line 11 but does not exist in `/root/config.py`.

### Missing Infrastructure

4. **No `requirements.txt`** or `pyproject.toml` — No formal dependency specification
5. **No `tests/` directory** — Zero pytest tests
6. **No `conftest.py`**
7. **No `setup.py` / `pyproject.toml`** — Package is not installable (`pip install -e .` won't work)
8. **No `.env` file** — `dotenv` is loaded but no env file present
9. **No data files** — `DATA_DIR = '/root/data'` but no data directory exists (`.pkl` files gitignored)

### Missing Functionality

10. **No concrete executor** — `execution/` has only the ABC; no cTrader, MT5, or other broker connector
11. **TabFM model is placeholder** — Uses random Dirichlet inference, not a trained neural network
12. **Slippage not applied** in the legacy backtest (`SLIPPAGE_PIPS` defined but never used)
13. **No portfolio-level manager** in the `nestquant` package — only position sizing; the scoring/ranking/selection layer lives only in the missing `portfolio_manager.py`

---

## 3. What Tests Currently Exist

**None that are runnable via pytest.**

| File | Type | Runnable? |
|------|------|-----------|
| `zero_costs_test.py` | Standalone script | No — depends on `backtest_hybrid_opt` |
| Everything else | No test files | — |

There are no `test_*.py` files, no `conftest.py`, no `tests/` directory, and no pytest configuration anywhere in the repository.

---

## 4. Dependencies / Environment

### Installed in `/root/venv/` (Python 3.12.3)

- `numpy 2.4.6`, `pandas 3.0.3` — core data
- `pydantic 2.13.4`, `pydantic_core 2.46.4` — config validation
- `python-dotenv 1.2.2` — env loading
- `matplotlib 3.11.0` — plotting
- `yfinance` — data (installed but not used by code)
- `curl_cffi`, `dukascopy-python` — data fetching

### NOT installed (but imported/needed)

- `torch` / PyTorch — needed by `regime/tabfm/model.py` (imported conditionally, currently skipped)
- `pytest` — no test runner installed
- `scipy` — not present but may be needed for statistical tests
- `scikit-learn` — not present

---

## 5. Importability / Runnability

| What | Importable? | Notes |
|------|-------------|-------|
| `nestquant` package (all submodules) | **Yes** (with `/root` on `sys.path`) | All 54 `.py` files in the package import successfully |
| `backtest_portfolio.py` | **No** | `ModuleNotFoundError: backtest_hybrid_opt` |
| `backtest_gft_crisis.py` | **No** | Same missing dependency |
| `oos_validation.py` | **No** | Same missing dependency |
| `zero_costs_test.py` | **No** | Same missing dependency |
| `debug_breakout.py` | **No** | Same missing dependency |
| `risk_manager.py` | **No** | `ImportError: FLOATING_LOSS_KILL_THRESHOLD` not in config |
| `config.py` (root) | **Yes** | Standalone flat constants |

**The `nestquant` package itself is fully importable.** The 5 legacy scripts are all broken because they depend on `backtest_hybrid_opt.py` and `portfolio_manager.py` which do not exist anywhere on disk.

---

## 6. Inconsistencies Between Modules

| # | Inconsistency | Severity |
|---|---------------|----------|
| 1 | **Two config systems**: Root `config.py` (flat constants) vs `config/settings.py` (dataclass-based). Different pair lists (12 vs 28 vs 7 tradeable), different parameter values (`RISK_PER_TRADE` = 0.0023 vs 0.003), different SL multipliers (2.0 vs 3.0). | High |
| 2 | **`risk_manager.py` imports nonexistent constant** `FLOATING_LOSS_KILL_THRESHOLD` from `config.py` — that name doesn't exist there. | High |
| 3 | **Broken sys.path hacks**: `backtest_portfolio.py` does `sys.path = ['/root/nestquant', '/root'] + ...` then imports `backtest_hybrid_opt` which doesn't exist anywhere. | High |
| 4 | **Legacy scripts reach outside repo**: `backtest_portfolio.py` line 29 loads `/root/config.py` via `importlib`, line 44 imports `risk_manager` from `/root`, line 49 imports `portfolio_manager` from `/root` — all fragile external deps. | High |
| 5 | **Duplicate position sizing**: `portfolio/position_sizer.py` (clean, well-structured) vs `backtest_portfolio.py` inline sizing logic (different formula, different pip-value constants). | Medium |
| 6 | **Duplicate indicator implementations**: `indicators/` module has clean standalone functions, but `backtest_portfolio.py` uses the inline implementations from the missing `backtest_hybrid_opt`. | Medium |
| 7 | **`signals/breakout.py` TP ratio**: Uses `atr * 2.0` for TP but TECHNICAL_REPORT says RRR = 3.5. The `nestquant` package breakout signal uses a hardcoded `2.0` multiplier for TP. | Medium |
| 8 | **`config/settings.py` vs root `config.py` pair lists**: settings has 28 `all_pairs` and 7 `tradeable_pairs`; root config has 12 pairs. | Medium |
| 9 | **Regime engine not exported**: `engines/__init__.py` exports `BacktestEngine` but not `RegimeBacktestEngine`. | Low |
| 10 | **`logger.py` (root) vs `utils/logging.py`**: Two separate logging systems with different interfaces. | Low |

---

## 7. Recommended Fix Priority

### Phase 1: Make the package installable and testable (highest value)

1. **Create `pyproject.toml`** with proper package metadata and dependencies (`numpy`, `pandas`, `pydantic`, `python-dotenv`, optional `torch`)
2. **Add `pip install -e .` support** so `import nestquant` works from anywhere without sys.path hacks
3. **Create `tests/` directory** with `conftest.py` and basic smoke tests for every importable module
4. **Run the existing `nestquant` package through pytest** to confirm nothing is silently broken

### Phase 2: Resolve the broken legacy scripts

5. **Decide**: Either recover `backtest_hybrid_opt.py` and `portfolio_manager.py` from git history/legacy, OR deprecate the 5 broken scripts entirely
6. **If keeping legacy**: Fix `risk_manager.py` missing `FLOATING_LOSS_KILL_THRESHOLD` import
7. **If deprecating**: Move legacy scripts to an `archive/` directory with a note, stop trying to maintain them

### Phase 3: Fix internal inconsistencies

8. **Unify config**: Pick one config system. The `config/settings.py` dataclass approach is cleaner; deprecate or adapt the root `config.py` constants
9. **Fix breakout signal TP ratio** to match the documented RRR of 3.5 (currently hardcoded to 2.0 in `signals/breakout.py`)
10. **Export `RegimeBacktestEngine`** from `engines/__init__.py`
11. **Wire up `position_sizer`** to the backtest engines so sizing logic is shared, not duplicated

---

*Report generated 2026-08-09. Read-only audit — no files were modified.*
