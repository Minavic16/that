"""
Comprehensive test for the regime detection system.
"""

import sys
import os

# Add root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

from nestquant.regime.labels import RegimeLabel, REGIME_PARAMS
from nestquant.regime.adx_regime import ADXRegimeDetector
from nestquant.regime.hybrid import HybridRegimeDetector
from nestquant.regime.base import RegimePrediction


def generate_test_data(n_bars: int = 2000) -> pd.DataFrame:
    """Generate test OHLCV data."""
    np.random.seed(123)

    price = 1.1000
    prices = [price]

    for i in range(n_bars - 1):
        # Simple random walk
        ret = 0.0001 * np.random.randn()
        price = price * (1 + ret)
        prices.append(price)

    prices = np.array(prices)
    opens = prices * (1 + np.random.randn(n_bars) * 0.0001)
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


def test_regime_labels():
    """Test regime label definitions."""
    print("Testing regime labels...")

    # Check all expected regimes exist
    expected_regimes = [
        "TRENDING", "RANGING", "BREAKOUT", "HIGH_VOL",
        "LOW_VOL", "MEAN_REVERSION", "NEWS_DRIVEN", "UNKNOWN"
    ]
    for regime_name in expected_regimes:
        assert hasattr(RegimeLabel, regime_name), f"Missing regime: {regime_name}"

    # Check all regimes have params
    for regime in RegimeLabel:
        assert regime in REGIME_PARAMS, f"Missing params for {regime}"

    # Check params have required keys
    required_keys = ["risk_mult", "sl_mult", "tp_mult", "strategy_preference"]
    for regime, params in REGIME_PARAMS.items():
        for key in required_keys:
            assert key in params, f"Missing key {key} in {regime} params"

    print("  ✓ All regime labels defined")
    print(f"  ✓ {len(REGIME_PARAMS)} regime parameter sets")


def test_adx_detector():
    """Test ADX regime detector."""
    print("\nTesting ADX detector...")

    df = generate_test_data(2000)
    detector = ADXRegimeDetector()

    prediction = detector.predict("EUR/USD", df)

    assert isinstance(prediction, RegimePrediction)
    assert isinstance(prediction.regime, RegimeLabel)
    assert 0 <= prediction.confidence <= 1

    print(f"  ✓ ADX prediction: {prediction.regime.value} (conf={prediction.confidence:.2f})")
    print(f"  ✓ Scores: {len(prediction.scores)} regimes")


def test_hybrid_detector():
    """Test hybrid regime detector."""
    print("\nTesting hybrid detector...")

    df = generate_test_data(2000)
    detector = HybridRegimeDetector()

    prediction = detector.predict("EUR/USD", df)

    assert isinstance(prediction, RegimePrediction)
    assert isinstance(prediction.regime, RegimeLabel)
    assert 0 <= prediction.confidence <= 1

    print(f"  ✓ Hybrid prediction: {prediction.regime.value} (conf={prediction.confidence:.2f})")

    # Test diagnostics
    diagnostics = detector.get_diagnostics("EUR/USD", df)
    assert "adx_prediction" in diagnostics
    assert "tabfm_prediction" in diagnostics
    assert "hybrid_prediction" in diagnostics

    print(f"  ✓ Diagnostics available")
    print(f"    - ADX: {diagnostics['adx_prediction']['regime']}")
    print(f"    - TabFM available: {diagnostics['tabfm_prediction']['available']}")


def test_regime_consistency():
    """Test that regime detection is consistent."""
    print("\nTesting regime consistency...")

    df = generate_test_data(2000)
    detector = ADXRegimeDetector()

    # Run prediction multiple times
    predictions = []
    for _ in range(5):
        pred = detector.predict("EUR/USD", df)
        predictions.append(pred.regime)

    # All predictions should be the same (deterministic)
    assert len(set(predictions)) == 1, "Predictions should be deterministic"

    print(f"  ✓ Predictions are deterministic")


def test_regime_params():
    """Test regime parameter mappings."""
    print("\nTesting regime parameters...")

    # Check each regime has appropriate parameters
    for regime, params in REGIME_PARAMS.items():
        # Risk multiplier should be between 0 and 2
        assert 0 <= params["risk_mult"] <= 2, f"Invalid risk_mult for {regime}"

        # SL multiplier should be positive
        assert params["sl_mult"] > 0, f"Invalid sl_mult for {regime}"

        # TP multiplier should be positive
        assert params["tp_mult"] > 0, f"Invalid tp_mult for {regime}"

        # Strategy preference should be a list
        assert isinstance(params["strategy_preference"], list), f"Invalid strategy_preference for {regime}"

    print(f"  ✓ All regime parameters valid")

    # Show example parameters
    print("\n  Example parameters (TRENDING):")
    params = REGIME_PARAMS[RegimeLabel.TRENDING]
    print(f"    Risk multiplier: {params['risk_mult']}")
    print(f"    SL multiplier: {params['sl_mult']}")
    print(f"    TP multiplier: {params['tp_mult']}")
    print(f"    Trailing enabled: {params['trailing_enabled']}")
    print(f"    Strategy preference: {params['strategy_preference']}")


def test_prediction_confidence():
    """Test confidence scoring."""
    print("\nTesting confidence scoring...")

    df = generate_test_data(2000)
    detector = ADXRegimeDetector()

    prediction = detector.predict("EUR/USD", df)

    # Check confidence is in valid range
    assert 0 <= prediction.confidence <= 1, "Confidence out of range"

    # Check is_confident property
    assert prediction.is_confident == (prediction.confidence >= 0.6)

    # Check params property
    params = prediction.params
    assert "risk_mult" in params

    print(f"  ✓ Confidence: {prediction.confidence:.2f}")
    print(f"  ✓ Is confident: {prediction.is_confident}")
    print(f"  ✓ Risk multiplier: {params['risk_mult']}")


def main():
    """Run all regime detection tests."""
    print("=" * 60)
    print("NestQuant Regime Detection - Comprehensive Test")
    print("=" * 60)

    test_regime_labels()
    test_adx_detector()
    test_hybrid_detector()
    test_regime_consistency()
    test_regime_params()
    test_prediction_confidence()

    print("\n" + "=" * 60)
    print("All Tests Passed! ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
