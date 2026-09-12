# ADR-006: Strategy Promotion Gates

> **Status:** Accepted
> **Date:** 2026-09-11

---

## Context

No single validation test is sufficient to prove a strategy is ready for live trading. Backtests can be overfit, OOS can fail, execution can differ from simulation, and live markets can behave differently than historical data.

## Decision

Strategies must pass through 13 defined promotion gates, each with specific evidence requirements, tests, and approval criteria. No gate may be skipped. Explicit human approval is required at critical transitions.

## Consequences

- Every strategy undergoes comprehensive validation
- No strategy can "sneak" into production
- Evidence packages are maintained for audit
- Failed strategies are documented and archived

## Compliance

This ADR is enforced by:
- `platform/governance/PROMOTION_POLICY.md`
- `platform/governance/STRATEGY_LIFECYCLE.md`
- `platform/strategy_registry/STRATEGY_REGISTRY.md`
