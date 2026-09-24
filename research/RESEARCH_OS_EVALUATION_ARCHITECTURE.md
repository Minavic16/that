# Research OS — Canonical Evaluation & Provenance Architecture

Phase 3 of Research OS. Freezes the evaluation and provenance semantics that
downstream reporting will consume. Dependencies: data → execution →
**evaluation → provenance** → reporting (later).

- Evaluation package: `research/shared/evaluation/`
- Provenance package: `research/shared/provenance/`
- Phase 1 (data) and Phase 2 (execution) remain frozen and unchanged.

---

## 1. Executive Summary

Phase 3 introduces a single, experiment-agnostic **canonical evaluator** for
P&L/execution results and an **append-only research ledger** that records what
was run, with what code/data/config, and what it produced.

The evaluator:

- accepts an `EvaluationInput` (trades + optional equity + metadata) built by
  adapters from Phase 2 `ExecutionSimulator` / `BacktestEngine` / raw `Trade[]`
- returns an `EvaluationResult` with typed `MetricValue`s, explicit status
  (`VALID` / `VALID_WITH_WARNINGS` / `INVALID`), and warnings — never a
  universal quality score
- defines each metric’s unit, formula, and edge-case status in
  `METRIC_SEMANTICS`

Provenance answers: «what did we run, with what inputs, and what did it
produce?» — git identity, data identity, config hashes, evaluation id, run id —
persisted as immutable JSONL ledger entries.

## 2. Goals and Non-Goals

### Goals
- One canonical definition per P&L/execution metric, stable across callers.
- Explicit undefined/`NOT_APPLICABLE` handling (no silent NaN/0).
- Explicit fold roles and pooled-trade aggregation with fold results retained.
- Experiment-agnostic provenance with append-only persistence (no DB).
- Zero production imports; zero Strategy 2 imports in evaluation/provenance.

### Non-Goals
- No strategy optimizer, ranking, or universal score.
- No walk-forward engine (only evaluate already-defined folds).
- No new statistical methodology (no PBO/DSR/MC/bootstrap).
- No reporting/dashboards (reporting is a later phase).
- No OOS stitching across folds into one equity curve.
- No Strategy 2 / R2.1 forecast-metric changes (those stay in R2.1).

## 3. Architecture Overview

```
data (Phase 1, frozen)
  └─► execution (Phase 2, frozen)
        └─► evaluation (Phase 3)     evaluate(input, config) → EvaluationResult
              └─► provenance (Phase 3)  build_provenance(...) → Provenance → Ledger
                    └─► reporting (future phase)
```

Evaluation does not import Strategy 2 or production. Provenance does not import
production or Strategy 2; git/config-hash helpers are reimplemented research-side.

## 4. Canonical Evaluation

### 4.1 API

```python
from nestquant.research.shared.evaluation import (
    EvaluationConfig, evaluate, evaluation_input_from_simulator,
)

inp = evaluation_input_from_simulator(simulator, pair="EUR/USD")
result = evaluate(inp, EvaluationConfig())
result.status          # VALID | VALID_WITH_WARNINGS | INVALID
result.metrics.win_rate  # MetricValue(name, value, unit, definition, status)
```

`evaluate(execution_result, config)` — not `evaluate(strategy, data, ...)`.

### 4.2 Metric values and statuses

- `MetricStatus`: `DEFINED`, `UNDEFINED`, `NOT_APPLICABLE`
- `EvaluationStatus`: `VALID`, `VALID_WITH_WARNINGS`, `INVALID` — a pipeline
  status, **not** a quality grade.
- Undefined metrics: `value=None`, never accidental NaN or 0.
- Non-finite metric values in JSON: serialized as `null` + status
  `NOT_APPLICABLE` (e.g. infinite profit factor when there are no losses).

### 4.3 Canonical metric set (19)

| Metric | Unit | Edge cases |
|---|---|---|
| `total_trades` | count | 0 trades → DEFINED 0 |
| `winning_trades` / `losing_trades` / `breakeven_trades` / `open_trades_excluded` | count | open trades excluded with warning |
| `total_pnl` | account currency | non-finite PnL excluded + warning |
| `gross_profit` / `gross_loss` | account currency | empty sides → 0 DEFINED |
| `win_rate` | fraction [0,1] | 0 trades → UNDEFINED |
| `profit_factor` | ratio | no losses → NOT_APPLICABLE (infinite) + warning; no wins → 0 |
| `expectancy` | account currency | 0 trades → UNDEFINED |
| `average_win` / `average_loss` | account currency | empty side → UNDEFINED |
| `max_drawdown` | account currency | equity curve preferred; else trade-normalized cumsum + warning |
| `total_return` | fraction | initial_balance ≤ 0 → UNDEFINED |
| `sharpe_ratio` | ratio | <2 obs → UNDEFINED; zero variance → UNDEFINED + warning |
| `average_trade_duration` / `average_winning_trade_duration` / `average_losing_trade_duration` | seconds | missing exits skipped |

Canonical formulas (aligned with `research/shared/backtest/metrics.py`):

