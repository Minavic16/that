# R2.1 Stage 3B — Dependency Review

> **Version:** 1.0.0  
> **Date:** 2026-09-21  
> **Status:** Assessment  
> **Constraint:** Read-only inspection — no implementation

---

## 0. Question

Can we safely implement the six R2.1 volatility models now without creating additional architectural duplication or prematurely hard-coding R2.1-specific infrastructure into the Research OS?

---

## 1. Repository Evidence Inspected

| File | Path | Lines | Status |
|------|------|-------|--------|
| VolatilityModel protocol | `apparatus/models/base.py` | 147 | EXISTS, FROZEN (Stage 3A) |
| ForecastResult | `apparatus/models/base.py:24-47` | 24 | EXISTS |
| ModelDiagnostics | `apparatus/models/base.py:53-89` | 37 | EXISTS |
| Log returns | `apparatus/features/returns.py` | 48 | EXISTS, Stage 3A |
| Realized volatility | `apparatus/features/volatility.py` | 112 | EXISTS, Stage 3A |
| Horizon config | `apparatus/config/horizons.py` | 33 | EXISTS, Stage 3A |
| Data validation | `apparatus/data/validate.py` | 233 | EXISTS, Stage 3A |
| Synthetic fixture | `fixtures/synthetic.py` | 228 | EXISTS, Stage 3A |
| Stage 3B spec | `R2.1_STAGE_3B_FEATURE_MODEL_SPEC.md` | 946 | EXISTS, frozen at `6834ec9` |
| Phase 1 volatility models | `volatility_models.py` | 486 | EXISTS, frozen legacy |
| BacktestEngine | `research/shared/engines/backtest_engine.py` | 279 | EXISTS, trading signals → P&L |
| BacktestMetrics | `research/shared/backtest/metrics.py` | 122 | EXISTS, P&L-based metrics |
| Existing tests | `tests/` (7 files) | — | 97 tests, must remain GREEN |

---

## 2. Per-Model Dependency Analysis

### Model 1: NaiveModel

| # | Question | Answer |
|---|----------|--------|
| 1 | Interface to implement | `VolatilityModel` protocol from `apparatus/models/base.py` |
| 2 | Data structures consumed | `pd.Series` of log returns (from `apparatus/features/returns.py`) |
| 3 | Infrastructure dependencies | Protocol, ForecastResult, ModelDiagnostics — all exist in `base.py` |
| 4 | Infrastructure exists? | **YES** — all three exist and are frozen |
| 5 | Reusable or R2.1-specific? | **REUSABLE** — the protocol is domain-agnostic; any forecasting model can implement it |
| 6 | Independent of Market Simulator/Backtester? | **YES** — model receives returns, returns forecast. No execution, no P&L, no positions. |
| 7 | Existing code to reuse? | Phase 1 `NaiveModel` at `volatility_models.py:62-84` — reference implementation (not import; Phase 1 is frozen legacy). The new version adds gap-awareness per spec §9.3. |

**Classification: CLASS A — Safe to implement now**

### Model 2: RollingVolModel

| # | Question | Answer |
|---|----------|--------|
| 1 | Interface to implement | `VolatilityModel` protocol from `apparatus/models/base.py` |
| 2 | Data structures consumed | `pd.Series` of log returns |
| 3 | Infrastructure dependencies | Protocol, ForecastResult, ModelDiagnostics — all exist |
| 4 | Infrastructure exists? | **YES** |
| 5 | Reusable or R2.1-specific? | **REUSABLE** — rolling standard deviation is a universal volatility estimator |
| 6 | Independent of Market Simulator/Backtester? | **YES** |
| 7 | Existing code to reuse? | Phase 1 `RollingVolModel` at `volatility_models.py:91-110` — reference. New version adds gap-awareness (spec §9.3) and multi-horizon sqrt(h) scaling (spec §2.4). |

**Classification: CLASS A — Safe to implement now**

### Model 3: EWMAModel

| # | Question | Answer |
|---|----------|--------|
| 1 | Interface to implement | `VolatilityModel` protocol from `apparatus/models/base.py` |
| 2 | Data structures consumed | `pd.Series` of log returns |
| 3 | Infrastructure dependencies | Protocol, ForecastResult, ModelDiagnostics — all exist |
| 4 | Infrastructure exists? | **YES** |
| 5 | Reusable or R2.1-specific? | **REUSABLE** — EWMA is a universal exponentially-weighted volatility estimator |
| 6 | Independent of Market Simulator/Backtester? | **YES** |
| 7 | Existing code to reuse? | Phase 1 `EWMAModel` at `volatility_models.py:113-132` — reference. New version adds gap-awareness (spec §9.3, state-dependent: reset at gap boundaries) and multi-horizon sqrt(h) scaling. |

