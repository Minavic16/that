# Research OS — Build Readiness Assessment

> **Version:** 1.0.0  
> **Date:** 2026-09-21  
> **Status:** Assessment  
> **Constraint:** Read-only — no implementation

---

## 0. Source Documents and Repository Files Inspected

### Architecture/assessment documents:
- `research/NESTQUANT_RESEARCH_OS_ARCHITECTURE_PLAN.md` (590 lines)
- `research/NESTQUANT_RESEARCH_OS_STATE_ASSESSMENT.md` (449 lines)
- `research/R2.1_RESEARCH_OS_GAP_DECISION_MAP.md` (376 lines)
- `core/governance/RESEARCH_OPERATING_SYSTEM.md` (1104 lines)
- `core/governance/STRATEGY_LIFECYCLE.md` (488 lines)
- `core/architecture/REPOSITORY_ARCHITECTURE.md` (305 lines)

### Implementation files:
- `research/shared/engines/base_engine.py` (73 lines)
- `research/shared/engines/backtest_engine.py` (279 lines)
- `research/shared/engines/regime_backtest_engine.py` (266 lines)
- `research/shared/backtest/metrics.py` (122 lines)
- `research/shared/backtest/comparison.py` (274 lines)
- `research/shared/costs/model.py` (111 lines)
- `research/shared/regime/base.py` (76 lines)
- `research/shared/analytics/research_analysis.py` (257 lines)
- `core/contracts/execution_contracts.py` (326 lines)
- `core/contracts/zscore_contracts.py`
- `core/data/loader.py` (170 lines)
- `core/data/validation.py` (222 lines)
- `core/configuration/constitution.py` (45 lines)
- `core/knowledge/experiment_tracker.py` (160 lines)
- `production/signals/base.py` (53 lines)
- `apparatus/models/base.py` (147 lines)
- `apparatus/data/validate.py` (233 lines)
- `apparatus/features/returns.py` (48 lines)
- `apparatus/features/volatility.py` (112 lines)
- `apparatus/config/horizons.py` (33 lines)

### Test files:
- `tests/research/test_engines.py` (205 lines, ~15 tests)
- `tests/research/test_backtest_metrics.py` (105 lines, ~12 tests)
- `tests/research/test_signals.py`
- `research/experiments/strategy2/tests/` (7 files, ~97 tests)

---

## 1. Layer-by-Layer SPECIFIED / IMPLEMENTED / TESTED / INTEGRATED

### Layer 1 — Data Foundation

| Component | SPECIFIED | IMPLEMENTED | TESTED | INTEGRATED | Evidence |
|-----------|-----------|-------------|--------|------------|----------|
| Canonical OHLCV schema | YES (R2.1 spec §C) | **NO** — no shared canonical type | NO | NO | R2.1 defines schema in spec; no shared `MarketData` or `OHLCVBar` type |
| Timestamp handling (UTC) | YES (R2.1 spec §C) | **PARTIAL** — R2.1 validation checks UTC; core DataLoader doesn't enforce | PARTIAL | NO | `apparatus/data/validate.py:validate_timestamps()` checks UTC; `core/data/loader.py` loads pickle without UTC enforcement |
| Session/calendar handling | YES (architecture plan §3.5) | **PARTIAL** — `is_active_session()` exists in production; not reusable | YES (in BacktestEngine) | YES (BacktestEngine uses it) | `nestquant.core.tooling.indicators.session.is_active_session` — exists but in production path |
| Data validation | YES (R2.1 spec §C) | **YES** — two implementations exist | YES | PARTIAL | `apparatus/data/validate.py` (R2.1 Gate 1, 7 tests); `core/data/validation.py` (basic, tested?) |
| Data provenance/versioning | YES (architecture plan §14) | **NO** | NO | NO | Spec defines requirements; no implementation |
| Feature/transform boundaries | YES (R2.1 spec §C9-C10) | **YES** — R2.1 features exist | YES | YES (R2.1 apparatus) | `apparatus/features/returns.py`, `apparatus/features/volatility.py` |
| Data loading (multi-format) | YES (architecture plan §3.1) | **PARTIAL** — pickle only | PARTIAL | YES (used by regime code) | `core/data/loader.py` — DataLoader loads pickle; no bars.jsonl, no Dukascopy |

