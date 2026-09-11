# REPOSITORY MIGRATION PLAN

> **NestQuant Repository Architecture Reorganization**
> **Phase 0 — Forensic Inventory**
> **Date:** 2026-09-11
> **Git HEAD:** `e706995bed85196b8286f2eb1eca02de48433012` (master)
> **Working Tree:** Clean (2 untracked docs)

---

## 1. CURRENT REPOSITORY STRUCTURE

```
NestQuant/                          (268 .py files, ~78,600 lines)
├── __init__.py                     (root package)
├── AGENTS.md                       (constitution — 24 rules)
├── logger.py
├── risk_manager.py
├── pyproject.toml
├── .gitignore
├── .env.example
├── .env.telegram
│
├── analytics/                      (2 files, ~500 lines)
├── archive/legacy/                 (2 files, 222 lines)
├── backtest/                       (3 files, 401 lines)
├── backtests/                      (2 JSON files, 86 lines)
├── config/                         (8 files, ~1,400 lines)
│   └── policies/                   (4 files + 1 JSON)
├── costs/                          (2 files, ~300 lines)
├── dashboard/                      (Next.js, ~40 files)
├── dashboard-mobile/               (Android WebView, 3 files)
├── data/                           (5 files, ~1,500 lines)
├── data_validation/                (2 files, ~300 lines)
├── docs/                           (11 .md files, ~2,368 lines)
├── engines/                        (4 files, ~624 lines)
├── execution/                      (16 files, ~5,500 lines)
│   └── shadow/                     (11 files, ~3,200 lines)
├── indicators/                     (8 files, ~1,196 lines)
├── knowledge/                      (2 files, ~240 lines)
├── logs/shadow_live/
├── monitoring/                     (17 files, ~4,618 lines)
├── notifications/                  (9 files, ~1,288 lines)
├── portfolio/                      (2 files, ~264 lines)
├── regime/                         (11 files, ~2,510 lines)
│   └── tabfm/                      (5 files)
├── research/                       (empty __init__.py only)
├── research_data/                  (research output JSONs + figures)
├── risk/                           (2 files, ~643 lines)
├── scripts/                        (45 files, ~33,226 lines)
├── signals/                        (3 files, ~166 lines)
├── strategy/                       (9 files, ~1,305 lines)
│   ├── lifecycle/                  (3 files)
│   └── trade_management/           (4 files)
├── tests/                          (74 files, ~18,941 lines)
│   ├── unit/                       (6 files)
│   ├── integration/                (1 empty __init__.py)
│   ├── regression/                 (28 files)
│   └── smoke/                      (2 files)
├── utils/                          (3 files, ~350 lines)
├── zscore/                         (6 files, ~1,761 lines)
│
├── [62 root-level .md report files]
├── [14 root-level .py ad-hoc scripts]
└── [various __pycache__/ directories]
```

---

## 2. TARGET ARCHITECTURE

```
NestQuant/
├── production/                     ← Runtime strategy, execution, risk, monitoring
│   ├── strategies/                 ← Canonical strategy implementations
│   ├── risk/                       ← Risk management, circuit breakers
│   ├── execution/                  ← Execution adapters, MT5 bridge, orchestration
│   ├── monitoring/                 ← Observability, metrics, dashboards
│   ├── notifications/              ← Alert pipeline (Telegram, log)
│   ├── api/                        ← Dashboard API (Next.js)
│   └── deployment/                 ← systemd, service files, deployment config
│
├── research/                       ← All research code, experiments, analysis
│   ├── current/                    ← Active research
│   ├── proposed/                   ← Proposed but not started
│   ├── experiments/                ← Completed experiments
│   └── shared/                     ← Shared research utilities
│
├── archive/                        ← Historical, legacy, deprecated code
│   ├── strategies/                 ← Archived strategy implementations
│   ├── research/                   ← Historical research scripts + reports
│   ├── legacy/                     ← Legacy modules (GFT era)
│   ├── config/                     ← Superseded configurations
│   └── deprecated/                 ← Code removed from active use
│
├── platform/                       ← Shared infrastructure, governance, contracts
│   ├── architecture/               ← Architecture documentation
│   ├── governance/                 ← Constitution, lifecycle, promotion policies
│   ├── strategy_registry/          ← Strategy identity, versioning, lineage
│   ├── contracts/                  ← Data contracts, interfaces, protocols
│   ├── configuration/              ← Settings, policies, experiment config
│   ├── deployment/                 ← Deployment documentation, runbooks
│   ├── knowledge/                  ← Market knowledge, lessons learned
│   └── tooling/                    ← Shared utilities, helpers
│
└── tests/                          ← All test code
    ├── production/                 ← Production system tests
    ├── research/                   ← Research code tests
    ├── platform/                   ← Platform/utility tests
    ├── integration/                ← Integration tests
    ├── parity/                     ← Research↔production parity tests
    └── safety/                     ← Safety-critical system tests
```

---

## 3. FILE-BY-FILE CLASSIFICATION

### Legend

| Code | Meaning |
|------|---------|
| **P** | Production — runtime strategy/execution/risk/monitoring |
| **R** | Research — experiments, analysis, backtesting |
| **A** | Archive — historical, legacy, deprecated |
| **F** | Platform — shared infrastructure, contracts, governance |
| **T** | Tests — test code |
| **X** | Exclude from migration (cache, build artifacts) |

---

### 3.1 PRODUCTION FILES (target: `production/`)

#### 3.1.1 Strategy Core (`production/strategies/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 1 | `signals/base.py` | 53 | **P** | Signal contract — frozen dataclass |
| 2 | `signals/breakout.py` | 103 | **P** | Canonical Breakout V1 signal generator |
| 3 | `signals/__init__.py` | 10 | **P** | Package exports |
| 4 | `strategy/lifecycle/contracts.py` | 360 | **P** | Lifecycle rule contracts |
| 5 | `strategy/lifecycle/registry.py` | 363 | **P** | Lifecycle rule registry |
| 6 | `strategy/lifecycle/__init__.py` | 45 | **P** | Package exports |
| 7 | `strategy/trade_management/breakeven.py` | 96 | **P** | Breakeven manager (0.8R) |
| 8 | `strategy/trade_management/max_hold.py` | 105 | **P** | Max hold manager (7 days/42 bars) |
| 9 | `strategy/trade_management/trailing_stop.py` | 99 | **P** | Swing-based trailing stop |
| 10 | `strategy/trade_management/manager.py` | 192 | **P** | Trade lifecycle coordinator |
| 11 | `strategy/trade_management/__init__.py` | 44 | **P** | Package exports |
| 12 | `strategy/__init__.py` | 1 | **P** | Package init |

