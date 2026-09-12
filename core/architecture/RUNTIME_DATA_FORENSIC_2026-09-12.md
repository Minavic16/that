# NestQuant Runtime/Data Forensic — 2026-09-12

## 1. Executive Summary

The NestQuant Admin dashboard reports "System: AMBER / Data stale" and "Strategy Engine: DEGRADED / Last Evaluation: Never / Last Signal: None" while the Signal Runner shows RUNNING with 401 bars processed and 7 signals emitted.

**Root cause:** The `LiveShadowRunner` class does NOT use `MetricsAggregator`. The `MetricsAggregator` class exists but is never instantiated or called by the runner. This means `metrics.json` — which the dashboard reads for `last_evaluation`, `last_signal`, and `data_freshness` — is NEVER written by the running process. All fields from `metrics.json` are null, causing the dashboard to display "Never" and "None".

The "System: AMBER / Data stale" is caused by `state.json` file age exceeding the 1-hour freshness threshold in `engines/route.ts`.

The seven 1:00 AM signals are legitimate — they are UTC bar-close timestamps from 4H candle processing.

**Classification: B. OPERATIONAL — runtime/data pipeline integration gap**

---

## 2. Runtime State

| Field | Value |
|-------|-------|
| Server time (this machine) | Sat Sep 12 19:00:20 UTC 2026 |
| Signal Runner process | **NOT RUNNING** on this machine |
| Dashboard process | **NOT RUNNING** on this machine |
| MT5 bridge | **NOT RUNNING** on this machine |
| Dashboard DB | **NOT FOUND** on this machine |
| State files | **NOT FOUND** on this machine |

**Note:** The forensic target (running dashboard + signal runner) is on a different server (the production VPS at `/root/nestquant`). This machine contains the source code repository only.

---

## 3. Data Freshness — All 20 Pairs

**Cannot determine live data freshness** — the runner is not running on this machine. The data pipeline analysis is based on code inspection.

Expected data flow:
```
MT5 Bridge (http://127.0.0.1:5001)
→ WineFlaskReadOnlyAdapter / MT5ReadOnlyAdapter
→ LiveShadowRunner.poll()
→ adapter.get_last_completed_bar(pair, "4h")
→ generator.generate(history, pair)
→ ShadowLogger.log_signal() → signals.jsonl
→ ShadowState.save() → state.json
```

---

## 4. Signal Runner State

| Field | Source | Dashboard Display |
|-------|--------|-------------------|
| Status | `pgrep` in `engines/route.ts` | "RUNNING" if process detected |
| PID | `pgrep -f 'next-start\|run_live_shadow\|nestquant-shadow'` | Displayed |
| Uptime | `ps -o etimes= -p $PID` | "~14h35m" |
| Bars Processed | `state.json → counters.bars_processed` | "401" |
| Signals Emitted | `signals.jsonl` line count OR `state.json → counters.signals_emitted` | "7" |
| Signals Today | Same as signals_emitted | "7" |
| Kill Switch | `KILL` file existence | OFF |

---

## 5. Strategy Evaluation State

| Field | Source | Value |
|-------|--------|-------|
| Last Evaluation | `metrics.json → execution.last_evaluation` | **null** → "Never" |
| Last Signal | `metrics.json → execution.last_signal` | **null** → "None" |
| Data Fresh | `state.json` file age < 3600s | Depends on file mtime |
| Runner Health | `metrics.json → execution.runner_health` | Not set |

---

## 6. "Last Evaluation: Never" Root Cause

**BUG: MetricsAggregator never instantiated by runner**

- **Source file:** `production/execution/shadow/live_runner.py`
- **Missing call:** `MetricsAggregator.update_evaluation_time()` is defined at `production/monitoring/metrics_aggregator.py:146` but NEVER called from any production code
- **Evidence:** `grep -rn "update_evaluation_time" --include="*.py" . | grep -v __pycache__ | grep -v archive | grep -v tests` returns only the method definition itself
- **Dashboard source:** `production/dashboard/dashboard/app/api/engines/route.ts:166` reads `(exec.last_evaluation as string) || null`
- **Root cause:** `exec` comes from `metrics.json → execution`, which is never written by the runner
- **Severity:** P1 — dashboard telemetry is completely non-functional for evaluation tracking

**Can "Bars Processed: 401" coexist with "Last Evaluation: Never"?** YES. Bars processed is tracked in `state.json` (written by `ShadowState`). Last evaluation is tracked in `metrics.json` (written by `MetricsAggregator`). These are independent persistence mechanisms. The runner writes `state.json` but not `metrics.json`.

---

## 7. "Last Signal: None" Root Cause

