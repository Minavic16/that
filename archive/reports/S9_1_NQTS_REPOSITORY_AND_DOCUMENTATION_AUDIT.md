# S9.1 — NQTS Repository & Documentation Audit

**Date:** 2026-09-08
**Type:** Forensic documentation and repository-state audit
**Status:** Complete
**Predecessor:** S8.6.12 (Production Execution Protection)

---

## 1. Executive Summary

This audit establishes a canonical, evidence-based understanding of the NQTS repository after the 2026-09-08 consolidation. The repository contains 44 commits spanning 2025-07-21 to 2026-09-08, covering NestEdge website development (2025) and NestQuant Z-Score research-to-production (2026). The codebase is functional, testable, and well-structured — but documentation is stale and internally contradictory in several critical areas.

### Key Findings

| # | Finding | Severity |
|---|---------|----------|
| 1 | S8_PARITY_CERTIFICATION.md states "CONDITIONAL GREEN" for Production Execution Readiness; S8.6.12 upgraded it to GREEN — report is stale | HIGH |
| 2 | PROJECT_STATE.md describes pre-consolidation state, wrong local path, wrong branch | HIGH |
| 3 | TODO.md is pre-S7 era — none of the current priorities are listed | HIGH |
| 4 | CHANGELOG.md has only one entry (2026-08-07) — missing S7, S8, notifications | HIGH |
| 5 | docs/ARCHITECTURE.md describes Z-Score research pipeline, not current system | MEDIUM |
| 6 | Three inconsistent strategy configurations exist: ExperimentConfig, breakout.py, config/settings.py | CRITICAL |
| 7 | VPS dashboard code is out of sync with git (auth disabled locally, not committed) | HIGH |
| 8 | Dashboard credentials documented in CHANGELOG.md (security concern) | MEDIUM |
| 9 | 4 test failures: 1 pre-existing (`test_process_pair_with_signal`), 3 shadow tests (pandas-dependent, not importable locally) | LOW |
| 10 | 35/37 core modules import successfully without pandas | LOW |

### Documentation Health Matrix

| Document | Current? | Accurate? | Action Needed |
|----------|----------|-----------|---------------|
| AGENTS.md | ✅ Yes | ✅ Yes | None |
| S8_PARITY_CERTIFICATION.md | ❌ Stale | ⚠️ Partially | Update gate 3 to GREEN |
| PROJECT_STATE.md | ❌ Stale | ❌ Wrong path/branch | Full rewrite |
| TODO.md | ❌ Stale | ❌ Pre-S7 era | Full rewrite |
| CHANGELOG.md | ❌ Stale | ⚠️ Missing entries | Append S7, S8, notifications |
| docs/ARCHITECTURE.md | ❌ Stale | ❌ Wrong system | Rewrite or remove |
| S8_6_12 report | ✅ Current | ✅ Accurate | None |
| S8_6_REVIEW_ADDENDUM.md | ✅ Current | ✅ Accurate | None |
| S8_6_1 report | ✅ Current | ✅ Accurate | None |
| S8_6_3 report | ✅ Current | ✅ Accurate | None |

---

## 2. Repository State

### 2.1 Git Configuration

| Property | Value |
|----------|-------|
| Remote | `https://github.com/Minavic16/that.git` |
| Branch | `master` |
| HEAD | `339ba7e` (Merge branch 'master') |
| Working tree | Clean |
| Total commits | 44 |
| First commit | `5cfa801` 2025-07-21 — initial scaffold |
| Latest commit | `339ba7e` 2026-09-08 — merge |

### 2.2 Commit History (Chronological Phases)

| Phase | Commits | Date Range | Description |
|-------|---------|------------|-------------|
| NestEdge website | 14 | 2025-07-21 to 2025-09-03 | School management app (unrelated) |
| NestQuant baseline | 3 | 2026-08-07 to 2026-08-09 | Research state checkpoint + audit |
| Z-Score research | 1 | 2026-08-11 | Causal z-score research foundation |
| S7 shadow execution | 3 | 2026-08-19 to 2026-09-01 | Live shadow, MT5 bridge, protocol |
| S7 execution infrastructure | 7 | 2026-09-01 to 2026-09-02 | MT5 client, adapter, dry-run |
| Notifications | 2 | 2026-09-06 | Pipeline + Telegram bot |
| S8 runtime & monitoring | 3 | 2026-09-08 | Runtime, monitoring, tests, docs |

