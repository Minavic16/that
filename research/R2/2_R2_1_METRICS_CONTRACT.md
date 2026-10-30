# R2.1 Metrics Contract

> **Version:** 0.1.0  
> **Date:** 2026-09-21  
> **Status:** Specification  
> **Scope:** Formal metric definitions for R2.1 conditional volatility forecasting experiment  
> **Constraint:** Specification only — no implementation

---

## 0. Preamble

R2.1 is a **conditional volatility forecasting experiment**, not a P&L-generating trading strategy.

Every metric in this document is evaluated against that fact. Metrics that require trades, positions, equity curves, or P&L are explicitly excluded. Metrics that describe forecast quality relative to realized volatility are the primary evaluation surface.

The forward target for all metrics is:

```
RV(t, h) = sqrt( sum(r_{t+1}^2, ..., r_{t+h}^2) )
```

This is realized volatility over the forward window, NOT sample standard deviation. At h=1, this reduces to |r_{t+1}|.

---

## 1. Metric Categories

Every metric is classified into exactly one category:

| Category | Description |
|----------|-------------|
| **A. UNIVERSAL FORECAST METRIC** | Could reasonably be reused by other forecasting experiments (weather, macro, volatility, etc.) |
| **B. R2.1-SPECIFIC EVALUATION METRIC** | Exists because of R2.1's particular hypotheses, design, regime structure, horizons, or validation protocol |
| **C. DATA / EVALUATION-INTEGRITY METRIC** | Describes coverage, missingness, NOT_EVALUABLE, fold integrity, sample counts |
| **D. DIAGNOSTIC / DISPLAY METRIC** | Useful for understanding results but NOT part of formal hypothesis acceptance/rejection |
| **E. P&L / TRADING METRIC** | Explicitly excluded from R2.1 |

---

## 2. Metric Definitions

### 2.1 Forecast Accuracy Metrics

#### 2.1.1 RMSE — Root Mean Squared Error

- **Canonical name:** `rmse`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** Square root of the mean squared forecast error
- **Formula:** `RMSE = sqrt( mean( (f_i - r_i)^2 ) )`
- **Required inputs:** `forecast: np.ndarray`, `realized: np.ndarray`
- **Interpretation:** Average magnitude of forecast error in volatility units. Lower is better.
- **Higher/lower is better:** Lower
- **Granularity:** Per observation (then aggregated)
- **Safely aggregatable:** Yes — pooled RMSE is mathematically valid
- **Formal hypothesis evaluation:** Yes — Tier 1 primary evidence
- **Core engine or reporting:** Core engine

#### 2.1.2 MAE — Mean Absolute Error

- **Canonical name:** `mae`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** Mean of absolute forecast errors
- **Formula:** `MAE = mean( |f_i - r_i| )`
- **Required inputs:** `forecast: np.ndarray`, `realized: np.ndarray`
- **Interpretation:** Robust average error magnitude. Less sensitive to outliers than RMSE. Lower is better.
- **Higher/lower is better:** Lower
- **Granularity:** Per observation
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** Yes — Tier 1 primary evidence
- **Core engine or reporting:** Core engine

#### 2.1.3 QLIKE — Quasi-Likelihood Volatility Loss

- **Canonical name:** `qlike`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** Volatility-specific loss function that penalizes over-forecasting and under-forecasting asymmetrically
- **Formula:** `QLIKE = mean( log(f_i^2) + r_i^2 / f_i^2 )`
- **Required inputs:** `forecast: np.ndarray`, `realized: np.ndarray`, `epsilon: float = 1e-8`
- **Numerical stability:** Apply floor `max(x, epsilon)` to both forecast and realized before computation. Rationale: volatility is strictly positive; values < 1e-8 are effectively zero; this prevents division-by-zero without distorting meaningful values.
- **Interpretation:** Volatility-specific scoring rule. Proper loss function for variance forecasts. Lower is better.
- **Higher/lower is better:** Lower
- **Granularity:** Per observation
- **Safely aggregatable:** Yes (with floor applied consistently)
- **Formal hypothesis evaluation:** Yes — Tier 1 primary evidence
- **Core engine or reporting:** Core engine
- **Underspecification risk:** Without the epsilon floor, QLIKE is undefined when f ≈ 0. The floor value (1e-8) must be documented and fixed before implementation.

