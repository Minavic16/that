# OpenCode Task Report

**Task:** Research OS Phase 3 — Source-Level Review / Freeze Gate (Canonical Evaluation + Provenance / Research Ledger)
**Status:** AWAITING_REVIEW
**Date:** 2026-09-24
**Author:** OpenCode (via NestQuant Orchestrator)

---

## 1. Executive Verdict

**REMEDIATION REQUIRED**

Phase 3 is architecturally close to freeze-ready: evaluation is strategy-agnostic, provenance does not fabricate git identity, the ledger is append-only with duplicate `run_id` rejection, comparison is descriptive only, and Phase 1 / Phase 2 / Strategy 2 remain untouched. Acceptance criterion **21 (documentation matches implementation)** fails in material ways, including a runtime `MetricValue.definition` that contradicts observed `total_trades` behavior, architecture-doc API/warning drift, undocumented fold-pooling capital-continuity limitation, and a documented `config_hash` empty-config rule that the code does not implement.

No BLOCKER was found (no production dependency, no Strategy 2 dependency, no Phase 1/2 semantic change, no silent OOS equity stitch, no universal score/winner).

## 2. Architecture Review — Evaluation Boundary

**Desired API:** `result = evaluate(execution_result, evaluation_config)`  
**Observed:** `research/shared/evaluation/evaluator.py:43-52` — `evaluate(execution_result, evaluation_config=None, ...)` accepts `EvaluationInput | Sequence[Trade] | Mapping`.

Exact evaluation-package imports:

| File | Imports |
|---|---|
| `evaluation/__init__.py` | only `evaluation.*` submodules |
| `evaluation/contracts.py` | `nestquant.research.shared.execution.contracts.Trade`, stdlib |
| `evaluation/metrics.py` | `evaluation.contracts`, `execution.contracts.Trade`, `math`, `numpy` |
| `evaluation/evaluator.py` | `evaluation.contracts`, `evaluation.metrics`, `execution.contracts.Trade` |
| `evaluation/comparison.py` | `evaluation.contracts` only |
| `evaluation/folds.py` | `evaluation.contracts`, `evaluation.evaluator` |

**Provenance imports:** `provenance/*` → stdlib + `provenance.contracts` / `provenance.identity` only. No `execution`, no `production`, no Strategy 2.

**Forbidden boundaries observed as absent:** `nestquant.production`, `strategy2`, `apparatus` in evaluation/provenance sources (grep). Runtime test `test_importing_evaluation_does_not_load_production_signals` passes.

**Strategy object requirement:** None. Adapters `evaluation_input_from_trades/simulator/engine` (`evaluator.py:147-225`) consume Phase 2 outputs only.

**Exact imports verdict:** evaluation → execution is present and acceptable; evaluation → production / Strategy 2 is not present.

## 3. Metric Review

Sources: canonical `research/shared/evaluation/metrics.py`; previous `research/shared/backtest/metrics.py`.

| Metric | Canonical formula (code) | Previous formula | Same / Different | Reason / notes |
|---|---|---|---|---|
| total_trades | `len(closed_valid)` where closed and finite pnl (`metrics.py:246-289`) | `len(pnls)` (`backtest/metrics.py:60`) | **Different (edge)** | Canonical excludes non-finite pnl from count; definition text still says “exit_price is not None” |
| winning_trades | `pnl > 0` count | `pnls[pnls>0]` | Same (normal) | |
| losing_trades | `pnl < 0` count | `pnls[pnls<0]` | Same (normal) | |
| breakeven_trades | `pnl == 0` count | not a field | Canonical-only | |
| win_rate | `wins/n` (breakeven in denominator; optional numerator flag) | `winning/total` | Same (default) | Fraction, not percent |
| gross_profit | `sum(positive pnls)` | not exposed (inside PF) | Compatible | |
| gross_loss | `sum(negative pnls)` (negative) | not exposed | Compatible | |
| profit_factor | `gp/abs(gl)`; no losses+gp>0 → `None`+`NOT_APPLICABLE`; no wins+no losses → UNDEFINED | `inf` if no losses; `0.0` empty input | **Different (edge encoding)** | Same ratio when both sides defined; canonical avoids JSON inf |
| total_pnl | `sum(pnls)` | same | Same | |
| average_win / average_loss | mean of side; empty → UNDEFINED | empty → `0.0` | **Different (edge)** | Canonical does not fabricate 0 |
| expectancy | `mean(pnls)` | same | Same | Architecture text “total_pnl/n” equivalent when finite |
| max_drawdown | equity balances path if provided; else `initial + cumsum(closed_valid)` | always `initial + cumsum(pnls)` | **Same family; path source differs** | Canonical prefers equity; warns on fallback |
| max_drawdown_pct | `dd/peak*100` (peak≠0 else 0) | same structure | Same family | Simulator `get_results()["max_drawdown"]` is percent (pre-existing Phase 2 unit quirk; unchanged) |
| total_return | `(end-start)/start` if start>0 | not in backtest/metrics | Canonical-only | |
| sharpe_ratio | `mean(pnl-rf)/std(pnl)*sqrt(252)`; n<2 or std=0 → UNDEFINED | same formula when std>0 and n>1; else `0.0` | **Same formula; different edge** | Canonical does not return 0 for undefined |
| sortino / recovery / largest_win / largest_loss | absent | present in backtest/metrics | Not migrated | Out of Phase 3 canonical 19 |
| duration averages | mean `(exit-entry)` seconds by side | `avg_trade_duration` optional/None mostly | Canonical more complete | |

