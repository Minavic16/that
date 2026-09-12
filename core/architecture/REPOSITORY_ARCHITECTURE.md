# Repository Architecture

> **NestQuant Repository Structure Specification**
> **Status:** Authoritative
> **Last Updated:** 2026-09-11

---

## 1. Top-Level Structure

The NestQuant repository contains exactly five top-level application directories plus root-level metadata:

```
NestQuant/
├── production/       ← Runtime trading system
├── research/         ← Active and proposed research
├── archive/          ← Historical, legacy, deprecated code
├── platform/         ← Shared infrastructure, governance, contracts
├── tests/            ← All test code
├── AGENTS.md         ← Engineering constitution
├── CONTRIBUTING.md   ← Contributor guide
├── .gitignore
├── pyproject.toml
├── .env.example
└── .env.telegram
```

No additional top-level application or source code directories are permitted. New functionality MUST be placed within one of the five architectural directories.

---

## 2. production/

### Purpose
Contains all code that executes in the live trading runtime. This is the only directory tree that may participate in live order submission, position management, risk enforcement, or real-time monitoring.

### Allowed Contents
- `strategies/` — Canonical strategy implementations (signal generation, lifecycle, trade management)
- `risk/` — Risk management, circuit breakers
- `execution/` — Execution adapters, MT5 bridge, orchestration, shadow pipeline
- `monitoring/` — Observability, metrics collection, dashboard server
- `notifications/` — Alert pipeline (Telegram, log channels)
- `api/` — Dashboard application (Next.js), mobile app
- `deployment/` — Service files, deployment scripts, operational tooling

### Forbidden Contents
- Research experiments
- Archived code
- Strategy proposals
- Unvalidated hypotheses
- One-time analysis scripts

### Dependency Rules
- MAY import from `platform/contracts/`
- MAY import from `platform/configuration/`
- MAY import from `platform/knowledge/`
- MAY import from `platform/tooling/`
- MUST NOT import from `research/`
- MUST NOT import from `archive/`

### Ownership
Production code is owned by the deployment operator. All changes require explicit review and approval. Production code MUST NOT be modified without verifying impact on live trading behaviour.

---

## 3. research/

### Purpose
Contains all code related to hypothesis investigation, backtesting, strategy development, and experimental analysis. Research code MUST NEVER execute in the live trading runtime.

### Internal Structure
```
research/
├── current/          ← Active research (in progress)
├── proposed/         ← Proposed but not yet started
├── experiments/      ← Completed experiments
└── shared/           ← Shared research utilities (zscore, regime, engines, indicators)
```

### Allowed Contents
- Strategy research scripts
- Backtesting engines and utilities
- Statistical analysis code
- Data acquisition and processing
- Research configuration
- Research output and figures
- Hypothesis documentation

### Forbidden Contents
- Live execution code
- Order submission code
- Risk enforcement code
- Production monitoring code
- Production notification code
- MT5 bridge adapters

### Dependency Rules
- MAY import from `platform/contracts/`
- MAY import from `platform/configuration/`
- MAY import from `platform/knowledge/`
- MAY import from `platform/tooling/`
- MUST NOT import from `production/`
- MUST NOT import from `archive/`
- Research code that is promoted to production MUST go through the strategy lifecycle gates

### Ownership
Research code is owned by the research team. Researchers MAY modify research code freely within the governance rules. Research results MUST be validated before influencing production.

---

## 4. archive/

### Purpose
Contains code that is no longer active but is preserved for historical reference, forensics, failed experiments, and institutional memory. Archived code MUST NEVER execute in the live trading runtime.

### Internal Structure
```
archive/
├── strategies/       ← Archived strategy implementations
├── research/         ← Historical research scripts and reports
├── legacy/           ← Legacy modules from earlier eras (e.g., GFT)
├── config/           ← Superseded configurations
└── deprecated/       ← Code explicitly removed from active use
```

### Allowed Contents
- Historical strategy implementations
- Failed experiment code
- Superseded configurations
- Historical reports and analyses
- Legacy modules from previous eras
- Deprecated utilities

### Forbidden Contents
- Active production code
- Active research code
- Current configuration
- Current strategy implementations