#### 3.1.2 Risk Management (`production/risk/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 13 | `risk/circuit_breakers.py` | 620 | **P** | 6 circuit breakers + persistence |
| 14 | `risk/__init__.py` | 23 | **P** | Package exports |

#### 3.1.3 Execution Layer (`production/execution/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 15 | `execution/base.py` | 86 | **P** | Abstract execution adapter |
| 16 | `execution/contracts.py` | 326 | **P** | TradeIntent, OrderTicket, FillConfirmation |
| 17 | `execution/adapter.py` | 285 | **P** | LiveExecutionAdapter |
| 18 | `execution/mt5_client.py` | 445 | **P** | MT5 HTTP bridge client |
| 19 | `execution/mt5_adapter.py` | 389 | **P** | MT5 multi-account adapter |
| 20 | `execution/orchestration.py` | 209 | **P** | Order orchestration pipeline |
| 21 | `execution/intent_factory.py` | 161 | **P** | Signal→Intent conversion |
| 22 | `execution/data_feed.py` | 328 | **P** | MT5 streaming data feed |
| 23 | `execution/risk_guard.py` | 327 | **P** | Pre-trade risk validation |
| 24 | `execution/prop_firm_guard.py` | 355 | **P** | Prop firm constraints |
| 25 | `execution/trade_logger.py` | 511 | **P** | Trade audit logging |
| 26 | `execution/health_monitor.py` | 247 | **P** | Infrastructure health checks |
| 27 | `execution/protection.py` | 418 | **P** | Execution protection + retry |
| 28 | `execution/s7_engine.py` | 316 | **P** | S7 execution engine |
| 29 | `execution/s8_runtime.py` | 1320 | **P** | Main live trading runtime |
| 30 | `execution/__init__.py` | 50 | **P** | Package exports |

#### 3.1.4 Shadow Pipeline (`production/execution/shadow/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 31 | `execution/shadow/runner.py` | 405 | **P** | Shadow historical replay |
| 32 | `execution/shadow/signal_generator.py` | 248 | **P** | Causal signal generator (frozen Variant B) |
| 33 | `execution/shadow/state.py` | 93 | **P** | In-memory shadow state |
| 34 | `execution/shadow/kill_switch.py` | 60 | **P** | Emergency kill switch |
| 35 | `execution/shadow/safety.py` | 127 | **P** | Hard safety guard (ZERO orders) |
| 36 | `execution/shadow/health.py` | 164 | **P** | Shadow health monitoring |
| 37 | `execution/shadow/logger.py` | 253 | **P** | Shadow event logging |
| 38 | `execution/shadow/live_runner.py` | 427 | **P** | Live shadow runner |
| 39 | `execution/shadow/live_executor.py` | 522 | **P** | Live execution coordinator |
| 40 | `execution/shadow/live_adapter.py` | — | **P** | Live shadow adapter |
| 41 | `execution/shadow/wine_flask_adapter.py` | 233 | **P** | Wine/Flask MT5 bridge |
| 42 | `execution/shadow/__init__.py` | 40 | **P** | Package exports |

#### 3.1.5 Monitoring (`production/monitoring/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 43 | `monitoring/models.py` | 190 | **P** | Core data models |
| 44 | `monitoring/architecture.py` | 197 | **P** | 4-layer monitoring architecture |
| 45 | `monitoring/canonical_identity.py` | 284 | **P** | Strategy identity (SINGLE source of truth) |
| 46 | `monitoring/data_schema.py` | 275 | **P** | Calibration data schemas |
| 47 | `monitoring/percentiles.py` | 244 | **P** | Statistical percentile framework |
| 48 | `monitoring/ev_stability.py` | 324 | **P** | EV stability analysis |
| 49 | `monitoring/dd_clustering.py` | 474 | **P** | Drawdown clustering |
| 50 | `monitoring/slippage.py` | 203 | **P** | Slippage tracking |
| 51 | `monitoring/spread_collector.py` | 213 | **P** | Spread sampling |
| 52 | `monitoring/latency_probe.py` | 131 | **P** | Latency measurement |
| 53 | `monitoring/health_collector.py` | 141 | **P** | Health data collection |
| 54 | `monitoring/equity_tracker.py` | 194 | **P** | Equity curve tracking |
| 55 | `monitoring/decision.py` | 234 | **P** | Decision engine (Layer 4) |
| 56 | `monitoring/metrics_aggregator.py` | 303 | **P** | Dashboard metrics bridge |
| 57 | `monitoring/server.py` | 371 | **P** | HTTP monitoring server |
| 58 | `monitoring/__init__.py` | 64 | **P** | Package exports |

#### 3.1.6 Notifications (`production/notifications/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 59 | `notifications/events.py` | 160 | **P** | NQTSEvent canonical model |
| 60 | `notifications/bus.py` | 147 | **P** | Event dispatcher |
| 61 | `notifications/policy.py` | 127 | **P** | Routing policy |
| 62 | `notifications/channels.py` | 239 | **P** | Telegram + Log channels |
| 63 | `notifications/dedup.py` | 106 | **P** | Deduplication |
| 64 | `notifications/wiring.py` | 129 | **P** | Pipeline factory |
| 65 | `notifications/telegram_bot.py` | 163 | **P** | Telegram command bot |
| 66 | `notifications/__init__.py` | 47 | **P** | Package exports |

#### 3.1.7 Dashboard (`production/api/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 67 | `dashboard/app/` | ~5,000 | **P** | Next.js pages + API routes |
| 68 | `dashboard/lib/` | ~270 | **P** | Auth, DB, RBAC |
| 69 | `dashboard/middleware.ts` | 23 | **P** | Session middleware |
| 70 | `dashboard/types/` | 34 | **P** | Type declarations |
| 71 | `dashboard/scripts/seed.ts` | 105 | **F** | DB seed script |
| 72 | `dashboard/package.json` | 29 | **F** | NPM manifest |
| 73 | `dashboard/tsconfig.json` | 34 | **F** | TypeScript config |
| 74 | `dashboard/next.config.ts` | 7 | **F** | Next.js config |
| 75 | `dashboard/postcss.config.mjs` | 7 | **F** | PostCSS config |
| 76 | `dashboard/eslint.config.mjs` | 18 | **F** | ESLint config |
| 77 | `dashboard/app/globals.css` | 26 | **P** | Global styles |
| 78 | `dashboard/app/favicon.ico` | — | **P** | Favicon |
| 79 | `dashboard/public/nqts.apk` | — | **P** | Mobile APK |
| 80 | `dashboard-mobile/app/` | 122 | **P** | Android WebView |

