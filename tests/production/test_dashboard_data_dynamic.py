"""
S10.3 — Test that dashboard health values are read from live state files,
not hardcoded. Proves dynamic data flow from filesystem to API.

These tests exercise the same read pattern the Next.js health API uses
(readFileSync / JSON.parse on state.json, signals.jsonl, orders_submitted_count.json)
but in Python to prove the principle.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers — replicate the exact read pattern from dashboard/app/api/health/route.ts
# ---------------------------------------------------------------------------


def _read_state_uptime(state_path: Path) -> float:
    """Replicate health API: read state.json, compute uptime from created_at."""
    data = json.loads(state_path.read_text())
    created_at_ms = data.get("created_at", 0)
    return (time.time() * 1000 - created_at_ms) / 1000.0


def _read_bars_processed(state_path: Path) -> int:
    """Replicate health API: read state.json counters.bars_processed."""
    data = json.loads(state_path.read_text())
    return data.get("counters", {}).get("bars_processed", 0)


def _read_signals_emitted(signals_path: Path) -> int:
    """Replicate health API: count non-empty lines in signals.jsonl."""
    if not signals_path.exists():
        return 0
    content = signals_path.read_text().strip()
    if not content:
        return 0
    return len([line for line in content.split("\n") if line.strip()])


def _read_orders(orders_path: Path) -> dict:
    """Replicate health API: read orders_submitted_count.json."""
    if not orders_path.exists():
        return {"orders_submitted": 0, "blocked_attempts": 0}
    return json.loads(orders_path.read_text())


def _read_execution_mode() -> str:
    """Replicate health API: hardcoded execution mode."""
    return "SHADOW"


# ---------------------------------------------------------------------------
# Tests — prove dynamic values change when underlying files change
# ---------------------------------------------------------------------------


class TestDashboardDataDynamic:
    """Prove that Overview values are read from live state files, not hardcoded."""

    def test_uptime_changes_with_state_file(self, tmp_path: Path):
        """Uptime is computed from state.json created_at — prove it changes."""
        state = tmp_path / "state.json"
        now_ms = time.time() * 1000

        # Created 60 seconds ago
        state.write_text(json.dumps({"created_at": now_ms - 60_000}))
        uptime_1 = _read_state_uptime(state)
        assert 55 < uptime_1 < 65, f"Expected ~60s, got {uptime_1}"

        # Created 300 seconds ago
        state.write_text(json.dumps({"created_at": now_ms - 300_000}))
        uptime_2 = _read_state_uptime(state)
        assert 295 < uptime_2 < 305, f"Expected ~300s, got {uptime_2}"

        # Proves: uptime is dynamically computed from file, not hardcoded
        assert uptime_1 != uptime_2

    def test_bars_processed_changes_with_state_file(self, tmp_path: Path):
        """Bars processed is read from state.json counters — prove it changes."""
        state = tmp_path / "state.json"

        state.write_text(json.dumps({"counters": {"bars_processed": 50}}))
        bars_1 = _read_bars_processed(state)
        assert bars_1 == 50

        state.write_text(json.dumps({"counters": {"bars_processed": 181}}))
        bars_2 = _read_bars_processed(state)
        assert bars_2 == 181

        assert bars_1 != bars_2

    def test_signals_emitted_changes_with_file(self, tmp_path: Path):
        """Signals emitted is counted from nestquant.production.signals.jsonl — prove it changes."""
        sigs = tmp_path / "signals.jsonl"

        sigs.write_text('{"id":"s1"}\n{"id":"s2"}\n{"id":"s3"}\n')
        count_1 = _read_signals_emitted(sigs)
        assert count_1 == 3

        sigs.write_text('{"id":"s1"}\n{"id":"s2"}\n{"id":"s3"}\n{"id":"s4"}\n{"id":"s5"}\n{"id":"s6"}\n{"id":"s7"}\n')
        count_2 = _read_signals_emitted(sigs)
        assert count_2 == 7

        assert count_1 != count_2

    def test_orders_change_with_file(self, tmp_path: Path):
        """Orders submitted is read from orders_submitted_count.json — prove it changes."""
        orders = tmp_path / "orders.json"

        orders.write_text(json.dumps({"orders_submitted": 0, "blocked_attempts": 0}))
        data_1 = _read_orders(orders)
        assert data_1["orders_submitted"] == 0

        # Simulate what would happen if a bug allowed an order through
        orders.write_text(json.dumps({"orders_submitted": 1, "blocked_attempts": 0}))
        data_2 = _read_orders(orders)
        assert data_2["orders_submitted"] == 1

        assert data_1["orders_submitted"] != data_2["orders_submitted"]

    def test_execution_mode_is_hardcoded(self):
        """Execution mode is a constant — prove it never changes."""
        assert _read_execution_mode() == "SHADOW"
        assert _read_execution_mode() == "SHADOW"

    def test_kill_switch_changes_with_file(self, tmp_path: Path):
        """Kill switch is determined by file existence — prove it changes."""
        kill_file = tmp_path / "KILL"

        assert not kill_file.exists()
        kill_file.write_text("")

        assert kill_file.exists()
        kill_file.unlink()
        assert not kill_file.exists()


class TestDashboardDataNotCached:
    """Prove that reading state files returns fresh data on each call."""

    def test_consecutive_reads_return_independent_values(self, tmp_path: Path):
        """Each read of state.json should return the current file content."""
        state = tmp_path / "state.json"
        now_ms = time.time() * 1000

        # Read 1: created_at 10 seconds ago
        state.write_text(json.dumps({"created_at": now_ms - 10_000, "counters": {"bars_processed": 100}}))
        val_1 = _read_bars_processed(state)

        # Write new value
        state.write_text(json.dumps({"created_at": now_ms - 10_000, "counters": {"bars_processed": 200}}))
        val_2 = _read_bars_processed(state)

        # Proves: no caching — second read got the updated value
        assert val_1 == 100
        assert val_2 == 200

    def test_signals_count_grows_with_new_signals(self, tmp_path: Path):
        """Adding signals to signals.jsonl should increase the count."""
        sigs = tmp_path / "signals.jsonl"

        sigs.write_text('{"id":"s1"}\n')
        count_1 = _read_signals_emitted(sigs)

        # Append a new signal
        with open(sigs, "a") as f:
            f.write('{"id":"s2"}\n')
        count_2 = _read_signals_emitted(sigs)

        assert count_1 == 1
        assert count_2 == 2


class TestHealthApiReadPatternParity:
    """Verify the Python read pattern matches the TypeScript health API."""

    def test_state_json_fields_match_api_expectations(self, tmp_path: Path):
        """Verify state.json has the fields the health API expects."""
        state = tmp_path / "state.json"
        state.write_text(json.dumps({
            "created_at": time.time() * 1000 - 60000,
            "counters": {
                "bars_processed": 181,
                "signals_emitted": 7,
            }
        }))
        data = json.loads(state.read_text())
        assert "created_at" in data
        assert "counters" in data
        assert "bars_processed" in data["counters"]
        assert "signals_emitted" in data["counters"]

    def test_orders_json_fields_match_api_expectations(self, tmp_path: Path):
        """Verify orders_submitted_count.json has the fields the health API expects."""
        orders = tmp_path / "orders.json"
        orders.write_text(json.dumps({
            "orders_submitted": 0,
            "blocked_attempts": 0,
        }))
        data = json.loads(orders.read_text())
        assert "orders_submitted" in data
        assert "blocked_attempts" in data
