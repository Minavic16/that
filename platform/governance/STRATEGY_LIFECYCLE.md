# Strategy Lifecycle

> **NestQuant Strategy Development and Promotion Lifecycle**
> **Status:** Mandatory
> **Last Updated:** 2026-09-11

---

## 1. Principle

A trading strategy MUST progress through a defined lifecycle from initial idea to production deployment. No stage may be skipped. A profitable backtest alone does NOT qualify a strategy for live trading.

---

## 2. Lifecycle Stages

```
IDEA
  ↓
PROPOSED RESEARCH
  ↓
CURRENT RESEARCH
  ↓
BACKTEST
  ↓
COST MODEL
  ↓
ROBUSTNESS
  ↓
OUT-OF-SAMPLE
  ↓
WALK-FORWARD / STRESS
  ↓
COMPLEMENTARITY
  ↓
STRATEGY IDENTITY
  ↓
IMPLEMENTATION
  ↓
PARITY
  ↓
SHADOW
  ↓
DEMO
  ↓
BLUE/GREEN CANDIDATE
  ↓
CANARY
  ↓
CONTROLLED LIVE
  ↓
PROMOTION
```

---

## 3. Stage Definitions

### 3.1 IDEA

**Description:** Initial hypothesis or concept for a trading strategy.

**Entry Criteria:**
- A testable hypothesis exists
- The hypothesis has a plausible economic rationale

**Required Evidence:**
- Written hypothesis statement
- Expected relationship to existing strategies (especially V1)

**Approval:** Researcher judgement

**Failure:** Hypothesis rejected at intake → archive with reason

---

### 3.2 PROPOSED RESEARCH

**Description:** Formal research proposal with methodology and success criteria.

**Entry Criteria:**
- Idea accepted for investigation
- Research methodology defined
- Success criteria defined in advance
- Data requirements identified

**Required Evidence:**
- Research proposal document
- Defined hypothesis
- Defined methodology
- Defined success/failure criteria
- Data availability confirmed

**Approval:** Research lead review

**Failure:** Proposal rejected → archive with reason

---

### 3.3 CURRENT RESEARCH

**Description:** Active investigation and analysis.

**Entry Criteria:**
- Proposal approved
- Data acquired and validated
- Methodology implemented

**Required Evidence:**
- Working code in `research/current/`
- Data validation passed
- Initial results available

**Approval:** Ongoing research judgement

**Failure:** Early evidence contradicts hypothesis → document and archive

---

### 3.4 BACKTEST

**Description:** Historical simulation with realistic assumptions.

**Entry Criteria:**
- Research shows promising signals
- Backtest methodology defined
- Cost assumptions documented

**Required Evidence:**
- Complete backtest results
- Trade log with entries/exits
- Equity curve
- Per-period metrics (yearly, monthly)
- Per-instrument metrics
- Signal statistics (count, frequency)
- Trade statistics (count, win rate, expectancy)

**Approval:** Backtest meets minimum thresholds:
- Profit factor > 1.0
- Positive expectancy after costs
- Sufficient sample size (minimum 100 trades)
- No single instrument contributing > 50% of P&L

**Failure:** Backtest shows no edge → document and archive

---

### 3.5 COST MODEL

**Description:** Validate that the edge survives realistic transaction costs.

**Entry Criteria:**
- Backtest shows gross edge
- Cost model defined

**Required Evidence:**
- Results at multiple cost levels (break-even analysis)
- Break-even spread, commission, slippage
- Sensitivity analysis: how much cost before edge disappears
- Expected costs vs break-even costs comparison

**Approval:** Edge survives at realistic cost assumptions

**Failure:** Edge does not survive costs → document and archive

---

### 3.6 ROBUSTNESS

**Description:** Test strategy resilience to parameter variation and market conditions.

**Entry Criteria:**
- Edge survives costs
- Robustness methodology defined

**Required Evidence:**
- Parameter sensitivity analysis
- Bootstrap confidence intervals
- Monte Carlo analysis (where appropriate)
- Regime-conditional performance
- Drawdown analysis (depth, duration, recovery)
- Stability of metrics over time

**Approval:**
- Metrics stable across parameter ranges
- Confidence intervals exclude zero
- No catastrophic parameter sensitivity
- Drawdown characteristics acceptable

**Failure:** Strategy is fragile → document fragility and archive

---

### 3.7 OUT-OF-SAMPLE

**Description:** Validate on data not used in strategy development.

**Entry Criteria:**
- Strategy passes robustness
- Held-out data available

**Required Evidence:**
- Out-of-sample results
- Comparison with in-sample results
- Degradation assessment (how much worse OOS vs IS)
- Distribution of OOS performance

**Approval:**
- OOS performance is positive
- Degradation is within acceptable bounds
- OOS results are statistically distinguishable from random

**Failure:** OOS performance is negative or random → document and archive

---

### 3.8 WALK-FORWARD / STRESS

**Description:** Rolling validation and extreme scenario testing.

**Entry Criteria:**
- OOS validation passed
- Walk-forward methodology defined

**Required Evidence:**
- Walk-forward results across multiple windows
- Stress test results (crisis periods, extreme volatility)
- Temporal stability of edge
- Performance in different market regimes

**Approval:**
- Edge persists across walk-forward windows
- Stress test losses are within risk tolerance
- No structural break in edge over time

**Failure:** Edge is temporally unstable → document and archive

---

### 3.9 COMPLEMENTARITY

**Description:** Evaluate whether the candidate genuinely complements existing strategies.

**Entry Criteria:**
- Walk-forward validation passed
- Existing strategy (V1) baseline established

