# Phase 2 Report — Legacy Backtest Recovery Investigation

**Date:** 2026-08-09
**Scope:** Investigate recoverability of missing legacy backtest components
**Status:** Investigation complete. No files modified.

---

## 1. Investigation Performed

### Search Sources
1. **Git history** — NestQuant repo (local), `/root` parent repo, all branches, all commits, all tags, reflog, stash
2. **Remote/GitHub** — `origin` (https://github.com/Minavic16/that.git), all remote branches, tags
3. **Filesystem** — Full recursive search of `/root` and all subdirectories, including `.hermes`, `__pycache__`, `/tmp`
4. **Documentation** — `TECHNICAL_REPORT.md`, `PROJECT_STATE.md`, `AUDIT_REPORT.md`
5. **Bytecode** — Inspected `/root/__pycache__/backtest_hybrid_opt.cpython-312.pyc` for class/function definitions
6. **Cross-reference** — Every import statement in every broken legacy script mapped against all found files

### Symbols Searched
`backtest_hybrid_opt.py`, `portfolio_manager.py`, `HybridBacktest`, `load_and_resample`, `precompute_strength`, `precompute_signals_vectorized`, `precompute_atrs`, `B_TF_LADDER`, `is_active_session`, `PortfolioManager`, `FLOATING_LOSS_KILL_THRESHOLD`

---

## 2. Git History Findings

### NestQuant Repo (`/root/nestquant`)
- **1 commit** on `master`: `5dd3841` (Initial NestQuant baseline)
- **0 tags** locally
- **1 remote branch**: `origin/master`
- `backtest_hybrid_opt.py` — **NEVER committed**
- `portfolio_manager.py` — **NEVER committed**
- All `.py` files ever committed: 77 files (test scripts, analysis scripts, nestquant package modules). Neither missing file appears.

### `/root` Parent Repo
- **26 commits** total (NextJS website commits + 4 trading-related commits)
- `backtest_hybrid_opt.py` — **NEVER committed**
- `portfolio_manager.py` — **NEVER committed**
- All `.py` files ever committed: 33 files. Neither missing file appears.

### GitHub Remote
- **1 branch**: `master` (at `af57ec3`)
- **1 tag**: `legacy/pre-rebuild-2026-08-09` (annotated, tagged before the rebuild)
  - Points to commit `af57ec3` ("Add all backtest and analysis scripts")
  - Contains 15 test/analysis `.py` files. **Does NOT contain `backtest_hybrid_opt.py` or `portfolio_manager.py`.**
- No other remote refs exist.

### Git Stash / Reflog
- No stashes in either repo
- No evidence of deleted files in reflog

**Conclusion:** Neither `backtest_hybrid_opt.py` nor `portfolio_manager.py` was ever version-controlled in any repository accessible from this VPS.

---

## 3. Remote/GitHub Findings

| Ref | Contains `backtest_hybrid_opt.py`? | Contains `portfolio_manager.py`? |
|-----|------------------------------------|----------------------------------|
| `origin/master` (af57ec3) | No | No |
| `legacy/pre-rebuild-2026-08-09` tag | No | No |
| Any other remote ref | N/A (none exist) | N/A |

The GitHub repository (`Minavic16/that`) was primarily a NextJS website project. The trading scripts were added in commits `df508eb` through `af57ec3`, but these commits only contain test/analysis scripts, not the core backtest engine.

---

## 4. Filesystem Findings

### `backtest_hybrid_opt.py` — FOUND (2 copies + 1 .pyc)

| Location | Lines | Size | Date | Notes |
|----------|-------|------|------|-------|
| `/root/merged/backtest_hybrid_opt.py` | 1,026 | 48,522 B | Jul 1 22:34 | "Merged" version |
| `/root/backup_old/backtest_hybrid_opt.py` | 929 | 43,448 B | Jul 1 22:35 | "Backup old" version |
| `/root/__pycache__/backtest_hybrid_opt.cpython-312.pyc` | — | — | — | Compiled bytecode |

These files exist on disk but were **never committed to git**. They appear to be manually placed backup copies, likely created during a rebuild/reorganization on Jul 1, 2026.

### `portfolio_manager.py` — NOT FOUND

- **Zero files** named `portfolio_manager.py` anywhere on the filesystem
- **Zero `.pyc`** files for `portfolio_manager`
- **Zero class definitions** of `PortfolioManager` in any `.py` file
- The `.pyc` for `backtest_hybrid_opt` was inspected; it contains `HybridBacktest` and its methods but **no `PortfolioManager` class**

### Supporting Files Found

| File | Location | Lines | Status |
|------|----------|-------|--------|
| `config.py` (merged) | `/root/merged/config.py` | 150 | Has session/correlation/daily-loss symbols |
| `config.py` (backup_old) | `/root/backup_old/config.py` | 149 | Has daily-loss symbols, missing session/correlation |
| `config.py` (root) | `/root/config.py` | ~165 | Has session/correlation, missing `REGIME_ATR_MULTIPLIER`, `REGIME_LOOKBACK`, `MAX_DAILY_LOSS_PCT`, `MAX_CONSECUTIVE_LOSSES` |
| `indicators.py` | `/root/merged/indicators.py` | 202 | Identical to `/root/indicators.py` |
| `currency_strength.py` | `/root/merged/currency_strength.py` | 295 | Only in merged |
| `risk_manager.py` (merged) | `/root/merged/risk_manager.py` | 80 | Simplified, no FLOATING_LOSS_KILL_THRESHOLD |
| `risk_manager.py` (backup_old) | `/root/backup_old/risk_manager.py` | 281 | Has circuit breakers, uses different config symbols |

### Data Files
- `/root/data/` directory **does not exist**
- No `.pkl` data files found on the VPS (only numpy/joblib test fixtures)
- The legacy scripts expect `/root/data/<pair>.pkl` files which are absent

---

## 5. Missing-Module Dependency Graph

```
backtest_portfolio.py (1095 lines)
├── backtest_hybrid_opt  ← FOUND on disk (2 versions)
├── portfolio_manager    ← NOT FOUND (nowhere on filesystem)
├── risk_manager (from /root)  ← Found but broken (missing FLOATING_LOSS_KILL_THRESHOLD)
├── config (from nestquant)    ← Found
└── config (from /root)        ← Found (imported via importlib)

backtest_gft_crisis.py (308 lines)
├── backtest_hybrid_opt  ← FOUND on disk
└── config               ← Found

oos_validation.py (281 lines)
├── backtest_hybrid_opt  ← FOUND on disk
├── backtest_gft_crisis  ← Found (but broken transitively)
└── config               ← Found

zero_costs_test.py (76 lines)
├── backtest_hybrid_opt  ← FOUND on disk
├── backtest_portfolio   ← Found (but broken due to missing portfolio_manager)
└── config               ← Found

debug_breakout.py (127 lines)
├── backtest_hybrid_opt  ← FOUND on disk
├── backtest_portfolio   ← Found (but broken due to missing portfolio_manager)
└── config               ← Found
```

### Import Details Per Script

**`backtest_portfolio.py`** imports from `backtest_hybrid_opt`:
- `load_and_resample`, `precompute_strength`, `precompute_signals_vectorized`, `precompute_atrs`, `HybridBacktest`, `B_TF_LADDER`, `logger`
- Also imports `is_active_session`, `pip_size`, `COMMISSION_PER_LOT`, `MIN_LOT_SIZE`, `ENABLE_MACRO_FILTER`, `ENABLE_REGIME_FLIP`, `TRADEABLE_PAIRS`, `MAX_PER_CURRENCY_BLOCK` (inside `run_portfolio_backtest`)
- Imports `PortfolioManager` from `portfolio_manager` module at `/root`

**`backtest_gft_crisis.py`** imports from `backtest_hybrid_opt`:
- `load_and_resample`, `precompute_strength`, `precompute_signals_vectorized`, `precompute_atrs`, `HybridBacktest`

**`oos_validation.py`** imports from `backtest_hybrid_opt`:
- `load_and_resample`, `precompute_strength`, `precompute_signals_vectorized`, `precompute_atrs`, `HybridBacktest`
- Also imports `load_all_pairs`, `GFTDynamicRiskManager` from `backtest_gft_crisis`

**`zero_costs_test.py`** imports from `backtest_hybrid_opt`:
- `B_TF_LADDER`, `precompute_strength`, `precompute_signals_vectorized`
- Also imports `PortfolioManager`, `run_portfolio_backtest` from `backtest_portfolio`

**`debug_breakout.py`** imports from `backtest_hybrid_opt`:
- `B_TF_LADDER`, `precompute_strength`, `precompute_signals_vectorized`, `precompute_atrs`
- Also imports `precompute_breakout_signals`, `precompute_swing_levels` from `backtest_portfolio`
- Also imports `is_active_session`, `pip_size`, `COMMISSION_PER_LOT`, `MIN_LOT_SIZE`, `ENABLE_MACRO_FILTER`, `ENABLE_REGIME_FLIP`, `TRADEABLE_PAIRS`, `MAX_PER_CURRENCY_BLOCK`

---

## 6. Historical Evidence for Each Missing Component

### `backtest_hybrid_opt.py`

**Evidence of existence:**
- Two physical copies exist on disk (`/root/merged/` and `/root/backup_old/`)
- Compiled `.pyc` exists at `/root/__pycache__/backtest_hybrid_opt.cpython-312.pyc`
- 5 legacy scripts import from it
- `TECHNICAL_REPORT.md` references it implicitly through the architecture it describes

**Two versions found — key differences:**

| Aspect | Merged (1026 lines) | Backup Old (929 lines) |
|--------|---------------------|------------------------|
| `B_TF_LADDER` | `["1min", "5min", "15min", "4h", "1D"]` | `["5min", "15min", "4h", "1D"]` |
| Config imports | `SESSION_CLOSE_UTC`, `MAX_ENTRY_HOUR`, `SCALE_SL_AT_SESSION_CLOSE`, `SESSION_CLOSE_MINUTES_BEFORE`, `BLOCK_SAME_DIRECTION_REENTRY`, `CORRELATION_ENABLED`, `CORRELATION_WINDOW`, `CORRELATION_THRESHOLD` | `MAX_DAILY_LOSS_PCT`, `MAX_CONSECUTIVE_LOSSES` |
| `_precompute_correlations()` | Present | Absent |
| `HybridBacktest.run()` | `run(self, start_date, end_date)` | `run(self, start_date, end_date, external_risk_mgr=None)` |
| Config it requires | `/root/merged/config.py` (has all needed symbols) | `/root/backup_old/config.py` (has all needed symbols) |

**Neither version matches `/root/config.py` exactly** — the root config is missing `REGIME_ATR_MULTIPLIER`, `REGIME_LOOKBACK`, `MAX_DAILY_LOSS_PCT`, `MAX_CONSECUTIVE_LOSSES` which both versions import.

### `portfolio_manager.py`

**Evidence of existence:**
- `TECHNICAL_REPORT.md` line 57: `portfolio_manager.py | PM scoring/ranking/allocation (294 lines)`
- `TECHNICAL_REPORT.md` section 5 describes the PortfolioManager layer in detail:
  - Scoring dimensions: divergence strength (30%), trend alignment (25%), ATR regime (15%), spread (10%), correlation (20%)
  - Selection algorithm: score → sort → replacement check → greedy selection → risk allocation
  - Configuration: max_positions=1, max_trade_risk_pct=0.003, min_trade_risk_pct=0.0005, max_daily_risk_pct=0.015, per_currency_exposure=2, enable_replacement=True
- `backtest_portfolio.py` imports it: `import portfolio_manager as pm_module; PortfolioManager = pm_module.PortfolioManager`
- `backtest_portfolio.py` uses it: `pm.select_trades(...)` at line 729, `pm.max_trade_risk_pct` at line 746

**Evidence of NON-existence:**
- Zero files named `portfolio_manager.py` on the entire filesystem
- Zero `.pyc` files for `portfolio_manager`
- Zero class definitions of `PortfolioManager` in any `.py` file
- Never committed to any git repository (NestQuant, /root, or GitHub)
- Not in any backup directory (`/root/merged/`, `/root/backup_old/`)

**Conclusion:** `portfolio_manager.py` was never saved to this VPS. The TECHNICAL_REPORT describes it as if it existed (294 lines), but the file itself is absent from all storage. It may have existed on a different machine, in a different environment, or was lost before the VPS was set up.

### `FLOATING_LOSS_KILL_THRESHOLD`

**Evidence of existence:**
- `gft_backtest_fixed.py` (in `.hermes/skills/`) defines it: `FLOATING_LOSS_KILL_THRESHOLD = -15.0` (line 24)
- Comment: "Hard close all at -$15"
- Used at line 319: `if floating < FLOATING_LOSS_KILL_THRESHOLD:`
- `risk_manager.py` (root/nestquant) imports it from `config` at line 11
- `risk_manager.py` uses it at line 103: `self.daily_pnl = -FLOATING_LOSS_KILL_THRESHOLD`

**Historical meaning:** This is a GFT (The Funded Trader / Funded Next style) prop firm rule. When a single position's floating loss reaches -$15, the system force-closes all positions. The value is dollar-denominated, not percentage-based, designed for a $20 micro account.

**Where it should be defined:** In `/root/config.py` (the root config that `risk_manager.py` imports from). It is currently absent from that file.

---

## 7. Recoverability Assessment

### `backtest_hybrid_opt.py` — RECOVERABLE (with caveats)

**Status:** Two complete copies exist on disk. The file can be placed into the project.

**Caveats:**
1. **Two versions exist** with meaningful differences. The "merged" version (1026 lines) is more complete (includes `_precompute_correlations`, has the `1min` timeframe in `B_TF_LADDER`). The "backup old" version (929 lines) has a different `HybridBacktest.run()` signature (`external_risk_mgr` parameter).
2. **Config mismatch**: Both versions import symbols that don't exist in `/root/config.py` (e.g., `REGIME_ATR_MULTIPLIER`, `REGIME_LOOKBACK`). They require their companion `config.py` from the same directory.
3. **Missing companion**: `currency_strength.py` (only in `/root/merged/`) is required by `backtest_hybrid_opt.py`.
4. **No data files**: The `/root/data/` directory with `.pkl` pair data does not exist. The scripts cannot run without data.

### `portfolio_manager.py` — NOT RECOVERABLE

**Status:** No source code exists anywhere on the filesystem, git history, or remote.

**What we know from documentation:**
- 294 lines (per TECHNICAL_REPORT)
- Scoring: divergence_strength (30%), trend_alignment (25%), atr_regime (15%), spread (10%), correlation (20%)
- Selection: score → sort → replacement check → greedy selection → risk allocation
- Config: max_positions=1, max_trade_risk_pct=0.003, min_trade_risk_pct=0.0005, max_daily_risk_pct=0.015, per_currency_exposure=2, enable_replacement=True

**Recovery options:**
1. **Cannot be recovered from original source** — it simply does not exist
2. **Could be reconstructed from documentation** — the TECHNICAL_REPORT provides enough detail to reimplement it, but this would be invention, not recovery
3. **Could be extracted from `backtest_portfolio.py`** — the usage pattern (`pm.select_trades(...)`, `pm.max_trade_risk_pct`) defines the interface, and the scoring dimensions are documented, but the implementation logic is unknown

### `FLOATING_LOSS_KILL_THRESHOLD` — RECOVERABLE (trivially)

**Status:** The value is known (`-15.0`) from `gft_backtest_fixed.py`. It needs to be added to `/root/config.py`.

**Historical value:** `-15.0` (hard close all at -$15 floating loss on a $20 account)

---

## 8. FLOATING_LOSS_KILL_THRESHOLD Investigation

### Source
- **File:** `/root/.hermes/skills/optimized-forex-backtesting-framework/scripts/gft_backtest_fixed.py`
- **Line 24:** `FLOATING_LOSS_KILL_THRESHOLD = -15.0   # Hard close all at -$15`
- **Line 319:** `if floating < FLOATING_LOSS_KILL_THRESHOLD:`

### Context
This constant is part of the "GFT Death Rules" in the original GFT (prop firm) backtest:
```python
FLOATING_LOSS_KILL_THRESHOLD = -15.0   # Hard close all at -$15
DAILY_LOSS_LIMIT = 25.0               # Block entries at -$25
GFT_DAILY_DRAWDOWN = 30.0             # Awareness: GFT kills at -$30
GFT_TOTAL_DRAWDOWN = 60.0             # Awareness: GFT kills at -$60
GFT_FLOATING_DEATH = -20.0            # Awareness: GFT kills at -$20
```

### Meaning
On a $20 micro account with 1:500 leverage, if any single position reaches -$15 floating loss, the system force-closes all positions. This is a hard circuit breaker specific to the GFT prop firm evaluation rules.

### Usage in `risk_manager.py`
```python
from config import FLOATING_LOSS_KILL_THRESHOLD  # line 11
...
self.daily_pnl = -FLOATING_LOSS_KILL_THRESHOLD  # line 103 (sets daily limit to +$15)
```

The root `config.py` where `risk_manager.py` expects this constant does **not** define it. This causes an `ImportError` at import time.

---

## 9. Legacy Script Relevance Assessment

### Current NestQuant Architecture (from TECHNICAL_REPORT)

The documented "current" system is a **portfolio-aware, regime-adaptive FX momentum/breakout system**:
- 28 FX pairs, 4h entry signals, 1min execution
- PortfolioManager scoring/ranking layer
- ADX-based regime sizing
- Swing-based trailing stop
- Max 1 position

### Legacy Script Relevance

| Script | Purpose | Relevant to Current Architecture? | Verdict |
|--------|---------|-----------------------------------|---------|
| `backtest_portfolio.py` | Main portfolio-aware backtest | **YES** — this IS the current architecture's backtest engine | Should be recovered if possible |
| `backtest_hybrid_opt.py` | Core engine (data loading, signals, HybridBacktest class) | **YES** — core dependency for the above | Should be recovered (copies exist) |
| `portfolio_manager.py` | PM scoring/ranking layer | **YES** — critical component of current architecture | Cannot be recovered; would need reimplementation |
| `backtest_gft_crisis.py` | Monte Carlo crisis simulation on GFT rules | **PARTIALLY** — GFT-specific, but uses the same engine | Lower priority |
| `oos_validation.py` | In-sample/out-of-sample validation | **YES** — standard backtest validation | Depends on backtest_hybrid_opt + backtest_gft_crisis |
| `zero_costs_test.py` | Zero-cost spread test | **LOW** — diagnostic script | Low priority |
| `debug_breakout.py` | Breakout signal debugging | **LOW** — diagnostic script | Low priority |
| `risk_manager.py` | GFT-specific dynamic risk scaling | **NO** — GFT prop firm specific, not the current architecture's risk system | Different from `nestquant/risk/` circuit breakers |

### Key Insight

The legacy scripts (`backtest_portfolio.py` + `backtest_hybrid_opt.py` + `portfolio_manager.py`) represent the **documented current architecture** described in `TECHNICAL_REPORT.md`. However:
- The `nestquant` package has its own `engines/backtest_engine.py`, `portfolio/position_sizer.py`, `risk/circuit_breakers.py`, etc. which are a **different implementation** of similar concepts
- The legacy scripts and the nestquant package are **parallel implementations** that don't share code
- The legacy scripts are the ones that produced the results documented in TECHNICAL_REPORT.md

---

## 10. Risks of Reconstruction

### For `backtest_hybrid_opt.py` (recovery, not reconstruction)
- **Low risk** — the file exists on disk and can be copied directly
- **Config resolution risk** — the file imports from `config` module; the correct `config.py` must be co-located or on `sys.path`
- **Data dependency** — cannot run without `/root/data/*.pkl` files
- **Version ambiguity** — two versions exist with different features; must choose the correct one

### For `portfolio_manager.py` (reconstruction required)
- **HIGH RISK** — this would be invention, not recovery
- The interface is known (`select_trades`, `max_trade_risk_pct`), the scoring dimensions are documented, but the **exact implementation logic is unknown**
- Any reconstruction would produce a **different** implementation than the original
- The original produced the documented results; a reconstruction might not replicate them
- Trading logic changes could affect live system behavior if reconstruction is incorrect

### For `FLOATING_LOSS_KILL_THRESHOLD` (trivial fix)
- **Very low risk** — adding a constant to config
- Value is known from historical evidence (`-15.0`)
- But: the root `config.py` uses env-variable-based defaults; the constant format may differ

---

## 11. Recommended Next Action

### Immediate (can be done now)
1. **Place `backtest_hybrid_opt.py`** from `/root/merged/backtest_hybrid_opt.py` into `/root/nestquant/` (or a subdirectory). This is a direct file copy, not reconstruction.
2. **Place companion files**: `currency_strength.py`, `indicators.py` (from `/root/merged/`), and the merged `config.py` — or reconcile their differences with `/root/config.py`.
3. **Add `FLOATING_LOSS_KILL_THRESHOLD = -15.0`** to `/root/config.py` to fix the `risk_manager.py` import error.

### Requires Decision
4. **Choose which version** of `backtest_hybrid_opt.py` to use (merged vs backup_old). The merged version is more feature-complete (has `_precompute_correlations`, 1min TF).
5. **Decide on `portfolio_manager.py`**: Either reconstruct from TECHNICAL_REPORT documentation (high risk), or redesign the PM layer to work with the existing `nestquant/portfolio/` module.

### Not Recommended
- Do **not** attempt to reconstruct `portfolio_manager.py` from interpretation — the original logic is lost
- Do **not** place recovered legacy files into the nestquant package structure without understanding the full dependency chain
- Do ** not** run the legacy scripts without data files (`/root/data/*.pkl`)

---

## 12. Explicit Confirmation

**No trading logic or source code was modified during this investigation.**

- Zero files were created, modified, or deleted
- Zero commits were made
- Zero parameters were changed
- All investigation was read-only (file searches, git queries, diff comparisons, bytecode inspection)
- The `/root/nestquant` repository remains in its exact pre-investigation state

---

*Report generated 2026-08-09. Read-only investigation — no files were modified.*
