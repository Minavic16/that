"""
Pip size and price conversion utilities.
"""

from __future__ import annotations


def pip_size(pair: str) -> float:
    """Return pip size for a pair (0.01 for JPY pairs, 0.0001 otherwise)."""
    return 0.01 if "JPY" in pair.upper() else 0.0001


def price_to_pips(price_diff: float, pair: str) -> float:
    """Convert a raw price difference to pips."""
    return abs(price_diff) / pip_size(pair)


def pips_to_price(pips: float, pair: str) -> float:
    """Convert pips to raw price units."""
    return pips * pip_size(pair)
