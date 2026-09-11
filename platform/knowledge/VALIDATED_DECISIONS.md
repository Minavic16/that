# Validated Decisions

> **NestQuant Architecture and Strategy Decisions**
> **Status:** Active reference
> **Last Updated:** 2026-09-11

---

## 1. Validated Decisions

These decisions have been validated through implementation and testing:

### D-001: HTTP Bridge for MT5 Integration
- **Decision:** Use HTTP bridge (Flask at 127.0.0.1:5001) instead of direct MT5 SDK import
- **Evidence:** Clean separation, testable, no SDK dependency in Python
- **Date:** Pre-S7
- **Status:** VALIDATED

### D-002: Frozen Strategy Parameters via Dataclasses
- **Decision:** Use frozen dataclasses for strategy parameters, constitution, and policies
- **Evidence:** Prevents accidental mutation, type-safe, documented
- **Date:** Pre-S8
- **Status:** VALIDATED

### D-003: File-Based Kill Switch
- **Decision:** Use file-based sentinel for emergency stop
- **Evidence:** Simple, reliable, survives process restart, no network dependency
- **Date:** Pre-S7
- **Status:** VALIDATED

### D-004: Shadow Hard Guard (Zero Orders)
- **Decision:** Monkey-patch order submission to raise exception in shadow mode
- **Evidence:** Prevents accidental order submission, verifiable, auditable
- **Date:** S7
- **Status:** VALIDATED

### D-005: Constitution as Single Risk Source
- **Decision:** All risk parameters derive from `config/constitution.py`
- **Evidence:** Single source of truth, tested via constitution wiring tests
- **Date:** Pre-S8
- **Status:** VALIDATED

### D-006: Event Bus for Notifications
- **Decision:** Central event bus routes notifications through policy to channels
- **Evidence:** Decoupled, testable, channel errors don't propagate
- **Date:** Pre-S8
- **Status:** VALIDATED

### D-007: Fill-Aware Geometry
- **Decision:** Calculate SL/TP from fill price, not signal price
- **Evidence:** S8.6.7A audit validated this is essential for correct risk geometry
- **Date:** S8.6.7A
- **Status:** VALIDATED

### D-008: Startup Reconciliation
- **Decision:** Reconcile internal state with broker positions on startup
- **Evidence:** Prevents ghost positions, orphan detection, state consistency
- **Date:** S8.6.11
- **Status:** VALIDATED

### D-009: Causal Signal Generation
- **Decision:** Use only past data for signal generation (no look-ahead)
- **Evidence:** Causality tests in unit tests, smoke tests verify per-timeframe
- **Date:** Ongoing
- **Status:** VALIDATED

### D-010: Canonical Strategy Identity
- **Decision:** Maintain explicit strategy identity document as single source of truth
- **Evidence:** Prevents parameter drift, enables versioning, documents lineage
- **Date:** S8.6.3
- **STATUS:** VALIDATED

---

## 2. Provisional Decisions

These decisions are implemented but not yet fully validated:

### D-P001: Circuit Breaker Thresholds
- **Decision:** WinRateBreaker at 40%/45%, DrawdownPaceBreaker at 6%/9%, etc.
- **Evidence:** Calibration analysis performed, but limited live data
- **Date:** S8.6.1
- **Status:** PROVISIONAL — requires more live observation

### D-P002: Monitoring Percentile Thresholds
- **Decision:** NORMAL/ELEVATED/WARNING/EXTREME thresholds
- **Evidence:** Statistical calibration with limited sample sizes
- **Date:** S8.6.1
- **Status:** PROVISIONAL — requires more live data

### D-P003: Prop Firm Guard Parameters
- **Decision:** Max daily loss $600, max drawdown $1,600, etc.
- **Evidence:** Derived from constitution percentages, but not yet validated with live prop firm data
- **Date:** S8
- **Status:** PROVISIONAL — requires live prop firm validation

---

## 3. Rejected Decisions

### D-R001: Direct MT5 SDK Import
- **Decision:** rejected
- **Reason:** SDK dependency makes testing difficult, creates platform coupling
- **Evidence:** HTTP bridge approach is cleaner and more testable
- **Status:** REJECTED

### D-R002: Automatic Strategy Promotion
- **Decision:** Auto-promote strategy when backtest passes thresholds
- **Reason:** No single metric is sufficient evidence for live deployment
- **Evidence:** Multiple validation stages exist because each catches different failure modes
- **Status:** REJECTED

### D-R003: Zero Transaction Cost Assumption
- **Decision:** Assume zero costs in backtest
- **Reason:** Unrealistic, hides execution friction
- **Evidence:** Cost sensitivity analysis shows edge can disappear under realistic costs
- **Status:** REJECTED

---

*End of Validated Decisions*