**Layer 1 verdict:** Validation exists. Canonical representation does NOT exist. Two parallel validation implementations. No provenance.

### Layer 2 — Market Simulation

| Component | SPECIFIED | IMPLEMENTED | TESTED | INTEGRATED | Evidence |
|-----------|-----------|-------------|--------|------------|----------|
| Market state | YES (architecture plan §7) | **NO** | NO | NO | Not implemented |
| Event progression | YES | **NO** | NO | NO | Not implemented |
| Prices/bars/ticks | YES | **NO** (simulator) | NO | NO | BacktestEngine receives bars, but no formal simulator |
| Spread/commission/slippage | YES (architecture plan §7.3) | **PARTIAL** — hardcoded in BacktestConfig | YES (in BacktestEngine tests) | YES (BacktestEngine) | `BacktestConfig` has spread_pips, slippage_pips, commission_per_lot; also `research/shared/costs/model.py` has reusable cost functions |
| Latency | YES | **NO** | NO | NO | Not implemented |
| Orders/fills | YES (architecture plan §7.4) | **NO** — BacktestEngine does inline execution | NO | NO | No formal Order/Fill types |
| Positions/account state | YES | **PARTIAL** — inline in BacktestEngine | YES (in BacktestEngine tests) | YES (BacktestEngine) | `BacktestEngine._balance`, `_peak_balance`, `Trade` dataclass |

**Layer 2 verdict:** No formal simulator. BacktestEngine does inline execution simulation. CostModel exists but is not used by BacktestEngine.

### Layer 3 — Canonical Backtester

| Component | SPECIFIED | IMPLEMENTED | TESTED | INTEGRATED | Evidence |
|-----------|-----------|-------------|--------|------------|----------|
| Strategy/model interface | YES (architecture plan §4) | **YES** — two interfaces | YES | YES | `BaseSignal` (trading); `VolatilityModel` (forecasting) |
| Signal/order flow | YES | **PARTIAL** — BaseSignal → BacktestEngine inline | YES | YES | `BacktestEngine.on_bar()` takes `BaseSignal` |
| Simulator integration | YES | **NO** — no formal simulator | NO | NO | BacktestEngine does inline simulation |
| Portfolio/account integration | YES | **PARTIAL** — inline in BacktestEngine | YES | YES (BacktestEngine) | No standalone portfolio module |
| Result generation | YES | **YES** — BacktestEngine.get_results() | YES | YES | Returns dict with metrics |
| Reproducibility | YES | **NO** | NO | NO | No seed handling, no config snapshot |

**Layer 3 verdict:** BacktestEngine works end-to-end for trading signals. BUT it imports from `production/` (architecture violation). No standalone portfolio, no simulator integration, no reproducibility.

### Layer 4 — Evaluation

| Component | SPECIFIED | IMPLEMENTED | TESTED | INTEGRATED | Evidence |
|-----------|-----------|-------------|--------|------------|----------|
| Evaluation abstraction | YES (architecture plan §8) | **NO** | NO | NO | No formal evaluation pipeline |
| Metric abstraction | YES | **PARTIAL** — BacktestMetrics (P&L-based) | YES | YES (BacktestEngine) | `research/shared/backtest/metrics.py` — 16 P&L metrics; no forecast error metrics |
| IS/OOS | YES (architecture plan §6) | **NO** | NO | NO | Not implemented |
| Fold evaluation | YES | **NO** | NO | NO | Not implemented |
| Aggregation | YES | **NO** | NO | NO | Not implemented |
| Robustness | YES (architecture plan §9) | **NO** | NO | NO | No bootstrap/MC |