- `win_rate = wins / closed_trades` (fraction)
- `profit_factor = Σwins / |Σlosses|`
- `sharpe_ratio = mean(daily) / std(daily) * √252`, `risk_free_rate=0.0`, min obs=2
- `expectancy = total_pnl / closed_trades`
- `max_drawdown` from equity path when present; otherwise max peak-to-trough of
  trade-normalized cumulative PnL (zero-trades / no-equity cases warn)

All semantics are documented in `evaluation/metrics.py::METRIC_SEMANTICS`.

### 4.4 Status rules

- Zero trades: `VALID_WITH_WARNINGS`, not `INVALID`.
- Missing equity curve: `VALID_WITH_WARNINGS` (`equity_curve_missing_...`).
- NaN/Inf inputs on equity curve: raise `ValueError` (fail closed).
- `INVALID` reserved for structural contract violations (e.g. malformed input),
  not for “bad performance”.

### 4.5 Fold evaluation

- `FoldRole`: `TRAIN`, `IS`, `OOS`, `VALIDATION`, `HOLDOUT`, `UNKNOWN` — roles
  are always explicit; never inferred from timestamps.
- `aggregate_fold_evaluations(fold_evaluations, config)` uses
  `aggregation_method="pooled_closed_trades"`: pools trades for aggregate
  metrics while **retaining every fold-level `EvaluationResult`**.
- No equity-curve stitching across folds. If trades are not carried on
  `FoldEvaluation.trades`, aggregate metrics stay empty and warning
  `aggregate_without_trades_unavailable_use_fold_results` is set.
- Zero folds → `VALID_WITH_WARNINGS` + `zero_folds_no_aggregate_metrics`.

### 4.6 Comparison

`compare_evaluations(a, b)` returns per-metric absolute/relative differences.
It does **not** rank, score, or declare a winner. Missing metrics on either side
are reported as such.

## 5. Provenance and Research Ledger

### 5.1 Contracts

- `Provenance`: `run_id`, `experiment_id`, `git (GitIdentity)`, `code_version`,
  `data (DataIdentity)`, `strategy_identity`, `execution_config` +
  `evaluation_config` (+ sha256 config hashes), `evaluation_id`,
  `created_at`, `parent_run_id`, `notes`.
- `GitIdentity`: `commit`, `dirty`, `available` — unavailable git → all `None`
  / `available=False` (fail closed, never fabricate a SHA).
- `DataIdentity`: instruments, timeframe, start/end, source, dataset id/version,
  checksum, n_bars — all optional, all explicit.

### 5.2 Identity helpers (`provenance/identity.py`)

- `new_run_id(prefix)` → `run-<uuid4hex16>` / evaluation ids → `eval-…`.
- `get_git_commit` / `get_git_dirty`: subprocess, timeout, None on failure —
  same fail-closed pattern as `research/experiment.py`.
- `config_hash(mapping)`: deterministic JSON (`sort_keys`, compact separators)
  → SHA-256 → 16 hex chars; same pattern as `core/configuration/experiment.py`,
  **reimplemented research-side** (no production import). Empty/None → None.

### 5.3 Builder

`build_provenance(execution=…, evaluation=…, experiment=…, data=…, …)` accepts
duck-typed inputs (dataclasses with `to_dict`, mappings, `EvaluationResult`,
`EvaluationConfig`, `BacktestConfig`, `ProvenanceRecord`-shaped mappings) and
fills only what it can; the rest stays `None`.

### 5.4 Ledger (`provenance/ledger.py`)

- Append-only JSONL (default `research/ledger/research_ledger.jsonl`).
- One `LedgerEntry` per line: run/experiment ids, timestamp, workload identity,
  data/execution/evaluation identity blobs, result ref, git commit/dirty,
  status, evaluation status, warnings, notes.
- `append` refuses an existing `run_id` (`ValueError`) — **no silent overwrite**.
- Read path: `entries()`, `get(run_id)`, `run_ids()`, iteration, `to_jsonl()`.
- No database.

## 6. Boundary and Dependency Rules

| Package | May import | Must not import |
|---|---|---|
| `shared/evaluation` | `shared/execution.contracts`, pandas/numpy | `production.*`, Strategy 2 / apparatus |
| `shared/provenance` | `shared/evaluation`, local identity | `production.*`, Strategy 2 |
| tests | both | — |

Enforced by `tests/research/test_evaluation_contract.py::TestImportBoundaries`
(source scan for forbidden substrings + runtime check that importing evaluation
does not load `nestquant.production.signals`).

## 7. Compatibility with Phase 1 / Phase 2

- Phase 1 data layer and Phase 2 execution/simulator behavior are **unchanged**.
- `BacktestMetrics` / `calculate_metrics` (`shared/backtest/metrics.py`) remain
  available; canonical evaluator is the eventual semantic authority but shared
  formulas must keep agreeing (regression-tested).
- `ExecutionSimulator.get_results()` keys preserved (including `trades`);
  evaluation uses richer adapters (`evaluation_input_from_simulator/engine`)
  and does not remove or reshape Phase 2 outputs.