### 2.3 Working Tree Structure

```
/root/that/
├── execution/           # Core execution: runtime, adapter, MT5, protection, shadow
├── strategy/            # Lifecycle, trade management (breakeven, max_hold, trailing)
├── signals/             # Signal generators (breakout, base)
├── monitoring/          # Full monitoring stack (16 modules)
├── notifications/       # EventBus, policy, channels, Telegram, wiring
├── config/              # Experiment config, settings, policies, logging
├── analytics/           # Research analysis
├── indicators/          # ATR, EMA, swing, session, pip utils
├── nestquant/           # Root package (backtest, risk, validation, report)
├── tests/               # Test suite
├── dashboard/           # Next.js monitoring dashboard
├── dashboard-mobile/    # Native Android WebView app
├── scripts/             # Runners, validators
├── data/                # Raw data (gitignored)
├── logs/                # Runtime logs
├── research_data/       # S0-S6 research outputs (JSON, .md)
├── docs/                # Architecture, protocol, gate docs
├── config/policies/     # JSON policy files
└── *.md                 # 44 root-level markdown files (reports, audits, specs)
```

---

## 3. System Capability Matrix

### 3.1 Component Status

| Component | Implemented | Tested | Dry-Run | Demo-Validated | Production |
|-----------|-------------|--------|---------|----------------|------------|
| **Breakout signal** | ✅ | ✅ (pandas) | ✅ | ✅ S0-S6 | ❌ No live |
| **ATR calculation** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Swing detection** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **TradeGeometry.from_fill()** | ✅ | ✅ | ✅ | N/A | ❌ |
| **LifecycleRegistry** | ✅ | ✅ | ✅ | N/A | ❌ |
| **BreakevenManager** | ✅ | ✅ | ✅ | N/A | ❌ |
| **MaxHoldManager** | ✅ | ✅ | ✅ | N/A | ❌ |
| **TrailingStopManager** | ✅ | ✅ | ✅ | N/A | ❌ |
| **TradeLifecycleManager** | ✅ | ✅ | ✅ | N/A | ❌ |
| **S8Runtime** | ✅ | ✅ (1 failure) | ✅ | ❌ | ❌ |
| **IntentFactory** | ✅ | ✅ | ✅ | N/A | ❌ |
| **MT5Client** | ✅ | ✅ | ✅ | ✅ (VPS) | ❌ |
| **MT5ExecutionAdapter** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **ExecutionProtection** | ✅ | ✅ | ✅ | N/A | ❌ |
| **PropFirmGuard** | ✅ | ✅ | ✅ | N/A | ❌ |
| **LiveDataFeed** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **TradeLogger** | ✅ | ✅ | ✅ | N/A | ❌ |
| **PercentileFramework** | ✅ | ✅ | N/A | N/A | ❌ |
| **EVStabilityAnalyzer** | ✅ | ✅ | N/A | ❌ | ❌ |
| **DDClusterAnalyzer** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **CircuitBreakerAnalysis** | ✅ | ✅ | N/A | N/A | ❌ |
| **SlippageTracker** | ✅ | ✅ | N/A | N/A | ❌ |
| **LatencyTracker** | ✅ | ✅ | N/A | N/A | ❌ |
| **EquityTracker** | ✅ | ✅ | N/A | N/A | ❌ |
| **HealthCollector** | ✅ | ✅ | N/A | N/A | ❌ |
| **SpreadCollector** | ✅ | ✅ | N/A | N/A | ❌ |
| **Dashboard server** | ✅ | ✅ (import) | ❌ | ❌ (structural) | ❌ |
| **EventBus** | ✅ | ✅ | N/A | ❌ | ❌ |
| **NotificationPolicy** | ✅ | ✅ | N/A | N/A | ❌ |
| **TelegramChannel** | ✅ | ✅ | N/A | ❌ | ❌ |
| **EventDeduplicator** | ✅ | ✅ | N/A | N/A | ❌ |
| **Telegram bot** | ✅ | ✅ (import) | ❌ | ❌ | ❌ |
| **Wiring (pipeline)** | ✅ | ✅ | N/A | ❌ | ❌ |
| **Next.js dashboard** | ✅ | N/A | N/A | ❌ (auth broken) | ❌ |
| **Android APK** | ✅ | N/A | ❌ | ❌ (auth disabled) | ❌ |

