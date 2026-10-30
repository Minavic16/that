# NQTS / Research OS Phase 4 Reporting — Implementation Report

## 1. Objective

Implement Research OS Phase 4.1 ("Reporting") strictly per the approved architecture
document `research/RESEARCH_OS_REPORTING_ARCHITECTURE.md`:

- canonical `ReportInput` / `ResearchReport` contracts with fail-closed XOR validation;
- `ReportBuilder` thin composition over Phase 3 frozen `EvaluationResult` /
  `AggregateEvaluation` + `Provenance` (no metric recalculation, no provenance invention);
- sibling `MarkdownRenderer` and `JsonRenderer` (JSON via `to_dict()`, never from Markdown);
- deterministic golden fixture and Phase 4 test suite;
- zero changes to frozen Phase 1–3 trees or production.

## 2. Environment

- Repo path: `/root/that`
- Branch: `research/strategy-2`
- HEAD: `008b846a93006d716f0b6c1d87ea56f9658bd229` (Phase 3 frozen; unchanged)
- Architecture spec: `research/RESEARCH_OS_REPORTING_ARCHITECTURE.md`
  (845 lines, sha256 `0ead9abf2115cbf62b64eb3bc07c3ece56b04827f12590ad9483f011fd323b79`)

## 3. Files created (all new; no existing file modified)

```
research/shared/reporting/__init__.py            (897 B)
research/shared/reporting/contracts.py          (6800 B)
research/shared/reporting/builder.py            (1312 B)
research/shared/reporting/renderers/__init__.py  (258 B)
research/shared/reporting/renderers/markdown.py (15667 B)
research/shared/reporting/renderers/json.py     (1073 B)
tests/research/fixtures/__init__.py
tests/research/fixtures/reporting_fixtures.py
tests/research/fixtures/golden/research_report_single_run.md  (2827 B)
tests/research/test_reporting_contract.py
tests/research/test_reporting_golden.py
```

## 4. Implementation summary

### contracts.py
- `ReportInput(provenance, evaluation=None, aggregate=None, experiment_context=None)`;
  `validation_errors()` enforces exactly-one-of XOR (both → error, neither → error,
  provenance required). No union type; two optional fields.
- `ReportMetadata(report_type, schema_version, generated_at, renderer)` — artifact-level;
  `renderer` never fabricated by default.
- `ResearchReport(report_metadata, provenance, evaluation, aggregate, experiment_context)`;
  derived `evaluation_face`, `face_kind`, `status`, `warnings` (tuple preserved in order),
  `evaluation_id`, `get_metrics()` (canonical face metrics — evaluation.metrics or
  aggregate.aggregate_metrics, never recomputed), `to_dict()` / `from_dict()` using
  nested upstream frozen `to_dict()` paths.

### builder.py
- `build_report(report_input, metadata=None, generated_at=None)` → `ResearchReport`;
  raises `ResearchReportError` on any validation failure (fail closed). Pure assembly.

### renderers/markdown.py
- `MarkdownRenderer.render()` deterministic section order: header, Summary, Experiment,
  Evaluation, Folds (aggregate only / single-run fold note), Provenance,
  Warnings & Limitations.
- Metric rows render name/value/unit/`MetricValue.status` (UNDEFINED → `unavailable`,
  NOT_APPLICABLE → `n/a (not applicable)`); never a misleading number.
- Warnings preserved verbatim as `` `code` `` lines, order untouched; presentation-only
  `KNOWN_WARNING_TEXT` catalog supplies explanations for known Phase 3 codes; unknown
  codes render as-is. No severity invented.
- Forbidden quality adjectives are not emitted anywhere in renderer output.
- Limitations section is applicability-filtered (trade-sequence Sharpe, pooled/path
  dependence for aggregates, missing checksum, duplicate trades, warning-based DD,
  git unavailable, non-finite PnL).
- Aggregate fold section shows fold-level metrics + pooled aggregate metrics separately
  with explicit "not averaged" language.
- `render_with_renderer_meta()` stamps `renderer="markdown:1.0"` on a dataclass copy.

### renderers/json.py
- `JsonRenderer.render()` = `json.dumps(report.to_dict(), sort_keys=True, allow_nan=False)`
  after stamping `renderer="json:1.0"`. Never parses Markdown. Strict no-NaN.

### Experiment context
- `experiment_context` is pure pass-through (Mapping); no `ExperimentSpec` /
  `ExperimentConfig` import anywhere in the package.

## 5. Test results (all green)

| Suite | Command | Result |
|---|---|---|
| Phase 4 contract + golden | `pytest tests/research/test_reporting_contract.py tests/research/test_reporting_golden.py -q` | **30 passed** |
| Research OS regression | `pytest tests/research -q` | **198 passed** (168 frozen baseline + 30 new) |
| Strategy 2 regression | `pytest research/experiments/strategy2/tests -q` | **80 passed** |

Command environment: `PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1`.

Coverage of Phase 4 test plan:
- Contract: XOR both/neither rejected; provenance required; context pass-through; metadata roundtrip.
- Builder: identity-preserving (`is` checks), face_kind, status, warnings, evaluation_id,
  metrics-is-canonical, no-metric-recalculation (before/after dict equality),
  unavailable-provenance preservation, aggregate preservation + fold_count.
- Serialization: nested canonical `to_dict()` both faces; `from_dict()` roundtrip both faces.
- Markdown: 7 headings present, values + statuses, determinism (A==B), unavailable provenance
  (no fabricated 40-char sha), aggregate fold distinction, warnings verbatim, no quality adjectives.
- JSON: payload not-from-Markdown, nested status enum preserved, renderer id, no NaN/Infinity.
- Boundaries: no `nestquant.production` / `strategy2` / `apparatus` / `ResearchLedger` /
  `append_provenance` / `research.experiment` / `ExperimentConfig` tokens or imports in package.
- Golden: byte-exact snapshot match, cross-render stability, no live git dependency
  (constructed `GitIdentity`).

## 6. Validation

1. All 30 Phase 4 tests pass; full research suite 198; S2 suite 80 (exact frozen baselines).
2. Frozen-tree integrity: `git diff --name-only HEAD` over `research/shared/data`,
   `execution`, `engines`, `evaluation`, `provenance`, `strategy2/apparatus`, `production`
   → **empty** (zero modified tracked files anywhere: `git diff HEAD` = empty).
3. AST import scan of package → no violations; `production/` has no reporting imports.
4. Golden fixture verified independent of live Git (constructed identities, pinned timestamps).
5. No future information used: fixtures build trades deterministically; renderer only reads
   already-computed canonical metrics.

## 7. Git diff summary

- Tracked files modified: **none** (`git diff HEAD` empty).
- New untracked additions only: `research/shared/reporting/` (6 files),
  `tests/research/fixtures/` (3 files), 2 test files. All previously-listed untracked
  files left untouched per instructions.
- No commit made (not requested this step).

## 8. Safety confirmation

- **No live orders placed.** No MT5/order endpoint touched. `SHADOW_ONLY` not changed.
- No production, runner, dashboard, Telegram, signal-generation, risk, or execution
  configuration modified.
- No architecture redesign; no Phase 1–3 contract changes required → STOP condition not hit.

## 9. Conclusion (descriptive)

Phase 4.1 Reporting is implemented as a pure presentation boundary: one shared
`ResearchReport` object, two sibling renderers, fail-closed input validation, and
byte-exact golden coverage — with zero drift from the frozen research result.

Phase 4.1 complete. STOP per instruction (no cleanup/redesign).
