# R2.0 — Strategy 2 Research Prioritization
# Version: 0.1.0
# Date: 2026-09-15
# Branch: research/strategy-2 (frozen at 7d25be3)
# Status: DECISION REQUIRED — do not implement until approved

---

## Objective

Determine which hypothesis should become the first research experiment (R2.1)
based on **expected information yield per unit of effort** — not on which
hypothesis sounds most likely to produce alpha.

---

## Scoring Methodology

### Scale

| Score | Meaning |
|---|---|
| 5 | Very high / very easy / very available |
| 4 | High / easy / available |
| 3 | Moderate / moderate effort |
| 2 | Low / difficult / limited |
| 1 | Very low / very difficult / unavailable |

### Dimension Definitions

1. **Expected Information Yield** — How much new information about market
   structure is this likely to produce, regardless of whether it is tradable?
   A hypothesis that produces a clear negative result scores higher than one
   that produces an ambiguous positive.

2. **Potential Relevance to NQTS** — If the finding is positive, how many
   NQTS subsystems could benefit? (Alpha, risk, sizing, portfolio, execution,
   regime, strategy selection.)

3. **Ability to Produce a Useful Negative Result** — Can a failed hypothesis
   still teach us something valuable? A negative result that eliminates a
   class of effects is more valuable than one that merely says "no signal here."

4. **Falsifiability** — How cleanly can this hypothesis be tested? Can we
   define a clear threshold below which we abandon it? Or is it so ambiguous
   that we could always find a post-hoc reason to keep it alive?

5. **Existing Data Availability** — Do we already have the data needed? Do we
   need additional data sources, longer history, different instruments, or
   special datasets?

6. **Engineering/Compute Effort** — How much code must be written? How complex
   is the implementation? Does it require new infrastructure, new libraries,
   or new data pipelines?

7. **Statistical/Inference Difficulty** — How hard is it to draw valid
   statistical conclusions? Are there multiple-testing problems, non-stationarity
   issues, small-sample problems, or complex model selection?

8. **Realistic Transaction-Cost Testing** — Can we test this finding with
   realistic costs? Or does the testing require assumptions about execution
   that are hard to validate?

9. **Independence from Strategy 1** — Does this investigation duplicate work
   already done for the breakout strategy? Or does it explore genuinely new
   territory? Independence reduces the risk of confirming our own biases.

10. **Potential Downstream Value to Other Research** — If this investigation
    produces tools, datasets, or methods, can they be reused by future
    research branches? High infrastructure value multiplies the return.

---

## The Matrix

### H1 — Return Predictability

| Dimension | Score | Rationale |
|---|---|---|
| 1. Info yield | 3 | Return predictability is the most studied question in finance. We are unlikely to find something new. But a rigorous FX-specific result has value. |
| 2. NQTS relevance | 5 | If positive, directly enters alpha. The highest single-system relevance. |
| 3. Negative value | 3 | "No return predictability in FX crosses at 4H" is a useful negative — it tells us to focus elsewhere. |
| 4. Falsifiability | 4 | Clear: test momentum/reversion signals, compare to costs. Threshold is well-defined. |
| 5. Data availability | 5 | We have 4H OHLCV for 20 pairs. Sufficient for initial investigation. |
| 6. Eng. effort | 4 | Standard indicator calculation, simple statistical tests. Low implementation barrier. |
| 7. Statistical difficulty | 3 | Multiple-testing correction needed (many pairs, many lookbacks). Non-stationarity is a concern. |
| 8. Cost testing | 4 | Easy: apply spread/slippage to signal returns. We have cost models. |
| 9. Independence | 2 | Strategy 1 IS a return-predictability strategy (breakout). H1 overlaps heavily. Risk of confirming own biases. |
| 10. Downstream value | 3 | Tools built here (signal testing framework) are reusable. But the methodology is standard. |
| **Total** | **36** | |

### H2 — Volatility Structure

| Dimension | Score | Rationale |
|---|---|---|
| 1. Info yield | 4 | Volatility structure is less studied than returns in retail quant. Rich information content. |
| 2. NQTS relevance | 4 | Enters: position sizing, ATR-based stops, risk limits, circuit breakers, regime identification. Multiple subsystems. |
| 3. Negative value | 4 | "Volatility is not predictable beyond GARCH" is a strong negative that constrains all volatility-dependent systems. |
| 4. Falsifiability | 4 | Clear: test volatility forecasts against realized. Measure RMSE improvement over baseline. |
| 5. Data availability | 4 | 4H OHLCV is sufficient for realized volatility. Intraday data would help but is not required. |
| 6. Eng. effort | 3 | Requires: realized variance estimators, GARCH family, regime-switching models. Moderate complexity. |
| 7. Statistical difficulty | 3 | Volatility is more stable than returns. Lower multiple-testing burden. But model selection (GARCH vs HAR vs regime) is non-trivial. |
| 8. Cost testing | 3 | Indirect: volatility improves sizing/stops, not directly traded. Cost testing requires indirect evaluation through position sizing changes. |
| 9. Independence | 4 | Strategy 1 uses ATR as a fixed parameter. H2 would investigate whether ATR should be dynamic. Genuine new territory. |
| 10. Downstream value | 5 | Realized variance estimators, volatility forecasting framework, regime detection — all highly reusable across future research. |
| **Total** | **37** | |

