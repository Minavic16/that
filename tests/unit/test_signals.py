"""Unit tests for signal generation skeleton."""
from __future__ import annotations

import pandas as pd
from zscore.contracts import RegimeState, ZScoreObservation
from zscore.signals import (
    classify_observation,
    filter_to_executable,
    generate_candidate_signal,
)


def _make_zscore(z: float, pair: str = "T/USD") -> ZScoreObservation:
    return ZScoreObservation(
        pair=pair,
        timestamp=pd.Timestamp("2024-01-02 00:00", tz="UTC"),
        close=1.1000,
        z_score=z,
        rolling_mean=1.1000,
        rolling_std=0.001,
        lookback=20,
        is_causal=True,
    )


def _make_regime(vol: str = "mid_vol") -> RegimeState:
    return RegimeState(
        pair="T/USD",
        timestamp=pd.Timestamp("2024-01-02 00:00", tz="UTC"),
        trend="near_ema",
        volatility=vol,
        atr_percentile=50.0,
        is_causal=True,
    )


class TestClassifyObservation:
    def test_preserves_zscore(self):
        zs = _make_zscore(1.5)
        obs = classify_observation(zs, atr_pct=0.5)
        assert obs.z_score == 1.5
        assert obs.atr_pct == 0.5

    def test_preserves_regime(self):
        zs = _make_zscore(0.0)
        regime = _make_regime("high_vol")
        obs = classify_observation(zs, regime=regime)
        assert obs.regime.volatility == "high_vol"


class TestGenerateCandidateSignal:
    def test_long_signal(self):
        obs = classify_observation(_make_zscore(-2.5))
        cand = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        assert cand.direction == 1
        assert cand.strength > 0

    def test_short_signal(self):
        obs = classify_observation(_make_zscore(2.5))
        cand = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        assert cand.direction == -1

    def test_no_signal_within_threshold(self):
        obs = classify_observation(_make_zscore(0.5))
        cand = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        assert cand.direction == 0
        assert cand.strength == 0.0

    def test_deterministic(self):
        obs = classify_observation(_make_zscore(-2.5))
        c1 = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        c2 = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        assert c1.direction == c2.direction
        assert c1.strength == c2.strength


class TestFilterToExecutable:
    def test_returns_signal_for_valid_candidate(self):
        obs = classify_observation(_make_zscore(-2.5))
        cand = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        sig = filter_to_executable(cand)
        assert sig is not None
        assert sig.direction == 1

    def test_returns_none_for_no_signal(self):
        obs = classify_observation(_make_zscore(0.1))
        cand = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        sig = filter_to_executable(cand)
        assert sig is None

    def test_blocks_extreme_vol(self):
        obs = classify_observation(_make_zscore(-2.5), regime=_make_regime("extreme_vol"))
        cand = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        sig = filter_to_executable(cand, blocked_regimes=["extreme_vol"])
        assert sig is None

    def test_allows_unblocked_vol(self):
        obs = classify_observation(_make_zscore(-2.5), regime=_make_regime("low_vol"))
        cand = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        sig = filter_to_executable(cand, blocked_regimes=["extreme_vol"])
        assert sig is not None

    def test_min_strength_filter(self):
        obs = classify_observation(_make_zscore(-2.1))
        cand = generate_candidate_signal(obs, zscore_entry_threshold=2.0)
        sig = filter_to_executable(cand, min_strength=0.9)
        assert sig is None
