"""
Feature engineering pipeline for TabFM regime detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd


class FeatureGroup(Enum):
    """Feature group categories."""

    VOLATILITY = "volatility"
    TREND = "trend"
    MOMENTUM = "momentum"
    MICROSTRUCTURE = "microstructure"
    TEMPORAL = "temporal"
    CROSS_SECTIONAL = "cross_sectional"


@dataclass
class FeatureSpec:
    """Specification for a single feature."""

    name: str
    group: FeatureGroup
    lookback: int
    description: str


# Feature registry — defines all 45 features
FEATURE_REGISTRY: list[FeatureSpec] = [
    # Volatility group (8 features)
    FeatureSpec("atr_14", FeatureGroup.VOLATILITY, 14, "ATR 14-period"),
    FeatureSpec("atr_50", FeatureGroup.VOLATILITY, 50, "ATR 50-period"),
    FeatureSpec("atr_ratio", FeatureGroup.VOLATILITY, 50, "ATR(14)/ATR(50)"),
    FeatureSpec("realized_vol_20", FeatureGroup.VOLATILITY, 20, "20-period realized vol"),
    FeatureSpec("realized_vol_60", FeatureGroup.VOLATILITY, 60, "60-period realized vol"),
    FeatureSpec("vol_regime", FeatureGroup.VOLATILITY, 200, "Vol z-score vs 200-period"),
    FeatureSpec("garman_klass_vol", FeatureGroup.VOLATILITY, 20, "GK volatility estimator"),
    FeatureSpec("parkinson_vol", FeatureGroup.VOLATILITY, 20, "Parkinson volatility"),

    # Trend group (10 features)
    FeatureSpec("adx_14", FeatureGroup.TREND, 14, "ADX 14-period"),
    FeatureSpec("adx_slope", FeatureGroup.TREND, 14, "ADX rate of change"),
    FeatureSpec("plus_di", FeatureGroup.TREND, 14, "+DI"),
    FeatureSpec("minus_di", FeatureGroup.TREND, 14, "-DI"),
    FeatureSpec("di_ratio", FeatureGroup.TREND, 14, "+DI/-DI ratio"),
    FeatureSpec("ema_alignment", FeatureGroup.TREND, 200, "EMA50 vs EMA200"),
    FeatureSpec("price_vs_ema200", FeatureGroup.TREND, 200, "Price distance from EMA200"),
    FeatureSpec("price_vs_ema50", FeatureGroup.TREND, 50, "Price distance from EMA50"),
    FeatureSpec("trend_strength", FeatureGroup.TREND, 20, "Consecutive bars in trend"),
    FeatureSpec("higher_tf_trend", FeatureGroup.TREND, 200, "4H trend alignment"),

    # Momentum group (8 features)
    FeatureSpec("rsi_14", FeatureGroup.MOMENTUM, 14, "RSI 14-period"),
    FeatureSpec("rsi_slope", FeatureGroup.MOMENTUM, 14, "RSI rate of change"),
    FeatureSpec("roc_10", FeatureGroup.MOMENTUM, 10, "Rate of change 10-period"),
    FeatureSpec("roc_20", FeatureGroup.MOMENTUM, 20, "Rate of change 20-period"),
    FeatureSpec("momentum_z", FeatureGroup.MOMENTUM, 20, "Momentum z-score"),
    FeatureSpec("williams_r", FeatureGroup.MOMENTUM, 14, "Williams %R"),
    FeatureSpec("cci", FeatureGroup.MOMENTUM, 20, "Commodity Channel Index"),
    FeatureSpec("stoch_k", FeatureGroup.MOMENTUM, 14, "Stochastic %K"),

    # Microstructure group (8 features)
    FeatureSpec("spread_pips", FeatureGroup.MICROSTRUCTURE, 1, "Current spread"),
    FeatureSpec("spread_ratio", FeatureGroup.MICROSTRUCTURE, 20, "Spread vs 20-period avg"),
    FeatureSpec("volume_ratio", FeatureGroup.MICROSTRUCTURE, 20, "Volume vs 20-period avg"),
    FeatureSpec("obv_slope", FeatureGroup.MICROSTRUCTURE, 20, "OBV trend"),
    FeatureSpec("price_impact", FeatureGroup.MICROSTRUCTURE, 20, "Kyle's lambda estimate"),
    FeatureSpec("amihud_illiq", FeatureGroup.MICROSTRUCTURE, 20, "Amihud illiquidity"),
    FeatureSpec("tick_direction", FeatureGroup.MICROSTRUCTURE, 5, "Up/down tick ratio"),
    FeatureSpec("bid_ask_imbalance", FeatureGroup.MICROSTRUCTURE, 5, "Order flow imbalance"),

    # Temporal group (6 features)
    FeatureSpec("session_hour", FeatureGroup.TEMPORAL, 1, "Hour of session (0-1)"),
    FeatureSpec("day_of_week", FeatureGroup.TEMPORAL, 1, "Day encoding (0-4)"),
    FeatureSpec("session_quality", FeatureGroup.TEMPORAL, 1, "London/NY overlap score"),
    FeatureSpec("minutes_to_close", FeatureGroup.TEMPORAL, 1, "Minutes to session end"),
    FeatureSpec("is_news_hour", FeatureGroup.TEMPORAL, 1, "High-impact news proximity"),
    FeatureSpec("recent_volatility_cluster", FeatureGroup.TEMPORAL, 20, "Vol clustering indicator"),

    # Cross-sectional group (5 features)
    FeatureSpec("dxy_strength", FeatureGroup.CROSS_SECTIONAL, 20, "USD index momentum"),
    FeatureSpec("currency_divergence", FeatureGroup.CROSS_SECTIONAL, 20, "Base vs quote strength"),
    FeatureSpec("pair_correlation", FeatureGroup.CROSS_SECTIONAL, 20, "Rolling pair correlation"),
    FeatureSpec("cross_pair_momentum", FeatureGroup.CROSS_SECTIONAL, 20, "Momentum across pairs"),
    FeatureSpec("regime_dispersion", FeatureGroup.CROSS_SECTIONAL, 20, "Cross-pair regime correlation"),
]


class FeatureEngineer:
    """
    Computes all TabFM features from raw OHLCV + indicator data.

    Features are computed in a streaming fashion to support both
    backtesting (batch) and live (single-bar updates).
    """

    def __init__(self, pair: str, lookback: int = 200):
        self.pair = pair
        self.lookback = lookback
        self._cache: dict[str, np.ndarray] = {}

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all features for a given OHLCV DataFrame.

        Args:
            df: OHLCV DataFrame with columns: open, high, low, close, volume

        Returns:
            DataFrame with computed features
        """
        if len(df) < self.lookback:
            # Pad with NaN if not enough data
            pad_length = self.lookback - len(df)
            df = pd.concat([
                pd.DataFrame(np.nan, index=range(pad_length), columns=df.columns),
                df,
            ], ignore_index=True)

        features = {}

        # Volatility features
        features.update(self._compute_volatility_features(df))

        # Trend features
        features.update(self._compute_trend_features(df))

        # Momentum features
        features.update(self._compute_momentum_features(df))

        # Microstructure features
        features.update(self._compute_microstructure_features(df))

        # Temporal features
        features.update(self._compute_temporal_features(df))

        return pd.DataFrame(features)

    def compute_incremental(self, new_bar: pd.Series, state: dict) -> dict:
        """
        Update features with a single new bar (for live trading).

        Args:
            new_bar: New OHLCV bar
            state: Current feature state

        Returns:
            Updated feature state
        """
        # Placeholder for incremental computation
        # In production, this would update rolling features efficiently
        return state

    def _compute_volatility_features(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        """Compute volatility feature group."""
        features = {}

        # ATR
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)

        # ATR 14
        atr_14 = tr.ewm(alpha=1.0 / 14, adjust=False).mean()
        features["atr_14"] = atr_14.values

        # ATR 50
        atr_50 = tr.ewm(alpha=1.0 / 50, adjust=False).mean()
        features["atr_50"] = atr_50.values

        # ATR ratio
        features["atr_ratio"] = (atr_14 / atr_50.replace(0, np.nan)).fillna(1.0).values

        # Realized volatility
        returns = close.pct_change()
        features["realized_vol_20"] = returns.rolling(20).std().fillna(0).values
        features["realized_vol_60"] = returns.rolling(60).std().fillna(0).values

        # Vol regime (z-score)
        vol_20 = returns.rolling(20).std()
        vol_mean = vol_20.rolling(200).mean()
        vol_std = vol_20.rolling(200).std()
        features["vol_regime"] = ((vol_20 - vol_mean) / vol_std.replace(0, np.nan)).fillna(0).values

        # Garman-Klass volatility
        log_hl = np.log(high / low)
        log_co = np.log(close / df["open"])
        gk = 0.5 * log_hl**2 - (2 * np.log(2) - 1) * log_co**2
        features["garman_klass_vol"] = gk.rolling(20).std().fillna(0).values

        # Parkinson volatility
        parkinson = np.sqrt(log_hl**2 / (4 * np.log(2)))
        features["parkinson_vol"] = parkinson.rolling(20).mean().fillna(0).values

        return features

    def _compute_trend_features(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        """Compute trend feature group."""
        features = {}

        high = df["high"]
        low = df["low"]
        close = df["close"]

        # ADX components
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)

        up_move = high - high.shift(1)
        down_move = low.shift(1) - low
        pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        tr_smooth = tr.ewm(alpha=1.0 / 14, adjust=False).mean()
        pdi = 100.0 * pd.Series(pos_dm, index=df.index).ewm(alpha=1.0 / 14, adjust=False).mean() / tr_smooth.replace(0, np.nan)
        ndi = 100.0 * pd.Series(neg_dm, index=df.index).ewm(alpha=1.0 / 14, adjust=False).mean() / tr_smooth.replace(0, np.nan)

        dx = (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan) * 100.0
        adx = dx.ewm(alpha=1.0 / 14, adjust=False).mean()

        features["adx_14"] = adx.fillna(0).values
        features["adx_slope"] = adx.diff().fillna(0).values
        features["plus_di"] = pdi.fillna(0).values
        features["minus_di"] = ndi.fillna(0).values
        features["di_ratio"] = (pdi / ndi.replace(0, np.nan)).fillna(1.0).values

        # EMA alignment
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema200 = close.ewm(span=200, adjust=False).mean()
        features["ema_alignment"] = np.where(ema50 > ema200, 1.0, -1.0)

        # Price vs EMA
        features["price_vs_ema200"] = ((close - ema200) / ema200.replace(0, np.nan)).fillna(0).values
        features["price_vs_ema50"] = ((close - ema50) / ema50.replace(0, np.nan)).fillna(0).values

        # Trend strength (consecutive bars in same direction)
        direction = np.sign(close.diff())
        trend_strength = pd.Series(0.0, index=df.index)
        for i in range(1, len(direction)):
            if direction.iloc[i] == direction.iloc[i-1] and direction.iloc[i] != 0:
                trend_strength.iloc[i] = trend_strength.iloc[i-1] + 1
        features["trend_strength"] = trend_strength.values

        # Higher TF trend (simplified)
        features["higher_tf_trend"] = np.where(close > ema200, 1.0, -1.0)

        return features

    def _compute_momentum_features(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        """Compute momentum feature group."""
        features = {}

        close = df["close"]

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1.0 / 14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1.0 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        features["rsi_14"] = rsi.fillna(50).values
        features["rsi_slope"] = rsi.diff().fillna(0).values

        # Rate of change
        features["roc_10"] = close.pct_change(10).fillna(0).values
        features["roc_20"] = close.pct_change(20).fillna(0).values

        # Momentum z-score
        roc_20 = close.pct_change(20)
        features["momentum_z"] = ((roc_20 - roc_20.rolling(100).mean()) / roc_20.rolling(100).std().replace(0, np.nan)).fillna(0).values

        # Williams %R
        high_14 = df["high"].rolling(14).max()
        low_14 = df["low"].rolling(14).min()
        features["williams_r"] = ((high_14 - close) / (high_14 - low_14).replace(0, np.nan) * -100).fillna(-50).values

        # CCI
        tp = (df["high"] + df["low"] + close) / 3
        cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std().replace(0, np.nan))
        features["cci"] = cci.fillna(0).values

        # Stochastic %K
        features["stoch_k"] = ((close - low_14) / (high_14 - low_14).replace(0, np.nan) * 100).fillna(50).values

        return features

    def _compute_microstructure_features(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        """Compute microstructure feature group."""
        features = {}

        # Spread (placeholder - would need bid/ask data)
        features["spread_pips"] = np.full(len(df), 0.8)  # Default spread
        features["spread_ratio"] = np.ones(len(df))

        # Volume features
        volume = df.get("volume", pd.Series(1.0, index=df.index))
        vol_ma = volume.rolling(20).mean()
        features["volume_ratio"] = (volume / vol_ma.replace(0, np.nan)).fillna(1.0).values

        # OBV slope
        obv = (np.sign(df["close"].diff()) * volume).cumsum()
        features["obv_slope"] = obv.rolling(20).apply(
            lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 20 else 0,
            raw=True,
        ).fillna(0).values

        # Price impact (simplified Kyle's lambda)
        returns = df["close"].pct_change()
        features["price_impact"] = (returns.rolling(20).corr(volume)).fillna(0).values

        # Amihud illiquidity
        features["amihud_illiq"] = (returns.abs() / volume.replace(0, np.nan)).rolling(20).mean().fillna(0).values

        # Tick direction
        features["tick_direction"] = np.sign(df["close"].diff()).rolling(5).mean().fillna(0).values

        # Bid-ask imbalance (placeholder)
        features["bid_ask_imbalance"] = np.zeros(len(df))

        return features

    def _compute_temporal_features(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        """Compute temporal feature group."""
        features = {}

        if isinstance(df.index, pd.DatetimeIndex):
            # Session hour (normalized)
            features["session_hour"] = (df.index.hour - 7) / 14  # 7-21 UTC normalized to 0-1

            # Day of week (0-4 for trading days)
            dow = df.index.dayofweek
            features["day_of_week"] = dow.where(dow <= 4, 4) / 4.0

            # Session quality (London/NY overlap)
            hour = df.index.hour
            features["session_quality"] = np.where(
                (hour >= 13) & (hour <= 17), 1.0,  # London/NY overlap
                np.where((hour >= 7) & (hour < 13), 0.5, 0.0),  # London only
            )

            # Minutes to close
            features["minutes_to_close"] = np.clip((21 - hour) * 60, 0, 840) / 840

            # Is news hour (placeholder)
            features["is_news_hour"] = np.zeros(len(df))
        else:
            # Fallback for non-datetime index
            for feat in ["session_hour", "day_of_week", "session_quality",
                         "minutes_to_close", "is_news_hour"]:
                features[feat] = np.zeros(len(df))

        # Recent volatility cluster
        returns = df["close"].pct_change()
        vol = returns.rolling(20).std()
        vol_ma = vol.rolling(20).mean()
        features["recent_volatility_cluster"] = (vol > vol_ma * 1.5).astype(float).values

        return features