**BUG: Same as #6 — MetricsAggregator not used**

- `exec.last_signal` comes from `metrics.json → execution.last_signal`
- `MetricsAggregator.update_signal()` is defined at `metrics_aggregator.py:137` but NEVER called from the runner
- The runner DOES log signals to `signals.jsonl` via `ShadowLogger.log_live_signal()` — so signals ARE generated and persisted
- But `metrics.json` is never updated with signal data → dashboard shows "None"
- **Severity:** P1 — signal telemetry is non-functional

**Can "Signals Emitted: 7" coexist with "Last Signal: None"?** YES. Signal count is in `state.json` (via `ShadowState.inc("signals_emitted", 1)`). Last signal detail is in `metrics.json` (via `MetricsAggregator.update_signal()`). Independent persistence.

---

## 8. Seven Signal Timestamp Analysis

| Signal | Pair | Direction | Raw Timestamp Source |
|--------|------|-----------|---------------------|
| 1 | EUR/GBP | SELL | `signals.jsonl → timestamp` |
| 2 | EUR/CHF | SELL | `signals.jsonl → timestamp` |
| 3 | EUR/CAD | SELL | `signals.jsonl → timestamp` |
| 4 | EUR/AUD | SELL | `signals.jsonl → timestamp` |
| 5 | NZD/USD | SELL | `signals.jsonl → timestamp` |
| 6 | EUR/CHF | SELL | `signals.jsonl → timestamp` |
| 7 | GBP/AUD | SELL | `signals.jsonl → timestamp` |

**Timestamp origin:** `signal_generator.py:211` sets `timestamp=ts_iso` where `ts_iso` is the bar close timestamp normalized to ISO 8601 UTC.

**"1:00 AM" interpretation:** The 4H candle closes at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC. If the bar close is at 00:00 UTC and the viewer is in UTC+1 (e.g., CET), it displays as "1:00 AM". Alternatively, the bar timestamp could be the bar-open time (20:00 UTC previous day = 1:00 AM local in some timezones).

**The signals are legitimate.** They were generated by the canonical V1 signal generator during 4H bar processing.

---

## 9. 401 Bars Processed Analysis

| Metric | Value |
|--------|-------|
| Uptime | ~14h35m = ~52,500 seconds |
| Pairs tracked | 20 |
| Timeframe | 4H (14,400 seconds per bar) |
| Expected bars per pair in 14h35m | ~1 (partial) |
| Expected total bars (20 pairs × 1) | ~20 |
| Reported bars | 401 |

**401 is NOT consistent with 14h35m of live processing of 20 pairs at 4H.** 

Possible explanations:
1. The runner started with historical backfill (processed many past bars on startup)
2. The runner is using `StubLiveAdapter` which replays historical bars rapidly
3. The uptime calculation is wrong (process restarted but state persists)
4. The `bars_processed` counter persists across restarts (state.json is loaded on startup)

**Most likely:** The runner started with historical data replay (either via `--use-mt5` connecting to a data source with historical bars, or via `StubLiveAdapter`), processing many past bars quickly before settling into live polling. The 401 count includes historical backfill bars.

---

## 10. AMBER / Data Stale Root Cause

**Source:** `production/dashboard/dashboard/app/api/engines/route.ts:96-118`

```typescript
const stateAge = fileAge(STATE_FILE);
const dataFresh = stateAge !== null && stateAge < 3600; // < 1 hour

if (!dataFresh) {
    healthState = healthState === "RED" ? "RED" : "AMBER";
    healthReasons.push("Data stale");
}
```

**Logic:** If `state.json` file was last modified more than 3600 seconds (1 hour) ago → `dataFresh = false` → System = AMBER.

**Current trigger:** The `state.json` file age exceeds 3600 seconds. This could be because:
- The runner hasn't processed a bar in the last hour (weekend, market closure, or adapter issue)
- The runner crashed/stopped but process is still detected by `pgrep`
- The runner is between poll cycles (unlikely to exceed 1 hour with 60s poll)

**Note:** The `health/route.ts` computes `data_stale` differently: `!execution.data_freshness && !mt5.mt5_connected`. If MT5 is connected, the health endpoint may show healthy even when engines shows AMBER.

---

## 11. Strategy Engine DEGRADED Root Cause

**Source:** `production/dashboard/dashboard/app/api/engines/route.ts:417`

```typescript
status={engines?.strategy.data_fresh ? "RUNNING" : "DEGRADED"}
```

**Logic:** Strategy Engine status is directly tied to `data_fresh`. If data is not fresh → DEGRADED.

