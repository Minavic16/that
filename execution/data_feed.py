"""
NestQuant S8 — Live Data Feed
==============================
Fetches OHLCV candles from MT5 bridge, detects bar-close events,
validates data integrity, and caches for strategy consumption.

This module:
  - Polls MT5 bridge for candle data
  - Detects when a new bar closes (timestamp change)
  - Validates OHLCV integrity before returning
  - Caches last N bars per pair
  - Enforces causality: no future data leakage

This module does NOT:
  - Import MetaTrader5 directly
  - Perform strategy calculations
  - Make trading decisions
  - Place orders
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

from execution.mt5_client import MT5Client, MT5Response

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timeframe mapping (string → seconds for bar-close detection)
# ---------------------------------------------------------------------------

TIMEFRAME_SECONDS: dict[str, int] = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}


# ---------------------------------------------------------------------------
# OHLCV validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OHLCV:
    """Single OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    spread: float = 0.0
    real_volume: float = 0.0

    def validate(self) -> list[str]:
        """Return validation errors. Empty if valid."""
        errors: list[str] = []

        if self.open <= 0:
            errors.append(f"open must be positive, got {self.open}")
        if self.high <= 0:
            errors.append(f"high must be positive, got {self.high}")
        if self.low <= 0:
            errors.append(f"low must be positive, got {self.low}")
        if self.close <= 0:
            errors.append(f"close must be positive, got {self.close}")

        if self.high < self.low:
            errors.append(f"high ({self.high}) < low ({self.low})")
        if self.high < self.open:
            errors.append(f"high ({self.high}) < open ({self.open})")
        if self.high < self.close:
            errors.append(f"high ({self.high}) < close ({self.close})")
        if self.low > self.open:
            errors.append(f"low ({self.low}) > open ({self.open})")
        if self.low > self.close:
            errors.append(f"low ({self.low}) > close ({self.close})")

        if self.timestamp.tzinfo is None:
            errors.append("timestamp must be timezone-aware")

        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0


# ---------------------------------------------------------------------------
# Bar-close detection
# ---------------------------------------------------------------------------


@dataclass
class BarState:
    """Tracks bar-close state for a single pair."""

    pair: str
    timeframe: str
    last_bar_timestamp: Optional[datetime] = None
    bar_count: int = 0

    def detect_new_bar(self, candles: list[OHLCV]) -> bool:
        """Detect if a new bar has closed since last check.

        Args:
            candles: List of candles from fetch, most recent at end.

        Returns:
            True if a new bar closed (timestamp changed from last known).
        """
        if not candles:
            return False

        latest_ts = candles[-1].timestamp

        if self.last_bar_timestamp is None:
            self.last_bar_timestamp = latest_ts
            self.bar_count = len(candles)
            return True

        if latest_ts > self.last_bar_timestamp:
            self.last_bar_timestamp = latest_ts
            self.bar_count = len(candles)
            return True

        return False


# ---------------------------------------------------------------------------
# Data feed
# ---------------------------------------------------------------------------


