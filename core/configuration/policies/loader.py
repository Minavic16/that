"""
NestQuant Live Parameter Policy — Loader
==========================================
Serialization and deserialization for LiveParameterPolicy.

Supports JSON as the canonical exchange format.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Union

from nestquant.core.configuration.policies.models import (
    ExecutionParams,
    HardLimits,
    LiveParameterPolicy,
    RiskParams,
    StrategyParams,
)
from nestquant.core.configuration.policies.validator import PolicyValidationError, validate_policy


def _strategy_to_dict(s: StrategyParams) -> Dict[str, Any]:
    return {
        "z_entry_threshold": s.z_entry_threshold,
        "z_exit_threshold": s.z_exit_threshold,
        "lookback": s.lookback,
        "atr_period": s.atr_period,
        "atr_sl_multiplier": s.atr_sl_multiplier,
        "rrr": s.rrr,
        "min_divergence": s.min_divergence,
        "breakeven_ratio": s.breakeven_ratio,
        "enable_macro_filter": s.enable_macro_filter,
    }


def _execution_to_dict(e: ExecutionParams) -> Dict[str, Any]:
    return {
        "max_lot": e.max_lot,
        "min_lot": e.min_lot,
        "max_open_trades": e.max_open_trades,
        "max_per_currency_block": e.max_per_currency_block,
        "max_concurrent_positions": e.max_concurrent_positions,
        "commission_per_lot": e.commission_per_lot,
        "slippage_pips": e.slippage_pips,
        "default_spread_pips": e.default_spread_pips,
    }


def _risk_to_dict(r: RiskParams) -> Dict[str, Any]:
    return {
        "risk_per_trade": r.risk_per_trade,
        "initial_balance": r.initial_balance,
        "max_dd_pct": r.max_dd_pct,
        "dd_reduce_threshold": r.dd_reduce_threshold,
        "dd_reduced_risk": r.dd_reduced_risk,
        "enable_recovery": r.enable_recovery,
        "dynamic_lot_scaling": r.dynamic_lot_scaling,
        "max_position_risk_pct": r.max_position_risk_pct,
    }


def _hard_limits_to_dict(h: HardLimits) -> Dict[str, Any]:
    return {
        "hard_dd_pct": h.hard_dd_pct,
        "soft_dd_pct": h.soft_dd_pct,
        "max_consecutive_losses": h.max_consecutive_losses,
        "daily_loss_limit_pct": h.daily_loss_limit_pct,
        "floating_loss_kill_threshold": h.floating_loss_kill_threshold,
    }


def policy_to_dict(policy: LiveParameterPolicy) -> Dict[str, Any]:
    """Serialize a LiveParameterPolicy to a dictionary."""
    return {
        "policy_version": policy.policy_version,
        "research_run_id": policy.research_run_id,
        "strategy": _strategy_to_dict(policy.strategy),
        "execution": _execution_to_dict(policy.execution),
        "risk": _risk_to_dict(policy.risk),
        "hard_limits": _hard_limits_to_dict(policy.hard_limits),
    }


def policy_to_json(policy: LiveParameterPolicy, indent: int = 2) -> str:
    """Serialize a LiveParameterPolicy to a JSON string."""
    return json.dumps(policy_to_dict(policy), indent=indent)


def _dict_to_strategy(d: Dict[str, Any]) -> StrategyParams:
    return StrategyParams(
        z_entry_threshold=d.get("z_entry_threshold", 2.2),
        z_exit_threshold=d.get("z_exit_threshold", 0.5),
        lookback=d.get("lookback", 20),
        atr_period=d.get("atr_period", 14),
        atr_sl_multiplier=d.get("atr_sl_multiplier", 3.0),
        rrr=d.get("rrr", 2.0),
        min_divergence=d.get("min_divergence", 10.0),
        breakeven_ratio=d.get("breakeven_ratio", 1.5),
        enable_macro_filter=d.get("enable_macro_filter", True),
    )


def _dict_to_execution(d: Dict[str, Any]) -> ExecutionParams:
    return ExecutionParams(
        max_lot=d.get("max_lot", 0.20),
        min_lot=d.get("min_lot", 0.01),
        max_open_trades=d.get("max_open_trades", 1),
        max_per_currency_block=d.get("max_per_currency_block", 1),
        max_concurrent_positions=d.get("max_concurrent_positions", 1),
        commission_per_lot=d.get("commission_per_lot", 6.0),
        slippage_pips=d.get("slippage_pips", 0.1),
        default_spread_pips=d.get("default_spread_pips", 0.5),
    )


def _dict_to_risk(d: Dict[str, Any]) -> RiskParams:
    return RiskParams(
        risk_per_trade=d.get("risk_per_trade", 0.02),
        initial_balance=d.get("initial_balance", 200.0),
        max_dd_pct=d.get("max_dd_pct", 55.0),
        dd_reduce_threshold=d.get("dd_reduce_threshold", 30.0),
        dd_reduced_risk=d.get("dd_reduced_risk", 0.02),
        enable_recovery=d.get("enable_recovery", True),
        dynamic_lot_scaling=d.get("dynamic_lot_scaling", True),
        max_position_risk_pct=d.get("max_position_risk_pct", 1.0),
    )


def _dict_to_hard_limits(d: Dict[str, Any]) -> HardLimits:
    return HardLimits(
        hard_dd_pct=d.get("hard_dd_pct", 8.0),
        soft_dd_pct=d.get("soft_dd_pct", 6.0),
        max_consecutive_losses=d.get("max_consecutive_losses", 5),
        daily_loss_limit_pct=d.get("daily_loss_limit_pct", 0.03),
        floating_loss_kill_threshold=d.get("floating_loss_kill_threshold", -15.0),
    )


def dict_to_policy(d: Dict[str, Any]) -> LiveParameterPolicy:
    """Deserialize a dictionary to a LiveParameterPolicy.

    Does NOT validate by default — call validate_policy() explicitly if needed.
    """
    return LiveParameterPolicy(
        policy_version=d.get("policy_version", "1.0.0"),
        research_run_id=d.get("research_run_id", ""),
        strategy=_dict_to_strategy(d.get("strategy", {})),
        execution=_dict_to_execution(d.get("execution", {})),
        risk=_dict_to_risk(d.get("risk", {})),
        hard_limits=_dict_to_hard_limits(d.get("hard_limits", {})),
    )


def json_to_policy(raw: str, *, validate: bool = True) -> LiveParameterPolicy:
    """Deserialize a JSON string to a LiveParameterPolicy.

    Args:
        raw: JSON string.
        validate: If True, raises PolicyValidationError on invalid policies.

    Returns:
        LiveParameterPolicy instance.
    """
    d = json.loads(raw)
    policy = dict_to_policy(d)
    if validate:
        errors = validate_policy(policy)
        if errors:
            raise PolicyValidationError(errors)
    return policy


def save_policy(policy: LiveParameterPolicy, path: Union[str, Path]) -> None:
    """Save a LiveParameterPolicy to a JSON file.

    Always validates before saving.
    """
    errors = validate_policy(policy)
    if errors:
        raise PolicyValidationError(errors)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(policy_to_json(policy) + "\n")


def load_policy(path: Union[str, Path], *, validate: bool = True) -> LiveParameterPolicy:
    """Load a LiveParameterPolicy from a JSON file.

    Args:
        path: Path to JSON file.
        validate: If True, raises PolicyValidationError on invalid policies.

    Returns:
        LiveParameterPolicy instance.
    """
    raw = Path(path).read_text()
    return json_to_policy(raw, validate=validate)