#### 3.1.8 Portfolio (`production/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 81 | `portfolio/position_sizer.py` | 241 | **P** | Risk-based position sizing |
| 82 | `portfolio/__init__.py` | 23 | **P** | Package exports |

---

### 3.2 RESEARCH FILES (target: `research/`)

#### 3.2.1 Z-Score Engine (`research/shared/zscore/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 83 | `zscore/contracts.py` | 80 | **R** | Research data contracts |
| 84 | `zscore/zscore.py` | 423 | **R** | Causal Z-score computation |
| 85 | `zscore/regime.py` | 359 | **R** | Regime classification |
| 86 | `zscore/features.py` | 418 | **R** | Feature engineering |
| 87 | `zscore/config.py` | 480 | **R** | Research configuration |
| 88 | `zscore/__init__.py` | 1 | **R** | Package init |

#### 3.2.2 Research Analytics (`research/shared/analytics/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 89 | `analytics/research_analysis.py` | ~500 | **R** | S0-S6 trade analysis |
| 90 | `analytics/__init__.py` | 2 | **R** | Package init |

#### 3.2.3 Regime Classification (`research/shared/regime/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 91 | `regime/base.py` | 51 | **R** | Base classifier ABC |
| 92 | `regime/labels.py` | 87 | **R** | Regime label definitions |
| 93 | `regime/adx_regime.py` | 218 | **R** | ADX-based classifier |
| 94 | `regime/hybrid.py` | 352 | **R** | Hybrid regime classifier |
| 95 | `regime/tabfm/` (5 files) | ~1,779 | **R** | TabFM ML classifier |
| 96 | `regime/__init__.py` | 23 | **R** | Package init |

#### 3.2.4 Backtest Engines (`research/shared/engines/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 97 | `engines/base_engine.py` | 73 | **R** | Abstract backtest engine |
| 98 | `engines/backtest_engine.py` | 279 | **R** | Single-pair backtest |
| 99 | `engines/regime_backtest_engine.py` | 266 | **R** | Regime-aware backtest |
| 100 | `engines/__init__.py` | 6 | **R** | Package init |

#### 3.2.5 Backtest Utilities (`research/shared/backtest/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 101 | `backtest/metrics.py` | 122 | **R** | BacktestMetrics |
| 102 | `backtest/comparison.py` | 274 | **R** | A/B comparison framework |
| 103 | `backtest/__init__.py` | 5 | **R** | Package init |

#### 3.2.6 Data Acquisition (`research/shared/data/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 104 | `data/news.py` | ~250 | **R** | ForexFactory news collector |
| 105 | `data/loader.py` | ~500 | **R/F** | Multi-timeframe data loader |
| 106 | `data/acquisition.py` | ~400 | **R/F** | Data acquisition with provenance |
| 107 | `data/validation.py` | ~350 | **R/F** | OHLCV validation |
| 108 | `data/__init__.py` | 1 | **R/F** | Package init |

#### 3.2.7 Cost Model (`research/shared/costs/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 109 | `costs/model.py` | ~300 | **R** | CostModel: spread+commission+slippage |
| 110 | `costs/__init__.py` | 0 | **R** | Package init |

#### 3.2.8 Data Validation (`research/shared/data_validation/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 111 | `data_validation/validate.py` | ~300 | **R** | MarketData validation |
| 112 | `data_validation/__init__.py` | 0 | **R** | Package init |

#### 3.2.9 Indicators (`research/shared/indicators/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 113 | `indicators/atr.py` | 24 | **R** | ATR calculation |
| 114 | `indicators/adx.py` | 55 | **R** | ADX calculation |
| 115 | `indicators/ema.py` | 12 | **R** | EMA helper |
| 116 | `indicators/pip.py` | 22 | **R** | Pip size helper |
| 117 | `indicators/swing.py` | 133 | **R** | Swing high/low detection |
| 118 | `indicators/resampler.py` | 156 | **R** | Multi-timeframe resampling |
| 119 | `indicators/session.py` | 789 | **R** | Forex session detection |
| 120 | `indicators/__init__.py` | 5 | **R** | Package init |

#### 3.2.10 Root-Level Research Scripts

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 121 | `currency_strength.py` | 295 | **R** | Currency strength calculator |
| 122 | `debug_breakout.py` | 127 | **R** | Breakout debugging |
| 123 | `zero_costs_test.py` | 76 | **R** | Zero-cost backtest |
| 124 | `oos_validation.py` | 281 | **R** | Out-of-sample validation |
| 125 | `forensic_analysis.py` | 595 | **R** | Forensic analysis |
| 126 | `phase2_forensic_analysis.py` | 484 | **R** | Phase 2 forensic |
| 127 | `phase3_forensic_analysis.py` | 721 | **R** | Phase 3 forensic |
| 128 | `phase4_forensic_analysis.py` | 1066 | **R** | Phase 4 forensic |
| 129 | `phase5_forensic_analysis.py` | 1053 | **R** | Phase 5 forensic |