### H3 — Dependence Structure

| Dimension | Score | Rationale |
|---|---|---|
| 1. Info yield | 4 | Dynamic correlation in FX is genuinely interesting and underexplored in retail quant. |
| 2. NQTS relevance | 3 | Portfolio risk, correlation breakdown, concentration. Relevant but fewer subsystems than H2. |
| 3. Negative value | 3 | "Correlation is stable" is useful but less constraining than volatility results. |
| 4. Falsifiability | 3 | Harder: correlation is noisy, requires long windows, results are often ambiguous. |
| 5. Data availability | 4 | 20 pairs × 4H is workable for pairwise correlation. DCC-GARCH needs more data. |
| 6. Eng. effort | 2 | DCC-GARCH, copulas, regime-switching correlation models. Significant implementation. |
| 7. Statistical difficulty | 2 | Correlation estimation is notoriously noisy. Non-stationarity is severe. Confidence intervals are wide. |
| 8. Cost testing | 2 | Hard: correlation affects portfolio construction, not individual trade economics. Indirect evaluation required. |
| 9. Independence | 4 | Strategy 1 does not model correlation. Genuine new territory. |
| 10. Downstream value | 4 | Correlation tools reusable for portfolio research. But the statistical difficulty reduces practical value. |
| **Total** | **31** | |

### H4 — Market-State Dynamics

| Dimension | Score | Rationale |
|---|---|---|
| 1. Info yield | 5 | Latent regime identification is the highest-information hypothesis. It could restructure how we think about all strategies. |
| 2. NQTS relevance | 4 | Strategy selection, risk limits, conditional performance interpretation. Broad relevance. |
| 3. Negative value | 5 | "No detectable regimes in FX 4H" is an extremely valuable negative. It would simplify all future research. |
| 4. Falsifiability | 2 | Regime models are notoriously hard to falsify. Hidden Markov Models can always find "something." Risk of post-hoc rationalization is high. |
| 5. Data availability | 3 | Needs long history for regime detection. 4H data is available but regime transitions are rare — small sample of transitions. |
| 6. Eng. effort | 2 | HMMs, regime-switching VARs, change-point detection. Complex implementation. Model selection is hard. |
| 7. Statistical difficulty | 1 | Highest statistical difficulty of all hypotheses. Regime models are overparameterized, sensitive to initialization, hard to validate. |
| 8. Cost testing | 2 | Regime information enters strategy selection, not direct trading. Hard to evaluate economically. |
| 9. Independence | 5 | Strategy 1 has no regime component. Completely new territory. |
| 10. Downstream value | 4 | If successful, regime tools are highly reusable. But the difficulty of success reduces expected value. |
| **Total** | **29** | |

### H5 — Execution / Liquidity

| Dimension | Score | Rationale |
|---|---|---|
| 1. Info yield | 3 | Spread and slippage dynamics are real but well-characterized in academic literature. Marginal new information likely. |
| 2. NQTS relevance | 3 | Execution engine, cost models. Relevant but narrow — fewer subsystems than H2 or H4. |
| 3. Negative value | 3 | "Spreads are not predictable" is useful but expected — most studies find this. |
| 4. Falsifiability | 4 | Clear: test spread predictions against realized. Simple statistical framework. |
| 5. Data availability | 2 | We have OHLCV but NOT tick data, bid/ask, or order book. Spread dynamics require higher-frequency data than we have. |
| 6. Eng. effort | 3 | Spread estimation from OHLCV is possible (Corwin-Schultz etc.) but noisy. No tick data limits approaches. |
| 7. Statistical difficulty | 3 | Moderate. Spread estimation from OHLCV has known biases. |
| 8. Cost testing | 4 | Direct: test whether spread predictions improve execution cost estimates. |
| 9. Independence | 4 | Strategy 1 ignores spread dynamics. New territory. |
| 10. Downstream value | 3 | Tools reusable for execution research. But data limitation constrains value. |
| **Total** | **32** | |

