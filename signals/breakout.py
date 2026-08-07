"""
Breakout signal generator using swing high/low detection.
"""

from __future__ import annotations

import pandas as pd

from nestquant.config.settings import ATR_SL_MULTIPLIER
from nestquant.indicators.atr import calculate_atr
from nestquant.indicators.swing import swing_high_series, swing_low_series
from nestquant.signals.base import BaseSignal, SignalResult


class BreakoutSignal(BaseSignal):
    """
    Generates breakout signals when price breaks confirmed swing levels.

    BUY when price > confirmed swing high
    SELL when price < confirmed swing low
    """

    def __init__(
        self,
        lookback: int = 5,
        atr_period: int = 14,
        atr_sl_multiplier: float = ATR_SL_MULTIPLIER,
    ):
        super().__init__("breakout")
        self.lookback = lookback
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier

    def generate(self, df: pd.DataFrame, pair: str) -> SignalResult:
        """
        Generate breakout signal from OHLCV data.

        Args:
            df: OHLCV DataFrame with at least lookback*2+1 rows
            pair: Currency pair identifier

        Returns:
            SignalResult with BUY/SELL/NEUTRAL direction
        """
        if len(df) < self.lookback * 2 + 2:
            return SignalResult(pair=pair, direction="NEUTRAL")

        # Calculate swing levels
        swing_high = swing_high_series(df, self.lookback)
        swing_low = swing_low_series(df, self.lookback)

        # Get current values (last confirmed swings)
        current_high = swing_high.iloc[-2]  # Use previous bar to avoid lookahead
        current_low = swing_low.iloc[-2]
        current_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        # Calculate ATR for stop loss
        atr = calculate_atr(df, self.atr_period)
        current_atr = atr.iloc[-1]

        # Determine signal
        direction = "NEUTRAL"
        entry_price = None
        sl_price = None
        tp_price = None

        if not pd.isna(current_high) and prev_close <= current_high < current_close:
            direction = "BUY"
            entry_price = current_high
            sl_price = entry_price - (current_atr * self.atr_sl_multiplier)
            tp_price = entry_price + (current_atr * self.atr_sl_multiplier * 2.0)

        elif not pd.isna(current_low) and prev_close >= current_low > current_close:
            direction = "SELL"
            entry_price = current_low
            sl_price = entry_price + (current_atr * self.atr_sl_multiplier)
            tp_price = entry_price - (current_atr * self.atr_sl_multiplier * 2.0)

        return SignalResult(
            pair=pair,
            direction=direction,
            strength=1.0 if direction != "NEUTRAL" else 0.0,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            metadata={
                "swing_high": current_high,
                "swing_low": current_low,
                "atr": current_atr,
                "lookback": self.lookback,
            },
        )
