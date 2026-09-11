"""NestQuant configuration module."""

from nestquant.config.settings import (
    NestQuantConfig,
    get_config,
)

# Re-export all flat constants from settings so legacy scripts can do:
#   from config import TRADEABLE_PAIRS, INITIAL_BALANCE, ...
from nestquant.config.settings import *  # noqa: F401,F403

__all__ = ["NestQuantConfig", "get_config"]
