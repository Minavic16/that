"""
Time and session utilities.
"""

from __future__ import annotations

from datetime import datetime, time

from nestquant.core.configuration.settings import SESSION_CLOSE_UTC, SESSION_OPEN_UTC


def is_trading_day(dt: datetime) -> bool:
    """
    Check if a datetime is a trading day (not weekend).

    Args:
        dt: Datetime to check

    Returns:
        True if trading day
    """
    return dt.weekday() < 5  # Monday=0, Friday=4


def get_session_hours() -> tuple[time, time]:
    """
    Get trading session hours in UTC.

    Returns:
        Tuple of (open_time, close_time)
    """
    return (
        time(hour=SESSION_OPEN_UTC, minute=0),
        time(hour=SESSION_CLOSE_UTC, minute=0),
    )


def is_within_session(dt: datetime) -> bool:
    """
    Check if a datetime is within trading session hours.

    Args:
        dt: Datetime to check

    Returns:
        True if within session
    """
    if not is_trading_day(dt):
        return False

    session_open, session_close = get_session_hours()
    current_time = dt.time()

    return session_open <= current_time < session_close


def get_session_progress(dt: datetime) -> float:
    """
    Get progress through the trading session (0.0 to 1.0).

    Args:
        dt: Datetime to check

    Returns:
        Session progress as float
    """
    session_open, session_close = get_session_hours()
    current_time = dt.time()

    if current_time < session_open:
        return 0.0
    elif current_time >= session_close:
        return 1.0

    # Calculate progress
    open_minutes = session_open.hour * 60 + session_open.minute
    close_minutes = session_close.hour * 60 + session_close.minute
    current_minutes = current_time.hour * 60 + current_time.minute

    total_duration = close_minutes - open_minutes
    elapsed = current_minutes - open_minutes

    return elapsed / total_duration if total_duration > 0 else 0.0
