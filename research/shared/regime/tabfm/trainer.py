"""
Rule-based regime labeler for training data preparation.

Labels historical data with regimes using heuristics based on:
- ADX for trend strength
- Realized volatility for high/low vol
- EMA distance for mean reversion
- Price breakouts for breakout detection

These labels serve as training targets for TabFM fine-tuning.
The labeling is intentionally conservative — only high-confidence
labels are used for training.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from nestquant.regime.labels import RegimeLabel
from nestquant.indicators.atr import calculate_atr
from nestquant.indicators.adx import calculate_adx


@dataclass
class LabelingConfig:
    """Configuration for regime labeling rules."""

    # ADX thresholds
    adx_trending_threshold: float = 25.0
    adx_ranging_threshold: float = 20.0

    # Volatility thresholds
    vol_high_percentile: float = 80.0
    vol_low_percentile: float = 20.0
    vol_lookback: int = 20
    vol_zscore_lookback: int = 200

    # Mean reversion zone
    mr_ema_period: int = 200
    mr_ema_distance_threshold: float = 0.005  # 0.5%

    # Breakout detection
    breakout_lookback: int = 20

    # Confidence thresholds
    min_confidence: float = 0.6


class RegimeLabeler:
    """
    Labels historical data with regimes using rule-based heuristics.

    These labels serve as training targets for TabFM fine-tuning.
    The labeling is intentionally conservative — only high-confidence
    labels are used for training.
    """

    def __init__(self, config: Optional[LabelingConfig] = None):
        self.config = config or LabelingConfig()

    def label_series(self, df: pd.DataFrame) -> pd.Series:
        """
        Assign regime labels to each bar.

        Algorithm:
        1. Compute ADX → trend strength
        2. Compute realized vol → high/low vol
        3. Check EMA distance → mean reversion zone
        4. Check breakout conditions
        5. Combine rules with priority

        Args:
            df: OHLCV DataFrame

        Returns:
            Series of regime labels
        """
        # Compute indicators
        adx = calculate_adx(df, 14)
        returns = df["close"].pct_change()

        # Volatility regime
        vol = returns.rolling(self.config.vol_lookback).std()
        vol_percentile = vol.rolling(self.config.vol_zscore_lookback).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100
        )

        # EMA distance
        ema = df["close"].ewm(span=self.config.mr_ema_period, adjust=False).mean()
        ema_distance = (df["close"] - ema).abs() / ema

        # Breakout detection
        high_rolling = df["high"].rolling(self.config.breakout_lookback).max()
        low_rolling = df["low"].rolling(self.config.breakout_lookback).min()
        breakout_up = df["close"] > high_rolling.shift(1)
        breakout_down = df["close"] < low_rolling.shift(1)

        # Initialize labels
        labels = pd.Series(RegimeLabel.UNKNOWN.value, index=df.index)

        # Apply rules with priority
        for i in range(len(df)):
            if i < self.config.vol_zscore_lookback:
                labels.iloc[i] = RegimeLabel.UNKNOWN.value
                continue

            # Priority 1: High volatility (most conservative)
            if vol_percentile.iloc[i] > self.config.vol_high_percentile:
                labels.iloc[i] = RegimeLabel.HIGH_VOL.value
                continue

            # Priority 2: Low volatility
            if vol_percentile.iloc[i] < self.config.vol_low_percentile:
                labels.iloc[i] = RegimeLabel.LOW_VOL.value
                continue

            # Priority 3: Breakout
            if breakout_up.iloc[i] or breakout_down.iloc[i]:
                labels.iloc[i] = RegimeLabel.BREAKOUT.value
                continue

            # Priority 4: Mean reversion zone
            if ema_distance.iloc[i] < self.config.mr_ema_distance_threshold:
                labels.iloc[i] = RegimeLabel.MEAN_REVERSION.value
                continue

            # Priority 5: Trending (ADX-based)
            if adx.iloc[i] > self.config.adx_trending_threshold:
                labels.iloc[i] = RegimeLabel.TRENDING.value
                continue

            # Priority 6: Ranging (ADX-based)
            if adx.iloc[i] < self.config.adx_ranging_threshold:
                labels.iloc[i] = RegimeLabel.RANGING.value
                continue

            # Default
            labels.iloc[i] = RegimeLabel.UNKNOWN.value

        return labels

    def compute_confidence(self, df: pd.DataFrame, labels: pd.Series) -> pd.Series:
        """
        Compute confidence scores for each label.

        Higher confidence when:
