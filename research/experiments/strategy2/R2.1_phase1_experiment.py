"""
R2.1 Phase 1 — Volatility Structure Experiment
================================================

One pair (EUR/USD). Minimal implementation.
Prove the measurement apparatus is correct before making scientific claims.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Add experiment directory to path
EXPERIMENT_DIR = Path(__file__).parent
sys.path.insert(0, str(EXPERIMENT_DIR))

from data_loader import (
    load_bars,
    compute_log_returns,
    realized_volatility,
    compute_atr,
    generate_synthetic_ohlcv,
    validate_data,
)
from volatility_models import (
    NaiveModel,
    RollingVolModel,
    EWMAModel,
    GARCHModel,
    GJRGARCHModel,
    HARModel,
    walk_forward_evaluate,
    compute_metrics,
    compute_improvement_over_baseline,
)
from causality_tests import run_causality_tests


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PAIR = "EUR/USD"
TRAIN_WINDOW = 24  # 4 days at 4H
HORIZONS = [1, 3, 6, 12]  # 4h, 12h, 24h, 48h at 4H (per R2.1_EXPERIMENT_DESIGN.md)
RESULTS_DIR = EXPERIMENT_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Phase 1 Report Sections
# ---------------------------------------------------------------------------

def section_a_data_definition(df: pd.DataFrame) -> str:
    """A. Data Definition."""
    close = df["close"]
    returns = compute_log_returns(close)

    report = []
    report.append("=" * 70)
    report.append("A. DATA DEFINITION")
    report.append("=" * 70)
    report.append(f"\nPair: {PAIR}")
    report.append(f"Bars: {len(df)}")
    report.append(f"Period: {df.index[0]} to {df.index[-1]}")
    report.append(f"Frequency: 4H")
    report.append(f"\nReturn definition:")
    report.append(f"  r_t = log(close_t / close_{{t-1}})")
    report.append(f"  Return range: [{returns.min():.6f}, {returns.max():.6f}]")
    report.append(f"  Return mean: {returns.mean():.6f}")
    report.append(f"  Return std: {returns.std():.6f}")
    report.append(f"\nRealized volatility (target):")
    report.append(f"  sigma_t = std(r_{{t-window+1}}, ..., r_t)")
    report.append(f"  Using close-to-close log-returns")
    report.append(f"\nATR definition:")
    atr = compute_atr(df["high"], df["low"], df["close"], period=14)
    report.append(f"  ATR_{{14}} last value: {atr.iloc[-1]:.6f}")
    report.append(f"\nForecast horizons: {HORIZONS} bars ({[h*4 for h in HORIZONS]} hours)")
    report.append(f"Training window: {TRAIN_WINDOW} bars ({TRAIN_WINDOW*4} hours)")
    report.append(f"Test window: remainder after training")
    return "\n".join(report)


def section_b_model_definition() -> str:
    """B. Model Definition."""
    report = []
    report.append("\n" + "=" * 70)
    report.append("B. MODEL DEFINITION")
    report.append("=" * 70)

    report.append("\n--- Baseline 1: Naive (Persistence) ---")
    report.append("  sigma_hat_{{t+1}} = |r_t|")
    report.append("  No parameters to estimate")

    report.append("\n--- Baseline 2: Rolling Volatility ---")
    report.append("  sigma_hat_{{t+1}} = std(r_{{t-W+1}}, ..., r_t)")
    report.append(f"  Windows tested: [6, 12, 24, 48] bars")

    report.append("\n--- Baseline 3: EWMA ---")
    report.append("  sigma_hat_{{t+1}} = EWMA(span=lambda) of |r|")
    report.append(f"  Spans tested: [6, 12, 24] bars")

    report.append("\n--- Model 1: GARCH(1,1) ---")
    report.append("  sigma_t^2 = omega + alpha * epsilon_{{t-1}}^2 + beta * sigma_{{t-1}}^2")
    report.append("  Estimated by MLE via arch package")
    report.append("  Returns scaled to percentage for numerical stability")

    report.append("\n--- Model 2: GJR-GARCH(1,1) ---")
    report.append("  sigma_t^2 = omega + (alpha + gamma * I_{{t-1}}) * epsilon_{{t-1}}^2 + beta * sigma_{{t-1}}^2")
    report.append("  Asymmetric term captures leverage effect")

    report.append("\n--- Model 3: HAR-RV ---")
    report.append("  RV_{{t+h}} = c + beta_d * RV_t(daily) + beta_w * RV_t(weekly) + beta_l * RV_t(monthly)")
    report.append("  Multi-timescale volatility model")
    report.append("  daily=6 bars, weekly=30 bars, monthly=90 bars")

    return "\n".join(report)


def section_c_causality_audit(df: pd.DataFrame) -> str:
    """C. Causality Audit."""
    report = []
    report.append("\n" + "=" * 70)
    report.append("C. CAUSALITY AUDIT")
    report.append("=" * 70)
    report.append("\nAll models and transformations must satisfy:")
    report.append("  forecast_t = f(data_{{<= t}})")
    report.append("  forecast_t NEVER sees data_{{> t}}")
    report.append("\nTest methodology:")
    report.append("  1. Modify future data (last 5 observations)")
    report.append("  2. Verify past outputs are unchanged")
    report.append("  3. Verify train/test boundaries are strictly temporal")
    report.append("  4. Verify walk-forward loop has no overlap")
    report.append("  5. Verify on synthetic data with known structure")

    results = run_causality_tests(df, PAIR)

    report.append("\n--- Test Results ---")
    all_passed = True
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        report.append(f"  {status}: {r.name}")
        report.append(f"         {r.detail}")
        if not r.passed:
            all_passed = False

    report.append(f"\n  Total: {sum(1 for r in results if r.passed)}/{len(results)} passed")
    if all_passed:
        report.append("  CAUSALITY VERIFIED: All models are strictly causal.")
    else:
        report.append("  CAUSALITY FAILED: Some models may use future information.")

    return "\n".join(report)


def section_d_one_pair_validation(df: pd.DataFrame) -> str:
    """D. One-Pair Validation."""
    report = []
    report.append("\n" + "=" * 70)
    report.append("D. ONE-PAIR VALIDATION (EUR/USD)")
    report.append("=" * 70)

    returns = compute_log_returns(df["close"])

    # Test each model individually
    models = [
        NaiveModel(),
        RollingVolModel(window=6),
        RollingVolModel(window=12),
        RollingVolModel(window=24),
        EWMAModel(span=12),
        EWMAModel(span=24),
        GARCHModel(),
        GJRGARCHModel(),
        HARModel(),
    ]

    report.append("\n--- Model Execution ---")
    for model in models:
        try:
            model.fit(returns.dropna())
            forecast = model.forecast()
            report.append(f"  OK: {model.name:20s} forecast={forecast:.6f}")
        except Exception as e:
            report.append(f"  FAIL: {model.name:20s} error={e}")

    return "\n".join(report)


def section_e_test_results(df: pd.DataFrame) -> str:
    """E. Test Results."""
    report = []
    report.append("\n" + "=" * 70)
    report.append("E. TEST RESULTS")
    report.append("=" * 70)

    returns = compute_log_returns(df["close"]).dropna()

    # Build model list
    models = [
        NaiveModel(),
        RollingVolModel(window=6),
        RollingVolModel(window=12),
        RollingVolModel(window=24),
        RollingVolModel(window=48),
        EWMAModel(span=6),
        EWMAModel(span=12),
        EWMAModel(span=24),
        GARCHModel(),
        GJRGARCHModel(),
    ]

    for horizon in HORIZONS:
        report.append(f"\n--- Horizon: {horizon} bars ({horizon*4}h) ---")

        # Skip if insufficient data
        if len(returns) < TRAIN_WINDOW + horizon + 10:
            report.append(f"  Insufficient data for horizon {horizon} (need {TRAIN_WINDOW + horizon + 10}, have {len(returns)})")
            continue

        results_df = walk_forward_evaluate(
            returns=returns,
            models=[type(m)() for m in models],  # fresh instances
            target_horizon=horizon,
            train_window=TRAIN_WINDOW,
            step=1,
        )

        if results_df.empty:
            report.append("  No forecasts generated")
            continue

        metrics = compute_metrics(results_df)
        metrics = compute_improvement_over_baseline(metrics, baseline_name="rolling_vol_24")

        report.append(f"\n  {'Model':<20s} {'RMSE':>10s} {'RMSE imp':>10s} {'MAE':>10s} {'Corr':>8s} {'N':>5s}")
        report.append("  " + "-" * 65)

        for _, row in metrics.iterrows():
            imp = row.get("rmse_improvement", float("nan"))
            imp_str = f"{imp:+.1%}" if not np.isnan(imp) else "N/A"
            corr_str = f"{row['direction_accuracy']:.3f}" if not np.isnan(row['direction_accuracy']) else "N/A"
            report.append(
                f"  {row['model']:<20s} {row['rmse']:>10.6f} {imp_str:>10s} "
                f"{row['mae']:>10.6f} {corr_str:>8s} {int(row['n_forecasts']):>5d}"
            )

    return "\n".join(report)


def section_f_research_readiness(df: pd.DataFrame, causality_results: list) -> str:
    """F. Research Readiness."""
    report = []
    report.append("\n" + "=" * 70)
    report.append("F. RESEARCH READINESS ASSESSMENT")
    report.append("=" * 70)

    # Check causality
    all_causal = all(r.passed for r in causality_results)
    report.append(f"\n  Causality: {'VERIFIED' if all_causal else 'FAILED'}")

    # Check data sufficiency
    returns = compute_log_returns(df["close"]).dropna()
    report.append(f"  Data: {len(returns)} returns available")
    report.append(f"  Minimum for GARCH: 60 bars")
    report.append(f"  Data sufficient: {'YES' if len(returns) >= 60 else 'NO — GARCH estimation unreliable'}")

    # Check models
    models_ok = True
    for model in [NaiveModel(), RollingVolModel(24), GARCHModel()]:
        try:
            model.fit(returns)
            f = model.forecast()
            if f <= 0 or np.isnan(f):
                models_ok = False
                report.append(f"  {model.name}: INVALID forecast ({f})")
        except Exception as e:
            models_ok = False
            report.append(f"  {model.name}: FAILED ({e})")

    if models_ok:
        report.append(f"  Models: ALL PRODUCE VALID FORECASTS")

    # Overall
    ready = all_causal and models_ok
    report.append(f"\n  {'='*50}")
    if ready:
        report.append(f"  RESEARCH READINESS: READY FOR EXPANSION")
        report.append(f"  The measurement apparatus is validated.")
        report.append(f"  Next: expand to all 20 pairs and full R2.1 experiment.")
    else:
        report.append(f"  RESEARCH READINESS: NOT READY")
        report.append(f"  Fix issues before proceeding.")

    return "\n".join(report)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("R2.1 PHASE 1 — VOLATILITY STRUCTURE EXPERIMENT")
    print("=" * 70)

    # Load data
    print("\nLoading data...")
    df = load_bars(PAIR)
    print(f"  Loaded {len(df)} bars")

    # Validate data
    print("\nValidating data integrity...")
    checks = validate_data(df, PAIR)
    all_valid = True
    for name, (passed, detail) in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name} — {detail}")
        if not passed:
            all_valid = False

    if not all_valid:
        print("\nDATA VALIDATION FAILED. Fix data issues before proceeding.")
        return

    # Run causality tests
    print("\nRunning causality tests...")
    causality_results = run_causality_tests(df, PAIR)
    all_causal = all(r.passed for r in causality_results)
    for r in causality_results:
        print(f"  {r}")

    # Generate report
    report = []
    report.append("R2.1 PHASE 1 REPORT")
    report.append(f"Generated: {pd.Timestamp.now(tz='UTC')}")
    report.append(f"Pair: {PAIR}")
    report.append(f"Git commit: (run git log -1 --format=%h)")

    report.append(section_a_data_definition(df))
    report.append(section_b_model_definition())
    report.append(section_c_causality_audit(df))
    report.append(section_d_one_pair_validation(df))
    report.append(section_e_test_results(df))
    report.append(section_f_research_readiness(df, causality_results))

    # Write report
    report_text = "\n".join(report)
    report_path = RESULTS_DIR / "R2.1_phase1_report.txt"
    with open(report_path, "w") as f:
        f.write(report_text)

    print(f"\nReport written to {report_path}")
    print("\n" + report_text)


if __name__ == "__main__":
    main()
