# NQTS Architecture Freeze
# Date: 2026-09-15
# Status: FROZEN — no changes without new evidence-based requirement

## Architecture

```
Caddy (HTTPS reverse proxy, port 443)
  └── nqts-dashboard.service (Next.js 16.3.3, port 8080)
        ├── /api/engines   — system status, runner state, data freshness
        ├── /api/health    — full health endpoint (account, equity, P&L)
        ├── /api/signals   — recent signals list
        ├── /api/status    — infrastructure events
        ├── /api/backtest  — backtest management
        ├── /api/execute   — execution controls (SHADOW only)
        └── /              — admin dashboard UI

run_live_shadow.py (standalone process)
  ├── WineFlaskReadOnlyAdapter → MT5 Flask bridge (http://127.0.0.1:5001)
  │     └── MetaTrader 5 (MetaQuotes-Demo, Account 111308298)
  ├── MetricsAggregator → metrics.json
  ├── ShadowRunner → state.json, bars.jsonl, signals.jsonl, infrastructure.jsonl
  └── SignalNotifier → @NQTSbot (Telegram, chat 7170946902)

Data Flow:
  MT5 → Flask bridge → WineFlaskAdapter → LiveShadowRunner
    → bars.jsonl (completed 4H candles)
    → signals.jsonl (strategy decisions)
    → state.json (run state, last_bar per pair, counters)
    → metrics.json (runner health, execution status)
    → infrastructure.jsonl (events, gaps, duplicates)
    → Telegram (signal alerts, health alerts)
    → Dashboard API (reads state.json + metrics.json)
    → Caddy → Browser (https://169.58.230.92)
```

## Frozen Components

| Component | Version | Last Verified |
|---|---|---|
| NQTS Package | 0.2.0 | 2026-09-15 |
| Strategy | Canonical Breakout V1 (NQ-BREAKOUT-V1) | 2026-09-15 |
| Timeframe | 4H | 2026-09-15 |
| Dashboard | Next.js 16.3.3 | 2026-09-15 |
| Python | 3.12.3 (VPS system) | 2026-09-15 |
| Node.js | 20.18.0 | 2026-09-15 |
| MT5 Bridge | Wine+Flask REST (http://127.0.0.1:5001) | 2026-09-15 |
| Git HEAD | 5b4a352 | 2026-09-15 |

## What Is Frozen

1. **Dashboard API routes** — No new endpoints, no removal of existing endpoints
2. **Dashboard data contracts** — API response shapes are stable
3. **Runner telemetry pipeline** — state.json, metrics.json, signals.jsonl, infrastructure.jsonl
4. **Health assessment logic** — GREEN/AMBER/RED criteria
5. **Freshness threshold** — 1.5x candle interval (6h for 4H)
6. **Notification pipeline** — EventBus → Policy → Channels → Telegram
7. **Signal format** — signal_id, timestamp, symbol, direction, entry/sl/tp, ATR, spread
8. **State persistence** — run_id, created_at, updated_at, last_bar, counters

## What Is NOT Frozen

1. **Strategy parameters** — Subject to research evidence (but not silent changes)
2. **New dashboard features** — Can be added without breaking existing functionality
3. **New notification channels** — Can be added alongside Telegram
4. **Additional telemetry** — Can be added to existing endpoints
5. **Bug fixes** — Always allowed
6. **Security patches** — Always allowed

## Change Protocol

Any change to a frozen component requires:
1. A documented evidence-based requirement
2. An experiment ID (e.g., NQTS-2026-XXX)
3. A new git commit with clear message
4. Dashboard rebuild and restart on VPS
5. Runtime verification (12/12 checks)
6. This document updated with new version/date

## Deployment Commands

```bash
# Dashboard rebuild and deploy
ssh root@169.58.230.92
cd /root/nestquant/production/dashboard/dashboard
rm -rf .next && npm run build
systemctl restart nqts-dashboard

# Runner restart
kill $(pgrep -f run_live_shadow)
cd /root/nestquant
PYTHONPATH=/root NESTQUANT_SKIP_LIVE_CHECK=1 NESTQUANT_SKIP_DASHBOARD_CHECK=1 \
  nohup python3 -u production/deployment/run_live_shadow.py \
  --use-wine-flask --api-url http://127.0.0.1:5001 \
  --pairs EUR/USD GBP/USD USD/JPY USD/CHF USD/CAD AUD/USD NZD/USD \
  EUR/GBP EUR/JPY EUR/CHF EUR/CAD EUR/AUD EUR/NZD GBP/JPY GBP/CHF \
  GBP/CAD GBP/AUD GBP/NZD CHF/JPY CAD/JPY \
  --timeframe 4h --poll 60 \
  --log-dir /root/nestquant/logs/shadow_live &

# Verify
curl -s http://localhost:8080/api/engines | python3 -m json.tool
curl -s http://localhost:8080/api/health | python3 -m json.tool
```
