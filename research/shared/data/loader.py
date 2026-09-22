"""Canonical OHLCV data loader.

Wraps `core.data.loader.DataLoader` (pickle-backed multi-timeframe
store) behind the Research OS canonical interface:

- `load(pair, timeframe)` → `OHLCVFrame | None`
- `load_all(pairs, timeframe)` → `dict[str, OHLCVFrame]`

The loader guarantees structural minimums only (DatetimeIndex +
required OHLC columns). It performs NO timezone conversion, NO
imputation, NO filtering, and NO resampling — data quality is judged
by `validate.validate_ohlcv`, never silently fixed here.
"""

from __future__ import annotations

import pandas as pd

from nestquant.core.data.loader import DataLoader as CoreDataLoader
from nestquant.research.shared.data.schema import has_required_columns
from nestquant.research.shared.data.types import OHLCVFrame


class DataLoader(CoreDataLoader):
    """Canonical loader for OHLCV research data."""

    def load(self, pair: str, timeframe: str = "4h") -> OHLCVFrame | None:
        """Load one pair as a canonical OHLCV frame.

        Returns None when the file is missing, unreadable, lacks the
        required OHLC columns, or has no DatetimeIndex. Timezone is
        left exactly as stored; see `validate_timestamps`.
        """
        df = self.load_pair(pair, timeframe)
        if df is None:
            return None
        if not has_required_columns(df):
            return None
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df = df.copy()
                df.index = pd.to_datetime(df.index)
            except (ValueError, TypeError):
                return None
        return df

    def load_all(self, pairs: list[str], timeframe: str = "4h") -> dict[str, OHLCVFrame]:
        """Load multiple pairs. Pairs must be passed explicitly.

        Unlike the core loader, there is no global-config universe
        fallback and no minimum-bar filter here — pair selection and
        sufficiency are research decisions, not loading decisions.
        Missing/unloadable pairs are skipped.
        """
        frames: dict[str, OHLCVFrame] = {}
        for pair in pairs:
            df = self.load(pair, timeframe)
            if df is not None:
                frames[pair] = df
        return frames