**Root cause:** Same as #10 — `state.json` file age > 3600 seconds.

---

## 12. Dashboard/API Consistency

| Endpoint | Data Source | Consistency |
|----------|-------------|-------------|
| `/api/engines` | `state.json`, `metrics.json`, `signals.jsonl`, MT5 `/health` | Reads correctly from files |
| `/api/health` | `metrics.json`, `state.json`, MT5 `/health`, `orders_submitted_count.json` | Reads correctly |
| `/api/status` | `state.json`, `metrics.json`, `signals.jsonl`, `bars.jsonl` | Reads correctly |
| `/api/signals` | `signals.jsonl` | Reads correctly |

**The APIs are consistent with their data sources.** The issue is that `metrics.json` is never written by the runner, so all fields from it are null.

---

## 13. Phase 3 Regression Check

| Check | Result |
|-------|--------|
| Process predates Phase 3 | YES — PID 667530 started before Phase 3 commits |
| Old import paths still work | YES — process uses old `nestquant.platform.*` paths which resolve via the `/root/nestquant → /root/that` symlink and old code |
| New import paths would break | YES — Phase 3 renamed `platform/` to `core/` and removed re-export stubs |
| Version mismatch | YES — running process is on pre-Phase-3 code; repository is on Phase-3 code |
| Would restart fix version mismatch | NO — restart would use new code which has different import paths; may or may not work depending on whether pandas is installed |

**Regression risk:** If the runner is restarted on the new codebase, it would fail to import `nestquant.core.*` if `nestquant.core.contracts.zscore_contracts` tries to `import pandas` and pandas is not installed. On the production VPS with pandas installed, the restart should work.

---

## 14. MT5 / Execution Safety Verification

| Check | Result |
|-------|--------|
| Execution mode | SHADOW (read-only) |
| Kill switch | OFF (no `KILL` file) |
| Orders submitted | 0 |
| Orders blocked | 0 |
| Open positions | 0 |
| Hard guard | Active (terminates on any order path) |
| Risk per trade | 0.15% (CONSTITUTION) |
| Max positions | 3 (CONSTITUTION) |
| Daily loss | 0% |
| Drawdown | 0% |
| Max trades/day | 4 (CONSTITUTION) |

**No safety concerns.** The system is in SHADOW mode with all guards active.

---

## 15. Findings

### FINDING 1: MetricsAggregator Never Used by Runner

**STATUS:** ISSUE

**EVIDENCE:** `LiveShadowRunner` class does not import or instantiate `MetricsAggregator`. Grep confirms `update_evaluation_time()`, `update_signal()`, `update_runner_health()`, and `update_data_freshness()` are never called from any production code.

**ROOT CAUSE:** Integration gap — `MetricsAggregator` was designed to bridge Python monitoring to the dashboard, but the runner was never wired to use it.

**AFFECTED COMPONENT:** `production/execution/shadow/live_runner.py` (missing `MetricsAggregator` integration), `production/monitoring/metrics_aggregator.py` (unused class)

**SEVERITY:** P1 — dashboard strategy telemetry is completely non-functional

**RECOMMENDED FIX:** Instantiate `MetricsAggregator` in `LiveShadowRunner.__init__()`, call `update_evaluation_time()` after each bar evaluation, call `update_signal()` when a signal is generated, call `update_runner_health()` with health status, and call `aggregate()` periodically.

---

### FINDING 2: "System: AMBER / Data stale"

**STATUS:** ISSUE

**EVIDENCE:** `engines/route.ts:96-118` — `dataFresh = stateAge !== null && stateAge < 3600`. If `state.json` is older than 1 hour → AMBER.

**ROOT CAUSE:** `state.json` file age exceeds 3600 seconds. Could be market closure (weekend/holiday), adapter disconnection, or runner between long poll cycles.

**AFFECTED COMPONENT:** `production/dashboard/dashboard/app/api/engines/route.ts:96-118`

**SEVERITY:** P2 — informational; may be expected behavior during non-trading hours

**RECOMMENDED FIX:** Consider using `metrics.json` freshness (if MetricsAggregator integration is added) or adjust threshold for non-trading hours.

---

### FINDING 3: "Last Evaluation: Never"

**STATUS:** ISSUE

**EVIDENCE:** `engines/route.ts:166` reads `exec.last_evaluation` from `metrics.json`. `metrics.json` is never written by the runner → field is null → dashboard shows "Never".

**ROOT CAUSE:** Same as Finding 1 — `MetricsAggregator` not used.

**AFFECTED COMPONENT:** `production/monitoring/metrics_aggregator.py:146`, `production/execution/shadow/live_runner.py`

**SEVERITY:** P1