#### 2.1.4 R² — Coefficient of Determination

- **Canonical name:** `r_squared`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** Proportion of variance in realized volatility explained by the forecast
- **Formula:** `R² = 1 - SS_res / SS_tot = 1 - sum((f_i - r_i)^2) / sum((r_i - mean(r))^2)`
- **Required inputs:** `forecast: np.ndarray`, `realized: np.ndarray`
- **Interpretation:** How much better the forecast is than simply predicting the mean. R²=1 is perfect; R²=0 is no better than mean; R²<0 is worse than mean.
- **Higher/lower is better:** Higher
- **Granularity:** Per observation
- **Safely aggregatable:** Yes (pooled R² is valid)
- **Formal hypothesis evaluation:** Yes — Tier 1 primary evidence
- **Core engine or reporting:** Core engine
- **Underspecification risk:** R² can be negative and is sensitive to the variance of the realized series. When realized variance is very low (quiet markets), R² can be unstable. Report with caveat.

#### 2.1.5 Direction Accuracy — Forecast-Realized Correlation

- **Canonical name:** `direction_accuracy`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** Pearson correlation between forecast and realized volatility series
- **Formula:** `direction_accuracy = corrcoef(f, r)[0,1]`
- **Required inputs:** `forecast: np.ndarray`, `realized: np.ndarray`
- **Interpretation:** Linear association between forecast and realized. Measures whether the forecast moves in the same direction as realized volatility. +1 = perfect positive correlation, 0 = no correlation, -1 = negative correlation.
- **Higher/lower is better:** Higher (closer to +1)
- **Granularity:** Per observation (correlation is computed over a series)
- **Safely aggregatable:** NO — correlation computed on pooled data can mask per-fold or per-pair heterogeneity. Must report per-unit first.
- **Formal hypothesis evaluation:** Yes — Tier 2 robustness
- **Core engine or reporting:** Core engine
- **Note:** This is NOT "direction accuracy" in the binary sense (did vol go up or down?). It is the Pearson correlation coefficient. The name is inherited from R2.1 spec §H1 Tier 2.

#### 2.1.6 Mean Error / Forecast Bias

- **Canonical name:** `forecast_bias`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** Average of forecast errors (forecast minus realized)
- **Formula:** `bias = mean( f_i - r_i )`
- **Required inputs:** `forecast: np.ndarray`, `realized: np.ndarray`
- **Interpretation:** Systematic tendency to over-forecast (positive) or under-forecast (negative). Zero is unbiased.
- **Higher/lower is better:** Closer to zero is better
- **Granularity:** Per observation
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** No — diagnostic only. Bias is informative but not part of the falsification criteria.
- **Core engine or reporting:** Reporting layer
- **Why diagnostic:** R2.1's falsification criteria use RMSE improvement and block hit rate, not bias. Bias helps interpret results but doesn't determine acceptance/rejection.

#### 2.1.7 Mean Squared Error

- **Canonical name:** `mse`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** Mean of squared forecast errors
- **Formula:** `MSE = mean( (f_i - r_i)^2 )`
- **Required inputs:** `forecast: np.ndarray`, `realized: np.ndarray`
- **Interpretation:** RMSE without the square root. Redundant with RMSE — included only for completeness.
- **Higher/lower is better:** Lower
- **Granularity:** Per observation
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** No — redundant with RMSE
- **Core engine or reporting:** Reporting layer
- **Redundancy flag:** MSE is the square of RMSE. Including both adds no information. If RMSE is computed, MSE is unnecessary. Recommend computing RMSE only.

---

### 2.2 Baseline Comparison Metrics

#### 2.2.1 Naive Baseline Error

- **Canonical name:** `naive_error`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** RMSE of the naive (persistence) model: forecast = last observed |return|
- **Formula:** Same as RMSE but computed for the naive model's forecasts
- **Required inputs:** `forecast: np.ndarray`, `realized: np.ndarray`
- **Interpretation:** The "do nothing" baseline. Any model must beat this to have value.
- **Higher/lower is better:** Lower
- **Granularity:** Per fold (this IS a model, not a metric per se, but its error serves as a reference)
- **Safely aggregatable:** Yes (pooled naive error is valid)
- **Formal hypothesis evaluation:** Yes — the baseline against which improvement is measured
- **Core engine or reporting:** Core engine

