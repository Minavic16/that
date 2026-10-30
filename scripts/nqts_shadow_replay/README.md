# NQTS Post-9 Shadow Replay — ANALYSIS ONLY

**Classification:** analysis-only tooling. NOT part of any frozen architecture.
**Location:** `scripts/nqts_shadow_replay/` (outside `research/shared/*` and `production/*`).

## What this does

Reads the append-only shadow logs copied from the NQTS live-shadow runner
(evidence/), resolves the signal population, and replays each signal against
the market bars that followed it, using **unchanged, imported** canonical
components:

- `nestquant.research.shared.execution.ExecutionSimulator` + `BacktestConfig`
  (frozen Phase 2 execution core) — fills, spread/slippage, SL-before-TP exit
  ordering, commission, P&L.
- `nestquant.production.execution.risk_guard.RiskGuard` + `RiskGuardConfig`
  (constitution gates: 4 trades/day, 3 concurrent, 0.15%/trade, 3% daily
  loss, 8% drawdown, 0.10 lots/pair, 3.0 lots total) — evaluated exactly as
  live execution would evaluate them.
- The one-position-per-pair control rule from
  `production/execution/shadow/live_executor.py` (line ~430).

Sensitivity passes (S1 session gate from the research backtest engine,
S2 `max_open_trades=1`, S3 entry-bar-excluded) are clearly labelled in output.

## What this never does

- Never imports or calls the MT5 bridge, any adapter, `requests`, or any
  order/position endpoint.
- Never writes to any frozen tree, signal log, state file, ledger, runner,
  dashboard, Telegram path, or configuration.
- Never modifies signal-generation, risk, or execution source.
- Outputs only into this directory and `archive/reports/`.

## Run

```bash
cd /root/that
PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 \
  python3 scripts/nqts_shadow_replay/replay_audit.py
```

Outputs:
- `post9_ledger.jsonl` — machine-readable trade ledger (populations A+B)
- `post9_summary.json` — statistics for primary + sensitivity passes
- stdout — population table, validation evidence, summary
