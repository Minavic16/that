# Project Context
> Single source of truth. Updated as progress is made.

---

## Strategy: MR+TF with Correlation Filter

### Core Logic
- **MR regime**: price near 4H EMA200 (within 0.5%) → session close exit
- **TF regime**: price breaks away from EMA200 (>0.5%) → trailing stop exit
- **Correlation filter**: 0.85 threshold, max 2 per currency, currency overlap filter

### Parameters
| Parameter | Value |
|---|---|
| Timeframe | 30min |
| Pairs | 12 (EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, NZD/USD, EUR/GBP, EUR/CHF, EUR/JPY, AUD/JPY, EUR/AUD, AUD/CAD) |
| EMA | 200 |
| MR threshold | 0.5% from EMA200 |
| TF threshold | >0.5% from EMA200 |
| MR risk | 3.5% |
| MR RR | 2.2 |
| TF risk | 2.2% |
| Breakout zone | 0.5% |
| Trail ATR mult | 2.5 |
| TF time stop | 30 bars (15h) |
| Correlation | 0.85 |
| Max per currency | 2 |
| Session filter | London(7-16), NY(12-20), skip Fri>=20, skip Mon<3 |
| Account | $2,500 |
| Leverage | 1:100 |

### Costs (baked into backtest)
| Cost | Value |
|---|---|
| Spread | Fixed per pair: EUR/USD 0.8, GBP/USD 1.0, USD/JPY 1.0, USD/CHF 1.2, AUD/USD 0.9, NZD/USD 1.2, EUR/GBP 1.2, EUR/CHF 1.5, EUR/JPY 2.0, AUD/JPY 2.0, EUR/AUD 2.0, AUD/CAD 2.0 |
| Entry slippage | 0.3 pips (added to half-spread on entry fill) |
| Commission | $3.50 per lot per trade |
| Total round-trip cost | ~spread + 0.6 pips + $3.50 commission |

### Slippage Stress Test Results
- Even +5 pips extra slippage barely affects performance (EV drops from $435 to $435 — negligible)
- Spread widening matters more: at 2x spreads, EV=$344/trade, 1 losing month
- At 3x spreads, EV=$253/trade, still profitable
- **Worst realistic case** (2x spread + 2 pips slippage): 62% WR, PF=2.6, $12.7K/mo, 1 losing month
- **Conclusion**: Slippage is not the risk. Spread widening during news is. Avoid entries 5min around major news.

### Backtest Results — Compounding (Full Period 2022-2026)
- 2,651 trades (49/mo), 61.2% WR, 2.1 PF, 9.20% MDD
- Final: $1,655,251 from $2,500 (66,110% return)
- Avg P&L: $623/trade, Avg Win: $1,980, Avg Loss: -$1,516
- MR: 2,188 trades, TF: 465 trades, Corr skipped: 52,986

### Backtest Results — Compounding (IS 2022-2024)
- 1,737 trades (49/mo), 66.4% WR, 2.6 PF, 9.20% MDD
- Final: $1,331,292 from $2,500

### Backtest Results — Compounding (OOS 2025-2026)
- 865 trades (48/mo), 70.8% WR, 4.5 PF, 5.81% MDD
- Final: $379,152 from $2,500
- Avg P&L: $435/trade, Avg Win: $792, Avg Loss: -$427
- MR: 764, TF: 103, Corr skipped: 17,396

### Backtest Results — Fixed $2,500 Sizing (THE REAL NUMBERS)
**All position sizes computed on $2,500 balance, not compounding.**

| Period | Trades | WR | PF | MDD | Final | Return | $/month |
|--------|--------|-----|-----|-----|-------|--------|---------|
| IS | 1,738 | 66.3% | 2.9 | 2.8% | $27,574 | 1,003% | $1,407 |
| **OOS** | **864** | **70.7%** | **4.4** | **3.7%** | **$16,256** | **550%** | **$764** |
| Full | 2,652 | 61.2% | 2.3 | 2.8% | $30,843 | 1,134% | $491 |

- OOS: MR=74.2% WR $19/trade, TF=44.7% WR -$4/trade
- All 12 pairs profitable OOS
- Zero losing months in 18 months OOS

### Risk Sensitivity (Fixed Sizing, OOS)
| Risk/Trade | Monthly Return | MDD | Worst Month |
|-----------|---------------|-----|-------------|
| 0.5% | ~24% | 9.8% | +$331 |
| 1.0% | ~47% | 10.5% | +$653 |
| 2.0% | ~95% | 12.1% | +$194 |
| 3.5% | ~165% | 16.6% | +$662 |

### MR-Only at 1% Risk (Conservative)
- 797 trades (44/mo), 73.3% WR, 5.7 PF, MDD 2.48%
- $760/month (30.4%), worst month +$121 (+4.8%)
- Zero losing months

