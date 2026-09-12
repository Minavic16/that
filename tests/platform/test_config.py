"""
Tests for nestquant.config module.
"""

import os

import pytest


class TestNestQuantConfig:
    def test_singleton(self):
        from nestquant.core.configuration.settings import get_config, _config
        import nestquant.core.configuration.settings as mod

        # Reset singleton
        mod._config = None
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_universe_config(self):
        from nestquant.core.configuration.settings import UniverseConfig

        u = UniverseConfig()
        assert len(u.all_pairs) == 28
        assert len(u.tradeable_pairs) == 7
        assert "EUR/USD" in u.all_pairs
        assert "EUR/USD" in u.tradeable_pairs

    def test_strategy_config(self):
        from nestquant.core.configuration.settings import StrategyConfig

        s = StrategyConfig()
        assert s.atr_period == 14
        assert s.commission_per_lot == 6.0

    def test_risk_config(self):
        from nestquant.core.configuration.settings import RiskConfig

        r = RiskConfig()
        assert r.initial_balance == 200.0
        assert r.max_dd_pct == 55.0
        assert r.max_open_trades == 1

    def test_session_config(self):
        from nestquant.core.configuration.settings import SessionConfig

        s = SessionConfig()
        assert s.open_utc == 7
        assert s.close_utc == 21

    def test_circuit_breaker_config(self):
        from nestquant.core.configuration.settings import CircuitBreakerConfig

        cb = CircuitBreakerConfig()
        assert cb.winrate_20 == 0.40
        assert cb.winrate_30 == 0.45

    def test_data_config_paths(self):
        from nestquant.core.configuration.settings import get_config

        cfg = get_config()
        assert cfg.data.data_dir is not None
        assert len(cfg.data.data_dir) > 0

    def test_legacy_aliases(self):
        from nestquant.core.configuration.settings import (
            ALL_PAIRS,
            TRADEABLE_PAIRS,
            SESSION_OPEN_UTC,
            SESSION_CLOSE_UTC,
            ATR_SL_MULTIPLIER,
            RRR,
        )
        assert len(ALL_PAIRS) == 28
        assert len(TRADEABLE_PAIRS) == 7
        assert SESSION_OPEN_UTC == 7
        assert SESSION_CLOSE_UTC == 21
        assert ATR_SL_MULTIPLIER == 3.0
        assert RRR == 2.0

    def test_frozen_dataclasses(self):
        from nestquant.core.configuration.settings import UniverseConfig, StrategyConfig

        u = UniverseConfig()
        with pytest.raises(AttributeError):
            u.all_pairs = ()

        s = StrategyConfig()
        with pytest.raises(AttributeError):
            s.atr_period = 99

    def test_config_post_init_paths(self):
        from nestquant.core.configuration.settings import get_config

        cfg = get_config()
        # data_dir should be an absolute path
        assert os.path.isabs(cfg.data.data_dir)