**Layer 4 verdict:** Only BacktestMetrics exists (P&L domain). No evaluation pipeline. No IS/OOS. No fold evaluation.

### Layer 5 — Research Provenance

| Component | SPECIFIED | IMPLEMENTED | TESTED | INTEGRATED | Evidence |
|-----------|-----------|-------------|--------|------------|----------|
| Experiment identity | YES (architecture plan §14) | **PARTIAL** — ExperimentTracker | NO | NO | `core/knowledge/experiment_tracker.py` — basic, no git commit, no config snapshot |
| Configuration | YES | **PARTIAL** — ConstitutionRiskConfig, horizons | NO | NO | Two config implementations; no unified hierarchy |
| Dataset/version | YES | **NO** | NO | NO | No data versioning |
| Code/version | YES | **NO** | NO | NO | No git commit tracking |
| Result artifacts | YES | **PARTIAL** — ExperimentTracker.log_artifact | NO | NO | File path only, no structured storage |
| Research ledger | YES (architecture plan §14.3) | **NO** | NO | NO | Not implemented |

**Layer 5 verdict:** ExperimentTracker is minimal (name, params, metrics, artifacts). No provenance, no config snapshot, no data versioning, no ledger.

### Layer 6 — Reporting / ROS

| Component | SPECIFIED | IMPLEMENTED | TESTED | INTEGRATED | Evidence |
|-----------|-----------|-------------|--------|------------|----------|
| Machine-readable results | YES | **NO** | NO | NO | No JSON/structured output |
| Human-readable reports | YES | **PARTIAL** — R2.1 Phase 1 text report | NO | NO | `research/experiments/strategy2/R2.1_phase1_experiment.py` |
| Experiment comparison | YES | **PARTIAL** — ABComparison | NO | NO | `research/shared/backtest/comparison.py` — 274 lines |
| Provenance display | YES | **NO** | NO | NO | Not implemented |

**Layer 6 verdict:** ABComparison exists but is not tested. No structured reporting.

---

## 2. Critical Dependency Graph

### Derived from repository (not assumed):

```
Data Foundation
  │
  ├── DataLoader (core/data/loader.py) — pickle loading, no canonical type
  ├── DataValidationReport (core/data/validation.py) — basic
  ├── Gate 1 Validation (apparatus/data/validate.py) — R2.1-specific
  └── Features (apparatus/features/) — R2.1-specific
      │
      ▼
Execution Contracts (core/contracts/execution_contracts.py) — EXISTS, tested
  │
  ├── TradeIntent
  ├── RiskDecision  
  ├── OrderRequest
  └── ExecutionResult
      │
      ▼
Signal Interface (production/signals/base.py) — EXISTS, in production path
  │
  └── BaseSignal.generate(df, pair) → SignalResult
      │
      ▼
BacktestEngine (research/shared/engines/backtest_engine.py) — EXISTS, tested
  │  ⚠️ imports from production/ (BreakerSuite, BaseSignal)
  │  ⚠️ imports from core.tooling (is_active_session)
  │  ⚠️ inline execution simulation (no formal simulator)
  │  ⚠️ inline portfolio tracking (no standalone module)
  │  ⚠️ hardcoded costs (doesn't use CostModel)
      │
      ▼
BacktestMetrics (research/shared/backtest/metrics.py) — EXISTS, tested
  │  P&L-based: Sharpe, drawdown, win rate, etc.
      │
      ▼
ExperimentTracker (core/knowledge/experiment_tracker.py) — EXISTS, minimal
      │
      ▼
ABComparison (research/shared/backtest/comparison.py) — EXISTS, not tested
```

### What this graph reveals:

1. **BacktestEngine is the only end-to-end working pipeline.** It is the de facto canonical backtester for trading signals.