#### 2.2.2 Rolling-Vol Baseline Error

- **Canonical name:** `rolling_vol_error`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** RMSE of the rolling-window standard deviation baseline
- **Formula:** Same as RMSE for the rolling vol model's forecasts
- **Required inputs:** Rolling vol forecasts, realized
- **Interpretation:** The "simple statistical" baseline. Models must beat this to demonstrate conditional structure.
- **Higher/lower is better:** Lower
- **Granularity:** Per fold
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** Yes — reference baseline
- **Core engine or reporting:** Core engine

#### 2.2.3 EWMA Baseline Error

- **Canonical name:** `ewma_error`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** RMSE of the EWMA baseline
- **Formula:** Same as RMSE for the EWMA model's forecasts
- **Required inputs:** EWMA forecasts, realized
- **Interpretation:** The "exponentially weighted" baseline. Captures recent volatility trend.
- **Higher/lower is better:** Lower
- **Granularity:** Per fold
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** Yes — reference baseline
- **Core engine or reporting:** Core engine

#### 2.2.4 Model Error (Absolute)

- **Canonical name:** `model_error`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** RMSE of a specific test model (GARCH, GJR-GARCH, HAR-RV, etc.)
- **Formula:** Same as RMSE for the test model
- **Required inputs:** Model forecasts, realized
- **Interpretation:** Raw error of the model being evaluated.
- **Higher/lower is better:** Lower
- **Granularity:** Per model/horizon/pair/fold
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** Yes — the thing being evaluated
- **Core engine or reporting:** Core engine

#### 2.2.5 Absolute Improvement vs Baseline

- **Canonical name:** `absolute_improvement`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** Difference in error between baseline and model
- **Formula:** `Δ_abs = RMSE_baseline - RMSE_model`
- **Required inputs:** `rmse_baseline: float`, `rmse_model: float`
- **Interpretation:** How many volatility-units the model improves over baseline. Positive = model is better.
- **Higher/lower is better:** Higher (more positive)
- **Granularity:** Per model/horizon/pair/fold
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** Yes — used in Tier 2 consistency metrics
- **Core engine or reporting:** Core engine
- **Underspecification risk:** Absolute improvement is in volatility units (e.g., 0.001), which are hard to interpret across different volatility regimes. Relative improvement (§2.2.6) is more interpretable.

#### 2.2.6 Relative Improvement vs Baseline

- **Canonical name:** `relative_improvement`
- **Category:** A. UNIVERSAL FORECAST METRIC
- **Definition:** Percentage improvement of model error over baseline error
- **Formula:** `Δ_rel = 1 - (RMSE_model / RMSE_baseline)`
- **Required inputs:** `rmse_baseline: float`, `rmse_model: float`
- **Interpretation:** Percentage by which the model beats the baseline. +5% means model RMSE is 5% lower than baseline.
- **Higher/lower is better:** Higher (more positive)
- **Granularity:** Per model/horizon/pair/fold
- **Safely aggregatable:** Yes (mean relative improvement is valid)
- **Formal hypothesis evaluation:** Yes — Tier 1 primary evidence. R2.1's falsification criteria require >5% relative improvement.
- **Core engine or reporting:** Core engine
- **Why R2.1-specific:** The 5% threshold is R2.1-specific (from falsification criteria), but the metric itself is universal.

---

### 2.3 R2.1 Experimental Metrics

#### 2.3.1 Block Hit Rate

