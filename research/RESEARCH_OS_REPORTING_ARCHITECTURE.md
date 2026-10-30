# Research OS — Reporting Architecture

Phase 4 of Research OS. Freezes the presentation boundary over already-defined
research results. Reporting is **not** another analysis engine.

- Reporting package (Phase 4.1, not yet implemented): `research/shared/reporting/`
- Upstream frozen inputs: `research/shared/evaluation/`, `research/shared/provenance/`
- Dependency direction: **data → execution → evaluation → provenance → reporting**
- Phase 1–3 source remains frozen and unchanged.

**Core invariant:**

> If two renderers disagree about a metric, the renderer is wrong—not the research result.

---

## 1. What Phase 4 solves

| Layer | Question |
|---|---|
| Data (Phase 1, frozen) | What data did we research on? |
| Execution (Phase 2, frozen) | What happened when the strategy interacted with that data? |
| Evaluation (Phase 3, frozen) | How do we measure those results? |
| Provenance (Phase 3, frozen) | Exactly what produced those results? |
| **Reporting (Phase 4)** | **How do we communicate those results clearly and reproducibly?** |

Reporting consumes Evaluation + Provenance (and optional experiment context)
and turns them into human-readable research artifacts.

It must **not**:

- calculate alternative performance metrics
- decide whether a strategy is good
- rank strategies
- optimize parameters
- discover hypotheses
- modify trades
- perform statistical inference
- introduce its own definitions of metrics
- become a second evaluation framework

---

## 2. Inspection of frozen Phase 3 source (actual interfaces)

The architecture below references **only** types that exist in the frozen tree
at Phase 3 HEAD `008b846a93006d716f0b6c1d87ea56f9658bd229`.

### 2.1 Evaluation package (`research/shared/evaluation/`)

**Public surface (`evaluation/__init__.py`)** exports contracts, evaluator
helpers, metrics helpers, and comparison helpers.

Relevant frozen types:

| Type | Module | Role for Reporting |
|---|---|---|
| `EvaluationResult` | `contracts.py` | Canonical single-run evaluation face |
| `AggregateEvaluation` | `contracts.py` | Canonical multi-fold evaluation face |
| `EvaluationMetrics` | `contracts.py` | 19 typed `MetricValue` fields |
| `MetricValue` | `contracts.py` | `name`, `value`, `unit`, `definition`, `status` |
| `MetricStatus` | `contracts.py` | `DEFINED` / `UNDEFINED` / `NOT_APPLICABLE` |
| `EvaluationStatus` | `contracts.py` | `VALID` / `VALID_WITH_WARNINGS` / `INVALID` |
| `EvaluationConfig` | `contracts.py` | Evaluation conventions (rf, periods, min obs, …) |
| `Fold` / `FoldEvaluation` / `FoldRole` / `TimeWindow` | `contracts.py` | Fold identity and fold-bound results |
| `METRIC_SEMANTICS` | `metrics.py` | Canonical definition text per metric |
| `metrics_to_jsonable` | `metrics.py` | JSON-safe metric serialization |

**`EvaluationResult` fields (frozen):**

```text
evaluation_id: str
metrics: EvaluationMetrics
warnings: tuple[str, ...]
status: EvaluationStatus
configuration: EvaluationConfig
execution_ref: Optional[str]
fold: Optional[Mapping[str, Any]]          # optional embedded fold payload
experiment: Optional[Mapping[str, Any]]    # optional embedded experiment payload
```

**`AggregateEvaluation` fields (frozen):**

```text
fold_evaluations: tuple[FoldEvaluation, ...]
aggregate_metrics: EvaluationMetrics
aggregation_method: str                    # default "pooled_closed_trades"
warnings: tuple[str, ...]
status: EvaluationStatus
configuration: EvaluationConfig
evaluation_id: str
fold_count: int                            # property
```

**`FoldEvaluation` fields (frozen):**

```text
fold: Fold
evaluation: EvaluationResult
trades: Optional[Sequence[Trade]]          # optional; not required for presentation
```