- Strategy 2 methodology and R2.1 forecast metrics are out of scope.

## 8. Testing Strategy

| Layer | File | Focus |
|---|---|---|
| Unit / edge | `tests/research/test_evaluation_metrics.py` | zero trades, all-win PF, Sharpe UNDEFINED, equity vs trade drawdown, non-finite handling, folds, comparison, no score |
| Contract / boundary / provenance / ledger / regression | `tests/research/test_evaluation_contract.py` | engine/simulator adapters, import boundaries, Phase 2 compat, canonical vs backtest formulas, git/config hash, ledger append-only + round-trip |

Baselines that must stay green:

- `tests/research/` (was 114 → now includes Phase 3 tests)
- `research/experiments/strategy2/tests/` → 80 passed

## 9. Runbook

```bash
cd /root/that
PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 \
  python3 -m pytest tests/research/ -q
PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 \
  python3 -m pytest research/experiments/strategy2/tests/ -q
```

Typical call:

```python
from nestquant.research.shared.evaluation import evaluate, EvaluationConfig
from nestquant.research.shared.evaluation.evaluator import evaluation_input_from_simulator
from nestquant.research.shared.provenance import build_provenance, ResearchLedger

result = evaluate(evaluation_input_from_simulator(sim), EvaluationConfig())
prov = build_provenance(evaluation=result, data=data_identity, strategy_identity="…")
ResearchLedger().append_provenance(prov, status="COMPLETE", result_ref=f"eval://{result.evaluation_id}")
```

## 10. ADRs

### ADR-1: Evaluation accepts execution results, not strategies/data
- **Context:** Phase 3 must not re-open Strategy 2 or the data layer; reporting
  needs one stable entry point.
- **Decision:** Public API is `evaluate(execution_result, config)`. Strategy
  construction, data loading, and execution stay outside evaluation.
- **Consequences:** Adapters (`evaluation_input_from_*`) are the only bridge;
  evaluation stays experiment-agnostic and frozen-data-layer friendly.

### ADR-2: Canonical metrics aligned with existing backtest formulas
- **Context:** `shared/backtest/metrics.py`, engine state, and architecture-plan
  metric tables disagree in places (win_rate fraction vs %, PF definition,
  Sharpe annualization).
- **Decision:** Canonical formulas = existing backtest/metrics.py behavior
  (win_rate fraction, profit_factor = Σwins/|Σlosses|, Sharpe √252 rf=0,
  min obs 2). Evaluation is the authority going forward; a regression test pins
  agreement on a shared fixture.
- **Consequences:** No silent semantic drift; callers of old helpers keep
  working; report can cite one definition per metric.

### ADR-3: Status separates validity from quality
- **Context:** Requirement forbids PASS/FAIL/GOOD/BAD and universal scores.
- **Decision:** `EvaluationStatus` is pipeline validity (`VALID` /
  `VALID_WITH_WARNINGS` / `INVALID`); per-metric `MetricStatus` is
  `DEFINED` / `UNDEFINED` / `NOT_APPLICABLE`. Quality comparison is left to
  explicit, scoped comparison — never a scalar score.
- **Consequences:** Downstream reports can show “metric undefined” honestly;
  zero-trade runs remain inspectable (`VALID_WITH_WARNINGS`).

### ADR-4: Fold aggregation pools closed trades; roles are explicit
- **Context:** Fold semantics were ad hoc; OOS stitching is forbidden without a
  methodology decision.
- **Decision:** `FoldRole` enum is always set (never inferred from dates);
  aggregate metrics use `pooled_closed_trades`; fold-level results always
  retained; no cross-fold equity stitch. If trades aren’t available, aggregate
  metrics are empty with an explicit warning rather than a fabricated number.
- **Consequences:** Aggregates are reproducible and conservative; walk-forward
  methodology remains a future, explicit design.

### ADR-5: Append-only JSONL ledger; no database
- **Context:** Ledger must answer run questions with zero new infrastructure;
  persistence architecture changes are a stop condition.
- **Decision:** JSONL, one immutable entry per line, append-only, duplicate
  `run_id` rejected. Default path `research/ledger/research_ledger.jsonl`.
- **Consequences:** Greppable, git-friendly, trivially portable; concurrent
  writers should coordinate externally (out of scope for Phase 3).

### ADR-6: Research-side git/config identity (no production imports)
- **Context:** Existing helpers live partly under `core/` (production-adjacent)
  and partly under `research/experiment.py`. Provenance must not import
  production.
- **Decision:** Reimplement fail-closed git subprocess helpers and deterministic
  sha256 config hashing in `research/shared/provenance/identity.py`, following
  the same patterns (and compatible hash length) as
  `core/configuration/experiment.py`.
- **Consequences:** Dependency direction stays data→execution→evaluation→
  provenance→reporting; production can change without breaking research
  provenance.

---

*Phase 3 — Canonical Evaluation + Provenance/Research Ledger.*