### H6 — Mathematical Models

| Dimension | Score | Rationale |
|---|---|---|
| 1. Info yield | 4 | Rich theoretical framework. Could reveal deep structure. |
| 2. NQTS relevance | 3 | SDE models could improve risk estimation and process understanding. But very indirect. |
| 3. Negative value | 3 | "Returns do not follow an OU process" is useful but expected. |
| 4. Falsifiability | 3 | Model comparison tests are well-established (AIC, BIC, likelihood ratio). But nested model selection is tricky. |
| 5. Data availability | 4 | 4H OHLCV is sufficient for basic SDE fitting. |
| 6. Eng. effort | 1 | SDE estimation (MLE, GMM, Bayesian), stochastic volatility, jump-diffusion. Very high implementation cost. |
| 7. Statistical difficulty | 2 | SDE parameter estimation is notoriously difficult. Convergence issues, identifiability problems. |
| 8. Cost testing | 2 | Very indirect. SDE models don't produce tradeable signals directly. |
| 9. Independence | 5 | Completely new territory for NestQuant. |
| 10. Downstream value | 4 | Mathematical tools are reusable. But very high barrier to entry. |
| **Total** | **31** | |

---

## Summary Matrix

| Hypothesis | H1 Return | H2 Volatility | H3 Dependence | H4 Regime | H5 Execution | H6 Math |
|---|---|---|---|---|---|---|
| 1. Info yield | 3 | **4** | 4 | 5 | 3 | 4 |
| 2. NQTS relevance | **5** | 4 | 3 | 4 | 3 | 3 |
| 3. Negative value | 3 | 4 | 3 | **5** | 3 | 3 |
| 4. Falsifiability | 4 | 4 | 3 | 2 | 4 | 3 |
| 5. Data availability | **5** | 4 | 4 | 3 | 2 | 4 |
| 6. Eng. effort | 4 | 3 | 2 | 2 | 3 | **1** |
| 7. Statistical difficulty | 3 | 3 | 2 | **1** | 3 | 2 |
| 8. Cost testing | 4 | 3 | 2 | 2 | 4 | 2 |
| 9. Independence | 2 | 4 | 4 | **5** | 4 | **5** |
| 10. Downstream value | 3 | **5** | 4 | 4 | 3 | 4 |
| **TOTAL** | **36** | **37** | **31** | **33** | **32** | **31** |

---

## Ranking

| Rank | Hypothesis | Total Score | Classification |
|---|---|---|---|
| **1** | **H2 — Volatility Structure** | **37** | Recommended for R2.1 |
| 2 | H1 — Return Predictability | 36 | Wait — overlaps Strategy 1 |
| 3 | H4 — Market-State Dynamics | 33 | Wait — too complex for first experiment |
| 4 | H5 — Execution / Liquidity | 32 | Wait — data-limited |
| 5 | H3 — Dependence Structure | 31 | Wait — noisy, complex |
| 6 | H6 — Mathematical Models | 31 | Wait — highest barrier |

---

## Recommendation: H2 — Volatility Structure for R2.1

### Why H2 First

**H2 has the highest expected information yield per unit of effort.**

The reasoning:

**1. It is actionable across multiple NQTS subsystems simultaneously.**

A volatility finding enters: position sizing (ATR-based), risk limits,
circuit breakers, regime identification, stop placement, and portfolio
allocation. That is 6 subsystems from one investigation.

**2. It produces high-value negative results.**

"Volatility is not predictable beyond GARCH at 4H FX" is an extremely
constraining result. It would simplify all volatility-dependent decisions
across NQTS. That negative result is almost as valuable as a positive one.

**3. It is genuinely independent from Strategy 1.**

Strategy 1 uses ATR as a FIXED parameter. H2 investigates whether ATR
should be DYNAMIC. This is new territory, not a rehash of breakout research.

**4. The data we need is the data we have.**

4H OHLCV is sufficient for realized volatility estimation. No additional
data sources are required for the initial investigation.

**5. The implementation effort is moderate, not extreme.**

Realized variance estimators and GARCH-family models are well-established.
The implementation is non-trivial but not prohibitive. Compare this to
H4 (HMMs, regime-switching) or H6 (SDE estimation).

**6. The statistical difficulty is manageable.**

Volatility is more stable and predictable than returns. The signal-to-noise
ratio is higher. Fewer multiple-testing problems. Lower risk of
overfitting relative to return-prediction research.

**7. The downstream infrastructure is highly reusable.**

Realized variance estimators, volatility forecasting frameworks, and
regime detection tools built for H2 will be used by H3, H4, and
potentially H5. Investing in this infrastructure first multiplies
the return of future research.

