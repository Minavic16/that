# OpenCode Task Report

**Task:** Research OS Phase 2 — decouple the backtester into a strategy-agnostic execution core (`research/shared/execution/`), preserve exact trading behavior, on branch `research/strategy-2`
**Status:** COMPLETE
**Date:** 2026-09-22
**Author:** OpenCode (via NestQuant Orchestrator)

---

## Objective

Extract a strategy-agnostic execution core from `BacktestEngine` so entry fills, SL/TP exits, portfolio/cash state, and result metrics no longer live inside a strategy-coupled engine. Preserve bit-for-bit trading behavior on real research workloads. Do not touch Strategy 2 methodology, production/live, master, or the frozen data layer. Inventory only (no rewrite) the four duplicate research backtests. End with report, Termux notification, clipboard copy, and a clean commit on `research/strategy-2`.

## What Was Inspected

- `research/shared/engines/backtest_engine.py` (pre-change 279 lines): session filter, `BaseSignal`/`SignalResult`, `BreakerSuite`, entry/exit math, metrics all in one class.
- `research/shared/engines/{base_engine,regime_backtest_engine}.py`, `research/shared/backtest/{metrics,comparison}.py`, `research/shared/costs/model.py`, `core/contracts/execution_contracts.py`, `production/signals/base.py`, `core/tooling/indicators/session.py`, `production/risk/circuit_breakers.py`.
- Protecting tests: `tests/research/test_engines.py`, `test_backtest_metrics.py`, `test_signals.py`; Strategy 2 suite under `research/experiments/strategy2/tests/`.
- Duplicate backtests (inventory only, left frozen): `research/experiments/{zscore_mr_backtest,exit_surface,exit_forensics,signal_discovery}.py`.
- Assessment authority: `research/RESEARCH_OS_BUILD_READINESS.md` §12 Component 2 (Backtester Decoupling).
- Pre-change behavior baseline captured via git-stash replay to `/tmp/phase2_pre.json` / `/tmp/phase2_post.json`.

**Step 0 inventory (10 items):**

1. **Entry point:** `BacktestEngine.on_bar` / `RegimeBacktestEngine.on_bar`.
2. **Dependency graph (pre):** engines → `production.signals.base`, `production.risk.circuit_breakers`, `core.tooling.indicators.session`; metrics inline; costs module unused by engine.
3. **Responsibilities pre-change:** strategy signal call + session gate + fills + exits + cash + breaker recording + metrics all in `BacktestEngine`.
4. **Protecting tests:** `tests/research/test_engines.py` (18), `test_backtest_metrics.py` (13), `test_signals.py` (7).
5. **Reusable after extract:** `Trade`, `BacktestConfig`, `SignalIntent`, `Portfolio`, `ExecutionSimulator.get_results`.
6. **Duplicates:** 4 experiment-local backtests — frozen, not rewritten.
7. **Extraction boundary:** `research/shared/execution/` owns intent→fill→exit→portfolio→metrics; `BacktestEngine` remains thin adapter (session + signal generate + BreakerSuite); `RegimeBacktestEngine` unchanged logic, still subclasses adapter.
8. **Contract alignment:** `SignalIntent` mirrors `SignalResult` field names (`pair/direction/strength/entry/sl/tp/metadata/is_active`); `Trade`/`BacktestConfig` re-exported from old import path.
9. **Production imports after extract:** zero in `research/shared/execution/`; adapter still wires `BreakerSuite` (composition root).
10. **Out of scope confirmed:** OHLCVFrame migration, evaluation framework, Strategy 2, production changes, experiment backtest rewrites.

## What Was Changed

- New package `research/shared/execution/`:
  - `contracts.py` — `Trade`, `BacktestConfig`, `SignalIntent`, `to_signal_intent`.
  - `portfolio.py` — `Portfolio` (trades, open trades, balance, peak, reset/can_open/open).
  - `simulator.py` — `ExecutionSimulator.open_trade` / `check_exits(on_close=...)` / `get_results` with legacy cost/PnL math copied exactly.
- `BacktestEngine` rewritten as thin adapter: session filter, signal generation, `_to_intent` coercion, BreakerSuite recording via `on_close` callback (same per-trade ordering as before), `config`/`_trades`/`_open_trades`/`_balance`/`_peak_balance` exposed as properties so `RegimeBacktestEngine` and existing tests keep working without edits.
- Removed `production.signals` import from `backtest_engine.py` (duck-typed signal source).
- `Trade`/`BacktestConfig` remain importable from `nestquant.research.shared.engines.backtest_engine`.
- New tests `tests/research/test_execution_core.py` (15 tests): intent semantics, package boundary (no `production.` in execution sources; importing execution does not load `production.signals`), simulator open/exit/callback/ordering/zero-SL, portfolio reset, duck-signal engine, config setter, re-exports.
- Not changed: `regime_backtest_engine.py` logic, frozen data layer, experiment backtests, production runtime.

