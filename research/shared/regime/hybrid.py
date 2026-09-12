"""
Hybrid regime detector that combines TabFM with ADX fallback.

Strategy:
- TabFM is primary (80% weight) when confidence > 0.6
- Falls back to ADX when TabFM confidence is low
- ADX takes over if TabFM model fails
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from nestquant.research.shared.regime.base import RegimeDetector, RegimePrediction
from nestquant.research.shared.regime.labels import RegimeLabel, REGIME_PARAMS
from nestquant.research.shared.regime.adx_regime import ADXRegimeDetector
from nestquant.research.shared.regime.tabfm.predictor import TabFMRegimeDetector


@dataclass
class HybridConfig:
    """Configuration for hybrid regime detector."""

    # Confidence thresholds
    tabfm_confidence_threshold: float = 0.6
    high_confidence_threshold: float = 0.8

    # Weights
    tabfm_weight_high_conf: float = 0.8
    tabfm_weight_low_conf: float = 0.4
    adx_weight_high_conf: float = 0.2
    adx_weight_low_conf: float = 0.6

    # Fallback settings
    enable_tabfm: bool = True
    enable_adx_fallback: bool = True


class HybridRegimeDetector(RegimeDetector):
    """
    Combines TabFM predictions with legacy ADX logic.

    This detector provides robust regime classification by:
    1. Using TabFM as primary when confidence is high
    2. Blending TabFM with ADX when confidence is moderate
    3. Falling back to ADX when TabFM is unavailable or low confidence

    Usage:
        detector = HybridRegimeDetector(tabfm_detector, adx_detector)
        prediction = detector.predict(pair="EUR/USD", features_df=df)
        print(prediction.regime)  # RegimeLabel.TRENDING
        print(prediction.confidence)  # 0.87
    """

    def __init__(
        self,
        tabfm_detector: Optional[TabFMRegimeDetector] = None,
        adx_detector: Optional[ADXRegimeDetector] = None,
        config: Optional[HybridConfig] = None,
    ):
        self._tabfm = tabfm_detector
        self._adx = adx_detector or ADXRegimeDetector()
        self._config = config or HybridConfig()

    @classmethod
    def from_checkpoint(
        cls,
        tabfm_checkpoint: str,
        device: str = "auto",
        config: Optional[HybridConfig] = None,
    ) -> HybridRegimeDetector:
        """
        Create hybrid detector from TabFM checkpoint.

        Args:
            tabfm_checkpoint: Path to TabFM model checkpoint
            device: Device for inference
            config: Hybrid configuration

        Returns:
            Initialized HybridRegimeDetector
        """
        try:
            tabfm_detector = TabFMRegimeDetector.from_checkpoint(
                tabfm_checkpoint, device
            )
        except Exception:
            tabfm_detector = None

        return cls(
            tabfm_detector=tabfm_detector,
            config=config,
        )

    def predict(self, pair: str, features_df: pd.DataFrame) -> RegimePrediction:
        """
        Predict regime using hybrid approach.

        Args:
            pair: Currency pair identifier
            features_df: DataFrame with OHLCV and indicator data

        Returns:
            RegimePrediction combining TabFM and ADX predictions
        """
        # Get ADX prediction (always available)
        adx_pred = self._adx.predict(pair, features_df)

        # Get TabFM prediction if available
        tabfm_pred = None
        if self._config.enable_tabfm and self._tabfm is not None:
            try:
                tabfm_pred = self._tabfm.predict(pair, features_df)
            except Exception:
                tabfm_pred = None

        # If TabFM not available or failed, use ADX only
        if tabfm_pred is None or not self._config.enable_tabfm:
            return adx_pred

        # Combine predictions based on confidence
        if tabfm_pred.confidence >= self._config.high_confidence_threshold:
            # High confidence: mostly TabFM
            weights = [
                self._config.tabfm_weight_high_conf,
                self._config.adx_weight_high_conf,
            ]
        elif tabfm_pred.confidence >= self._config.tabfm_confidence_threshold:
            # Medium confidence: balanced blend
            weights = [
                self._config.tabfm_weight_low_conf,
                self._config.adx_weight_low_conf,
            ]
        else:
            # Low confidence: mostly ADX
            weights = [
                self._config.tabfm_weight_low_conf * 0.5,
                self._config.adx_weight_low_conf * 1.5,
            ]

        # Normalize weights
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]

        # Blend predictions
        all_scores: dict[RegimeLabel, float] = {}
        for pred, weight in zip([tabfm_pred, adx_pred], weights):
            for regime, score in pred.scores.items():
                all_scores[regime] = all_scores.get(regime, 0.0) + score * weight

        # Get best regime
        if all_scores:
            best_regime = max(all_scores, key=all_scores.get)
            confidence = all_scores[best_regime]
        else:
            best_regime = RegimeLabel.UNKNOWN
            confidence = 0.0

        return RegimePrediction(
            regime=best_regime,
            confidence=confidence,
            scores=all_scores,
            features_used=["tabfm", "adx"],
            model_version="hybrid_v1",
        )

    def predict_with_source(
        self,
        pair: str,
        features_df: pd.DataFrame,
    ) -> tuple[RegimePrediction, str]:
        """
        Predict regime and return the source (tabfm/adx/hybrid).

        Args:
            pair: Currency pair identifier
            features_df: DataFrame with OHLCV and indicator data

        Returns:
            Tuple of (RegimePrediction, source_string)
        """
        # Get predictions
        adx_pred = self._adx.predict(pair, features_df)

        tabfm_pred = None
        if self._config.enable_tabfm and self._tabfm is not None:
            try:
                tabfm_pred = self._tabfm.predict(pair, features_df)
            except Exception:
                tabfm_pred = None

        # Determine source and return
        if tabfm_pred is None:
            return adx_pred, "adx"

        if tabfm_pred.confidence >= self._config.high_confidence_threshold:
            return tabfm_pred, "tabfm_high_conf"
        elif tabfm_pred.confidence >= self._config.tabfm_confidence_threshold:
            # Blended
            return self.predict(pair, features_df), "hybrid"
        else:
            return adx_pred, "adx_fallback"

    def get_diagnostics(
        self,
        pair: str,
        features_df: pd.DataFrame,
    ) -> dict:
        """
        Get diagnostic information about regime detection.

        Useful for debugging and understanding model behavior.

        Args:
            pair: Currency pair identifier
            features_df: DataFrame with OHLCV and indicator data

        Returns:
            Dict with diagnostic information
        """
        adx_pred = self._adx.predict(pair, features_df)

        tabfm_pred = None
        if self._tabfm is not None:
            try:
                tabfm_pred = self._tabfm.predict(pair, features_df)
            except Exception:
                tabfm_pred = None

        hybrid_pred = self.predict(pair, features_df)

        return {
            "pair": pair,
            "adx_prediction": {
                "regime": adx_pred.regime.value,
                "confidence": adx_pred.confidence,
            },
            "tabfm_prediction": {
                "regime": tabfm_pred.regime.value if tabfm_pred else None,
                "confidence": tabfm_pred.confidence if tabfm_pred else None,
                "available": tabfm_pred is not None,
            },
            "hybrid_prediction": {
                "regime": hybrid_pred.regime.value,
                "confidence": hybrid_pred.confidence,
                "scores": {r.value: s for r, s in hybrid_pred.scores.items()},
            },
            "config": {
                "tabfm_enabled": self._config.enable_tabfm,
                "adx_fallback_enabled": self._config.enable_adx_fallback,
                "confidence_threshold": self._config.tabfm_confidence_threshold,
            },
        }