**Classification: CLASS A — Safe to implement now**

### Model 4: GARCHModel

| # | Question | Answer |
|---|----------|--------|
| 1 | Interface to implement | `VolatilityModel` protocol from `apparatus/models/base.py` |
| 2 | Data structures consumed | `pd.Series` of log returns |
| 3 | Infrastructure dependencies | Protocol, ForecastResult, ModelDiagnostics, `arch` package |
| 4 | Infrastructure exists? | **YES** — `arch` is listed as already installed on VPS (spec §17) |
| 5 | Reusable or R2.1-specific? | **REUSABLE** — GARCH is a universal conditional volatility model |
| 6 | Independent of Market Simulator/Backtester? | **YES** — receives returns, returns forecast. No execution. |
| 7 | Existing code to reuse? | Phase 1 `GARCHModel` at `volatility_models.py:135-189` — reference. Key differences: new version adds gap-awareness (spec §9.3), stationarity gate (spec §2.4), analytical multi-step term-structure (spec §2.4), and returns `valid=False` instead of falling back to rolling std. |

**Classification: CLASS A — Safe to implement now**

### Model 5: GJRGARCHModel

| # | Question | Answer |
|---|----------|--------|
| 1 | Interface to implement | `VolatilityModel` protocol from `apparatus/models/base.py` |
| 2 | Data structures consumed | `pd.Series` of log returns |
| 3 | Infrastructure dependencies | Protocol, ForecastResult, ModelDiagnostics, `arch` package |
| 4 | Infrastructure exists? | **YES** |
| 5 | Reusable or R2.1-specific? | **REUSABLE** — GJR-GARCH is a universal asymmetric volatility model |
| 6 | Independent of Market Simulator/Backtester? | **YES** |
| 7 | Existing code to reuse? | Phase 1 `GJRGARCHModel` at `volatility_models.py:192-252` — reference. Same gap/stationarity improvements as GARCH. |

**OPEN DECISION (spec §13.3):** GJR-GARCH multi-step asymmetry-term approximation (`E[I(ε<0)] ≈ 0.5`) is proposed but NOT YET APPROVED. Until approved, GJR reports `FORECAST_UNAVAILABLE` for h > 1 with diagnostic `"GJR_ASYMMETRY_NOT_APPROVED"`. This blocks GJR multi-step only — all other models proceed independently.

**Classification: CLASS A — Safe to implement now** (h=1 only until asymmetry decision; h>1 blocked by single open decision)

### Model 6: HARModel

| # | Question | Answer |
|---|----------|--------|
| 1 | Interface to implement | `VolatilityModel` protocol from `apparatus/models/base.py` |
| 2 | Data structures consumed | `pd.Series` of log returns |
| 3 | Infrastructure dependencies | Protocol, ForecastResult, ModelDiagnostics, `apparatus/features/indicators.py` (for HAR regressors: `mean(r²)` over 6/30/132 windows) |
| 4 | Infrastructure exists? | **PARTIAL** — `indicators.py` does not exist yet. It must be created as part of Stage 3B (spec §1.6, §15). It provides: backward realized variance, Parkinson volatility, EWMA variance. These are simple pandas rolling computations — no external dependencies. |
| 5 | Reusable or R2.1-specific? | **REUSABLE** — HAR-RV is a universal volatility forecasting model. The indicator functions (rolling RV, Parkinson, EWMA) are universal. |
| 6 | Independent of Market Simulator/Backtester? | **YES** |
| 7 | Existing code to reuse? | Phase 1 `HARModel` at `volatility_models.py:255-345` — reference. Key differences: new version uses per-horizon direct regression (spec §3), monthly window 132 (not 90), explicit squared-return regressors (spec §3.1), and 4 instances per pair (one per horizon). |

**Classification: CLASS B — Requires a small prerequisite**

**Prerequisite:** `apparatus/features/indicators.py` must be created first. This file provides:
- `backward_realized_variance(returns, window)` — `mean(r²)` over window
- `parkinson_volatility(high, low, window)` — Parkinson estimator
- `ewma_variance(returns, span)` — EWMA variance

