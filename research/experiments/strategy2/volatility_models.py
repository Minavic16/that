"""
R2.1 Volatility Structure Research — Model Definitions
=======================================================

Implements:
- Baseline models (rolling vol, EWMA, naive)
- GARCH(1,1) and GJR-GARCH(1,1)
- HAR-RV model
- Walk-forward forecasting framework

All models are strictly causal: forecast_t uses only information
available at time t.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd
from arch import arch_model


# ---------------------------------------------------------------------------
# Forecast Result
# ---------------------------------------------------------------------------

@dataclass
class ForecastResult:
    """Single forecast observation."""
    timestamp: pd.Timestamp
    forecast: float
    realized: float
    model_name: str
    horizon: int


# ---------------------------------------------------------------------------
# Model Protocol
# ---------------------------------------------------------------------------

class VolatilityModel(Protocol):
    """Protocol for all volatility models."""

    @property
    def name(self) -> str: ...

    def fit(self, returns: pd.Series) -> None:
        """Fit model on historical returns (CAUSAL: past only)."""
        ...

    def forecast(self) -> float:
        """Generate 1-step-ahead forecast (CAUSAL: uses only fitted state)."""
        ...


# ---------------------------------------------------------------------------
# Baseline: Naive (Persistence)
# ---------------------------------------------------------------------------

class NaiveModel:
    """Forecast: next period's volatility = current volatility.

    CAUSAL: sigma_hat_{t+1} = sigma_t.
    No estimation required.
    """

    def __init__(self):
        self._last_vol: float = 0.0

    @property
    def name(self) -> str:
        return "naive"

    def fit(self, returns: pd.Series) -> None:
        """Set last observed volatility."""
        if len(returns) > 0:
            self._last_vol = abs(returns.iloc[-1])
        else:
            self._last_vol = 0.0

    def forecast(self) -> float:
        return self._last_vol


# ---------------------------------------------------------------------------
# Baseline: Rolling Standard Deviation
# ---------------------------------------------------------------------------

class RollingVolModel:
    """Forecast: rolling standard deviation of returns.

    CAUSAL: sigma_hat_{t+1} = std(r_{t-W+1}, ..., r_t).
    """

    def __init__(self, window: int = 24):
        self._window = window
        self._last_vol: float = 0.0

    @property
    def name(self) -> str:
        return f"rolling_vol_{self._window}"

    def fit(self, returns: pd.Series) -> None:
        """Compute rolling std over the window."""
        if len(returns) >= self._window:
            self._last_vol = returns.iloc[-self._window:].std()
        elif len(returns) > 1:
            self._last_vol = returns.std()
        else:
            self._last_vol = 0.0

    def forecast(self) -> float:
        return self._last_vol


# ---------------------------------------------------------------------------
# Baseline: EWMA
# ---------------------------------------------------------------------------

class EWMAModel:
    """Forecast: exponentially weighted moving standard deviation.

    CAUSAL: sigma_hat_{t+1} = EWMA of squared returns.
    Uses exponential decay to weight recent observations more.
    """

    def __init__(self, span: int = 24):
        self._span = span
        self._last_vol: float = 0.0

    @property
    def name(self) -> str:
        return f"ewma_{self._span}"

    def fit(self, returns: pd.Series) -> None:
        """Compute EWMA std."""
        if len(returns) > 1:
            ewm_var = returns.ewm(span=self._span, min_periods=1).var()
            self._last_vol = np.sqrt(ewm_var.iloc[-1])
        else:
            self._last_vol = 0.0

    def forecast(self) -> float:
        return self._last_vol


# ---------------------------------------------------------------------------
# GARCH(1,1)
# ---------------------------------------------------------------------------

class GARCHModel:
    """GARCH(1,1) volatility forecasting.

    CAUSAL: Parameters estimated on historical data only.
    Forecast uses only past squared residuals and past conditional variance.

    sigma_t^2 = omega + alpha * epsilon_{t-1}^2 + beta * sigma_{t-1}^2
    """

    def __init__(self, mean: str = "Constant", vol: str = "GARCH",
                 p: int = 1, q: int = 1):
        self._mean = mean
        self._vol = vol
        self._p = p
        self._q = q
        self._fitted = None
        self._last_forecast: float = 0.0

    @property
    def name(self) -> str:
        return f"GARCH({self._p},{self._q})"

    def fit(self, returns: pd.Series) -> None:
        """Fit GARCH model on historical returns.

        CAUSAL: arch_model.fit() uses only the provided returns.
        No look-ahead in parameter estimation.
        """
        # Scale returns to percentage for numerical stability
        scaled = returns * 100

        if len(scaled) < 30:
            # Not enough data for GARCH estimation
            self._last_forecast = returns.std() if len(returns) > 1 else 0.0
            self._fitted = None
            return

        try:
            am = arch_model(
                scaled,
                mean=self._mean,
                vol=self._vol,
                p=self._p,
                q=self._q,
                dist="Normal",
            )
            self._fitted = am.fit(disp="off", show_warning=False)

            # 1-step-ahead forecast
            forecasts = self._fitted.forecast(horizon=1, reindex=False)
            # variance forecast, convert back from percentage scale
            var_forecast = forecasts.variance.iloc[-1].values[0]
            self._last_forecast = np.sqrt(var_forecast) / 100
        except Exception:
            # Fallback to simple volatility if GARCH fails to converge
            self._last_forecast = returns.std() if len(returns) > 1 else 0.0
            self._fitted = None

    def forecast(self) -> float:
        return self._last_forecast


# ---------------------------------------------------------------------------
# GJR-GARCH(1,1)
# ---------------------------------------------------------------------------

class GJRGARCHModel:
    """GJR-GARCH(1,1) — asymmetric GARCH capturing leverage effect.

    CAUSAL: Same as GARCH but with asymmetry parameter gamma.
    sigma_t^2 = omega + (alpha + gamma * I_{t-1}) * epsilon_{t-1}^2 + beta * sigma_{t-1}^2
    """

    def __init__(self):
        self._fitted = None
        self._last_forecast: float = 0.0

    @property
    def name(self) -> str:
        return "GJR-GARCH(1,1)"

    def fit(self, returns: pd.Series) -> None:
        scaled = returns * 100

        if len(scaled) < 30:
            self._last_forecast = returns.std() if len(returns) > 1 else 0.0
            self._fitted = None
            return

        try:
            am = arch_model(
                scaled,
                mean="Constant",
                vol="GARCH",
                p=1,
                o=1,  # Asymmetric/GJR term
                q=1,
                dist="Normal",
            )
            self._fitted = am.fit(disp="off", show_warning=False)
            forecasts = self._fitted.forecast(horizon=1, reindex=False)
            var_forecast = forecasts.variance.iloc[-1].values[0]
            self._last_forecast = np.sqrt(var_forecast) / 100
        except Exception:
            self._last_forecast = returns.std() if len(returns) > 1 else 0.0
            self._fitted = None

    def forecast(self) -> float:
        return self._last_forecast


# ---------------------------------------------------------------------------
# HAR-RV (Heterogeneous Autoregressive Realized Volatility)
# ---------------------------------------------------------------------------

class HARModel:
    """HAR-RV model: multi-timescale volatility forecasting.

    CAUSAL: Uses only past realized volatilities at daily, weekly, monthly scales.

    RV_{t+h} = c + beta_d * RV_t(daily) + beta_w * RV_t(weekly) + beta_l * RV_t(monthly)
    """

    def __init__(self, daily: int = 6, weekly: int = 30, monthly: int = 90):
        self._daily = daily    # ~1 day at 4H = 6 bars
        self._weekly = weekly  # ~5 days
        self._monthly = monthly  # ~22 days
        self._coeffs: np.ndarray | None = None
        self._last_features: np.ndarray | None = None

    @property
    def name(self) -> str:
        return "HAR-RV"

    def _build_features(self, log_ret_sq: pd.Series) -> pd.DataFrame:
        """Build HAR features from squared returns.

        CAUSAL: all features use only past data.
        """
        daily = log_ret_sq.rolling(self._daily, min_periods=self._daily).mean()
        weekly = log_ret_sq.rolling(self._weekly, min_periods=self._daily).mean()
        monthly = log_ret_sq.rolling(self._monthly, min_periods=self._daily).mean()

        return pd.DataFrame({
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
        })

    def fit(self, returns: pd.Series) -> None:
        """Fit HAR model using OLS on historical data.

        CAUSAL: training data is strictly in the past.
        """
        log_ret_sq = returns ** 2
        features = self._build_features(log_ret_sq)

        # Target: next period's squared return
        target = log_ret_sq.shift(-1)

        # Align and drop NaN
        combined = pd.concat([features, target.rename("target")], axis=1).dropna()

        if len(combined) < max(self._monthly, 30) + 10:
            self._coeffs = None
            self._last_features = None
            return

        X = combined[["daily", "weekly", "monthly"]].values
        y = combined["target"].values

        # OLS: beta = (X'X)^{-1} X'y
        try:
            self._coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
            self._last_features = X[-1]
        except Exception:
            self._coeffs = None
            self._last_features = None

    def forecast(self) -> float:
        """Forecast volatility using HAR model.

        CAUSAL: uses only last fitted features.
        """
        if self._coeffs is None or self._last_features is None:
            return 0.0

        pred_sq = self._coeffs @ self._last_features
        return np.sqrt(max(pred_sq, 0.0))


# ---------------------------------------------------------------------------
# Walk-Forward Evaluation Engine
# ---------------------------------------------------------------------------

def walk_forward_evaluate(
    returns: pd.Series,
    models: list[VolatilityModel],
    target_horizon: int,
    train_window: int,
    step: int = 1,
) -> pd.DataFrame:
    """Walk-forward out-of-sample evaluation.

    CAUSAL GUARANTEE:
    - At time t, models are fitted on returns[t - train_window : t]
    - Forecast is made for returns[t : t + target_horizon]
    - Target (realized vol) is computed from returns[t : t + target_horizon]
    - Forecast and target are compared ONLY after the target period

    Parameters:
        returns: Full return series
        models: List of fitted model instances
        target_horizon: Forecast horizon in bars
        train_window: Number of past bars for training
        step: Step size between forecasts (default: every bar)
    """
    n = len(returns)
    results = []

    for t in range(train_window, n - target_horizon, step):
        # Training window: [t - train_window, t)
        train_returns = returns.iloc[t - train_window:t]

        # Realized volatility target: [t, t + target_horizon)
        target_returns = returns.iloc[t:t + target_horizon]
        realized_vol = target_returns.std()

        # Timestamp for this forecast (the bar at time t)
        forecast_ts = returns.index[t]

        # Fit each model on training data only
        for model in models:
            model.fit(train_returns)

            # Generate forecast
            forecast = model.forecast()

            results.append(ForecastResult(
                timestamp=forecast_ts,
                forecast=forecast,
                realized=realized_vol,
                model_name=model.name,
                horizon=target_horizon,
            ))

    return pd.DataFrame([{
        "timestamp": r.timestamp,
        "forecast": r.forecast,
        "realized": r.realized,
        "model": r.model_name,
        "horizon": r.horizon,
    } for r in results])


# ---------------------------------------------------------------------------
# Forecast Error Metrics
# ---------------------------------------------------------------------------

def compute_metrics(results_df: pd.DataFrame) -> pd.DataFrame:
    """Compute forecast error metrics per model.

    Returns DataFrame with columns:
        model, rmse, mae, qlike, direction_accuracy, n_forecasts
    """
    metrics = []

    for model_name in results_df["model"].unique():
        model_data = results_df[results_df["model"] == model_name]
        f = model_data["forecast"].values
        r = model_data["realized"].values

        # Avoid division by zero
        mask = (r > 1e-10) & (f > 1e-10)
        f_clean = f[mask]
        r_clean = r[mask]

        if len(f_clean) < 5:
            metrics.append({
                "model": model_name,
                "rmse": np.nan,
                "mae": np.nan,
                "qlike": np.nan,
                "direction_accuracy": np.nan,
                "n_forecasts": len(f_clean),
            })
            continue

        # RMSE
        rmse = np.sqrt(np.mean((f_clean - r_clean) ** 2))

        # MAE
        mae = np.mean(np.abs(f_clean - r_clean))

        # QLIKE (volatility-specific loss)
        qlike = np.mean(np.log(f_clean ** 2) + r_clean ** 2 / f_clean ** 2)

        # Direction accuracy (did we predict the sign of vol change?)
        # Not directly applicable for level forecasts; use correlation instead
        direction_acc = np.corrcoef(f_clean, r_clean)[0, 1] if len(f_clean) > 2 else np.nan

        metrics.append({
            "model": model_name,
            "rmse": rmse,
            "mae": mae,
            "qlike": qlike,
            "direction_accuracy": direction_acc,
            "n_forecasts": len(f_clean),
        })

    return pd.DataFrame(metrics)


def compute_improvement_over_baseline(
    metrics_df: pd.DataFrame,
    baseline_name: str = "rolling_vol_24",
) -> pd.DataFrame:
    """Compute improvement of each model over a baseline.

    Improvement = 1 - (metric_model / metric_baseline).
    Positive = model is better.
    """
    baseline_row = metrics_df[metrics_df["model"] == baseline_name]
    if baseline_row.empty:
        return metrics_df

    baseline_rmse = baseline_row["rmse"].values[0]
    baseline_mae = baseline_row["mae"].values[0]

    metrics_df = metrics_df.copy()
    metrics_df["rmse_improvement"] = 1 - metrics_df["rmse"] / baseline_rmse
    metrics_df["mae_improvement"] = 1 - metrics_df["mae"] / baseline_mae

    return metrics_df