#### 3.2.11 Scripts — Research (23 files)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 130 | `scripts/signal_discovery.py` | 938 | **R** | Phase 6 signal discovery |
| 131 | `scripts/cost_sensitivity.py` | 121 | **R** | Cost sensitivity analysis |
| 132 | `scripts/run_regime_analysis.py` | 307 | **R** | Regime analysis |
| 133 | `scripts/cross_timeframe_agreement.py` | 574 | **R** | Cross-timeframe agreement |
| 134 | `scripts/temporal_stability_analysis.py` | 538 | **R** | Temporal stability |
| 135 | `scripts/build_stability_reports.py` | 727 | **R** | Report generation |
| 136 | `scripts/ev_risk_analysis.py` | 1198 | **R** | EV & risk analysis |
| 137 | `scripts/build_ev_risk_report.py` | 547 | **R** | EV/Risk report |
| 138 | `scripts/elapsed_time_analysis.py` | 654 | **R** | Elapsed time analysis |
| 139 | `scripts/zscore_mr_backtest.py` | 1313 | **R** | Z-score MR backtest |
| 140 | `scripts/phase7_oos_validation.py` | 1270 | **R** | Phase 7 OOS validation |
| 141 | `scripts/phase8_fast_slow_discovery.py` | 1274 | **R** | Phase 8 fast/slow discovery |
| 142 | `scripts/phase9_probability_gated_mr.py` | 1063 | **R** | Phase 9 probability-gated MR |
| 143 | `scripts/phase9b_corrected_validation.py` | 1061 | **R** | Phase 9B corrected validation |
| 144 | `scripts/phase10_currency_strength_validation.py` | 708 | **R** | Phase 10 currency strength |
| 145 | `scripts/phase10_edge_decomposition.py` | 1180 | **R** | Phase 10 edge decomposition |
| 146 | `scripts/phase11_conditional_structure.py` | 970 | **R** | Phase 11 conditional structure |
| 147 | `scripts/phase11_filter_ablation.py` | 678 | **R** | Phase 11 filter ablation |
| 148 | `scripts/phase12_regime_validation.py` | 685 | **R** | Phase 12 regime validation |
| 149 | `scripts/phase_hg1_holy_grail.py` | 1566 | **R** | Phase HG-1 Holy Grail |
| 150 | `scripts/phase_m1_carry.py` | 580 | **R** | Phase M1 carry |
| 151 | `scripts/phase_m1_structural_discovery.py` | 868 | **R** | Phase M1 structural |
| 152 | `scripts/exit_forensics.py` | 773 | **R** | Phase 5 exit forensics |
| 153 | `scripts/exit_surface.py` | 1451 | **R** | Phase 5 exit surface |

#### 3.2.12 Scripts — Research Archive (8 files)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 154 | `scripts/phase_s0_breakout_reassessment.py` | 1090 | **A→R** | Phase S0 (archive, historical) |
| 155 | `scripts/phase_s1_structural_interrogation.py` | 1244 | **A→R** | Phase S1 (archive, historical) |
| 156 | `scripts/phase_s2_mechanism_identification.py` | 1293 | **A→R** | Phase S2 (archive, historical) |
| 157 | `scripts/phase_s3_independent_validation.py` | 1069 | **A→R** | Phase S3 (archive, historical) |
| 158 | `scripts/phase_s4_walk_forward_sensitivity.py` | 1138 | **A→R** | Phase S4 (archive, historical) |
| 159 | `scripts/phase_s5_5_failure_analysis.py` | 761 | **A→R** | Phase S5.5 (archive, historical) |
| 160 | `scripts/phase_s6_adaptive_risk.py` | 1203 | **A→R** | Phase S6 (archive, historical) |
| 161 | `scripts/phase_s6_causal_swing_check.py` | 328 | **A→R** | Phase S6C (archive, historical) |

#### 3.2.13 Research Data (`research/data/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 162 | `research_data/` (all subdirs) | — | **R** | Research output JSONs + figures |

---

### 3.3 ARCHIVE FILES (target: `archive/`)

#### 3.3.1 Legacy Code (`archive/legacy/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 163 | `archive/legacy/config.py` | 109 | **A** | GFT Dynamic Risk Config |
| 164 | `archive/legacy/structured_entry.py` | 113 | **A** | EMA200 pullback signal |

#### 3.3.2 Archived Strategies (`archive/strategies/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 165 | `risk_manager.py` | 84 | **A** | Legacy sizing-only manager (no circuit breakers, can_trade=True always) |
| 166 | `notifications/signal_notifier.py` | 170 | **A** | Legacy Telegram notifier (pre-event-bus) |

#### 3.3.3 Archived Backtests (`archive/research/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 167 | `backtest_gft_crisis.py` | 308 | **A** | GFT crisis-era backtest |
| 168 | `backtest_hybrid_opt.py` | 1026 | **A** | Hybrid optimization backtest |
| 169 | `backtest_portfolio.py` | 1095 | **A** | Portfolio backtest |
| 170 | `backtests/restore_original_results.json` | 70 | **A** | Historical backtest results |
| 171 | `backtests/crisis_years_results.json` | 16 | **A** | Crisis year stress test |