- **Canonical name:** `block_hit_rate`
- **Category:** B. R2.1-SPECIFIC EVALUATION METRIC
- **Definition:** Fraction of walk-forward folds (blocks) where the test model's error is lower than the best baseline's error
- **Formula:** `block_hit_rate = n_folds_beating_best_baseline / n_valid_folds`
- **Required inputs:** Per-fold RMSE for each model and baseline
- **Interpretation:** How consistently the model beats the baseline across time. 1.0 = beats baseline in every fold; 0.0 = never beats baseline.
- **Higher/lower is better:** Higher
- **Granularity:** Per model/horizon/pair (aggregated across folds)
- **Safely aggregatable:** NO — block hit rate must be reported per model/horizon/pair first, then aggregated. Pooling across pairs or horizons can mask heterogeneity.
- **Formal hypothesis evaluation:** Yes — R2.1 falsification criterion: >50% of pairs must have positive block hit rate
- **Core engine or reporting:** Core engine
- **Why R2.1-specific:** The block structure (alternating IS/OOS, fold-relative regimes) is R2.1's validation architecture. Other forecasting experiments may use different block definitions.

#### 2.3.2 Pair Consistency

- **Canonical name:** `pair_consistency`
- **Category:** B. R2.1-SPECIFIC EVALUATION METRIC
- **Definition:** Fraction of currency pairs where the model achieves positive relative improvement over the best baseline (averaged across folds)
- **Formula:** `pair_consistency = n_pairs_with_positive_effect / n_valid_pairs`
- **Required inputs:** Per-pair mean relative improvement
- **Interpretation:** How broadly the model works across instruments. High pair consistency = model is not cherry-picked for one pair.
- **Higher/lower is better:** Higher
- **Granularity:** Per model/horizon (aggregated across pairs)
- **Safely aggregatable:** NO — must report per-pair results first
- **Formal hypothesis evaluation:** Yes — R2.1 falsification criterion: >50% of pairs (≥10 of 20)
- **Core engine or reporting:** Core engine
- **Why R2.1-specific:** The 20-pair universe and the 50% threshold are R2.1-specific design choices.

#### 2.3.3 Regime Consistency

- **Canonical name:** `regime_consistency`
- **Category:** B. R2.1-SPECIFIC EVALUATION METRIC
- **Definition:** Fraction of predefined volatility regimes where the model achieves positive relative improvement over the best baseline
- **Formula:** `regime_consistency = n_regimes_with_positive_effect / n_predefined_regimes`
- **Required inputs:** Per-regime mean relative improvement, regime taxonomy: LOW_VOL, MEDIUM_VOL, HIGH_VOL
- **Interpretation:** Whether the model works across market conditions, not just in one regime.
- **Higher/lower is better:** Higher
- **Granularity:** Per model/horizon/pair (aggregated across regimes)
- **Safely aggregatable:** NO — must report per-regime results first
- **Formal hypothesis evaluation:** Yes — R2.1 robustness target: ≥2/3 of regimes
- **Core engine or reporting:** Core engine
- **Why R2.1-specific:** The regime taxonomy (fold-relative training-derived volatility terciles) and the 2/3 threshold are R2.1-specific.

#### 2.3.4 OOS Degradation

- **Canonical name:** `oos_degradation`
- **Category:** B. R2.1-SPECIFIC EVALUATION METRIC
- **Definition:** Ratio of OOS error to IS error, measuring how much performance degrades on unseen data
- **Formula:** `oos_degradation = RMSE_OOS / RMSE_IS`
- **Required inputs:** `rmse_is: float`, `rmse_oos: float`
- **Interpretation:** <1.0 = OOS is better than IS (unusual); =1.0 = no degradation; >1.0 = OOS is worse. High degradation suggests overfitting.
- **Higher/lower is better:** Lower (closer to 1.0 or below)
- **Granularity:** Per model/horizon/pair
- **Safely aggregatable:** Yes (mean degradation is valid)
- **Formal hypothesis evaluation:** Yes — R2.1 stability criteria require degradation within acceptable bounds
- **Core engine or reporting:** Core engine
- **Why R2.1-specific:** The IS/OOS split is defined by R2.1's walk-forward architecture. Other experiments may define IS/OOS differently.

#### 2.3.5 Fold Dispersion