These are ~50-80 lines of pandas rolling computations. They are:
- Self-contained (no external deps beyond numpy/pandas)
- Reusable (universal volatility features)
- Not duplicating any existing code
- Required by HAR (spec §3.1) and optionally useful for other models

The prerequisite is small and can be implemented in the same PR as HAR.

---

## 3. Dependency Classes

### CLASS A — Safe to implement now

| Model | Why safe |
|-------|----------|
| NaiveModel | Self-contained. Protocol exists. No external deps. Reusable interface. |
| RollingVolModel | Self-contained. Protocol exists. No external deps. Reusable interface. |
| EWMAModel | Self-contained. Protocol exists. No external deps. Reusable interface. |
| GARCHModel | Self-contained. Protocol exists. `arch` package installed. Reusable interface. |
| GJRGARCHModel | Self-contained. Protocol exists. `arch` package installed. Reusable interface. h>1 blocked by open decision, but h=1 works now. |

### CLASS B — Requires a small prerequisite

| Model | Prerequisite | Why needed |
|-------|-------------|------------|
| HARModel | `apparatus/features/indicators.py` (~50-80 lines) | HAR regressors require `mean(r²)` over daily/weekly/monthly windows. These are backward-looking rolling features not yet implemented. The spec explicitly lists this file as a Stage 3B deliverable (spec §1.6, §15). |

### CLASS C — Should wait for Research OS infrastructure

**None.** All six models are self-contained forecasting components. They do not depend on:
- Market Simulator (not needed for offline forecasting)
- Canonical BacktestEngine (trading signals → P&L; irrelevant to volatility forecasting)
- Walk-Forward Engine (Stage 3C — evaluation, not model implementation)
- Research Ledger (Stage 3C+ — provenance, not model implementation)
- Bootstrap/MC Engine (Stage 3D — robustness, not model implementation)

---

## 4. Interface Reusability Assessment

### Is the VolatilityModel protocol clean enough to become a reusable forecasting-model interface?

**YES.** Evidence:

1. **Domain-agnostic signature:** `fit(returns: pd.Series, gaps: pd.Series | None) → ModelDiagnostics` and `forecast(horizon: int) → ForecastResult`. Any univariate volatility model can implement this.

2. **No R2.1-specific leakage:** The protocol does not reference R2.1, forex, 4H bars, specific horizons, or any experiment-specific parameters. Horizons are passed as arguments, not hardcoded.

3. **Horizon-agnostic:** `forecast(horizon)` accepts any integer horizon. The protocol does not enforce `{1, 3, 6, 12}` — that is an experiment-level configuration, not a protocol constraint.

4. **Gap-awareness is optional:** The `gaps` parameter is `pd.Series | None`. Models that don't need gap handling can ignore it.

5. **Clean separation of concerns:** Models receive returns (not raw prices, not OHLCV, not order books). This is the correct abstraction for a forecasting model.

6. **Future extensibility:** The protocol can be implemented by GARCH-M, FIGARCH, HARQ, or any future model without modification.

**Conclusion:** The protocol is reusable as a common forecasting-model interface. It should be promoted from R2.1-specific to Research OS common infrastructure in a future stage — but that promotion is NOT required for Stage 3B.

---

## 5. Duplication Assessment

### Would implementing Stage 3B create architectural duplication?

**NO.** Evidence:

1. **New files, not modifications:** Stage 3B creates 6 new model files in `apparatus/models/` (spec §15). It modifies zero existing files.

2. **Phase 1 code is frozen legacy:** `volatility_models.py` is not imported by Stage 3B (spec §0.1). The known divergences (monthly window 90→132, fallback→valid=False, 1-step→multi-horizon) are documented and intentional.

3. **`indicators.py` is new, not a duplicate:** No existing file provides rolling realized variance, Parkinson volatility, or EWMA variance as standalone functions. `apparatus/features/volatility.py` provides `realized_volatility_forward` (target) and `realized_volatility_backward` (std), but not `mean(r²)` (variance). The indicators are additive, not duplicative.

4. **Models consume existing protocol:** All six models implement the same `VolatilityModel` protocol. There is exactly one protocol, one ForecastResult, one ModelDiagnostics. No parallel interfaces.

