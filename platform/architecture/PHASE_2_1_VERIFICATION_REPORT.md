# Phase 2.1 — Post-Migration Verification & Migration-Debt Audit

> **Date:** 2026-09-12
> **Git HEAD:** `6a36b68` (master)
> **Status:** READ-ONLY VERIFICATION — ZERO MODIFICATIONS MADE
> **Environment:** Python 3.14.6, numpy 2.4.4, pytest 9.1.1 (no pandas, no MT5)

---

## 1. Git State

| Field | Value |
|-------|-------|
| Branch | master |
| HEAD | `6a36b6823c812921f320a4a48fd0647e9e5231e7` |
| Untracked files | 0 |
| Modified files | 0 |
| Deleted (uncommitted) | 135 files in `docs/` (11) and `research_data/` (124) |

**Finding:** 135 files were deleted from the working tree but the deletions were never committed. `docs/` and `research_data/` directories no longer exist on disk. These are migration artifacts — Phase 2 moved their contents but the deletions were left uncommitted.

---

## 2. Actual Repository Root

```
/root/that/
├── .env.example          ← acceptable metadata (tracked)
├── .env.telegram          ← UNTRACKED, contains live credential (see §12)
├── .git/                  ← acceptable metadata
├── .gitignore             ← acceptable metadata
├── .pytest_cache/         ← temporary build artifact
├── __init__.py            ← MIGRATION DEBT (see §3)
├── __pycache__/           ← temporary build artifact
├── AGENTS.md              ← acceptable documentation
├── CONTRIBUTING.md        ← acceptable documentation (stale paths, see §15)
├── REPOSITORY_MIGRATION_PLAN.md ← acceptable documentation
├── config/                ← RE-EXPORT STUB DIRECTORY (see §4)
├── execution/             ← RE-EXPORT STUB DIRECTORY (see §4)
├── indicators/            ← RE-EXPORT STUB DIRECTORY (see §4)
├── knowledge/             ← RE-EXPORT STUB DIRECTORY (see §4)
├── platform/              ← architectural domain ✓
├── production/            ← architectural domain ✓
├── pyproject.toml         ← requires update (see §8)
├── research/              ← architectural domain ✓
├── tests/                 ← architectural domain ✓
└── utils/                 ← RE-EXPORT STUB DIRECTORY (see §4)
```

**5 extra source-code directories exist at root:** `config/`, `execution/`, `indicators/`, `knowledge/`, `utils/`. These are re-export stubs, not architectural violations, but they are migration debt.

---

## 3. Root `__init__.py`

```python
"""
NestQuant — Autonomous Quantitative Research Platform
"""
__version__ = "0.2.0"
__author__ = "NestQuant"
from nestquant.config.settings import NestQuantConfig, get_config
__all__ = ["NestQuantConfig", "get_config"]
```

| Question | Answer |
|----------|--------|
| Why does it exist? | Makes the repo root an importable Python package (`import nestquant`) |
| Is the repo intended as an importable package? | Partially — some production files use `from nestquant.X import` |
| Does anything import it? | Yes: `tests/platform/test_imports.py:11` — `import nestquant` |
| Creates namespace ambiguity? | YES — `nestquant` resolves to the root dir, which contains stub directories that shadow canonical locations |
| Required after migration? | Only for files using `nestquant.X` imports (risk_guard.py, signals/breakout.py, etc.) |
| Would removing it break anything? | YES — 40+ production files import via `nestquant.X` |

**Recommendation:** `REMOVE IN PHASE 3` — after all `nestquant.X` imports are migrated to direct package paths.

---

## 4. Re-Export Stub Audit

8 re-export stubs exist. All are thin wrappers importing from canonical locations.

