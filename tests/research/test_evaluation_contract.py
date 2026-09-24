"""Contract, boundary, provenance, and ledger tests for Phase 3."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from nestquant.research.shared.evaluation import (
    EvaluationConfig,
    EvaluationResult,
    EvaluationStatus,
    evaluate,
    evaluation_input_from_engine,
    evaluation_input_from_simulator,
    evaluation_input_from_trades,
)
from nestquant.research.shared.execution.contracts import (
    BacktestConfig,
    SignalIntent,
    Trade,
)
from nestquant.research.shared.execution.simulator import ExecutionSimulator
from nestquant.research.shared.provenance import (
    DataIdentity,
    LedgerEntry,
    Provenance,
    ResearchLedger,
    build_provenance,
    config_hash,
    get_git_commit,
    get_git_dirty,
    new_run_id,
)
from nestquant.research.shared.engines.backtest_engine import BacktestEngine


class DuckSignal:
    def generate(self, df, pair):
        price = float(df["close"].iloc[-1])
        return type(
            "R",
            (),
            {
                "pair": pair,
                "direction": "BUY",
                "strength": 1.0,
                "entry_price": price,
                "sl_price": price - 0.001,
                "tp_price": price + 0.002,
                "metadata": {},
                "is_active": True,
            },
        )()


def _session_df(n: int = 40) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 08:00", periods=n, freq="1h", tz="UTC")
    close = [1.10 + 0.0002 * i for i in range(n)]
    return pd.DataFrame(
        {
            "open": [c - 0.0001 for c in close],
            "high": [c + 0.0008 for c in close],
            "low": [c - 0.0008 for c in close],
            "close": close,
            "volume": [100.0] * n,
        },
        index=idx,
    )


class TestExecutionToEvaluationContract:
    def test_engine_to_evaluation(self):
        engine = BacktestEngine(DuckSignal(), BacktestConfig())
        engine.start()
        df = _session_df(60)
        for i in range(len(df) - 10):
            engine.on_bar("EUR/USD", df.iloc[i : i + 10])
        inp = evaluation_input_from_engine(engine)
        result = evaluate(inp)
        assert result.metrics.total_trades.status.value in ("DEFINED", "UNDEFINED")
        assert result.status in (EvaluationStatus.VALID, EvaluationStatus.VALID_WITH_WARNINGS)

    def test_simulator_to_evaluation(self):
        sim = ExecutionSimulator(BacktestConfig())
        intent = SignalIntent(
            pair="EUR/USD",
            direction="BUY",
            strength=1.0,
            entry_price=1.10,
            sl_price=1.099,
            tp_price=1.102,
        )
        sim.open_trade(intent, pd.Timestamp("2024-01-02 10:00", tz="UTC"))
        df = _session_df(1)
        df.index = pd.DatetimeIndex([pd.Timestamp("2024-01-02 11:00", tz="UTC")])
        df.loc[:, "high"] = 1.11
        df.loc[:, "low"] = 1.0995
        sim.check_exits("EUR/USD", df)
        inp = evaluation_input_from_simulator(sim)
        result = evaluate(inp)
        assert result.metrics.total_trades.value == 1
        assert result.execution_ref == "execution.ExecutionSimulator"


class TestImportBoundaries:
    def test_evaluation_package_no_production_or_strategy2(self):
        pkg = Path(__file__).resolve().parents[2] / "research" / "shared" / "evaluation"
        for py in pkg.glob("*.py"):
            src = py.read_text()
            assert "nestquant.production" not in src, py
            assert "strategy2" not in src, py
            assert "apparatus" not in src, py

    def test_provenance_package_no_production_or_strategy2(self):
        pkg = Path(__file__).resolve().parents[2] / "research" / "shared" / "provenance"
        for py in pkg.glob("*.py"):
            src = py.read_text()
            assert "nestquant.production" not in src, py
            assert "strategy2" not in src, py

    def test_importing_evaluation_does_not_load_production_signals(self):
        import importlib
        import sys

        for m in [k for k in sys.modules if k.startswith("nestquant.production")]:
            del sys.modules[m]
        importlib.import_module("nestquant.research.shared.evaluation")
        assert not any(k.startswith("nestquant.production.signals") for k in sys.modules)


class TestCompatibilityPhase2:
    def test_backtest_metrics_still_importable(self):
        from nestquant.research.shared.backtest.metrics import calculate_metrics

        m = calculate_metrics([10.0, -5.0])
        assert m.total_trades == 2

    def test_execution_get_results_unchanged_shape(self):
        sim = ExecutionSimulator(BacktestConfig())
        intent = SignalIntent(
            pair="EUR/USD",
            direction="BUY",
            strength=1.0,
            entry_price=1.10,
            sl_price=1.099,
            tp_price=1.102,
        )
        sim.open_trade(intent, pd.Timestamp("2024-01-02 10:00", tz="UTC"))
        df = _session_df(1)
        df.index = pd.DatetimeIndex([pd.Timestamp("2024-01-02 11:00", tz="UTC")])
        df.loc[:, "high"] = 1.11
        df.loc[:, "low"] = 1.0995
        sim.check_exits("EUR/USD", df)
        results = sim.get_results()
        assert set(results.keys()) >= {
            "total_trades",
            "win_rate",
            "profit_factor",
            "total_pnl",
            "max_drawdown",
            "sharpe_ratio",
            "avg_win",
            "avg_loss",
            "expectancy",
            "trades",
        }

    def test_canonical_vs_backtest_metrics_shared_formulas(self):
        """Exact-compat: shared formulas agree on mixed fixture."""
        from nestquant.research.shared.backtest.metrics import calculate_metrics

        pnls = [10.0, -5.0, 20.0, -10.0]
        trades = []
        for i, p in enumerate(pnls):
            trades.append(
                Trade(
                    pair="EUR/USD",
                    direction="BUY",
                    entry_price=1.1,
                    entry_time=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
                    sl_price=1.09,
                    tp_price=1.12,
                    lot_size=0.1,
                    exit_price=1.11,
                    exit_time=pd.Timestamp("2024-01-02 14:00", tz="UTC"),
                    pnl=p,
                    exit_reason="tp",
                )
            )
        bt = calculate_metrics(pnls, initial_balance=10000.0)
        can, _ = __import__(
            "nestquant.research.shared.evaluation.metrics", fromlist=["compute_metrics"]
        ).compute_metrics(trades, EvaluationConfig(), initial_balance=10000.0)
        assert can.total_trades.value == bt.total_trades
        assert can.win_rate.value == pytest.approx(bt.win_rate)
        assert can.total_pnl.value == pytest.approx(bt.total_pnl)
        assert can.expectancy.value == pytest.approx(bt.expectancy)
        # drawdown: both use trade-normalized equity when no equity curve
        assert can.max_drawdown.value == pytest.approx(bt.max_drawdown, rel=1e-9)
        assert can.sharpe_ratio.value == pytest.approx(bt.sharpe_ratio, rel=1e-9)


class TestProvenance:
    def test_new_run_id_unique(self):
        assert new_run_id() != new_run_id()

    def test_config_hash_deterministic(self):
        a = {"x": 1, "y": [1, 2]}
        b = {"y": [1, 2], "x": 1}
        assert config_hash(a) == config_hash(b)
        assert config_hash(a) is not None
        assert config_hash(None) is None

    def test_git_identity_available_or_none(self):
        commit = get_git_commit()
        dirty = get_git_dirty()
        # In this repo git should work
        assert commit is None or (isinstance(commit, str) and len(commit) >= 7)
        assert dirty is None or isinstance(dirty, bool)

    def test_build_provenance_from_evaluation(self):
        result = evaluate(
            [
                Trade(
                    pair="EUR/USD",
                    direction="BUY",
                    entry_price=1.1,
                    entry_time=pd.Timestamp("2024-01-02 10:00", tz="UTC"),
                    sl_price=1.09,
                    tp_price=1.12,
                    lot_size=0.1,
                    exit_price=1.11,
                    exit_time=pd.Timestamp("2024-01-02 14:00", tz="UTC"),
                    pnl=10.0,
                    exit_reason="tp",
                )
            ],
            execution_metadata=__import__(
                "nestquant.research.shared.evaluation.contracts",
                fromlist=["ExecutionMetadata"],
            ).ExecutionMetadata(initial_balance=10000.0),
        )
        prov = build_provenance(
            evaluation=result,
            data=DataIdentity(instruments=("EUR/USD",), timeframe="1h"),
            strategy_identity="duck",
        )
        assert prov.run_id.startswith("run-")
        assert prov.evaluation_id == result.evaluation_id
        assert prov.evaluation_config_hash is not None
        assert prov.git.available in (True, False)
        # dirty tree must be represented if known
        d = prov.to_dict()
        assert d["git"]["dirty"] in (True, False, None)

    def test_provenance_roundtrip(self):
        prov = build_provenance(
            evaluation=EvaluationConfig().to_dict(),
            data={"instruments": ["EUR/USD"], "timeframe": "4h", "start": "2020-01-01"},
        )
        back = Provenance.from_dict(prov.to_dict())
        assert back.run_id == prov.run_id
        assert back.data.timeframe == "4h"

    def test_provenance_without_git_fails_closed(self, tmp_path):
        # cwd that is not a git repo
        prov = build_provenance(cwd=str(tmp_path))
        assert prov.git.available is False
        assert prov.git.commit is None
        assert prov.code_version is None


class TestLedger:
    def test_append_and_retrieve(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = ResearchLedger(path)
        prov = build_provenance(strategy_identity="w1")
        entry = ledger.append_provenance(prov, status="RECORDED", result_ref="eval://x")
        assert path.exists()
        assert ledger.get(prov.run_id) is not None
        assert ledger.get(prov.run_id).result_ref == "eval://x"
        assert prov.run_id in ledger.run_ids()

    def test_no_silent_overwrite(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = ResearchLedger(path)
        prov = build_provenance()
        ledger.append_provenance(prov)
        with pytest.raises(ValueError, match="already exists"):
            ledger.append_provenance(prov)

    def test_serialize_deserialize(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = ResearchLedger(path)
        prov = build_provenance(strategy_identity="abc")
        ledger.append_provenance(prov, warnings=("w1",))
        entries = ledger.entries()
        assert len(entries) == 1
        line = path.read_text().strip().splitlines()[0]
        parsed = json.loads(line)
        assert parsed["run_id"] == prov.run_id
        assert parsed["warnings"] == ["w1"]
        # deterministic line for same entry
        again = json.dumps(entries[0].to_dict(), sort_keys=True, default=str)
        assert again == line

    def test_append_only_preserves_prior(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = ResearchLedger(path)
        p1 = build_provenance(strategy_identity="a")
        p2 = build_provenance(strategy_identity="b")
        ledger.append_provenance(p1)
        ledger.append_provenance(p2)
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["run_id"] == p1.run_id
        assert json.loads(lines[1])["run_id"] == p2.run_id

    def test_ledger_entry_from_provenance_fields(self, tmp_path):
        prov = build_provenance(
            evaluation=evaluate([]),
            data=DataIdentity(instruments=("EUR/USD",), timeframe="4h"),
            strategy_identity="test-workload",
        )
        entry = LedgerEntry.from_provenance(prov, status="COMPLETE")
        d = entry.to_dict()
        assert d["run_id"] == prov.run_id
        assert d["data_identity"]["timeframe"] == "4h"
        assert d["workload_identity"] == "test-workload"
        assert d["git_commit"] is None or isinstance(d["git_commit"], str)