2. **BacktestEngine has 3 architecture violations:**
   - Imports `BreakerSuite` from `production/risk/circuit_breakers`
   - Imports `BaseSignal` from `production/signals/base`
   - Imports `is_active_session` from `core.tooling.indicators.session`

3. **Execution contracts exist but are not used by BacktestEngine.** The engine has its own inline `Trade` dataclass instead of using `TradeIntent → RiskDecision → OrderRequest → ExecutionResult`.

4. **CostModel exists but is not used by BacktestEngine.** The engine hardcodes spread/commission/slippage in `BacktestConfig` instead of using `research/shared/costs/model.py`.

5. **Two parallel validation implementations:** `core/data/validation.py` (basic) and `apparatus/data/validate.py` (R2.1 Gate 1). Neither is the canonical data layer.

6. **No canonical market data type.** Both BacktestEngine and R2.1 use raw `pd.DataFrame` with implicit schema expectations. No shared `MarketBar` or `OHLCV` dataclass.

7. **No evaluation pipeline.** BacktestMetrics computes P&L metrics. No IS/OOS, no fold evaluation, no forecast error metrics.

---

## 3. Candidate Starting Points — Explicit Evaluation

### Candidate 1: Canonical Data Layer

| Attribute | Assessment |
|-----------|------------|
| Dependencies | None (standalone) |
| Current implementation | **PARTIAL** — DataLoader (pickle), two validation implementations, R2.1 features. No canonical OHLCV type. |
| Current tests | **PARTIAL** — R2.1 validation has 7 tests; core validation has tests; DataLoader untested |
| Downstream unlocks | Simulator, backtester, evaluation, provenance — ALL depend on a shared data representation |
| Architectural risk | **LOW** — adding a canonical dataclass is additive; no existing code breaks |
| Estimated scope | **SMALL** — ~200-300 lines for OHLCV type + validation wrapper + tests |
| Safe to make canonical now? | **YES** — the primitives already exist in two places; consolidation is the right first step |

### Candidate 2: Market Simulator

| Attribute | Assessment |
|-----------|------------|
| Dependencies | Canonical data layer, execution model, cost model |
| Current implementation | **NONE** — BacktestEngine does inline simulation |
| Current tests | **NONE** |
| Downstream unlocks | Backtester (formal), evaluation |
| Architectural risk | **HIGH** — wide design space; wrong abstraction locks in bad architecture |
| Estimated scope | **LARGE** — 500-1000 lines + tests |
| Safe to make canonical now? | **NO** — depends on data layer; design needs validation against real use cases |

### Candidate 3: Execution Model

| Attribute | Assessment |
|-----------|------------|
| Dependencies | Execution contracts (exist) |
| Current implementation | **PARTIAL** — `core/contracts/execution_contracts.py` exists (TradeIntent, RiskDecision, OrderRequest, ExecutionResult) |
| Current tests | **UNKNOWN** — contracts have `validate()` methods but no dedicated tests found |
| Downstream unlocks | Simulator, portfolio |
| Architectural risk | **LOW** — contracts are already defined; implementation is thin |
| Estimated scope | **SMALL** — contracts exist; need adapter layer |
| Safe to make canonical now? | **PARTIAL** — contracts exist but BacktestEngine doesn't use them. Making them canonical requires also making BacktestEngine use them (refactoring). |

### Candidate 4: Portfolio/Account Layer

| Attribute | Assessment |
|-----------|------------|
| Dependencies | Execution model, positions |
| Current implementation | **PARTIAL** — inline in BacktestEngine (`_balance`, `_peak_balance`, `Trade`) |
| Current tests | **YES** — via BacktestEngine tests |
| Downstream unlocks | Evaluation (equity curve), risk management |
| Architectural risk | **MEDIUM** — extracting from BacktestEngine requires refactoring |
| Estimated scope | **MEDIUM** — ~200-400 lines to extract + tests |
| Safe to make canonical now? | **NO** — requires BacktestEngine refactoring; blocked by architecture violations |

### Candidate 5: Canonical Backtester

