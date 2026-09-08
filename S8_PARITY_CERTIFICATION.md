# S8.6 — Consolidated Research-to-Production Parity Certification

**Date:** 2026-09-04
**Status:** Complete
**Certification:** Three-tier gate applied

---

## Canonical Parity Matrix

### Strategy Lineage

| Component | Research Spec | Production Spec | Status |
|-----------|--------------|-----------------|--------|
| Signal trigger | breakout | breakout | ✅ |
| Signal level | swing high/low | swing high/low | ✅ |
| Lookback | 5 | 5 | ✅ |
| ATR period | 14 | 14 | ✅ |
| ATR SL multiplier | 2.0 | 2.0 | ✅ |
| RRR | 3.5 | 3.5 | ✅ |
| Timeframe | 4h | H4 | ✅ |

### Lifecycle Management

| Component | Research Spec | Production Spec | Status |
|-----------|--------------|-----------------|--------|
| SL → TP → MH ordering | SL first | SL first | ✅ |
| Breakeven trigger | 0.8R from entry | 0.8R from fill | ✅ |
| Trailing reference | previous swing | previous swing | ✅ |
| Trailing before BE | yes | yes | ✅ |
| Max hold | 42 bars (7×6) | 42 bars (7×6) | ✅ |
| Max hold exit | close | close | ✅ |

### Execution Geometry

| Component | Research Spec | Production Spec | Status |
|-----------|--------------|-----------------|--------|
| Entry reference | next bar open | actual broker fill | ✅ Equivalent |
| SL anchor | execution price | fill price | ✅ |
| TP anchor | execution price | fill price | ✅ |
| Risk formula | pnl_pips / risk_pips | pnl_pips / risk_pips | ✅ |
| Risk immutability | fixed after entry | fixed after entry | ✅ |

### Runtime Integration

| Component | Research Spec | Production Spec | Status |
|-----------|--------------|-----------------|--------|
| Lifecycle wired | evaluate on bar close | evaluate on bar close | ✅ |
| Swing data provided | previous bar | previous bar | ✅ |
| Fill-aware geometry | N/A | TradeGeometry.from_fill() | ✅ |
| Risk reconciliation | N/A | expected vs actual | ✅ |

### Production Safety

| Component | Status | Notes |
|-----------|--------|-------|
| Startup reconciliation | ✅ | Mandatory before trading |
| Broker orphan detection | ✅ | HALT or CLOSE policy |
| Internal ghost recovery | ✅ | Finalized, audit trail |
| State mismatch detection | ✅ | CRITICAL → SAFE_HALTED |
| Runtime state gating | ✅ | SAFE_HALTED blocks orders |
| SL modification adapter | ✅ | MT5 adapter + mock tests |
| Periodic reconciliation | ✅ | SL mismatch detection |

---

## Three-Tier Gate Model

### Strategy Lineage Parity — 🟢 GREEN

All strategy parameters, signal logic, lifecycle ordering, breakeven, trailing, max hold, fill-aware geometry, and R calculation match the research model.

**Evidence:**
- Forensic spec (S8.6.4)
- 29 parity tests (S8.6.4)
- 23 lifecycle tests (S8.6.5)
- 12 fill-aware geometry tests (S8.6.7.B)
- Shifted-fill replay proving 5-pip deviation propagates correctly

### Runtime Integration Parity — 🟢 GREEN

Dry-run runtime integration is complete. All lifecycle paths execute through the actual S8Runtime. MT5 adapter modification tested with mocked client.

**Evidence:**
- 4 E2E runtime replay tests (S8.6.7)
- 8 mocked MT5 modification tests (S8.6.8)
- 18 startup reconciliation tests (S8.6.11)
- Reconciliation implemented and tested (S8.6.9)

### Production Execution Readiness — 🟡 CONDITIONAL GREEN

Infrastructure gaps remain:
- SL modification retry not implemented (MEDIUM priority)
- Circuit breaker feedback not wired (LOW priority)
- Priority exit during halt not implemented (LOW priority)

**Evidence:**
- S8.6.10 Execution Failure Audit
- S8.6.11 Startup Reconciliation

---

## Test Inventory

```
tests/test_trade_management_parity.py      29 passed  (S8.6.4)
tests/test_lifecycle_integration.py        23 passed  (S8.6.5)
tests/test_e2e_runtime_replay.py            4 passed  (S8.6.7)
tests/test_fill_aware_geometry.py          12 passed  (S8.6.7.B)
tests/test_mt5_adapter_modification.py      8 passed  (S8.6.8)
tests/test_startup_reconciliation.py       18 passed  (S8.6.11)
                                           ──────
Total (S8.6 series)                        94 passed
```

---

## File Inventory

### Created (S8.6.4-11)
- `strategy/trade_management/breakeven.py`
- `strategy/trade_management/max_hold.py`
- `strategy/trade_management/trailing_stop.py`
- `strategy/trade_management/manager.py`
- `strategy/lifecycle/contracts.py`
- `strategy/lifecycle/registry.py`
- `tests/test_trade_management_parity.py`
- `tests/test_lifecycle_integration.py`
- `tests/test_e2e_runtime_replay.py`
- `tests/test_fill_aware_geometry.py`
- `tests/test_mt5_adapter_modification.py`
- `tests/test_startup_reconciliation.py`

### Modified (S8.6.4-11)
- `config/experiment.py` — StrategyIdentity parameters
- `execution/s8_runtime.py` — LifecycleRegistry, fill-aware geometry, reconciliation, startup reconciliation, RuntimeState
- `execution/adapter.py` — modify_position_stop() base + fake
- `execution/mt5_client.py` — modify_position()
- `execution/mt5_adapter.py` — modify_position_stop()
- `strategy/lifecycle/contracts.py` — TradeGeometry, RiskReconciliation, OrphanPositionPolicy, StartupReconciliationResult
- `strategy/lifecycle/__init__.py` — exports

### Reports
- `S8_6_4_STRATEGY_FORENSIC_SPEC.md`
- `S8_6_4_STRATEGY_RECONCILIATION_REPORT.md`
- `S8_6_5_LIFECYCLE_INTEGRATION_REPORT.md`
- `S8_6_6_RUNTIME_PARITY_AUDIT.md`
- `S8_6_6A_ENTRY_SEMANTICS.md`
- `S8_6_7_RUNTIME_LIFECYCLE_INTEGRATION_REPORT.md`
- `S8_6_7A_ENTRY_RISK_GEOMETRY_AUDIT.md`
- `S8_6_7B_FILL_AWARE_GEOMETRY_REPORT.md`
- `S8_6_8_LIVE_ADAPTER_REPORT.md`
- `S8_6_9_RECONCILIATION_BROKER_STATE.md`
- `S8_6_10_EXECUTION_FAILURE_AUDIT.md`
- `S8_6_11_STARTUP_RECONCILIATION_REPORT.md`
- `S8_PARITY_CERTIFICATION.md`

---

## Remaining Work

| Item | Priority | Phase |
|------|----------|-------|
| SL modification retry | MEDIUM | S8.6.12 |
| Circuit breaker trade feedback | LOW | S8.7+ |
| Priority exit during halt | LOW | S8.7+ |
| Demo-account live validation | HIGH | S8.7 |

---

## Gate Summary

| Gate | Status |
|------|--------|
| Strategy Lineage Parity | 🟢 GREEN |
| Runtime Integration Parity | 🟢 GREEN |
| Production Execution Readiness | 🟡 CONDITIONAL GREEN |
