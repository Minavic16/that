# S8.6.12 — Execution Protection Hardening

**Date:** 2026-09-04
**Status:** Complete
**Gate:** 🟢 GREEN

---

## 1. Problem Statement

Temporary broker/network failures could silently cause persistent divergence between internal lifecycle state and broker position state. Specifically:

- SL modification failure → internal SL advances, broker SL stays old
- No retry for transient failures
- No escalation for repeated critical mismatches
- No structured events for monitoring

---

## 2. Failure Model

| Failure | Current Impact | S8.6.12 Mitigation |
|---------|---------------|-------------------|
| Network timeout | SL not modified | Retry with backoff |
| Bridge unavailable | SL not modified | Retry with backoff |
| Invalid SL | SL not modified | Non-retryable, halt |
| Invalid position | SL not modified | Non-retryable, halt |
| Market closed | SL not modified | Non-retryable, halt |
| Trading disabled | SL not modified | Non-retryable, halt |
| Repeated mismatches | Silent divergence | Circuit breaker opens |

---

## 3. Retry Architecture

```
Lifecycle proposes new SL
        ↓
Execute modification with retry
        ↓
    Attempt 1 → fails (retryable?)
        ↓ YES
    Sleep(backoff)
        ↓
    Attempt 2 → fails (retryable?)
        ↓ YES
    Sleep(backoff)
        ↓
    Attempt 3 → fails
        ↓
    All retries exhausted
        ↓
    Rollback pending SL
    Record reconciliation requirement
    Emit CRITICAL event
```

Configuration:
- `MAX_MODIFICATION_RETRIES = 3`
- `INITIAL_RETRY_DELAY_SECONDS = 1.0`
- `BACKOFF_MULTIPLIER = 2.0`
- `MAX_DELAY_SECONDS = 30.0`

---

## 4. Failure Classification

| Class | Examples | Retry? |
|-------|----------|--------|
| RETRYABLE | Connection timeout, bridge error, network reset | Yes |
| NON_RETRYABLE | Invalid ticket, invalid SL, market closed, trading disabled | No |
| UNKNOWN | Unclassified errors | No |

Classification is based on MT5 retcodes and error message patterns.

---

## 5. State Integrity Invariant

**Critical change:** Lifecycle proposals stage a pending SL. Broker confirmation triggers commit.

```
evaluate_bar() → stages pending SL
        ↓
adapter.modify_position_stop()
        ↓
    Success → commit_sl() → advances current_sl
    Failure → rollback_sl() → discards pending, keeps confirmed
```

**Before S8.6.12:**
```python
# registry.py line 179 (OLD)
object.__setattr__(position, 'current_sl', decision.new_sl)  # ← IMMEDIATE COMMIT
```

**After S8.6.12:**
```python
# registry.py (NEW)
self._pending_sl[trade_id] = decision.new_sl  # ← STAGED, NOT COMMITTED
# ... later, after broker confirmation:
registry.commit_sl(trade_id)  # ← ONLY NOW COMMITS
```

---

## 6. Circuit Breaker Behavior

```
Critical mismatch detected
        ↓
Increment counter
        ↓
Counter >= threshold?
        │
    YES → OPEN breaker (block new entries)
    NO  → continue monitoring
```

While breaker is open:
- ❌ New trade entries blocked
- ✅ Existing positions continue lifecycle
- ✅ Reconciliation continues
- ✅ SL modifications continue
- ❌ No automatic reset — requires explicit `reset_circuit_breaker()`

Configuration:
- `MAX_CRITICAL_RECONCILIATION_FAILURES = 3`

---

## 7. Code Changes

### Created
- `execution/protection.py` — ExecutionProtection, RetryConfig, CircuitBreakerConfig, classify_failure, FailureClass, ClassifiedModificationResult, ExecutionProtectionEvent

### Modified
- `strategy/lifecycle/registry.py` — pending_sl tracking, commit_sl(), rollback_sl(), get_pending_sl(), get_confirmed_sl(), get_current_sl()
- `execution/s8_runtime.py` — _execute_sl_modification() with retry+integrity, _reconcile_broker_state() with circuit breaker, _process_signal() with breaker gate

### Tests Updated (state integrity)
- `tests/test_fill_aware_geometry.py` — added commit_sl() after evaluate_bar()
- `tests/test_e2e_runtime_replay.py` — added commit_sl() after evaluate_bar()
- `tests/test_lifecycle_integration.py` — added commit_sl() after evaluate_bar()

---

## 8. Test Inventory

```
tests/test_execution_protection.py      33 passed

TestFailureClassification               8 tests
  test_success_is_non_retryable
  test_connection_failure_is_retryable
  test_invalid_ticket_is_non_retryable
  test_invalid_sl_is_non_retryable
  test_market_closed_is_non_retryable
  test_trading_disabled_is_non_retryable
  test_unknown_error_is_unknown
  test_bridge_error_is_retryable

TestRetryLogic                          7 tests
  test_succeeds_on_first_attempt
  test_fails_once_then_succeeds
  test_fails_twice_then_succeeds
  test_all_retries_exhausted
  test_non_retryable_failure_does_not_retry
  test_events_recorded

TestStateIntegrity                      4 tests
  test_pending_sl_not_committed_before_confirmation
  test_commit_sl_advances_confirmed_sl
  test_rollback_preserves_previous_confirmed_sl
  test_successful_retry_commits_sl_once

TestCircuitBreaker                      8 tests
  test_one_mismatch_does_not_halt
  test_threshold_opens_breaker
  test_new_entries_blocked_while_open
  test_reset_allows_new_entries
  test_reset_records_event
  test_breaker_open_event_recorded
  test_existing_positions_continue_lifecycle
  test_reconciliation_continues_while_open
  test_manual_reset_required

TestClassifiedModificationResult        4 tests
  test_success_should_not_retry
  test_retryable_failure_should_retry
  test_retryable_exhausted_should_not_retry
  test_non_retryable_is_permanent

TestRetryConfig                         2 tests
  test_delay_for_attempt
  test_max_delay_cap
```

---

## 9. Full Test Results

```
127 passed

test_execution_protection.py           33 passed
test_startup_reconciliation.py         18 passed
test_mt5_adapter_modification.py        8 passed
test_fill_aware_geometry.py            12 passed
test_e2e_runtime_replay.py              4 passed
test_lifecycle_integration.py          23 passed
test_trade_management_parity.py        29 passed
```

---

## 10. Remaining Execution Risks

| Risk | Priority | Status |
|------|----------|--------|
| Naked-order window (fill → SL mod) | MEDIUM | Accepted inherent risk |
| Startup reconciliation | HIGH | ✅ Implemented (S8.6.11) |
| SL modification retry | HIGH | ✅ This task |
| State integrity (pending→commit) | HIGH | ✅ This task |
| Circuit breaker escalation | HIGH | ✅ This task |
| Circuit breaker feedback from trades | LOW | Out of scope |

---

## 11. Updated Production Readiness

| Gate | Status |
|------|--------|
| Strategy Lineage Parity | 🟢 GREEN |
| Runtime Integration Parity | 🟢 GREEN |
| Production Execution Readiness | 🟢 GREEN |

**Production Execution Readiness upgraded from 🟡 to 🟢.**

All critical execution protection gaps have been addressed:
- Startup reconciliation prevents orphan management
- Retry policy handles transient failures
- State integrity prevents silent SL divergence
- Circuit breaker escalates repeated critical mismatches
- Structured events enable monitoring integration
