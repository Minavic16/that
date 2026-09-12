"""
Base regime detector interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from nestquant.research.shared.regime.labels import REGIME_PARAMS, RegimeLabel


@dataclass
class RegimePrediction:
    """Result of a regime prediction."""

    regime: RegimeLabel
    confidence: float  # 0.0 - 1.0
    scores: dict[RegimeLabel, float] = field(default_factory=dict)
    features_used: list[str] = field(default_factory=list)
    model_version: str = ""
    latency_ms: float = 0.0

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.6

    @property
    def params(self) -> dict:
        """Get strategy parameter multipliers for this regime."""
        return REGIME_PARAMS.get(self.regime, REGIME_PARAMS[RegimeLabel.UNKNOWN])


class RegimeDetector(ABC):
    """Abstract base for all regime detectors."""

    @abstractmethod
    def predict(self, pair: str, features_df: pd.DataFrame) -> RegimePrediction:
        """
        Predict the current market regime.

        Args:
            pair: Currency pair identifier
            features_df: DataFrame with feature data

        Returns:
            RegimePrediction with regime label and confidence
        """
        ...

    def predict_ensemble(
        self,
        detectors: list[RegimeDetector],
        pair: str,
        features_df: pd.DataFrame,
        weights: Optional[list[float]] = None,
    ) -> RegimePrediction:
        """Ensemble prediction with weighted averaging."""
        if weights is None:
            weights = [1.0 / len(detectors)] * len(detectors)

        all_scores: dict[RegimeLabel, float] = {}
        for det, w in zip(detectors, weights):
            pred = det.predict(pair, features_df)
            for regime, score in pred.scores.items():
                all_scores[regime] = all_scores.get(regime, 0.0) + score * w

        best_regime = max(all_scores, key=all_scores.get)
        return RegimePrediction(
            regime=best_regime,
            confidence=all_scores[best_regime],
            scores=all_scores,
        )
