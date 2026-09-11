# NestQuant Strategy Identity Remediation Proposal
> Generated: 2026-09-09 | Branch: master | Commit: d898669
> **STATUS: PROPOSAL — DO NOT EXECUTE UNTIL APPROVED**

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Current Strategy Definitions](#2-current-strategy-definitions)
3. [Import/Dependency Graph](#3-importdependency-graph)
4. [Canonical Strategy Contract](#4-canonical-strategy-contract)
5. [Recommended Changes](#5-recommended-changes)
6. [Migration Order](#6-migration-order)
7. [Regression Requirements](#7-regression-requirements)
8. [Safety Checklist](#8-safety-checklist)

---

## 1. Executive Summary

The NestQuant codebase contains **multiple conflicting definitions** of the trading strategy. This creates a strategy-identity ambiguity where different modules define different parameters for the same strategy, and some modules export signals that use wrong parameters.

### The Problem

There are **four separate configuration sources** and **two signal implementations**, creating a matrix of contradictions:

| Source | ATR Mult | RRR | BE | Max Hold | Status |
|--------|----------|-----|----|----------|--------|
| `signals/breakout.py` RESEARCH_DEFAULTS | **2.0** | **3.5** | **ABSENT** | **ABSENT** | ✅ CANONICAL (source of truth) |
| `execution/shadow/signal_generator.py` STRATEGY_PARAMS | **2.0** | **3.5** | **0.8** | **7d** | ⚠️ Signal correct, lifecycle extras |
| `config/experiment.py` StrategyIdentity | **2.0** | **3.5** | **0.8** | **7d** | ⚠️ Config-only, not imported by signal |
| `config/settings.py` StrategyConfig | **3.0** | **2.0** | **1.5** | — | ❌ **WRONG** (legacy GFT values) |
| Root `config.py` | **2.0** | **3.5** | **0.8** | **7d** | 🗑️ Dead GFT legacy |

### The Impact

1. **`signals/structured_entry.py`** imports from `config/settings.py` and uses **ATR=3.0, RRR=2.0** — wrong parameters for the canonical strategy
2. **`signals/__init__.py`** exports `StructuredEntrySignal` alongside `BreakoutSignal` as if both are valid production signals
3. **`signals/breakout.py`** (canonical) does NOT implement breakeven/max_hold/trailing — but the shadow runner and S8 runtime DO apply them during position lifecycle
4. **`canonical_identity.py`** documents breakeven/max_hold as "absently absent" from the deployed strategy — but the live executor (`live_executor.py`) actively uses them

### The Resolution

Establish `signals/breakout.py` RESEARCH_DEFAULTS as the **single source of truth** for signal generation parameters. Separately, recognize that **breakeven, max_hold, and trailing_stop** are **position lifecycle parameters** — not signal parameters — and they are correctly implemented in the execution layer (`strategy/trade_management/`).

**Key distinction**: Signal generation (entry) vs. Position lifecycle (exit management) are separate concerns with separate parameter sets.

---

## 2. Current Strategy Definitions

### A. Definition Table

| Definition | ATR | RRR | Lifecycle | Production Reachable? | Classification |
|-----------|-----|-----|-----------|----------------------|----------------|
| `signals/breakout.py` RESEARCH_DEFAULTS | 2.0 | 3.5 | None (signal only) | ✅ YES — canonical signal | **CANONICAL** |
| `execution/shadow/signal_generator.py` STRATEGY_PARAMS | 2.0 | 3.5 | BE=0.8, MH=7d | ✅ YES — shadow pipeline | **PRODUCTION** (shadow) |
| `config/experiment.py` StrategyIdentity | 2.0 | 3.5 | BE=0.8, MH=7d, Trail=True | ⚠️ Only via test_s8_experiment | **EXPERIMENTAL** (config-only) |
| `config/settings.py` StrategyConfig | 3.0 | 2.0 | BE=1.5 | ⚠️ structured_entry.py + shadow lazy imports | **LEGACY** (wrong values) |
| Root `config.py` | 2.0 | 3.5 | BE=0.8, MH=7d | 🗑️ Only legacy root files + scripts | **DEAD** |
| `signals/structured_entry.py` | 3.0 | 2.0 | None | ⚠️ Exported in __init__.py, tests | **WRONG** (uses legacy config) |

### B. Signal Generation vs. Position Lifecycle — The Critical Distinction

The codebase has two separate concerns that are currently conflated:

**Signal Generation** (decides WHEN to enter):
- Defined in: `signals/breakout.py` (canonical) and `execution/shadow/signal_generator.py` (shadow)
- Parameters: lookback=5, atr_period=14, atr_sl_mult=2.0, rrr=3.5
- These are **identical** in both files ✅

**Position Lifecycle** (decides WHEN to exit/manage):
- Defined in: `strategy/trade_management/breakeven.py`, `max_hold.py`, `trailing_stop.py`
- Implemented in: `execution/shadow/runner.py` (ShadowPosition), `execution/shadow/live_executor.py` (LiveExecutionRunner), `execution/s8_runtime.py` (LifecycleRegistry)
- Parameters: breakeven_ratio=0.8, max_hold_days=7, trailing_enabled=True
- These are **consistent across all execution paths** ✅

**The confusion**: `canonical_identity.py` lists breakeven/max_hold/trailing as "absent features" from the *deployed strategy*. This is correct for **signal generation** (breakout.py does not have them). But it is misleading for **position lifecycle** (the execution layer does use them).

### C. `signals/structured_entry.py` — Complete Trace

**Upstream (what it imports from):**
| Module | Import |
|--------|--------|
| `nestquant.config.settings` | `ATR_PERIOD=14`, `ATR_SL_MULTIPLIER=3.0`, `MACRO_EMA_PERIOD=200`, `RRR=2.0` |
| `nestquant.indicators.adx` | `calculate_adx` |
| `nestquant.indicators.atr` | `calculate_atr` |
| `nestquant.indicators.ema` | `calculate_ema` |
| `nestquant.signals.base` | `BaseSignal`, `SignalResult` |

**Downstream (what imports it):**
| File | Import | Type |
|------|--------|------|
| `signals/__init__.py:5` | `from nestquant.signals.structured_entry import StructuredEntrySignal` | Re-export |
| `signals/__init__.py:11` | `"StructuredEntrySignal"` in `__all__` | Export list |
| `tests/test_imports.py:29` | `"nestquant.signals.structured_entry"` | String reference |
| `tests/test_signals.py:11` | `from nestquant.signals.structured_entry import StructuredEntrySignal` | Import |
| `tests/test_signals.py:87` | `class TestStructuredEntrySignal` | Test class |
| `tests/test_signals.py:94,99` | `StructuredEntrySignal()` | Instantiation |

**NOT referenced by:**
- ❌ Any execution code (`execution/`)
- ❌ Any shadow code (`execution/shadow/`)
- ❌ Any script (`scripts/`)
- ❌ Any dashboard/API code (`dashboard/`)
- ❌ Any production signal path

**Strategy semantics**: EMA200 pullback logic with ADX filter. Completely different signal logic from the canonical breakout (swing-based). Uses ATR=3.0/RRR=2.0 from wrong config.

**Conclusion**: `signals/structured_entry.py` is **dead code** from a different strategy family (MR+TF). It is not reachable from any production execution path. It uses wrong parameters. It should be archived.

### D. `config/experiment.py` — Complete Trace

**Upstream (what it imports from):**
| Module | Import |
|--------|--------|
| `hashlib`, `json`, `uuid` | Standard library |
| `dataclasses`, `datetime` | Standard library |

No external dependencies. Self-contained configuration definition.

**Downstream (what imports it):**
| File | Import | Type |
|------|--------|------|
| `tests/test_s8_experiment.py:26` | `from config.experiment import (ExperimentConfig, ExperimentPhase, ...)` | Test import |

**NOT imported by:**
- ❌ Any execution code
- ❌ Any shadow code
- ❌ Any production signal path
- ❌ Any script (research scripts hardcode their own values)

**Breakeven/MaxHold lineage**: The `StrategyIdentity` in experiment.py declares `breakeven_ratio=0.8, breakeven_enabled=True, max_hold_days=7, max_hold_bars=42, trailing_enabled=True`. These match the **research-validated lifecycle parameters** used in:
- `execution/shadow/signal_generator.py` STRATEGY_PARAMS (BE=0.8, MH=7)
- `execution/shadow/runner.py` ShadowPosition (MH=42 bars, BE=0.8)
- `execution/shadow/live_executor.py` (BE=0.8, MH=42)
- `execution/s8_runtime.py` LifecycleRegistry (BE=0.8, MH=7d, Trail=True)
- `strategy/trade_management/breakeven.py` (BE=0.8)
- `strategy/trade_management/max_hold.py` (MH=7 days)
- `strategy/trade_management/trailing_stop.py` (Trail enabled)

**All S0-S6 research scripts** hardcode `BREAKEVEN_RATIO=0.8, MAX_HOLD_DAYS=7` locally.

**Classification**: `config/experiment.py` is a **configuration-as-documentation** module. It correctly records the validated lifecycle parameters. It is not imported by production execution. Its values ARE correct for the validated strategy lifecycle. It should remain as **experimental/identity documentation** but should NOT be the runtime source of truth for lifecycle parameters (those are hardcoded in the execution layer).

---

## 3. Import/Dependency Graph

### 3.1 `signals/structured_entry.py` Dependency Chain

```
signals/structured_entry.py
├── IMPORTS FROM:
│   ├── nestquant.config.settings → ATR_PERIOD=14, ATR_SL_MULTIPLIER=3.0, MACRO_EMA_PERIOD=200, RRR=2.0
│   ├── nestquant.indicators.adx → calculate_adx
│   ├── nestquant.indicators.atr → calculate_atr
│   ├── nestquant.indicators.ema → calculate_ema
│   └── nestquant.signals.base → BaseSignal, SignalResult
│
├── IMPORTED BY:
│   ├── signals/__init__.py → re-exports StructuredEntrySignal
│   ├── tests/test_imports.py → string reference
│   └── tests/test_signals.py → imports + TestStructuredEntrySignal class
│
└── NOT REACHABLE FROM:
    ├── execution/ ❌
    ├── execution/shadow/ ❌
    ├── scripts/ ❌
    └── dashboard/ ❌
```

### 3.2 `signals/breakout.py` Dependency Chain

```
signals/breakout.py
├── IMPORTS FROM:
│   ├── nestquant.indicators.atr → calculate_atr
│   ├── nestquant.indicators.swing → swing_high_series, swing_low_series
│   └── nestquant.signals.base → BaseSignal, SignalResult
│
├── IMPORTED BY:
│   ├── signals/__init__.py → re-exports BreakoutSignal
│   ├── execution/shadow/signal_generator.py → imports swing/atr directly (same logic)
│   ├── tests/test_signals.py → imports BreakoutSignal
│   ├── tests/test_s8_strategy_fidelity.py → validates RESEARCH_DEFAULTS
│   └── backtest/comparison.py → via signals.base
│
└── REACHABLE FROM (production):
    ├── execution/shadow/signal_generator.py ✅ (same algorithm, frozen params)
    ├── execution/shadow/live_runner.py ✅ (via signal_generator)
    └── execution/shadow/live_executor.py ✅ (via signal_generator)
```

### 3.3 `config/experiment.py` Dependency Chain

```
config/experiment.py
├── IMPORTS FROM: (standard library only)
│
├── IMPORTED BY:
│   └── tests/test_s8_experiment.py → imports all 5 classes
│
├── NOT IMPORTED BY:
│   ├── execution/ ❌
│   ├── execution/shadow/ ❌
│   ├── signals/ ❌
│   └── scripts/ ❌
│
└── VALUES MATCH:
    ├── execution/shadow/signal_generator.py STRATEGY_PARAMS ✅ (BE=0.8, MH=7)
    ├── execution/s8_runtime.py LifecycleRegistry ✅ (BE=0.8, MH=7, Trail=True)
    ├── strategy/trade_management/ ✅ (BE=0.8, MH=7, Trail=True)
    └── ALL research scripts ✅ (hardcode BE=0.8, MH=7 locally)
```

### 3.4 `config/settings.py` Dependency Chain

```
config/settings.py
├── IMPORTS FROM: (standard library + dotenv)
│
├── IMPORTED BY (direct):
│   ├── __init__.py → NestQuantConfig, get_config
│   ├── config/__init__.py → re-exports everything
│   ├── data/loader.py → get_config
│   ├── execution/shadow/live_adapter.py → get_config (lazy)
│   ├── execution/shadow/live_runner.py → get_config (lazy)
│   ├── execution/shadow/runner.py → get_config (lazy)
│   ├── indicators/session.py → SESSION_CLOSE_UTC, SESSION_OPEN_UTC
│   ├── signals/structured_entry.py → ATR_PERIOD, ATR_SL_MULTIPLIER, MACRO_EMA_PERIOD, RRR
│   ├── utils/time_utils.py → SESSION_CLOSE_UTC, SESSION_OPEN_UTC
│   └── tests/test_config.py, test_imports.py, test_s8_strategy_fidelity.py
│
├── IMPORTED BY (via config/__init__.py re-exports):
│   ├── backtest_hybrid_opt.py → ALL_PAIRS, ...
│   ├── currency_strength.py → ALL_PAIRS, ...
│   ├── risk_manager.py → ALL_PAIRS, ...
│   └── 15+ research scripts → ALL_PAIRS, CURRENCIES
│
└── VALUES (WRONG):
    ├── ATR_SL_MULTIPLIER = 3.0 ❌ (canonical is 2.0)
    ├── RRR = 2.0 ❌ (canonical is 3.5)
    └── BREAKEVEN_RATIO = 1.5 ❌ (canonical is 0.8)
```

### 3.5 `canonical_identity.py` Dependency Chain

```
monitoring/canonical_identity.py
├── IMPORTS FROM: (standard library only)
│
├── IMPORTED BY: (NOTHING — standalone documentation module)
│
├── DOCUMENTS:
│   ├── CANONICAL_STRATEGY_PARAMS: lookback=5, atr_period=14, atr_sl_mult=2.0, rrr=3.5 ✅
│   ├── CANONICAL_ABSENT_FEATURES: breakeven, max_hold, trailing, session, macro, news, regime ✅
│   └── KNOWN_POPULATIONS: S0, S5.5, S6A — all MISMATCH due to BE/MH ✅
│
└── ISSUE: Documents BE/MH as "absent" from deployed strategy, but execution layer uses them
    → This is CORRECT for signal generation, MISLEADING for position lifecycle
```

---

## 4. Canonical Strategy Contract

### 4.1 Signal Generation (Entry)

The canonical signal generation is defined in `signals/breakout.py` RESEARCH_DEFAULTS:

```python
CANONICAL_SIGNAL_PARAMS = {
    "lookback": 5,              # 5-bar swing detection
    "atr_period": 14,           # 14-period ATR (Wilder's smoothing)
    "atr_sl_multiplier": 2.0,   # Stop loss = 2.0 × ATR
    "rrr": 3.5,                 # Take profit = 3.5 × SL distance
}
```

**Entry logic**:
- BUY when price breaks above confirmed swing high (previous bar)
- SELL when price breaks below confirmed swing low (previous bar)
- Symmetric BUY/SELL — no directional bias
- 4H timeframe (6 bars/day)

**Explicitly absent from signal generation**:
- ❌ NO correlation filter
- ❌ NO currency strength filter
- ❌ NO session time filter
- ❌ NO macro EMA filter
- ❌ NO news filter
- ❌ NO regime filter
- ❌ NO ADX filter (structured_entry has this, but it's NOT canonical)

### 4.2 Position Lifecycle (Exit Management)

The position lifecycle parameters are defined across the execution layer:

```python
CANONICAL_LIFECYCLE_PARAMS = {
    "breakeven_ratio": 0.8,     # Move SL to entry when profit >= 0.8 × risk
    "breakeven_enabled": True,
    "max_hold_days": 7,         # Exit after 7 days (42 bars at 4H)
    "max_hold_bars": 42,        # 7 days × 6 bars/day
    "trailing_enabled": True,   # Trail SL using previous bar's swing level
    "trailing_type": "swing_based",
}
```

**Exit priority** (evaluated in order):
1. SL hit → exit at SL price
2. TP hit → exit at TP price
3. Max hold → exit at close
4. Trailing stop → move SL tighter (swing-based)
5. Breakeven → move SL to entry

**Source of truth**: These values are hardcoded in:
- `execution/shadow/signal_generator.py` lines 41-42 (BE=0.8, MH=7)
- `execution/shadow/runner.py` line 71 (BE=0.8, MH=42 bars)
- `execution/shadow/live_executor.py` lines 33-38 (BE=0.8, MH=42, Trail)
- `execution/s8_runtime.py` lines 400-402 (LifecycleRegistry config)
- `strategy/trade_management/breakeven.py` line 39 (BE=0.8)
- `strategy/trade_management/max_hold.py` line 49 (MH=7 days)
- `strategy/trade_management/trailing_stop.py` line 50 (Trail enabled)

### 4.3 Complete Canonical Contract

```
SIGNAL GENERATION:
  Strategy:    Breakout (swing-based)
  Timeframe:   4H
  Lookback:    5 bars
  ATR period:  14
  SL mult:     2.0 × ATR
  RRR:         3.5
  Direction:   Symmetric BUY/SELL
  Filters:     None

POSITION LIFECYCLE:
  Breakeven:   Trigger at 0.8R, move SL to entry
  Max hold:    7 days (42 bars)
  Trailing:    Swing-based, previous bar's level

RISK (per config/experiment.py RiskIdentity):
  Risk/trade:  0.15% of equity
  Max concurrent: 3 positions
  Max position:  0.10 lots
  Max total:     3.0 lots
  Max daily loss: 3%
  Max drawdown:  8%
  Max trades/day: 4
```

---

## 5. Recommended Changes

### 5.1 File-by-File Recommendations

| # | File | Action | Justification |
|---|------|--------|---------------|
| 1 | `signals/structured_entry.py` | **ARCHIVE** → `archive/legacy/structured_entry.py` | Dead code. Uses wrong params (ATR=3.0/RRR=2.0). Different strategy family (EMA pullback, not swing breakout). Not imported by any production code. |
| 2 | `signals/__init__.py` | **MODIFY** — Remove `StructuredEntrySignal` export | Eliminate strategy ambiguity. Only `BreakoutSignal` should be exported from signals package. |
| 3 | `config/settings.py` | **KEEP (with restrictions)** — Do NOT delete. Remove legacy constants. | Contains `NestQuantConfig`, `get_config()`, `UniverseConfig` which are imported by `data/loader.py`, `execution/shadow/` (lazy), `indicators/session.py`, `utils/time_utils.py`. The ~100 legacy module-level constants (ATR_SL_MULTIPLIER=3.0, RRR=2.0) should be removed or documented as legacy. |
| 4 | `config/experiment.py` | **KEEP** — Identity documentation | Correctly records validated lifecycle params. Not imported by production. Useful as configuration-as-documentation. |
| 5 | `signals/breakout.py` | **KEEP** — CANONICAL, NEVER MODIFY | Source of truth for signal generation. Already verified by `test_s8_strategy_fidelity.py`. |
| 6 | `execution/shadow/signal_generator.py` | **KEEP** — Production shadow signal | Frozen Variant B params match canonical (2.0/3.5). Lifecycle params (BE=0.8, MH=7) are correctly placed here for the shadow pipeline. |
| 7 | `monitoring/canonical_identity.py` | **MODIFY** — Clarify lifecycle documentation | Currently lists breakeven/max_hold/trailing as "absent features". Should clarify these are absent from **signal generation** but present in **position lifecycle**. The absent features list should specify: "absent from signal generation: breakeven, max_hold, trailing, session, macro, news, regime". |
| 8 | Root `config.py` | **ARCHIVE** → `archive/legacy/config.py` | Dead GFT legacy. Only imported by root-level legacy files and research scripts. Not imported by any production code. |
| 9 | `tests/test_signals.py` | **MODIFY** — Remove `TestStructuredEntrySignal` class | Tests for archived module should not remain in active test suite. |
| 10 | `tests/test_imports.py` | **MODIFY** — Remove `"nestquant.signals.structured_entry"` from import list | Archived module should not be in active import verification. |
| 11 | `tests/test_config.py` | **MODIFY** — Remove assertions on legacy ATR=3.0/RRR=2.0 values | These test the wrong values. Remove or update to not assert specific ATR/RRR from settings. |

### 5.2 Files NOT Changed

| File | Reason |
|------|--------|
| `signals/breakout.py` | CANONICAL — never modify without approval |
| `execution/shadow/safety.py` | CANONICAL hard guard — safety-critical |
| `execution/shadow/live_runner.py` | Active production — no behavior change needed |
| `execution/shadow/live_executor.py` | Active production — lifecycle params are correct |
| `execution/s8_runtime.py` | Active production — LifecycleRegistry config is correct |
| `strategy/trade_management/*.py` | Active production — lifecycle implementations are correct |
| `execution/orchestration.py` | Active production — defense-in-depth |
| `execution/risk_guard.py` | Active production — risk gates |
| `execution/mt5_adapter.py` | Active production — MT5 adapter |
| `execution/mt5_client.py` | Active production — bridge client |
| `risk/circuit_breakers.py` | Active production — breakers |
| `dashboard/` | TypeScript — unaffected |
| `notifications/` | Active production — unaffected |

---

## 6. Migration Order

### Phase 1: Archive `structured_entry.py` (LOW RISK)
**Goal**: Eliminate the wrong-parameter signal from the production namespace.

1. Create `archive/legacy/` directory
2. `git mv signals/structured_entry.py archive/legacy/structured_entry.py`
3. Edit `signals/__init__.py`: remove `StructuredEntrySignal` import and export
4. Edit `tests/test_signals.py`: remove `TestStructuredEntrySignal` class (lines 87-99)
5. Edit `tests/test_imports.py`: remove `"nestquant.signals.structured_entry"` from list (line 29)
6. Verify: `python -c "from nestquant.signals.breakout import BreakoutSignal; print('OK')"`
7. Run tests: `python -m pytest tests/test_signals.py tests/test_s8_strategy_fidelity.py tests/test_imports.py -v`
8. **Commit**: `fix(signals): archive structured_entry.py — wrong params, dead code`

### Phase 2: Archive root `config.py` (LOW RISK)
**Goal**: Remove the dead GFT legacy config that shadows the config/ package.

1. `git mv config.py archive/legacy/config.py` (after archive/legacy/ exists from Phase 1)
2. Verify no production imports break (root config.py is only imported by legacy root files)
3. Run tests: `python -m pytest tests/ -v --tb=short`
4. **Commit**: `refactor(archive): move dead root config.py to archive/legacy/`

### Phase 3: Clean `signals/__init__.py` exports (LOW RISK)
**Goal**: signals package exports only the canonical signal.

1. Verify `signals/__init__.py` only exports: `BaseSignal`, `SignalResult`, `BreakoutSignal`
2. Run tests: `python -m pytest tests/test_signals.py tests/test_imports.py -v`
3. **Commit**: `refactor(signals): clean exports to canonical BreakoutSignal only`

### Phase 4: Clarify `canonical_identity.py` documentation (LOW RISK)
**Goal**: Resolve the misleading "absent features" documentation.

1. Edit `monitoring/canonical_identity.py`:
   - Change `CANONICAL_ABSENT_FEATURES` docstring to: "Features absent from signal generation (breakout.py). Position lifecycle parameters (breakeven, max_hold, trailing) are implemented in execution layer."
   - Add `CANONICAL_LIFECYCLE_PARAMS` section documenting BE=0.8, MH=7, Trail=True
2. Run tests: `python -m pytest tests/ -v --tb=short`
3. **Commit**: `docs(canonical): clarify signal vs lifecycle parameter boundary`

### Phase 5: Clean config/settings.py legacy constants (MEDIUM RISK)
**Goal**: Remove or isolate the ~100 legacy module-level constants with wrong values.

1. **Do NOT delete** `config/settings.py` — it's imported by production code
2. Instead: wrap legacy constants in a `# --- Legacy Compatibility ---` section with clear documentation
3. Or: remove constants that are NOT imported by production (ATR_SL_MULTIPLIER=3.0, RRR=2.0, BREAKEVEN_RATIO=1.5, etc.)
4. Verify: `python -c "from nestquant.config.settings import get_config; print('OK')"`
5. Run tests: `python -m pytest tests/test_config.py tests/test_imports.py -v`
6. **Commit**: `refactor(config): isolate legacy constants in settings.py`

### Phase 6: Update `test_config.py` legacy assertions (LOW RISK)
**Goal**: Tests should not assert wrong values as correct.

1. Edit `tests/test_config.py`: remove or comment assertions on ATR_SL_MULTIPLIER==3.0 and RRR==2.0
2. These values are legacy/wrong — testing them as correct is misleading
3. Run tests: `python -m pytest tests/test_config.py -v`
4. **Commit**: `test(config): remove assertions on legacy wrong-value constants`

### Phase 7: Verification (NO CHANGES)
**Goal**: Prove nothing changed in production behavior.

1. Run full test suite: `python -m pytest tests/ -v`
2. Verify shadow runner imports: `python -c "from nestquant.execution.shadow.live_runner import ShadowLiveRunner"`
3. Verify signal imports: `python -c "from nestquant.signals.breakout import BreakoutSignal"`
4. Verify canonical identity: `python -c "from nestquant.monitoring.canonical_identity import CanonicalStrategyIdentity; print(CanonicalStrategyIdentity().summary())"`
5. Compare test counts before/after
6. **No commit needed — verification only**

---

## 7. Regression Requirements

### Before Remediation (Baseline)

| Metric | Value | Source |
|--------|-------|--------|
| Test collected | 1,741 | Prior run |
| Tests passed | 1,719 | Prior run |
| Tests failed | 22 | Prior run (known: test_mt5_adapter:16, test_s7_engine:3, test_risk_guard:1, test_signal_discovery:1, test_s85_remediation:1) |
| Canonical signal params | lookback=5, ATR=14, SL=2.0, RRR=3.5 | signals/breakout.py |
| Shadow signal params | lookback=5, ATR=14, SL=2.0, RRR=3.5 | execution/shadow/signal_generator.py |
| Shadow lifecycle params | BE=0.8, MH=7d, Trail=True | execution/shadow/runner.py + live_executor.py |
| S8 lifecycle params | BE=0.8, MH=7d, Trail=True | execution/s8_runtime.py |
| Canonical identity hash | (computed) | monitoring/canonical_identity.py |
| Shadow hard guard | ACTIVE | execution/shadow/safety.py |
| Dashboard | Running (port 8080, HTTPS) | VPS |
| Telegram bot | Running | VPS |
| MT5 bridge | Healthy | VPS |

### After Remediation (Expected)

| Metric | Expected | Acceptable Change |
|--------|----------|-------------------|
| Test collected | 1,738–1,741 | −3 max (removed structured_entry tests) |
| Tests passed | 1,716–1,719 | −3 max (removed structured_entry tests) |
| Tests failed | 22 | Same (known failures unchanged) |
| Canonical signal params | **UNCHANGED** | No change |
| Shadow signal params | **UNCHANGED** | No change |
| Shadow lifecycle params | **UNCHANGED** | No change |
| S8 lifecycle params | **UNCHANGED** | No change |
| Canonical identity hash | May change if lifecycle params added | Acceptable |
| Shadow hard guard | **UNCHANGED** | No change |
| Dashboard | **UNCHANGED** | No change |
| Telegram bot | **UNCHANGED** | No change |
| MT5 bridge | **UNCHANGED** | No change |

### Comparison Checklist

```
□ Test count: before vs after (expect −3 max from removed structured_entry tests)
□ Test pass rate: before vs after (expect same or better)
□ Canonical signal output: breakout.py RESEARCH_DEFAULTS unchanged
□ Shadow signal output: signal_generator.py STRATEGY_PARAMS unchanged
□ Strategy fingerprint: canonical_identity.py config_hash (may change if lifecycle added)
□ Shadow hard guard: safety.py unmodified
□ S8 runtime: s8_runtime.py LifecycleRegistry unmodified
□ DEMO execution: s8_runtime.py DRY_RUN path unmodified
□ Dashboard: dashboard/app/ TypeScript unmodified
□ Telegram: notifications/ unmodified
□ Authentication: dashboard/lib/auth.ts unmodified
□ Risk guards: execution/risk_guard.py unmodified
□ Circuit breakers: risk/circuit_breakers.py unmodified
□ MT5 adapter: execution/mt5_adapter.py unmodified
```

---

## 8. Safety Checklist

### What DOES NOT Change

- [ ] `signals/breakout.py` — NEVER MODIFY
- [ ] `execution/shadow/safety.py` — NEVER MODIFY
- [ ] `execution/shadow/signal_generator.py` — No change (params already correct)
- [ ] `execution/shadow/live_runner.py` — No change
- [ ] `execution/shadow/live_executor.py` — No change
- [ ] `execution/s8_runtime.py` — No change
- [ ] `execution/orchestration.py` — No change
- [ ] `execution/risk_guard.py` — No change
- [ ] `execution/mt5_adapter.py` — No change
- [ ] `execution/mt5_client.py` — No change
- [ ] `risk/circuit_breakers.py` — No change
- [ ] `strategy/trade_management/` — No change
- [ ] `portfolio/position_sizer.py` — No change
- [ ] Dashboard TypeScript — No change
- [ ] Notifications — No change
- [ ] MT5 account — No change
- [ ] Live execution gates — No change
- [ ] `NESTQUANT_EXPERIMENTAL_LIVE` — No change
- [ ] Shadow hard guard — No change
- [ ] No live trading enabled
- [ ] No strategy behavior changed
- [ ] No risk thresholds changed
- [ ] No ATR changed
- [ ] No RRR changed
- [ ] No lifecycle behavior changed

### What DOES Change

- [ ] `signals/structured_entry.py` → archived (dead code, wrong params)
- [ ] `signals/__init__.py` → remove StructuredEntrySignal export
- [ ] Root `config.py` → archived (dead GFT legacy)
- [ ] `monitoring/canonical_identity.py` → documentation clarification only
- [ ] `config/settings.py` → legacy constants isolated/removed (NOT the dataclasses)
- [ ] `tests/test_signals.py` → remove structured_entry tests
- [ ] `tests/test_imports.py` → remove structured_entry reference
- [ ] `tests/test_config.py` → remove legacy wrong-value assertions

### No Behavior Change Guarantee

Every change in this proposal either:
1. **Archives dead code** that is not reachable from any production path
2. **Removes exports** of a signal implementation that uses wrong parameters and is not used by production
3. **Clarifies documentation** without changing any executable code
4. **Cleans tests** to not assert wrong values as correct

**Zero production behavior changes.** The strategy signal generation, position lifecycle, risk management, execution, monitoring, and dashboard all remain identical.

---

*This proposal is a READ-ONLY analysis. No code has been modified. All proposed changes require user review and approval before execution.*