**Semantic authority:** evaluation/metrics is declared canonical (ADR-2, arch §7). `backtest/metrics.py` remains compatibility authority. Strategy 2 / R2.1 forecast metrics remain strategy-specific (not imported).

## 4. Drawdown Review

**Code:** `max_drawdown_from_path` (`evaluation/metrics.py:212-230`); source selection (`metrics.py:360-388`).

Behavior:

1. If `equity_curve` non-empty: path = balance series from `EquityPoint.balance`. Non-finite → `ValueError` → `evaluate` returns `INVALID` (`evaluator.py:109-123`).
2. Else trade-normalized path: `trade_equity_path(closed_valid, initial_balance or 0.0)`.
3. Fallback warnings:
   - equity missing + initial known: `equity_curve_missing_trade_normalized_drawdown`
   - equity missing + initial unknown: `equity_curve_missing_and_initial_balance_unknown` (base 0.0)
4. Metric unit is currency; `max_drawdown_pct` is percent of running peak.

**Contract distinction:** `METRIC_SEMANTICS["max_drawdown"]` documents both sources. Downstream can distinguish **when warnings are present** on `EvaluationResult.warnings`. There is **no per-metric source field** (e.g. `source=equity|trade_normalized`); when equity is supplied, no positive warning labels “this is equity DD”.

**Masquerade check:** fallback is intentional, warned, and not named as equity-only in the definition. Residual risk: consumers that ignore warnings see a single `max_drawdown` name for two different economic quantities. Flagged as MATERIAL documentation/labeling gap (Issue M-3), not as silent equivalence in code.

**Aggregate drawdown:** when fold trades are pooled, `initial_balance=None` → path base 0.0 + warning above. Arithmetic is peak-to-trough of concatenated closed-trade cumsum — valid as **trade-sequence** DD, not as independent-fold portfolio DD (see §6).

## 5. Sharpe Review

**Code:** `metrics.py:408-426`.

| Aspect | Observed |
|---|---|
| Return series | Per-trade closed PnL array `pnls` (not bar/equity time series) |
| Annualization | `* sqrt(periods_per_year)` default 252 (`EvaluationConfig`) |
| Risk-free | `excess = arr - risk_free_rate` per trade (default 0.0); matches previous code’s per-period subtraction |
| Min obs | `< min_observations_for_sharpe` (default 2) → UNDEFINED + warning |
| Zero variance / non-finite std | UNDEFINED + warning (not 0, not inf) |
| vs previous | Formula equal when defined; previous returns `0.0` on n≤1 or std=0 |
| Explicit / deterministic / documented | Yes — `EvaluationConfig`, `METRIC_SEMANTICS["sharpe_ratio"]`, ADR-2 |

**Methodological ambiguity (flagged, not resolved):** annualizing a **trade-PnL** series with √252 assumes ~daily-equivalent observation frequency. Trades are not necessarily daily. This convention is explicit, deterministic, consistent with prior in-repo code, and documented — but it remains a **methodology choice**, not a universal Sharpe definition. Also, non-zero `risk_free_rate` is applied as a per-trade absolute subtract (same pattern as `backtest/metrics.py:89`), despite the older docstring saying “annual” rate. Flag as methodology documentation debt, not as divide-by-zero / silent-inf bug (those paths are guarded).

