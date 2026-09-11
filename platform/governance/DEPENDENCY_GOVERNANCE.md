# Dependency Governance

> **NestQuant Dependency Direction Policy**
> **Status:** Mandatory
> **Last Updated:** 2026-09-11

---

## 1. Principle

The dependency graph MUST enforce clear boundaries between production, research, and archive. This prevents accidental contamination of live trading systems with unvalidated code.

---

## 2. Dependency Categories

### 2.1 Source Dependency
A source dependency exists when module A imports module B at the Python level. This is the primary dependency type governed by this document.

### 2.2 Runtime Dependency
A runtime dependency exists when module A depends on module B at execution time (e.g., through configuration files, database connections, or network services). Runtime dependencies MUST follow the same rules as source dependencies.

### 2.3 Test Dependency
A test dependency exists when test code imports module under test. Tests MAY import from production, research, and platform for the purpose of verification.

### 2.4 Research Dependency
A research dependency exists when research code imports from platform contracts or configuration for the purpose of hypothesis investigation. Research MUST NOT depend on production runtime code.

---

## 3. Allowed Dependencies

### 3.1 Production Dependencies

| Source | Target | Condition |
|--------|--------|-----------|
| `production/*` | `platform/contracts/` | Always permitted |
| `production/*` | `platform/configuration/` | Always permitted |
| `production/*` | `platform/knowledge/` | Read-only, metadata only |
| `production/*` | `platform/tooling/` | Always permitted |
| `production/*` | `production/*` | Internal production imports permitted |

### 3.2 Research Dependencies

| Source | Target | Condition |
|--------|--------|-----------|
| `research/*` | `platform/contracts/` | Always permitted |
| `research/*` | `platform/configuration/` | Always permitted |
| `research/*` | `platform/knowledge/` | Read-only |
| `research/*` | `platform/tooling/` | Always permitted |
| `research/*` | `research/*` | Internal research imports permitted |

### 3.3 Test Dependencies

| Source | Target | Condition |
|--------|--------|-----------|
| `tests/*` | `production/*` | For testing only |
| `tests/*` | `research/*` | For testing only |
| `tests/*` | `platform/*` | For testing only |

### 3.4 Platform Dependencies

| Source | Target | Condition |
|--------|--------|-----------|
| `platform/*` | Nothing external | Platform is the dependency root |

---

## 4. Forbidden Dependencies

### 4.1 Production → Research

Production code MUST NOT import from `research/` under any circumstances.

**Rationale:** Research code is unvalidated, may contain experimental logic, and could introduce unpredictable behaviour into live trading.

**Exception:** None. If a research result is valuable enough for production, it MUST go through the strategy lifecycle and be implemented in `production/strategies/`.

### 4.2 Production → Archive

Production code MUST NOT import from `archive/` under any circumstances.

**Rationale:** Archived code is preserved for historical reference only. It may contain superseded logic, deprecated patterns, or known defects.

### 4.3 Platform Core → Research

Platform contracts, configuration, and governance MUST NOT import from `research/`.

**Rationale:** Platform is the shared foundation. If platform depends on research, then production transitively depends on research, violating the fundamental boundary.

### 4.4 Platform Core → Archive

Platform contracts, configuration, and governance MUST NOT import from `archive/`.

**Rationale:** Archive is terminal. Nothing active should depend on archived code.

### 4.5 Active Runtime → Archive

No active runtime code (production or research) may import from `archive/`.

**Rationale:** Archive is for reference only. Executing archived code creates untracked behaviour.

---

## 5. Import Verification

### 5.1 Automated Checks

Tests MUST verify forbidden import boundaries:
- `test_execution_contracts.py` verifies production contracts do not import research
- `test_mt5_adapter.py` verifies MT5 adapters do not import research
- `test_mt5_client.py` verifies MT5 clients do not import forbidden dependencies

### 5.2 Manual Review

Pull requests that modify import statements in production code MUST be reviewed for dependency boundary compliance.

### 5.3 Migration Verification

After any repository reorganization, the full import dependency graph MUST be verified:
1. No production code imports from research
2. No production code imports from archive
3. No platform code imports from research or archive
4. All test imports are valid

---

## 6. Promotion Boundary

When code moves from research to production, it MUST:

1. Be validated through the strategy lifecycle
2. Be assigned a strategy identity
3. Be implemented as new code in `production/strategies/`
4. Pass parity validation against the research implementation
5. NOT be a direct import of research code into production

The promotion boundary exists because research code may contain:
- Experimental parameters
- Unvalidated assumptions
- Debugging artefacts
- Non-deterministic behaviour
- Performance issues

Production implementations MUST be clean, validated, purpose-built code.

---

## 7. Configuration Dependencies

Configuration files may be shared between production and research through `platform/configuration/`. However:

- Production runtime configuration MUST be in `platform/configuration/` or `production/deployment/`
- Research configuration MAY reference platform configuration
- Research MUST NOT modify production configuration at runtime
- Configuration changes that affect production MUST go through the deployment policy

---

## 8. Third-Party Dependencies

Third-party library dependencies MUST be:
- Documented in `pyproject.toml`
- Pinned to specific versions where stability is critical
- Reviewed for security and maintenance status
- Justified for each architectural layer

Production MUST NOT introduce new third-party dependencies without:
1. Security review
2. Maintenance assessment
3. Dependency count justification
4. Cross-team approval

---

*End of Dependency Governance*
