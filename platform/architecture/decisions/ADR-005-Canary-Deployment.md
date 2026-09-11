# ADR-005: Canary Deployment

> **Status:** Accepted
> **Date:** 2026-09-11

---

## Context

A strategy that passes demo validation may still fail in live trading due to execution differences, slippage, or market impact. Promoting directly to full production is risky.

## Decision

New strategies enter canary deployment with limited allocation, strict health criteria, and automatic rollback. Only after sustained canary health may allocation expand.

## Consequences

- Live trading risk is bounded during initial deployment
- Automatic rollback prevents catastrophic losses
- Evidence is preserved for investigation
- The canary failure does not affect BLUE

## Compliance

This ADR is enforced by:
- `platform/deployment/CANARY_ROLLBACK_POLICY.md`
- `platform/governance/PROMOTION_POLICY.md`
- Automated health monitoring
