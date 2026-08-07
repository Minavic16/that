"""
Data loader for regime training data.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd

from nestquant.config.settings import get_config


class DataLoader:
    """
    Load historical OHLCV data from pickle files.
    """

    def __init__(self, data_dir: Optional[str] = None):
        config = get_config()
        self.data_dir = Path(data_dir or config.data.data_dir)

    def load_pair(self, pair: str, timeframe: str = "1min") -> Optional[pd.DataFrame]:
        """
        Load data for a single pair.

        Args:
            pair: Currency pair (e.g., "EUR/USD")
            timeframe: Data timeframe

        Returns:
            OHLCV DataFrame or None if not found
        """
        # Convert pair format: EUR/USD -> EUR_USD
        pair_file = pair.replace("/", "_")
        file_path = self.data_dir / f"{pair_file}.pkl"

        if not file_path.exists():
            return None

        try:
            df = pd.read_pickle(file_path)
            # Ensure datetime index
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            return df
        except Exception:
            return None

    def load_pairs(
        self,
        pairs: Optional[list[str]] = None,
        timeframe: str = "1min",
    ) -> dict[str, pd.DataFrame]:
        """
        Load data for multiple pairs.

        Args:
            pairs: List of currency pairs to load
            timeframe: Data timeframe

        Returns:
            Dict mapping pair to OHLCV DataFrame
        """
        config = get_config()
        if pairs is None:
            pairs = list(config.universe.all_pairs)

        pair_dfs = {}
        for pair in pairs:
            df = self.load_pair(pair, timeframe)
            if df is not None and len(df) > 1000:
                pair_dfs[pair] = df

        return pair_dfs

    def get_available_pairs(self) -> list[str]:
        """Get list of pairs with available data."""
        config = get_config()
        available = []
        for pair in config.universe.all_pairs:
            if self.load_pair(pair) is not None:
                available.append(pair)
        return available

    def get_data_info(self) -> dict:
        """Get information about available data."""
        config = get_config()
        info = {
            "total_pairs": 0,
            "total_bars": 0,
            "pairs": {},
        }

        for pair in config.universe.all_pairs:
            df = self.load_pair(pair)
            if df is not None:
                info["total_pairs"] += 1
                info["total_bars"] += len(df)
                info["pairs"][pair] = {
                    "bars": len(df),
                    "start": str(df.index[0]),
                    "end": str(df.index[-1]),
                }

        return info
