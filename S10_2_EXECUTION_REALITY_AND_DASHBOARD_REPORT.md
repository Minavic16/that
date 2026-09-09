# S10.2 Execution Reality and Dashboard Report

**Date:** 2026-09-09
**Status:** Verified
**Mode:** SHADOW (read-only)

---

## 1. Current Operating Mode

**SHADOW** — The system operates in read-only mode. The shadow runner polls MT5 for live market data but never submits real orders. A hard guard blocks any order submission attempt.

## 2. Signal Count

| Metric | Value |
|--------|-------|
| Signals observed | **7** |
| Intents created | **0** |
| Orders submitted | **0** |
| Orders blocked | **0** |
| Fills | **0** |
| Actual MT5 positions | **0** |

## 3. Reconciliation

| Signal ID | Symbol | Side | Intent | Order | Fill | Position | Status |
|-----------|--------|------|--------|-------|------|----------|--------|
| 8634f612 | EUR/GBP | SELL | No | No | No | No | SIGNAL ONLY |
| f4630bcf | EUR/CHF | SELL | No | No | No | No | SIGNAL ONLY |
| 467b7dcf | EUR/CAD | SELL | No | No | No | No | SIGNAL ONLY |
| a33b611f | EUR/AUD | SELL | No | No | No | No | SIGNAL ONLY |
| (3 more) | Various | SELL | No | No | No | No | SIGNAL ONLY |

**All 7 signals are analytical observations only.** No real orders were submitted.

## 4. MT5 Account Verification

| Field | Value |
|-------|-------|
| Account | 111308298 (MetaQuotes-Demo) |
| Name | Nonso Nonso |
| Currency | GBP |
| Leverage | 100 |
| Balance | £4,999,999.65 |
| Equity | £4,999,999.65 |
| Margin | £0.00 |
| Free Margin | £4,999,999.65 |
| Profit | £0.00 |
| Open Positions | **0** |
| Pending Orders | **0** |

**MT5 confirms: Account is flat. No positions. No orders.**

## 5. Overview Root Cause

**Before:** Health API only proxied MT5 `/health` (3 fields). Frontend expected 11 fields. Field mismatch caused `NaN` for uptime (undefined / 3600 = NaN).

**After:** Health API now merges:
- MT5 health (connected, status)
- Shadow runner state (uptime, bars, signals)
- Infrastructure events (gaps, integrity)
- Zero orders count
- Execution mode
- Kill switch state

## 6. Fixes Made

| File | Change |
|------|--------|
| `dashboard/app/api/health/route.ts` | Enriched with shadow runner state, uptime calculation, execution mode |
| `dashboard/app/admin/page.tsx` | Updated HealthData interface, added execution mode badge, MT5 status, positions |
| `dashboard/app/page.tsx` | Updated user dashboard with execution mode, MT5 status, removed duplicate Zero Orders section |

## 7. Dashboard Display

### Overview Tab (Admin)
```
Status: HEALTHY [SHADOW]
Uptime: 24h 38m
MT5: Connected
Bars Processed: 181
Signals Emitted: 7
Open Positions: 0
Orders Submitted: 0
Orders Blocked: 0
Gaps Detected: 20
Integrity Warnings: 21
Kill Switch: off
```

### Signals Tab
```
7 recent signals

EUR/GBP SELL
entry=0.85820  atr=0.00084  7.9ms
SL=0.85989  TP=0.85229  2026-09-08, 20:00:00

EUR/CHF SELL
entry=0.93946  atr=0.00149  9.3ms
SL=0.94243  TP=0.92906  2026-09-08, 20:00:00

...
```

## 8. Execution State Machine

```
Signal (ShadowSignalRecord)
  → Logged to signals.jsonl
  → Intended order logged to intended_orders.jsonl
  → SHADOW_ONLY — no broker order sent

Live Mode (S8Runtime):
  Signal → IntentFactory → TradeIntent → RiskGuard → RiskDecision
    → ExecutionCoordinator → OrderRequest → MT5ExecutionAdapter → MT5Client
    → HTTP POST to Flask bridge → MT5 order_send()

Current: SHADOW mode only. Live mode requires NESTQUANT_EXPERIMENTAL_LIVE=true.
```

## 9. Key Evidence

| Check | Evidence |
|-------|----------|
| orders_submitted_count.json | `{"orders_submitted": 0, "blocked_attempts": 0}` |
| MT5 /get_positions | `{"positions": []}` |
| MT5 account profit | `0.0` |
| Shadow runner hard guard | Blocks any order submission attempt |
| Signal logs | All marked `SHADOW_ONLY — no broker order sent` |

## 10. Commit Hash

`db6ec4a` — `fix(dashboard): enrich health API, add execution mode, fix Overview NaN`

---

## ANSWER: DID NQTS ACTUALLY OPEN POSITIONS?

**NO.**

The recent signals remain signal/shadow activity only. No broker position was opened. The hard guard in the shadow runner blocks all order submission. MT5 confirms 0 open positions and £0.00 profit on the demo account.

The 7 signals are analytical observations from the breakout strategy evaluating live market data. They represent what the system *would* trade if in live mode. Currently, no live mode is active.