| Attribute | Assessment |
|-----------|------------|
| Dependencies | Data layer, signal interface, execution model, portfolio, cost model |
| Current implementation | **YES** — BacktestEngine works end-to-end for trading signals |
| Current tests | **YES** — ~15 tests in `test_engines.py` |
| Downstream unlocks | Evaluation, provenance |
| Architectural risk | **MEDIUM** — BacktestEngine exists but has production imports |
| Estimated scope | **MEDIUM** — fix imports (~50 lines) + add canonical data consumption (~100 lines) |
| Safe to make canonical now? | **NO** — has architecture violations; must fix imports first. Also, "canonical" means it works for BOTH trading signals AND volatility forecasting — BacktestEngine only does trading. |

### Candidate 6: Evaluation Framework

| Attribute | Assessment |
|-----------|------------|
| Dependencies | Backtester (or model interface), metrics |
| Current implementation | **PARTIAL** — BacktestMetrics (P&L domain only) |
| Current tests | **YES** — 12 tests for BacktestMetrics |
| Downstream unlocks | Provenance, reporting |
| Architectural risk | **MEDIUM** — needs to work for both P&L and forecast error domains |
| Estimated scope | **LARGE** — evaluation pipeline + metric abstraction + IS/OOS + fold evaluation |
| Safe to make canonical now? | **NO** — depends on backtester; design needs validation |

### Candidate 7: Research Ledger/Provenance

| Attribute | Assessment |
|-----------|------------|
| Dependencies | None (standalone) |
| Current implementation | **MINIMAL** — ExperimentTracker (160 lines, no provenance) |
| Current tests | **UNKNOWN** |
| Downstream unlocks | Reporting, reproducibility |
| Architectural risk | **LOW** — additive; no existing code breaks |
| Estimated scope | **MEDIUM** — ~300-500 lines for ledger + provenance + tests |
| Safe to make canonical now? | **YES** — but lower priority than data layer |

---

## 4. Selection: THE FIRST BUILDABLE ROS COMPONENT

### Selected: Canonical Data Layer

### Why this component:

1. **It is the foundation of everything else.** Every downstream component (simulator, backtester, evaluation, provenance) needs a shared data representation. Without it, every component re-invents its own data handling.

2. **It is reusable across multiple future research programs.** Any research program that works with OHLCV data (R2.1, future strategy research, signal discovery) needs this layer.

3. **Its interface can be frozen cleanly.** An OHLCV bar is a well-understood financial data structure. The interface is stable by nature.

4. **It can be implemented and tested without requiring the entire Research OS.** It is a standalone data type + validation + loading utilities.

5. **It reduces rather than increases architectural duplication.** Currently there are TWO validation implementations and NO shared data type. Consolidation reduces duplication.

6. **It does not belong specifically to R2.1.** R2.1 has its own data validation in `apparatus/data/validate.py`, but the canonical data layer is a shared primitive.

7. **The primitives already exist.** DataLoader, validation, features — they just need to be unified under a canonical type.

---

## 5. Duplication Rule — Existing Code Assessment

### What should be REUSED (import as-is):
- `apparatus/features/returns.py:compute_log_returns` — clean, tested, reusable
- `apparatus/features/volatility.py:realized_volatility_forward` — clean, tested, reusable
- `apparatus/features/volatility.py:realized_volatility_backward` — clean, tested, reusable
- `apparatus/config/horizons.py:HORIZONS` — clean, tested, reusable

### What should be WRAPPED (adapt to canonical interface):
- `core/data/loader.py:DataLoader` — wraps into canonical data loading interface
- `apparatus/data/validate.py:run_all_validations` — wraps into canonical validation
- `research/shared/costs/model.py:compute_costs` — wraps into canonical cost model

### What should be MIGRATED LATER (after canonical data layer exists):
- `BacktestEngine` — migrate to consume canonical OHLCV type instead of raw DataFrame
- `RegimeBacktestEngine` — same migration
- `research/shared/backtest/comparison.py` — migrate to use canonical types

