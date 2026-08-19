"""
NestQuant Live Parameter Policy — Validator
============================================
Validates a LiveParameterPolicy for correctness and safety.

Validation rules:
  - policy_version must be a valid semver string
  - research_run_id must be non-empty
  - All thresholds must be positive
  - Risk percentages must be in (0, 1]
  - max_lot > 0
  - hard_dd_pct > soft_dd_pct
  - max_consecutive_losses > 0
"""

from __future__ import annotations

import re
from dataclasses import fields
from typing import List

from nestquant.config.policies.models import (
    ExecutionParams,
    HardLimits,
    LiveParameterPolicy,
    RiskParams,
    StrategyParams,
)

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))"
    r"?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


class PolicyValidationError(ValueError):
    """Raised when a LiveParameterPolicy fails validation."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__(f"Policy validation failed: {'; '.join(errors)}")


def _check_positive(value: float, name: str) -> List[str]:
    if value <= 0:
        return [f"{name} must be positive, got {value}"]
    return []


def _check_risk_pct(value: float, name: str) -> List[str]:
    if not (0 < value <= 1.0):
        return [f"{name} must be in (0, 1], got {value}"]
    return []


def _check_non_negative_int(value: int, name: str) -> List[str]:
    if value <= 0:
        return [f"{name} must be > 0, got {value}"]
    return []


def validate_strategy(s: StrategyParams) -> List[str]:
    """Validate strategy parameters."""
    errors: List[str] = []
    errors.extend(_check_positive(s.z_entry_threshold, "z_entry_threshold"))
    errors.extend(_check_positive(s.z_exit_threshold, "z_exit_threshold"))
    errors.extend(_check_positive(float(s.lookback), "lookback"))
    errors.extend(_check_positive(float(s.atr_period), "atr_period"))
    errors.extend(_check_positive(s.atr_sl_multiplier, "atr_sl_multiplier"))
    errors.extend(_check_positive(s.rrr, "rrr"))
    errors.extend(_check_positive(s.min_divergence, "min_divergence"))
    errors.extend(_check_positive(s.breakeven_ratio, "breakeven_ratio"))
    return errors


def validate_execution(e: ExecutionParams) -> List[str]:
    """Validate execution parameters."""
    errors: List[str] = []
    if e.max_lot <= 0:
        errors.append(f"max_lot must be > 0, got {e.max_lot}")
    if e.min_lot <= 0:
        errors.append(f"min_lot must be > 0, got {e.min_lot}")
    if e.min_lot > e.max_lot:
        errors.append(f"min_lot ({e.min_lot}) must be <= max_lot ({e.max_lot})")
    if e.max_open_trades <= 0:
        errors.append(f"max_open_trades must be > 0, got {e.max_open_trades}")
    if e.max_per_currency_block <= 0:
        errors.append(f"max_per_currency_block must be > 0, got {e.max_per_currency_block}")
    if e.max_concurrent_positions <= 0:
        errors.append(f"max_concurrent_positions must be > 0, got {e.max_concurrent_positions}")
    errors.extend(_check_positive(e.commission_per_lot, "commission_per_lot"))
    errors.extend(_check_positive(e.slippage_pips, "slippage_pips"))
    errors.extend(_check_positive(e.default_spread_pips, "default_spread_pips"))
    return errors


def validate_risk(r: RiskParams) -> List[str]:
    """Validate risk parameters."""
    errors: List[str] = []
    errors.extend(_check_risk_pct(r.risk_per_trade, "risk_per_trade"))
    errors.extend(_check_risk_pct(r.max_position_risk_pct, "max_position_risk_pct"))
    if r.initial_balance <= 0:
        errors.append(f"initial_balance must be > 0, got {r.initial_balance}")
    if r.max_dd_pct <= 0:
        errors.append(f"max_dd_pct must be > 0, got {r.max_dd_pct}")
    if r.dd_reduce_threshold <= 0:
        errors.append(f"dd_reduce_threshold must be > 0, got {r.dd_reduce_threshold}")
    if r.dd_reduced_risk <= 0:
        errors.append(f"dd_reduced_risk must be > 0, got {r.dd_reduced_risk}")
    return errors


def validate_hard_limits(h: HardLimits) -> List[str]:
    """Validate hard safety limits."""
    errors: List[str] = []
    if h.hard_dd_pct <= 0:
        errors.append(f"hard_dd_pct must be > 0, got {h.hard_dd_pct}")
    if h.soft_dd_pct <= 0:
        errors.append(f"soft_dd_pct must be > 0, got {h.soft_dd_pct}")
    if h.hard_dd_pct <= h.soft_dd_pct:
        errors.append(
            f"hard_dd_pct ({h.hard_dd_pct}) must be > soft_dd_pct ({h.soft_dd_pct})"
        )
    errors.extend(_check_non_negative_int(h.max_consecutive_losses, "max_consecutive_losses"))
    errors.extend(_check_risk_pct(h.daily_loss_limit_pct, "daily_loss_limit_pct"))
    return errors


def validate_policy(policy: LiveParameterPolicy) -> List[str]:
    """Validate a complete LiveParameterPolicy.

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors: List[str] = []

    # Validate version format
    if not _SEMVER_RE.match(policy.policy_version):
        errors.append(f"policy_version must be valid semver, got '{policy.policy_version}'")

    # Validate research_run_id
    if not policy.research_run_id or not policy.research_run_id.strip():
        errors.append("research_run_id must be non-empty")

    # Validate sub-models
    errors.extend(validate_strategy(policy.strategy))
    errors.extend(validate_execution(policy.execution))
    errors.extend(validate_risk(policy.risk))
    errors.extend(validate_hard_limits(policy.hard_limits))

    return errors


def assert_valid(policy: LiveParameterPolicy) -> None:
    """Raise PolicyValidationError if the policy is invalid."""
    errors = validate_policy(policy)
    if errors:
        raise PolicyValidationError(errors)
