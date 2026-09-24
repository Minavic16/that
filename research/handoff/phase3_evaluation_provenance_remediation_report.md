# OpenCode Task Report

**Task:** Research OS Phase 3 — Freeze-Gate Remediation (bounded contract/documentation fixes)
**Status:** AWAITING_REVIEW
**Date:** 2026-09-24
**Author:** OpenCode (via NestQuant Orchestrator)

---

## A. Findings resolved

| ID | Resolution | Files changed | Tests added/updated | Behavior vs contract/doc only |
|---|---|---|---|---|
| **M-1** | Preserved calculation (`len(closed_valid)`). Updated `METRIC_SEMANTICS["total_trades"]` and `EvaluationMetrics.empty()` definition + architecture §4.3 to state finite-PnL closed population; non-finite excluded with warning. | `evaluation/metrics.py`, `evaluation/contracts.py`, `RESEARCH_OS_EVALUATION_ARCHITECTURE.md` | Strengthened `test_non_finite_pnl_excluded`; added `test_total_trades_contract_finite_nan_finite` | **Contract/doc only** (calculation unchanged) |
| **M-2** | Architecture matches implementation: `evaluation_input_from_simulator(simulator)` (no `pair`); `open_trades_excluded` documented as warning not metric; zero-fold warning `aggregate_zero_folds`. | `RESEARCH_OS_EVALUATION_ARCHITECTURE.md` | Doc consistency checks in verification (no stale strings in arch) | **Doc only** |
| **M-3** | Explicit drawdown source contract in `METRIC_SEMANTICS` + arch §4.3.1: equity-path vs trade-normalized; consumers MUST inspect warnings; aggregate without equity = trade-sequence DD. | `evaluation/metrics.py`, `RESEARCH_OS_EVALUATION_ARCHITECTURE.md` | Added `test_drawdown_source_interpretation_contract` | **Contract/doc**; existing warnings unchanged |
| **M-4** | Documented `pooled_closed_trades` limitations in arch §4.5 and ADR-4: recompute not average; path metrics depend on fold order; no capital continuity; no overlap detection; no OOS equity stitch. | `RESEARCH_OS_EVALUATION_ARCHITECTURE.md` | Added `test_aggregate_recomputes_not_averages_fold_metrics` | **Doc only**; algorithm unchanged |
| **m-1** | Docstring: `None` → `None`; `{}` → deterministic hash of empty mapping. | `provenance/identity.py`, arch §5.2 | Extended `test_config_hash_deterministic` | **Doc only** |
| **m-2** | Added `Provenance.evaluation_status: Optional[str]`; builder stores extracted status; serialization round-trips; ledger defaults from provenance. No evaluation package import. | `provenance/contracts.py`, `provenance/builder.py`, `provenance/ledger.py`, arch §5.1 | Extended `test_build_provenance_from_evaluation` | **Small contract extension** |
| **m-3** | Documented reproducibility-grade DataIdentity completeness; no fabrication. | arch §5.1 | Added `test_data_identity_never_fabricates` | **Doc/test only** |
| **m-4** | `EvaluationResult.to_dict()` routes metrics through `metrics_to_jsonable()`. | `evaluation/contracts.py` | Added `test_result_to_dict_json_safe_nonfinite` | **Serialization behavior hardened**; finite values unchanged |
| **m-5** | Engine adapter test asserts trade population, `total_trades`, `total_pnl`, `execution_ref`, Phase 2 `get_results` compatibility. | `tests/research/test_evaluation_contract.py` | Updated `test_engine_to_evaluation` | **Test only** |
| **m-6** | Documented duplicate-trade convention in `metrics.py` module docstring, `EvaluationResult` docstring, arch §4.3. | `evaluation/metrics.py`, `evaluation/contracts.py`, arch | Added `test_duplicate_trades_counted_as_supplied` | **Doc only** |

## B. Intentionally unchanged

- **Phase 1** data layer — untouched (`research/shared/data` clean).
- **Phase 2** execution core / `ExecutionSimulator` / `BacktestEngine` semantics — untouched.
- **Strategy 2** methodology and experiments — untouched; no Phase 3 imports of strategy2.
- **Sharpe methodology** — trade-PnL series, √252, per-observation rf subtraction — **unchanged**; still documented as trade-PnL convention, not universal portfolio Sharpe.
- **pooled-fold algorithm** — still concatenate trades → `compute_metrics`; not averaged; no equity stitch.
- **No OOS stitching** machinery introduced.
- **No reporting** layer implemented.
- **No** database, concurrency, optimizer, ranking/score framework, or architecture redesign.

## C. Test evidence

```bash
cd /root/that
PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 \
  python3 -m pytest tests/research/ -q
# -> 168 passed  (was 162; +6 new/strengthened Phase 3 tests)

PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 \
  python3 -m pytest research/experiments/strategy2/tests/ -q
# -> 80 passed

PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 \
  python3 -m pytest tests/research/test_evaluation_metrics.py tests/research/test_evaluation_contract.py -q
# -> 54 passed (focused Phase 3 suite)
```

Doc consistency probe (architecture): no stale `zero_folds_no_aggregate_metrics`, `open_trades_excluded` as metric row, `pair="EUR/USD")` example, or `Empty/None → None` for config_hash.

Boundary probe: no `nestquant.production` / `strategy2` / `apparatus` under `research/shared/evaluation` or `research/shared/provenance`.

Phase 1/2/Strategy 2: `git status` clean for those trees (only pre-existing untracked `apparatus/models/` unrelated).

## D. Remaining limitations

- Aggregate path-dependent metrics still depend on fold input order (documented; not “fixed” by design).
- No fold overlap detection (documented).
- DataIdentity remains optional/partial unless callers supply checksum/version (documented; no fabrication).
- Ledger concurrency still out of scope (unchanged).
- Pre-existing unrelated failures outside `tests/research/` (platform imports, safety/shadow, numba collection) — not addressed per scope.
- Drawdown still uses one metric name with warning-based source distinction (no new metric framework — per M-3 preferred approach).

## E. Freeze recommendation

**READY_FOR_REVIEW**

This task does **not** freeze Phase 3. A separate source-level review/freeze gate must decide freeze.

---

*Phase 3 freeze-gate remediation report.*
