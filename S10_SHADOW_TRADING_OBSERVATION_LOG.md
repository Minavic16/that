# S10 Shadow Trading Observation Log

## Baseline — 2026-09-08 22:20 UTC

### Repository State
- **HEAD**: `480a9d9` (master)
- **VPS HEAD**: `480a9d9` (synced after pull)
- **Last commit**: `docs(s9): APK login fix report — trailing space from Android keyboard`

### Infrastructure
| Component | Status | Notes |
|-----------|--------|-------|
| nqts-dashboard | **active** | Port 8080, HTTPS via Caddy |
| caddy | **active** | Let's Encrypt cert auto-renewing |
| docker | **active** | Container: mt5 (Up 12+ days) |
| nqts-shadow-live | **active** | Polling 20 pairs, 4h timeframe |

### MT5 Bridge
| Check | Result |
|-------|--------|
| Health | `{"mt5_connected":true,"mt5_initialized":true,"status":"healthy"}` |
| Symbol Info (EURUSD) | Live: bid=1.16231 ask=1.16232 spread=1 |
| Symbol Tick | Live tick with timestamp 1788909260 |
| Fetch Data (H4) | Returns bars with correct OHLC |
| Account | Login 111308298, MetaQuotes-Demo, ~5M balance |

### Strategy Configuration
| Parameter | Value |
|-----------|-------|
| Strategy Version | Variant B S6C-2026-001 |
| Risk per Trade | 0.003 |
| Max Hold Bars | 42 |
| Pairs | 20 (EUR/USD, GBP/USD, USD/JPY, USD/CHF, USD/CAD, AUD/USD, NZD/USD, EUR/GBP, EUR/JPY, EUR/CHF, EUR/CAD, EUR/AUD, EUR/NZD, GBP/JPY, GBP/CHF, GBP/CAD, GBP/AUD, GBP/NZD, CHF/JPY, CAD/JPY) |
| Timeframe | 4H |
| Poll Interval | 60 seconds |

### Shadow Runner State
| Metric | Value |
|--------|-------|
| Run ID | s7-shadow-03602404 |
| Created | 2026-08-30T15:10:39 UTC |
| Updated | 2026-09-08T20:18:32 UTC |
| Bars Processed | 41 |
| Signals Emitted | 0 |
| Orders Submitted | 0 |
| Duplicates Caught | 47 |
| Missed Bars | 20 (expected: gap from Aug 30 → Sep 8) |

### Notification Pipeline
| Component | Status |
|-----------|--------|
| EventBus | **OPERATIONAL** |
| NotificationPolicy | **OPERATIONAL** |
| LogNotificationChannel | **OPERATIONAL** |
| TelegramChannel | Not configured (no bot token) |
| EventDeduplicator | **OPERATIONAL** |

### Dashboard
| Check | Result |
|-------|--------|
| Health API | Returns MT5 bridge health |
| Status API | Shows run_id, bars, signals, pairs |
| Config API | Shows strategy version, risk, max_hold |
| Authentication | `Mindavic`/`admin123` works (trim fix applied) |
| APK | v3.0, HTTPS endpoint, auth working |

### Test Suite
| Run | Passed | Failed | Errors |
|-----|--------|--------|--------|
| Core (30 files) | **789** | **0** | 0 |

### Demo Exit Criteria (Initial)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| System operational | **GREEN** | All services active, shadow runner processing |
| MT5 connected | **GREEN** | Bridge healthy, live tick data flowing |
| Market data fresh | **GREEN** | 16:00 UTC bars received for all 20 pairs |
| Strategy processing live data | **GREEN** | Signal generator evaluated 41 bars |
| No critical exceptions | **GREEN** | No crashes, no unhandled exceptions |
| No duplicate execution | **GREEN** | 47 duplicates correctly detected and skipped |
| Lifecycle events coherent | **GREEN** | Bars processed, state saved, zero orders |
| Protection mechanisms | **GREEN** | Hard guard active, zero orders submitted |
| Dashboard usable | **GREEN** | Auth, status, config endpoints working |
| APK auth stable | **GREEN** | trim fix verified, login working |
| State persisted | **GREEN** | state.json, bars.jsonl, infrastructure.jsonl |
| Infrastructure healthy | **GREEN** | All 4 services active |

### Initial Verdict: **GREEN**

The system is operational against live market data. All 20 pairs are receiving 4H bars from MT5. The signal generator is evaluating conditions. Zero orders are being submitted (correct for shadow mode). Infrastructure is healthy.

### Observation Period 1: 2026-09-08 22:00–22:30 UTC

**Start**: 22:00 UTC
**End**: 22:30 UTC

| Metric | Value |
|--------|-------|
| Engine uptime | 12 minutes (service started 22:18) |
| MT5 status | Connected, healthy |
| Market data | Fresh (16:00 UTC bars for all pairs) |
| Signals generated | 0 |
| Shadow trades | 0 |
| Lifecycle events | 41 bars processed, 47 duplicates detected |
| Errors | 20 "missed bar" events (expected: Aug 30 → Sep 8 gap) |
| Warnings | 21 clock mismatch warnings (old: Aug 30 data) |
| Restarts | 0 |
| Dashboard | Accessible, auth working |
| APK | Auth working (trim fix) |
| Notification pipeline | Operational (Telegram not configured) |

**Notes**: The "missed bar" and "clock mismatch" events are expected consequences of the 9-day gap between the previous shadow run (Aug 30) and today. Once the runner processes the current 16:00 UTC bar and waits for the next 4H bar (20:00 UTC), these gap-related events will cease. The system is functioning correctly.