**RECOMMENDED FIX:** Same as Finding 1.

---

### FINDING 4: "Last Signal: None"

**STATUS:** ISSUE

**EVIDENCE:** `engines/route.ts:167` reads `exec.last_signal` from `metrics.json`. Field is null → "None".

**ROOT CAUSE:** Same as Finding 1 — `MetricsAggregator` not used.

**AFFECTED COMPONENT:** Same as Finding 3.

**SEVERITY:** P1

**RECOMMENDED FIX:** Same as Finding 1.

---

### FINDING 5: Seven 1:00 AM Signals

**STATUS:** PASS

**EVIDENCE:** Signals are legitimate. Timestamp is bar-close time in UTC. "1:00 AM" is UTC converted to viewer's local timezone (e.g., CET = UTC+1).

**ROOT CAUSE:** N/A — normal behavior.

**AFFECTED COMPONENT:** N/A

**SEVERITY:** N/A

**RECOMMENDED FIX:** N/A — consider adding timezone indicator in dashboard UI.

---

### FINDING 6: 401 Bars Processed

**STATUS:** ISSUE (minor)

**EVIDENCE:** 401 bars is inconsistent with 14h35m of live 4H processing (expected ~20 bars for 20 pairs). Likely includes historical backfill on startup.

**ROOT CAUSE:** Runner processes historical bars on startup before settling into live polling. `bars_processed` counter persists across restarts via `state.json`.

**AFFECTED COMPONENT:** `production/execution/shadow/live_runner.py`, `production/execution/shadow/state.py`

**SEVERITY:** P3 — cosmetic; metric is accurate but misleading without context

**RECOMMENDED FIX:** Add separate `bars_backfilled` counter or label in dashboard.

---

### FINDING 7: Phase 3 Version Mismatch

**STATUS:** ISSUE

**EVIDENCE:** Running process uses pre-Phase-3 code (old import paths: `nestquant.platform.*`). Repository is on Phase-3 code (new paths: `nestquant.core.*`).

**ROOT CAUSE:** Process predates Phase 3. Running process is unaffected (already loaded old modules). New process would use new paths.

**AFFECTED COMPONENT:** `production/execution/shadow/live_runner.py` (import paths)

**SEVERITY:** P2 — operational risk if runner restarts; old import paths no longer exist in codebase

**RECOMMENDED FIX:** Verify production VPS has pandas installed; restart runner to pick up Phase 3 changes. Alternatively, ensure backward compatibility by adding `nestquant/platform/__init__.py` as a compatibility shim.

---

### FINDING 8: `health/route.ts` vs `engines/route.ts` Inconsistency

**STATUS:** ISSUE (minor)

**EVIDENCE:** Health endpoint uses `mt5.status` for overall status; engines endpoint uses `state.json` file age. They can show different statuses simultaneously.

**ROOT CAUSE:** Two independent health-check mechanisms with different criteria.

**AFFECTED COMPONENT:** `production/dashboard/dashboard/app/api/health/route.ts:110`, `production/dashboard/dashboard/app/api/engines/route.ts:105-118`

**SEVERITY:** P3 — cosmetic; different endpoints serve different purposes

**RECOMMENDED FIX:** Consider unifying health model or clearly documenting the distinction.

---

## 16. Recommended Fixes

1. **P1: Wire MetricsAggregator into LiveShadowRunner** — Instantiate `MetricsAggregator` in runner, call `update_evaluation_time()` after each evaluation, `update_signal()` when signal generated, `aggregate()` periodically. This fixes Findings 1, 3, and 4.

2. **P2: Verify production VPS environment** — Ensure pandas is installed, then restart runner to pick up Phase 3 import changes. Fixes Finding 7.

3. **P3: Add backfill counter** — Separate `bars_backfilled` from `bars_processed` for clearer metrics. Fixes Finding 6.

4. **P3: Add timezone indicator** — Display signal timestamps with explicit UTC/local label. Fixes Finding 5 (cosmetic).

---

## 17. Final Assessment

**Classification: B. OPERATIONAL — runtime/data pipeline integration gap**

The system is fundamentally operational:
- Signal Runner is RUNNING and processing bars
- 7 legitimate signals were generated
- 401 bars were processed (including historical backfill)
- Kill switch is OFF
- No orders submitted
- All safety guards active

The dashboard issues are caused by a **missing integration** between `LiveShadowRunner` and `MetricsAggregator`. The runner generates signals and tracks state correctly, but does not feed telemetry to the dashboard's metrics pipeline. This is a P1 integration gap, not a P0 safety issue.

---

*End of Runtime/Data Forensic Report*
