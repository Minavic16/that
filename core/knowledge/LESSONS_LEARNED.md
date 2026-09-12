# Lessons Learned

> **NestQuant Institutional Knowledge**
> **Status:** Active reference
> **Last Updated:** 2026-09-11

---

## 1. Strategy Identity

### Canonical identity must be explicit
Every strategy MUST have a clearly defined, documented identity. Without explicit identity, strategies can be silently modified, making it impossible to determine what is actually running.

### Strategy identity must be immutable after promotion
Once a strategy is promoted to production, its identity MUST NOT be modified. Material changes MUST create a new version.

### Population mismatch is a real risk
Research parameters can drift from production parameters. The `monitoring/canonical_identity.py` module documents this risk. Every parameter divergence MUST be explicitly tracked.

---

## 2. Research-Production Boundary

### Research code must not leak into production
Research code is unvalidated and may contain experimental logic. Production MUST NOT import from research under any circumstances.

### Production safety boundaries must be independent of research
Safety systems (kill switch, circuit breakers, risk guards) MUST be implemented in production code, not in research code. Research may analyse safety, but must not implement it for production use.

### Version identity prevents silent strategy mutation
Without versioning, a "small parameter tweak" can silently transform a validated strategy into an unvalidated one. Version identity prevents this.

---

## 3. Validation Reality

### Broker execution validation does not prove profitability
Successful demo execution proves the infrastructure works. It does NOT prove the strategy is profitable. Demo validation is an infrastructure gate, not a profitability gate.

### Demo validation must not be confused with profitability validation
A strategy that runs successfully on demo may still be unprofitable. The demo phase validates execution quality, not strategy edge.

### Backtest profitability alone is insufficient
A profitable backtest does not account for: execution friction, slippage, market impact, regime changes, parameter instability, or data snooping. Multiple validation stages exist because no single stage is sufficient.

---

## 4. Risk Management

### Risk controls must be independently verified
Risk limits, circuit breakers, and safety guards MUST have dedicated tests. They cannot be assumed correct because the strategy logic is correct.

### Circuit breakers must be treated separately from strategy signals
Circuit breakers are infrastructure safety, not strategy logic. They must be tested, calibrated, and maintained independently.

### Position limits must be enforced at multiple levels
Pre-trade risk checks, prop firm guards, and circuit breakers provide defence in depth. No single layer is sufficient.

---

## 5. Filters and Features

### Strategy filters should not be added merely because they sound useful
Every filter must be validated independently. "This filter should help" is not evidence. Filters can reduce trade count without improving risk-adjusted performance.

### Correlation, session, regime features must be validated before becoming signal filters
These features may have statistical relationships with returns, but those relationships must survive: cost modelling, out-of-sample validation, walk-forward testing, and complementarity analysis before influencing live trading.

### Historical correlation logic belonged to a different research implementation
The correlation research from the MR+TF investigation is separate from the current breakout strategy. Do not conflate them.

---

## 6. Execution

### MT5 integration lessons
- HTTP bridge (Flask) provides clean separation from MT5 SDK
- No Python code should import MetaTrader5 directly
- All order submission goes through the adapter pattern
- Retry logic must handle transient failures without duplicating orders

### Fill-aware execution matters
SL/TP must be calculated from fill price, not signal price. This distinction was validated through the S8.6.7A entry risk geometry audit.

### Startup reconciliation is critical
On restart, the system must reconcile internal state with broker positions. Orphan positions, ghost positions, and state mismatches must be detected and handled.

---

## 7. Deployment

### Deployment architecture must permit rollback
If a strategy fails, it MUST be possible to disable it without taking down the entire system. This requires independent operation and independent monitoring.

### Shadow trading is not live trading
Shadow trading observes signals without placing orders. It validates signal generation, not execution quality.

### Controlled demo execution does not prove live profitability
A single test order on demo proves the execution pipeline works. It does not prove the strategy is profitable over time.

---

## 8. Research

### Z-score mean reversion had gross edge below realistic transaction costs
The Phase 3 Z-score research showed statistical signals, but the edge was too small to survive realistic transaction costs. This is a common finding in quantitative research.

### Failed experiments are valuable
Failed experiments prevent repeated mistakes. They MUST be documented and preserved, not deleted.

### Forensic analysis reveals implementation quality issues
The MR forensic reports (MR_PHASE2-5) revealed material bugs, look-ahead bias, and implementation quality issues in the original research. Forensic analysis is essential.

---

*End of Lessons Learned*