**`Fold` fields (frozen):**

```text
fold_id: str
role: FoldRole                             # TRAIN|IS|OOS|VALIDATION|HOLDOUT|UNKNOWN
train_window / validation_window / test_window: Optional[TimeWindow]
metadata: Mapping[str, Any]
```

**Warnings representation:** `tuple[str, ...]` on both `EvaluationResult` and
`AggregateEvaluation`. Flat string codes (sometimes `code:N` or
`fold[id]:code`). **No severity field. No warning class hierarchy.**

**Aggregation semantics (frozen):** `aggregate_fold_evaluations` pools closed
trades and recomputes metrics; it does **not** average fold metrics; it does
**not** stitch equity curves. Path-dependent metrics depend on supplied fold
order. Documented in `RESEARCH_OS_EVALUATION_ARCHITECTURE.md` §4.5 and ADR-4.

### 2.2 Provenance package (`research/shared/provenance/`)

**`Provenance` fields (frozen):**

```text
run_id: str
experiment_id: Optional[str]
git: GitIdentity                            # commit, dirty, available
code_version: Optional[str]
data: DataIdentity                          # instruments, timeframe, window, source, ids, checksum, n_bars
strategy_identity: Optional[str]
execution_config / evaluation_config: Optional[Mapping]
execution_config_hash / evaluation_config_hash: Optional[str]
created_at: Optional[str]
evaluation_id: Optional[str]
evaluation_status: Optional[str]            # string form; provenance does not import evaluation enums
parent_run_id: Optional[str]
notes: tuple[str, ...]
```

**Fail-closed identity:** unavailable git → `commit=None`, `dirty=None`,
`available=False`. Missing data identity fields stay `None` / empty. Reporting
must present these as unavailable, never invent them.

**Ledger:** `ResearchLedger` / `LedgerEntry` persist provenance records
append-only. Reporting **reads conceptually from upstream records**; Reporting
**never writes** to the ledger.

### 2.3 What does **not** exist in Phase 3

| Absent concept | Consequence for Reporting |
|---|---|
| Phase 3 `ExperimentSpec` | **Do not invent one.** No hypothesis engine. |
| Canonical hypothesis / strategy model beyond `strategy_identity` | Experiment section is identity pass-through only. |
| Warning severity | Phase 4.1 preserves `tuple[str, ...]` only. |
| Report / report registry / report schema package | Phase 4.1 defines the first report contract. |
| Charts / equity presentation contract | Explicitly out of Phase 4.1. |

**Legacy note:** `research/experiment.py::ExperimentConfig` exists outside the
frozen Phase 3 shared evaluation/provenance packages. Reporting **must not**
import it.

---

## 3. Principle and dependency direction

```text
research/shared/data
        ↓
research/shared/execution
        ↓
research/shared/evaluation
        ↓
research/shared/provenance
        ↓
research/shared/reporting          ← Phase 4 (future implementation)
```

Forbidden edges from Reporting:

```text
reporting ─X→ strategy2
reporting ─X→ production
reporting ─X→ apparatus
reporting ─X→ specific experiment modules
```

Reporting is downstream presentation infrastructure only.

---

## 4. Locked Decision 1 — `ReportInput`

### 4.1 Shape

```text
ReportInput
├── evaluation: EvaluationResult              # single-run face
├── aggregate: Optional[AggregateEvaluation]  # multi-fold face
├── provenance: Provenance                    # required
└── experiment_context: Optional[Mapping]     # pure pass-through
```

### 4.2 Validation rules (XOR)

1. **Exactly one** of `evaluation` or `aggregate` must be supplied as the
   evaluation face.
   - `evaluation is not None` XOR `aggregate is not None`
   - Zero or both → builder validation error (fail closed).
2. `provenance` is **required** (`Provenance` instance).
3. `experiment_context` is **optional**.
4. `experiment_context` is a **pure pass-through mapping** — not a new
   experiment semantic model.
