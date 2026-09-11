"""Z-Score Research Engine — Data Contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class MarketData:
    """Raw ingested market data for a single pair."""
    pair: str
    timestamps: pd.DatetimeIndex
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    @property
    def n(self) -> int:
        return len(self.timestamps)


@dataclass
class InstrumentMetadata:
    """Instrument-specific properties."""
    pair: str
    pip_size: float
    pip_value_per_lot: float
    typical_spread_pips: float
    contract_size: int = 100_000


@dataclass
class ValidationReport:
    """Result of data validation checks."""
    pair: str
    total_bars: int
    duplicate_timestamps: int
    missing_bars: int
    gap_timestamps: list[pd.Timestamp]
    ohlc_violations: int
    nan_counts: dict[str, int]
    is_valid: bool


@dataclass
class ValidatedMarketData:
    """Market data with validation report attached."""
    market_data: MarketData
    validation: ValidationReport


@dataclass
class NormalizedMarketData:
    """Aligned market data with indicators, consumed by all downstream stages."""
    pair: str
    metadata: InstrumentMetadata
    timestamps: pd.DatetimeIndex
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    ema_200: np.ndarray
    ema_50: np.ndarray
    daily_open: np.ndarray
    daily_close: np.ndarray
    daily_direction: np.ndarray  # bool: prev day close > open (causal)
    pip: float
    pv: float
    spread: float
    daily: pd.DataFrame

    @property
    def n(self) -> int:
        return len(self.timestamps)


@dataclass
class FeatureSet:
    """Computed features for each bar."""
    pair: str
    timestamps: pd.DatetimeIndex
    atr_pct: np.ndarray
    rv_20: np.ndarray
    dist_ema200: np.ndarray
    dist_ema50: np.ndarray

    @property
    def n(self) -> int:
        return len(self.timestamps)


@dataclass
class RegimeState:
    """Regime classification at a single bar."""
    pair: str
    timestamp: pd.Timestamp
    trend: str  # "near_ema200" | "weak_trend" | "strong_trend"
    volatility: str  # "low_vol" | "mid_vol" | "high_vol" | "extreme_vol" | "unknown"
    atr_percentile: float
    is_causal: bool


@dataclass
class ZScoreObservation:
    """Z-score value at a single bar."""
    pair: str
    timestamp: pd.Timestamp
    close: float
    z_score: float
    rolling_mean: float
    rolling_std: float
    lookback: int
    is_causal: bool


@dataclass
class Signal:
    """Trading signal at a single bar."""
    pair: str
    timestamp: pd.Timestamp
    direction: int  # 1 = long, -1 = short
    strength: float
    entry_price: float
    sl_price: float
    tp_price: float
    regime: RegimeState | None = None
    z_score: ZScoreObservation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CostModel:
    """Execution cost configuration."""
    spread_pips: float
    commission_per_lot: float
    slippage_pips: float
    execution_delay_bars: int = 0


@dataclass
class CostBreakdown:
    """Cost components for a single trade."""
    spread_cost: float
    commission_cost: float
    slippage_cost: float
    total_cost: float


@dataclass
class SimulatedOrder:
    """Order after cost application."""
    pair: str
    timestamp: pd.Timestamp
    direction: int
    entry_price: float
    sl_price: float
    tp_price: float
    lot_size: float
    cost_model: CostModel
    costs: CostBreakdown


@dataclass
class Trade:
    """Completed trade with full accounting."""
    pair: str
    direction: int
    entry_price: float
    exit_price: float
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    sl_price: float
    tp_price: float
    lot_size: float
    gross_pnl: float
    costs: CostBreakdown
    pnl: float
    exit_reason: str  # "SL" | "TP" | "SC" | "MH" | "DL"
    holding_bars: int
    is_win: bool


@dataclass
class PortfolioState:
    """Portfolio accounting results."""
    initial_balance: float
    balance: float
    equity_curve: np.ndarray
    trades: list[Trade]
    peak_balance: float
    max_drawdown_pct: float
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentConfig:
    """Full experiment configuration for reproducibility."""
    experiment_id: str
    git_commit: str
    timestamp: str
    dataset_version: str
    data_source: str
    instruments: list[str]
    timeframe: str
    date_range: tuple[str, str]
    timezone: str
    spread_pips: dict[str, float]
    commission_per_lot: float
    slippage_pips: float
    execution_delay_bars: int
    lookback_window: int
    z_score_threshold: float
    max_concurrent: int
    risk_per_trade: float
    leverage: float
    max_hold_bars: int
    sessions: dict[str, tuple[int, int]]
    vol_min_history: int
    trend_thresholds: tuple[float, float]
    random_seed: int | None = None
