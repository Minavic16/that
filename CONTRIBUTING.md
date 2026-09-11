# Contributing to NestQuant

> **Contributor Guide**
> **Last Updated:** 2026-09-11

---

## 1. Repository Structure

NestQuant is organized into five top-level directories:

| Directory | Purpose | Who Modifies |
|-----------|---------|--------------|
| `production/` | Live trading system | Deployment operator (with approval) |
| `research/` | Hypothesis investigation | Researchers |
| `archive/` | Historical/legacy code | Platform team (metadata only) |
| `platform/` | Shared infrastructure | Platform team |
| `tests/` | Test code | Anyone (matching ownership) |

---

## 2. Where Things Go

### "I have an idea"
→ Create a proposal in `research/proposed/`

### "I am testing a hypothesis"
→ Work in `research/current/` or `research/experiments/`

### "I have validated a candidate"
→ Submit a strategy registry proposal in `platform/strategy_registry/`

### "I want to change V1"
→ You CANNOT modify V1 directly. Create a new version (V2) following the strategy lifecycle.

### "I found old code"
→ Assess whether it belongs in `archive/`. Do not delete it.

### "I want production access"
→ Follow the promotion process. No shortcut exists.

---

## 3. Strategy Versioning

Every strategy has a unique identity: `NQ-{TYPE}-{VERSION}`

Examples:
- `NQ-BREAKOUT-V1` (current canonical, frozen)
- `NQ-BREAKOUT-V2` (future breakout variant)
- `NQ-MR-V1` (future mean reversion)

A material change to a strategy MUST create a new version. See `platform/strategy_registry/STRATEGY_VERSIONING.md`.

---

## 4. Dependency Rules

**Production code MUST NOT import from research or archive.**
**Research code MUST NOT import from production.**
**Archive code MUST NOT be imported by anything active.**

Both production and research MAY import from `platform/` (contracts, configuration, tooling).

See `platform/governance/DEPENDENCY_GOVERNANCE.md`.

---

## 5. Testing Requirements

Every meaningful change MUST be accompanied by tests:

| Change Type | Required Tests |
|-------------|---------------|
| New strategy logic | Unit tests + parity tests |
| Risk logic change | Safety tests + unit tests |
| Execution change | Integration tests + safety tests |
| Research experiment | Causality tests + regression tests |
| Platform change | Unit tests + integration tests |

See `docs/TEST_STRUCTURE.md` for test organization.

---

## 6. Commit Expectations

Commit messages MUST follow conventional format:

```
type(scope): description
```

Types:
- `feat` — New feature
- `fix` — Bug fix
- `docs` — Documentation
- `test` — Tests
- `chore` — Maintenance
- `refactor` — Code refactoring (behaviour preserved)

Scopes:
- `strategy` — Strategy logic
- `execution` — Execution system
- `risk` — Risk management
- `monitoring` — Monitoring system
- `platform` — Platform infrastructure
- `research` — Research code
- `dashboard` — Dashboard application

Examples:
- `feat(strategy): implement trailing stop for V1`
- `docs(strategy): establish NQ-BREAKOUT-V1 canonical identity`
- `test(risk): verify constitution wiring`

---

## 7. Pull Request Expectations

Every PR MUST:
1. Have a clear description of what changed and why
2. Include tests for new functionality
3. Pass all existing tests
4. Not violate dependency rules
5. Not modify frozen strategy parameters
6. Not modify risk constitution
7. Not modify production safety systems

---

## 8. Safety Restrictions

The following are NEVER permitted without explicit approval:

| Action | Required Approval |
|--------|------------------|
| Modify V1 parameters | Strategy lifecycle gates |
| Modify risk constitution | Governance review |
| Modify kill switch | Safety review |
| Modify circuit breakers | Safety review |
| Enable live trading | Deployment governance |
| Modify MT5 integration | Operations review |
| Modify dashboard auth | Security review |

---

## 9. Getting Started

1. Read `AGENTS.md` (the engineering constitution)
2. Read this document (`CONTRIBUTING.md`)
3. Read `platform/architecture/REPOSITORY_ARCHITECTURE.md`
4. Read `platform/governance/STRATEGY_LIFECYCLE.md`
5. Explore the codebase structure
6. Check `platform/knowledge/RESEARCH_BACKLOG.md` for current research opportunities
7. Start with research code — production requires proven track record

---

*End of Contributing Guide*
