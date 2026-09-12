# ADR-003: Research-Production Dependency Boundary

> **Status:** Accepted
> **Date:** 2026-09-11

---

## Context

Research code is unvalidated and may contain experimental logic. If production code imports from research, live trading could be affected by unvalidated code changes.

## Decision

Production code MUST NOT import from research or archive. Research code MUST NOT import from production. Both MAY import from platform (contracts, configuration, tooling).

## Consequences

- Production trading is isolated from research experiments
- Research can evolve freely without affecting production
- Platform provides the shared contract layer
- Dependencies are auditable and enforceable

## Compliance

This ADR is enforced by:
- `platform/governance/DEPENDENCY_GOVERNANCE.md`
- Forbidden import tests (`test_execution_contracts.py`, `test_mt5_adapter.py`, `test_mt5_client.py`)
- Code review processes