## Files Changed

| File | Change Type | Description |
|---|---|---|
| research/shared/execution/__init__.py | NEW | Package exports + boundary docstring |
| research/shared/execution/contracts.py | NEW | Trade, BacktestConfig, SignalIntent, adapter |
| research/shared/execution/portfolio.py | NEW | Portfolio cash/position state |
| research/shared/execution/simulator.py | NEW | Strategy-agnostic fills, exits, results |
| research/shared/engines/backtest_engine.py | MODIFIED | Thin adapter over execution core (−199/+55) |
| tests/research/test_execution_core.py | NEW | 15 decoupling/boundary/regression tests |
| research/handoff/phase2_backtester_decoupling_report.md | NEW | This report |

## Tests

- Command: `PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 python3 -m pytest tests/research/ -q` → **114 passed** (99 pre-existing research + 15 new).
- Command: `... pytest research/experiments/strategy2/tests/ -q` → **80 passed**.
- Behavior comparison: git-stash pre vs post workloads W1 stub-buy, W2 breakout, W3 regime-buy → **ALL_EXACT** (trades, PnL, equity, timestamps, lots, exit reasons identical).
- Representative workload numbers (unchanged): W1 3 trades PnL 549.3609101804602 balance 10549.3609; W2 1 trade PnL −204.60133035694784; W3 1 trade PnL 314.7119260915166.
- Two new-test authoring bugs fixed during execution (SL-before-TP bar fixture; zero-SL needs zero spread so adjusted entry equals SL).
- Pre-existing (not caused by this change; verified identical with changes stashed): `tests/platform/test_imports.py` legacy flat-path failures; `test_horizon_encoding.py` missing `arch`; 13 safety/shadow collection-or-test failures; 13 `tests/` collection errors under regression/unit/smoke/s8.

## Test Results

- PASS: 114/114 `tests/research/`.
- PASS: 80/80 Strategy 2 tests (excluding pre-existing `arch` horizon file).
- PASS: old-vs-new exact match on 3 real workloads.
- PASS: execution package source contains no `production.` imports.
- NOT YET PROVEN / pre-existing fails unchanged (listed above) — not introduced by Phase 2.

## Evidence

- Pre/post JSON: `/tmp/phase2_pre.json`, `/tmp/phase2_post.json` (exact deep-equality).
- Diff scope: only `backtest_engine.py` modified among tracked files; new untracked `research/shared/execution/` + test + this report.
- Branch: `research/strategy-2` (no push, no merge, master/production untouched).
- Data layer commits `ba44ed5` / `22fe320` untouched.

## Remaining Issues

- `BacktestEngine` adapter still imports `production.risk.circuit_breakers.BreakerSuite` (composition at adapter only; execution core clean). Full removal needs an observer injection interface — optional follow-up.
- Assessment also mentioned OHLCVFrame migration; deferred to keep fill/exit behavior bit-identical (still consumes raw OHLCV DataFrame columns as before).
- Four experiment duplicate backtests remain frozen (by design).
- Pre-existing test debt unchanged (imports path smoke, `arch`, safety/shadow, regression collection).

## Decisions Required

1. **Accepted default:** BreakerSuite stays on the thin engine adapter (zero production imports inside `research/shared/execution/`). Alternative: inject risk observer and delete the last production import from engines — flag if reviewer wants that in Phase 2.
2. **Accepted default:** OHLCVFrame migration deferred (behavior preservation priority). Alternative: follow-up ticket to type `on_bar`/`check_exits` with `OHLCVFrame`.
3. No Strategy 2 / data-layer decisions required.

## Recommended Next Action

Assessment §12 Component 3: **Evaluation Abstraction** (metric pipeline, fold evaluation, IS/OOS), consuming this execution core’s `get_results` / `Trade` outputs. Optionally first land the two flagged follow-ups (risk-observer injection, OHLCVFrame typing) if reviewer prioritizes closing Component 2 fully.

## Commit

_(filled after commit — see notification / final handoff)_

---
*Report generated by OpenCode. Review by ChatGPT/Claude before next action.*
