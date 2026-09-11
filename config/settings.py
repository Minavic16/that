"""Backward-compatible re-export. Canonical location: platform/configuration/settings.py"""
from nestquant.platform.configuration.settings import *

# Re-export everything from the canonical location
from nestquant.platform.configuration.settings import (
    NestQuantConfig,
    get_config,
    _config,
    ALL_PAIRS,
    SESSION_OPEN_UTC,
    SESSION_CLOSE_UTC,
)