#### 3.3.4 Historical Reports (`archive/research/reports/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 172 | `PHASE_1_REPORT.md` | 160 | **A** | Phase 1 completion report |
| 173 | `PHASE_2_DATA_REPORT.md` | 289 | **A** | Phase 2 data report |
| 174 | `PHASE_2_RECOVERY_REPORT.md` | 177 | **A** | Phase 2 recovery report |
| 175 | `PHASE_2_REPORT.md` | 368 | **A** | Phase 2 report |
| 176 | `PHASE_3_AUDIT_REPORT.md` | 194 | **A** | Phase 3 audit |
| 177 | `PHASE_3_FINAL_CONSISTENCY_AUDIT.md` | 285 | **A** | Phase 3 consistency audit |
| 178 | `PHASE_3_REGIME_ANALYSIS.md` | 218 | **A** | Phase 3 regime analysis |
| 179 | `PHASE_3_REPORT.md` | 379 | **A** | Phase 3 report |
| 180 | `PHASE_3_ZSCORE_RESEARCH_REPORT.md` | 221 | **A** | Phase 3 Z-score research |
| 181 | `MR_DATA_REQUIREMENTS.md` | 167 | **A** | MR data requirements |
| 182 | `MR_DATA_ACQUISITION_PLAN.md` | 271 | **A** | MR data acquisition plan |
| 183 | `MR_BASELINE_FORENSIC_REPORT.md` | 570 | **A** | MR baseline forensic |
| 184 | `MR_PHASE2_FORENSIC_REPORT.md` | 509 | **A** | MR Phase 2 forensic |
| 185 | `MR_PHASE3_FORENSIC_REPORT.md` | 411 | **A** | MR Phase 3 forensic |
| 186 | `MR_PHASE4_FORENSIC_REPORT.md` | 420 | **A** | MR Phase 4 forensic |
| 187 | `MR_PHASE5_EXECUTIVE_SUMMARY.md` | 143 | **A** | MR Phase 5 summary |
| 188 | `S7_GATE_REPORT.md` | 154 | **A** | S7 gate report |
| 189 | `S7_LIVE_SHADOW_REPORT.md` | 215 | **A** | S7 live shadow report |
| 190 | `S7_WINE_MT5_GATE_REPORT.md` | 201 | **A** | S7 Wine MT5 gate |
| 191 | `S8_5_PREFLIGHT_REPORT.md` | 331 | **A** | S8.5 preflight |
| 192 | `S8_5_REMEDIATION_REPORT.md` | 249 | **A** | S8.5 remediation |
| 193 | `S8_6_MONITORING_REPORT.md` | 460 | **A** | S8.6 monitoring |
| 194 | `S8_6_REVIEW_ADDENDUM.md` | 485 | **A** | S8.6 review addendum |
| 195 | `S8_6_1_MONITORING_RECALIBRATION_REPORT.md` | 581 | **A** | S8.6.1 recalibration |
| 196 | `S8_6_2_MONITORING_ARCHITECTURE_REPORT.md` | 392 | **A** | S8.6.2 architecture |
| 197 | `S8_6_3_STRATEGY_LINEAGE_REPORT.md` | 436 | **A** | S8.6.3 lineage |
| 198 | `S8_6_4_STRATEGY_FORENSIC_SPEC.md` | 156 | **A** | S8.6.4 forensic spec |
| 199 | `S8_6_4_STRATEGY_RECONCILIATION_REPORT.md` | 244 | **A** | S8.6.4 reconciliation |
| 200 | `S8_6_5_LIFECYCLE_INTEGRATION_REPORT.md` | 238 | **A** | S8.6.5 lifecycle |
| 201 | `S8_6_6_RUNTIME_PARITY_AUDIT.md` | 285 | **A** | S8.6.6 parity audit |
| 202 | `S8_6_6A_ENTRY_SEMANTICS.md` | 90 | **A** | S8.6.6A entry semantics |
| 203 | `S8_6_7_RUNTIME_LIFECYCLE_INTEGRATION_REPORT.md` | 184 | **A** | S8.6.7 lifecycle |
| 204 | `S8_6_7A_ENTRY_RISK_GEOMETRY_AUDIT.md` | 217 | **A** | S8.6.7A risk geometry |
| 205 | `S8_6_7B_FILL_AWARE_GEOMETRY_REPORT.md` | 193 | **A** | S8.6.7B fill-aware |
| 206 | `S8_6_10_EXECUTION_FAILURE_AUDIT.md` | 275 | **A** | S8.6.10 failure audit |
| 207 | `S8_6_11_STARTUP_RECONCILIATION_REPORT.md` | 210 | **A** | S8.6.11 startup |
| 208 | `S8_6_12_EXECUTION_PROTECTION_REPORT.md` | 245 | **A** | S8.6.12 protection |
| 209 | `S8_PARITY_CERTIFICATION.md` | 177 | **A** | S8.6 certification |
| 210 | `S9_1_NQTS_REPOSITORY_AND_DOCUMENTATION_AUDIT.md` | 321 | **A** | S9.1 audit |
| 211 | `S9_2_DEMO_READINESS_REPORT.md` | 190 | **A** | S9.2 readiness |
| 212 | `S9_3_CONTROLLED_DEMO_VALIDATION.md` | 160 | **A** | S9.3 validation |
| 213 | `S9_4_ACTUAL_APK_LOGIN_FIX.md` | 82 | **A** | S9.4 APK fix |
| 214 | `S10_1_SIGNAL_DATA_INTEGRITY_REPORT.md` | 129 | **A** | S10.1 signal integrity |
| 215 | `S10_2_EXECUTION_REALITY_AND_DASHBOARD_REPORT.md` | 144 | **A** | S10.2 execution reality |
| 216 | `S10_3_DASHBOARD_DATA_AND_CORRELATION_AUDIT.md` | 447 | **A** | S10.3 dashboard audit |
| 217 | `S10_4_CONTROLLED_MT5_DEMO_EXECUTION_REPORT.md` | 352 | **A** | S10.4 demo execution |
| 218 | `AUDIT_REPORT.md` | 161 | **A** | Initial codebase audit |
| 219 | `TECHNICAL_REPORT.md` | 551 | **A** | Early technical report |
| 220 | `POST_REMEDIATION_VERIFICATION.md` | 156 | **A** | Post-remediation verification |
| 221 | `MONITORING_DATA_INVENTORY.md` | 409 | **A** | Monitoring data inventory |
| 222 | `RISK_DASHBOARD_BACKTEST_FORENSIC_AUDIT.md` | 717 | **A** | Risk/dashboard forensic |
| 223 | `RISK_DASHBOARD_SIGNAL_REMEDIATION_REPORT.md` | 321 | **A** | Risk/dashboard remediation |
| 224 | `STRATEGY_IDENTITY_REMEDIATION.md` | 573 | **A** | Strategy identity proposal |
| 225 | `STRATEGY_IDENTITY_REMEDIATION_EXECUTION.md` | 227 | **A** | Strategy identity execution |
| 226 | `TIMEFRAME_MIGRATION_PLAN.md` | 430 | **A** | Timeframe migration proposal |
| 227 | `NESTQUANT_TECHNICAL_SYSTEM_REPORT_PRE_LIVE.md` | 1150 | **A** | Pre-live system report |
| 228 | `CHANGELOG.md` | 24 | **A** | Initial setup log |
| 229 | `PROJECT_STATE.md` | 73 | **A** | Outdated project state |
| 230 | `TODO.md` | 58 | **A** | Outdated task list |

---

### 3.4 PLATFORM FILES (target: `platform/`)

#### 3.4.1 Configuration (`platform/configuration/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 231 | `config/settings.py` | 526 | **F** | NestQuantConfig (frozen dataclasses) |
| 232 | `config/constitution.py` | 45 | **F** | Constitution risk params (FROZEN) |
| 233 | `config/experiment.py` | 190 | **F** | Experiment identity + hashing |
| 234 | `config/policies/models.py` | 97 | **F** | LiveParameterPolicy (frozen) |
| 235 | `config/policies/validator.py` | 160 | **F** | Policy validation |
| 236 | `config/policies/loader.py` | 200 | **F** | Policy serialization |
| 237 | `config/policies/s7_shadow.json` | 42 | **F** | S7 shadow policy |
| 238 | `config/policies/__init__.py` | 56 | **F** | Package exports |
| 239 | `config/__init__.py` | 12 | **F** | Package exports |

#### 3.4.2 Contracts (`platform/contracts/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 240 | `execution/contracts.py` | 326 | **F→P** | Canonical data contracts (also used by production) |

#### 3.4.3 Knowledge (`platform/knowledge/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 241 | `knowledge/instruments.py` | ~240 | **F** | Instrument metadata (28 FX pairs) |
| 242 | `knowledge/__init__.py` | 1 | **F** | Package init |

#### 3.4.4 Utilities (`platform/tooling/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 243 | `utils/normalize.py` | ~200 | **F** | Pair normalization |
| 244 | `utils/io.py` | ~150 | **F** | File I/O, JSONL writing |
| 245 | `utils/__init__.py` | 1 | **F** | Package init |

