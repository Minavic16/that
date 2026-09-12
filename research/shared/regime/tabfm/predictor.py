"""
TabFM-based regime detector with fallback logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from nestquant.research.shared.regime.base import RegimeDetector, RegimePrediction
from nestquant.research.shared.regime.labels import RegimeLabel
from nestquant.research.shared.regime.tabfm.features import FeatureEngineer
from nestquant.research.shared.regime.tabfm.model import TabFMConfig, TabFMModel


@dataclass
class PredictionCache:
    """LRU cache for regime predictions to avoid redundant inference."""

    predictions: dict[str, RegimePrediction]
    max_size: int = 1000

    def get(self, key: str) -> Optional[RegimePrediction]:
        """Get prediction from cache."""
        return self.predictions.get(key)

    def put(self, key: str, pred: RegimePrediction) -> None:
        """Add prediction to cache, evicting oldest if full."""
        if len(self.predictions) >= self.max_size:
            # Remove oldest entry (first key)
            oldest_key = next(iter(self.predictions))
            del self.predictions[oldest_key]
        self.predictions[key] = pred


class TabFMRegimeDetector(RegimeDetector):
    """
    TabFM-based regime detector implementing the RegimeDetector interface.

    Usage:
        detector = TabFMRegimeDetector.from_checkpoint("models/tabfm/checkpoints/best.pt")
        prediction = detector.predict(pair="EUR/USD", features_df=df)
        print(prediction.regime)           # RegimeLabel.TRENDING
        print(prediction.confidence)       # 0.87
        print(prediction.scores)           # {TRENDING: 0.87, RANGING: 0.08, ...}
    """

    def __init__(
        self,
        model: TabFMModel,
        feature_engineer: FeatureEngineer,
        confidence_threshold: float = 0.5,
        fallback_regime: RegimeLabel = RegimeLabel.UNKNOWN,
    ):
        self._model = model
        self._feature_engineer = feature_engineer
        self._confidence_threshold = confidence_threshold
        self._fallback_regime = fallback_regime
        self._cache = PredictionCache(predictions={})

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: str,
        device: str = "auto",
    ) -> TabFMRegimeDetector:
        """
        Factory method to load from saved checkpoint.

        Args:
            checkpoint_path: Path to model checkpoint
            device: Device to use for inference

        Returns:
            Initialized TabFMRegimeDetector
        """
        config = TabFMConfig(model_path=checkpoint_path, device=device)
        model = TabFMModel(config)
        model.load(checkpoint_path)
        fe = FeatureEngineer(pair="", lookback=config.max_seq_len)
        return cls(model=model, feature_engineer=fe)

    def predict(self, pair: str, features_df: pd.DataFrame) -> RegimePrediction:
        """
        Full prediction pipeline: features → model → regime.

        Args:
            pair: Currency pair identifier
            features_df: DataFrame with OHLCV and indicator data

        Returns:
            RegimePrediction with regime label and confidence
        """
        # Compute features
        features = self._feature_engineer.compute(features_df)

        # Get feature vector for last bar
        if len(features) == 0:
            return RegimePrediction(
                regime=self._fallback_regime,
                confidence=0.0,
                scores={},
            )

        feature_vector = features.iloc[-1:].values

        # Run inference
        probs = self._model.predict(feature_vector.flatten())

        # Convert to RegimePrediction
        scores = {}
        for regime_name, prob in probs.items():
            try:
                regime = RegimeLabel(regime_name)
                scores[regime] = prob
            except ValueError:
                continue

        # Get best regime
        if scores:
            best_regime = max(scores, key=scores.get)
            confidence = scores[best_regime]
        else:
            best_regime = self._fallback_regime
            confidence = 0.0

        return RegimePrediction(
            regime=best_regime,
            confidence=confidence,
            scores=scores,
            features_used=list(features.columns),
            model_version="tabfm_v1",
        )

    def predict_from_features(self, features: np.ndarray) -> RegimePrediction:
        """
        Direct prediction from pre-computed feature vector.

        Args:
            features: Feature vector of shape (n_features,)

        Returns:
            RegimePrediction
        """
        probs = self._model.predict(features)

        scores = {}
        for regime_name, prob in probs.items():
            try:
                regime = RegimeLabel(regime_name)
                scores[regime] = prob
            except ValueError:
                continue

        if scores:
            best_regime = max(scores, key=scores.get)
            confidence = scores[best_regime]
        else:
            best_regime = self._fallback_regime
            confidence = 0.0

        return RegimePrediction(
            regime=best_regime,
            confidence=confidence,
            scores=scores,
            model_version="tabfm_v1",
        )

    def predict_with_fallback(
        self,
        pair: str,
        features_df: pd.DataFrame,
        fallback_detector: Optional[RegimeDetector] = None,
    ) -> RegimePrediction:
        """
        Prediction with confidence-based fallback.

        If TabFM confidence is below threshold, falls back to another detector.

        Args:
            pair: Currency pair identifier
            features_df: DataFrame with OHLCV and indicator data
            fallback_detector: Optional fallback detector

        Returns:
            RegimePrediction
        """
        tabfm_pred = self.predict(pair, features_df)

        if tabfm_pred.confidence >= self._confidence_threshold:
            return tabfm_pred

        if fallback_detector is not None:
            return fallback_detector.predict(pair, features_df)

        return tabfm_pred
