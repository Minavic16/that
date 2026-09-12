"""
A/B comparison framework for regime detection methods.

Compares:
- ADX-only regime detection
- TabFM regime detection (when available)
- Hybrid regime detection
- No regime detection (baseline)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np

from nestquant.research.shared.engines.regime_backtest_engine import RegimeBacktestEngine, RegimeBacktestConfig
from nestquant.research.shared.regime.base import RegimeDetector
from nestquant.research.shared.regime.adx_regime import ADXRegimeDetector
from nestquant.research.shared.regime.hybrid import HybridRegimeDetector
from nestquant.production.signals.base import BaseSignal
from nestquant.research.shared.backtest.metrics import calculate_metrics, BacktestMetrics


@dataclass
class ComparisonConfig:
    """Configuration for A/B comparison."""

    # Backtest parameters
    initial_balance: float = 10000.0
    risk_per_trade: float = 0.02
    max_open_trades: int = 1
    commission_per_lot: float = 6.0
    spread_pips: float = 1.0

    # Comparison settings
    methods: list[str] = field(default_factory=lambda: ["adx", "no_regime"])
    run_parallel: bool = False


@dataclass
class ComparisonResult:
    """Result of a single method comparison."""

    method: str
    metrics: BacktestMetrics
    regime_stats: Optional[dict] = None
    regime_summary: Optional[dict] = None
    trades: list = field(default_factory=list)


class ABComparison:
    """
    A/B comparison framework for regime detection methods.

    Runs backtests with different regime detection methods and compares
    performance metrics.
    """

    def __init__(
        self,
        signal: BaseSignal,
        config: Optional[ComparisonConfig] = None,
    ):
        self.signal = signal
        self.config = config or ComparisonConfig()
        self._results: list[ComparisonResult] = []

    def run_comparison(
        self,
        pair: str,
        df: pd.DataFrame,
        methods: Optional[list[str]] = None,
    ) -> list[ComparisonResult]:
        """
        Run A/B comparison on a single pair.

        Args:
            pair: Currency pair
            df: OHLCV DataFrame
            methods: List of methods to compare

        Returns:
            List of ComparisonResult for each method
        """
        methods = methods or self.config.methods
        self._results = []

        for method in methods:
            print(f"\nRunning {method} regime detection...")

            # Get regime detector
            detector = self._get_detector(method)

            # Create backtest config
            backtest_config = RegimeBacktestConfig(
                initial_balance=self.config.initial_balance,
                risk_per_trade=self.config.risk_per_trade,
                max_open_trades=self.config.max_open_trades,
                commission_per_lot=self.config.commission_per_lot,
                spread_pips=self.config.spread_pips,
                use_regime_sizing=(method != "no_regime"),
                regime_method=method,
            )

            # Create and run backtest
            engine = RegimeBacktestEngine(
                signal=self.signal,
                regime_detector=detector,
                config=backtest_config,
            )

            engine.start()

            # Process bars
            for i in range(len(df)):
                bar_df = df.iloc[:i+1]
                engine.on_bar(pair, bar_df)

            engine.stop()

            # Get results
            results = engine.get_results()
            metrics = calculate_metrics(
                [t.pnl for t in results.get("trades", [])],
                self.config.initial_balance,
            )

            comparison_result = ComparisonResult(
                method=method,
                metrics=metrics,
                regime_stats=results.get("regime_stats"),
                regime_summary=engine.get_regime_summary(),
                trades=results.get("trades", []),
            )

            self._results.append(comparison_result)

            # Print summary
            print(f"  Trades: {metrics.total_trades}")
            print(f"  Win Rate: {metrics.win_rate:.2%}")
            print(f"  Profit Factor: {metrics.profit_factor:.2f}")
            print(f"  Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
            print(f"  Max Drawdown: {metrics.max_drawdown_pct:.2f}%")

        return self._results

    def _get_detector(self, method: str) -> Optional[RegimeDetector]:
        """Get regime detector for specified method."""
        if method == "adx":
            return ADXRegimeDetector()
        elif method == "hybrid":
            return HybridRegimeDetector()
        elif method == "no_regime":
            return None
        else:
            raise ValueError(f"Unknown method: {method}")

    def get_comparison_table(self) -> pd.DataFrame:
        """
        Get comparison table of all methods.

        Returns:
            DataFrame with metrics for each method
        """
        if not self._results:
            return pd.DataFrame()

        rows = []
        for result in self._results:
            rows.append({
                "method": result.method,
                "total_trades": result.metrics.total_trades,
                "win_rate": result.metrics.win_rate,
                "profit_factor": result.metrics.profit_factor,
                "total_pnl": result.metrics.total_pnl,
                "max_drawdown_pct": result.metrics.max_drawdown_pct,
                "sharpe_ratio": result.metrics.sharpe_ratio,
                "sortino_ratio": result.metrics.sortino_ratio,
                "expectancy": result.metrics.expectancy,
            })

        return pd.DataFrame(rows)

    def get_regime_analysis(self) -> dict:
        """
        Get regime analysis across all methods.

        Returns:
            Dict with regime analysis for each method
        """
        analysis = {}

        for result in self._results:
            method_analysis = {
                "total_bars": 0,
                "regime_distribution": {},
                "regime_performance": {},
            }

            if result.regime_summary:
                method_analysis["total_bars"] = result.regime_summary.get("total_bars", 0)
                method_analysis["regime_distribution"] = result.regime_summary.get(
                    "regime_percentages", {}
                )

            if result.regime_stats:
                method_analysis["regime_performance"] = result.regime_stats

            analysis[result.method] = method_analysis

        return analysis

    def print_comparison(self) -> None:
        """Print formatted comparison table."""
        df = self.get_comparison_table()

        if df.empty:
            print("No comparison results available")
            return

        print("\n" + "=" * 80)
        print("A/B Comparison Results")
        print("=" * 80)

        # Format table
        print("\n{:<12} {:>10} {:>10} {:>10} {:>12} {:>10} {:>10}".format(
            "Method", "Trades", "Win Rate", "PF", "Total PnL", "Max DD%", "Sharpe"
        ))
        print("-" * 80)

        for _, row in df.iterrows():
            print("{:<12} {:>10} {:>10.2%} {:>10.2f} {:>12.2f} {:>10.2f} {:>10.2f}".format(
                row["method"],
                row["total_trades"],
                row["win_rate"],
                row["profit_factor"],
                row["total_pnl"],
                row["max_drawdown_pct"],
                row["sharpe_ratio"],
            ))

        print("-" * 80)

        # Find best method
        best_idx = df["sharpe_ratio"].idxmax()
        best_method = df.loc[best_idx, "method"]
        print(f"\nBest method by Sharpe: {best_method}")

    def print_regime_analysis(self) -> None:
        """Print regime analysis for each method."""
        analysis = self.get_regime_analysis()

        print("\n" + "=" * 80)
        print("Regime Analysis")
        print("=" * 80)

        for method, data in analysis.items():
            print(f"\n{method}:")
            print(f"  Total bars analyzed: {data['total_bars']}")

            if data["regime_distribution"]:
                print("  Regime distribution:")
                for regime, pct in sorted(data["regime_distribution"].items()):
                    print(f"    {regime}: {pct:.1f}%")

            if data["regime_performance"]:
                print("  Performance by regime:")
                for regime, stats in data["regime_performance"].items():
                    wr = stats.get("win_rate", 0)
                    pnl = stats.get("total_pnl", 0)
                    print(f"    {regime}: WR={wr:.2%}, PnL={pnl:.2f}")