5. Reporting must not invent hypothesis, strategy, configuration, or experiment
   semantics that do not exist upstream.

### 4.3 Why two optional fields + XOR (not a union type)

The frozen source already provides two distinct evaluation faces
(`EvaluationResult` and `AggregateEvaluation`) with overlapping but not
identical fields. Two optional fields + XOR validation:

- mirrors the frozen types without inventing a parallel evaluation union
- keeps `isinstance` / field-presence checks explicit
- avoids a Reporting-owned union that could drift from Phase 3

**No concrete technical blocker** was found in the frozen source that would
require a different representation. If implementation later discovers one, the
STOP condition applies (§17): document the blocker; do not redesign Phase 3.

### 4.4 Single-run path

When `evaluation` is supplied:

- it is the canonical evaluation face;
- metrics come directly from `EvaluationResult.metrics`;
- status comes from `EvaluationResult.status`;
- warnings come from `EvaluationResult.warnings`;
- optional `evaluation.fold` / `evaluation.experiment` maps are passed through
  if present;
- reporting does **not** recalculate metrics;
- reporting does **not** normalize or reinterpret metric semantics.

### 4.5 Aggregate / multi-fold path

When `aggregate` is supplied, the aggregate object is the canonical evaluation face:

| Report need | Frozen source field |
|---|---|
| Fold list | `aggregate.fold_evaluations` |
| Fold-level metrics | each `FoldEvaluation.evaluation.metrics` |
| Fold identity / role / windows | each `FoldEvaluation.fold` |
| Aggregate metrics | `aggregate.aggregate_metrics` |
| Aggregation semantics | `aggregate.aggregation_method` |
| Aggregate status / warnings | `aggregate.status`, `aggregate.warnings` |

Reporting must **NEVER**:

- average fold metrics itself
- silently convert pooled metrics into averaged fold metrics or vice versa
- recompute fold metrics
- invent OOS stitching or walk-forward semantics
- infer fold overlap
- alter fold ordering relative to the supplied tuple

The rendered report must make **fold-level**, **aggregate/pooled**, and
**path-dependent** distinctions clear enough that a reader cannot reasonably
mistake one for the other.

---

## 5. Locked Decision 2 — `ResearchReport` (thin composition)

### 5.1 Shape

```text
ResearchReport
├── report_metadata: ReportMetadata
├── evaluation_face
│     = EvaluationResult
│     OR AggregateEvaluation
├── provenance: Provenance
└── experiment_context: Optional[Mapping]
```

`evaluation_face` represents **exactly one** canonical upstream object.

### 5.2 Thin composition rules

- Reporting does **not** own a rich parallel semantic model of evaluation fields.
- Sections (Summary, Experiment, Evaluation, Folds, Provenance, Warnings) are
  **projections** over the held objects — not independent sources of truth.
- The builder holds references/snapshots of frozen upstream objects; it does
  not fork metric values into Reporting-owned metric types that can drift.
- `ResearchReport` is the canonical Reporting object for all renderers.

### 5.3 Builder responsibilities

Input: validated `ReportInput`  
Output: `ResearchReport`

The builder must:

1. validate required inputs and XOR rule
2. assemble the thin composition (evaluation face + provenance + optional
   experiment context + report metadata)
3. **not** recalculate evaluation metrics
4. **not** invent provenance fields
5. produce a structure that renderers can project deterministically

The builder must **not**:

- average or re-aggregate folds
- rewrite warnings
- fill missing git/data/config identity
- attach scores, ranks, or quality labels

---

## 6. `ReportMetadata` (artifact identity only)

```text
ReportMetadata
├── report_type            # e.g. "research_report"
├── schema_version         # Reporting-owned schema version string
├── generated_at           # ISO timestamp when this artifact was rendered/built
└── renderer               # optional: renderer name / version IF genuinely available
```

### 6.1 Research identity vs artifact metadata