- **Canonical name:** `fold_dispersion`
- **Category:** B. R2.1-SPECIFIC EVALUATION METRIC
- **Definition:** Interquartile range (IQR) of per-fold relative improvements
- **Formula:** `fold_dispersion = IQR( Δ_rel_1, Δ_rel_2, ..., Δ_rel_n )`
- **Required inputs:** Per-fold relative improvement values
- **Interpretation:** How variable the model's performance is across folds. Low dispersion = consistent; high dispersion = unstable.
- **Higher/lower is better:** Lower
- **Granularity:** Per model/horizon/pair
- **Safely aggregatable:** NO — dispersion is inherently a distributional measure
- **Formal hypothesis evaluation:** Yes — Tier 2 robustness (from R2.1 spec §H1 Tier 2: "Dispersion: IQR of per-block improvements")
- **Core engine or reporting:** Core engine
- **Why R2.1-specific:** The fold structure is R2.1's walk-forward architecture.

#### 2.3.6 Median Fold Performance

- **Canonical name:** `median_fold_performance`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** Median of per-fold relative improvements
- **Formula:** `median(Δ_rel_1, ..., Δ_rel_n)`
- **Required inputs:** Per-fold relative improvement values
- **Interpretation:** Typical performance across folds. More robust than mean (resistant to outliers).
- **Higher/lower is better:** Higher
- **Granularity:** Per model/horizon/pair
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** No — diagnostic. The mean relative improvement is used for formal evaluation; the median is for understanding distribution shape.
- **Core engine or reporting:** Reporting layer
- **Why diagnostic:** R2.1's falsification criteria use block hit rate and pair consistency, not median fold performance.

#### 2.3.7 Worst Fold

- **Canonical name:** `worst_fold`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** Minimum per-fold relative improvement (worst-performing fold)
- **Formula:** `min(Δ_rel_1, ..., Δ_rel_n)`
- **Required inputs:** Per-fold relative improvement values
- **Interpretation:** Worst-case performance. If worst fold is very negative, the model may fail catastrophically in some periods.
- **Higher/lower is better:** Higher (less negative)
- **Granularity:** Per model/horizon/pair
- **Safely aggregatable:** NO
- **Formal hypothesis evaluation:** No — diagnostic
- **Core engine or reporting:** Reporting layer
- **Why diagnostic:** R2.1's falsification criteria don't reference worst fold. It helps interpret stability but doesn't determine acceptance/rejection.

#### 2.3.8 Best Fold

- **Canonical name:** `best_fold`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** Maximum per-fold relative improvement
- **Formula:** `max(Δ_rel_1, ..., Δ_rel_n)`
- **Required inputs:** Per-fold relative improvement values
- **Interpretation:** Best-case performance. Paired with worst fold to show the full range.
- **Higher/lower is better:** Higher
- **Granularity:** Per model/horizon/pair
- **Safely aggregatable:** NO
- **Formal hypothesis evaluation:** No — diagnostic
- **Core engine or reporting:** Reporting layer

---

### 2.4 Data / Evaluation-Integrity Metrics

#### 2.4.1 NOT_EVALUABLE Rate

- **Canonical name:** `not_evaluable_rate`
- **Category:** C. DATA / EVALUATION-INTEGRITY METRIC
- **Definition:** Fraction of block sizes that are NOT_EVALUABLE for a given pair (because n_bars / block_size < 3)
- **Formula:** `not_evaluable_rate = n_not_evaluable_block_sizes / n_total_block_sizes`
- **Required inputs:** Per-block-size feasibility check results
- **Interpretation:** How much of the robustness analysis is achievable for this pair. High rate = limited data for large block sizes.
- **Higher/lower is better:** Lower (more blocks are evaluable)
- **Granularity:** Per pair (block sizes are global)
- **Safely aggregatable:** Yes (across pairs)
- **Formal hypothesis evaluation:** No — integrity metric. Used to assess data sufficiency, not model quality.
- **Core engine or reporting:** Core engine
- **Why R2.1-specific:** The block size definitions and the NOT_EVALUABLE threshold (< 3 blocks) are R2.1-specific.

#### 2.4.2 Evaluation Coverage

- **Canonical name:** `evaluation_coverage`
- **Category:** C. DATA / EVALUATION-INTEGRITY METRIC
- **Definition:** Fraction of (model, horizon, pair, block_size) combinations that were successfully evaluated
- **Formula:** `coverage = n_successful_evaluations / n_planned_evaluations`
- **Required inputs:** Count of successful vs planned evaluations
- **Interpretation:** Whether the full experimental matrix was completed. Low coverage = missing results, possibly due to data issues or model failures.
- **Higher/lower is better:** Higher
- **Granularity:** Global (per experiment run)
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** No — integrity metric
- **Core engine or reporting:** Core engine

