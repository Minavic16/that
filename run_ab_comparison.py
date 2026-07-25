"""
Integrated A/B comparison runner for regime detection methods.

Compares ADX vs no_regime detection on synthetic data.
"""

from __future__ import annotations

import sys
import os

# Add root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

from nestquant.signals.breakout import BreakoutSignal
from nestquant.signals.structured_entry import StructuredEntrySignal
from nestquant.backtest.comparison import ABComparison, ComparisonConfig
from nestquant.backtest.metrics import calculate_metrics
from nestquant.regime.labels import RegimeLabel, REGIME_PARAMS


def generate_backtest_data(n_bars: int = 5000) -> pd.DataFrame:
    """
    Generate synthetic market data for backtesting.

    Creates data with varying regimes to test regime detection.
    """
    np.random.seed(42)

    price = 1.1000
    prices = [price]

    for i in range(n_bars - 1):
        cycle = i % 500

        if cycle < 100:
            drift = 0.0002
            vol = 0.0006
        elif cycle < 200:
            drift = -0.0002
            vol = 0.0006
        elif cycle < 300:
            drift = 0.0
            vol = 0.0003
        elif cycle < 400:
            drift = np.random.choice([-0.0001, 0.0001])
            vol = 0.0010
        else:
            drift = 0.0
            vol = 0.0004

        ret = drift + vol * np.random.randn()
        price = price * (1 + ret)
        prices.append(price)

    prices = np.array(prices)
    opens = prices * (1 + np.random.randn(n_bars) * 0.00005)
    highs = np.maximum(prices, opens) * (1 + np.abs(np.random.randn(n_bars)) * 0.0002)
    lows = np.minimum(prices, opens) * (1 - np.abs(np.random.randn(n_bars)) * 0.0002)
    volumes = np.random.randint(1000, 10000, n_bars).astype(float)

    dates = pd.date_range("2020-01-01", periods=n_bars, freq="5min")

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": prices,
        "volume": volumes,
    }, index=dates)