| Research identity (upstream — never owned by Reporting) | Report artifact metadata (Reporting-owned) |
|---|---|
| experiment identity (`Provenance.experiment_id`, context) | `report_type` |
| code identity (git commit / `code_version`) | `schema_version` |
| configuration identity (config hashes) | `generated_at` |
| data identity (`DataIdentity`) | `renderer` name/version if available |
| evaluation identity/status (`evaluation_id`, `status`, `evaluation_status`) | |

Rules:

- Reporting must not become a second provenance system.
- Reporting must not fabricate renderer/version information if unavailable
  (leave absent / explicit unavailable marker).
- `generated_at` is **allowed to be dynamic** (artifact metadata).
- Research identity fields are presented only as supplied by the upstream
  objects.

---

## 7. Canonical report sections (baseline vocabulary)

Sections are presentation projections. Exact Markdown layout is an
implementation detail; the **vocabulary and honesty rules** are architectural.

### 7.1 Summary

Factual summary only. May include:

- experiment identity where actually available
- trade/observation counts where defined upstream (`MetricValue`)
- canonical key metrics (formatted from `MetricValue`)
- evaluation status (`EvaluationStatus`)
- warnings (`tuple[str, ...]`)

**Forbidden automatic language** (unless explicitly supplied as
researcher-authored content in an upstream mapping such as
`experiment_context` or provenance notes):

`good`, `bad`, `strong`, `weak`, `excellent`, `poor`, `promising`, `robust`,
and equivalent quality judgments.

### 7.2 Experiment

Do **not** invent an `ExperimentSpec`. Derive identity from:

1. `Provenance` — `experiment_id`, `strategy_identity`, related identity fields
2. `evaluation.experiment` when the evaluation face is an `EvaluationResult`
   and the field is non-None
3. `experiment_context` when supplied (pure pass-through)

No hypothesis engine. No strategy-specific interpretation. No import of
`research/experiment.py`.

### 7.3 Evaluation

Display canonical metrics already produced upstream.

- Single-run: iterate `EvaluationResult.metrics` (`EvaluationMetrics.as_mapping()`
  or `to_dict()`); format each `MetricValue` (`value`, `unit`, `status`,
  optional `definition` / `METRIC_SEMANTICS` label).
- Aggregate: present `aggregate.aggregate_metrics` as the **aggregate** face,
  clearly labeled; do not present it as a single-run result without the
  aggregation context.

The exact metric vocabulary **must** be derived from the frozen Phase 3
`EvaluationMetrics` fields (19 metrics) — not a Reporting-side list that can
drift.

**STOP rule:** if Reporting discovers it needs a metric Evaluation does not
provide, stop. Do not calculate it in Reporting. Return the issue as an
architectural blocker for a future upstream Evaluation decision (§17).

### 7.4 Folds

Only relevant when the evaluation face is `AggregateEvaluation` (or when a
single `EvaluationResult.fold` payload is present and should be shown as
fold *metadata*, not as a fold series).

For aggregates, display:

- each `FoldEvaluation.fold` — id, role, windows, metadata
- each `FoldEvaluation.evaluation` — fold-level status, warnings, metrics
- `aggregate.aggregation_method`
- aggregate metrics labeled as aggregate/pooled
- `aggregate.fold_count`

Do not:

- recompute fold metrics
- average fold metrics
- invent OOS stitching or walk-forward semantics
- infer overlap
- alter fold ordering

Respect frozen Phase 3 limitations (path-dependent aggregates, fold-order
dependence, no capital-continuity claim across independent folds).

### 7.5 Provenance

Display the canonical `Provenance` object.

Where a field is unavailable (`None`, `available=False`, empty identity),
report it honestly as unavailable.

Never manufacture:

- Git commits
- data checksums
- versions
- timestamps (except Reporting-owned `ReportMetadata.generated_at`)
- experiment identifiers

Evaluation status must remain preserved:

- from evaluation face: `EvaluationResult.status` / `AggregateEvaluation.status`
- from provenance: `Provenance.evaluation_status` (string) when present