@dataclass
class LiveDataFeed:
    """Fetches and validates OHLCV data from MT5 bridge.

    Manages:
      - Candle fetching per pair
      - Bar-close detection
      - OHLCV validation
      - Candle caching
    """

    client: MT5Client
    timeframe: str = "H4"
    max_cache_size: int = 200
    _caches: dict[str, list[OHLCV]] = field(default_factory=dict)
    _bar_states: dict[str, BarState] = field(default_factory=dict)

    def fetch_candles(
        self,
        pair: str,
        num_bars: int = 100,
    ) -> list[OHLCV]:
        """Fetch candles from MT5 bridge and return validated OHLCV list.

        Args:
            pair: Currency pair in "BASE/QUOTE" format (e.g., "EUR/USD").
                  Converted to MT5 format "EURUSD" for the bridge.
            num_bars: Number of bars to fetch.

        Returns:
            List of validated OHLCV candles, most recent at end.
            Empty list on error.
        """
        symbol = pair.replace("/", "")
        resp = self.client.fetch_candles(
            symbol=symbol,
            timeframe=self.timeframe,
            num_bars=num_bars,
        )

        if not resp.ok:
            logger.error(f"Failed to fetch candles for {pair}: {resp.error}")
            return []

        raw_candles = resp.data if isinstance(resp.data, list) else []
        if not raw_candles:
            logger.warning(f"No candle data returned for {pair}")
            return []

        candles = self._parse_candles(raw_candles)
        if not candles:
            return []

        # Validate all candles
        valid_candles = []
        for c in candles:
            errors = c.validate()
            if errors:
                logger.warning(f"Invalid candle for {pair} at {c.timestamp}: {errors}")
                continue
            valid_candles.append(c)

        if not valid_candles:
            logger.error(f"All candles invalid for {pair}")
            return []

        # Update cache
        self._update_cache(pair, valid_candles)

        return valid_candles

    def has_new_bar(self, pair: str, candles: list[OHLCV]) -> bool:
        """Check if a new bar has closed since last check.

        Args:
            pair: Currency pair.
            candles: Latest candles from fetch_candles().

        Returns:
            True if a new bar closed.
        """
        if pair not in self._bar_states:
            self._bar_states[pair] = BarState(pair=pair, timeframe=self.timeframe)
        return self._bar_states[pair].detect_new_bar(candles)

    def get_cached_candles(self, pair: str) -> list[OHLCV]:
        """Get cached candles for a pair."""
        return list(self._caches.get(pair, []))

    def get_last_close(self, pair: str) -> Optional[float]:
        """Get the last close price for a pair from cache."""
        cache = self._caches.get(pair, [])
        if cache:
            return cache[-1].close
        return None

    def get_last_candle(self, pair: str) -> Optional[OHLCV]:
        """Get the last candle for a pair from cache."""
        cache = self._caches.get(pair, [])
        if cache:
            return cache[-1]
        return None

    def get_atr(self, pair: str, period: int = 14) -> Optional[float]:
        """Calculate ATR from cached candles.

        Args:
            pair: Currency pair.
            period: ATR lookback period.

        Returns:
            Current ATR value, or None if insufficient data.
        """
        cache = self._caches.get(pair, [])
        if len(cache) < period + 1:
            return None

        true_ranges = []
        for i in range(1, len(cache)):
            high = cache[i].high
            low = cache[i].low
            prev_close = cache[i - 1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        if len(true_ranges) < period:
            return None

        # Simple moving average of true ranges
        atr = sum(true_ranges[-period:]) / period
        return atr

    def _parse_candles(self, raw: list[dict]) -> list[OHLCV]:
        """Parse raw bridge response into OHLCV objects."""
        candles = []
        for r in raw:
            try:
                ts = r.get("time")
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                elif isinstance(ts, (int, float)):
                    dt = datetime.fromtimestamp(ts, tz=UTC)
                else:
                    continue

                candles.append(OHLCV(
                    timestamp=dt,
                    open=float(r.get("open", 0)),
                    high=float(r.get("high", 0)),
                    low=float(r.get("low", 0)),
                    close=float(r.get("close", 0)),
                    volume=float(r.get("tick_volume", r.get("volume", 0))),
                    spread=float(r.get("spread", 0)),
                    real_volume=float(r.get("real_volume", 0)),
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse candle: {e}")
                continue

        return candles

    def _update_cache(self, pair: str, new_candles: list[OHLCV]) -> None:
        """Update candle cache, maintaining sorted order and size limit."""
        if pair not in self._caches:
            self._caches[pair] = list(new_candles)
        else:
            existing = self._caches[pair]
            # Merge: add new candles, deduplicate by timestamp
            seen = {c.timestamp for c in existing}
            for c in new_candles:
                if c.timestamp not in seen:
                    existing.append(c)
                    seen.add(c.timestamp)
            existing.sort(key=lambda c: c.timestamp)

        # Trim to max size (applies to both new and merged caches)
        if len(self._caches[pair]) > self.max_cache_size:
            self._caches[pair] = self._caches[pair][-self.max_cache_size:]

    def __repr__(self) -> str:
        return (
            f"<LiveDataFeed(timeframe={self.timeframe}, "
            f"cached_pairs={list(self._caches.keys())})>"
        )