#### 3.4.5 Root Platform Files

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 246 | `__init__.py` | 10 | **F** | Root package |
| 247 | `logger.py` | 27 | **F** | Logging setup |
| 248 | `pyproject.toml` | — | **F** | Project configuration |
| 249 | `.gitignore` | — | **F** | Git ignore rules |
| 250 | `.env.example` | — | **F** | Environment template |
| 251 | `.env.telegram` | — | **F** | Telegram config |

---

### 3.5 TEST FILES (target: `tests/`)

#### 3.5.1 Safety-Critical Tests (`tests/safety/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 252 | `tests/test_constitution_wiring.py` | 131 | **T** | Constitution → RiskGuard wiring |
| 253 | `tests/test_circuit_breakers.py` | 261 | **T** | All 6 circuit breakers |
| 254 | `tests/test_risk_guard.py` | 478 | **T** | RiskGuard gates |
| 255 | `tests/test_s8_prop_firm_guard.py` | 237 | **T** | PropFirmGuard |
| 256 | `tests/test_execution_contracts.py` | 698 | **T** | Execution contracts |
| 257 | `tests/test_execution_protection.py` | 581 | **T** | Execution protection |
| 258 | `tests/test_shadow.py` | 393 | **T** | Shadow pipeline |
| 259 | `tests/test_live_shadow.py` | 310 | **T** | Live shadow safety |
| 260 | `tests/test_startup_reconciliation.py` | 455 | **T** | Startup reconciliation |

#### 3.5.2 Production Tests (`tests/production/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 261 | `tests/test_mt5_adapter.py` | 535 | **T** | MT5 adapter |
| 262 | `tests/test_mt5_client.py` | 461 | **T** | MT5 client |
| 263 | `tests/test_health_monitor.py` | 283 | **T** | Health monitor |
| 264 | `tests/test_monitoring.py` | 742 | **T** | Monitoring system |
| 265 | `tests/test_orchestration.py` | 786 | **T** | Execution orchestration |
| 266 | `tests/test_trade_logger.py` | 554 | **T** | Trade audit logging |
| 267 | `tests/test_signals.py` | ~100 | **T** | Signal generation |
| 268 | `tests/test_position_sizer.py` | ~100 | **T** | Position sizing |
| 269 | `tests/test_policies.py` | ~100 | **T** | Policy tests |
| 270 | `tests/test_lifecycle_integration.py` | 512 | **T** | Lifecycle integration |
| 271 | `tests/test_fill_aware_geometry.py` | 297 | **T** | Fill-aware geometry |

#### 3.5.3 Parity Tests (`tests/parity/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 272 | `tests/test_trade_management_parity.py` | 385 | **T** | Research↔production parity |

#### 3.5.4 Unit Tests (`tests/research/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 273 | `tests/unit/test_zscore.py` | 100 | **T** | Z-score causality |
| 274 | `tests/unit/test_signals.py` | 107 | **T** | Signal contracts |
| 275 | `tests/unit/test_regime.py` | 125 | **T** | Regime causality |
| 276 | `tests/unit/test_features.py` | 124 | **T** | Feature causality |
| 277 | `tests/unit/test_data.py` | 168 | **T** | Data validation |

#### 3.5.5 Smoke Tests (`tests/integration/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 278 | `tests/smoke/test_end_to_end.py` | 335 | **T** | End-to-end pipeline |

#### 3.5.6 Regression Tests (`tests/platform/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 279-306 | `tests/regression/test_phase_*.py` | ~5,228 | **T** | 28 regression test files |

---

### 3.6 PLATFORM/GOVERNANCE FILES (target: `platform/governance/` and `platform/architecture/`)

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 307 | `AGENTS.md` | 306 | **F** | Engineering constitution |
| 308 | `docs/ARCHITECTURE.md` | 239 | **F** | Z-Score pipeline architecture |
| 309 | `docs/CAUSALITY_TEST_DESIGN.md` | 182 | **F** | Causality test methodology |
| 310 | `docs/COST_MODEL_DESIGN.md` | 146 | **F** | Cost model design |
| 311 | `docs/DATA_CONTRACTS.md` | 237 | **F** | Data contracts |
| 312 | `docs/DATA_SOURCE_COMPARISON.md` | 352 | **F** | Data source evaluation |
| 313 | `docs/EXPERIMENT_REPRODUCIBILITY.md` | 174 | **F** | Experiment reproducibility |
| 314 | `docs/NEWS_DATA_RESEARCH.md` | 119 | **F** | News data research design |
| 315 | `docs/REGIME_RESEARCH_DESIGN.md` | 123 | **F** | Regime research design |
| 316 | `docs/S7_PROTOCOL.md` | 499 | **F** | S7 live execution protocol |
| 317 | `docs/SMOKE_TEST_SPEC.md` | 154 | **F** | Smoke test specification |
| 318 | `docs/TEST_STRUCTURE.md` | 171 | **F** | Test structure specification |
| 319 | `CODEBASE_MANIFEST.md` | 773 | **F** | Codebase manifest |
| 320 | `DEMO_V1_LAUNCH_REPORT.md` | 250 | **F** | Current system status |
| 321 | `S10_SHADOW_TRADING_OBSERVATION_LOG.md` | 211 | **F** | Active observation log |

---

### 3.7 SCRIPTS — OPERATIONAL/PLATFORM

| # | Current Path | Lines | Classification | Notes |
|---|---|---|---|---|
| 322 | `scripts/run_shadow.py` | 232 | **P** | Shadow runner entry point |
| 323 | `scripts/run_live_shadow.py` | 308 | **P** | Live shadow entry point |
| 324 | `scripts/run_live_executor.py` | 66 | **P** | Live executor entry point |
| 325 | `scripts/s8_runner.py` | 77 | **P** | S8 runtime entry point |
| 326 | `scripts/check_shadow_health.py` | 357 | **F** | Shadow health CLI |
| 327 | `scripts/s7_dry_run_standalone.py` | 158 | **F** | Standalone dry-run |
| 328 | `scripts/s7_dry_run.py` | 187 | **F** | Dry-run validation |
| 329 | `scripts/s7_health_check.py` | 209 | **F** | MT5 bridge health check |
| 330 | `scripts/validate_shadow_fidelity.py` | 326 | **F** | Shadow fidelity validation |
| 331 | `scripts/download_fx_data.py` | 211 | **F** | Data acquisition |
| 332 | `scripts/extract_financial_numbers.py` | 203 | **F** | Financial extraction |
| 333 | `scripts/compare_timeframes.py` | 324 | **F** | Timeframe comparison |
| 334 | `scripts/nestquant-shadow.service` | 33 | **F** | systemd service file |

