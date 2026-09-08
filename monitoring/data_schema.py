"""
NestQuant S8.6.2 — Data Schema for Percentile Calibration
==========================================================

Defines the data structures needed for future monitoring calibration.

When live data begins flowing, these schemas define what must be
collected and stored for percentile-based threshold calibration.

COLLECTION LAYERS:
    Layer 1 (Observation): Raw facts per trade/event
    Layer 2 (Aggregation): Rolling windows and distributions
    Layer 3 (Storage): JSONL for persistence

DESIGN PRINCIPLE:
    Every metric must have an identifiable source dataset.
    No metric appears in monitoring without a collection path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
# Layer 1: Raw Observation Schema (per trade)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class TradeObservation:
    """
    A single trade observation. Layer 1 of the monitoring architecture.

    This is the atomic unit of monitoring data.
    Every field is optional to allow partial collection.
    """
    # Identity
    trade_id: str = ""
    timestamp: str = ""
    pair: str = ""
    direction: str = ""

    # Entry
    entry_price: float = 0.0
    entry_time: str = ""
    requested_price: float = 0.0

    # Exit
    exit_price: float = 0.0
    exit_time: str = ""
    exit_reason: str = ""  # "tp", "sl", "breakeven", "timeout", "manual"

    # PnL
    pnl_pips: float = 0.0
    pnl_r: float = 0.0  # R-multiple (strategy-native)
    pnl_dollars: float = 0.0  # Account-level

    # Costs
    spread_pips: float = 0.0
    slippage_pips: float = 0.0
    commission_dollars: float = 0.0

    # Execution
    fill_latency_ms: float = 0.0
    fill_price: float = 0.0

    # Context
    equity_at_entry: float = 0.0
    equity_at_exit: float = 0.0
    peak_equity: float = 0.0
    drawdown_at_entry_pct: float = 0.0

    # Regime
    regime_at_entry: str = ""  # "trending", "ranging", "volatile"
    session_at_entry: str = ""  # "london", "newyork", "asian"

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v != "" and v != 0.0}


# ─────────────────────────────────────────────────────────────────────
# Layer 1: Equity Snapshot Schema (periodic)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class EquitySnapshot:
    """
    Periodic equity snapshot. Layer 1 of the monitoring architecture.

    Collected at fixed intervals (e.g., every hour) regardless of trading activity.
    """
    timestamp: str = ""
    balance: float = 0.0
    equity: float = 0.0
    floating_pnl: float = 0.0
    realized_pnl_today: float = 0.0
    open_positions: int = 0
    total_exposure_lots: float = 0.0
    peak_equity: float = 0.0
    drawdown_pct: float = 0.0
    drawdown_r: float = 0.0  # DD in R-units

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v != 0.0}


# ─────────────────────────────────────────────────────────────────────
# Layer 1: Execution Quality Schema (per fill)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ExecutionQuality:
    """
    Execution quality observation. Layer 1.

    Collected for every order fill.
    """
    timestamp: str = ""
    pair: str = ""
    order_type: str = ""  # "market", "limit", "stop"
    requested_price: float = 0.0
    fill_price: float = 0.0
    slippage_pips: float = 0.0
    spread_pips: float = 0.0
    latency_ms: float = 0.0
    fill_status: str = ""  # "filled", "partial", "rejected", "cancelled"

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v != "" and v != 0.0}


# ─────────────────────────────────────────────────────────────────────
# Layer 2: Rolling Window Schema
# ─────────────────────────────────────────────────────────────────────

@dataclass
class RollingWindowStats:
    """
    Aggregated statistics for a rolling window. Layer 2.

    Computed from Layer 1 observations.
    """
    window_size: int = 0
    metric_name: str = ""

    # Core statistics
    mean: float = 0.0
    std: float = 0.0
    variance: float = 0.0
    min: float = 0.0
    max: float = 0.0

    # Percentiles (computed when sample_size >= min_samples)
    p5: float = 0.0
    p10: float = 0.0
    p25: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0

    # Sample info
    sample_size: int = 0
    min_samples_for_percentiles: int = 30
    is_sufficient: bool = False

    # Classification
    current_value: float = 0.0
    percentile_of_current: float = 0.0
    z_score_of_current: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ─────────────────────────────────────────────────────────────────────
# Layer 3: JSONL Storage Schema
# ─────────────────────────────────────────────────────────────────────

TRADE_OBSERVATION_SCHEMA = {
    "type": "object",
    "properties": {
        "trade_id": {"type": "string"},
        "timestamp": {"type": "string", "format": "date-time"},
        "pair": {"type": "string"},
        "direction": {"type": "string", "enum": ["BUY", "SELL"]},
        "entry_price": {"type": "number"},
        "exit_price": {"type": "number"},
        "pnl_pips": {"type": "number"},
        "pnl_r": {"type": "number"},
        "pnl_dollars": {"type": "number"},
        "spread_pips": {"type": "number"},
        "slippage_pips": {"type": "number"},
        "fill_latency_ms": {"type": "number"},
        "exit_reason": {"type": "string"},
    },
    "required": ["trade_id", "timestamp", "pair", "pnl_pips"],
}

EQUITY_SNAPSHOT_SCHEMA = {
    "type": "object",
    "properties": {
        "timestamp": {"type": "string", "format": "date-time"},
        "balance": {"type": "number"},
        "equity": {"type": "number"},
        "floating_pnl": {"type": "number"},
        "open_positions": {"type": "integer"},
        "drawdown_pct": {"type": "number"},
        "drawdown_r": {"type": "number"},
    },
    "required": ["timestamp", "balance", "equity"],
}

EXECUTION_QUALITY_SCHEMA = {
    "type": "object",
    "properties": {
        "timestamp": {"type": "string", "format": "date-time"},
        "pair": {"type": "string"},
        "order_type": {"type": "string"},
        "requested_price": {"type": "number"},
        "fill_price": {"type": "number"},
        "slippage_pips": {"type": "number"},
        "spread_pips": {"type": "number"},
        "latency_ms": {"type": "number"},
        "fill_status": {"type": "string"},
    },
    "required": ["timestamp", "pair", "fill_status"],
}


# ─────────────────────────────────────────────────────────────────────
# Minimum Sample Sizes for Calibration
# ─────────────────────────────────────────────────────────────────────

MIN_SAMPLES = {
    "win_rate": 200,
    "ev": 200,
    "slippage": 200,
    "spread": 200,
    "latency": 500,
    "drawdown_depth": 30,
    "drawdown_duration": 30,
    "loss_streak": 100,
    "profit_factor": 200,
}

PROVISIONAL_THRESHOLDS = {
    "note": (
        "These thresholds are PROVISIONAL and based on simulated data. "
        "They must be replaced with live-calibrated thresholds after "
        "sufficient data is collected."
    ),
    "win_rate_20t": {
        "monitoring": 0.30,
        "warning": 0.25,
        "investigation": 0.20,
        "halt": 0.15,
        "source": "S5.5 simulated (NOT trade-level)",
        "confidence": "LOW",
    },
    "profit_factor": {
        "threshold": 1.0,
        "window": 20,
        "source": "S6A lifetime PF=2.01",
        "confidence": "MEDIUM",
    },
    "drawdown_r": {
        "soft_warning_r": 10.0,
        "hard_halt_r": 20.0,
        "source": "S6A max DD=19.61R",
        "confidence": "MEDIUM",
    },
}