**Required Evidence:**
- Return correlation with V1
- Signal overlap analysis
- Directional overlap analysis
- Drawdown overlap analysis
- Regime behaviour comparison
- Marginal Sharpe analysis
- Portfolio-level backtest with V1

**Approval:**
- Candidate provides meaningful diversification
- Portfolio-level risk-adjusted metrics improve
- Candidate does not increase portfolio drawdown disproportionately

**Failure:** Candidate does not complement V1 → document and archive or hold for future reassessment

---

### 3.10 STRATEGY IDENTITY

**Description:** Assign immutable identity and formalize the strategy contract.

**Entry Criteria:**
- Complementarity validated
- Strategy parameters finalized

**Required Evidence:**
- Strategy identity assigned (e.g., `NQ-MR-V1`)
- Identity document created in `platform/strategy_registry/`
- All parameters frozen and documented
- Source commit recorded
- Validation status recorded

**Approval:** Strategy registry approval

**Failure:** Cannot define stable identity → parameter instability, return to research

---

### 3.11 IMPLEMENTATION

**Description:** Implement the strategy in production-grade code.

**Entry Criteria:**
- Strategy identity assigned
- Implementation plan defined

**Required Evidence:**
- Production code in `production/strategies/`
- Code follows NestQuant coding standards
- Unit tests for strategy logic
- Integration with lifecycle management
- Integration with risk management

**Approval:** Code review + test pass

**Failure:** Implementation does not match specification → fix or return to research

---

### 3.12 PARITY

**Description:** Verify that production implementation matches research logic.

**Entry Criteria:**
- Production implementation complete
- Research reference implementation available

**Required Evidence:**
- Parity test results (identical signals on identical data)
- Entry semantics match
- Exit semantics match
- Lifecycle behaviour matches
- Risk calculations match

**Approval:** Parity tests pass with 100% match

**Failure:** Parity mismatch → investigate and fix; may require return to implementation

---

### 3.13 SHADOW

**Description:** Run the strategy alongside the existing system without placing orders.

**Entry Criteria:**
- Parity validated
- Shadow infrastructure available

**Required Evidence:**
- Shadow signals match expected signals
- Shadow lifecycle behaviour is correct
- No order submission (hard guard verified)
- Monitoring infrastructure observes shadow correctly

**Approval:**
- Shadow runs for minimum observation period
- Signal fidelity verified
- No safety violations

**Failure:** Shadow shows unexpected behaviour → investigate and fix

---

### 3.14 DEMO

**Description:** Run the strategy on a demo/paper trading account with real market data.

**Entry Criteria:**
- Shadow validation complete
- Demo infrastructure available

**Required Evidence:**
- Demo execution matches shadow signals
- Slippage is within expected bounds
- Fill quality is acceptable
- Risk controls function correctly
- Monitoring captures demo performance

**Approval:**
- Demo runs for minimum observation period
- Execution quality acceptable
- No safety violations

**Failure:** Demo shows execution problems → investigate; may require return to shadow

---

### 3.15 BLUE/GREEN CANDIDATE

**Description:** The candidate is designated as GREEN alongside the existing BLUE.

**Entry Criteria:**
- Demo observation sufficient
- BLUE/GREEN deployment model established

**Required Evidence:**
- GREEN operates independently of BLUE
- GREEN can be disabled without affecting BLUE
- GREEN monitoring is independent
- Portfolio allocation rationale documented

**Approval:** Deployment governance review

**Failure:** GREEN cannot operate independently → return to implementation

---

### 3.16 CANARY

**Description:** Controlled rollout with limited allocation.

**Entry Criteria:**
- BLUE/GREEN candidate validated
- Canary deployment infrastructure available

**Required Evidence:**
- Canary allocation defined
- Health criteria defined
- Failure criteria defined
- Rollback procedure tested

**Approval:** Deployment governance + risk review

**Failure:** Canary fails health criteria → automatic rollback

---

### 3.17 CONTROLLED LIVE

**Description:** Gradual expansion of live allocation under monitoring.

**Entry Criteria:**
- Canary passed health criteria
- Expansion criteria defined

**Required Evidence:**
- Continued health under expanded allocation
- No degradation of portfolio-level metrics
- Risk limits not breached

**Approval:** Ongoing monitoring + risk review

**Failure:** Performance degrades → reduce allocation or rollback

---

### 3.18 PROMOTION

**Description:** Full production deployment.

**Entry Criteria:**
- Controlled live sufficient duration
- All promotion gates passed
- Explicit human approval

**Required Evidence:**
- Complete lifecycle evidence package
- Portfolio-level impact analysis
- Risk assessment
- Deployment readiness checklist

**Approval:** Explicit human approval required. No automatic promotion.

**Failure:** Promotion denied → maintain current status, document reason

---

## 4. Stage Transitions

Each stage transition MUST:
1. Be recorded in the strategy's lineage document
2. Include the evidence package
3. Include the approval decision
4. Include the Git commit hash
5. Be traceable to the responsible researcher/operator

---

## 5. Rejection at Any Stage

A strategy may be rejected at any stage. When rejected:
1. Record the reason for rejection
2. Record the evidence that led to rejection
3. Archive the research with full lineage
4. Record whether the approach may be reconsidered in the future
5. Do NOT delete the research — preserve it per AGENTS.md Section 15

---

## 6. Rollback at Any Stage

A strategy may be rolled back to a previous stage at any time. When rolling back:
1. Record the reason for rollback
2. Preserve all evidence from the current stage
3. Return to the appropriate previous stage
4. Record the rollback in the strategy's lineage document

---

*End of Strategy Lifecycle*