### What should be LEFT FROZEN (legacy, not touched):
- `research/experiments/strategy2/volatility_models.py` — Phase 1 legacy
- `research/experiments/strategy2/data_loader.py` — Phase 1 legacy (hardcoded VPS path)
- `research/experiments/strategy2/causality_tests.py` — Phase 1 legacy

### What should be DEPRECATED EVENTUALLY:
- `research/experiments/zscore_mr_backtest.py` — duplicates BacktestEngine
- `research/experiments/exit_surface.py:run_raw_backtest` — duplicates BacktestEngine
- `research/experiments/exit_forensics.py:run_backtest` — duplicates BacktestEngine
- `research/experiments/signal_discovery.py:run_backtest` — duplicates BacktestEngine

---

## 6. R2.1 Boundary

### R2.1 components that can continue INDEPENDENTLY of Research OS:
- VolatilityModel protocol (frozen, tested)
- 6 model implementations (Stage 3B — not blocked by Research OS)
- R2.1-specific evaluation (walk-forward, blocked temporal, forecast metrics)
- R2.1 Gate 1 validation (already exists)

### R2.1 components that should eventually CONSUME the Research OS:
- Data loading — currently uses legacy `data_loader.py`; should eventually use canonical DataLoader
- Data validation — currently uses `apparatus/data/validate.py`; should eventually use canonical validation (or layer on top)
- Provenance — currently has no provenance; should eventually use Research OS ledger

### What the Research OS should NOT become:
- It should NOT be R2.1-specific. The canonical data layer must work for ANY OHLCV research, not just volatility forecasting.
- It should NOT import from `apparatus/` (R2.1-specific code).
- It should NOT depend on R2.1's VolatilityModel protocol (that's a model-layer interface, not a data-layer interface).

---

## 7. RESEARCH OS CURRENT PHASE

**Phase: Foundation Implementation — Starting Point Identified**

The Research OS has:
- Architecture: FROZEN (590-line plan)
- Specification: COMPLETE (ROS spec, lifecycle, contracts)
- Data foundation: PRIMITIVES EXIST (no canonical type)
- Simulator: NOT STARTED
- Backtester: WORKING (with architecture violations)
- Evaluation: MINIMAL (P&L metrics only)
- Provenance: MINIMAL (ExperimentTracker)
- Reporting: NOT STARTED

---

## 8. FIRST BUILD COMPONENT

### Canonical Data Layer

---

## 9. WHY THIS COMPONENT

1. **Foundation dependency:** Every downstream component needs a shared data representation.
2. **Reducing duplication:** Two parallel validation implementations exist; no shared type.
3. **Reusable:** Works for any OHLCV research program, not just R2.1.
4. **Testable standalone:** Can be built and tested without the rest of the ROS.
5. **Low risk:** Additive change; no existing code breaks.
6. **Primitives exist:** DataLoader, validation, features — need unification.

---

## 10. IMPLEMENTATION SCOPE

### Objective

Create a canonical OHLCV market data representation with validation, loading, and feature boundaries — the shared data primitive for all Research OS components.

### Why it comes first

Every downstream component (simulator, backtester, evaluation, provenance) needs a shared data representation. Without it, every component re-invents its own data handling. The primitives already exist in two places (core/data and apparatus/data); consolidation is the natural first step.

### Exact files/modules to create or modify