## 6. Fold Review

**Contracts:** `FoldRole` enum (`contracts.py:31-39`) — TRAIN/IS/OOS/VALIDATION/HOLDOUT/UNKNOWN; never inferred from chronology. `Fold` carries optional windows + metadata; single runs may omit folds (`Fold` only used when provided). `FoldEvaluation` = fold + `EvaluationResult` + optional `trades`.

**`aggregate_fold_evaluations` (`evaluator.py:228-310`):**

| Question | Observed behavior |
|---|---|
| Trades available? | Concatenate `fe.trades` → `compute_metrics(all_trades, initial_balance=None)` — **recompute from underlying observations**, not average of fold metrics |
| Trades absent? | `EvaluationMetrics.empty()` + warning `aggregate_without_trades_unavailable_use_fold_results` |
| Which metrics recomputed? | Full canonical set from pooled closed trades (counts, rates, PF, expectancy, DD on trade path, Sharpe on pooled pnls, durations, total_return) |
| Which remain unavailable? | Without trades: all aggregate metrics UNDEFINED/empty. With trades but start≤0: total_return UNDEFINED; Sharpe may be UNDEFINED |
| Drawdown mathematically valid? | Valid as **pooled trade-sequence** DD from base 0; **not** a multi-portfolio equity DD; warned for missing equity/initial |
| Sharpe mathematically valid? | Valid as Sharpe of concatenated trade-PnL series; not average-of-fold-Sharpes (good) |
| Capital continuity preserved? | **No** — independent fold capitals are not modeled; pooled path pretends sequential continuity of the trade list |
| Fold ordering relevant? | Yes for path-dependent DD/Sharpe; order = input sequence; **not validated** |
| Fold overlap detected? | **No** |
| Can aggregate imply continuous portfolio? | **Yes**, for path-dependent metrics, if folds were independent — no dedicated warning |

**Verdict:** Aggregation correctly avoids the classic invalid pattern `mean(fold_sharpe)` / `mean(fold_PF)` by recomputing from pooled trades when trades exist, and refuses to invent numbers when trades are missing. The residual issue is **labeling/limitation**: path-dependent aggregates across independent IS/OOS/holdout folds can be misread as one continuous book. ADR-4 documents “pooled_closed_trades” and “no equity stitch” but not the independence/capital-continuity caveat. → Issue M-4.

## 7. OOS Stitching Review

- No equity-curve merge across folds (`aggregate` never builds stitched equity).
- No walk-forward generation.
- Trade-list concatenation is **not** equity stitching; method id is explicit `pooled_closed_trades`.
- Fold roles remain explicit on each `FoldEvaluation`.

**Verdict:** No implicit OOS **equity** stitching methodology. Trade pooling limitation is separate (M-4), not a stitching engine.

## 8. Provenance Review

| Field | Source | Reliable? | Optional? | Fabrication risk |
|---|---|---|---|---|
| run_id | `new_run_id()` uuid4[:16] or caller | Event-unique (not content hash) | auto | Low |
| experiment_id | duck-typed `experiment_id`/`id` | If caller supplies | Yes | None if absent → None |
| git.commit | `git rev-parse HEAD` subprocess | High when repo present | Yes | **Never fabricated** — None on failure (`identity.py:27-42`) |
| git.dirty | `git status --porcelain` | High when present | Yes | None on failure |
| git.available | `commit is not None` | Derived | — | Honest |
| code_version | same as commit | Derived | Yes | None mirrors commit |
| data.* | `DataIdentity` / mapping duck-type | Only as good as caller | All optional | Empty → empty identity, not fake checksum |
| strategy_identity | arg or execution class name | Derived weakly | Yes | Class name can be generic (`BacktestConfig` path returns type name of config holder) — not a false SHA |
| execution_config / hash | `asdict`/to_dict + sha256[:16] | Deterministic if mapping JSON-safe | Yes | Hash only of provided keys |
| evaluation_config / hash | EvaluationConfig.to_dict / mapping | Deterministic | Yes | |
| evaluation_id | from EvaluationResult | Reliable if result passed | Yes | |
| created_at | `now_iso()` UTC or arg | Wall clock | auto | Not backdated unless caller passes |
| parent_run_id | arg | If supplied | Yes | |
| evaluation_status | **captured in builder as `_eval_status` then dropped** | N/A | — | Not stored on `Provenance` (Issue m-2) |