### 3.2 Validation Coverage

| Validation Type | Coverage | Notes |
|----------------|----------|-------|
| Unit tests | 850 passing | Core modules verified |
| Import tests | 35/37 modules | 2 fail due to missing pandas |
| Dry-run execution | ✅ | S8 runtime dry-run validated |
| S0-S6 backtests | ✅ | 6 research populations, 74,755+ trades |
| Live shadow (stub) | ✅ | 420 bars, 38 signals, 100% fidelity |
| Live shadow (real MT5) | ❌ Blocked | No MT5 on Linux VPS |
| Production trading | ❌ Blocked | C7 feedback gap + lineage break |

---

## 4. Critical Findings

### 4.1 Strategy Identity Fragmentation (CRITICAL)

Three inconsistent configurations exist in the codebase:

| Configuration | WR | PF | Breakeven | Max Hold | RRR | ATR Mult |
|---------------|-----|-----|-----------|----------|-----|----------|
| `ExperimentConfig` (config/experiment.py) | N/A | N/A | 0.8 | 42 bars | 3.5 | 2.0 |
| `breakout.py` (RESEARCH_DEFAULTS) | N/A | N/A | **NONE** | **NONE** | 3.5 | 2.0 |
| `config/settings.py` | N/A | N/A | NONE | NONE | 3.5 | 2.0 |

**Impact:** All research populations (S0, S5.5, S6A) used breakeven + max_hold. The deployed `breakout.py` does NOT implement them. No historical population exactly matches the deployed strategy. This is the #1 blocker for live trading (identified in S8.6.3, Gate: RED).

### 4.2 Circuit Breaker Calibration Gap (CRITICAL)

- WinRateBreaker at 40% (20-trade window) would trigger ~56% of the time on S6A baseline (35.7% WR)
- The S8.6 report incorrectly concluded "0/127 triggers = correctly calibrated" by testing monthly WR instead of trade-level WR
- DrawdownPaceBreaker thresholds match S6A's max DD — would trigger during normal drawdown events
- SlippageBreaker has zero empirical data
- **None of the circuit breakers can function** because `record_trade_result()` is never called (C7 gap)

### 4.3 Documentation Staleness

**PROJECT_STATE.md:**
- States local path as `/root/nestquant` (actual: `/root/that`)
- Describes branch as `main` (actual: `master`)
- Lists "12 untracked directories" — all now committed
- References pre-S7 state entirely

**TODO.md:**
- Lists 15 tasks, all from pre-S7 era
- None of the current priorities (C7, lineage resolution, calibration) are mentioned
- Still shows "Research engine → 10.5 months of daily data" as pending (completed in S0-S6)

**CHANGELOG.md:**
- Only one entry: 2026-08-07 "Initial NestQuant baseline"
- Missing: S7 shadow execution, S7 execution infrastructure, notifications, S8 runtime, S8 monitoring
- Contains dashboard credentials in plaintext (`Mindavic`/`admin123`)

**S8_PARITY_CERTIFICATION.md:**
- Gate 3 "Production Execution Readiness" still says "CONDITIONAL GREEN"
- S8.6.12 upgraded it to GREEN
- The certification is the canonical status document — it must be current

**docs/ARCHITECTURE.md:**
- Describes the Z-Score research pipeline (rolling mean, rolling std, Z-score, forward returns)
- Does not describe the current system (runtime, monitoring, lifecycle, notifications)

### 4.4 VPS Code Drift

The VPS (`/root/nestquant/dashboard/`) has local modifications not in git:
- Auth middleware disabled (passthrough)
- `/api/auth/me` always returns `authenticated: true`
- Cookie handling changes
- Session endpoint modifications

These changes were made to fix Android WebView cookie issues but were never committed. The git repo and VPS are out of sync.

### 4.5 Security Concern

CHANGELOG.md contains plaintext credentials:
```
Admin: Mindavic / admin123
User: Noble prime / admin123
```
These are dashboard credentials documented in a version-controlled file.

---

## 5. Test Suite Status

### 5.1 Results Summary

```
850 passed, 4 failed (58.99s)
```

| Test | Status | Root Cause |
|------|--------|------------|
| `test_process_pair_with_signal` | FAILED | `_lifecycle_registry` is None — test creates S8Runtime without initializing registry |
| `test_creates_files_and_appends_jsonl` | FAILED | Requires pandas (not installed locally) |
| `test_small_replay_produces_logs_and_state` | FAILED | Requires pandas |
| `test_kill_switch_halts_runner` | FAILED | Requires pandas |