| # | File | What | Lines (est.) |
|---|------|------|-------------|
| 1 | `research/shared/data/__init__.py` | Package init | 1 |
| 2 | `research/shared/data/types.py` | `MarketBar` dataclass, `OHLCVFrame` type alias, `Timestamp` type | ~80 |
| 3 | `research/shared/data/schema.py` | Schema definition, column names, types, constraints | ~60 |
| 4 | `research/shared/data/validate.py` | Canonical validation (unified from two existing implementations) | ~150 |
| 5 | `research/shared/data/loader.py` | Canonical DataLoader (wrap `core/data/loader.py` + extend) | ~100 |
| 6 | `research/shared/data/features.py` | Re-export `compute_log_returns`, `realized_volatility_forward/backward` | ~20 |
| 7 | `tests/research/test_data_types.py` | Unit tests for MarketBar, OHLCVFrame, schema | ~100 |
| 8 | `tests/research/test_data_validate.py` | Unit tests for canonical validation | ~120 |
| 9 | `tests/research/test_data_loader.py` | Unit tests for DataLoader | ~80 |

**Total:** ~700 lines (implementation + tests)

### Interfaces that will become canonical

```python
# research/shared/data/types.py

@dataclass(frozen=True)
class MarketBar:
    """Single OHLCV bar — the atomic unit of market data."""
    timestamp: pd.Timestamp  # UTC, timezone-aware
    pair: str                 # "EUR/USD"
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float | None = None

    def validate(self) -> list[str]:
        """Self-validation. Returns empty list if valid."""

# Type alias for bar collections
OHLCVFrame = pd.DataFrame  # DatetimeIndex, columns: open, high, low, close, volume, spread

# research/shared/data/schema.py

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume", "spread"]
OHLCV_COLUMN_TYPES = {"open": float, "high": float, "low": float, "close": float, "volume": float}

# research/shared/data/validate.py

@dataclass
class ValidationResult:
    name: str
    passed: bool
    message: str
    severity: str = "ERROR"

def validate_ohlcv(df: OHLCVFrame, pair: str | None = None) -> list[ValidationResult]:
    """Run all canonical OHLCV validation checks."""

def validate_timestamps(df: OHLCVFrame) -> ValidationResult: ...
def validate_4h_alignment(df: OHLCVFrame) -> ValidationResult: ...
def validate_prices(df: OHLCVFrame) -> ValidationResult: ...
def validate_duplicates(df: OHLCVFrame) -> ValidationResult: ...
def validate_gaps(df: OHLCVFrame) -> ValidationResult: ...
def validate_schema(df: OHLCVFrame) -> ValidationResult: ...

# research/shared/data/loader.py

class DataLoader:
    """Canonical data loader for OHLCV data."""
    def load(self, pair: str, timeframe: str = "4h") -> OHLCVFrame: ...
    def load_all(self, pairs: list[str], timeframe: str = "4h") -> dict[str, OHLCVFrame]: ...

# research/shared/data/features.py — re-exports
from apparatus.features.returns import compute_log_returns
from apparatus.features.volatility import realized_volatility_forward, realized_volatility_backward
```

### Explicit non-goals

| Not implementing | Why |
|------------------|-----|
| Market simulator | Separate component; depends on data layer |
| Backtester refactoring | Out of scope for this stage |
| R2.1-specific validation | Stays in `apparatus/data/validate.py` |
| Data ingestion (Dukascopy) | Future work; current DataLoader wraps pickle |
| Data versioning/provenance | Future stage |
| Feature engineering beyond re-exports | Future stage |

### Unit tests

1. `test_market_bar_creation` — create valid MarketBar
2. `test_market_bar_validation` — price constraints, positive volume
3. `test_market_bar_immutability` — frozen dataclass
4. `test_ohlcv_frame_schema` — correct columns, correct types
5. `test_validate_timestamps_utc` — reject non-UTC
6. `test_validate_timestamps_monotonic` — reject non-monotonic
7. `test_validate_4h_alignment` — accept valid, reject invalid
8. `test_validate_prices` — H>=L, H>=O, H>=C, L<=O, L<=C, all>0
9. `test_validate_duplicates` — reject duplicates
10. `test_validate_gaps` — detect weekend, holiday, corruption gaps
11. `test_validate_schema` — missing columns, wrong types
12. `test_validate_ohlcv_composite` — all checks together
13. `test_data_loader_single_pair` — load one pair
14. `test_data_loader_all_pairs` — load multiple pairs
15. `test_data_loader_missing_file` — graceful error

