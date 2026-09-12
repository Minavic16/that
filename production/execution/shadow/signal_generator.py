"""
Shadow signal generator — strictly causal Variant B (S6C-2026-001 baseline).

Implements the frozen S6 breakout configuration exactly as validated in
S6C-2026-001 Variant B. All parameters match the comparison script:

  lookback=5, atr_period=14, atr_sl_mult=2.0, rrr=3.5,
  max_hold_days=7, breakeven_ratio=0.8, timeframe 4h

Causality guarantee:
  Swing levels are sourced from `indicators.swing`, which internally does
  center=True + shift(lookback) to eliminate lookahead. The generator
  additionally requires one bar of confirmation by reading `swing.iloc[-2]`
  (previous bar's confirmed level) against close[-1] vs close[-2].

No broker imports, no network, no mutable strategy logic.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any, Optional

import pandas as pd

from nestquant.core.tooling.indicators.atr import calculate_atr
from nestquant.core.tooling.indicators.swing import swing_high_series, swing_low_series


# ---------------------------------------------------------------------------
# Frozen Variant B constants (DO NOT MODIFY — see docs/S7_PROTOCOL.md)
# ---------------------------------------------------------------------------

LOOKBACK = 5
ATR_PERIOD = 14
ATR_SL_MULT = 2.0
RRR = 3.5
MAX_HOLD_DAYS = 7
BREAKEVEN_RATIO = 0.8
TIMEFRAME = "4h"
BARS_PER_DAY_4H = 6

STRATEGY_PARAMS: dict[str, Any] = {
    "lookback": LOOKBACK,
    "atr_period": ATR_PERIOD,
    "atr_sl_mult": ATR_SL_MULT,
    "rrr": RRR,
    "max_hold_days": MAX_HOLD_DAYS,
    "breakeven_ratio": BREAKEVEN_RATIO,
}


@dataclass(frozen=True)
class ShadowSignalRecord:
    """Immutable per-signal record per S7 Protocol §3.1 (shadow mode).

    All price fields are in quote currency. Timestamp is bar close in UTC.
    """

    signal_id: str
    timestamp: str  # ISO 8601 UTC
    symbol: str  # e.g. "EUR/USD" (slash form)
    direction: str  # "BUY" | "SELL"
    strategy_params: dict[str, Any]
    swing_level: float
    signal_bar_close: float
    expected_entry: float
    expected_sl: float
    expected_tp: float
    atr_at_signal: float
    spread_at_signal: float
    # Shadow-specific observability
    bar_open: float
    bar_high: float
    bar_low: float
    generation_latency_ms: float
    policy_version: str = "s7-shadow-v1"
    research_run_id: str = "S6C-2026-001-variant-b"


class ShadowCausalSignalGenerator:
    """Stateless, strictly causal breakout signal generator for shadow mode.

    Usage (incremental, bar-by-bar):
        gen = ShadowCausalSignalGenerator()
        record = gen.generate(historical_df_up_to_bar_close, pair="EUR/USD")
        # record is None if NEUTRAL, else ShadowSignalRecord

    The generator does not retain state; the caller supplies the full
    DataFrame slice ending at the bar to evaluate. This makes fidelity
    testing trivial and eliminates hidden state bugs.

    All indicators are causally safe:
      - swing_*_series: shifted by lookback
      - calculate_atr: Wilder's smoothing (causal)
    """

    def __init__(
        self,
        lookback: int = LOOKBACK,
        atr_period: int = ATR_PERIOD,
        atr_sl_mult: float = ATR_SL_MULT,
        rrr: float = RRR,
        spread_pips_map: Optional[dict[str, float]] = None,
        default_spread: float = 0.3,
    ) -> None:
        self.lookback = lookback
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.rrr = rrr
        self.spread_pips_map = spread_pips_map or {}
        self.default_spread = default_spread

    def _spread_for(self, pair: str) -> float:
        return float(self.spread_pips_map.get(pair, self.default_spread))

    def generate(
        self,
        df: pd.DataFrame,
        pair: str,
    ) -> Optional[ShadowSignalRecord]:
        """Evaluate one bar close for a breakout signal.

        Args:
            df: OHLCV DataFrame ending at the bar to evaluate (inclusive).
                Must have columns open/high/low/close and a DatetimeIndex
                (UTC preferred). At least lookback*2 + atr_period + 2 bars.
            pair: Symbol in slash form, e.g. "EUR/USD".

        Returns:
            ShadowSignalRecord if BUY/SELL, else None for NEUTRAL.
        """
        if df is None or len(df) < self.lookback * 2 + self.atr_period + 2:
            return None
        if not {"open", "high", "low", "close"}.issubset(df.columns):
            return None

        t0 = time.perf_counter()

        swing_high = swing_high_series(df, self.lookback)
        swing_low = swing_low_series(df, self.lookback)
        atr = calculate_atr(df, self.atr_period)

        # Causality: use previous bar's confirmed swing level
        try:
            current_high = float(swing_high.iloc[-2])
            current_low = float(swing_low.iloc[-2])
            current_close = float(df["close"].iloc[-1])
            prev_close = float(df["close"].iloc[-2])
            current_atr = float(atr.iloc[-1])
            bar_open = float(df["open"].iloc[-1])
            bar_high = float(df["high"].iloc[-1])
            bar_low = float(df["low"].iloc[-1])
            bar_ts = df.index[-1]
        except Exception:
            return None

        # Bar close timestamp must be valid
        if pd.isna(current_high) and pd.isna(current_low):
            return None
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        direction: Optional[str] = None
        swing_level: Optional[float] = None

        if not pd.isna(current_high) and prev_close <= current_high < current_close:
            direction = "BUY"
            swing_level = current_high
        elif not pd.isna(current_low) and prev_close >= current_low > current_close:
            direction = "SELL"
            swing_level = current_low
        else:
            return None

        # Compute intended entry / SL / TP (at swing level, not next-bar open)
        assert direction is not None and swing_level is not None
        atr_dist = current_atr * self.atr_sl_mult
        if direction == "BUY":
            expected_entry = float(swing_level)
            expected_sl = float(expected_entry - atr_dist)
            expected_tp = float(expected_entry + atr_dist * self.rrr)
        else:
            expected_entry = float(swing_level)
            expected_sl = float(expected_entry + atr_dist)
            expected_tp = float(expected_entry - atr_dist * self.rrr)

        # Basic sanity: SL/TP must be on correct side
        if direction == "BUY" and not (expected_sl < expected_entry < expected_tp):
            return None
        if direction == "SELL" and not (expected_sl > expected_entry > expected_tp):
            return None

        # Normalize timestamp to ISO8601 UTC
        if isinstance(bar_ts, pd.Timestamp):
            if bar_ts.tzinfo is None:
                bar_ts = bar_ts.tz_localize(timezone.utc)
            else:
                bar_ts = bar_ts.tz_convert(timezone.utc)
            ts_iso = bar_ts.isoformat()
        else:
            ts_iso = str(bar_ts)

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return ShadowSignalRecord(
            signal_id=str(uuid.uuid4()),
            timestamp=ts_iso,
            symbol=pair,
            direction=direction,
            strategy_params=dict(STRATEGY_PARAMS),
            swing_level=float(swing_level),
            signal_bar_close=float(current_close),
            expected_entry=float(expected_entry),
            expected_sl=float(expected_sl),
            expected_tp=float(expected_tp),
            atr_at_signal=float(current_atr),
            spread_at_signal=float(self._spread_for(pair)),
            bar_open=float(bar_open),
            bar_high=float(bar_high),
            bar_low=float(bar_low),
            generation_latency_ms=float(latency_ms),
        )

    def generate_batch(
        self,
        df_full: pd.DataFrame,
        pair: str,
    ) -> list[ShadowSignalRecord]:
        """Replay a full history bar-by-bar (for fidelity testing).

        Iterates from the earliest evaluable bar to the last, calling
        `generate` on the growing prefix. Returns all signals in chronological
        order. No lookahead: each call sees only data up to that bar.
        """
        if df_full is None or len(df_full) == 0:
            return []
        warmup = self.lookback * 2 + self.atr_period + 2
        out: list[ShadowSignalRecord] = []
        for i in range(warmup, len(df_full) + 1):
            prefix = df_full.iloc[:i]
            rec = self.generate(prefix, pair)
            if rec is not None:
                out.append(rec)
        return out
