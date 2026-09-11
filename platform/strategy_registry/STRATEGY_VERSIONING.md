# Strategy Versioning

> **NestQuant Strategy Identity and Versioning Policy**
> **Status:** Mandatory
> **Last Updated:** 2026-09-11

---

## 1. Principle

Every strategy deployed in NestQuant MUST have a unique, immutable identity. A material strategy modification MUST create a new version. A promoted version MUST NEVER be silently mutated.

---

## 2. Strategy Identity Format

```
NQ-{STRATEGY_TYPE}-{VERSION}
```

### Components

| Component | Description | Examples |
|-----------|-------------|----------|
| `NQ` | NestQuant prefix | Always `NQ` |
| `STRATEGY_TYPE` | Strategy family identifier | `BREAKOUT`, `MR`, `STATARB`, `MOMENTUM` |
| `VERSION` | Sequential version number | `V1`, `V2`, `V3` |

### Examples

| Strategy ID | Description |
|-------------|-------------|
| `NQ-BREAKOUT-V1` | First breakout strategy (canonical) |
| `NQ-BREAKOUT-V2` | Second breakout variant (future) |
| `NQ-MR-V1` | First mean reversion strategy (future) |
| `NQ-STATARB-V1` | First statistical arbitrage strategy (future) |

---

## 3. Strategy Identity Record

Each strategy version MUST have an identity record containing:

### 3.1 Identity Fields

| Field | Description | Example |
|-------|-------------|---------|
| `strategy_id` | Unique identifier | `NQ-BREAKOUT-V1` |
| `version` | Version number | `V1` |
| `strategy_family` | Strategy type | `BREAKOUT` |
| `timeframe` | Primary timeframe | `4H` |
| `signal_parameters` | Signal generation parameters | See NQ-BREAKOUT-V1.md |
| `lifecycle_parameters` | Trade lifecycle parameters | See NQ-BREAKOUT-V1.md |
| `risk_contract` | Risk parameters | See constitution |
| `data_requirements` | Required data | OHLCV 4H, 28 FX pairs |
| `research_lineage` | Research origin | Phase S0-S6 |
| `source_commit` | Git commit at identity assignment | `e706995` |
| `validation_status` | Current validation state | `DEMO_OBSERVATION` |
| `deployment_status` | Current deployment state | `SHADOW` |
| `promotion_history` | Record of promotions | `PROPOSED → CURRENT → ...` |

### 3.2 Separation of Concerns

The strategy identity clearly separates:

| Aspect | Location | Mutability |
|--------|----------|------------|
| Identity (what it is) | `platform/strategy_registry/` | Immutable after promotion |
| Implementation (how it works) | `production/strategies/` | Version-specific, frozen |
| Runtime configuration | `platform/configuration/` | May be adjusted with approval |
| Deployment configuration | `production/deployment/` | May be adjusted with approval |

---

## 4. Version Immutability Rules

### 4.1 Before Promotion

Before a strategy is promoted to production, its parameters MAY be adjusted during research. Each adjustment MUST be recorded.

### 4.2 After Promotion

After a strategy is promoted to production:

- Its identity record MUST NOT be modified
- Its signal parameters MUST NOT be modified
- Its lifecycle parameters MUST NOT be modified
- Its risk contract MUST NOT be modified

### 4.3 Material Changes

A material change is any change that would produce different trading signals or different trade management behaviour on identical market data.

Material changes include:
- Signal parameter changes (lookback, ATR period, SL multiplier, RRR)
- Lifecycle parameter changes (breakeven ratio, max hold, trailing method)
- Risk parameter changes (risk per trade, position limits, drawdown limits)
- Direction logic changes (BUY/SELL symmetry)
- Filter additions or removals
- Session logic changes
- Regime logic changes

Non-material changes include:
- Code refactoring that preserves identical behaviour
- Performance optimization that preserves identical results
- Bug fixes that correct unintended deviations from the specification
- Documentation updates

### 4.4 Material Change Procedure

When a material change is needed:

1. Create a new strategy version (e.g., `NQ-BREAKOUT-V2`)
2. Assign a new identity record
3. Implement the new version alongside the existing version
4. Follow the full lifecycle for the new version
5. The old version remains in its current deployment state
6. The new version starts from the appropriate lifecycle stage

---

## 5. Version Lifecycle States

| State | Description |
|-------|-------------|
| `PROPOSED` | Identity assigned, not yet implemented |
| `IMPLEMENTED` | Code exists in production |
| `PARITY_VALIDATED` | Implementation matches research |
| `SHADOW` | Running in shadow mode |
| `DEMO` | Running on demo account |
| `CANARY` | Limited live allocation |
| `CONTROLLED_LIVE` | Gradually expanding allocation |
| `PRODUCTION` | Full production deployment |
| `FROZEN` | No longer actively developed, stable |
| `ARCHIVED` | Retired from active use |
| `REJECTED` | Failed validation, archived with reason |

---

## 6. Multiple Concurrent Versions

Multiple strategy versions MAY coexist in production simultaneously, subject to:
- Portfolio-level risk limits
- Complementarity validation
- Deployment governance approval
- Total exposure limits

---

## 7. Strategy Family

A strategy family groups related versions:

```
NQ-BREAKOUT
├── NQ-BREAKOUT-V1  (canonical, frozen)
├── NQ-BREAKOUT-V2  (future candidate)
└── NQ-BREAKOUT-V3  (future candidate)
```

The family identifier MUST be stable across versions. The family name describes the core approach, not specific parameters.

---

*End of Strategy Versioning*
