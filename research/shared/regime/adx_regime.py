"""
ADX-based regime detector (legacy).
"""

from __future__ import annotations

import pandas as pd

from nestquant.core.tooling.indicators.adx import calculate_adx
from nestquant.research.shared.regime.base import RegimeDetector, RegimePrediction
from nestquant.research.shared.regime.labels import RegimeLabel


class ADXRegimeDetector(RegimeDetector):
    """
    Simple regime detector based on ADX thresholds.

    - ADX > 25: TRENDING
    - ADX < 20: RANGING
    - Otherwise: UNKNOWN
    """

    def __init__(
        self,
        trending_threshold: float = 25.0,
        ranging_threshold: float = 20.0,
    ):
        self.trending_threshold = trending_threshold
        self.ranging_threshold = ranging_threshold

    def predict(self, pair: str, features_df: pd.DataFrame) -> RegimePrediction:
        """
        Predict regime using ADX.

        Args:
            pair: Currency pair identifier
            features_df: DataFrame with OHLCV data

        Returns:
            RegimePrediction based on ADX
        """
        adx = calculate_adx(features_df, 14)
        current_adx = adx.iloc[-1]

        if current_adx > self.trending_threshold:
            regime = RegimeLabel.TRENDING
            confidence = min(1.0, (current_adx - self.trending_threshold) / 20 + 0.5)
        elif current_adx < self.ranging_threshold:
            regime = RegimeLabel.RANGING
            confidence = min(1.0, (self.ranging_threshold - current_adx) / 10 + 0.5)
        else:
            regime = RegimeLabel.UNKNOWN
            confidence = 0.5

        scores = {
            RegimeLabel.TRENDING: confidence if regime == RegimeLabel.TRENDING else 0.0,
            RegimeLabel.RANGING: confidence if regime == RegimeLabel.RANGING else 0.0,
            RegimeLabel.UNKNOWN: confidence if regime == RegimeLabel.UNKNOWN else 0.0,
        }

        return RegimePrediction(
            regime=regime,
            confidence=confidence,
            scores=scores,
            features_used=["adx"],
            model_version="adx_v1",
        )
