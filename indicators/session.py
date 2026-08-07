"""
Session filter for London-NY overlap trading hours.
"""

from __future__ import annotations

import pandas as pd

from nestquant.config.settings import (
    SESSION_CLOSE_UTC,
    SESSION_OPEN_UTC,
    SKIP_FRIDAY_CLOSE,
    SKIP_MONDAY_OPEN,
)


def is_active_session(dt: pd.Timestamp) -> bool:
    """
    Return True if dt falls within the London–New York overlap session (UTC).

    Filters applied:
        • Weekends excluded entirely
        • Monday 00:00–SESSION_OPEN_UTC skipped (erratic open)  [if configured]
        • Friday after 17:00 skipped (liquidity dries up)       [if configured]
        • Exact session window: SESSION_OPEN_UTC ≤ hour < SESSION_CLOSE_UTC

    Args:
        dt: Timestamp to check

    Returns:
        True if within active trading session
    """
    if dt.weekday() >= 5:
        return False  # Saturday / Sunday

    if SKIP_MONDAY_OPEN and dt.weekday() == 0 and dt.hour < SESSION_OPEN_UTC:
        return False

    if SKIP_FRIDAY_CLOSE and dt.weekday() == 4 and dt.hour >= 17:
        return False

    return SESSION_OPEN_UTC <= dt.hour < SESSION_CLOSE_UTC
