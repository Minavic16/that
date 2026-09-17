"""
R2.1 Horizon Configuration
==========================

Canonical horizon definitions for R2.1.
Horizons are specified in bars at 4H frequency.

Per §F1 of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

from __future__ import annotations

# Canonical horizons: bars at 4H frequency
HORIZONS: list[int] = [1, 3, 6, 12]

# Bar-to-hours conversion
HOURS_PER_BAR: int = 4

# Expected hours for each horizon
HORIZON_HOURS: dict[int, int] = {h: h * HOURS_PER_BAR for h in HORIZONS}


def validate_horizons(horizons: list[int]) -> bool:
    """Validate that horizons match the canonical set.

    Returns True if horizons == [1, 3, 6, 12].
    """
    return horizons == HORIZONS


def horizon_to_hours(horizon: int) -> int:
    """Convert horizon in bars to hours."""
    return horizon * HOURS_PER_BAR
