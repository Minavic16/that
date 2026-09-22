"""NestQuant Research OS — Canonical Data Layer.

Shared OHLCV market-data primitives for all research programs:
canonical types, schema, validation, loading, and feature boundaries.

This package MUST NOT import from `production/` or from
R2.1-specific `apparatus/` code. The dependency direction is:
research workloads consume the Research OS, never the reverse.
"""

from nestquant.research.shared.data.loader import DataLoader
from nestquant.research.shared.data.schema import (
    FOUR_H_BAR_HOURS,
    FOUR_H_BAR_INTERVAL_HOURS,
    OHLCV_COLUMNS,
    OHLCV_COLUMN_TYPES,
    OHLCV_REQUIRED_COLUMNS,
)
from nestquant.research.shared.data.types import MarketBar, OHLCVFrame, Timestamp
from nestquant.research.shared.data.validate import (
    ValidationResult,
    validate_4h_alignment,
    validate_duplicates,
    validate_gaps,
    validate_ohlcv,
    validate_prices,
    validate_schema,
    validate_timestamps,
    validation_passed,
)

__all__ = [
    "DataLoader",
    "FOUR_H_BAR_HOURS",
    "FOUR_H_BAR_INTERVAL_HOURS",
    "MarketBar",
    "OHLCVFrame",
    "OHLCV_COLUMNS",
    "OHLCV_COLUMN_TYPES",
    "OHLCV_REQUIRED_COLUMNS",
    "Timestamp",
    "ValidationResult",
    "validate_4h_alignment",
    "validate_duplicates",
    "validate_gaps",
    "validate_ohlcv",
    "validate_prices",
    "validate_schema",
    "validate_timestamps",
    "validation_passed",
]