def run_manual_comparison(pair: str, df: pd.DataFrame) -> None:
    """
    Run manual A/B comparison without using the comparison framework.
    This shows the detailed logic.
    """
    print("=" * 80)
    print(f"Manual A/B Comparison for {pair}")
    print("=" * 80)

    from nestquant.engines.backtest_engine import BacktestEngine, BacktestConfig
    from nestquant.regime.adx_regime import ADXRegimeDetector
    from nestquant.regime.labels import REGIME_PARAMS

    signal = BreakoutSignal(lookback=5)

    # Method 1: No regime detection (baseline)
    print("\n[1] Running baseline (no regime detection)...")
    config1 = BacktestConfig(
        initial_balance=10000,
        risk_per_trade=0.02,
        max_open_trades=1,
    )
    engine1 = BacktestEngine(signal, config1)
    engine1.start()

    for i in range(min(2000, len(df))):
        bar_df = df.iloc[:i+1]
        engine1.on_bar(pair, bar_df)

    engine1.stop()
    results1 = engine1.get_results()
    metrics1 = calculate_metrics([t.pnl for t in results1["trades"]], 10000)

    print(f"  Trades: {metrics1.total_trades}")
    print(f"  Win Rate: {metrics1.win_rate:.2%}")
    print(f"  Profit Factor: {metrics1.profit_factor:.2f}")
    print(f"  Sharpe Ratio: {metrics1.sharpe_ratio:.2f}")
    print(f"  Max Drawdown: {metrics1.max_drawdown_pct:.2f}%")

    # Method 2: With ADX regime detection
    print("\n[2] Running with ADX regime detection...")
    from nestquant.engines.regime_backtest_engine import RegimeBacktestEngine, RegimeBacktestConfig

    config2 = RegimeBacktestConfig(
        initial_balance=10000,
        risk_per_trade=0.02,
        max_open_trades=1,
        use_regime_sizing=True,
    )
    engine2 = RegimeBacktestEngine(signal, ADXRegimeDetector(), config2)
    engine2.start()

    for i in range(min(2000, len(df))):
        bar_df = df.iloc[:i+1]
        engine2.on_bar(pair, bar_df)

    engine2.stop()
    results2 = engine2.get_results()
    metrics2 = calculate_metrics([t.pnl for t in results2["trades"]], 10000)

    print(f"  Trades: {metrics2.total_trades}")
    print(f"  Win Rate: {metrics2.win_rate:.2%}")
    print(f"  Profit Factor: {metrics2.profit_factor:.2f}")
    print(f"  Sharpe Ratio: {metrics2.sharpe_ratio:.2f}")
    print(f"  Max Drawdown: {metrics2.max_drawdown_pct:.2f}%")

    # Compare
    print("\n" + "=" * 80)
    print("Comparison Summary")
    print("=" * 80)

    print("\n{:<25} {:>15} {:>15}".format("Metric", "No Regime", "ADX Regime"))
    print("-" * 55)
    print("{:<25} {:>15} {:>15}".format("Trades", metrics1.total_trades, metrics2.total_trades))
    print("{:<25} {:>15.2%} {:>15.2%}".format("Win Rate", metrics1.win_rate, metrics2.win_rate))
    print("{:<25} {:>15.2f} {:>15.2f}".format("Profit Factor", metrics1.profit_factor, metrics2.profit_factor))
    print("{:<25} {:>15.2f} {:>15.2f}".format("Sharpe Ratio", metrics1.sharpe_ratio, metrics2.sharpe_ratio))
    print("{:<25} {:>15.2f} {:>15.2f}".format("Max Drawdown%", metrics1.max_drawdown_pct, metrics2.max_drawdown_pct))
    print("{:<25} {:>15.2f} {:>15.2f}".format("Total PnL", metrics1.total_pnl, metrics2.total_pnl))

    # Determine winner
    if metrics2.sharpe_ratio > metrics1.sharpe_ratio:
        print("\n✓ ADX regime detection outperforms baseline")
    elif metrics2.sharpe_ratio < metrics1.sharpe_ratio:
        print("\n✗ Baseline outperforms ADX regime detection")
    else:
        print("\n~ Both methods perform similarly")

    # Show regime distribution
    regime_summary = engine2.get_regime_summary()
    if "regime_percentages" in regime_summary:
        print("\nRegime Distribution:")
        for regime, pct in sorted(regime_summary["regime_percentages"].items()):
            print(f"  {regime}: {pct:.1f}%")


def main():
    """Run the full A/B comparison."""
    print("=" * 80)
    print("NestQuant Regime Detection A/B Comparison")
    print("=" * 80)

    # Generate data
    print("\nGenerating synthetic market data...")
    df = generate_backtest_data(5000)
    print(f"Generated {len(df)} bars")

    # Run manual comparison
    run_manual_comparison("EUR/USD", df)

    # Run framework comparison
    print("\n\n" + "=" * 80)
    print("Running Framework Comparison")
    print("=" * 80)

    signal = BreakoutSignal(lookback=5)
    config = ComparisonConfig(
        initial_balance=10000,
        risk_per_trade=0.02,
        methods=["adx", "no_regime"],
    )

    comparison = ABComparison(signal, config)
    results = comparison.run_comparison("EUR/USD", df)

    comparison.print_comparison()
    comparison.print_regime_analysis()

    # Show regime parameters
    print("\n" + "=" * 80)
    print("Regime Parameters Used")
    print("=" * 80)

    for regime in RegimeLabel:
        params = REGIME_PARAMS[regime]
        print(f"\n{regime.value}:")
        print(f"  Risk multiplier: {params['risk_mult']}")
        print(f"  SL multiplier: {params['sl_mult']}")
        print(f"  TP multiplier: {params['tp_mult']}")
        print(f"  Strategy preference: {params['strategy_preference']}")


if __name__ == "__main__":
    main()
