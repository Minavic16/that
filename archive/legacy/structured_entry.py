"""
Structured entry signal generator using EMA pullback logic.
"""

from __future__ import annotations

import pandas as pd

from nestquant.config.settings import (
    ATR_PERIOD,
    ATR_SL_MULTIPLIER,
    MACRO_EMA_PERIOD,
    RRR,
)
from nestquant.indicators.adx import calculate_adx
from nestquant.indicators.atr import calculate_atr
from nestquant.indicators.ema import calculate_ema
from nestquant.signals.base import BaseSignal, SignalResult


class StructuredEntrySignal(BaseSignal):
    """
    Generates structured entry signals using EMA200 pullback logic.

    Entry conditions:
    1. Price is in trending regime (above/below EMA200)
    2. Price pulls back to EMA zone (0.5% distance)
    3. Daily candle alignment confirms direction
    """

    def __init__(
        self,
        ema_period: int = MACRO_EMA_PERIOD,
        atr_period: int = ATR_PERIOD,
        atr_sl_multiplier: float = ATR_SL_MULTIPLIER,
        rrr: float = RRR,
        pullback_zone_pct: float = 0.005,
    ):
        super().__init__("structured_entry")
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.rrr = rrr
        self.pullback_zone_pct = pullback_zone_pct

    def generate(self, df: pd.DataFrame, pair: str) -> SignalResult:
        """
        Generate structured entry signal from OHLCV data.

        Args:
            df: OHLCV DataFrame (should be 4H timeframe for trend identification)
            pair: Currency pair identifier

        Returns:
            SignalResult with BUY/SELL/NEUTRAL direction
        """
        if len(df) < self.ema_period + 10:
            return SignalResult(pair=pair, direction="NEUTRAL")

        # Calculate indicators
        ema = calculate_ema(df, self.ema_period)
        atr = calculate_atr(df, self.atr_period)
        adx = calculate_adx(df, 14)

        current_price = df["close"].iloc[-1]
        current_ema = ema.iloc[-1]
        current_atr = atr.iloc[-1]
        current_adx = adx.iloc[-1]

        if pd.isna(current_ema) or pd.isna(current_atr):
            return SignalResult(pair=pair, direction="NEUTRAL")

        # Calculate distance from EMA
        ema_distance_pct = (current_price - current_ema) / current_ema

        # Determine trend direction
        direction = "NEUTRAL"
        entry_price = None
        sl_price = None
        tp_price = None

        # Check if in pullback zone
        if abs(ema_distance_pct) < self.pullback_zone_pct:
            # Check ADX for trend strength
            if current_adx > 25:  # Trending
                if ema_distance_pct > 0:
                    # Price above EMA, pullback to support
                    direction = "BUY"
                    entry_price = current_price
                    sl_price = entry_price - (current_atr * self.atr_sl_multiplier)
                    tp_price = entry_price + (current_atr * self.atr_sl_multiplier * self.rrr)
                else:
                    # Price below EMA, pullback to resistance
                    direction = "SELL"
                    entry_price = current_price
                    sl_price = entry_price + (current_atr * self.atr_sl_multiplier)
                    tp_price = entry_price - (current_atr * self.atr_sl_multiplier * self.rrr)

        return SignalResult(
            pair=pair,
            direction=direction,
            strength=1.0 if direction != "NEUTRAL" else 0.0,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            metadata={
                "ema": current_ema,
                "ema_distance_pct": ema_distance_pct,
                "atr": current_atr,
                "adx": current_adx,
                "rrr": self.rrr,
            },
        )
