# NQTS Shadow Validation Plan
# Date: 2026-09-15
# Status: READY TO BEGIN
# Validation target: Can NQTS continuously operate according to its
# constitution, preserve state, maintain data integrity, survive
# expected operational events, and faithfully report what it is doing?

## Validation Principle

The goal is NOT "can it generate another signal?"
The goal IS "does the system do exactly what it says it does, reliably, over time?"

A negative result is a valid result. If NQTS fails these gates, we have
found a real bug, which is more valuable than a passing test.

## Gate Structure

Each gate must PASS before moving to the next.
Each gate has: criteria, observation window, evidence collection, and verdict.

---

### Gate D1: State Persistence (24h)
**Question:** Does NQTS preserve its state across 24 hours of continuous operation?

**Criteria:**
- state.json exists and is readable
- state.json updated_at advances over time
- bars_processed increases as new 4H candles complete
- signals_emitted is accurate (matches signals.jsonl count)
- last_bar timestamps are monotonically increasing per pair
- No corruption in state.json (valid JSON, correct schema)

**Observation window:** 24 hours minimum
**Evidence:** state.json snapshots every 6 hours, signals.jsonl line count
**Verdict:** PASS if state is consistent across all snapshots; FAIL if any corruption detected

---

### Gate D2: Data Integrity (48h)
**Question:** Does NQTS maintain data integrity across 48 hours of operation?

**Criteria:**
- bars.jsonl contains only completed candles (no forming candles)
- Each bar has valid OHLCV relationships (H >= O,C,L; L <= O,C,H)
- No duplicate timestamps in bars.jsonl (same pair + timestamp)
- signals.jsonl entries have valid signal_id (UUID4 format)
- signals.jsonl entries have consistent schema across all entries
- infrastructure.jsonl events have valid timestamps and event types
- No file grows beyond reasonable bounds (>1GB = suspect)

**Observation window:** 48 hours minimum
**Evidence:** File sizes, line counts, schema validation scripts
**Verdict:** PASS if all integrity checks pass; FAIL on any violation

---

### Gate D3: Operational Resilience (72h)
**Question:** Does NQTS survive expected operational events?

**Events to observe (natural occurrence):**
- Weekend market closure (Saturday-Sunday)
- Monday market open
- Daylight saving transitions (if applicable)
- MT5 bridge temporary disconnection (if it occurs)
- Network latency spikes (if they occur)

**Criteria:**
- Runner stays alive through weekend (no crash, no restart needed)
- State.json updates correctly on Monday (new bars processed)
- No duplicate processing of same bar after weekend gap
- Gaps in infrastructure.jsonl correctly identified and logged
- Health status transitions are accurate (GREEN during trading, appropriately during weekends)

**Observation window:** 72 hours minimum (ideally spanning a weekend)
**Evidence:** Runner process uptime, state.json continuity, infrastructure.jsonl events
**Verdict:** PASS if system survives all observed events; FAIL on crash, data loss, or incorrect state

---

### Gate D4: Reporting Fidelity (96h)
**Question:** Does the dashboard accurately reflect the system's actual state?

**Criteria:**
- Dashboard health endpoint matches runner's actual state
- Dashboard bars_processed matches state.json counters
- Dashboard signals_emitted matches signals.jsonl count
- Dashboard data_fresh is TRUE when state.json was recently updated
- Dashboard data_fresh is FALSE when state.json is stale
- Dashboard mt5.connected matches actual bridge connectivity
- Dashboard runner.status matches actual process existence
- Dashboard telegram.connected matches actual credential availability
- Health endpoint GREEN when all systems nominal
- Health endpoint AMBER when degradation detected

**Observation window:** 96 hours minimum
**Evidence:** API responses vs state.json snapshots, side-by-side comparison
**Verdict:** PASS if dashboard always reflects reality; FAIL on any desync

---

### Gate D5: Signal Accuracy (variable)
**Question:** When a signal IS generated, is it correct according to the strategy?

**Criteria:**
- Signal generated from a completed candle (not forming)
- Entry = swing level (as defined by 5-bar lookback)
- SL = entry ± (ATR14 × 2.0)
- TP = entry ∓ (ATR14 × 2.0 × 3.5) — i.e., RRR = 3.5
- Direction matches breakout direction
- Timestamp = bar close time (UTC)
- Signal ID is unique UUID4
- Signal appears in both signals.jsonl AND Telegram notification

**Observation window:** Until next signal occurs
**Evidence:** signals.jsonl entry, Telegram notification, strategy parameter verification
**Verdict:** PASS if all signals match specification; FAIL on any deviation

---

### Gate D6: Notification Pipeline (continuous)
**Question:** Does the notification pipeline deliver correct information?

**Criteria:**
- Telegram @NQTSbot sends signal alerts within 30 seconds of signal generation
- Alert format matches specification (direction, symbol, entry, SL, TP, ATR)
- Health alerts sent when status changes (GREEN→AMBER, AMBER→RED)
- Circuit breaker alerts sent when breaker triggers
- Risk block alerts sent when risk guard rejects
- No duplicate alerts for same event (dedup working)
- No alerts suppressed that should have been sent

**Observation window:** Continuous from now
**Evidence:** Telegram message history, notification pipeline logs
**Verdict:** PASS if all observable notifications are correct; FAIL on missing or incorrect alerts

---

### Gate D7: System Longevity (7 days)
**Question:** Can NQTS operate continuously for 7 days without intervention?

**Criteria:**
- No manual restarts required
- No disk space exhaustion
- No memory leaks (process RSS stable)
- No log file corruption
- State.json remains valid throughout
- Dashboard remains accessible throughout
- All previous gates (D1-D6) continue to pass

**Observation window:** 7 days minimum
**Evidence:** Process uptime, disk usage, memory usage, all previous gate evidence
**Verdict:** PASS if system runs unattended for 7 days; FAIL on any required intervention

---

## Execution Protocol

1. Gates D1-D4 run in parallel (all start from T=0)
2. Gate D5 activates on next signal event
3. Gate D6 activates immediately (Telegram notifications begin)
4. Gate D7 starts after D1 passes (24h minimum)
5. Each gate produces a verdict file: `logs/shadow_live/validation/D{n}_verdict.json`
6. All verdicts are collected in `logs/shadow_live/validation/summary.json`

## Verdict File Format

```json
{
  "gate": "D1",
  "title": "State Persistence",
  "start_time": "2026-09-15T17:00:00Z",
  "end_time": "2026-09-16T17:00:00Z",
  "verdict": "PASS",
  "criteria": [
    {"name": "state.json exists", "passed": true, "evidence": "..."},
    {"name": "updated_at advances", "passed": true, "evidence": "..."}
  ],
  "notes": ""
}
```

## How to Begin

The shadow runner is already running. The validation begins now.
First evidence collection: check state.json at 6-hour intervals.
First verdict: D1 after 24 hours (2026-09-16T17:00:00 UTC+2).
