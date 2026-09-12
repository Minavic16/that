"""Z-Score Research Engine — Signal Generation Skeleton.

Separates three layers:
  1. Statistical observation  — raw Z-score / regime values
  2. Candidate signal         — hypothesis-based rule application
  3. Executable signal        — filtered, cost-adjusted, actionable

This module does NOT optimize thresholds or claim profitability.
It is a placeholder interface for the research pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nestquant.core.contracts.zscore_contracts import RegimeState, Signal, ZScoreObservation


@dataclass
class StatisticalObservation:
    """Raw statistical values at a bar — no trading decision."""
    pair: str
    timestamp: Any
    z_score: float
    regime: RegimeState | None = None
    atr_pct: float = 0.0
    rv: float = 0.0
    dist_ema200: float = 0.0
    dist_ema50: float = 0.0


@dataclass
class CandidateSignal:
    """Hypothesis-derived signal before execution filtering."""
    pair: str
    timestamp: Any
    direction: int  # 1=long, -1=short, 0=no signal
    strength: float  # [0, 1]
    reason: str
    observation: StatisticalObservation | None = None


def classify_observation(
    zscore: ZScoreObservation,
    regime: RegimeState | None = None,
    atr_pct: float = 0.0,
    rv: float = 0.0,
    dist_ema200: float = 0.0,
    dist_ema50: float = 0.0,
) -> StatisticalObservation:
    """Wrap Z-score and regime into a statistical observation."""
    return StatisticalObservation(
        pair=zscore.pair,
        timestamp=zscore.timestamp,
        z_score=zscore.z_score,
        regime=regime,
        atr_pct=atr_pct,
        rv=rv,
        dist_ema200=dist_ema200,
        dist_ema50=dist_ema50,
    )


def generate_candidate_signal(
    obs: StatisticalObservation,
    zscore_entry_threshold: float = 2.0,
) -> CandidateSignal:
    """Apply a simple mean-reversion rule as a placeholder hypothesis.

    This is NOT a proven strategy. It exists to exercise the pipeline.

    Rule:
    - Z-score < -threshold => long candidate
    - Z-score > +threshold => short candidate
    - Otherwise => no signal

    Thresholds are NOT optimized. They are arbitrary defaults.
    """
    if obs.z_score < -zscore_entry_threshold:
        direction = 1
        strength = min(abs(obs.z_score) / (zscore_entry_threshold * 2), 1.0)
        reason = "zscore_mean_reversion_long"
    elif obs.z_score > zscore_entry_threshold:
        direction = -1
        strength = min(abs(obs.z_score) / (zscore_entry_threshold * 2), 1.0)
        reason = "zscore_mean_reversion_short"
    else:
        direction = 0
        strength = 0.0
        reason = "no_signal"

    return CandidateSignal(
        pair=obs.pair,
        timestamp=obs.timestamp,
        direction=direction,
        strength=strength,
        reason=reason,
        observation=obs,
    )


def filter_to_executable(
    candidate: CandidateSignal,
    min_strength: float = 0.1,
    blocked_regimes: list[str] | None = None,
) -> Signal | None:
    """Convert candidate to executable Signal, or return None.

    Filters:
    - Direction must be non-zero
    - Strength must meet minimum
    - Volatility regime must not be blocked

    Returns None if signal is filtered out.
    """
    if candidate.direction == 0:
        return None
    if candidate.strength < min_strength:
        return None
    if blocked_regimes and candidate.observation and candidate.observation.regime and candidate.observation.regime.volatility in blocked_regimes:
        return None

    return Signal(
        pair=candidate.pair,
        timestamp=candidate.timestamp,
        direction=candidate.direction,
        strength=candidate.strength,
        entry_price=0.0,  # placeholder — execution engine sets this
        sl_price=0.0,
        tp_price=0.0,
        regime=candidate.observation.regime if candidate.observation else None,
        metadata={"reason": candidate.reason},
    )