## 9. Data Identity Review

`DataIdentity` fields: instruments, timeframe, start/end, source/path, dataset_id/version, checksum, n_bars (`provenance/contracts.py:33-71`).

- **Honest:** all optional; `data=None` → empty identity; no invented checksum.
- **Useful when filled:** source + window + instruments + timeframe + optional checksum/version is enough to point at a dataset without mandatory full-file hashing (spec allows this).
- **Collision risk:** two different datasets **can** share identity if caller supplies only the same high-level window/instruments and omits checksum/version. That is a **caller completeness** limitation, not silent fabrication. Document as acceptable-but-partial (Issue m-3 MINOR).

## 10. Configuration Identity Review

`config_hash` (`identity.py:67-78`):

- `sort_keys=True`, compact separators, UTF-8 SHA-256 → 16 hex — deterministic for key order.
- Nested lists/dicts handled by `json.dumps`.
- `default=str` for non-JSON types (stringifies rather than failing) — can hash two different objects to same string form (edge).
- `None` → `None`.
- **Empty `{}` → actual hash** (probe: `44136fa355b3678a…`), **not** `None`, contradicting docstring/arch “Empty/None → None” (Issue m-1).
- No automatic inclusion of timestamps unless caller puts them in the mapping — caller must avoid ephemeral fields (not enforced).

## 11. Git Identity Review

| Case | Behavior |
|---|---|
| Clean tree | commit SHA, dirty=False |
| Dirty tree | commit SHA, dirty=True |
| Detached HEAD | `rev-parse HEAD` still returns SHA |
| Missing git / timeout / not a repo | commit=None, dirty=None, available=False |
| Fabrication | **Never** |

Probe with non-repo `cwd` (`test_provenance_without_git_fails_closed`) passes.

## 12. Run ID Review

- Format: `run-` + 16 hex of `uuid4` (`identity.py:18-20`); evaluations `eval-` + 16 hex (`evaluator.py:28-29`).
- Uniqueness: event-based random; not a content hash; not deterministic.
- Collision: practical 64-bit space; ledger rejects duplicate `run_id` on append.

## 13. Ledger Review

`ResearchLedger` (`ledger.py:117-168`):

| Operation | Behavior |
|---|---|
| append new | open mode `a`, one JSON line, `sort_keys=True` |
| append existing run_id | `ValueError("ledger run_id already exists: ...")` |
| read | full-file line parse → `LedgerEntry` |
| overwrite history | **Not implemented** — no rewrite API |
| serialize/deserialize | Tested; round-trip stable for entry dict |
| concurrency | Out of scope — **stated honestly** in ADR-5 (“concurrent writers should coordinate externally”) and arch §5.4 |

**Existing + new = append; existing + same id = rejected.** Verified by source and tests `test_append_only_preserves_prior`, `test_no_silent_overwrite`.

## 14. Serialization Review

- Ledger lines: `json.dumps(..., sort_keys=True, default=str)` — deterministic per entry.
- Timestamps: `datetime.now(UTC).isoformat()` — timezone-aware.
- Enums: stored via `.value` on eval/fold/metric status paths.
- `EvaluationResult.to_dict` uses `metrics.to_dict()` **not** `metrics_to_jsonable()`. Current metric builders avoid `inf` (PF uses None+NOT_APPLICABLE); probe `json.dumps(evaluate([]).to_dict())` succeeds. Residual: if a future metric value were non-finite, standard `json.dumps` would emit `Infinity` (non-strict JSON). `metrics_to_jsonable` exists (`metrics.py:481-492`) but is unused by `EvaluationResult.to_dict` (Issue m-4 MINOR).
- Round-trip tests: evaluation result dict, provenance dict, ledger line — present and passing.

## 15. Immutability Review

| Type | Mutable? | Risk |
|---|---|---|
| `EvaluationResult` | `frozen=True` dataclass; metrics/warnings/config frozen or tuples | Attribute mutation blocked |
| Nested `fold`/`experiment` | plain dicts (shallow-copied at build) | Nested values could be mutated if shared — low |
| `Provenance` | frozen | OK; `execution_config` is Mapping reference if caller reuses dict |
| `LedgerEntry` | frozen; persisted as line | File is append-only; in-memory frozen |
| Input `Trade[]` | mutable Phase 2 objects | Metrics already snapshotted into `EvaluationResult`; **aggregate** re-reads `FoldEvaluation.trades` at call time — mutation between fold eval and aggregate would affect aggregates only |

