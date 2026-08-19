"""
Data loader for regime training data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nestquant.config.settings import get_config


# Timeframe directory mapping: user-facing name -> subdirectory under data_dir
TIMEFRAME_DIR_MAP: dict[str, str] = {
    "1min": "1min",
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "1h": "1h",
    "4h": "4h",
    "1day": "1day",
}

# Bars per trading day for each timeframe (FX: ~24h/day, ~6.5 major session hours
# used for annualization, but bar count is what matters for lookbacks)
TIMEFRAME_BARS_PER_DAY: dict[str, int] = {
    "1min": 1440,
    "5min": 288,
    "15min": 96,
    "30min": 48,
    "1h": 24,
    "4h": 6,
    "1day": 1,
}


class DataLoader:
    """
    Load historical OHLCV data from pickle files.

    Supports multi-timeframe data stored in subdirectories:
        data_dir/1min/EUR_USD.pkl
        data_dir/1h/EUR_USD.pkl
        data_dir/4h/EUR_USD.pkl

    Falls back to legacy flat layout (data_dir/EUR_USD.pkl) if
    the timeframe subdirectory does not exist.
    """

    def __init__(self, data_dir: str | None = None):
        config = get_config()
        self.data_dir = Path(data_dir or config.data.data_dir)

    def _resolve_path(self, pair: str, timeframe: str) -> Path:
        """Resolve pickle file path for a pair and timeframe.

        Tries timeframe subdirectory first, falls back to flat layout.
        """
        pair_file = pair.replace("/", "_")

        # Try timeframe subdirectory: data_dir/1h/EUR_USD.pkl
        tf_dir = TIMEFRAME_DIR_MAP.get(timeframe)
        if tf_dir:
            tf_path = self.data_dir / tf_dir / f"{pair_file}.pkl"
            if tf_path.exists():
                return tf_path

        # Fallback: flat layout (legacy 1min data)
        return self.data_dir / f"{pair_file}.pkl"

    def load_pair(self, pair: str, timeframe: str = "1h") -> pd.DataFrame | None:
        """
        Load data for a single pair at the specified timeframe.

        Args:
            pair: Currency pair (e.g., "EUR/USD")
            timeframe: Data timeframe ("1min", "5min", "15min", "30min", "1h", "4h", "1day")

        Returns:
            OHLCV DataFrame or None if not found
        """
        file_path = self._resolve_path(pair, timeframe)

        if not file_path.exists():
            return None

        try:
            df = pd.read_pickle(file_path)
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            return df
        except Exception:
            return None

    def load_pairs(
        self,
        pairs: list[str] | None = None,
        timeframe: str = "1h",
        min_bars: int = 100,
    ) -> dict[str, pd.DataFrame]:
        """
        Load data for multiple pairs.

        Args:
            pairs: List of currency pairs to load
            timeframe: Data timeframe
            min_bars: Minimum number of bars to include a pair

        Returns:
            Dict mapping pair to OHLCV DataFrame
        """
        config = get_config()
        if pairs is None:
            pairs = list(config.universe.all_pairs)

        pair_dfs = {}
        for pair in pairs:
            df = self.load_pair(pair, timeframe)
            if df is not None and len(df) > min_bars:
                pair_dfs[pair] = df

        return pair_dfs

    def get_available_pairs(self, timeframe: str = "1h") -> list[str]:
        """Get list of pairs with available data for a timeframe."""
        config = get_config()
        available = []
        for pair in config.universe.all_pairs:
            if self.load_pair(pair, timeframe) is not None:
                available.append(pair)
        return available

    def get_data_info(self, timeframe: str = "1h") -> dict:
        """Get information about available data for a timeframe."""
        config = get_config()
        info = {
            "timeframe": timeframe,
            "total_pairs": 0,
            "total_bars": 0,
            "pairs": {},
        }

        for pair in config.universe.all_pairs:
            df = self.load_pair(pair, timeframe)
            if df is not None:
                info["total_pairs"] += 1
                info["total_bars"] += len(df)
                info["pairs"][pair] = {
                    "bars": len(df),
                    "start": str(df.index[0]),
                    "end": str(df.index[-1]),
                }

        return info