If both are present and equal, show consistently; if only one is present, show
that one; do not invent reconciliation logic beyond honest display.

### 7.6 Warnings & Limitations

**Reuse the frozen Phase 3 representation:** `tuple[str, ...]` (exact type on
`EvaluationResult.warnings` and `AggregateEvaluation.warnings`).

Phase 4.1 rules:

- Do **not** create a new warning framework.
- Do **not** add severity semantics in Phase 4.1.
- Preserve warning strings in order (and fold-prefixed forms when supplied).
- A **static presentation catalog** mapping known warning strings to
  explanatory text may be documented/used for display, but it remains
  presentation documentation — not a new inference or severity framework.
- Only display limitations **actually applicable** to the supplied result
  (e.g. do not claim equity-curve missing if that warning is absent).

Applicable Phase 3 limitations that Reporting may surface when present or
inherent in the presented metrics (via warnings, config, or documented
semantics of shown metrics) include:

- trade-sequence Sharpe methodology (when Sharpe is shown and convention
  applies)
- pooled fold / path-dependent metric limitations (when aggregate face is used)
- optional DataIdentity (when provenance data fields are empty)
- fold-order dependence (when aggregate path metrics are shown)
- duplicate trades counted as supplied (when that convention applies upstream)
- warning-based drawdown-source distinction (when drawdown warnings present)

Rendering must not hide uncertainty that the upstream objects already expose.

---

## 8. Rendering architecture

```text
ResearchReport
      │
      ├── MarkdownRenderer   → str (human-readable)
      │
      └── JsonRenderer       → str / structured dict (machine-readable)
```

### 8.1 Format independence

- `ResearchReport` is format-independent.
- Markdown and JSON are **sibling** renderers over the same object.
- JSON must **not** be generated by parsing Markdown.

### 8.2 Canonical serialization path

```text
ResearchReport.to_dict()
        ↓
structured dict (nested canonical upstream structures preserved)
        ↓
JsonRenderer.render(report)  → JSON string
```

- `ResearchReport` is the canonical Reporting object.
- JSON is **not** the semantic source of truth either; it is a serialization
  of the report object, which itself projects upstream truth.
- Nested canonical structures (`evaluation` / `aggregate`, `provenance`) should
  be preserved via their frozen `to_dict()` methods rather than flattened into
  presentation-only field names that lose type/status information.

### 8.3 Markdown requirements

Baseline section order (suggested; not exhaustive formatting lock):

```markdown
# Research Report

## Summary
## Experiment
## Evaluation
## Folds          <!-- when aggregate (or fold metadata) present -->
## Provenance
## Warnings & Limitations
```

Requirements:

- deterministic section ordering for a given report shape
- stable labels
- canonical metric values (from `MetricValue`, not recomputed)
- honest missing-value representation
- preserved warnings
- preserved fold semantics (aggregate vs fold-level distinction)
- no hidden calculations

Dynamic `generated_at` is allowed. For deterministic snapshot tests, the
mechanism must be explicit (inject fixed timestamp, or exclude/normalize the
timestamp line in comparison) — documented in test design when implemented.

### 8.4 File output / persistence

Keep rendering and persistence separate:

```text
renderer.render(report) -> str
# caller decides where to save the artifact
```

Phase 4.1 does **not** introduce:

- report database
- report registry
- automatic publishing
- report lifecycle management
- storage abstraction as a core Reporting responsibility

---

## 9. Ledger boundary

| Layer | Question |
|---|---|
| Ledger (Phase 3) | What experiments/results have been **recorded**? |
| Reporting (Phase 4) | How do we **present** one of those results? |

Rules:

- Reporting may consume/read canonical provenance information (and optionally
  be *given* a `Provenance` that was loaded from a ledger entry upstream).
- Reporting must **NEVER** automatically write to the Research Ledger.
- Rendering a report must not mutate research state.
- Ledger remains the upstream research-record mechanism.

---

## 10. Charts / visualization (explicitly out of Phase 4.1)

