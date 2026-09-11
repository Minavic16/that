# ADR-002: Strategy Version Immutability

> **Status:** Accepted
> **Date:** 2026-09-11

---

## Context

Strategy parameters can be silently modified, transforming a validated strategy into an unvalidated one. This has happened in the project's history (parameter drift between research and production).

## Decision

Every promoted strategy version is immutable. Material modifications MUST create a new version. The identity record (strategy_id, version, parameters) MUST NOT be modified after promotion.

## Consequences

- Promoted strategies cannot be accidentally or intentionally mutated
- Every material change is tracked as a new version
- Historical versions are preserved for reference
- Promotion history is auditable

## Compliance

This ADR is enforced by:
- `platform/strategy_registry/STRATEGY_VERSIONING.md`
- `platform/strategy_registry/NQ-BREAKOUT-V1.md` (frozen identity)
- `monitoring/canonical_identity.py` (runtime verification)
