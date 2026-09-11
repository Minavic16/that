"""
Regime-aware backtest engine.

Integrates regime detection with the backtest engine to:
- Use regime predictions for position sizing
- Select strategies based on regime
- Apply regime-specific parameters
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from nestquant.engines.backtest_engine import BacktestEngine, BacktestConfig, Trade
from nestquant.regime.base import RegimeDetector, RegimePrediction
from nestquant.regime.labels import RegimeLabel, REGIME_PARAMS
from nestquant.regime.adx_regime import ADXRegimeDetector
from nestquant.signals.base import BaseSignal, SignalResult
from nestquant.indicators.session import is_active_session


@dataclass
class RegimeBacktestConfig(BacktestConfig):
    """Extended config for regime-aware backtesting."""

    # Regime settings
    use_regime_sizing: bool = True
    regime_method: str = "adx"  # "adx", "tabfm", "hybrid"

    # Regime-specific risk adjustments
    regime_risk_mult: float = 1.0  # Additional multiplier on top of regime params

    # Strategy selection
    use_regime_strategy_selection: bool = False


@dataclass
class RegimeTrade(Trade):
    """Extended trade with regime information."""

    regime_at_entry: Optional[str] = None
    regime_confidence: float = 0.0
    regime_risk_mult: float = 1.0
    regime_params: dict = field(default_factory=dict)


class RegimeBacktestEngine(BacktestEngine):
    """
    Backtest engine with regime-aware position sizing and strategy selection.

    Extends the base BacktestEngine to:
    1. Detect market regime before each trade
    2. Adjust position size based on regime parameters
    3. Select appropriate strategy for current regime
    4. Log regime information with each trade
    """

    def __init__(
        self,
        signal: BaseSignal,
        regime_detector: Optional[RegimeDetector] = None,
        config: Optional[RegimeBacktestConfig] = None,
    ):
        super().__init__(signal, config)
        self.config = config or RegimeBacktestConfig()
        self._regime_detector = regime_detector or ADXRegimeDetector()
        self._current_regime: Optional[RegimePrediction] = None
        self._regime_history: list[dict] = []

    def on_bar(self, pair: str, df: pd.DataFrame) -> None:
        """
        Process new bar data with regime detection.

        Args:
            pair: Currency pair
            df: OHLCV DataFrame
        """
        if not self._state.running:
            return

        # Check session filter
        if not is_active_session(df.index[-1]):
            return

        # Detect regime
        self._current_regime = self._regime_detector.predict(pair, df)
        self._regime_history.append({
            "timestamp": df.index[-1],
            "regime": self._current_regime.regime.value,
            "confidence": self._current_regime.confidence,
        })

        # Check if regime allows trading
        if not self._can_trade_in_regime():
            # Still check exits for existing trades
            self._check_exits(pair, df)
            self._update_state()
            return

        # Close existing trades (check SL/TP)
        self._check_exits(pair, df)

        # Generate new signal
        signal = self.signal.generate(df, pair)

        if signal.is_active and len(self._open_trades) < self.config.max_open_trades:
            self._open_trade(signal, df.index[-1])

        # Update state
        self._update_state()

    def _can_trade_in_regime(self) -> bool:
        """Check if trading is allowed in current regime."""
        if self._current_regime is None:
            return True

        regime = self._current_regime.regime

        # Don't trade in high volatility or news-driven regimes
        if regime in [RegimeLabel.HIGH_VOL, RegimeLabel.NEWS_DRIVEN]:
            return False

        # Check regime parameters
        params = REGIME_PARAMS.get(regime, {})
        risk_mult = params.get("risk_mult", 1.0)

        # If risk multiplier is 0, don't trade
        if risk_mult == 0:
            return False

        return True

    def _get_regime_risk_multiplier(self) -> float:
        """Get risk multiplier based on current regime."""
        if self._current_regime is None or not self.config.use_regime_sizing:
            return 1.0

        params = self._current_regime.params
        base_mult = params.get("risk_mult", 1.0)

        # Apply additional regime risk multiplier
        return base_mult * self.config.regime_risk_mult

    def _get_regime_sl_multiplier(self) -> float:
        """Get stop loss multiplier based on current regime."""
        if self._current_regime is None:
            return 1.0

        params = self._current_regime.params
        return params.get("sl_mult", 1.0)

    def _get_regime_tp_multiplier(self) -> float:
        """Get take profit multiplier based on current regime."""
        if self._current_regime is None:
            return 1.0

        params = self._current_regime.params
        return params.get("tp_mult", 1.0)

    def _open_trade(self, signal: SignalResult, timestamp: pd.Timestamp) -> None:
        """Open a new trade with regime-adjusted parameters."""
        # Apply spread and slippage
        spread_cost = self.config.spread_pips * 0.0001
        slippage_cost = self.config.slippage_pips * 0.0001

        if signal.direction == "BUY":
            entry_price = signal.entry_price + spread_cost / 2 + slippage_cost
        else:
            entry_price = signal.entry_price - spread_cost / 2 - slippage_cost

        # Get regime-adjusted multipliers
        risk_mult = self._get_regime_risk_multiplier()
        sl_mult = self._get_regime_sl_multiplier()
        tp_mult = self._get_regime_tp_multiplier()

        # Calculate SL and TP with regime adjustments
        base_sl_distance = abs(signal.entry_price - signal.sl_price)
        sl_distance = base_sl_distance * sl_mult

        if signal.direction == "BUY":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + (base_sl_distance * signal.metadata.get("rrr", 2.0) * tp_mult)
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - (base_sl_distance * signal.metadata.get("rrr", 2.0) * tp_mult)

        # Calculate position size with regime adjustment
        risk_amount = self._balance * self.config.risk_per_trade * risk_mult
        sl_distance_price = abs(entry_price - sl_price)

        if sl_distance_price <= 0:
            return

        lot_size = risk_amount / (sl_distance_price * 100000)
        lot_size = max(0.01, round(lot_size, 2))

        trade = RegimeTrade(
            pair=signal.pair,
            direction=signal.direction,
            entry_price=entry_price,
            entry_time=timestamp,
            sl_price=sl_price,
            tp_price=tp_price,
            lot_size=lot_size,
            regime_at_entry=self._current_regime.regime.value if self._current_regime else None,
            regime_confidence=self._current_regime.confidence if self._current_regime else 0.0,
            regime_risk_mult=risk_mult,
            regime_params=self._current_regime.params if self._current_regime else {},
        )

        self._open_trades.append(trade)
        self._trades.append(trade)

    def get_results(self) -> dict:
        """Get backtest results with regime analysis."""
        results = super().get_results()

        # Add regime analysis
        regime_trades = [t for t in self._trades if isinstance(t, RegimeTrade)]

        if regime_trades:
            # Group by regime
            regime_stats = {}
            for trade in regime_trades:
                regime = trade.regime_at_entry or "unknown"
                if regime not in regime_stats:
                    regime_stats[regime] = {
                        "count": 0,
                        "wins": 0,
                        "losses": 0,
                        "total_pnl": 0.0,
                    }
                regime_stats[regime]["count"] += 1
                if trade.pnl > 0:
                    regime_stats[regime]["wins"] += 1
                else:
                    regime_stats[regime]["losses"] += 1
                regime_stats[regime]["total_pnl"] += trade.pnl

            # Calculate win rates
            for regime, stats in regime_stats.items():
                stats["win_rate"] = stats["wins"] / stats["count"] if stats["count"] > 0 else 0.0
                stats["avg_pnl"] = stats["total_pnl"] / stats["count"] if stats["count"] > 0 else 0.0

            results["regime_stats"] = regime_stats
            results["regime_history"] = self._regime_history

        return results

    def get_regime_summary(self) -> dict:
        """Get summary of regime detection during backtest."""
        if not self._regime_history:
            return {"error": "No regime history"}

        regimes = [r["regime"] for r in self._regime_history]
        regime_counts = pd.Series(regimes).value_counts()

        return {
            "total_bars": len(self._regime_history),
            "regime_distribution": regime_counts.to_dict(),
            "regime_percentages": (regime_counts / len(regimes) * 100).to_dict(),
        }