Phase 4.1 = **textual + structured reporting only**.

Excluded from Phase 4.1 architecture and any Phase 4.1 implementation:

- equity-curve contract
- OOS stitching for visualization
- drawdown visualization semantics
- fold visualization semantics
- chart data APIs

Rationale: those are upstream semantic questions. Adding them now would risk
forcing Reporting to invent research semantics.

Visualization may become a later architecture phase after the underlying
research objects justify it.

---

## 11. Explicit non-goals (Phase 4.1)

Reporting must not introduce:

- new evaluation metrics
- statistical inference (p-values, confidence intervals, significance tests)
- scoring
- ranking
- optimization
- strategy discovery
- strategy-specific report logic (`if strategy == ...`)
- Strategy 2 dependencies
- production dependencies
- apparatus dependencies
- HTML
- PDF
- charts
- dashboards
- web UI
- experiment comparison UI
- automated publishing
- report database
- report registry
- email/Telegram reporting
- portfolio analytics
- walk-forward engine
- OOS stitching methodology
- changes to frozen Phase 1–3 contracts

---

## 12. Testing architecture (specified, not implemented)

Phase 4 implementation must include these test categories. This section
defines intent only; no tests are created by this architecture task.

### 12.1 Contract tests

- required fields on `ReportInput` / `ResearchReport` / `ReportMetadata`
- XOR validation (evaluation only, aggregate only, neither, both → errors)
- serialization round-trip where applicable
- optional `experiment_context` present/absent
- missing optional values handled honestly
- schema/version fields present on report metadata

### 12.2 Builder tests

- canonical `EvaluationResult` is preserved (identity/metrics/status/warnings)
- canonical `AggregateEvaluation` is preserved (folds, aggregate metrics,
  method, status, warnings)
- provenance is preserved field-for-field (including unavailable fields)
- evaluation status preserved (evaluation face + `evaluation_status` string)
- experiment context passed through unchanged when supplied
- warnings preserved in order
- folds preserved (order, roles, fold-level results)
- **no metrics are recalculated** (compare against upstream `MetricValue`s)

### 12.3 Markdown renderer tests

- deterministic section ordering
- canonical metric values appear as supplied
- honest unavailable values for missing provenance
- warning preservation
- fold vs aggregate distinction visible
- no fabricated provenance
- no hidden calculations / no quality adjectives injected

### 12.4 JSON tests

```text
ResearchReport
    ↓ to_dict()
dict
    ↓
JSON
```

- preserves defined canonical nested structure
- lossless for the defined report contract
- JSON is not derived by parsing Markdown

### 12.5 Boundary tests

Reporting source must not import:

- `strategy2` / `apparatus`
- `production`
- forbidden evaluation-internal reverse edges beyond allowed upstream imports

Dependency direction remains downstream only.

### 12.6 Golden / snapshot report

One deterministic golden fixture:

1. deterministic `EvaluationResult` (fixed metrics, status, warnings)
2. minimal valid `Provenance` (and a variant with honest-unavailable git/data
   fields)
3. optional: deterministic `AggregateEvaluation` fixture for fold section
   (may be a second golden case)
4. render Markdown → compare to expected artifact

**Prerequisites to avoid:**

- Git cleanliness / live repository state must **not** be a prerequisite for
  the fixture (use constructed `Provenance` / `GitIdentity` values, not live
  `get_git_commit()`).
- Network, production, Strategy 2, or dashboard state must not be required.

---

## 13. Preservation requirement (frozen trees)

Phase 4 implementation must not require modifying:

```text
research/shared/data/
research/shared/execution/
research/shared/engines/
research/shared/evaluation/
research/shared/provenance/
research/experiments/strategy2/
production/
```

If a genuine upstream blocker is discovered during implementation:

**STOP.** Do not patch around it by duplicating upstream semantics in
Reporting. Document the blocker.

---

## 14. Intended package layout (not created by this task)

Illustrative only — Phase 4.1 implementation scope when authorized later:

