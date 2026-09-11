# S8.6.11 — Startup Reconciliation & Orphan Position Recovery

**Date:** 2026-09-04
**Status:** Complete
**Gate:** 🟢 GREEN

---

## 1. Problem Statement

A runtime crash or restart can leave broker positions completely unmanaged:

1. Runtime sends market order → broker fills
2. Runtime crashes before `LifecycleRegistry.register_entry()`
3. Broker has open position; internal registry does not
4. Position receives no lifecycle management (no SL moves, no trailing, no BE)

This was the highest-priority production safety gap.

---

## 2. Architecture Implemented

### Startup Flow

```
INITIALIZE
    ↓
CONNECT TO BROKER
    ↓
FETCH BROKER OPEN POSITIONS
    ↓
FETCH INTERNAL REGISTRY POSITIONS
    ↓
RECONCILE (classify every position)
    ↓
HANDLE ORPHANS (per policy)
    ↓
VERIFY SAFE STATE
    ↓
ALLOW NORMAL TRADING
```

Normal trading MUST NOT begin before reconciliation completes.

---

## 3. Position Classification

| Category | Broker | Registry | Severity | Action |
|----------|--------|----------|----------|--------|
| MATCHED | ✅ | ✅ | OK | Verify state matches |
| BROKER_ORPHAN | ✅ | ❌ | CRITICAL | Per policy (HALT/CLOSE) |
| INTERNAL_GHOST | ❌ | ✅ | WARNING | Finalize in registry |
| STATE_MISMATCH | ✅ | ✅ | CRITICAL | HALT — auto-repair unsafe |

---

## 4. Orphan Policy

```python
class OrphanPositionPolicy(Enum):
    HALT = "HALT"   # Default: stop trading, require manual intervention
    CLOSE = "CLOSE" # Explicit: close orphan, re-verify, continue
```

**Default: HALT** — safest behavior, no automatic position closure.

---

## 5. Internal Ghost Handling

When registry has a position not at broker:
1. Detect during reconciliation
2. Log WARNING with trade_id
3. Record reconciliation event
4. Continue (ghosts don't block trading)

Ghosts indicate the position was closed while offline (SL/TP hit, manual closure, etc.).

---

## 6. State Mismatch Handling

When both broker and registry have a position but state differs:
1. Log CRITICAL with mismatch details
2. Enter SAFE_HALTED state
3. Do NOT auto-repair

Reason: State mismatch may indicate external intervention or failed modification. Automatic repair could mask real issues.

---

## 7. Runtime Safety State Machine

```python
class RuntimeState(Enum):
    IDLE = "idle"
    RECONCILING = "reconciling"    # NEW
    RUNNING = "running"
    SAFE_HALTED = "safe_halted"    # NEW
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
```

`_process_pair()` blocks signal processing when `state == SAFE_HALTED`.

---

## 8. Contracts Added

- `OrphanPositionPolicy` — enum for orphan handling policy
- `StartupReconciliationResult` — structured result with classification counts
- `ExitReason.RECONCILIATION_GHOST` — exit reason for ghost-reconciled positions

---

## 9. Test Inventory

```
tests/test_startup_reconciliation.py     18 passed

TestCleanStartupReconciliation           3 tests
  test_clean_startup_no_positions
  test_clean_startup_dry_run_with_empty_registry
  test_dry_run_ghost_positions_cleaned

TestBrokerOrphanDetection                3 tests
  test_broker_orphan_halts_runtime
  test_broker_orphan_multiple_halt
  test_orphan_detected_even_with_active_registry

TestClosePolicy                          2 tests
  test_close_policy_closes_orphan
  test_close_policy_failure_leaves_halted

TestInternalGhostRecovery                2 tests
  test_internal_ghost_is_reconciled
  test_multiple_ghosts_detected

TestStateMismatchDetection               3 tests
  test_stop_loss_mismatch_halts_runtime
  test_direction_mismatch_halts_runtime
  test_matching_state_is_ok

TestRuntimeStateMachine                  3 tests
  test_reconcile_sets_reconciling_state
  test_safe_halted_state_blocks_processing
  test_halted_state_prevents_start

TestReconciliationResult                 2 tests
  test_result_has_all_fields
  test_result_to_dict
```

---

## 10. Test Results

```
94 passed (all S8.6 lifecycle tests)
```

Full suite:
- test_startup_reconciliation.py: 18
- test_mt5_adapter_modification.py: 8
- test_fill_aware_geometry.py: 12
- test_e2e_runtime_replay.py: 4
- test_lifecycle_integration.py: 23
- test_trade_management_parity.py: 29

---

## 11. Remaining Production Gaps

| Gap | Priority | Status |
|-----|----------|--------|
| Startup reconciliation | HIGH | ✅ This task |
| Runtime state gating | HIGH | ✅ This task |
| SL modification retry | MEDIUM | Not implemented |
| Circuit breaker feedback | LOW | Out of scope |
| Priority exit during halt | LOW | Gap identified |

---

## 12. Gate Decision

**🟢 GREEN for S8.6.11**

All criteria met:
- ✅ Startup reconciliation mandatory
- ✅ Broker orphans detected
- ✅ Internal ghosts reconciled
- ✅ State mismatches detected
- ✅ Unsafe state blocks trading
- ✅ SAFE_HALTED prevents new orders
- ✅ Explicit orphan policy implemented
- ✅ Full test suite passing (94/94)

---

## 13. Files Modified

- `execution/s8_runtime.py` — RuntimeState, reconcile_startup_state(), _process_pair() guard, start() reconciliation
- `strategy/lifecycle/contracts.py` — OrphanPositionPolicy, StartupReconciliationResult, ExitReason.RECONCILIATION_GHOST
- `strategy/lifecycle/__init__.py` — exports
- `tests/test_startup_reconciliation.py` — 18 new tests

All reports copied to `/sdcard/`.
