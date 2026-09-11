# Research Backlog

> **NestQuant Proposed Future Research**
> **Status:** Proposals — not yet started
> **Last Updated:** 2026-09-11

---

## 1. Strategy V2 — Breakout Variant

### Hypothesis
A modified breakout strategy with additional validated filters could improve risk-adjusted performance while maintaining the core breakout edge.

### Reason for Investigation
V1 is the baseline. V2 should only be developed if it can be demonstrated to complement V1, not merely produce more trades.

### Expected Relationship to V1
Complementary — V2 should perform well when V1 does not, or provide diversification benefit.

### Required Data
Same as V1: 4H OHLCV for 28 FX pairs.

### Validation Criteria
- Full strategy lifecycle completion
- Complementarity analysis shows marginal Sharpe improvement
- Portfolio-level drawdown does not increase
- Independent rollback capability

### Status
NOT STARTED — proposal only

---

## 2. Mean Reversion Research

### Hypothesis
Mean reversion strategies may provide complementarity to the breakout approach, particularly in ranging markets.

### Reason for Investigation
Breakout strategies perform well in trending markets. Mean reversion may perform well in ranging markets, providing natural diversification.

### Expected Relationship to V1
Complementary — different market regime focus.

### Required Data
Same as V1: 4H OHLCV for 28 FX pairs.

### Validation Criteria
- Full strategy lifecycle completion
- Edge survives realistic transaction costs
- Complementarity analysis positive
- Regime analysis shows different regime focus

### Status
PREVIOUSLY INVESTIGATED — MR approaches had gross edge below costs. May be reconsidered with different methodology.

---

## 3. Statistical Arbitrage

### Hypothesis
Statistical arbitrage (pairs trading, cointegration-based) may provide market-neutral returns that complement the directional breakout approach.

### Reason for Investigation
Market-neutral returns would provide diversification from the directional V1.

### Expected Relationship to V1
Complementary — market-neutral vs directional.

### Required Data
Same as V1: 4H OHLCV for 28 FX pairs. May require additional data for cointegration testing.

### Validation Criteria
- Full strategy lifecycle completion
- Cointegration validated statistically
- Edge survives transaction costs
- Complementarity analysis positive

### Status
NOT STARTED — proposal only

---

## 4. Volatility Regime Research

### Hypothesis
Explicit volatility regime classification may improve strategy selection or position sizing.

### Reason for Investigation
V1 does not use regime filtering. If regime classification can be validated, it may improve V1 or enable V2.

### Expected Relationship to V1
Enhancement — may improve V1 position sizing or timing.

### Required Data
Same as V1, plus potential for higher-frequency data for regime estimation.

### Validation Criteria
- Regime classification validated causally
- Regime improves strategy performance
- Does not introduce look-ahead bias
- Robust across time periods

### Status
PREVIOUSLY INVESTIGATED — regime approaches showed promise but need more validation. Phase 12 regime validation is a starting point.

---

## 5. Currency Strength Research

### Hypothesis
Currency strength rankings may provide additional signal information for breakout timing.

### Reason for Investigation
Currency strength captures cross-pair dynamics that single-pair analysis misses.

### Expected Relationship to V1
Enhancement — may improve entry timing.

### Required Data
Same as V1: 4H OHLCV for 28 FX pairs. Currency strength ranking from `currency_strength.py`.

### Validation Criteria
- Currency strength validated as predictive
- Does not introduce look-ahead bias
- Edge survives transaction costs
- Independent validation

### Status
PREVIOUSLY INVESTIGATED — Phase 10 showed limited improvement. May be reconsidered.

---

## 6. Session Behaviour Research

### Hypothesis
Different trading sessions (London, New York, Asian) may exhibit different breakout characteristics.

### Reason for Investigation
Session-aware position sizing or timing may improve performance.

### Expected Relationship to V1
Enhancement — may improve entry timing or position sizing.

### Required Data
Same as V1: 4H OHLCV for 28 FX pairs, plus session classification from `indicators/session.py`.

### Validation Criteria
- Session effects validated statistically
- Does not introduce look-ahead bias
- Edge survives transaction costs
- Independent validation

### Status
NOT STARTED — proposal only

---

## 7. TimesFM Investigation

### Hypothesis
Google's TimesFM foundation model may provide useful financial time series predictions.

### Reason for Investigation
Foundation models may capture patterns not visible to traditional methods.

### Expected Relationship to V1
Unknown — exploration phase.

### Required Data
TimesFM model access, same market data as V1.

### Validation Criteria
- Model produces meaningful predictions
- Predictions are causal (no look-ahead)
- Edge survives transaction costs
- Independent validation

### Status
NOT STARTED — exploration phase

---

## 8. Portfolio Correlation Research

### Hypothesis
Cross-pair correlation dynamics may provide additional signal or risk management information.

### Reason for Investigation
Correlation changes may indicate regime changes or risk accumulation.

### Expected Relationship to V1
Risk management enhancement.

### Required Data
Same as V1: 4H OHLCV for 28 FX pairs.

### Validation Criteria
- Correlation changes are predictable
- Predictions are causal
- Useful for risk management
- Independent validation

### Status
NOT STARTED — proposal only

---

## 9. Execution Quality Research

### Hypothesis
Detailed execution quality analysis may reveal opportunities to reduce slippage and improve fills.

### Reason for Investigation
Execution quality directly impacts profitability.

### Expected Relationship to V1
Enhancement — may improve execution without changing strategy logic.

### Required Data
Execution logs from shadow/demo operation.

### Validation Criteria
- Execution patterns are analysable
- Improvements are measurable
- Do not change strategy behaviour
- Independent validation

### Status
NOT STARTED — requires more live execution data

---

*End of Research Backlog*
