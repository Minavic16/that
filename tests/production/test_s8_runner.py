"""
Tests for S8.5 — s8_runner.py authorization & CLI
===================================================
Verifies mode authorization, argument parsing, and safety gates.

Run: PYTHONPATH=/root/that python -m pytest tests/test_s8_runner.py -v --noconftest
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


from nestquant.research.experiments.s8_runner import main as runner_main, parse_args


def _make_mock_factory():
    """Return (factory_fn, mock_instance) pair."""
    mock_instance = MagicMock()
    mock_instance.start.return_value = None
    factory = MagicMock(return_value=mock_instance)
    return factory, mock_instance


# ===================================================================
# Argument parsing
# ===================================================================


class TestArgParsing:
    def test_defaults(self):
        with patch("sys.argv", ["s8_runner.py"]):
            args = parse_args()
        assert args.mode == "dry-run"
        assert args.pairs == ["EUR/USD"]
        assert args.timeframe == "H4"
        assert args.poll == 60

    def test_custom_pairs(self):
        with patch("sys.argv", ["s8_runner.py", "--pairs", "EUR/USD", "GBP/USD"]):
            args = parse_args()
        assert args.pairs == ["EUR/USD", "GBP/USD"]

    def test_mode_experimental_live(self):
        with patch("sys.argv", ["s8_runner.py", "--mode", "experimental-live"]):
            args = parse_args()
        assert args.mode == "experimental-live"


# ===================================================================
# Mode authorization
# ===================================================================


class TestModeAuthorization:
    def test_dry_run_always_allowed(self):
        factory, inst = _make_mock_factory()
        with patch("sys.argv", ["s8_runner.py", "--mode", "dry-run"]):
            result = runner_main(runtime_factory=factory)
        assert result == 0
        factory.assert_called_once()

    def test_experimental_live_without_env_fails(self):
        factory, inst = _make_mock_factory()
        with patch("sys.argv", ["s8_runner.py", "--mode", "experimental-live"]):
            env = os.environ.copy()
            env.pop("NESTQUANT_EXPERIMENTAL_LIVE", None)
            with patch.dict(os.environ, env, clear=True):
                result = runner_main(runtime_factory=factory)
        assert result == 1
        factory.assert_not_called()

    def test_experimental_live_with_env_succeeds(self):
        factory, inst = _make_mock_factory()
        with patch("sys.argv", ["s8_runner.py", "--mode", "experimental-live"]):
            with patch.dict(os.environ, {"NESTQUANT_EXPERIMENTAL_LIVE": "true"}):
                result = runner_main(runtime_factory=factory)
        assert result == 0
        factory.assert_called_once()

    def test_experimental_live_with_wrong_env_value_fails(self):
        factory, inst = _make_mock_factory()
        with patch("sys.argv", ["s8_runner.py", "--mode", "experimental-live"]):
            with patch.dict(os.environ, {"NESTQUANT_EXPERIMENTAL_LIVE": "True"}):
                result = runner_main(runtime_factory=factory)
        assert result == 1
        factory.assert_not_called()

    def test_experimental_live_with_empty_env_fails(self):
        factory, inst = _make_mock_factory()
        with patch("sys.argv", ["s8_runner.py", "--mode", "experimental-live"]):
            with patch.dict(os.environ, {"NESTQUANT_EXPERIMENTAL_LIVE": ""}):
                result = runner_main(runtime_factory=factory)
        assert result == 1
        factory.assert_not_called()