Material risk: low for stored evaluation evidence; moderate only if callers mutate trades before a later aggregate. Flagged MINOR.

## 16. Dependency Direction Review

```
data (Phase 1) → execution (Phase 2) → evaluation → provenance → reporting
```

- Evaluation depends on execution contracts only.
- Provenance depends on evaluation only via duck-typed builder args (no hard import of evaluation required in provenance modules — builder uses `hasattr`).
- No reverse edges to production/Strategy 2/data in Phase 3 packages.
- Reporting not implemented (correctly downstream/absent).

## 17. Compatibility Review

| Boundary | Evidence | Result |
|---|---|---|
| Phase 1 data | `git status` / diff clean for `research/shared/data`; no Phase 3 imports of data package | Untouched |
| Phase 2 execution | Diff clean for `execution/` + `engines/`; last execution commit remains `adc898c` | Untouched |
| `get_results()` keys | Test asserts superset of `total_trades, win_rate, profit_factor, total_pnl, max_drawdown, sharpe_ratio, avg_win, avg_loss, expectancy, trades` | Preserved |
| Strategy 2 | 80 tests pass; no evaluation/provenance imports in strategy2 tree; no strategy2 imports in Phase 3 | Untouched |
| Pre-existing failures | platform 44 fail / safety 13 fail / 13 collection errors — no Phase 3 references in those suites | Unrelated |

**Note (pre-existing, not introduced):** `ExecutionSimulator.get_results()["max_drawdown"]` is a **percent**, while `backtest/metrics.max_drawdown` and canonical `max_drawdown` are **currency**. Phase 3 did not change this; canonical evaluator uses currency + separate pct field.

## 18. Test Review

**Counts (re-run this review):**

- `tests/research/` → **162 passed** (matches report)
- `research/experiments/strategy2/tests/` → **80 passed** (matches report)

**What tests genuinely protect:**

- Metric edge cases: zero trades, all-win PF, Sharpe undefined, non-finite pnl, open trades, equity vs trade DD, duration, round-trip, no score field — **real**.
- Boundaries: source scan for `nestquant.production` / `strategy2` / `apparatus`; runtime import check — **real** (scan-based, not AST — acceptable).
- Fold aggregation: with trades / without trades / zero folds — **real** but does **not** assert independence/capital-continuity caveats.
- Provenance/ledger: run id, config hash determinism, git fail-closed, append-only, duplicate reject, serialize — **real**.
- Compatibility: get_results keys, canonical vs backtest formulas — **real** for shared formulas.

**Weak / non-protective spots:**

- `test_engine_to_evaluation`: asserts `total_trades.status` in `("DEFINED","UNDEFINED")` and status in VALID* — nearly tautological; does not assert non-zero trades or metric correctness on engine path.
- No test that `MetricValue.definition` text matches exclusion behavior for non-finite pnl (would have caught M-1).
- No test for architecture-documented APIs (`pair=` arg, `zero_folds_no_aggregate_metrics` name, empty `config_hash is None`).
- No AST import graph beyond substring scan (minor).

## 19. Documentation Review

Doc under review: `research/RESEARCH_OS_EVALUATION_ARCHITECTURE.md`.

| Area | Match? | Notes |
|---|---|---|
| Layering / non-goals / ADRs 1-6 | Yes | Aligns with code structure |
| Metric set / statuses | Mostly | Claims `open_trades_excluded` is a metric — **not in EvaluationMetrics** (warning only) |
| total_trades definition | **No** | Doc + METRIC_SEMANTICS say closed-by-exit; code excludes non-finite pnl |
| Fold warning name | **No** | Doc: `zero_folds_no_aggregate_metrics`; code: `aggregate_zero_folds` |
| Simulator adapter example | **No** | Doc: `evaluation_input_from_simulator(simulator, pair="EUR/USD")`; code: no `pair` parameter |
| config_hash empty → None | **No** | Doc/docstring say None; code hashes `{}` |
| Ledger append-only / concurrency honesty | Yes | ADR-5 states concurrent writers out of scope |
| Drawdown dual-source | Partial | Documented in METRIC_SEMANTICS; no per-metric source label; aggregate independence caveat missing |
| Sharpe convention | Yes | Explicit; methodology caveat not elevated in arch doc |
| Provenance evaluation_status | **No** | Builder extracts status and discards it; arch doesn’t mention the gap |
| Duplicate authority | Yes | ADR-2 + §7 name evaluation as authority, backtest as compat |

