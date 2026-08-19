"""NestQuant live parameter policy package.

Provides the research → live parameter contract:
  - LiveParameterPolicy: immutable frozen dataclass
  - Validation functions
  - JSON serialization/deserialization
"""

from nestquant.config.policies.loader import (
    dict_to_policy,
    json_to_policy,
    load_policy,
    policy_to_dict,
    policy_to_json,
    save_policy,
)
from nestquant.config.policies.models import (
    ExecutionParams,
    HardLimits,
    LiveParameterPolicy,
    RiskParams,
    StrategyParams,
)
from nestquant.config.policies.validator import (
    PolicyValidationError,
    assert_valid,
    validate_execution,
    validate_hard_limits,
    validate_policy,
    validate_risk,
    validate_strategy,
)

__all__ = [
    # Models
    "LiveParameterPolicy",
    "StrategyParams",
    "ExecutionParams",
    "RiskParams",
    "HardLimits",
    # Validation
    "validate_policy",
    "validate_strategy",
    "validate_execution",
    "validate_risk",
    "validate_hard_limits",
    "assert_valid",
    "PolicyValidationError",
    # Loader
    "policy_to_dict",
    "policy_to_json",
    "dict_to_policy",
    "json_to_policy",
    "save_policy",
    "load_policy",
]
