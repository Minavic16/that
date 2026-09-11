# Complementarity Policy

> **NestQuant Strategy Complementarity Evaluation Policy**
> **Status:** Mandatory for Strategy V2+
> **Last Updated:** 2026-09-11

---

## 1. Principle

A new strategy is NOT simply another strategy. It is a portfolio component. A candidate strategy MUST demonstrate that it genuinely improves the portfolio's risk-adjusted performance, not merely that it produces additional trades or additional total return.

---

## 2. When Complementarity Applies

Complementarity evaluation is required when:
- A second strategy is proposed for simultaneous live deployment with an existing strategy
- A strategy variant is proposed as a replacement for an existing strategy
- Multiple strategies compete for the same capital allocation

Complementarity evaluation is NOT required for:
- Research investigations that do not intend live deployment
- Sequential strategy replacement (one strategy fully retires before the next starts)
- Strategies operating on entirely different instruments or timeframes with no overlap

---

## 3. Evaluation Dimensions

### 3.1 Return Correlation

| Metric | Description |
|--------|-------------|
| Pearson correlation | Linear relationship between strategy returns |
| Spearman correlation | Rank-based relationship |
| Rolling correlation | Time-varying relationship |

**Assessment:** Low positive or negative correlation is preferred. High positive correlation suggests the candidate adds little diversification.

### 3.2 Signal Overlap

| Metric | Description |
|--------|-------------|
| Signal frequency overlap | How often both strategies signal simultaneously |
| Directional agreement | How often signals agree on direction |
| Timing overlap | How often signals occur on the same bar |

**Assessment:** High overlap suggests the candidate duplicates V1 rather than complementing it.

### 3.3 Directional Overlap

| Metric | Description |
|--------|-------------|
| BUY-BUY overlap | Both strategies go long simultaneously |
| SELL-SELL overlap | Both strategies go short simultaneously |
| BUY-SELL offset | Strategies take opposite positions |

**Assessment:** Some offset is beneficial. Excessive offset suggests the strategies cancel each other.

### 3.4 Drawdown Overlap

| Metric | Description |
|--------|-------------|
| Drawdown timing overlap | Both strategies in drawdown simultaneously |
| Drawdown depth correlation | How correlated drawdown depths are |
| Recovery timing | Do strategies recover together or staggered |

**Assessment:** Staggered drawdowns are preferred. Simultaneous deep drawdowns amplify portfolio risk.

### 3.5 Losing-Period Overlap

| Metric | Description |
|--------|-------------|
| Monthly losing overlap | Both strategies lose in the same month |
| Weekly losing overlap | Both strategies lose in the same week |
| Consecutive losing overlap | Both strategies have consecutive losses simultaneously |

**Assessment:** Overlapping losing periods create extended portfolio drawdowns that may exceed risk tolerance.

### 3.6 Regime Behaviour

| Metric | Description |
|--------|-------------|
| Performance by regime | How each strategy performs in trending/ranging/volatile markets |
| Regime sensitivity difference | Whether strategies are sensitive to different regimes |
| Regime transition behaviour | How strategies behave during regime changes |

**Assessment:** Strategies that perform well in different regimes provide natural diversification.

### 3.7 Volatility Behaviour

| Metric | Description |
|--------|-------------|
| Return volatility | Standard deviation of returns |
| Volatility of volatility | Stability of return variance |
| Tail behaviour | Frequency and magnitude of extreme returns |

**Assessment:** Different volatility profiles suggest different risk exposures.

### 3.8 Exposure Concentration

| Metric | Description |
|--------|-------------|
| Instrument overlap | Both strategies trade the same instruments |
| Currency exposure overlap | Both strategies expose the same currencies |
| Time-of-day overlap | Both strategies are active at the same times |

**Assessment:** Concentrated exposure amplifies risk. Diversified exposure reduces it.

### 3.9 Marginal Sharpe

| Metric | Description |
|--------|-------------|
| Sharpe with candidate | Portfolio Sharpe including both strategies |
| Sharpe without candidate | Portfolio Sharpe with only existing strategies |
| Marginal contribution | Difference in Sharpe |

**Assessment:** The candidate MUST improve portfolio Sharpe. A positive standalone Sharpe that reduces portfolio Sharpe is insufficient.

### 3.10 Marginal Expectancy

| Metric | Description |
|--------|-------------|
| Portfolio expectancy with candidate | Expected P&L per trade with both strategies |
| Portfolio expectancy without candidate | Expected P&L per trade with existing strategy only |
| Marginal contribution | Change in expectancy |

**Assessment:** The candidate MUST improve or maintain portfolio expectancy.

### 3.11 Portfolio Drawdown

| Metric | Description |
|--------|-------------|
| Maximum drawdown with candidate | Portfolio max DD including candidate |
| Maximum drawdown without candidate | Portfolio max DD with existing strategy only |
| Drawdown duration | How long the portfolio stays in drawdown |

**Assessment:** The candidate MUST NOT increase maximum drawdown beyond risk tolerance.

### 3.12 Diversification Benefit

| Metric | Description |
|--------|-------------|
| Portfolio variance reduction | Does adding the candidate reduce portfolio variance? |
| Effective number of strategies | Does the portfolio behave as if it has more independent bets? |
| Correlation-adjusted return | Return adjusted for correlation with existing strategies |

**Assessment:** True diversification requires more than just different strategy names.

---

## 4. Explicit Non-Criteria

The following are NOT sufficient evidence of complementarity:

| Claim | Why Insufficient |
|-------|-----------------|
| "More trades" | More trades ≠ better risk-adjusted performance |
| "Higher standalone profit" | Higher standalone profit ≠ portfolio superiority |
| "Lower correlation alone" | Low correlation with negative expectancy destroys value |
| "Different signal type" | Different signals can still be correlated in practice |
| "Works in different regime" | Must be validated statistically, not assumed |

---

## 5. Portfolio-Level Evaluation

Complementarity MUST be evaluated at the portfolio level, not just at the individual strategy level.

The portfolio-level evaluation MUST include:
1. Combined equity curve
2. Combined drawdown analysis
3. Combined risk metrics (Sharpe, Sortino, Calmar)
4. Combined trade statistics
5. Combined exposure analysis
6. Combined regime analysis

---

## 6. Decision Criteria

A candidate strategy is considered complementary if and only if:

1. Portfolio Sharpe improves (or is maintained with acceptable trade-offs)
2. Portfolio maximum drawdown does not exceed risk tolerance
3. Portfolio expectancy is positive
4. The candidate provides meaningful diversification (not just more trades)
5. Losing-period overlap is manageable
6. Exposure concentration is acceptable

If ANY of these criteria fail, the candidate MUST NOT be promoted to simultaneous live deployment.

---

## 7. Documentation

Every complementarity evaluation MUST produce a documented report containing:
1. All metrics defined in Section 3
2. Comparison tables (with and without candidate)
3. Statistical significance of improvements
4. Risk assessment
5. Recommendation (promote / reject / hold for reassessment)

---

*End of Complementarity Policy*