#### 2.4.3 Fold Count

- **Canonical name:** `n_folds`
- **Category:** C. DATA / EVALUATION-INTEGRITY METRIC
- **Definition:** Number of valid folds for a given model/horizon/pair/block_size combination
- **Formula:** Count of non-NOT_EVALUABLE folds
- **Required inputs:** Fold metadata
- **Interpretation:** Sample size for statistical inference. More folds = more reliable metrics.
- **Higher/lower is better:** Higher (more data)
- **Granularity:** Per model/horizon/pair/block_size
- **Safely aggregatable:** No (each combination has its own count)
- **Formal hypothesis evaluation:** No — integrity metric, but determines whether other metrics are trustworthy
- **Core engine or reporting:** Core engine

#### 2.4.4 Convergence Rate

- **Canonical name:** `convergence_rate`
- **Category:** C. DATA / EVALUATION-INTEGRITY METRIC
- **Definition:** Fraction of model fits that converged successfully (GARCH/GJR-GARCH only; baselines always converge)
- **Formula:** `convergence_rate = n_converged_fits / n_total_fits`
- **Required inputs:** ModelDiagnostics.converged for each fit
- **Interpretation:** Whether the model can be estimated reliably on the available data. Low convergence = model is unsuitable for this data.
- **Higher/lower is better:** Higher
- **Granularity:** Per model/pair
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** No — integrity metric, but informs model eligibility
- **Core engine or reporting:** Core engine

---

### 2.5 Diagnostic / Display Metrics (Additional)

#### 2.5.1 Per-Fold RMSE

- **Canonical name:** `fold_rmse`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** RMSE computed on a single fold's OOS data
- **Formula:** Same as RMSE but scoped to one fold
- **Required inputs:** Per-fold forecast/realized pairs
- **Interpretation:** Per-fold error. Used to compute block hit rate and fold dispersion.
- **Higher/lower is better:** Lower
- **Granularity:** Per fold
- **Safely aggregatable:** Yes (to pooled RMSE)
- **Formal hypothesis evaluation:** No — input to other metrics, not evaluated directly
- **Core engine or reporting:** Core engine (intermediate)

#### 2.5.2 Per-Fold Relative Improvement

- **Canonical name:** `fold_relative_improvement`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** Relative improvement of model over best baseline within a single fold
- **Formula:** Same as relative improvement but scoped to one fold
- **Required inputs:** Per-fold RMSE for model and best baseline
- **Interpretation:** Per-fold improvement. Used to compute block hit rate, fold dispersion, median/best/worst fold.
- **Higher/lower is better:** Higher
- **Granularity:** Per fold
- **Safely aggregatable:** Yes (to mean improvement)
- **Formal hypothesis evaluation:** No — input to other metrics
- **Core engine or reporting:** Core engine (intermediate)

#### 2.5.3 Per-Pair Mean Relative Improvement

- **Canonical name:** `pair_mean_improvement`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** Mean of per-fold relative improvements for a given pair
- **Formula:** `mean(fold_relative_improvement_1, ..., fold_relative_improvement_n)`
- **Required inputs:** Per-fold relative improvements
- **Interpretation:** Average performance on a specific pair. Used to compute pair consistency.
- **Higher/lower is better:** Higher
- **Granularity:** Per pair
- **Safely aggregatable:** Yes (to mean across pairs)
- **Formal hypothesis evaluation:** No — input to pair consistency
- **Core engine or reporting:** Core engine (intermediate)

#### 2.5.4 Per-Regime Mean Relative Improvement

- **Canonical name:** `regime_mean_improvement`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** Mean of per-fold relative improvements for a given regime
- **Formula:** `mean(fold_relative_improvement for folds in regime)`
- **Required inputs:** Per-fold relative improvements, regime labels
- **Interpretation:** Average performance in a specific regime. Used to compute regime consistency.
- **Higher/lower is better:** Higher
- **Granularity:** Per regime
- **Safely aggregatable:** Yes (to mean across regimes)
- **Formal hypothesis evaluation:** No — input to regime consistency
- **Core engine or reporting:** Core engine (intermediate)

