# ADR-001: Repository Boundaries

> **Status:** Accepted
> **Date:** 2026-09-11

---

## Context

The NestQuant repository contains production trading code, research experiments, archived historical code, shared platform infrastructure, and tests. Without explicit boundaries, contributors may accidentally modify production code, introduce research experiments into live trading, or execute archived code.

## Decision

The repository is divided into exactly five top-level directories:

1. `production/` — Runtime trading system
2. `research/` — Hypothesis investigation
3. `archive/` — Historical/legacy code
4. `platform/` — Shared infrastructure, governance, contracts
5. `tests/` — Test code

No additional top-level application directories are permitted.

## Consequences

- Contributors immediately understand what is production vs research vs archived
- Dependency rules can be enforced at the directory level
- Safety boundaries are explicit and auditable
- New functionality must be classified before implementation

## Compliance

This ADR is enforced by:
- `platform/governance/DEPENDENCY_GOVERNANCE.md`
- Import verification tests
- Code review processes
