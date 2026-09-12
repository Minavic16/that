# ADR-004: Blue-Green Deployment

> **Status:** Accepted
> **Date:** 2026-09-11

---

## Context

Replacing an entire trading strategy without a rollback path is risky. If the new strategy fails, there is no way to revert without taking down the system.

## Decision

NestQuant uses a blue-green deployment model. BLUE is the current trusted deployment. GREEN is the candidate. GREEN must operate independently and be rollback-capable without affecting BLUE.

## Consequences

- Failed candidates can be disabled without affecting the current production strategy
- Multiple strategies can coexist during transition
- Portfolio allocation between BLUE and GREEN is governed by risk analysis
- Rollback is always available

## Compliance

This ADR is enforced by:
- `platform/deployment/BLUE_GREEN_POLICY.md`
- `platform/deployment/CANARY_ROLLBACK_POLICY.md`
- Independent monitoring for BLUE and GREEN