5. **No premature hard-coding:** Models receive returns as `pd.Series` — they don't know about data sources, file formats, or experiment structure. The interface is clean for later extraction to common ROS.

---

## 6. Simulator/Backtester Independence Assessment

### Can models be implemented independently of the Market Simulator and canonical Backtest?

**YES.** Evidence:

1. **Models are pure functions of returns:** `fit(returns) → forecast(horizon)`. No prices, no orders, no execution, no positions, no P&L.

2. **The BacktestEngine is for trading signals:** `backtest_engine.py` imports `BaseSignal` (trading signals with direction, SL, TP). Volatility models produce `ForecastResult` (volatility estimate + horizon tag). These are different domains.

3. **BacktestMetrics is P&L-based:** `metrics.py` computes Sharpe, drawdown, win rate — all require trade P&L. R2.1 needs forecast error metrics (RMSE, MAE, QLIKE). These are completely different.

4. **The architecture plan's §11 metrics do not apply:** The plan lists 16 P&L-based metrics (11a-11p). R2.1 needs forecast error metrics specified in `research/R2/2_R2_1_METRICS_CONTRACT.md`. No overlap.

5. **Walk-forward evaluation is Stage 3C:** The evaluation engine consumes model outputs. It is not needed for model implementation.

6. **R2.1 does not generate P&L:** It is a volatility forecasting experiment. The evaluation metric is forecast accuracy, not trading profitability.

---

## 7. Code Reuse Assessment

### Should any existing code be reused rather than duplicated?

| Existing code | Location | Reuse? | Reason |
|---------------|----------|--------|--------|
| Phase 1 NaiveModel | `volatility_models.py:62-84` | **REFERENCE** (not import) | Frozen legacy. New version adds gap-awareness. |
| Phase 1 RollingVolModel | `volatility_models.py:91-110` | **REFERENCE** (not import) | Frozen legacy. New version adds gap-awareness + sqrt(h) scaling. |
| Phase 1 EWMAModel | `volatility_models.py:113-132` | **REFERENCE** (not import) | Frozen legacy. New version adds gap-awareness + sqrt(h) scaling. |
| Phase 1 GARCHModel | `volatility_models.py:135-189` | **REFERENCE** (not import) | Frozen legacy. New version adds stationarity gate + multi-step term-structure. |
| Phase 1 GJRGARCHModel | `volatility_models.py:192-252` | **REFERENCE** (not import) | Frozen legacy. New version adds stationarity gate + asymmetry decision. |
| Phase 1 HARModel | `volatility_models.py:255-345` | **REFERENCE** (not import) | Frozen legacy. New version uses per-horizon regression + monthly=132. |
| VolatilityModel protocol | `apparatus/models/base.py` | **REUSE** (import) | This is the canonical interface. All models import from here. |
| ForecastResult | `apparatus/models/base.py` | **REUSE** (import) | This is the canonical output type. |
| ModelDiagnostics | `apparatus/models/base.py` | **REUSE** (import) | This is the canonical diagnostics type. |
| compute_log_returns | `apparatus/features/returns.py` | **REUSE** (import) | Canonical log return computation. |
| realized_volatility_backward | `apparatus/features/volatility.py` | **REUSE** (import) | Canonical backward RV (used by HAR). |
| HORIZONS constant | `apparatus/config/horizons.py` | **REUSE** (import) | Canonical horizon definitions. |

**Conclusion:** Models reuse the existing apparatus infrastructure (protocol, features, config). They reference Phase 1 code for algorithmic understanding but do not import it. No duplication.

---

## 8. Decision

### PROCEED WITH STAGE 3B

**Evidence-based reasoning:**

1. **All dependencies exist.** The VolatilityModel protocol, ForecastResult, ModelDiagnostics, log returns, realized volatility, horizon config, data validation, and synthetic fixture are all implemented and frozen (Stage 3A). The `arch` package is installed. No external dependencies are missing.

2. **No architectural duplication.** Stage 3B creates 6 new model files + 1 new indicators file + 9 new test files. It modifies zero existing files. Phase 1 code is frozen legacy, not imported.

3. **No premature hard-coding.** Models implement a clean, reusable protocol. They receive `pd.Series` of returns — no data source specifics, no experiment structure, no R2.1 references in the interface.

4. **Independent of Market Simulator and Backtest.** Models are pure forecasting functions. They do not need execution, positions, P&L, or the trading-signal BacktestEngine. R2.1 evaluates forecast accuracy, not trading profitability.

