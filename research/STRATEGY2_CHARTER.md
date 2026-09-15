# Strategy 2 Research Charter
# Version: 0.1.0
# Date: 2026-09-15
# Branch: research/strategy-2
# Status: ACTIVE

## Research Question

> Can we discover stable, reproducible structure in financial markets that provides
> useful information to NQTS or NestQuant OS — even if that information cannot itself
> be monetized as a standalone trading strategy?

This is not "find another technical indicator."
This is "find structure in noisy systems and determine what information that structure contains."

---

## Research Philosophy

### What We Are Not Doing

- We are not optimizing indicators until the backtest looks profitable.
- We are not hunting for a single "Strategy 2" to replace or complement Strategy 1.
- We are not assuming that every discovery must become a trading signal.

### What We Are Doing

Investigating the mathematical and statistical structure of financial markets.
Classifying what information that structure contains.
Determining where that information belongs in NQTS.

### The Core Distinction

A phenomenon that fails to produce standalone alpha is not a failed experiment.
It is an incomplete characterization. We must ask:

> "What information does this phenomenon contain?"

Not merely:

> "Does this make money?"

---

## Research Outcome Taxonomy

Every finding must be classified into one of these outcomes:

### A. Tradable Edge

- Predictive of direction or level
- Economically profitable after costs
- Robust across time, pairs, and regimes
- **Destination:** Strategy candidate → NQTS promotion pathway

### B. Predictive but Not Directly Tradable

- Statistically significant predictive power
- Insufficient after transaction costs for standalone trading
- **Destination:** Input to risk models, position sizing, regime filters

### C. Risk Information

- Improves volatility or risk estimation
- Improves sizing, exposure control, or stop placement
- No directional prediction required
- **Destination:** Risk engine, position sizer, circuit breakers

### D. Portfolio Information

- Correlation structure, dependence, diversification
- Concentration risk, regime-dependent correlation
- **Destination:** Portfolio construction, exposure limits

### E. Execution Information

- Spread dynamics, slippage prediction, liquidity conditions
- Optimal timing, market impact
- **Destination:** Execution engine, cost models

### F. Regime Information

- Identifies changing market conditions
- Conditional strategy performance
- **Destination:** Strategy selection, risk limits, performance interpretation

### G. Research Infrastructure Value

- Improves data or modeling methodology
- Better testing frameworks, better causal inference tools
- **Destination:** Research engine capabilities

### H. No Useful Information

- Fails appropriate tests
- Not reproducible
- **Destination:** Archive with documented failure reason

### I. Interesting but Currently Unusable

- Phenomenon appears real but cannot yet be characterized sufficiently
- **Destination:** Hold, revisit when data/methods improve

---

## Research Hypothesis Tree

These are contenders, not commitments. We investigate them. Some die quickly.
Some become interesting. Some survive.

```
STRATEGY 2 RESEARCH
│
├── H1 — Return Predictability
│   ├── H1.1 Momentum / continuation
│   ├── H1.2 Mean reversion
│   ├── H1.3 Conditional asymmetry (asymmetric returns)
│   └── H1.4 Cross-sectional effects (currency strength, carry)
│
├── H2 — Volatility Structure
│   ├── H2.1 Volatility persistence (clustering)
│   ├── H2.2 Volatility mean reversion
│   ├── H2.3 Volatility regime transitions
│   └── H2.4 Tail-risk predictability
│
├── H3 — Dependence Structure
│   ├── H3.1 Dynamic correlation
│   ├── H3.2 Cross-asset dependence
│   ├── H3.3 Correlation breakdown events
│   └── H3.4 Portfolio concentration risk
│
├── H4 — Market-State Dynamics
│   ├── H4.1 Latent regime identification
│   ├── H4.2 State transition probabilities
│   └── H4.3 Conditional strategy performance
│
├── H5 — Execution / Liquidity
│   ├── H5.1 Spread dynamics
│   ├── H5.2 Slippage prediction
│   └── H5.3 Liquidity conditions
│
└── H6 — Mathematical Models
    ├── H6.1 Stochastic process characterization
    ├── H6.2 SDE model fitting
    ├── H6.3 Multivariable state functions
    └── H6.4 Stochastic control applications
```

---

## Mathematical Framework

### Stochastic Processes

Investigate whether returns, volatility, and other market variables follow
discernible stochastic processes:

```
dX_t = μ(X_t, t) dt + σ(X_t, t) dW_t
```

Questions:
- Is volatility state-dependent?
- Is drift state-dependent?
- Are returns heteroskedastic?
- Does volatility mean-revert?
- Are there persistent volatility states?
- Are jumps important?
- Does the distribution change conditionally?

