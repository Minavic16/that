"""
Smoke tests: verify every nestquant submodule is importable.
"""

import importlib
import pkgutil
import sys

import pytest

import nestquant

# All submodules that should be importable
_SUBMODULES = [
    "nestquant",
    "nestquant.config",
    "nestquant.config.settings",
    "nestquant.indicators",
    "nestquant.indicators.adx",
    "nestquant.indicators.atr",
    "nestquant.indicators.ema",
    "nestquant.indicators.pip",
    "nestquant.indicators.resampler",
    "nestquant.indicators.session",
    "nestquant.indicators.swing",
    "nestquant.signals",
    "nestquant.signals.base",
    "nestquant.signals.breakout",
    "nestquant.engines",
    "nestquant.engines.base_engine",
    "nestquant.engines.backtest_engine",
    "nestquant.engines.regime_backtest_engine",
    "nestquant.execution",
    "nestquant.execution.base",
    "nestquant.portfolio",
    "nestquant.portfolio.position_sizer",
    "nestquant.risk",
    "nestquant.risk.circuit_breakers",
    "nestquant.regime",
    "nestquant.regime.base",
    "nestquant.regime.labels",
    "nestquant.regime.adx_regime",
    "nestquant.regime.hybrid",
    "nestquant.regime.tabfm",
    "nestquant.regime.tabfm.model",
    "nestquant.regime.tabfm.features",
    "nestquant.regime.tabfm.trainer",
    "nestquant.regime.tabfm.pipeline",
    "nestquant.regime.tabfm.predictor",
    "nestquant.backtest",
    "nestquant.backtest.metrics",
    "nestquant.backtest.comparison",
    "nestquant.data",
    "nestquant.data.loader",
    "nestquant.knowledge",
    "nestquant.knowledge.experiment_tracker",
    "nestquant.utils",
    "nestquant.utils.logging",
    "nestquant.utils.time_utils",
]


class TestSmokeImports:
    """Verify every submodule can be imported."""

    @pytest.mark.parametrize("module_name", _SUBMODULES)
    def test_import(self, module_name):
        mod = importlib.import_module(module_name)
        assert mod is not None, f"importlib returned None for {module_name}"

    def test_version(self):
        assert hasattr(nestquant, "__version__")
        assert nestquant.__version__ == "0.2.0"

    def test_config_singleton(self):
        from nestquant.core.configuration.settings import get_config

        cfg = get_config()
        assert cfg is not None
        assert hasattr(cfg, "universe")
        assert hasattr(cfg, "strategy")

    def test_package_all_exports(self):
        from nestquant import __all__

        assert "NestQuantConfig" in __all__
        assert "get_config" in __all__