### Dependency Rules
- MUST NOT be imported by any active code
- MUST NOT be executed by production systems
- MUST NOT be executed by research systems (unless explicitly loading for historical comparison)
- Archive code MAY reference platform contracts for documentation purposes only

### Ownership
Archived code is maintained by the platform team. Changes to archive are restricted to metadata updates and documentation improvements.

---

## 5. platform/

### Purpose
Contains shared infrastructure, governance documentation, contracts, configuration, and institutional knowledge that is referenced by both production and research.

### Internal Structure
```
platform/
├── architecture/         ← Architecture documentation and ADRs
├── governance/           ← Constitution, lifecycle, policies
├── strategy_registry/    ← Strategy identity, versioning, lineage
├── contracts/            ← Data contracts, interfaces, protocols
├── configuration/        ← Settings, policies, experiment config
├── deployment/           ← Deployment documentation, runbooks
├── knowledge/            ← Lessons learned, validated decisions, research backlog
└── tooling/              ← Shared utilities, helpers
```

### Allowed Contents
- Architecture documentation
- Governance policies
- Strategy lifecycle definitions
- Data contracts and interfaces
- Configuration management
- Deployment documentation
- Institutional knowledge
- Shared utilities

### Forbidden Contents
- Live execution logic
- Research experiment code
- Archived code
- Strategy-specific implementations

### Dependency Rules
- Platform contracts MAY be imported by both production and research
- Platform configuration MAY be imported by both production and research
- Platform tooling MAY be imported by both production and research
- Platform governance documents are reference-only (not imported at runtime)
- Platform MUST NOT import from production, research, or archive

### Ownership
Platform code is owned by the platform team. Changes to contracts and configuration require cross-team review.

---

## 6. tests/

### Purpose
Contains all test code organized by the system under test.

### Internal Structure
```
tests/
├── production/     ← Tests for production systems
├── research/       ← Tests for research systems
├── platform/       ← Tests for platform utilities
├── integration/    ← Integration tests
├── parity/         ← Research↔production parity tests
└── safety/         ← Safety-critical system tests
```

### Allowed Contents
- Unit tests
- Integration tests
- Regression tests
- Smoke tests
- Causality tests
- Parity tests
- Safety verification tests

### Forbidden Contents
- Production logic (tests verify, not execute production)
- Research experiments (tests verify, not conduct research)
- Configuration files (tests reference, not define)

### Dependency Rules
- MAY import from production (for testing)
- MAY import from research (for testing)
- MAY import from platform (for testing)
- MUST NOT import from archive

### Ownership
Test code is maintained by whoever owns the code being tested.

---

## 7. Dependency Direction Summary

```
         ┌─────────────┐
         │  platform/   │
         │  contracts   │
         │  config      │
         │  knowledge   │
         │  tooling     │
         └──────┬───────┘
                │
        ┌───────┴───────┐
        │               │
   ┌────▼────┐    ┌─────▼─────┐
   │production│    │  research  │
   └────┬────┘    └─────┬─────┘
        │               │
        └───────┬───────┘
                │
         ┌──────▼───────┐
         │    tests/     │
         └──────────────┘
```

**Allowed:**
- `production` → `platform/`
- `research` → `platform/`
- `tests` → `production/`, `research/`, `platform/`

**Forbidden:**
- `production` → `research/`
- `production` → `archive/`
- `research` → `production/`
- `platform/` → `production/`
- `platform/` → `research/`
- `platform/` → `archive/`
- `archive/` → anything active

---

## 8. Strategy Promotion Relationship

A strategy flows through the architecture as follows:

```
research/current/     →  (hypothesis investigation)
        ↓
research/experiments/  →  (completed experiment evidence)
        ↓
platform/strategy_registry/  →  (identity assignment)
        ↓
production/strategies/  →  (canonical implementation)
        ↓
production/execution/  →  (runtime execution)
```

At no point does a strategy skip from research directly to production execution. Every transition requires:
1. Passing the relevant lifecycle gate
2. Strategy identity assignment
3. Implementation in production code
4. Parity validation
5. Shadow observation
6. Demo observation
7. Controlled promotion

---

*End of Repository Architecture Specification*