#### 2.5.5 Pooled RMSE

- **Canonical name:** `pooled_rmse`
- **Category:** D. DIAGNOSTIC / DISPLAY METRIC
- **Definition:** RMSE computed on all OOS data pooled across folds
- **Formula:** Same as RMSE but on concatenated OOS data
- **Required inputs:** All fold forecast/realized pairs
- **Interpretation:** Overall error across all folds. Should only be reported AFTER per-fold results.
- **Higher/lower is better:** Lower
- **Granularity:** Per model/horizon/pair (pooled across folds)
- **Safely aggregatable:** Yes
- **Formal hypothesis evaluation:** No — per R2.1 spec §G6: "Never pool results across pairs, horizons, or time windows without first reporting per-unit results"
- **Core engine or reporting:** Reporting layer
- **Risk:** Pooled RMSE can mask unstable per-fold behavior. Must always be accompanied by per-fold results.

---

### 2.6 Excluded Metrics (Category E: P&L / Trading)

The following metrics are **explicitly excluded from R2.1** because R2.1 does not generate trades:

| Metric | Why Excluded |
|--------|-------------|
| Sharpe Ratio | Requires P&L; R2.1 produces forecast errors, not returns |
| Sortino Ratio | Requires P&L; R2.1 produces forecast errors |
| Maximum Drawdown | Requires equity curve; R2.1 has no positions |
| Win Rate | Requires trades; R2.1 produces forecasts |
| Profit Factor | Requires P&L; R2.1 produces forecasts |
| Expectancy | Requires P&L; R2.1 produces forecasts |
| Turnover | Requires trades; R2.1 produces forecasts |
| Exposure | Requires positions; R2.1 has no positions |
| Tail Loss | Requires P&L distribution; R2.1 produces forecast error distribution |
| Latency | Execution concern; R2.1 is offline research |
| Slippage | Execution concern; R2.1 is offline research |
| Fill Rate | Execution concern; R2.1 is offline research |
| Transaction-Cost-Adjusted Return | Requires P&L; R2.1 produces forecasts |
| Capacity / Correlation / Cost Sensitivity | Strategy-evaluation concern; R2.1 is information-gathering |
| Prop-Firm Breach Probability | Live-trading concern; R2.1 is research |

---

## 3. Formal Hypothesis Evaluation Criteria

The following metrics are used in R2.1's formal falsification/survival criteria (from `R2.1_EXPERIMENT_DESIGN.md`):

### H2 Falsification (H2 dies if ALL hold):

1. No test model improves RMSE over best baseline by >5% (relative improvement < 0.05)
2. AND improvement is NOT stable across: ≥10 of 20 pairs, ≥3 of 4 time windows, ≥2 of 3 regimes
3. AND direction accuracy is no better than random (correlation ≈ 0)

### H2 Survival (H2 survives if ANY hold):

1. At least one model improves RMSE by >5% AND improvement is stable across pairs/time/regimes
2. OR direction accuracy > 55% AND stable
3. OR economic evaluation shows position sizing improvement AND stable

**Metrics used for formal evaluation:**
- `relative_improvement` (RMSE-based) — Tier 1
- `pair_consistency` — Tier 2
- `regime_consistency` — Tier 2
- `block_hit_rate` — Tier 2
- `direction_accuracy` (correlation) — Tier 2
- `oos_degradation` — stability criteria

---

## 4. Aggregation Rules

Per R2.1 spec §G6: "Never pool results across pairs, horizons, or time windows without first reporting per-unit results."

### Required reporting order:

1. **Per fold** → per model → per horizon → per pair
2. **Per pair** → per model → per horizon
3. **Per horizon** → per model
4. **Pooled** → per model

Each level must be available independently. Pooled metrics must not hide unstable per-block behavior.

### Metrics that CANNOT be safely pooled:

| Metric | Reason |
|--------|--------|
| `direction_accuracy` | Correlation computed on pooled data can mask per-fold heterogeneity |
| `fold_dispersion` | Dispersion is inherently a distributional measure |
| `worst_fold` | Range metric, not aggregatable |
| `best_fold` | Range metric, not aggregatable |
| `regime_consistency` | Must report per-regime first |
| `pair_consistency` | Must report per-pair first |
| `block_hit_rate` | Must report per-pair first |

### Metrics that CAN be safely pooled:

| Metric | Reason |
|--------|--------|
| `rmse` | Pooled RMSE is mathematically valid |
| `mae` | Pooled MAE is valid |
| `r_squared` | Pooled R² is valid |
| `relative_improvement` | Mean relative improvement is valid |
| `oos_degradation` | Mean degradation is valid |
| `qlike` | Pooled QLIKE is valid (with consistent floor) |

---

## 5. Redundancy Flags

| Pair | Redundancy | Recommendation |
|------|------------|----------------|
| MSE and RMSE | MSE = RMSE². Computing both adds no information. | Compute RMSE only. MSE is redundant. |
| Absolute Improvement and Relative Improvement | Both measure model-beats-baseline, but relative is more interpretable across volatility regimes. | Compute both, but use relative for formal evaluation. |
| Mean Relative Improvement and Median Fold Performance | Mean is used for formal evaluation; median is a robustness check. | Compute both. Mean for formal, median for diagnostic. |

---

## 6. Underspecified or Potentially Misleading Metrics

| Metric | Issue | Recommendation |
|--------|-------|----------------|
| QLIKE | Undefined when f ≈ 0 (division by zero). | Apply epsilon floor (1e-8). Document floor value. |
| R² | Can be negative. When realized variance is very low, R² is unstable. | Report with caveat. Negative R² means model is worse than predicting the mean. |
| Direction Accuracy (correlation) | Named "direction accuracy" but is Pearson correlation, not binary direction. | Document that this is correlation, not binary accuracy. |
| Block Hit Rate | Requires defining "best baseline" — which baseline? | Define: best baseline = lowest RMSE among naive, rolling, EWMA for that fold. Document. |
| OOS Degradation | When RMSE_IS = 0 (perfect IS fit), degradation is undefined. | Handle: if RMSE_IS < epsilon, set degradation to a large sentinel value. |
| Fold Dispersion (IQR) | IQR can be unstable with very few folds (< 5). | Report fold count alongside dispersion. Flag when n_folds < 5. |

---

## 7. Implementation Location

All metrics are implemented in `apparatus/evaluation/metrics.py`.

The metrics engine takes `WalkForwardResult` (from `apparatus/evaluation/walk_forward.py`) as input and produces a `MetricsReport` dataclass containing all metrics at all granularities.

```python
@dataclass
class FoldMetrics:
    """Metrics for a single fold."""
    fold_index: int
    rmse: float
    mae: float
    qlike: float
    r_squared: float
    direction_accuracy: float
    forecast_bias: float
    relative_improvement: float  # vs best baseline

@dataclass
class PairMetrics:
    """Metrics aggregated across folds for one pair."""
    pair: str
    mean_rmse: float
    mean_mae: float
    mean_qlike: float
    mean_r_squared: float
    mean_direction_accuracy: float
    mean_forecast_bias: float
    block_hit_rate: float
    mean_relative_improvement: float
    fold_dispersion: float  # IQR of per-fold improvements
    median_fold_performance: float
    worst_fold: float
    best_fold: float
    n_folds: int

@dataclass
class HorizonMetrics:
    """Metrics aggregated across pairs for one horizon."""
    horizon: int
    pair_consistency: float
    mean_rmse: float
    mean_relative_improvement: float
    per_pair: dict[str, PairMetrics]

@modelMetrics:
    """Metrics for one model across all horizons and pairs."""
    model_name: str
    per_horizon: dict[int, HorizonMetrics]
    regime_consistency: float
    oos_degradation: float

@dataclass
class MetricsReport:
    """Complete metrics report for an experiment run."""
    per_model: dict[str, ModelMetrics]
    not_evaluable_rate: float
    evaluation_coverage: float
    convergence_rate: float
```

---

*End of R2.1 Metrics Contract*