## 20. Status Model / Comparison Review

- `EvaluationStatus`: VALID / VALID_WITH_WARNINGS / INVALID only (`contracts.py:15-20`). Zero trades → VALID_WITH_WARNINGS (`evaluator.py:32-40`).
- `MetricStatus`: DEFINED / UNDEFINED / NOT_APPLICABLE.
- No good/bad/strong/weak/promising/robust/winner/score fields on evaluation results (grep + tests).
- `compare_evaluations`: absolute/relative diffs only; no rank/winner; no hidden score function.

## 21. Issues

### M-1 — MATERIAL  
**File:** `research/shared/evaluation/metrics.py`  
**Function/class:** `METRIC_SEMANTICS["total_trades"]`, `compute_metrics`  
**Observed:** Definition string: “Count of closed trades (exit_price is not None).” Implementation counts only closed trades with **finite** pnl (`closed_valid`). Probe: trades `[10, nan, -5]` → `total_trades=2` while definition still claims all closed.  
**Why it matters:** `MetricValue.definition` is part of the evidence contract shown to consumers; criterion 21 requires doc/impl match; silent redefinition of “total trades” on data-quality edges.  
**Required change:** Align definition text (and architecture metric table) with finite-pnl exclusion **or** count all closed trades and report non-finite separately — without changing frozen Phase 1/2.

### M-2 — MATERIAL  
**File:** `research/RESEARCH_OS_EVALUATION_ARCHITECTURE.md` (+ `evaluation_input_from_simulator` example)  
**Function/class:** §4.1 API example; §4.3 metric table; §4.5 zero-fold warning name  
**Observed:** (a) documents `evaluation_input_from_simulator(simulator, pair=...)` but signature is `(simulator)` only; (b) lists `open_trades_excluded` as a metric field — not in `EvaluationMetrics`; (c) documents warning `zero_folds_no_aggregate_metrics` — code emits `aggregate_zero_folds`.  
**Why it matters:** Architecture doc is controlling design/implementation map; drift fails criterion 21 and misleads Phase 4 consumers.  
**Required change:** Correct doc (or code if a pair filter was intended) to a single truth.

### M-3 — MATERIAL  
**File:** `research/RESEARCH_OS_EVALUATION_ARCHITECTURE.md`, `evaluation/metrics.py`  
**Function/class:** `compute_metrics` drawdown source selection / `EvaluationMetrics.max_drawdown`  
**Observed:** Equity-path DD and trade-normalized DD share one metric name; distinction only via result-level warnings and prose. No per-metric `source` (equity vs trade path). Aggregate path additionally runs with `initial_balance=None`.  
**Why it matters:** Spec Q4: these must not be silently treated as equivalent; consumers who drop warnings cannot distinguish portfolio equity DD from trade-sequence DD.  
**Required change:** Document limitation explicitly in arch + consider a stable label/warning contract Phase 4 can rely on (do not silently merge semantics).

### M-4 — MATERIAL  
**File:** `research/shared/evaluation/evaluator.py`  
**Function/class:** `aggregate_fold_evaluations`  
**Observed:** Pools trades across folds and recomputes path-dependent metrics (drawdown, Sharpe, total_return) on a single concatenated trade sequence with base-0 equity path. No fold-order validation, no overlap detection, no warning that folds may be independent portfolios. ADR-4 documents pooling and “no equity stitch” but not capital-continuity/non-independence limitation.  
**Why it matters:** Spec Q10.7–Q10.10: aggregate can imply a continuous book when folds were independent; acceptance criterion 8 requires honest unavailability rather than misleading fabricates — arithmetic is defined, **interpretation is under-warned**.  
**Required change:** Document the limitation in ADR-4/arch §4.5 (and/or emit an explicit multi-fold path-metric warning). Do not average fold metrics.

### m-1 — MINOR  
**File:** `research/shared/provenance/identity.py`  
**Function/class:** `config_hash`  
**Observed:** Docstring/arch: empty/None → None; code: `None` → None, `{}` → hash.  
**Why:** Doc/impl mismatch (criterion 21).  
**Required change:** Implement empty→None or fix docs.

