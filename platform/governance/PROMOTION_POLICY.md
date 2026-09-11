# Promotion Policy

> **NestQuant Strategy Promotion Gates**
> **Status:** Mandatory
> **Last Updated:** 2026-09-11

---

## 1. Principle

A strategy MUST pass through defined promotion gates before advancing to each lifecycle stage. No gate may be skipped. No automatic promotion is permitted. Explicit human approval is required at critical transitions.

---

## 2. Promotion Gates

### Gate 1: Research Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Idea accepted for investigation |
| Evidence | Written hypothesis, methodology, success criteria |
| Tests | None required (investigation phase) |
| Approval | Research lead |
| Failure | Archive with reason |

### Gate 2: Backtest Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Research shows promising signals |
| Evidence | Complete backtest with trade log, equity curve, per-period metrics |
| Tests | Backtest passes basic sanity checks |
| Approval | Automated thresholds + researcher review |
| Failure | Document and archive |

**Minimum Thresholds:**
- Profit factor > 1.0
- Positive expectancy after costs
- Minimum 100 trades
- No single instrument contributing > 50% of P&L

### Gate 3: Cost Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Backtest shows gross edge |
| Evidence | Cost sensitivity analysis, break-even analysis |
| Tests | Cost model validation |
| Approval | Researcher review |
| Failure | Document cost sensitivity and archive |

### Gate 4: Robustness Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Edge survives costs |
| Evidence | Parameter sensitivity, bootstrap CI, regime analysis |
| Tests | Robustness tests pass |
| Approval | Researcher review |
| Failure | Document fragility and archive |

### Gate 5: Out-of-Sample Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Robustness validated |
| Evidence | OOS results, degradation assessment |
| Tests | OOS performance positive, statistically significant |
| Approval | Researcher review |
| Failure | Document OOS failure and archive |

### Gate 6: Walk-Forward / Stress Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | OOS validated |
| Evidence | Walk-forward windows, stress test results |
| Tests | Edge persists across windows |
| Approval | Researcher review |
| Failure | Document temporal instability and archive |

### Gate 7: Complementarity Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Walk-forward validated |
| Evidence | Full complementarity analysis per COMPLEMENTARITY_POLICY.md |
| Tests | Portfolio-level metrics improve |
| Approval | Research lead + risk review |
| Failure | Document non-complementarity; may hold for future reassessment |

### Gate 8: Implementation Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Complementarity validated, identity assigned |
| Evidence | Production code, unit tests, integration plan |
| Tests | All new tests pass |
| Approval | Code review |
| Failure | Fix implementation or return to research |

### Gate 9: Parity Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Production implementation complete |
| Evidence | Parity test results |
| Tests | 100% signal match on identical data |
| Approval | Automated parity tests + review |
| Failure | Investigate and fix; may require return to implementation |

### Gate 10: Shadow Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Parity validated |
| Evidence | Shadow observation period, signal fidelity |
| Tests | Shadow matches expected behaviour, zero orders verified |
| Approval | Automated shadow fidelity + review |
| Failure | Investigate; may require return to implementation |

### Gate 11: Demo Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Shadow observation sufficient |
| Evidence | Demo execution quality, slippage, fills |
| Tests | Demo matches shadow, risk controls function |
| Approval | Demo observation review |
| Failure | Investigate execution quality; may return to shadow |

### Gate 12: Canary Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Demo validated |
| Evidence | Canary deployment plan, health criteria, rollback plan |
| Tests | Canary health criteria met |
| Approval | Deployment governance + risk review |
| Failure | Automatic rollback if health criteria breached |

### Gate 13: Production Promotion Gate

| Aspect | Requirement |
|--------|-------------|
| Entry | Canary passed, controlled live sufficient |
| Evidence | Complete lifecycle evidence package |
| Tests | All promotion criteria met |
| Approval | **Explicit human approval required** |
| Failure | Maintain current status, document reason |

---

## 3. Approval Authority

| Gate | Minimum Approval |
|------|-----------------|
| Research gates (1-7) | Research lead |
| Implementation gate (8) | Code reviewer |
| Parity gate (9) | Automated + reviewer |
| Shadow gate (10) | Automated + reviewer |
| Demo gate (11) | Operator review |
| Canary gate (12) | Deployment governance + risk |
| Production promotion (13) | **Explicit human approval** |

---

## 4. Rejection

At any gate, a strategy may be rejected. When rejected:
1. Record the gate at which rejection occurred
2. Record the evidence that led to rejection
3. Record the specific failure criteria that were triggered
4. Archive the research with full lineage
5. Record whether the approach may be reconsidered

---

## 5. No Automatic Self-Promotion

A strategy MUST NOT automatically advance from one gate to the next. Every transition requires:
1. Evidence package completion
2. Review (human or automated with human oversight)
3. Explicit approval decision
4. Documentation of the transition

---

*End of Promotion Policy*