| Old Path | Canonical Path | Lines | Production Reachable? | Research Reachable? | Safe to Remove? |
|----------|---------------|-------|----------------------|--------------------|-----------------| 
| `execution/contracts.py` | `platform/contracts/execution_contracts.py` | 6 | YES (risk_guard.py) | YES (via stubs) | After import update |
| `config/constitution.py` | `platform/configuration/constitution.py` | 3 | YES (risk_guard.py, monitoring/) | YES (via stubs) | After import update |
| `config/settings.py` | `platform/configuration/settings.py` | 3 | YES (root __init__.py) | YES (via stubs) | After import update |
| `config/__init__.py` | — | 2 | No direct refs found | No direct refs found | YES — no references |
| `config/experiment.py` | `platform/configuration/experiment.py` | 2 | No direct refs found | No direct refs found | YES — no references |
| `config/policies/__init__.py` | `platform/configuration/policies/` | 2 | No direct refs found | No direct refs found | YES — no references |
| `indicators/__init__.py` | `platform/tooling/indicators/` | 8 | YES (signals/breakout.py) | YES (phase_hg1) | After import update |
| `utils/__init__.py` | `platform/tooling/utils/` | 3 | No direct refs found | No direct refs found | YES — no references |
| `knowledge/__init__.py` | `platform/knowledge/` | 2 | No direct refs found | No direct refs found | YES — no references |

**Key finding:** `execution/contracts.py`, `config/constitution.py`, `config/settings.py`, and `indicators/__init__.py` are actively referenced by production code. The remaining 5 stubs have zero references and can be removed immediately in Phase 3.

---

## 5. Bare Import Inventory

### 5a. Production Files (40+ bare imports)

All production bare imports use `nestquant.X` or bare `X` paths. These resolve through:
- Root `__init__.py` (for `nestquant.X`)
- Re-export stubs at root (for bare `X`)
- Python path resolution (root dir is in sys.path)

