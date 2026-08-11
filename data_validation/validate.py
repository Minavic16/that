"""Z-Score Research Engine — Data Validation."""
from __future__ import annotations

import numpy as np
import pandas as pd
from zscore.contracts import MarketData, ValidatedMarketData, ValidationReport


def validate_market_data(data: MarketData) -> ValidatedMarketData:
    """Run all validation checks on raw market data.

    Checks:
    - Timestamps are strictly monotonically increasing
    - No duplicate timestamps
    - No missing bars (gap detection)
    - OHLC consistency: high >= low, high >= open, high >= close, low <= open, low <= close
    - No NaN in OHLC columns
    """
    ts = data.timestamps
    n = data.n

    # Duplicate timestamps
    duplicates = int(pd.Index(ts).duplicated().sum())

    # Monotonic ordering
    is_ordered = bool(pd.Series(ts).is_monotonic_increasing)

    # Gap detection (expect uniform spacing, flag if gap > 2x median gap)
    if n > 1:
        diffs = np.diff(ts.view(np.int64))
        median_gap = np.median(diffs)
        gap_threshold = median_gap * 2
        gap_indices = np.where(diffs > gap_threshold)[0]
        gap_timestamps = [ts[i + 1] for i in gap_indices]
    else:
        gap_timestamps = []

    missing_bars = len(gap_timestamps)

    # OHLC consistency
    ohlc_violations = 0
    ohlc_violations += int(np.sum(data.high < data.low))
    ohlc_violations += int(np.sum(data.high < data.open))
    ohlc_violations += int(np.sum(data.high < data.close))
    ohlc_violations += int(np.sum(data.low > data.open))
    ohlc_violations += int(np.sum(data.low > data.close))

    # NaN counts
    nan_counts = {
        'open': int(np.sum(np.isnan(data.open))),
        'high': int(np.sum(np.isnan(data.high))),
        'low': int(np.sum(np.isnan(data.low))),
        'close': int(np.sum(np.isnan(data.close))),
    }

    is_valid = (
        is_ordered
        and duplicates == 0
        and missing_bars == 0
        and ohlc_violations == 0
        and all(v == 0 for v in nan_counts.values())
    )

    report = ValidationReport(
        pair=data.pair,
        total_bars=n,
        duplicate_timestamps=duplicates,
        missing_bars=missing_bars,
        gap_timestamps=gap_timestamps,
        ohlc_violations=ohlc_violations,
        nan_counts=nan_counts,
        is_valid=is_valid,
    )

    return ValidatedMarketData(
        market_data=data,
        validation=report,
    )