---

## 4. PRODUCTION REACHABILITY ANALYSIS

### 4.1 Canonical V1 Strategy Files

These files implement the validated Breakout V1 strategy:

| File | What It Contains |
|------|-----------------|
| `signals/breakout.py` | Signal generation: LOOKBACK=5, ATR_PERIOD=14, ATR_SL_MULT=2.0, RRR=3.5 |
| `execution/shadow/signal_generator.py` | Frozen Variant B: STRATEGY_PARAMS dict (identical values) |
| `strategy/trade_management/breakeven.py` | Breakeven at 0.8R |
| `strategy/trade_management/max_hold.py` | Max hold 7 days / 42 bars |
| `strategy/trade_management/trailing_stop.py` | Swing-based trailing |
| `strategy/lifecycle/registry.py` | Lifecycle rule orchestration |
| `config/constitution.py` | Risk: 0.15%, 3 positions, 0.10 lots, 3.0 total, 3% daily, 8% DD, 4 trades/day |
| `monitoring/canonical_identity.py` | SINGLE source of truth for deployed params |

### 4.2 Runtime Entry Points

| Entry Point | File | Purpose |
|-------------|------|---------|
| S8 Live Runtime | `scripts/s8_runner.py` → `execution/s8_runtime.py` | Main trading runtime |
| Shadow Runner | `scripts/run_shadow.py` → `execution/shadow/runner.py` | Historical shadow |
| Live Shadow | `scripts/run_live_shadow.py` → `execution/shadow/live_runner.py` | Live shadow |
| Live Executor | `scripts/run_live_executor.py` → `execution/shadow/live_executor.py` | Signal→order |

### 4.3 Safety-Critical Import Chain

```
execution/s8_runtime.py
├── execution/prop_firm_guard.py → config/constitution.py (FROZEN)
├── execution/risk_guard.py → risk/circuit_breakers.py
├── execution/shadow/safety.py → install_hard_guard() [ZERO ORDERS]
├── execution/shadow/kill_switch.py → file-based sentinel
├── execution/protection.py → retry + state integrity
├── execution/mt5_adapter.py → MT5 bridge (HTTP, no MT5 SDK)
└── monitoring/canonical_identity.py → strategy params (FROZEN)
```

### 4.4 Forbidden Import Boundaries

| Must NOT Import | Verified By |
|----------------|-------------|
| Production → Research | `test_execution_contracts.py`, `test_mt5_adapter.py` |
| Production → Archive | Architecture rule |
| MT5 SDK in Python | `test_mt5_client.py`, `test_mt5_adapter.py` |
| Research → Production runtime | Architecture rule |

---

## 5. DEPENDENCY RISKS

### 5.1 High Risk

| Risk | Details | Mitigation |
|------|---------|------------|
| `execution/contracts.py` dual-use | Used by both production and research | Move to `platform/contracts/`, both import from there |
| `config/` dual-use | Settings used everywhere | Move to `platform/configuration/`, both import from there |
| `knowledge/instruments.py` | Used by production (intent_factory) and research (scripts) | Move to `platform/knowledge/`, both import from there |
| `utils/` | Used by production and research | Move to `platform/tooling/`, both import from there |

### 5.2 Medium Risk

| Risk | Details | Mitigation |
|------|---------|------------|
| `indicators/` | Used by research scripts AND production (intent_factory uses atr, swing) | Move to `research/shared/indicators/`, production imports via `platform/contracts` interface |
| `data/` modules | loader.py used by research, validation.py used by tests | Move to `research/shared/data/` |
| Root `__init__.py` | May be imported as `nestquant` package | Keep at root, ensure re-exports work |

### 5.3 Low Risk

| Risk | Details | Mitigation |
|------|---------|------------|
| `monitoring/circuit_breaker_analysis.py` | Research analytics in production dir | Move to `research/experiments/` |
| `notifications/signal_notifier.py` | Legacy, still importable | Move to `archive/strategies/` |
| `risk_manager.py` | Legacy, still importable | Move to `archive/strategies/` |

---

## 6. MIGRATION ORDER

### Phase 1: Platform Foundation (no code changes, only documentation)

1. Create `platform/governance/` with constitution, lifecycle, policies
2. Create `platform/architecture/` with architecture docs
3. Create `platform/contracts/` with data contracts
4. Create `platform/configuration/` with settings
5. Create `platform/knowledge/` with instrument metadata
6. Create `platform/tooling/` with utilities
7. Create `platform/strategy_registry/` with strategy identity docs
8. Create `platform/deployment/` with deployment docs
9. Create `platform/knowledge/LESSONS_LEARNED.md`

### Phase 2: Archive Migration (safe, no production impact)

10. Move root-level historical reports → `archive/research/reports/`
11. Move `archive/legacy/` contents → `archive/legacy/`
12. Move `risk_manager.py` → `archive/strategies/`
13. Move `notifications/signal_notifier.py` → `archive/strategies/`
14. Move root-level backtest scripts → `archive/research/`
15. Move `backtests/` → `archive/research/`
16. Move archived S-series scripts → `archive/research/scripts/`
17. Move outdated docs → `archive/research/`

### Phase 3: Research Migration

18. Move `zscore/` → `research/shared/zscore/`
19. Move `analytics/` → `research/shared/analytics/`
20. Move `regime/` → `research/shared/regime/`
21. Move `engines/` → `research/shared/engines/`
22. Move `backtest/` → `research/shared/backtest/`
23. Move `costs/` → `research/shared/costs/`
24. Move `data_validation/` → `research/shared/data_validation/`
25. Move `indicators/` → `research/shared/indicators/`
26. Move `data/` → `research/shared/data/`
27. Move `monitoring/circuit_breaker_analysis.py` → `research/experiments/`
28. Move root-level research scripts → `research/experiments/`
29. Move scripts research files → `research/experiments/scripts/`
30. Move `research_data/` → `research/data/`

### Phase 4: Production Migration

31. Move `signals/` → `production/strategies/`
32. Move `strategy/` → `production/strategies/`
33. Move `risk/` → `production/risk/`
34. Move `execution/` → `production/execution/`
35. Move `monitoring/` → `production/monitoring/`
36. Move `notifications/` → `production/notifications/`
37. Move `portfolio/` → `production/strategies/portfolio/`
38. Move `dashboard/` → `production/api/`
39. Move `dashboard-mobile/` → `production/api/mobile/`
40. Move operational scripts → `production/deployment/scripts/`

