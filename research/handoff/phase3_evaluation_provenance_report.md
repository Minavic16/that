# OpenCode Task Report

**Task:** Research OS Phase 3 — Canonical Evaluation + Provenance/Research Ledger (`research/shared/evaluation/`, `research/shared/provenance/`)
**Status:** COMPLETE
**Date:** 2026-09-24
**Author:** OpenCode (via NestQuant Orchestrator)

---

## Objective

Implement the Canonical Evaluation and Provenance/Research Ledger layer on branch `research/strategy-2` (working path `/root/that`), after mandatory repo investigation. Evaluation must accept execution results (`evaluate(execution_result, config)`), define explicit metric semantics/statuses, support fold evaluation without OOS stitching, and stay free of production/Strategy 2 imports. Provenance must record run identity (git, data, config hashes, evaluation id) in an append-only JSONL ledger with no database. Phase 1 (data) and Phase 2 (execution) remain frozen. End with tests, architecture doc + ADRs, single focused commit, push, Termux notification, clipboard byte-verified report.

## What Was Inspected

- Metrics inventory: `research/shared/backtest/metrics.py`, Phase 2 `ExecutionSimulator.get_results()`, engine state, architecture plan metric tables, ROS metric tiers, R2.1 forecast metrics contract (out of scope).
- Fold handling: no generic fold evaluator existed; Strategy 2 folds are spec/ad-hoc only.
- Provenance layers: `research/experiment.py` git helpers, `core/configuration/experiment.py` config-hash pattern (reimplemented research-side), `research/experiments/strategy2/provenance/schema.py` pattern, `research/ledger/` absent (designed, unbuilt — Phase 3 fills it).
- Phase 2 frozen surfaces: `research/shared/execution/{contracts,simulator}.py`, `get_results()` keys.
- Boundaries: zero `production.*` / Strategy 2 imports in evaluation & provenance; dependency data → execution → evaluation → provenance → reporting.
- Stop conditions A–H: no material conflict in the P&L evaluation lane; metric authority pinned to existing backtest formulas.

## What Was Changed

- New package `research/shared/evaluation/`: contracts (`MetricValue`, `EvaluationStatus`, `MetricStatus`, `FoldRole`, `EvaluationResult`, fold types), `metrics.py` (`METRIC_SEMANTICS` + `compute_metrics`), `evaluator.py` (`evaluate`, adapters, `aggregate_fold_evaluations` with `pooled_closed_trades`), `comparison.py` (diff-only, no winner), `folds.py`, exports.
- New package `research/shared/provenance/`: `contracts.py` (`Provenance`, `GitIdentity`, `DataIdentity`), `identity.py` (run ids, fail-closed git, sha256 config hash), `builder.py` (`build_provenance`), `ledger.py` (append-only JSONL, duplicate `run_id` rejected).
- Architecture doc `research/RESEARCH_OS_EVALUATION_ARCHITECTURE.md` with 10 sections + ADR-1..ADR-6.
- Tests: `tests/research/test_evaluation_metrics.py` (unit/edge), `tests/research/test_evaluation_contract.py` (contract/boundary/regression/provenance/ledger/determinism).
- This report under `research/handoff/`.

Not changed: Phase 1 data layer, Phase 2 execution behavior/`get_results()`, Strategy 2 methodology, production runtime.

## Files Changed

| File | Change Type | Description |
|---|---|---|
| research/shared/evaluation/__init__.py | NEW | Package exports + boundary docstring |
| research/shared/evaluation/contracts.py | NEW | Metric/evaluation/fold contracts |
| research/shared/evaluation/metrics.py | NEW | Canonical metric computation + semantics |
| research/shared/evaluation/evaluator.py | NEW | `evaluate`, adapters, fold aggregation |
| research/shared/evaluation/comparison.py | NEW | Pairwise metric differences (no rank) |
| research/shared/evaluation/folds.py | NEW | Fold type re-exports + aggregate |
| research/shared/provenance/__init__.py | NEW | Package exports + boundary docstring |
| research/shared/provenance/contracts.py | NEW | Provenance / Git / Data identity |
| research/shared/provenance/identity.py | NEW | Run IDs, git capture, config hash |
| research/shared/provenance/builder.py | NEW | `build_provenance` from layered objects |
| research/shared/provenance/ledger.py | NEW | Append-only JSONL research ledger |
| research/RESEARCH_OS_EVALUATION_ARCHITECTURE.md | NEW | Architecture + ADR-1..ADR-6 |
| tests/research/test_evaluation_metrics.py | NEW | Unit/edge metric tests |
| tests/research/test_evaluation_contract.py | NEW | Contract/boundary/provenance/ledger tests |
| research/handoff/phase3_evaluation_provenance_report.md | NEW | This report |

## Tests

- `PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 python3 -m pytest tests/research/ -q` → **162 passed** (114 pre-existing + 48 new).
- Same env `pytest research/experiments/strategy2/tests/ -q` → **80 passed**.
- Import-boundary tests: evaluation/provenance sources contain no `nestquant.production` / Strategy 2 / apparatus strings; importing evaluation does not load `nestquant.production.signals`.
- Regression: canonical vs `backtest/metrics.py` agree on shared fixture (total_trades, win_rate, total_pnl, expectancy, max_drawdown, sharpe).
- Compatibility: `BacktestMetrics`/`calculate_metrics` still importable; `ExecutionSimulator.get_results()` key set preserved.

## Test Results

- PASS: 162/162 `tests/research/`.
- PASS: 80/80 Strategy 2 tests.
- PASS: import boundary + Phase 2 compatibility + ledger append-only/no-overwrite/round-trip + determinism (metrics stable across runs; ids differ by design).
- Pre-existing (unchanged, not introduced by Phase 3): `tests/platform/test_imports.py` legacy flat-path failures (44 failed / 125 passed in platform suite); `test_horizon_encoding.py` missing `arch`; 13 safety/shadow failures; 13 `tests/` collection errors under regression/unit/smoke/s8 (e.g. missing `numba`).

## Evidence

- Test commands and counts above; architecture doc cites formula sources (`backtest/metrics.py`).
- Git status after staging: only Phase 3 paths staged; pre-existing untracked docs (`NESTQUANT_*`, `R2/`, `BUILD_READINESS`, `apparatus/models/`, `scripts/`) left untracked and not committed.
- Phase 1/2 diffs empty (`git status` clean for `research/shared/data`, `research/shared/execution`).

## Remaining Issues

- Aggregate fold metrics require `FoldEvaluation.trades` to be carried; otherwise aggregate metrics stay empty with explicit warning `aggregate_without_trades_unavailable_use_fold_results`.
- Ledger is single-process append-only; concurrent writers not coordinated (out of scope).
- Equity-curve metrics optional; without equity, drawdown is trade-normalized and warns.
- Pre-existing suite failures listed above remain.

## Decisions Required

None blocking. Reviewer may confirm ADR-1..ADR-6 (API shape, formula authority, status model, fold aggregation, JSONL ledger, research-side git/config identity).

## Recommended Next Action

Reviewer feedback on Phase 3, then plan Phase 4 (reporting/consumers of evaluation + provenance) under Research OS.

## Commit

`feat(research): add canonical evaluation and provenance layer` (this commit on `research/strategy-2`)

---
*Report generated by OpenCode. Review by ChatGPT/Claude before next action.*
