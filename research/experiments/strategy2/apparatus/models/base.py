"""R2.1 Stage 3B — Base Model Interfaces

Defines the three foundational types for all R2.1 volatility models:
- VolatilityModel: protocol every model implements
- ModelDiagnostics: standard diagnostics structure
- ForecastResult: horizon-tagged forecast output

Spec reference: R2.1_STAGE_3B_FEATURE_MODEL_SPEC.md §2, §6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# ForecastResult
# ---------------------------------------------------------------------------

@dataclass
class ForecastResult:
    """Horizon-tagged forecast result.

    Every forecast() call returns an instance of this class.
    The horizon tag enables the forecast-horizon/target-horizon
    consistency invariant: evaluation code must assert
    forecast.horizon == target.horizon before scoring.

    Spec: §2.2, §2.3.
    """

    volatility: float  # Realized volatility estimate (non-negative when valid)
    horizon: int  # Forecast horizon in bars (1, 3, 6, or 12)
    valid: bool  # False if forecast cannot be produced
    diagnostic: str | None  # e.g., "FORECAST_UNAVAILABLE", "STATIONARITY_VIOLATION"
    model_name: str  # Model identifier

    def __post_init__(self) -> None:
        if self.valid and self.volatility < 0:
            raise ValueError(
                f"Forecast volatility must be >= 0, got {self.volatility}"
            )


# ---------------------------------------------------------------------------
# ModelDiagnostics
# ---------------------------------------------------------------------------

@dataclass
class ModelDiagnostics:
    """Standard diagnostics for all R2.1 volatility models.

    Produced by fit() and stored on the model instance.
    Must NOT alter the forecast silently.

    Spec: §6.1.
    """

    # Convergence
    converged: bool
    warning: str | None

    # Observations
    n_observations: int
    min_observations_required: int

    # Parameters (model-specific)
    parameters: dict[str, float]

    # Fit quality (where applicable)
    log_likelihood: float | None
    aic: float | None
    bic: float | None

    # GARCH-specific: stationarity gate
    alpha_plus_beta: float | None  # GARCH/GJR-GARCH only
    stationary: bool | None  # True if α+β < 1, None for non-GARCH models

    # HAR-specific: per-horizon coefficients
    horizons_fitted: list[int] | None  # HAR only: [1, 3, 6, 12]
    coefficients_per_horizon: dict[int, np.ndarray] | None  # HAR only

    # Metadata
    model_name: str
    fit_timestamp: pd.Timestamp | None


# ---------------------------------------------------------------------------
# VolatilityModel Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class VolatilityModel(Protocol):
    """Protocol for all R2.1 volatility models.

    All models produce forecasts tagged with a horizon.
    The forecast() method accepts a horizon parameter and returns
    a ForecastResult containing the volatility estimate and metadata.

    Spec: §2.1.
    """

    @property
    def name(self) -> str:
        """Unique model identifier (e.g., 'GARCH(1,1)', 'HAR-RV-h6')."""
        ...

    @property
    def min_observations(self) -> int:
        """Minimum observations required for fitting/forecasting."""
        ...

    def fit(
        self, returns: pd.Series, gaps: pd.Series | None = None
    ) -> ModelDiagnostics:
        """Fit model on historical returns.

        CAUSAL: uses only the provided returns. No future information.
        Must handle: empty series, series with NaN, series < minimum length.

        Args:
            returns: Historical log returns.
            gaps: Optional boolean series marking gap boundaries (True = gap).
                  If provided, state-dependent models must not propagate
                  state across gap boundaries.

        Returns: ModelDiagnostics with convergence status.
        """
        ...

    def forecast(self, horizon: int) -> ForecastResult:
        """Generate volatility forecast for the specified horizon.

        CAUSAL: uses only fitted state from last fit() call.

        Args:
            horizon: Forecast horizon in bars (1, 3, 6, or 12).

        Returns: ForecastResult with volatility estimate, horizon tag,
                 and validity flag. Invalid if model failed to fit,
                 horizon is unsupported, or stationarity gate blocks.
        """
        ...