5. **One small prerequisite can be included in the same PR.** `apparatus/features/indicators.py` (~50-80 lines) is needed by HAR. It is new code, self-contained, reusable, and explicitly part of the Stage 3B spec (§1.6, §15). It should be created as the first step of Stage 3B, not as a separate stage.

6. **One open decision does not block the stage.** The GJR-GARCH asymmetry-term approximation blocks GJR h>1 only. All other models and GJR h=1 proceed. The decision can be approved independently.

---

## 9. What Stage 3B Would Implement

| # | File | What | Est. Lines |
|---|------|------|-----------|
| 1 | `apparatus/features/indicators.py` | Rolling realized variance, Parkinson volatility, EWMA variance | ~60 |
| 2 | `apparatus/models/naive.py` | NaiveModel (gap-aware) | ~50 |
| 3 | `apparatus/models/rolling.py` | RollingVolModel (gap-aware, sqrt(h) scaling) | ~60 |
| 4 | `apparatus/models/ewma.py` | EWMAModel (gap-aware, state-dependent, sqrt(h) scaling) | ~60 |
| 5 | `apparatus/models/garch.py` | GARCHModel (gap-aware, stationarity gate, multi-step term-structure) | ~100 |
| 6 | `apparatus/models/gjr_garch.py` | GJRGARCHModel (gap-aware, stationarity gate, h>1 blocked until asymmetry decision) | ~100 |
| 7 | `apparatus/models/har.py` | HARModel (4 instances per pair, per-horizon OLS regression) | ~120 |
| 8 | `apparatus/config/models.py` | ModelConfig, predeclared R2.1 configs | ~60 |
| 9 | `tests/test_model_contract.py` | Protocol compliance, diagnostics, name, min_obs | ~120 |
| 10 | `tests/test_model_fixture.py` | Model-on-fixture integration + multi-horizon scaling | ~100 |
| 11 | `tests/test_model_causality.py` | Perturbation tests for features + models | ~200 |
| 12 | `tests/test_model_failure.py` | Insufficient data, non-convergence, NaN, gap semantics | ~100 |
| 13 | `tests/test_model_config.py` | Configuration immutability, predeclaration | ~40 |
| 14 | `tests/test_horizon_consistency.py` | Horizon mismatch, stationarity gate, HAR independence | ~50 |
| 15 | `tests/test_gap_semantics.py` | Gap handling per model type | ~60 |
| 16 | `tests/test_rolling_features.py` | Unit tests for indicators.py | ~80 |
| 17 | `tests/test_har_definition.py` | HAR windows, regressors, per-horizon OLS | ~80 |

**Total:** ~1,300 new lines (implementation + tests). Zero existing files modified.

---

## 10. What Stage 3B Explicitly Would NOT Implement

| Not implementing | Why |
|------------------|-----|
| Walk-Forward Evaluation Engine | Stage 3C — evaluation, not model implementation |
| Blocked Temporal Evaluation | Stage 3C — evaluation framework |
| Forecast Error Metrics (RMSE, MAE, etc.) | Stage 3C — metrics engine |
| Regime Classifier | Stage 3C — analysis layer |
| Research Ledger | Stage 3C+ — provenance |
| Bootstrap/MC Engines | Stage 3D — robustness |
| Market Simulator | Future core layer — not needed for R2.1 |
| Canonical BacktestEngine refactoring | Out of scope — 7 implementations remain as-is |
| Equity-curve continuity | Not needed for R2.1 (volatility forecasting, not P&L) |
| GJR asymmetry-term approximation | Pending explicit approval — GJR h>1 blocked |

---

## 11. Next Approved Task

Implement Stage 3B per the frozen spec at `6834ec9`, in this order:

1. Create `apparatus/features/indicators.py` (prerequisite for HAR)
2. Create `apparatus/models/naive.py`
3. Create `apparatus/models/rolling.py`
4. Create `apparatus/models/ewma.py`
5. Create `apparatus/models/garch.py`
6. Create `apparatus/models/gjr_garch.py` (h=1 only until asymmetry decision)
7. Create `apparatus/models/har.py`
8. Create `apparatus/config/models.py`
9. Create all test files
10. Run all tests — verify 97 existing + ~74 new pass
11. Request GJR asymmetry-term decision for h>1

**STOP.**
