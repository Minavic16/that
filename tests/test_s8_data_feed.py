"""
Tests for S8.1 — Live Data Feed
================================
Verifies candle fetching, OHLCV validation, bar-close detection,
candle caching, and ATR calculation.

Run: PYTHONPATH=/root/that python -m pytest tests/test_s8_data_feed.py -v --noconftest
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

NESTQUANT_ROOT = str(Path(__file__).parent.parent)
if NESTQUANT_ROOT not in os.sys.path:
    os.sys.path.insert(0, NESTQUANT_ROOT)

from execution.data_feed import OHLCV, BarState, LiveDataFeed, TIMEFRAME_SECONDS
from execution.mt5_client import MT5Client, MT5Response


# ===================================================================
# OHLCV
# ===================================================================


class TestOHLCV:
    def test_valid_candle(self):
        c = OHLCV(
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            open=1.0800, high=1.0850, low=1.0780, close=1.0830,
            volume=1000,
        )
        assert c.is_valid()
        assert c.validate() == []

    def test_high_less_than_low_invalid(self):
        c = OHLCV(
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            open=1.0800, high=1.0700, low=1.0800, close=1.0750,
            volume=1000,
        )
        errors = c.validate()
        assert any("high" in e and "low" in e for e in errors)

    def test_zero_close_invalid(self):
        c = OHLCV(
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            open=1.0800, high=1.0850, low=1.0780, close=0.0,
            volume=1000,
        )
        assert not c.is_valid()
        assert any("close" in e for e in c.validate())

    def test_naive_timestamp_invalid(self):
        c = OHLCV(
            timestamp=datetime(2026, 1, 1, 12, 0),  # No timezone
            open=1.0800, high=1.0850, low=1.0780, close=1.0830,
            volume=1000,
        )
        assert not c.is_valid()
        assert any("timezone" in e for e in c.validate())


# ===================================================================
# BarState
# ===================================================================


class TestBarState:
    def test_first_bar_returns_true(self):
        state = BarState(pair="EUR/USD", timeframe="H4")
        candles = [
            OHLCV(
                timestamp=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
                open=1.0800, high=1.0850, low=1.0780, close=1.0830, volume=1000,
            )
        ]
        assert state.detect_new_bar(candles) is True

    def test_same_bar_returns_false(self):
        state = BarState(pair="EUR/USD", timeframe="H4")
        ts = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
        candles = [
            OHLCV(timestamp=ts, open=1.0800, high=1.0850, low=1.0780, close=1.0830, volume=1000)
        ]
        state.detect_new_bar(candles)  # First call — sets state
        assert state.detect_new_bar(candles) is False  # Same bar

    def test_new_bar_returns_true(self):
        state = BarState(pair="EUR/USD", timeframe="H4")
        ts1 = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
        ts2 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        c1 = [OHLCV(timestamp=ts1, open=1.0800, high=1.0850, low=1.0780, close=1.0830, volume=1000)]
        c2 = [
            OHLCV(timestamp=ts1, open=1.0800, high=1.0850, low=1.0780, close=1.0830, volume=1000),
            OHLCV(timestamp=ts2, open=1.0830, high=1.0870, low=1.0810, close=1.0860, volume=1200),
        ]
        state.detect_new_bar(c1)
        assert state.detect_new_bar(c2) is True

    def test_empty_candles_returns_false(self):
        state = BarState(pair="EUR/USD", timeframe="H4")
        assert state.detect_new_bar([]) is False


# ===================================================================
# LiveDataFeed
# ===================================================================


class TestLiveDataFeed:
    def _make_client(self) -> MT5Client:
        return MagicMock(spec=MT5Client)

    def test_fetch_candles_converts_pair_format(self):
        client = self._make_client()
        client.fetch_candles.return_value = MT5Response(
            ok=True,
            data=[{
                "time": "2026-01-01T08:00:00+00:00",
                "open": 1.0800, "high": 1.0850, "low": 1.0780, "close": 1.0830,
                "tick_volume": 1000, "spread": 8, "real_volume": 0,
            }],
        )

        feed = LiveDataFeed(client=client, timeframe="H4")
        candles = feed.fetch_candles("EUR/USD", num_bars=50)

        client.fetch_candles.assert_called_once_with(
            symbol="EURUSD", timeframe="H4", num_bars=50,
        )
        assert len(candles) == 1
        assert candles[0].open == 1.0800

    def test_fetch_candles_returns_empty_on_error(self):
        client = self._make_client()
        client.fetch_candles.return_value = MT5Response(ok=False, error="Connection failed")

        feed = LiveDataFeed(client=client)
        candles = feed.fetch_candles("EUR/USD")
        assert candles == []

    def test_fetch_candles_filters_invalid(self):
        client = self._make_client()
        client.fetch_candles.return_value = MT5Response(
            ok=True,
            data=[
                # Valid candle
                {
                    "time": "2026-01-01T08:00:00+00:00",
                    "open": 1.0800, "high": 1.0850, "low": 1.0780, "close": 1.0830,
                    "tick_volume": 1000, "spread": 8, "real_volume": 0,
                },
                # Invalid candle (high < low)
                {
                    "time": "2026-01-01T12:00:00+00:00",
                    "open": 1.0800, "high": 1.0700, "low": 1.0800, "close": 1.0750,
                    "tick_volume": 1000, "spread": 8, "real_volume": 0,
                },
            ],
        )

        feed = LiveDataFeed(client=client)
        candles = feed.fetch_candles("EUR/USD")
        # Only valid candle should remain
        assert len(candles) == 1
        assert candles[0].timestamp.hour == 8

    def test_cache_updated_after_fetch(self):
        client = self._make_client()
        client.fetch_candles.return_value = MT5Response(
            ok=True,
            data=[
                {
                    "time": "2026-01-01T08:00:00+00:00",
                    "open": 1.0800, "high": 1.0850, "low": 1.0780, "close": 1.0830,
                    "tick_volume": 1000, "spread": 8, "real_volume": 0,
                },
            ],
        )

        feed = LiveDataFeed(client=client)
        feed.fetch_candles("EUR/USD")

        cached = feed.get_cached_candles("EUR/USD")
        assert len(cached) == 1
        assert cached[0].close == 1.0830

    def test_get_last_close(self):
        client = self._make_client()
        client.fetch_candles.return_value = MT5Response(
            ok=True,
            data=[{
                "time": "2026-01-01T08:00:00+00:00",
                "open": 1.0800, "high": 1.0850, "low": 1.0780, "close": 1.0830,
                "tick_volume": 1000, "spread": 8, "real_volume": 0,
            }],
        )

        feed = LiveDataFeed(client=client)
        feed.fetch_candles("EUR/USD")

        assert feed.get_last_close("EUR/USD") == 1.0830
        assert feed.get_last_close("GBP/USD") is None

    def test_has_new_bar(self):
        client = self._make_client()
        client.fetch_candles.return_value = MT5Response(
            ok=True,
            data=[
                {
                    "time": "2026-01-01T08:00:00+00:00",
                    "open": 1.0800, "high": 1.0850, "low": 1.0780, "close": 1.0830,
                    "tick_volume": 1000, "spread": 8, "real_volume": 0,
                },
            ],
        )

        feed = LiveDataFeed(client=client)
        candles = feed.fetch_candles("EUR/USD")
        # First fetch → new bar detected
        assert feed.has_new_bar("EUR/USD", candles) is True

    def test_atr_calculation(self):
        client = self._make_client()
        base_ts = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        candles_data = []
        for i in range(20):
            candles_data.append({
                "time": (base_ts + timedelta(hours=4 * i)).isoformat(),
                "open": 1.0800 + i * 0.001,
                "high": 1.0850 + i * 0.001,
                "low": 1.0780 + i * 0.001,
                "close": 1.0830 + i * 0.001,
                "tick_volume": 1000,
                "spread": 8,
                "real_volume": 0,
            })
        client.fetch_candles.return_value = MT5Response(ok=True, data=candles_data)

        feed = LiveDataFeed(client=client)
        feed.fetch_candles("EUR/USD", num_bars=20)

        atr = feed.get_atr("EUR/USD", period=14)
        assert atr is not None
        assert atr > 0  # ATR should be positive

    def test_atr_returns_none_insufficient_data(self):
        client = self._make_client()
        client.fetch_candles.return_value = MT5Response(
            ok=True,
            data=[{
                "time": "2026-01-01T08:00:00+00:00",
                "open": 1.0800, "high": 1.0850, "low": 1.0780, "close": 1.0830,
                "tick_volume": 1000, "spread": 8, "real_volume": 0,
            }],
        )

        feed = LiveDataFeed(client=client)
        feed.fetch_candles("EUR/USD")

        assert feed.get_atr("EUR/USD", period=14) is None

    def test_cache_deduplication(self):
        client = self._make_client()
        ts = "2026-01-01T08:00:00+00:00"
        client.fetch_candles.return_value = MT5Response(
            ok=True,
            data=[{
                "time": ts,
                "open": 1.0800, "high": 1.0850, "low": 1.0780, "close": 1.0830,
                "tick_volume": 1000, "spread": 8, "real_volume": 0,
            }],
        )

        feed = LiveDataFeed(client=client)
        feed.fetch_candles("EUR/USD")
        feed.fetch_candles("EUR/USD")  # Same candle again

        cached = feed.get_cached_candles("EUR/USD")
        assert len(cached) == 1  # Deduplicated

    def test_cache_respects_max_size(self):
        client = self._make_client()
        base_ts = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        candles_data = []
        for i in range(250):  # More than max_cache_size
            candles_data.append({
                "time": (base_ts + timedelta(hours=4 * i)).isoformat(),
                "open": 1.0800 + i * 0.0001,
                "high": 1.0850 + i * 0.0001,
                "low": 1.0780 + i * 0.0001,
                "close": 1.0830 + i * 0.0001,
                "tick_volume": 1000, "spread": 8, "real_volume": 0,
            })
        client.fetch_candles.return_value = MT5Response(ok=True, data=candles_data)

        feed = LiveDataFeed(client=client, max_cache_size=200)
        feed.fetch_candles("EUR/USD", num_bars=250)

        cached = feed.get_cached_candles("EUR/USD")
        assert len(cached) == 200
        # Most recent candles should be kept
        assert cached[-1].timestamp > cached[0].timestamp


# ===================================================================
# TIMEFRAME_SECONDS
# ===================================================================


class TestTimeframeConstants:
    def test_common_timeframes_defined(self):
        assert "M1" in TIMEFRAME_SECONDS
        assert "M5" in TIMEFRAME_SECONDS
        assert "M15" in TIMEFRAME_SECONDS
        assert "M30" in TIMEFRAME_SECONDS
        assert "H1" in TIMEFRAME_SECONDS
        assert "H4" in TIMEFRAME_SECONDS
        assert "D1" in TIMEFRAME_SECONDS

    def test_h4_is_4_hours(self):
        assert TIMEFRAME_SECONDS["H4"] == 14400