```text
research/shared/reporting/
├── __init__.py
├── contracts.py          # ReportInput, ReportMetadata, ResearchReport
├── builder.py            # ReportInput → ResearchReport
├── renderers/
│   ├── __init__.py
│   ├── markdown.py
│   └── json.py
```

Optional later: a thin sections helper module if renderer duplication warrants
it. No report-template framework, no persistence module, no chart module in
4.1.

**This architecture task does not create this tree.**

---

## 15. Phase 4.1 scope

### In scope (when implementation is authorized)

- report contracts (`ReportInput`, `ReportMetadata`, `ResearchReport`)
- report builder (XOR validation, thin composition)
- canonical section projections
- Markdown renderer (deterministic)
- JSON serialization / renderer via `to_dict()`
- warnings/limitations presentation (preserve `tuple[str, ...]`)
- provenance presentation (honest unavailable)
- fold presentation (aggregate vs fold-level)
- tests per §12
- architecture documentation alignment with implementation

### Out of scope

HTML, PDF, charts, dashboards, web UI, comparison UI, automated publishing,
report DB/registry, email/Telegram, Strategy 2 migration, new evaluation
metrics, new statistical methods, scoring/ranking, portfolio analytics,
walk-forward visualization, any frozen Phase 1–3 contract change.

---

## 16. Acceptance gate (Phase 4.1)

Phase 4.1 is **ACCEPTED** only if:

1. Reporting has a documented contract.
2. Actual frozen Phase 3 interfaces are identified and referenced (this
   document §2; implementation matches).
3. No invented `ExperimentSpec`.
4. `ReportInput` uses the locked single-run/aggregate XOR model.
5. `ResearchReport` remains thin composition.
6. No duplicated evaluation semantics (no recalculated metrics).
7. Provenance remains canonical (no fabricated identity).
8. Evaluation status is preserved.
9. Fold semantics remain canonical (no averaging/stitching/overlap invention).
10. Warnings remain canonical/preserved (`tuple[str, ...]` semantics).
11. Missing provenance is represented honestly.
12. Markdown renderer contract documented (and implemented deterministically).
13. JSON renderer contract documented (and implemented via `to_dict()`).
14. `ResearchReport` is the shared semantic source for both renderers.
15. Determinism requirements documented (including timestamp handling for
    snapshots).
16. Golden-report test contract documented (and implemented without live git
    prerequisites).
17. Reporting has no Strategy 2 dependency.
18. Reporting has no production dependency.
19. Reporting has no apparatus dependency.
20. No charts/visualization semantics introduced.
21. No database/registry/publishing architecture introduced.
22. Frozen Phase 1–3 contracts remain untouched.

---

## 17. STOP condition

> If implementation of the approved architecture would require changing a
> frozen Phase 1–3 contract, **stop and report the blocker** rather than
> redesigning upstream architecture.

Likely blocker classes to watch (not currently expected from inspection):

- need for a metric not on `EvaluationMetrics`
- need for fold semantics not expressible from `AggregateEvaluation`
- need for provenance fields not on `Provenance`
- need for warning severity as a research fact (would be an upstream Evaluation
  decision, not a Reporting invention)
- need to write ledger state as a side effect of rendering (forbidden)

---

## 18. Relationship to Phase 3 documentation

| Document | Authority |
|---|---|
| `research/RESEARCH_OS_EVALUATION_ARCHITECTURE.md` | Evaluation + provenance semantics (Phase 3, frozen) |
| `research/RESEARCH_OS_REPORTING_ARCHITECTURE.md` | Reporting presentation boundary (Phase 4, this document) |
| Phase 3 final review / remediation handoffs | Acceptance history for Phase 3 |

Reporting documentation must not contradict Phase 3 metric definitions,
warning names, fold aggregation method, or provenance field meanings. Where
this document restates Phase 3 facts, Phase 3 source and architecture remain
authoritative.

---

*Phase 4 — Reporting Architecture. Architecture only; no Reporting implementation, tests, or package created by this document.*