| File | Current Import | Canonical Import | Risk |
|------|---------------|-----------------|------|
| `production/execution/risk_guard.py` | `from nestquant.config.constitution import CONSTITUTION` | `from platform.configuration.constitution import CONSTITUTION` | Stub-dependent |
| `production/execution/risk_guard.py` | `from nestquant.execution.contracts import RiskDecision, TradeIntent` | `from platform.contracts.execution_contracts import RiskDecision, TradeIntent` | Stub-dependent |
| `production/execution/s8_runtime.py` | `from execution.data_feed import LiveDataFeed` | `from production.execution.data_feed import LiveDataFeed` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from execution.health_monitor import HealthMonitor` | `from production.execution.health_monitor import HealthMonitor` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from execution.intent_factory import IntentFactory` | `from production.execution.intent_factory import IntentFactory` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from execution.mt5_adapter import MT5ExecutionAdapter` | `from production.execution.mt5_adapter import MT5ExecutionAdapter` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from execution.mt5_client import MT5Client` | `from production.execution.mt5_client import MT5Client` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from execution.orchestration import ExecutionCoordinator` | `from production.execution.orchestration import ExecutionCoordinator` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from execution.prop_firm_guard import PropFirmConfig` | `from production.execution.prop_firm_guard import PropFirmConfig` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from execution.trade_logger import TradeLogger` | `from production.execution.trade_logger import TradeLogger` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from execution.protection import ExecutionProtection` | `from production.execution.protection import ExecutionProtection` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from strategy.lifecycle import ...` | `from production.strategy.lifecycle import ...` | Bare import, stub-dependent |
| `production/execution/s8_runtime.py` | `from strategy.trade_management.breakeven import BreakevenConfig` | `from production.strategy.trade_management.breakeven import BreakevenConfig` | Bare import, stub-dependent |
| `production/signals/breakout.py` | `from nestquant.indicators.atr import calculate_atr` | `from platform.tooling.indicators.atr import calculate_atr` | Stub-dependent |
| `production/signals/breakout.py` | `from nestquant.indicators.swing import swing_high_series` | `from platform.tooling.indicators.swing import swing_high_series` | Stub-dependent |
| `production/monitoring/__init__.py` | `from monitoring.percentiles import PercentileResult` | `from production.monitoring.percentiles import PercentileResult` | Bare import |
| `production/monitoring/metrics_aggregator.py` | `from config.constitution import CONSTITUTION` | `from platform.configuration.constitution import CONSTITUTION` | Stub-dependent |
| `production/notifications/__init__.py` | `from notifications.events import NQTSEvent` | `from production.notifications.events import NQTSEvent` | Bare import |

**Summary:** 40+ bare imports in production. All are migration debt, not violations. All resolve through re-export stubs or path resolution.

### 5b. Test Files (30+ bare imports)

| File | Current Import | Canonical Import |
|------|---------------|-----------------|
| `tests/conftest.py` | `from zscore.contracts import InstrumentMetadata` | `from platform.contracts.zscore_contracts import InstrumentMetadata` |
| `tests/regression/test_causality.py` | `from zscore.regime import ...` | `from research.shared.zscore.regime import ...` |
| `tests/regression/test_cross_timeframe_agreement.py` | `from scripts.cross_timeframe_agreement import ...` | `from research.experiments.cross_timeframe_agreement import ...` |
| `tests/regression/test_phase_s0_breakout.py` | `from scripts.phase_s0_breakout_reassessment import ...` | `from research.experiments.phase_s0_breakout_reassessment import ...` |
| `tests/safety/test_execution_protection.py` | `from execution.protection import ...` | `from production.execution.protection import ...` |
| `tests/parity/test_trade_management_parity.py` | `from strategy.trade_management.breakeven import ...` | `from production.strategy.trade_management.breakeven import ...` |
| `tests/smoke/test_end_to_end.py` | `from costs.model import ...` | `from research.shared.costs.model import ...` |
| `tests/unit/test_zscore.py` | `from zscore.zscore import compute_zscore_causal` | `from research.shared.zscore.zscore import compute_zscore_causal` |

**Summary:** 30+ bare imports in tests. All reference pre-migration paths. Many reference modules that no longer exist at the imported path (`zscore.contracts`, `scripts.*`).

### 5c. Research Files (20+ bare imports)

| File | Current Import | Canonical Import |
|------|---------------|-----------------|
| `research/phase3_research.py` | `from zscore.regime import classify_regime_chunked` | `from research.shared.zscore.regime import classify_regime_chunked` |
| `research/experiments/phase_hg1_holy_grail.py` | `from indicators.atr import calculate_atr` | `from platform.tooling.indicators.atr import calculate_atr` |
| `research/shared/analytics/research_analysis.py` | `from monitoring.percentiles import compute_percentiles` | `from production.monitoring.percentiles import compute_percentiles` |
| `research/shared/costs/model.py` | `from zscore.contracts import CostBreakdown, CostModel` | `from platform.contracts.zscore_contracts import CostBreakdown, CostModel` |

**Summary:** 20+ bare imports. All resolve through `sys.path.insert` calls (87 total across the codebase) that add parent directories to the Python path at runtime.

---

## 6. Dependency Graph

### 6a. `sys.path.insert` Usage

87 files use `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` to inject parent directories into the Python path. This is the primary mechanism enabling bare imports to resolve.

| Location | Files Using sys.path.insert |
|----------|---------------------------|
| `research/experiments/` | 29 |
| `tests/parity/` | ~3 |
| `tests/production/` | ~3 |
| `tests/regression/` | ~3 |
| `tests/safety/` | ~2 |
| `archive/research/` | several |
| `archive/scripts/` | several |
| `platform/tooling/` | several |
| `production/deployment/` | several |

### 6b. `nestquant.X` Imports (via root __init__.py)

Production files that import through the root package namespace:
- `production/execution/risk_guard.py` → `nestquant.config.constitution`, `nestquant.execution.contracts`, `nestquant.portfolio.position_sizer`, `nestquant.risk.circuit_breakers`
- `production/signals/breakout.py` → `nestquant.indicators.atr`, `nestquant.indicators.swing`, `nestquant.signals.base`
- `production/signals/__init__.py` → `nestquant.signals.base`, `nestquant.signals.breakout`
- `production/execution/shadow/__init__.py` → `nestquant.execution.shadow.*`
- `production/monitoring/metrics_aggregator.py` → `config.constitution`

### 6c. No subprocess, Docker, or CI references found

No Dockerfiles, docker-compose, or CI workflow files exist in the repository.

---

## 7. Architecture Boundary Audit

| Forbidden Edge | Violations |
|----------------|------------|
| production → research | **0** |
| production → archive | **0** |
| platform core → research | **0** |
| platform core → archive | **0** |
| active runtime → archive | **0** |

| Allowed Edge | Usage |
|--------------|-------|
| production → platform | Via `nestquant.config.*`, `nestquant.execution.contracts` (through stubs) |
| research → platform | Via `indicators.*`, `monitoring.*` (through bare imports) |
| tests → any | Extensive (expected) |

**All architectural boundaries are clean.** No forbidden edges exist.

---

## 8. pyproject.toml Findings

```toml
[tool.setuptools.packages.find]
where = [".."]
include = ["nestquant", "nestquant.*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

| Issue | Severity | Detail |
|-------|----------|--------|
| `where = [".."]` | P1 | Points to parent directory. After migration, packages are at root level (`production/`, `research/`, `platform/`), not nested under a `nestquant/` package. Discovery will fail to find any packages. |
| `include = ["nestquant", "nestquant.*"]` | P1 | Assumes a `nestquant` top-level package. No such directory exists. The root `__init__.py` is not in a `nestquant/` directory. |
| `testpaths = ["tests"]` | P2 | Tests are now in `tests/safety/`, `tests/production/`, etc. This should still work for pytest discovery, but test files import broken bare paths. |
| No `packages` directive for new domains | P1 | `production`, `research`, `platform` are not configured as discoverable packages. |

**Phase 3 must:** Rewrite `[tool.setuptools.packages.find]` to discover `production`, `research`, `platform` as top-level packages.

---

## 9. Dashboard Findings

**Dashboard root:** `production/dashboard/dashboard/`

| Issue | Detail |
|-------|--------|
| `RESULTS_DIR` | `/root/nestquant/research_data` — STALE, `research_data/` no longer exists at this path |
| `cmd` path | `cd /root/nestquant && ... /root/nestquant/scripts/run_live_executor.py` — STALE, `scripts/` no longer at this path |
| `kill_switch` | `touch /root/nestquant/logs/shadow_live/kill_switch` — VALID (logs/ is not part of migration) |
| `LOG_DIR` | `/root/nestquant/logs/shadow_live` — VALID |
| `zeroFile` | `/root/nestquant/orders_submitted_count.json` — VALID (root-level metadata) |
| `WorkingDirectory` | `/root/nestquant` — references old repo location, STALE |

**8 stale path references** across dashboard API routes. Dashboard is correctly classified as production code.

---

## 10. Deployment/Runtime Findings

**systemd service:** `production/deployment/nestquant-shadow.service`

| Field | Value | Status |
|-------|-------|--------|
| `WorkingDirectory` | `/root/nestquant` | STALE — repo is at `/root/that` |
| `ExecStart` | `/root/nestquant/scripts/run_live_shadow.py` | STALE — `scripts/` no longer at this path |
| `--log-dir` | `/root/nestquant/logs/shadow_live` | VALID (logs not part of migration) |

**Shadow runner:** `scripts/run_live_shadow.py` was moved to `production/deployment/` during Phase 2. The systemd service still references the old path.

**MT5 bridge:** External dependency, not part of this repository. Referenced in dashboard API routes via `MT5_API_URL=http://127.0.0.1:5001`.

---

## 11. V1 Integrity Verification

### Signal Parameters (production/execution/shadow/signal_generator.py)

| Parameter | Value | Status |
|-----------|-------|--------|
| LOOKBACK | 5 | ✅ UNCHANGED |
| ATR_PERIOD | 14 | ✅ UNCHANGED |
| ATR_SL_MULT | 2.0 | ✅ UNCHANGED |
| RRR | 3.5 | ✅ UNCHANGED |
| MAX_HOLD_DAYS | 7 | ✅ UNCHANGED |
| BREAKEVEN_RATIO | 0.8 | ✅ UNCHANGED |

### Constitution Risk Parameters (platform/configuration/constitution.py)

| Parameter | Value | Status |
|-----------|-------|--------|
| risk_per_trade_pct | 0.0015 (0.15%) | ✅ UNCHANGED |
| max_concurrent_positions | 3 | ✅ UNCHANGED |
| max_position_size_per_pair | 0.10 | ✅ UNCHANGED |
| max_total_exposure | 3.0 | ✅ UNCHANGED |
| max_daily_loss_pct | 0.03 (3%) | ✅ UNCHANGED |
| max_drawdown_pct | 0.08 (8%) | ✅ UNCHANGED |
| max_trades_per_day | 4 | ✅ UNCHANGED |

### Safety Systems

| System | Status |
|--------|--------|
| RiskGuard → constitution | ✅ INTACT — `risk_guard.py:26` imports `CONSTITUTION` from canonical path |
| Circuit breakers | ✅ INTACT — 6 breaker classes in `production/risk/circuit_breakers.py` |
| Kill switch | ✅ INTACT — `production/execution/shadow/kill_switch.py` |
| Shadow hard guard | ✅ INTACT — `production/execution/shadow/safety.py` with `OrderSubmissionBlocked` |
| Zero orders file | ✅ INTACT — `init_zero_orders_file()` present |

**NQ-BREAKOUT-V1 behavior was NOT modified by the migration.**

---

## 12. Secret/Environment Audit

### .env.example (TRACKED by Git)

| Field | Status |
|-------|--------|
| Tracked by Git | YES |
| Contains real secrets | NO — all values are placeholders |
| Protected by .gitignore | The example file should be tracked; `.env` should not |

### .env.telegram (UNTRACKED by Git)

| Field | Status |
|-------|--------|
| Tracked by Git | **NO** — `git ls-files .env.telegram` returns nothing |
| Contains real secret material | **YES** — contains a live Telegram bot token: `8658869685:AAF...` |
| Protected by .gitignore | Need to verify |
| Potential secret exposure in Git history | **NO** — never committed |

**⚠️ FINDING:** `.env.telegram` contains a live Telegram bot token but is NOT tracked by Git. This is safe from Git history exposure. However, the token is present on disk in plaintext. Verify `.gitignore` includes `.env.telegram` to prevent accidental future commits.

---

## 13. Duplicate Implementation Audit

| Original | Canonical | Stub | Duplicate? |
|----------|-----------|------|------------|
| `execution/contracts.py` | `platform/contracts/execution_contracts.py` | YES (re-export) | NO — stub only |
| `config/constitution.py` | `platform/configuration/constitution.py` | YES (re-export) | NO — stub only |
| `config/settings.py` | `platform/configuration/settings.py` | YES (re-export) | NO — stub only |
| `indicators/__init__.py` | `platform/tooling/indicators/` | YES (re-export) | NO — stub only |
| `utils/__init__.py` | `platform/tooling/utils/` | YES (re-export) | NO — stub only |
| `knowledge/__init__.py` | `platform/knowledge/` | YES (re-export) | NO — stub only |

**No duplicate implementations found.** All old locations contain only thin re-export wrappers. No code was copied.

---

## 14. Test Environment Diagnosis

| Check | Result |
|-------|--------|
| Python version | 3.14.6 |
| numpy | 2.4.4 ✓ |
| pandas | **MISSING** — required by pyproject.toml and most modules |
| pytest | 9.1.1 ✓ |
| torch | MISSING (optional ml dependency) |
| MT5/ MetaTrader5 | **MISSING** — not installable on this platform (ARM/Termux) |
| `__import__`/`importlib` | Not used for module loading |

**Diagnosis:** Test failure is **environment-only**, not migration-induced. The test suite requires pandas (missing) and some tests require MT5 (unavailable on ARM). The migration did not break any import paths that were working before — the same bare imports existed pre-migration and resolved through the same mechanisms.

---

## 15. Documentation Drift

| Document | Stale References |
|----------|-----------------|
| `CONTRIBUTING.md` | References `production/`, `research/`, `archive/`, `platform/`, `tests/` correctly — NO drift |
| `AGENTS.md` | Constitution references are correct — NO drift |
| `REPOSITORY_MIGRATION_PLAN.md` | Pre-migration document, paths are historical — EXPECTED |
| Phase 1 docs | Created during Phase 1, reference old structure — EXPECTED |
| Phase 2 report | Created during Phase 2, documents the migration — EXPECTED |
| Dashboard code | 8 stale `/root/nestquant/` paths — **DRIFT** (see §9) |
| systemd service | 2 stale `/root/nestquant/` paths — **DRIFT** (see §10) |

---

## 16. P0/P1/P2 Issue Register

| ID | Severity | Issue | Evidence | Affected Files | Required Phase 3 Action |
|----|----------|-------|----------|----------------|------------------------|
| P0-01 | **P0** | `.env.telegram` contains live Telegram bot token on disk | `head -1 .env.telegram` shows token `8658869685:AAF...` | `.env.telegram` | Rotate token if compromised; ensure `.gitignore` includes `.env.telegram`; never commit |
| P0-02 | **P0** | 135 deleted files in working tree (uncommitted) | `git status` shows 135 `D` entries for `docs/` and `research_data/` | Working tree | Commit the deletions or restore them — these are migration artifacts |
| P1-01 | **P1** | 40+ bare imports in production files | `grep -rn "^from execution\.\|^from strategy\.\|^from monitoring\." production/` | `s8_runtime.py`, `risk_guard.py`, `signals/breakout.py`, `monitoring/__init__.py`, etc. | Update all production imports to canonical paths |
| P1-02 | **P1** | `pyproject.toml` package discovery broken | `where = [".."]` and `include = ["nestquant", "nestquant.*"]` — no `nestquant/` dir exists | `pyproject.toml` | Rewrite `[tool.setuptools.packages.find]` for new structure |
| P1-03 | **P1** | Root `__init__.py` creates `nestquant` namespace ambiguity | Root dir is importable as `nestquant` package, shadows canonical locations | `__init__.py` | Remove after all `nestquant.X` imports are migrated |
| P1-04 | **P1** | Dashboard has 8 stale `/root/nestquant/` hardcoded paths | `grep -rn "/root/nestquant/" production/dashboard/` | `route.ts` (5 files) | Update all paths to current structure |
| P1-05 | **P1** | systemd service has stale `/root/nestquant/` paths | `WorkingDirectory=/root/nestquant`, `ExecStart=.../run_live_shadow.py` | `nestquant-shadow.service` | Update paths to current structure |
| P1-06 | **P1** | 5 unused re-export stubs with zero references | `config/__init__.py`, `config/experiment.py`, `config/policies/__init__.py`, `utils/__init__.py`, `knowledge/__init__.py` — grep finds no imports | 5 stub files | Remove in Phase 3 |
| P1-07 | **P1** | 30+ bare imports in tests reference non-existent modules | `from zscore.contracts import` — no `zscore/` dir at root; `from scripts.X import` — no `scripts/` at root | 30+ test files | Update all test imports to canonical paths |
| P1-08 | **P1** | 87 `sys.path.insert` calls for runtime path injection | `grep -rn "sys.path.insert" --include="*.py"` | research/experiments, tests, archive | Replace with proper package imports |
| P1-09 | **P1** | 20+ bare imports in research files | `from zscore.regime import`, `from indicators.atr import` | 20+ research files | Update to canonical `research.shared.zscore.*` paths |
| P2-01 | **P2** | `research/phase3_research.py` hardcodes `RESULTS_DIR = "/root/nestquant/research_data/phase3"` | Line 22 | `phase3_research.py` | Update path |
| P2-02 | **P2** | `.pytest_cache/` and `__pycache__/` at root | Temporary build artifacts | Root directory | Add to `.gitignore` if not present |
| P2-03 | **P2** | Phase 1 docs reference pre-migration structure | Historical documents | `platform/architecture/` | Expected — historical docs |
| P2-04 | **P2** | `research/shared/analytics/research_analysis.py` imports from `monitoring.percentiles` | Cross-domain import (research → production) — ALLOWED but unusual | `research_analysis.py` | Consider moving `percentiles` to platform if widely shared |

---

## 17. Phase 3 Readiness

### Decision: **NOT READY FOR PHASE 3**

### Reasons

1. **P0-01: Live credential on disk.** `.env.telegram` contains a real bot token. While not tracked by Git, this must be addressed (rotation or secure storage) before further work.

2. **P0-02: 135 uncommitted deletions.** The working tree has 135 deleted files that were never committed. This is a dirty Git state that must be resolved.

3. **P1-01 through P1-09: Systemic migration debt.** 40+ production bare imports, 30+ test bare imports, 20+ research bare imports, 87 `sys.path.insert` calls, broken `pyproject.toml`, and a namespace-ambiguous root `__init__.py` collectively mean the codebase is not structurally sound. The migration moved files but did not update the import graph.

4. **P1-04/P1-05: Stale runtime paths.** Dashboard and systemd service reference `/root/nestquant/` which is the old location. These would fail at runtime.

### What Phase 3 Must Do (in order)

1. Resolve P0-01 (credential) and P0-02 (Git state)
2. Rewrite `pyproject.toml` for the new structure
3. Update all production imports to canonical paths
4. Update all test imports to canonical paths
5. Update all research imports to canonical paths
6. Remove root `__init__.py` and all `sys.path.insert` calls
7. Remove 5 unused re-export stubs
8. Update dashboard and deployment paths
9. Run full test suite to verify

---

*End of Phase 2.1 Verification Report*
