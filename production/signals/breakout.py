"""
Breakout signal generator using swing high/low detection.
"""

from __future__ import annotations

import pandas as pd

from nestquant.core.tooling.indicators.atr import calculate_atr
from nestquant.core.tooling.indicators.swing import swing_high_series, swing_low_series
from nestquant.production.signals.base import BaseSignal, SignalResult


# Research-validated defaults (S0-S6: ATR_SL_MULT=2.0, RRR=3.5)
RESEARCH_DEFAULTS = {
    "lookback": 5,
    "atr_period": 14,
    "atr_sl_multiplier": 2.0,
    "rrr": 3.5,
}


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
        atr_sl_multiplier: float = 2.0,
        rrr: float = 3.5,
    ):
        super().__init__("breakout")
        self.lookback = lookback
        self.atr_period = atr_period
        self.atr_sl_multiplier = atr_sl_multiplier
        self.rrr = rrr

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
            tp_price = entry_price + (current_atr * self.atr_sl_multiplier * self.rrr)

        elif not pd.isna(current_low) and prev_close >= current_low > current_close:
            direction = "SELL"
            entry_price = current_low
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
                "swing_high": current_high,
                "swing_low": current_low,
                "atr": current_atr,
                "lookback": self.lookback,
            },
        )