### Integration tests

1. `test_ohlcv_through_validation` — load data → validate → pass
2. `test_ohlcv_with_features` — load data → compute returns → compute volatility
3. `test_backtest_engine_consumes_ohlcv` — verify BacktestEngine works with canonical type (if backward-compatible)

### Acceptance criteria

1. `MarketBar` dataclass exists, is frozen, has self-validation
2. `OHLCVFrame` type alias is defined with correct schema
3. `validate_ohlcv()` runs all validation checks and returns `list[ValidationResult]`
4. `DataLoader.load()` returns a properly typed `OHLCVFrame`
5. All existing tests pass (97 R2.1 tests + 27 research tests)
6. New tests pass (~15 unit + 3 integration)
7. No imports from `production/` or `apparatus/` in `research/shared/data/`
8. The canonical data layer is used by ZERO existing components yet (additive, not replacing)

---

## 11. WHAT THIS UNLOCKS

After the canonical data layer is complete:

1. **Backtester migration (next stage):** BacktestEngine can be migrated to consume `OHLCVFrame` instead of raw DataFrame. This fixes the architecture violation (remove production imports) and makes the backtester reusable.

2. **Simulator construction:** A formal market simulator can be built on top of the canonical data type.

3. **Evaluation framework:** Evaluation can consume canonical data + canonical backtester output.

4. **R2.1 data unification:** R2.1 can use the canonical DataLoader instead of its legacy data_loader.py.

5. **Provenance:** Data versioning can attach to the canonical type.

---

## 12. NEXT TWO COMPONENTS AFTER IT

### Component 2: Backtester Decoupling

- **Objective:** Remove architecture violations from BacktestEngine (remove production imports); make it consume canonical OHLCVFrame; extract standalone portfolio module
- **Why:** BacktestEngine is the only working end-to-end pipeline; making it canonical enables all downstream work
- **Scope:** ~300-500 lines (import fixes + portfolio extraction + tests)

### Component 3: Evaluation Abstraction

- **Objective:** Build evaluation pipeline with metric abstraction (P&L metrics + forecast error metrics), fold evaluation, IS/OOS
- **Why:** Evaluation is the core research output; currently only BacktestMetrics exists
- **Scope:** ~500-800 lines (evaluation engine + metric abstraction + tests)

---

## 13. DECISION

```
RESEARCH OS CURRENT PHASE
  Foundation Implementation — Starting Point Identified

FIRST BUILD COMPONENT
  Canonical Data Layer (research/shared/data/)

WHY THIS COMPONENT
  Foundation dependency for all downstream components.
  Primitives exist in two places; consolidation reduces duplication.
  Reusable across all research programs.
  Testable standalone. Low risk. Additive change.

IMPLEMENTATION SCOPE
  ~700 lines across 9 files (6 implementation + 3 test files).
  MarketBar dataclass, OHLCVFrame type, canonical validation,
  canonical DataLoader, feature re-exports.

NON-GOALS
  No simulator. No backtester refactoring. No R2.1-specific work.
  No data ingestion. No versioning. No feature engineering.

ACCEPTANCE CRITERIA
  MarketBar exists with validation. OHLCVFrame typed.
  validate_ohlcv() runs all checks. DataLoader loads canonical data.
  All existing tests pass. ~18 new tests pass.
  Zero imports from production/ or apparatus/.

WHAT THIS UNLOCKS
  Backtester migration (fix architecture violations).
  Formal simulator construction.
  Evaluation framework.
  R2.1 data unification.
  Provenance/data versioning.

NEXT TWO COMPONENTS AFTER IT
  1. Backtester Decoupling (remove production imports, extract portfolio)
  2. Evaluation Abstraction (metric pipeline, fold evaluation, IS/OOS)
```

---

*End of Research OS Build Readiness Assessment*