- ADX is far from threshold (for TRENDING/RANGING)
- Volatility is far from threshold (for HIGH_VOL/LOW_VOL)
- Price is well outside EMA zone (for MEAN_REVERSION)

        Args:
            df: OHLCV DataFrame
            labels: Assigned regime labels

        Returns:
            Series of confidence scores (0.0 to 1.0)
        """
        # Compute indicators
        adx = calculate_adx(df, 14)
        returns = df["close"].pct_change()

        # Volatility
        vol = returns.rolling(self.config.vol_lookback).std()
        vol_percentile = vol.rolling(self.config.vol_zscore_lookback).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100
        )

        # EMA distance
        ema = df["close"].ewm(span=self.config.mr_ema_period, adjust=False).mean()
        ema_distance = (df["close"] - ema).abs() / ema

        # Compute confidence
        confidence = pd.Series(0.5, index=df.index)

        for i in range(len(df)):
            label = labels.iloc[i]

            if label == RegimeLabel.TRENDING.value:
                # Confidence based on how far ADX is above threshold
                adx_value = adx.iloc[i]
                if adx_value > self.config.adx_trending_threshold:
                    confidence.iloc[i] = min(1.0, 0.6 + (adx_value - self.config.adx_trending_threshold) / 30)

            elif label == RegimeLabel.RANGING.value:
                # Confidence based on how far ADX is below threshold
                adx_value = adx.iloc[i]
                if adx_value < self.config.adx_ranging_threshold:
                    confidence.iloc[i] = min(1.0, 0.6 + (self.config.adx_ranging_threshold - adx_value) / 15)

            elif label == RegimeLabel.HIGH_VOL.value:
                # Confidence based on percentile
                pct = vol_percentile.iloc[i]
                if pct > self.config.vol_high_percentile:
                    confidence.iloc[i] = min(1.0, 0.6 + (pct - self.config.vol_high_percentile) / 20)

            elif label == RegimeLabel.LOW_VOL.value:
                # Confidence based on percentile
                pct = vol_percentile.iloc[i]
                if pct < self.config.vol_low_percentile:
                    confidence.iloc[i] = min(1.0, 0.6 + (self.config.vol_low_percentile - pct) / 20)

            elif label == RegimeLabel.MEAN_REVERSION.value:
                # Confidence based on EMA distance
                dist = ema_distance.iloc[i]
                if dist < self.config.mr_ema_distance_threshold:
                    confidence.iloc[i] = min(1.0, 0.6 + (self.config.mr_ema_distance_threshold - dist) / 0.005)

            elif label == RegimeLabel.BREAKOUT.value:
                confidence.iloc[i] = 0.8  # Fixed confidence for breakouts

            else:
                confidence.iloc[i] = 0.3  # Low confidence for unknown

        return confidence

    def prepare_training_data(
        self,
        pair_dfs: dict[str, pd.DataFrame],
        train_end: str = "2023-12-31",
        val_end: str = "2024-06-30",
    ) -> dict:
        """
        Prepare training data with labels and splits.

        Args:
            pair_dfs: Dict mapping pair to OHLCV DataFrame
            train_end: End date for training set
            val_end: End date for validation set

        Returns:
            Dict with train/val/test splits and metadata
        """
        all_features = []
        all_labels = []
        all_confidences = []
        all_pairs = []

        for pair, df in pair_dfs.items():
            # Skip if not enough data
            if len(df) < self.config.vol_zscore_lookback + 100:
                continue

            # Label the data
            labels = self.label_series(df)
            confidences = self.compute_confidence(df, labels)

            # Create feature DataFrame (simplified for now)
            features = self._create_features(df)

            all_features.append(features)
            all_labels.append(labels)
            all_confidences.append(confidences)
            all_pairs.append(pd.Series(pair, index=df.index, name="pair"))

        if not all_features:
            return {"error": "No valid data for training"}

        # Combine all pairs
        combined_features = pd.concat(all_features)
        combined_labels = pd.concat(all_labels)
        combined_confidences = pd.concat(all_confidences)
        combined_pairs = pd.concat(all_pairs)

        # Split by date
        train_mask = combined_features.index <= train_end
        val_mask = (combined_features.index > train_end) & (combined_features.index <= val_end)
        test_mask = combined_features.index > val_end

        return {
            "train": {
                "features": combined_features[train_mask],
                "labels": combined_labels[train_mask],
                "confidences": combined_confidences[train_mask],
                "pairs": combined_pairs[train_mask],
            },
            "val": {
                "features": combined_features[val_mask],
                "labels": combined_labels[val_mask],
                "confidences": combined_confidences[val_mask],
                "pairs": combined_pairs[val_mask],
            },
            "test": {
                "features": combined_features[test_mask],
                "labels": combined_labels[test_mask],
                "confidences": combined_confidences[test_mask],
                "pairs": combined_pairs[test_mask],
            },
            "metadata": {
                "n_pairs": len(pair_dfs),
                "total_samples": len(combined_features),
                "train_samples": int(train_mask.sum()),
                "val_samples": int(val_mask.sum()),
                "test_samples": int(test_mask.sum()),
                "label_distribution": combined_labels.value_counts().to_dict(),
            },
        }

    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create feature DataFrame for TabFM.

        This is a simplified version that creates core features.
        The full FeatureEngineer will be used during inference.

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with features
        """
        features = pd.DataFrame(index=df.index)

        # Price returns
        returns = df["close"].pct_change()
        features["return_1"] = returns
        features["return_5"] = df["close"].pct_change(5)
        features["return_10"] = df["close"].pct_change(10)
        features["return_20"] = df["close"].pct_change(20)

        # Volatility
        features["vol_20"] = returns.rolling(20).std()
        features["vol_60"] = returns.rolling(60).std()
        features["vol_ratio"] = features["vol_20"] / features["vol_60"].replace(0, np.nan)

        # ATR
        atr = calculate_atr(df, 14)
        features["atr_14"] = atr
        features["atr_ratio"] = atr / calculate_atr(df, 50).replace(0, np.nan)

        # ADX
        features["adx_14"] = calculate_adx(df, 14)

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1.0 / 14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1.0 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        features["rsi_14"] = 100 - (100 / (1 + rs))

        # EMA distances
        ema_50 = df["close"].ewm(span=50, adjust=False).mean()
        ema_200 = df["close"].ewm(span=200, adjust=False).mean()
        features["price_vs_ema50"] = (df["close"] - ema_50) / ema_50
        features["price_vs_ema200"] = (df["close"] - ema_200) / ema_200

        # Volume
        if "volume" in df.columns:
            vol_ma = df["volume"].rolling(20).mean()
            features["volume_ratio"] = df["volume"] / vol_ma.replace(0, np.nan)

        # Temporal features
        if isinstance(df.index, pd.DatetimeIndex):
            features["hour"] = df.index.hour / 24
            features["day_of_week"] = df.index.dayofweek / 4

        # Fill NaN with 0
        features = features.fillna(0)

        return features
