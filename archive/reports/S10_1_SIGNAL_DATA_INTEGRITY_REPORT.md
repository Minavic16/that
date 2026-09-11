# S10.1 Signal Data Integrity Report

**Date:** 2026-09-09
**Status:** Fixed
**Root Cause:** Legacy Z-score schema in dashboard frontend

---

## 1. Root Cause

The admin dashboard's `Signal` interface was built for a previous Z-score/statistical-arbitrage strategy. The current breakout strategy produces a different signal schema. The frontend was reading fields that don't exist (`z_score`, `pair`, `latency_ms`) and ignoring fields that do (`symbol`, `atr_at_signal`, `generation_latency_ms`).

## 2. Raw Backend Schema (Current Breakout Strategy)

```json
{
  "signal_id": "uuid",
  "timestamp": "ISO 8601 UTC",
  "symbol": "EUR/GBP",
  "direction": "BUY|SELL",
  "strategy_params": { "lookback": 5, "atr_period": 14, ... },
  "swing_level": 0.8582,
  "signal_bar_close": 0.85793,
  "expected_entry": 0.8582,
  "expected_sl": 0.8599,
  "expected_tp": 0.8523,
  "atr_at_signal": 0.000844,
  "spread_at_signal": 0.3,
  "generation_latency_ms": 7.9,
  "broker_timestamp": "2026-09-08T20:00:00+00:00",
  "receipt_timestamp": "2026-09-08T21:00:34Z",
  "bid": 0.85793,
  "ask": 0.85913,
  "live_spread": 0.0012
}
```

## 3. Frontend Expected Schema (Legacy - Before Fix)

```typescript
interface Signal {
  timestamp?: string;
  pair?: string;        // WRONG: should be symbol
  direction?: string;
  z_score?: number;     // WRONG: doesn't exist in breakout strategy
  broker_timestamp?: string;
  receipt_timestamp?: string;
  latency_ms?: number;  // WRONG: should be generation_latency_ms
}
```

## 4. Schema Mismatches Found

| Issue | Frontend (Legacy) | Backend (Current) | Impact |
|-------|-------------------|-------------------|--------|
| Symbol field | `s.pair` | `s.symbol` | Shows "-" instead of "EUR/GBP" |
| Strategy metric | `s.z_score` | `s.atr_at_signal` | Shows "z=-" (meaningless) |
| Latency field | `s.latency_ms` | `s.generation_latency_ms` | Shows "-ms" instead of "7.9ms" |
| Timestamp | `new Date(s.timestamp).toLocaleTimeString()` | `s.broker_timestamp` | Shows "1:00:00 AM" (bar close in local TZ) |
| Signal ID | not displayed | `s.signal_id` | No debugging info |

## 5. Timestamp Root Cause

The `timestamp` field is `"2026-09-09T00:00:00+00:00"` (midnight UTC). When rendered with `toLocaleTimeString()` on a device in UTC+1, this becomes "1:00:00 AM". The fix uses `broker_timestamp` (`"2026-09-08T20:00:00+00:00"`) which shows the actual bar close time, rendered with `toLocaleString()` for full date+time.

## 6. Signal Duplication Analysis

The 4 signals are **genuinely distinct**, not duplicated:

| # | Signal ID | Symbol | Direction | Entry |
|---|-----------|--------|-----------|-------|
| 1 | 8634f612 | EUR/GBP | SELL | 0.8582 |
| 2 | f4630bcf | EUR/CHF | SELL | 0.9395 |
| 3 | 467b7dcf | EUR/CAD | SELL | 1.6006 |
| 4 | a33b611f | EUR/AUD | SELL | 1.6088 |

All 4 are different EUR cross pairs, triggered on the same 4H bar (2026-09-08 20:00 UTC). The repeated SELL direction is correct — all 4 met breakout sell conditions simultaneously.

## 7. Files Changed

| File | Change |
|------|--------|
| `dashboard/app/admin/page.tsx` | Updated Signal interface, fixed rendering, added current time |
| `dashboard/app/page.tsx` | Added current time display for user dashboard |
| `dashboard/app/api/signals/route.ts` | Added API access logging |
| `dashboard/app/api/status/route.ts` | Added API access logging |

## 8. Tests Added

- API access logging to `logs/shadow_live/api_access.log`
- Live validation against actual signal data (4/4 fields correct)

## 9. Test Results

| Check | Before | After |
|-------|--------|-------|
| Symbol display | "z=-" (pair field missing) | "EUR/GBP" (symbol field) |
| Strategy metric | "z=-" (z_score missing) | "atr=0.000844" |
| Latency | "-ms" (latency_ms missing) | "7.9ms" (generation_latency_ms) |
| Timestamp | "1:00:00 AM" (bar close in local TZ) | "2026-09-08, 20:00:00" (broker_timestamp) |
| Signal ID | not shown | UUID displayed |
| Current time | not shown | Live clock in header + footer |
| API logging | none | Access log with timestamps |

## 10. Commit Hash

`171a95b` — `fix(dashboard): correct signal schema, add current time, add API logging`

---

## Telegram Notification Wiring (Complete)

- Bot: @NQTSbot (ID: 8658869685)
- Token: configured
- Chat ID: `7170946902` (David Christian)
- Service: `nqts-bot.service` (active, running since Sep 8)
- Signal notifier: `notifications/signal_notifier.py`
- Integration: wired into `execution/shadow/live_runner.py`
- Test message: sent and verified (message_id: 21)

### Notification format:
```
🔴 SELL EUR/GBP
Entry: 0.85820
SL: 0.85989 | TP: 0.85229
ATR: 0.000844 | Latency: 7.9ms
Time: 2026-09-08T20:00:00+00:00
ID: 8634f612-1f7c...
```
