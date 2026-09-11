"""
Tests for nestquant.data.loader and nestquant.knowledge.experiment_tracker.
"""

import tempfile
from datetime import datetime

import pandas as pd
import pytest

from nestquant.data.loader import DataLoader
from nestquant.knowledge.experiment_tracker import Experiment, ExperimentTracker


class TestDataLoader:
    def test_init_default(self):
        loader = DataLoader()
        assert loader.data_dir is not None

    def test_init_custom_dir(self, tmp_path):
        loader = DataLoader(data_dir=str(tmp_path))
        assert loader.data_dir == tmp_path

    def test_load_pair_missing(self, tmp_path):
        loader = DataLoader(data_dir=str(tmp_path))
        result = loader.load_pair("EUR/USD")
        assert result is None

    def test_load_pair_existing(self, tmp_path):
        # Create a pickle file
        df = pd.DataFrame(
            {"open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "volume": [100]},
            index=pd.date_range("2024-01-01", periods=1, freq="1h"),
        )
        path = tmp_path / "EUR_USD.pkl"
        df.to_pickle(path)

        loader = DataLoader(data_dir=str(tmp_path))
        result = loader.load_pair("EUR/USD")
        assert result is not None
        assert len(result) == 1

    def test_load_pairs(self, tmp_path):
        # Create two pair files
        for pair in ["EUR_USD", "GBP_USD"]:
            df = pd.DataFrame(
                {"open": [1.0] * 2000, "high": [1.1] * 2000,
                 "low": [0.9] * 2000, "close": [1.0] * 2000,
                 "volume": [100] * 2000},
                index=pd.date_range("2024-01-01", periods=2000, freq="1h"),
            )
            df.to_pickle(tmp_path / f"{pair}.pkl")

        loader = DataLoader(data_dir=str(tmp_path))
        result = loader.load_pairs(pairs=["EUR/USD", "GBP/USD"])
        assert len(result) == 2

    def test_load_pairs_filters_small(self, tmp_path):
        # Create a file with too few rows
        df = pd.DataFrame(
            {"open": [1.0] * 100, "high": [1.1] * 100,
             "low": [0.9] * 100, "close": [1.0] * 100,
             "volume": [100] * 100},
            index=pd.date_range("2024-01-01", periods=100, freq="1h"),
        )
        df.to_pickle(tmp_path / "EUR_USD.pkl")

        loader = DataLoader(data_dir=str(tmp_path))
        result = loader.load_pairs(pairs=["EUR/USD"])
        # 100 rows < 1000 minimum, should be filtered out
        assert len(result) == 0

    def test_get_available_pairs(self, tmp_path):
        df = pd.DataFrame(
            {"open": [1.0] * 2000, "high": [1.1] * 2000,
             "low": [0.9] * 2000, "close": [1.0] * 2000,
             "volume": [100] * 2000},
            index=pd.date_range("2024-01-01", periods=2000, freq="1h"),
        )
        df.to_pickle(tmp_path / "EUR_USD.pkl")

        loader = DataLoader(data_dir=str(tmp_path))
        pairs = loader.get_available_pairs()
        assert "EUR/USD" in pairs

    def test_get_data_info_empty(self, tmp_path):
        loader = DataLoader(data_dir=str(tmp_path))
        info = loader.get_data_info()
        assert info["total_pairs"] == 0
        assert info["total_bars"] == 0


class TestExperimentTracker:
    def test_start_experiment(self):
        tracker = ExperimentTracker()
        exp = tracker.start_experiment("test_exp", params={"lr": 0.01})
        assert exp.name == "test_exp"
        assert exp.params["lr"] == 0.01
        assert exp.status == "running"

    def test_log_metric(self):
        tracker = ExperimentTracker()
        tracker.start_experiment("test")
        tracker.log_metric("accuracy", 0.95)
        exp = tracker._experiments[0]
        assert exp.metrics["accuracy"] == 0.95

    def test_log_params(self):
        tracker = ExperimentTracker()
        tracker.start_experiment("test")
        tracker.log_params({"lr": 0.01, "epochs": 100})
        exp = tracker._experiments[0]
        assert exp.params["lr"] == 0.01
        assert exp.params["epochs"] == 100

    def test_log_artifact(self):
        tracker = ExperimentTracker()
        tracker.start_experiment("test")
        tracker.log_artifact("model", "/path/to/model.pkl")
        exp = tracker._experiments[0]
        assert exp.artifacts["model"] == "/path/to/model.pkl"

    def test_end_experiment(self):
        tracker = ExperimentTracker()
        tracker.start_experiment("test")
        tracker.end_experiment("completed")
        exp = tracker._experiments[0]
        assert exp.status == "completed"
        assert exp.end_time is not None
        assert exp.duration is not None
        assert exp.duration >= 0

    def test_get_experiments_by_name(self):
        tracker = ExperimentTracker()
        tracker.start_experiment("exp_a")
        tracker.end_experiment()
        tracker.start_experiment("exp_b")
        tracker.end_experiment()

        results = tracker.get_experiments(name="exp_a")
        assert len(results) == 1
        assert results[0].name == "exp_a"

    def test_get_experiments_by_status(self):
        tracker = ExperimentTracker()
        tracker.start_experiment("exp_a")
        tracker.end_experiment("completed")
        tracker.start_experiment("exp_b")
        tracker.end_experiment("failed")

        results = tracker.get_experiments(status="completed")
        assert len(results) == 1

    def test_get_best_experiment(self):
        tracker = ExperimentTracker()
        tracker.start_experiment("exp_a")
        tracker.log_metric("sharpe", 1.5)
        tracker.end_experiment("completed")

        tracker.start_experiment("exp_b")
        tracker.log_metric("sharpe", 2.0)
        tracker.end_experiment("completed")

        best = tracker.get_best_experiment("sharpe", minimize=False)
        assert best.name == "exp_b"

    def test_get_best_experiment_minimize(self):
        tracker = ExperimentTracker()
        tracker.start_experiment("exp_a")
        tracker.log_metric("loss", 0.5)
        tracker.end_experiment("completed")

        tracker.start_experiment("exp_b")
        tracker.log_metric("loss", 0.1)
        tracker.end_experiment("completed")

        best = tracker.get_best_experiment("loss", minimize=True)
        assert best.name == "exp_b"

    def test_get_best_experiment_none_completed(self):
        tracker = ExperimentTracker()
        tracker.start_experiment("exp_a")
        # Don't end it
        best = tracker.get_best_experiment("sharpe")
        assert best is None

    def test_experiment_deterministic_duration(self):
        exp = Experiment(name="test")
        exp.end_time = exp.start_time
        assert exp.duration == 0.0

    def test_log_metric_no_current(self):
        tracker = ExperimentTracker()
        # Should not crash
        tracker.log_metric("acc", 0.9)