### Multivariable Calculus

Markets are not one-dimensional. Investigate functions:

```
f(x₁, x₂, ..., xₙ)
```

where variables may represent: return, volatility, volume, spread, correlation,
time, cross-asset relationships, momentum, liquidity.

Derivatives ∂f/∂xᵢ tell us how expected behavior changes as market state changes.
The gradient ∇f describes direction in state-space where expectation changes most rapidly.
The Hessian Hf describes curvature and interactions.

Applications:
- Nonlinear risk surfaces
- Volatility surfaces
- Conditional expected returns
- Sensitivity analysis
- Portfolio risk
- Regime transitions

### Stochastic Calculus (Advanced)

Eventually investigate:
- Brownian motion and martingales
- Itô processes and Itô's lemma
- Stochastic differential equations
- Geometric Brownian motion
- Mean-reverting processes (Ornstein–Uhlenbeck)
- Jump-diffusion processes
- Stochastic volatility models
- Filtering and state estimation
- Stochastic control

**Critical distinction:** We study these because they give us better languages
for describing uncertainty and evolving systems — NOT because sophisticated
mathematics automatically creates alpha.

---

## Where Does the Information Belong?

Every surviving finding must answer: **"Where does this information enter NQTS?"**

| Finding | Predictive? | Profitable Alone? | NQTS Destination |
|---|---|---|---|
| Return continuation | Yes | Yes | Alpha |
| Volatility forecast | No direction | No | Position sizing |
| Correlation regime | No | No | Portfolio risk |
| Spread forecast | No | No | Execution |
| Regime classifier | Maybe | No | Strategy selection |
| Tail-risk signal | No | No | Risk reduction |
| Nothing reproducible | No | No | Reject |

This prevents the common quant mistake of declaring research failed because
it doesn't produce standalone alpha. A volatility forecast that improves
position sizing is a successful research result.

---

## Research Principles

### Principle 1: Negative Results Are Valid

A finding that says "this phenomenon does not exist in FX markets" is a
valuable contribution. It prevents future researchers from wasting time.

### Principle 2: Replication Before Excitement

No finding is published internally until it has been independently replicated
on out-of-sample data. In-sample significance is hypothesis generation,
not evidence.

### Principle 3: Causality Is Required for Action

Correlation without causation may be interesting but must not be deployed
into risk or execution systems without understanding the mechanism.

### Principle 4: Costs Are Real

Every finding must be evaluated after realistic transaction costs.
A phenomenon that is significant at 0 pips spread but disappears at
2 pips spread is not economically useful at our spread.

### Principle 5: Characterize Before Classifying

Before declaring a finding "useful" or "useless," we must characterize it:
what does it predict, how strongly, under what conditions, with what
limitations, and with what failure modes?

---

## Current System Context

- **NQTS Version:** 0.2.0 shadow-v1
- **Active Strategy:** Canonical Breakout V1 (NQ-BREAKOUT-V1)
- **Timeframe:** 4H
- **Pairs:** 20 major/minor FX crosses
- **Data:** MT5 Demo, historical OHLCV via Wine+Flask bridge
- **Python:** 3.12.3 (VPS), 3.14.6 (dev machine)
- **Key limitation:** pandas available on VPS only

---

## Research Workflow

```
Hypothesis
  → Data acquisition / preparation
  → Exploratory analysis
  → Causal test design
  → In-sample investigation
  → Out-of-sample validation
  → Replication
  → Characterization (what, how strong, when, limitations)
  → Classification (A through I)
  → NQTS integration decision
  → Documentation
```

At each stage: STOP → VERIFY EVIDENCE → DECIDE → PROCEED OR ABANDON.

---

## Success Criteria

Success is NOT "finding Strategy 2."

Success IS:
1. Investigating the hypothesis tree systematically
2. Classifying findings into the outcome taxonomy
3. Producing reproducible evidence for each finding
4. Identifying where useful information enters NQTS
5. Archiving failures with documented reasons
6. Building research infrastructure that improves future investigation

If we investigate thoroughly and find nothing actionable, that is still success.
We will have learned something about markets and built tools for future research.

---

## Branch Strategy

This research lives on `research/strategy-2` branched from `master` at `e6a8647`.

Research code goes in `research/experiments/strategy2/`.
Research data goes in `research/data/strategy2/`.
Research results go in `research/results/strategy2/`.

Merges to `master` require:
1. Finding classified into outcome taxonomy
2. Replicated on out-of-sample data
3. Characterized with limitations documented
4. NQTS integration decision made
5. Human review and approval

---

## End of Charter

This is a living document. It will evolve as we learn what the markets
actually look like.
