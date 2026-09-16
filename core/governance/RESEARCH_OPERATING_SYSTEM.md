NestQuant Research Operating System

Document: "RESEARCH_OPERATING_SYSTEM.md"
Version: 1.0
Status: Proposed for Freeze
Scope: NestQuant Research / "research/*"
Production Scope: None — research only

---

1. Purpose

The NestQuant Research Operating System (ROS) defines the standard methodology for researching, testing, validating, falsifying, and potentially integrating quantitative market hypotheses.

Its purpose is to ensure that:

1. research questions are defined before results are observed;
2. experiments are reproducible;
3. causality and data leakage are explicitly tested;
4. weak hypotheses are killed as early as possible;
5. computational effort increases only when evidence justifies it;
6. negative and inconclusive results are preserved as valid research outcomes;
7. research results remain separate from production NQTS;
8. no single backtest or favorable period is treated as sufficient evidence;
9. model complexity never substitutes for empirical evidence.

The governing principle is:

«Human designs the experiment. Machine executes the protocol. Evidence determines whether the hypothesis survives.»

---

2. Research Philosophy

NestQuant research is not primarily a search for "strategies."

The objective is to discover and characterize reproducible market information and determine where that information belongs within the NestQuant system.

A discovery may ultimately provide:

- Alpha
- Risk information
- Position-sizing information
- Portfolio/dependence information
- Regime information
- Execution/liquidity information
- Research infrastructure value
- No actionable information

A hypothesis does not need to become a standalone trading strategy to be scientifically useful.

Likewise:

«A sophisticated model is not evidence of a useful phenomenon.»

Negative results are first-class research results.

---

3. Core Principles

3.1 Pre-registration

Before running substantive experiments, define:

- hypothesis;
- mechanism;
- observable;
- null hypothesis;
- alternative hypothesis;
- universe;
- timeframe;
- horizons;
- models;
- baselines;
- metrics;
- validation methodology;
- kill criteria;
- promotion criteria.

Results must not determine the methodology retroactively.

---

3.2 Falsification Before Optimization

The first objective is not to maximize performance.

The first objective is:

«Determine whether the hypothesis deserves further investigation.»

Cheap falsification precedes expensive optimization.

---

3.3 Causality Is Mandatory

For a forecast made at time t:

[
\hat{y}{t+h} = f(X{\leq t})
]

The model must never use:

[
X_{>t}
]

directly or indirectly.

This applies to:

- feature construction;
- normalization;
- model fitting;
- hyperparameter selection;
- regime classification;
- scaling;
- imputation;
- data transformations;
- validation;
- preprocessing.

---

3.4 Replication Before Promotion

A result observed in one pair, period, model, or partition is a research observation — not a validated phenomenon.

Promotion requires evidence that survives reasonable changes in:

- time;
- instrument;
- regime;
- validation window;
- model specification;
- data realization.

---

3.5 No Opportunistic Model Expansion

Models must be declared before the experiment.

A failed model does not automatically justify:

«"Try a more sophisticated model."»

New models require a new experiment specification or an explicitly pre-registered model family.

---

3.6 Production Isolation

Research code must not modify production behavior without explicit authorization.

Research experiments operate within:

research/*

Production NQTS remains separately controlled.

A successful research experiment is not automatically eligible for production integration.

---

4. Research Lifecycle

Every research hypothesis follows:

HYPOTHESIS
    ↓
SPECIFICATION
    ↓
DATA VALIDATION
    ↓
APPARATUS / CAUSALITY
    ↓
CHEAP FALSIFICATION
    ↓
PRIMARY CAUSAL OOS
    ↓
TEMPORAL ROBUSTNESS
    ↓
STATISTICAL ROBUSTNESS
    ↓
REPLICATION
    ↓
NQTS MAPPING
    ↓
INTEGRATION TEST
    ↓
DECISION

Each stage is governed by an explicit gate.

Possible outcomes:

- PASS — proceed;
- FAIL / KILL — terminate the hypothesis or experiment;
- INCONCLUSIVE — resolve the methodological/data deficiency before proceeding.

---

5. Research Card

Every hypothesis must have a Research Card.

Minimum fields:

Field| Requirement
Research ID| Unique
Hypothesis ID| Unique
Hypothesis| Falsifiable statement
Mechanism| Proposed reason
Observable| Measurable quantity
Null hypothesis| Defined
Alternative| Defined
Universe| Fixed
Timeframe| Fixed
Horizons| Fixed
Models| Pre-declared
Baselines| Pre-declared
Costs| If applicable
Dataset| Defined
Validation| Defined
Metrics| Defined
Kill criteria| Defined
Promotion criteria| Defined

No substantive experiment begins until the Research Card is complete.

---

6. Gate 0 — Research Definition

Objective

Determine whether the proposed research question is sufficiently precise to test.

Required

- falsifiable hypothesis;
- measurable observable;
- explicit causal ordering;
- predefined data requirements;
- predefined models;
- predefined metrics;
- predefined validation method;
- predefined kill criteria.

PASS

All required components exist and are internally consistent.

FAIL

The hypothesis cannot be objectively tested or the protocol permits post-hoc methodological changes.

INCONCLUSIVE

Research design requires clarification before execution.

---

7. Gate 1 — Data Integrity

Objective

Verify that the dataset is suitable for research.

Structural checks

- expected symbols;
- expected timeframe;
- chronological ordering;
- duplicate timestamps;
- missing observations;
- weekend gaps;
- abnormal gaps;
- OHLC consistency;
- timezone consistency.

Statistical checks

- invalid prices;
- zero/constant observations;
- abnormal returns;
- suspicious discontinuities;
- outliers;
- volatility anomalies.

Provenance

Every dataset must record:

- source;
- retrieval period;
- retrieval timestamp;
- decoder/version;
- transformations;
- checksum or equivalent identity;
- dataset version.

PASS

All critical integrity checks pass.

FAIL

Data corruption, provenance failure, or structural problems can materially affect the experiment.

INCONCLUSIVE

Coverage or quality is insufficient to determine validity.

No substantive model research proceeds on failed data.

---

8. Gate 2 — Apparatus and Causality

Objective

Verify that the research implementation faithfully executes the protocol.

Required checks

- imports;
- transformations;
- feature generation;
- horizon encoding;
- target shifting;
- train/test boundaries;
- model fitting;
- edge cases;
- synthetic-data behavior.

Causality invariants

The system must verify that:

- future data cannot affect past forecasts;
- OOS data cannot affect model fitting;
- normalization is fitted only on training data;
- preprocessing does not use future observations;
- regime labels do not contain future information;
- hyperparameter selection does not inspect OOS results.

Gate criterion

100% of critical causality tests must pass.

No exceptions.

This gate is an engineering gate, not a performance gate.

---

9. Gate 3 — Cheap Falsification

Objective

Determine whether the hypothesis has enough evidence to justify expensive research.

Use the simplest valid models first.

Example model family for conditional volatility research

1. Naive
2. Rolling Volatility
3. EWMA
4. GARCH
5. GJR-GARCH
6. HAR-RV

No additional models are introduced opportunistically.

Example horizons for 4H data

1 bar  = 4h
3 bars = 12h
6 bars = 24h
12 bars = 48h

Therefore:

HORIZONS = [1, 3, 6, 12]

Primary metrics

- MAE
- RMSE
- relative improvement versus baseline

Secondary metrics

- directional accuracy where relevant;
- forecast correlation;
- forecast bias;
- error dispersion.

For volatility forecasting, forecast-error metrics are primary. Directional accuracy is secondary.

Kill principle

If all approved models fail to produce meaningful OOS information relative to the appropriate baseline, the hypothesis should normally be killed before expensive model expansion.

The exact numerical threshold must be defined by the experiment protocol rather than selected after results are observed.

---

10. Gate 4 — Primary Causal Out-of-Sample Validation

Objective

Determine whether the phenomenon survives genuinely unseen chronological data.

The primary validation framework is:

- walk-forward validation;
- expanding or rolling training windows as predeclared;
- strictly chronological OOS evaluation.

For every OOS evaluation, record:

- pair;
- model;
- horizon;
- training period;
- OOS period;
- observations;
- MAE;
- RMSE;
- baseline MAE;
- baseline RMSE;
- relative improvement;
- directional accuracy where applicable;
- bias;
- forecast correlation.

Results must remain available at the individual-block level.

Do not report only pooled performance.

---

11. Gate 5 — Temporal Robustness

Temporal robustness has two distinct components.

11.1 Causal temporal robustness

The primary evidence remains chronological walk-forward testing.

This is the deployment-relevant validation.

---

11.2 Blocked Temporal Generalization

A complementary diagnostic may use alternating blocks.

Example:

Partition A

B1 = IS
B2 = OOS
B3 = IS
B4 = OOS
B5 = IS
B6 = OOS

Partition B

B1 = OOS
B2 = IS
B3 = OOS
B4 = IS
B5 = OOS
B6 = IS

This provides an opportunity for every block to be evaluated in an OOS role.

Important methodological rule

Symmetric blocked validation must not be interpreted as causal deployment validation.

If future blocks are used to model earlier blocks, the test is a temporal generalization diagnostic, not a live-like OOS simulation.

Its purpose is to determine whether an apparent relationship is localized to a particular historical segment.

---

12. Block Sizes

Where sufficient data exists, temporal robustness should be tested across predeclared scales:

1. Weekly
2. Monthly
3. Quarterly
4. Semiannual
5. Annual
6. Longer periods where statistically appropriate

Block size must not become an optimization variable.

We do not select the block size that produces the best result.

Instead:

«Block size is a robustness dimension.»

---

13. Temporal Robustness Metrics

For each model/horizon/pair:

Block Hit Rate

[
HR_{block}

\frac{#\text{blocks beating baseline}}
{#\text{valid blocks}}
]

Median Improvement

[
Median(\Delta)
]

Distribution

Record:

- minimum;
- Q1;
- median;
- Q3;
- maximum.

Cross-Pair Consistency

[
HR_{pairs}

\frac{\text{pairs with positive effect}}
{\text{valid pairs}}
]

Temporal Consistency

[
HR_{windows}

\frac{\text{windows with positive effect}}
{\text{valid windows}}
]

Regime Consistency

Fraction of predefined regimes in which the effect survives.

For R2.1, the standing robustness target is:

- «50% of pairs;»
- «50% of windows;»
- «2/3 of regimes.»

These are robustness criteria, not permission to tune the experiment until they are achieved.

---

14. Gate 6 — Statistical Robustness

Objective

Determine whether the observed effect is fragile under reasonable uncertainty.

Monte Carlo is a robustness tool.

It does not replace real unseen OOS evidence.

Approved families

Depending on the hypothesis:

- moving block bootstrap;
- stationary bootstrap;
- circular block bootstrap where appropriate;
- residual simulation;
- parameter perturbation;
- start-date perturbation;
- end-date perturbation;
- training-window perturbation;
- predeclared model perturbations.

Simple random shuffling is generally inappropriate for dependent time series because it destroys temporal structure.

---

15. Monte Carlo Reporting

Each simulation records:

- effect estimate;
- model metric;
- baseline metric;
- improvement;
- block hit rate;
- distribution of outcomes.

Where appropriate:

[
P(\Delta > 0)
]

and uncertainty intervals should be reported.

The central robustness question is:

«How often does the research conclusion change under reasonable perturbations?»

A result that survives most reasonable perturbations is materially different from one that survives only a narrow configuration.

---

16. Multiple Testing

NestQuant research may involve many:

- pairs;
- horizons;
- models;
- periods;
- block sizes;
- metrics;
- hypotheses.

Therefore the research record must distinguish:

Confirmatory tests

Defined before observing results.

Exploratory tests

Performed to investigate an observed phenomenon.

Exploratory discoveries may generate new hypotheses, but they must not be represented as if they were pre-registered confirmations.

Where appropriate, statistical procedures for multiple comparisons must be specified by the experiment protocol.

---

17. Gate 7 — Replication

Objective

Determine whether the result survives independent variation of the research environment.

Replication may vary:

- currency pair;
- historical period;
- market regime;
- validation window;
- model specification;
- independently acquired dataset.

The hypothesis itself must remain unchanged.

A phenomenon that disappears whenever the environment changes is not treated as robust evidence.

---

18. Gate 8 — Economic Relevance

A statistically significant or forecastable phenomenon does not automatically have economic value.

The result must be mapped to its possible function within NestQuant.

Potential categories:

ALPHA
RISK
SIZING
PORTFOLIO
REGIME
EXECUTION
LIQUIDITY
INFRASTRUCTURE
NO ACTIONABLE INFORMATION

Examples:

A volatility forecast might be useful for:

- position sizing;
- leverage;
- stop distance;
- risk budgeting;
- portfolio exposure;
- regime classification.

It does not necessarily need to predict direction.

---

19. Gate 9 — NQTS Integration Test

Only after research validation should integration be investigated.

The candidate information is tested against the frozen NQTS baseline.

Example:

Baseline:

[
PositionSize = f(Risk, ATR)
]

Candidate:

[
PositionSize =
f(Risk, ATR,\widehat{\sigma}_{t+h})
]

The integration experiment evaluates whether the additional information improves the relevant objective.

Depending on the integration, metrics may include:

- return;
- expectancy;
- Sharpe;
- Sortino;
- maximum drawdown;
- tail losses;
- turnover;
- exposure;
- risk stability;
- transaction costs;
- robustness.

Production NQTS remains unchanged during this stage.

---

20. Decision Framework

Outcome| Decision
Data integrity failure| Kill experiment
Causality failure| Kill experiment
Cheap falsification failure| Kill hypothesis
Weak causal OOS| Kill hypothesis
Localized temporal effect| Archive / investigate
Temporal instability| Archive / investigate
Statistical fragility| Archive / investigate
Robust but economically weak| Archive / monitor
Robust + replicated| Candidate
Robust + replicated + NQTS relevance| Integration candidate
Integration survives independent testing| Promotion candidate

Promotion candidate does not mean production-approved.

Production deployment requires a separate decision and validation process.

---

21. Metrics Hierarchy

Metrics are organized by purpose.

Tier 1 — Primary Evidence

Determines whether the hypothesis works.

Examples:

- RMSE
- MAE
- relative improvement
- appropriate probabilistic scoring metrics
- directional accuracy for directional hypotheses

---

Tier 2 — Robustness

Determines whether the result is consistent.

- block hit rate;
- median improvement;
- pair consistency;
- temporal consistency;
- regime consistency;
- dispersion.

---

Tier 3 — Statistical

Determines uncertainty and fragility.

- bootstrap distributions;
- uncertainty intervals;
- P(\Delta>0);
- perturbation sensitivity;
- simulation distributions.

---

Tier 4 — Economic

Determines practical value.

- expectancy;
- Sharpe;
- Sortino;
- maximum drawdown;
- turnover;
- exposure;
- tail loss;
- transaction-cost-adjusted performance.

---

Tier 5 — Operational

Determines implementation feasibility.

- latency;
- data availability;
- computational cost;
- failure rate;
- reproducibility;
- operational complexity.

A Tier 5 advantage cannot override failure in Tier 1.

---

22. Research Budget Principle

Research resources must increase with evidence.

Cheap

Data checks
↓
Causality
↓
Simple models
↓
Simple OOS

Medium

Walk-forward
↓
Multiple pairs
↓
Multiple horizons
↓
Temporal robustness

Expensive

Monte Carlo
↓
Bootstrap
↓
Sensitivity analysis
↓
Replication

Very expensive

NQTS integration
↓
Portfolio testing
↓
Shadow evaluation
↓
Production consideration

A hypothesis that fails an early gate does not receive resources allocated to later gates.

---

23. Research State Machine

The conceptual state machine is:

PROPOSED
   ↓
SPECIFIED
   ↓
DATA_VALIDATED
   ↓
APPARATUS_VALIDATED
   ↓
CHEAP_SCREEN
   ↓
CAUSAL_OOS
   ↓
TEMPORAL_ROBUSTNESS
   ↓
STATISTICAL_ROBUSTNESS
   ↓
REPLICATED
   ↓
NQTS_MAPPED
   ↓
INTEGRATION_TESTED
   ↓
PROMOTION_CANDIDATE

Terminal states:

KILLED
ARCHIVED
INCONCLUSIVE

A terminal state is permanent unless a new experiment is explicitly created.

---

24. Research Ledger

Every experiment must produce a machine-readable research record.

Minimum fields:

research_id
hypothesis_id

dataset_id
dataset_version
data_provenance

code_commit
experiment_version

universe
timeframe
horizons
models
parameters

validation_protocol
block_sizes
bootstrap_method

n_observations

primary_metrics
secondary_metrics

pair_consistency
window_consistency
regime_consistency

statistical_results
monte_carlo_results

gate_0_status
gate_1_status
gate_2_status
gate_3_status
gate_4_status
gate_5_status
gate_6_status
gate_7_status
gate_8_status
gate_9_status

decision
decision_reason
next_action

This creates a durable research memory for NestQuant.

---

25. Experiment Immutability

Once substantive results have been generated, the following must not be silently changed:

- hypothesis;
- dataset definition;
- primary metric;
- validation method;
- kill criteria;
- model family;
- primary horizons.

If a methodological correction is required, create:

1. correction note;
2. updated protocol;
3. regression test where applicable;
4. new experiment/version identifier;
5. explicit record of the previous state.

Historical results must not be silently rewritten.

---

26. Critical Infrastructure Rules

The following are classified as research-critical infrastructure:

- dataset acquisition;
- data decoders;
- timestamp normalization;
- bar construction;
- feature generation;
- target generation;
- horizon encoding;
- train/OOS splitting;
- causality enforcement;
- experiment configuration;
- metric calculation;
- bootstrap/Monte Carlo engines;
- result aggregation;
- research ledger;
- provenance tracking.

Changes to critical infrastructure require stronger controls than ordinary research code.

Required controls

1. Explicit specification before implementation.
2. Unit tests.
3. Causality tests where applicable.
4. Regression tests.
5. Synthetic-data tests.
6. Version-controlled changes.
7. Reproducible execution.
8. Review of generated results after infrastructure changes.
9. No silent modification of historical results.
10. Production isolation.

A critical infrastructure change must be treated as a research methodology change when it can alter experimental conclusions.

---

27. Critical Infrastructure Change Protocol

For any critical infrastructure modification:

CHANGE PROPOSED
      ↓
SPECIFICATION
      ↓
IMPACT ASSESSMENT
      ↓
IMPLEMENTATION
      ↓
UNIT TESTS
      ↓
CAUSALITY / REGRESSION TESTS
      ↓
CONTROLLED VALIDATION
      ↓
COMMIT
      ↓
RESEARCH CONTINUES

If the change can alter previous experimental conclusions:

«Previous results must be explicitly classified as potentially affected.»

They must not simply be overwritten.

---

28. Separation of Concerns

The research system must maintain clear boundaries:

DATA
  ↓
RESEARCH APPARATUS
  ↓
EXPERIMENT
  ↓
RESULT
  ↓
INTERPRETATION
  ↓
NQTS MAPPING
  ↓
PRODUCTION