### Phase 5: Test Migration

41. Reorganize `tests/` into subdirectories:
    - `tests/safety/` — risk guard, circuit breakers, shadow, execution protection
    - `tests/production/` — adapter, orchestration, monitoring, lifecycle
    - `tests/parity/` — trade management parity
    - `tests/research/` — unit tests (zscore, signals, regime, features, data)
    - `tests/integration/` — smoke tests + future integration tests
    - `tests/platform/` — regression tests

### Phase 6: Import Repair

42. Fix all imports to use new paths
43. Update `__init__.py` files
44. Run test suite
45. Verify no circular dependencies

---

## 7. EXPECTED VERIFICATION GATES

| Gate | What | Pass Criteria |
|------|------|---------------|
| G1 | Import integrity | `python -c "import production; import research; import platform; import tests"` |
| G2 | Unit tests | All existing unit tests pass |
| G3 | Safety tests | All safety-critical tests pass |
| G4 | Smoke tests | End-to-end pipeline executes |
| G5 | Canonical V1 params | Signal params unchanged: LOOKBACK=5, ATR=14, SL=2.0, RRR=3.5 |
| G6 | Constitution params | Risk unchanged: 0.15%, 3 positions, 0.10 lots, 3.0 total |
| G7 | Production isolation | No production code imports from `research/` or `archive/` |
| G8 | Research isolation | No research code executable by production |
| G9 | Archive isolation | No archive code executable by production |
| G10 | Kill switch | Kill switch functional |
| G11 | Zero orders guard | Hard guard prevents order submission |
| G12 | Demo/live separation | DRY_RUN mode enforced |
| G13 | Git history | Clean history, no force-push, migration commits |

---

## 8. CANONICAL V1 VERIFICATION CHECKLIST

| Parameter | Expected | Source |
|-----------|----------|--------|
| Timeframe | 4H | `signals/breakout.py`, `execution/shadow/signal_generator.py` |
| Swing lookback | 5 bars | `signals/breakout.py:LOOKBACK=5` |
| ATR period | 14 | `signals/breakout.py:ATR_PERIOD=14` |
| ATR stop multiplier | 2.0 | `signals/breakout.py:ATR_SL_MULT=2.0` |
| RRR | 3.5 | `signals/breakout.py:RRR=3.5` |
| BUY/SELL symmetric | Yes | `signals/breakout.py` — identical logic both directions |
| Breakeven | 0.8R | `strategy/trade_management/breakeven.py:BREAKEVEN_RATIO=0.8` |
| Max hold | 7 days / 42 bars | `strategy/trade_management/max_hold.py:MAX_HOLD_DAYS=7` |
| Trailing stop | Swing-based | `strategy/trade_management/trailing_stop.py` |
| Risk per trade | 0.15% | `config/constitution.py:risk_per_trade_pct=0.0015` |
| Max concurrent | 3 | `config/constitution.py:max_concurrent_positions=3` |
| Max position size | 0.10 lots | `config/constitution.py:max_position_size_per_pair=0.10` |
| Max total exposure | 3.0 lots | `config/constitution.py:max_total_exposure=3.0` |
| Max daily loss | 3% | `config/constitution.py:max_daily_loss_pct=0.03` |
| Max drawdown | 8% | `config/constitution.py:max_drawdown_pct=0.08` |
| Max trades/day | 4 | `config/constitution.py:max_trades_per_day=4` |
| Correlation filter | None | No correlation code in signal path |
| Session filter | None | Not active in V1 |
| EMA filter | None | Not active in V1 |
| ADX filter | None | Not active in V1 |
| News filter | None | Not active in V1 |
| Regime filter | None | Not active in V1 |
| Live trading | DISABLED | `RuntimeMode.DRY_RUN` default |

---

## 9. NQTS VERSIONING PLAN

### 9.1 Strategy Identity Format

```
NQ-{STRATEGY_TYPE}-{VERSION}
```

Examples:
- `NQ-BREAKOUT-V1` — Current canonical
- `NQ-BREAKOUT-V2` — Future breakout variant
- `NQ-MR-V1` — Mean reversion
- `NQ-STATARB-V1` — Statistical arbitrage

### 9.2 NQTS System Version

```
NQTS-{MAJOR}.{MINOR}.{PATCH}
```

Current: `NQTS-1.0.0` (initial production architecture)

### 9.3 Version File Locations

| What | Location | Format |
|------|----------|--------|
| Strategy identity | `platform/strategy_registry/IDENTITY.md` | Markdown + frozen dataclass |
| Strategy params | `production/strategies/breakout_v1/params.py` | Python frozen dataclass |
| Runtime config | `platform/configuration/settings.py` | Python frozen dataclass |
| Constitution | `platform/configuration/constitution.py` | Python frozen dataclass (FROZEN) |
| Deployment config | `production/deployment/config/` | JSON |

---

## 10. UNRESOLVED ISSUES

| # | Issue | Risk | Recommendation |
|---|-------|------|----------------|
| 1 | `execution/contracts.py` used by both production and research | Import path change needed | Move to `platform/contracts/`, both import from there |
| 2 | Root `__init__.py` may define `nestquant` package | Import breakage | Keep at root, ensure re-exports |
| 3 | `research/` directory currently empty | No active research code | Will contain moved zscore/regime/engines etc. |
| 4 | `data/` modules dual-use (production loader + research) | Boundary unclear | Keep in `research/shared/`, production imports via interface |
| 5 | Integration tests directory empty | No integration tests | Create placeholder, document gap |
| 6 | 62 root-level markdown reports | Clutter | Move to `archive/research/reports/` |
| 7 | 14 root-level ad-hoc Python scripts | Clutter | Classify and move |
| 8 | Dashboard executes shell commands | Security concern | Already admin-only, but flag in governance docs |

---

## 11. MIGRATION SAFETY RULES

1. **STOP** if any migration change affects production runtime behavior
2. **STOP** if any import repair creates a production→research dependency
3. **STOP** if any file move changes the kill switch path
4. **STOP** if any file move changes the shadow safety guard
5. **STOP** if any file move changes the zero-orders sentinel
6. **STOP** if constitution.py is modified
7. **STOP** if strategy parameters in signal_generator.py are modified
8. **STOP** if demo/live separation is affected
9. **STOP** if MT5 bridge configuration changes
10. **STOP** if any test fails after migration

---

*End of Phase 0 — Forensic Inventory*
*Next: Phase 1 — Architecture Documentation*