### Why the Others Should Wait

**H1 (Return Predictability) — Wait.**

H1 overlaps too heavily with Strategy 1. We already know breakout works
at some level. Investigating return predictability first risks confirming
our own biases rather than discovering new structure. H1 should be
investigated AFTER H2, when we have better volatility tools that can
improve H1 investigation (e.g., volatility-adjusted signals).

**H3 (Dependence Structure) — Wait.**

Correlation estimation is noisy, requires long windows, and produces
ambiguous results. The statistical difficulty is high, the implementation
is complex (DCC-GARCH, copolas), and the transaction-cost evaluation is
indirect. Investigate AFTER H2 builds the volatility infrastructure
that H3 needs.

**H4 (Market-State Dynamics) — Wait.**

H4 has the highest theoretical information yield but the lowest
falsifiability. Regime models are notoriously hard to validate. The
risk of post-hoc rationalization is high. Investigate AFTER H2 provides
volatility-based regime features that H4 can use as inputs.

**H5 (Execution / Liquidity) — Wait.**

We lack tick data, bid/ask, and order book data. Spread dynamics
investigation is data-constrained. Investigate IF we acquire higher-
frequency data. Not blocking — H2 findings may indirectly improve
execution through better volatility-based timing.

**H6 (Mathematical Models) — Wait.**

The implementation barrier is very high (SDE estimation, stochastic
calculus). The statistical difficulty is high. The downstream value
is real but distant. Investigate AFTER H2 establishes whether
stochastic volatility models add value over simpler approaches.

---

## R2.1 Experiment Design

### Research Question

> Does conditional volatility in 4H FX markets contain exploitable structure
> beyond what is captured by a simple rolling ATR?

### Minimum Experiment to Falsify

**Objective:** Determine whether volatility forecasting improves risk
estimation within a simple, well-defined framework.

**Approach:**

1. Compute realized volatility (RV) from 4H OHLCV using Parkinson and
   Yang-Zhang estimators.

2. Fit GARCH(1,1) and HAR-RV models to the RV series.

3. Generate 1-step-ahead volatility forecasts.

4. Evaluate forecast quality against realized volatility using:
   - RMSE improvement over naive (yesterday's RV)
   - QLIKE loss function
   - Direction accuracy (is next period's vol higher or lower?)

5. Test whether volatility forecasts are conditionally correlated with
   future returns (the leverage effect).

**Falsification threshold:**

If GARCH(1,1) does not improve RMSE over a simple rolling-window
volatility estimate by at least 5%, the hypothesis is falsified
at this timeframe/pair combination.

**Expected timeline:** 2–3 days of focused investigation.

### Evidence That Would Justify Expansion

Expand the experiment if:

- GARCH(1,1) improves RMSE by >5% over baseline
- Volatility forecasts show conditional correlation with future returns
  (leverage effect detected)
- HAR-RV outperforms GARCH, suggesting long-memory in volatility
- Results are consistent across at least 10 of 20 pairs

Expansion would include:
- Full cross-pair analysis
- Regime-conditional volatility forecasting
- Position-sizing simulation using volatility forecasts
- Integration assessment with NQTS risk engine

### Evidence That Would Cause Immediate Abandonment

Abandon H2 if:

- GARCH(1,1) does NOT improve RMSE over naive baseline
- Volatility forecasts show no correlation with realized volatility
  beyond what a rolling window already captures
- Results are inconsistent across pairs (some positive, some negative
  with no pattern)
- The leverage effect is absent or negligible in FX 4H data

In this case: archive H2 with documented failure reason. Move to H1.

---

## Single Research Question

R2.1 will answer one question:

> **Does conditional volatility in 4H FX markets contain exploitable structure
> beyond what is captured by a simple rolling ATR, and can that structure
> improve NQTS risk estimation?**

Everything else is secondary.

---

## Go / No-Go Decision

| Gate | Criterion | Status |
|---|---|---|
| GO | Charter approved | YES (7d25be3) |
| GO | Prioritization matrix complete | YES (this document) |
| GO | Falsification threshold defined | YES (5% RMSE improvement) |
| GO | Expansion criteria defined | YES (see above) |
| GO | Abandonment criteria defined | YES (see above) |
| GO | Minimum experiment defined | YES (GARCH vs naive) |
| PENDING | Human approval of R2.1 | REQUIRED |
| PENDING | Implementation decision | BLOCKED until approval |

**Decision required:** Approve or reject H2 as the first R2.1 experiment.

---

## End of R2.0

This document is frozen at the decision point.
Implementation begins only after explicit human approval.
