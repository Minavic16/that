"""
Regime label definitions and parameter mappings.
"""

from __future__ import annotations

from enum import Enum


class RegimeLabel(Enum):
    """
    Market regime labels for classification.

    Each label maps to specific strategy behaviors:
    - TRENDING:         Use trend-following, widen stops, trail
    - RANGING:          Use mean-reversion, tighten TP, reduce size
    - BREAKOUT:         Enter on breakout, wider stops, momentum sizing
    - HIGH_VOL:         Reduce size, widen stops, avoid new entries
    - LOW_VOL:          Normal sizing, tighter stops, expect compression
    - MEAN_REVERSION:   Fade extremes, RSI/Bollinger-based entries
    - NEWS_DRIVEN:      Pause entries, manage existing positions carefully
    """

    TRENDING = "trending"
    RANGING = "ranging"
    BREAKOUT = "breakout"
    HIGH_VOL = "high_vol"
    LOW_VOL = "low_vol"
    MEAN_REVERSION = "mean_reversion"
    NEWS_DRIVEN = "news_driven"
    UNKNOWN = "unknown"


# Strategy parameter multipliers by regime
REGIME_PARAMS: dict[RegimeLabel, dict] = {
    RegimeLabel.TRENDING: {
        "risk_mult": 1.2,
        "rr_mult": 1.0,
        "sl_mult": 1.5,       # Wider stops
        "tp_mult": 1.0,
        "max_hold_mult": 1.5,
        "trailing_enabled": True,
        "strategy_preference": ["breakout", "trend_following"],
    },
    RegimeLabel.RANGING: {
        "risk_mult": 0.7,
        "rr_mult": 0.8,
        "sl_mult": 0.8,       # Tighter stops
        "tp_mult": 0.7,       # Tighter TP
        "max_hold_mult": 0.5,
        "trailing_enabled": False,
        "strategy_preference": ["mean_reversion"],
    },
    RegimeLabel.BREAKOUT: {
        "risk_mult": 1.0,
        "rr_mult": 1.2,
        "sl_mult": 2.0,       # Wide stops for breakout
        "tp_mult": 1.5,
        "max_hold_mult": 2.0,
        "trailing_enabled": True,
        "strategy_preference": ["breakout"],
    },
    RegimeLabel.HIGH_VOL: {
        "risk_mult": 0.5,     # Half risk
        "rr_mult": 0.8,
        "sl_mult": 2.0,       # Very wide stops
        "tp_mult": 0.8,
        "max_hold_mult": 0.5,
        "trailing_enabled": True,
        "strategy_preference": [],  # Pause new entries
    },
    RegimeLabel.LOW_VOL: {
        "risk_mult": 1.0,
        "rr_mult": 1.0,
        "sl_mult": 0.7,       # Tight stops (expect expansion)
        "tp_mult": 0.8,
        "max_hold_mult": 1.0,
        "trailing_enabled": False,
        "strategy_preference": ["breakout"],  # Trade the breakout
    },
    RegimeLabel.MEAN_REVERSION: {
        "risk_mult": 0.8,
        "rr_mult": 0.9,
        "sl_mult": 0.9,
        "tp_mult": 0.8,
        "max_hold_mult": 0.3, # Short holds
        "trailing_enabled": False,
        "strategy_preference": ["mean_reversion"],
    },
    RegimeLabel.NEWS_DRIVEN: {
        "risk_mult": 0.0,     # No new entries
        "rr_mult": 1.0,
        "sl_mult": 3.0,       # Very wide for existing
        "tp_mult": 1.0,
        "max_hold_mult": 0.2,
        "trailing_enabled": True,
        "strategy_preference": [],
    },
    RegimeLabel.UNKNOWN: {
        "risk_mult": 0.5,
        "rr_mult": 1.0,
        "sl_mult": 1.0,
        "tp_mult": 1.0,
        "max_hold_mult": 1.0,
        "trailing_enabled": False,
        "strategy_preference": [],
    },
}