The 3 shadow test failures are environment-dependent (pandas not installed), not code defects. The 1 S8Runtime failure is a pre-existing test setup issue — the test instantiates S8Runtime with default config that doesn't initialize `_lifecycle_registry`.

### 5.2 Import Health

35 of 37 core modules import successfully without pandas. Only `signals.breakout` and `signals.base` fail due to pandas dependency. This is expected — signal generation requires OHLCV DataFrames.

---

## 6. Capability Gaps (Ordered by Priority)

| # | Gap | Blocks | Priority |
|---|-----|--------|----------|
| 1 | Strategy lineage break (breakeven/max_hold mismatch) | Live trading | CRITICAL |
| 2 | C7 trade outcome feedback | Circuit breakers, monitoring | CRITICAL |
| 3 | Circuit breaker recalibration (WR, DD thresholds) | Live monitoring | HIGH |
| 4 | Raw OHLCV data unavailable | Re-runs, validation | HIGH |
| 5 | Trade-level records missing | Monitoring calibration | HIGH |
| 6 | Dashboard auth broken for APK | Mobile monitoring | HIGH |
| 7 | VPS code drift | Deployment consistency | HIGH |
| 8 | Live slippage/latency/spread data | Threshold setting | MEDIUM |
| 9 | WinRateBreaker provably miscalibrated | False positives | MEDIUM |
| 10 | Monte Carlo DD values unreliable | Risk thresholds | MEDIUM |
| 11 | Live MT5 adapter (Linux blocked) | Real-market testing | LOW |
| 12 | Documentation staleness | Onboarding, clarity | MEDIUM |

---

## 7. Recommendations

### 7.1 Immediate (Before Any Further Development)

1. **Resolve strategy identity.** Decide: deploy breakeven+max_hold in breakout.py, OR accept S6A baseline (35.7% WR) as the deployed strategy. This is the #1 blocker.

2. **Update S8_PARITY_CERTIFICATION.md** — change gate 3 from "CONDITIONAL GREEN" to "GREEN" per S8.6.12.

3. **Scrub credentials from CHANGELOG.md** — remove plaintext `Mindavic`/`admin123` and `Noble prime`/`admin123`.

4. **Commit VPS dashboard changes** — auth disabled state should be version-controlled.

### 7.2 Short-Term (This Week)

5. **Rewrite PROJECT_STATE.md** — reflect post-consolidation reality, correct paths, current status.

6. **Rewrite TODO.md** — replace pre-S7 tasks with current priorities (C7, lineage, calibration).

7. **Update CHANGELOG.md** — add S7, S8, notifications entries.

8. **Decide on docs/ARCHITECTURE.md** — either rewrite to describe current system or remove.

### 7.3 Medium-Term (Before Live Trading)

9. **Implement C7 trade outcome feedback** — wire `record_trade_result()` into S8Runtime.

10. **Recalibrate circuit breakers** for S6A baseline (35.7% WR).

11. **Begin passive data collection** — spread, latency, health to build baseline distributions.

12. **Re-run research with breakout.py's actual config** (no breakeven/max_hold) to establish correct baseline.

---

## 8. What This Audit Did NOT Cover

- Deep code review of every module (covered by S8.6 review addendum)
- Performance profiling
- Security audit beyond credential exposure
- VPS infrastructure audit (covered by previous sessions)
- Live trading readiness assessment (covered by S8.6.12)

---

## 9. Conclusion

The NQTS repository is architecturally sound with a well-structured codebase, comprehensive test suite (850 passing), and clear separation of concerns. The S8 runtime, monitoring, and execution protection infrastructure is production-quality code. However, the project is blocked from live trading by a strategy identity fragmentation issue that predates S8 — no historical population matches the deployed strategy's exact configuration. Documentation is stale and contradictory in several key documents. These issues are all resolvable but must be addressed before any live deployment.

**Bottom line:** The code is good. The documentation is stale. The strategy identity is broken. Fix the identity, update the docs, then continue.

---

**Files changed:** None (audit only)
**Tests run:** 854 total, 850 passed, 4 failed (1 pre-existing, 3 environment-dependent)
**Git status:** Clean working tree, HEAD `339ba7e`