### m-2 — MINOR  
**File:** `research/shared/provenance/builder.py`  
**Function/class:** `build_provenance`  
**Observed:** `_eval_status` computed from `evaluation.status` then discarded; `Provenance` has no `evaluation_status` field (ledger entry can still take it only if caller passes separately).  
**Why:** Partial identity capture; easy to assume status was stored.  
**Required change:** Persist status on Provenance or stop extracting it; document.

### m-3 — MINOR  
**File:** `research/shared/provenance/contracts.py` / builder  
**Function/class:** `DataIdentity`  
**Observed:** Identity honest but optional; two distinct datasets can collide if caller omits checksum/version/source.  
**Required change:** Document required fields for reproducibility-grade runs (no mandatory hashing).

### m-4 — MINOR  
**File:** `research/shared/evaluation/contracts.py` / `metrics.py`  
**Function/class:** `EvaluationResult.to_dict`, `metrics_to_jsonable`  
**Observed:** `to_dict` bypasses `metrics_to_jsonable`; non-finite values would serialize as JSON `Infinity` if ever stored. Current builders avoid inf for PF.  
**Required change:** Route `to_dict` through jsonable helper or assert finite invariants.

### m-5 — MINOR  
**File:** `tests/research/test_evaluation_metrics.py`  
**Function/class:** `TestExecutionToEvaluationContract` (contract file) / engine adapter test  
**Observed:** Engine-path assertions are weak (status enum membership); would not catch wrong trade counts.  
**Required change:** Strengthen with non-trivial fixture assertions.

### m-6 — MINOR  
**File:** `research/shared/evaluation/metrics.py`  
**Function/class:** `compute_metrics`  
**Observed:** Duplicate trade objects are counted as distinct closed trades; no dedup or warning (spec Q7 listed duplicates).  
**Required change:** Document “duplicates counted as provided” as intentional convention.

### METHODOLOGY-1 — FLAG ONLY (not a coding bug)  
**File:** `evaluation/metrics.py` Sharpe  
**Observed:** Trade-PnL series annualized with √252; rf applied per trade. Explicit and consistent with prior repo code; frequency assumption is a methodology choice.  
**Required change:** None in code; reviewer/report must not treat as portfolio time-series Sharpe without stating the convention.

## 22. Acceptance Criteria Scorecard

| # | Criterion | Result |
|---|---|---|
| 1 | Evaluation strategy-agnostic | PASS |
| 2 | No production dependency | PASS |
| 3 | Metric semantics explicit | PASS (with M-1 definition defect) |
| 4 | Calculations correct vs stated definitions | PASS normal paths; **FAIL** total_trades vs its stated definition on non-finite edge |
| 5 | Edge cases honest | PASS largely (zero trades, PF inf, Sharpe undef) |
| 6 | Drawdown semantics explicit | **PARTIAL** (M-3) |
| 7 | Sharpe semantics explicit | PASS (methodology flagged) |
| 8 | Fold aggregation not fabricating invalid metrics | PASS on recompute/empty policy; **PARTIAL** on independence labeling (M-4) |
| 9 | IS/OOS explicit | PASS |
| 10 | No implicit OOS stitching | PASS (no equity stitch) |
| 11 | Comparison descriptive | PASS |
| 12 | Provenance no fabrication | PASS |
| 13 | Data identity meaningful | PASS with documented optional gaps |
| 14 | Config identity deterministic | PASS core; empty-config doc mismatch (m-1) |
| 15 | Ledger append-only + reject dups | PASS |
| 16 | Serialization round-trip | PASS tests; minor inf path (m-4) |
| 17 | Phase 1 untouched | PASS |
| 18 | Phase 2 compatible | PASS |
| 19 | Strategy 2 untouched | PASS |
| 20 | Tests protect architecture | PASS with weak spots (m-5) |
| 21 | Documentation matches implementation | **FAIL** (M-1, M-2, M-3, M-4, m-1, m-2) |
| 22 | Duplicate authority explained | PASS (ADR-2/§7) |

## 23. Final Verdict

**REMEDIATION REQUIRED**

Safe to re-review for freeze after MATERIAL issues are resolved (doc/contract alignment + fold-pooling limitation made explicit). No BLOCKER; Phase 1/2/Strategy 2 freeze integrity holds.

---

*Phase 3 source-level freeze-gate review. Read-only. No code, tests, docs, commits, or pushes were modified by this review task except this report file.*