---

## Trade Analysis Insights
- **MR dominates**: 2,186 trades, 63.8% WR, $735 avg P&L (compounding)
- **TF weak**: 465 trades, 49.0% WR, $100 avg P&L — consider removing
- **Early exits (1-10 bars)**: 40.1% WR, -$300 avg P&L — worst holding period
- **Session close exits**: 2,136 trades, 64.4% WR — bread and butter
- **Stop losses**: 57 trades, 0% WR, -$4,172 avg — unavoidable cost
- **Best pairs OOS**: EUR/USD (71.3%), GBP/USD (66.7%), USD/JPY (70.5%), EUR/GBP (72.6%)
- **Worst pairs OOS**: AUD/CAD (55.1%), NZD/USD (53.9%), AUD/JPY (53.8%)
- **Best hours**: 0:00 (73.5%), 23:00 (75.2%), 10:00 (75.0%)
- **Worst hours**: 11:00 (26.7%), 21:00 (12.5%)

---

## File Structure

### Core Strategy
| File | Purpose |
|---|---|
| `test_combined_corr.py` | Main backtest script — compounding + trade logging |
| `position_sizing.py` | Leverage-aware sizing, QuoteSnapshot class |

### Analysis
| File | Purpose |
|---|---|
| `test_proper_oos.py` | Fixed sizing OOS test |
| `test_risk_levels.py` | Risk sensitivity + monthly breakdown |
| `test_slippage_stress.py` | Slippage/spread stress test |
| `test_filtered_oos.py` | OOS filter analysis |
| `analyze_trades.py` | Trade breakdown by pair/exit/hour |

### Engine
| File | Purpose |
|---|---|
| `dry_run_engine.py` | yfinance-based engine, writes to dashboard JSON |
| `live_engine.py` | cTrader-based engine (blocked — sandbox tokens) |
| `run_live_pepperstone.py` | Runner for live engine |

### Dashboard
| File | Purpose |
|---|---|
| `app.py` | Flask backend — `/api/state`, `/api/live`, `/ctradercallback` |
| `templates/index.html` | Frontend — cards, admin panel |

### cTrader Connector
| File | Purpose |
|---|---|
| `ctrader_connector_new.py` | TCP/Protobuf async connector |

### Config
| File | Purpose |
|---|---|
| `.env` | cTrader credentials (sandbox app — broken), METAAPI_TOKEN |

---

## Current State

### Working
- Dry-run engine: running in background (screen session `dryrun`)
- Dashboard: running at http://localhost:5000
- Ngrok tunnel: `https://panama-crowbar-effort.ngrok-free.dev`
- All 12 pairs loading from yfinance
- Engine writes `/root/logs/live_engine_status.json`
- Dashboard `/api/live` reads that file
- **Dashboard shows MR+TF strategy**

### Broken / Blocked
- **cTrader tokens invalid**: App is sandbox-only, all tokens produce `CH_ACCESS_TOKEN_INVALID`
- **Live engine can't run**: No valid tokens

---

## Lessons Learned

1. **Don't model costs after the fact** — bake spread, slippage, commission into the main backtest from the start. If you want to test different assumptions, change the constants in the main script and re-run.
2. **Fixed sizing reveals true edge** — compounding masks the real per-trade EV. Always validate with fixed position sizing.
3. **OOS can outperform IS** — the 70.8% OOS WR vs 66.3% IS WR shows the strategy is robust, not overfitted.
4. **TF is a drag** — 49% WR, -$4/trade OOS. Consider MR-only.
5. **Spread widening > slippage** — the real execution risk is news-driven spread blowouts, not normal slippage.

---

## Dashboard Operations

### Starting Services
```bash
screen -dmS dryrun bash -c "cd /root && python3 dry_run_engine.py > logs/dryrun.log 2>&1"
screen -dmS dashboard bash -c "cd /root && python3 app.py > logs/dashboard.log 2>&1"
screen -dmS ngrok bash -c "ngrok http 5000 --log=stdout > /tmp/ngrok.log 2>&1"
```

### Stopping Services
```bash
screen -S dryrun -X quit
screen -S dashboard -X quit
screen -S ngrok -X quit
```

### Key Files
| File | Purpose | Written by |
|---|---|---|
| `/root/logs/live_engine_status.json` | Dashboard reads this | `dry_run_engine.py` |
| `/root/logs/open_positions.json` | Persisted positions | `dry_run_engine.py` |
| `/root/logs/trade_analysis.csv` | Trade log | `test_combined_corr.py` |

---

## Next Actions
1. **cTrader token resolution**: Either user creates new Demo app on cTrader portal, or explore MetaApi alternative
2. **Consider MR-only**: TF is a drag on OOS performance (-$4/trade). Test removing it.
3. **Dry-run trades**: Engine is running but needs market conditions to align for entries
