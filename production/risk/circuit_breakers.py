"""
Circuit breaker suite for live trading risk management.
Each breaker is independent: "pause" blocks new entries but leaves existing trades
to run to SL/TP. "hard_stop" flattens all and halts.

State persistence: breaker state is persisted to a JSON file via atomic
writes (temp + rename). On restart, state is loaded from the file.
Corrupted state is logged and start-fresh (corrupt file preserved for forensics).
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class BaseBreaker:
    """Base: tracks state, trigger events, and provides pause/hard_stop status."""

    def __init__(self, name: str):
        self.name = name
        self._paused = False
        self._hard_stopped = False
        self._events: list[dict] = []

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def hard_stopped(self) -> bool:
        return self._hard_stopped

    @property
    def triggered(self) -> bool:
        return self._paused or self._hard_stopped

    @property
    def events(self) -> list[dict]:
        return list(self._events)

    def _trigger(self, event_type: str, msg: str, value: float) -> None:
        event = {
            "breaker": self.name,
            "type": event_type,
            "message": msg,
            "value": value,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._events.append(event)
        logger.warning("CIRCUIT_BREAKER_TRIGGERED: %s [%s] %s", self.name, event_type, msg)

    def reset(self) -> None:
        self._paused = False
        self._hard_stopped = False
        self._events.clear()
        logger.info("CIRCUIT_BREAKER_RESET: %s", self.name)

    def pause(self) -> None:
        self._paused = True

    def unpause(self) -> None:
        self._paused = False

    def hard_stop(self) -> None:
        self._hard_stopped = True
        self._paused = True

    def check(self) -> bool:
        return False

    def status(self) -> dict:
        return {
            "name": self.name,
            "paused": self._paused,
            "hard_stopped": self._hard_stopped,
            "events": self._events[-5:] if self._events else [],
            "event_count": len(self._events),
        }

    def to_dict(self) -> dict:
        """Serialize breaker state for persistence."""
        return {
            "name": self.name,
            "paused": self._paused,
            "hard_stopped": self._hard_stopped,
            "events": self._events[-20:],  # keep last 20 events
        }

    def load_dict(self, data: dict) -> None:
        """Restore breaker state from persistence."""
        self._paused = data.get("paused", False)
        self._hard_stopped = data.get("hard_stopped", False)
        self._events = data.get("events", [])


class WinRateBreaker(BaseBreaker):
    """Pauses new entries if rolling WR drops below threshold."""

    def __init__(self, window_20: float = 0.40, window_30: float = 0.45):
        super().__init__("winrate")
        self.window_20 = window_20
        self.window_30 = window_30
        self._results: deque = deque(maxlen=30)

    def record_trade(self, pnl: float) -> None:
        self._results.append(1 if pnl > 0 else 0)

    def check(self) -> bool:
        """Check both windows. Returns True if a pause was triggered."""
        triggered = False
        if len(self._results) >= 20:
            wr_20 = np.mean(list(self._results)[-20:])
            if wr_20 < self.window_20:
                self._trigger(
                    "pause", f"WR over 20t={wr_20:.1%} < {self.window_20:.0%}", float(wr_20)
                )
                self.pause()
                triggered = True
        if len(self._results) >= 30:
            wr_30 = np.mean(list(self._results))
            if wr_30 < self.window_30:
                self._trigger(
                    "pause", f"WR over 30t={wr_30:.1%} < {self.window_30:.0%}", float(wr_30)
                )
                self.pause()
                triggered = True
        return triggered

    def status(self) -> dict:
        s = super().status()
        s["window_20_wr"] = (
            float(np.mean(list(self._results)[-20:])) if len(self._results) >= 20 else None
        )
        s["window_30_wr"] = (
            float(np.mean(list(self._results))) if len(self._results) >= 30 else None
        )
        s["total_trades_recorded"] = len(self._results)
        return s

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["results"] = list(self._results)
        d["window_20"] = self.window_20
        d["window_30"] = self.window_30
        return d

    def load_dict(self, data: dict) -> None:
        super().load_dict(data)
        self._results = deque(data.get("results", []), maxlen=30)


class SlippageBreaker(BaseBreaker):
    """Pauses if consecutive slippage outliers or rolling avg creep."""

    def __init__(
        self,
        consecutive_threshold: float = 4.8,
        consecutive_count: int = 3,
        avg_10_threshold: float = 6.0,
    ):
        super().__init__("slippage")
        self.consecutive_threshold = consecutive_threshold
        self.consecutive_count = consecutive_count
        self.avg_10_threshold = avg_10_threshold
        self._slippages: deque = deque(maxlen=10)
        self._consecutive_streak = 0

    def record_slippage(self, slippage_pips: float) -> None:
        self._slippages.append(slippage_pips)
        if slippage_pips > self.consecutive_threshold:
            self._consecutive_streak += 1
        else:
            self._consecutive_streak = 0

    def check(self) -> bool:
        triggered = False
        # Consecutive check
        if self._consecutive_streak >= self.consecutive_count:
            self._trigger(
                "pause",
                f"{self._consecutive_streak} consecutive trades >{self.consecutive_threshold}pips",
                float(self._consecutive_streak),
            )
            self.pause()
            triggered = True
        # Rolling avg check
        if len(self._slippages) >= 10:
            avg = np.mean(list(self._slippages))
            if avg > self.avg_10_threshold:
                self._trigger(
                    "pause",
                    f"10-trade avg slippage={avg:.1f}pips > {self.avg_10_threshold}pips",
                    float(avg),
                )
                self.pause()
                triggered = True
        return triggered

    def reset_consecutive(self) -> None:
        self._consecutive_streak = 0

    def status(self) -> dict:
        s = super().status()
        s["last_10_slippages"] = list(self._slippages)
        s["consecutive_streak"] = self._consecutive_streak
        s["avg_slippage_10"] = (
            float(np.mean(list(self._slippages))) if len(self._slippages) >= 10 else None
        )
        return s

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["slippages"] = list(self._slippages)
        d["consecutive_streak"] = self._consecutive_streak
        d["consecutive_threshold"] = self.consecutive_threshold
        d["consecutive_count"] = self.consecutive_count
        d["avg_10_threshold"] = self.avg_10_threshold
        return d

    def load_dict(self, data: dict) -> None:
        super().load_dict(data)
        self._slippages = deque(data.get("slippages", []), maxlen=10)
        self._consecutive_streak = data.get("consecutive_streak", 0)


class DrawdownPaceBreaker(BaseBreaker):
    """Hard stop if DD arrives too fast (the real failure signature).
    Soft pause as early warning."""

    def __init__(
        self,
        soft_dd: float = 6.0,
        soft_trades: int = 15,
        hard_dd: float = 9.0,
        hard_trades: int = 25,
    ):
        super().__init__("drawdown_pace")
        self.soft_dd = soft_dd
        self.soft_trades = soft_trades
        self.hard_dd = hard_dd
        self.hard_trades = hard_trades
        self._trade_count = 0
        self._current_dd = 0.0

    def record_trade(self, pnl: float, equity: float, peak: float) -> None:
        self._trade_count += 1
        self._current_dd = (peak - equity) / peak * 100 if peak > 0 else 0

    def check(self) -> bool:
        triggered = False
        if self._trade_count <= self.hard_trades and self._current_dd >= self.hard_dd:
            self._trigger(
                "hard_stop",
                f"DD={self._current_dd:.1f}% >= {self.hard_dd:.0f}% at trade {self._trade_count} (limit={self.hard_trades})",
                float(self._current_dd),
            )
            self.hard_stop()
            triggered = True
        elif self._trade_count <= self.soft_trades and self._current_dd >= self.soft_dd:
            self._trigger(
                "pause",
                f"DD={self._current_dd:.1f}% >= {self.soft_dd:.0f}% at trade {self._trade_count}",
                float(self._current_dd),
            )
            self.pause()
            triggered = True
        return triggered

    def status(self) -> dict:
        s = super().status()
        s["trade_count"] = self._trade_count
        s["current_dd"] = round(self._current_dd, 2)
        return s

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["trade_count"] = self._trade_count
        d["current_dd"] = self._current_dd
        d["soft_dd"] = self.soft_dd
        d["soft_trades"] = self.soft_trades
        d["hard_dd"] = self.hard_dd
        d["hard_trades"] = self.hard_trades
        return d

    def load_dict(self, data: dict) -> None:
        super().load_dict(data)
        self._trade_count = data.get("trade_count", 0)
        self._current_dd = data.get("current_dd", 0.0)


class ProfitFactorBreaker(BaseBreaker):
    """Pauses if trailing PF drops below 1.0 (edge may be gone)."""

    def __init__(self, threshold: float = 1.0, window: int = 20):
        super().__init__("profit_factor")
        self.threshold = threshold
        self.window = window
        self._pnls: deque = deque(maxlen=window)

    def record_trade(self, pnl: float) -> None:
        self._pnls.append(pnl)

    def check(self) -> bool:
        if len(self._pnls) < self.window:
            return False
        wins = [p for p in self._pnls if p > 0]
        losses = [p for p in self._pnls if p < 0]
        if not losses:
            return False
        pf = sum(wins) / abs(sum(losses))
        if pf < self.threshold:
            self._trigger(
                "pause", f"PF over {self.window}t={pf:.3f} < {self.threshold:.0f}", float(pf)
            )
            self.pause()
            return True
        return False

    def status(self) -> dict:
        s = super().status()
        wins = [p for p in self._pnls if p > 0]
        losses = [p for p in self._pnls if p < 0]
        s["current_pf"] = round(sum(wins) / abs(sum(losses)), 3) if losses else None
        s["trades_in_window"] = len(self._pnls)
        return s

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["pnls"] = list(self._pnls)
        d["threshold"] = self.threshold
        d["window"] = self.window
        return d

    def load_dict(self, data: dict) -> None:
        super().load_dict(data)
        self._pnls = deque(data.get("pnls", []), maxlen=self.window)


class CorrelationBreaker(BaseBreaker):
    """Pauses trading when average pair correlation spikes (diversification collapses).
    Updated each 1H candle with the current correlation matrix."""

    def __init__(self, threshold: float = 0.80):
        super().__init__("correlation")
        self.threshold = threshold
        self._avg_correlation: Optional[float] = None

    def update_matrix(self, corr_matrix: np.ndarray) -> None:
        n = corr_matrix.shape[0]
        if n < 3:
            return
        mask: np.ndarray = ~np.eye(n, dtype=bool)
        self._avg_correlation = float(np.mean(corr_matrix[mask]))
        if self.paused or self.hard_stopped:
            return
        if self._avg_correlation > self.threshold:
            self._trigger(
                "pause",
                f"Avg pair correlation {self._avg_correlation:.2f} > {self.threshold:.2f}",
                float(self._avg_correlation),
            )
            self.pause()

    def check(self) -> bool:
        return self._paused  # already checked in update_matrix

    def status(self) -> dict:
        s = super().status()
        s["avg_correlation"] = self._avg_correlation
        s["threshold"] = self.threshold
        return s

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["avg_correlation"] = self._avg_correlation
        d["threshold"] = self.threshold
        return d

    def load_dict(self, data: dict) -> None:
        super().load_dict(data)
        self._avg_correlation = data.get("avg_correlation")


class DrawdownDriftBreaker(BaseBreaker):
    """Hard-stops if live drawdown drifts too far from backtest expected DD.
    This catches regime changes or strategy failure live."""

    def __init__(self, expected_dd_pct: float = 0.0, max_drift_pct: float = 0.0):
        super().__init__("drawdown_drift")
        self.expected_dd_pct = expected_dd_pct
        self.max_drift_pct = max_drift_pct
        self._current_dd = 0.0
        self._peak = 0.0
        self._balance = 0.0

    def record_state(self, balance: float, peak: float) -> None:
        self._balance = balance
        self._peak = peak
        self._current_dd = (peak - balance) / peak * 100 if peak > 0 else 0

    def check(self) -> bool:
        if self.max_drift_pct <= 0 and self.expected_dd_pct <= 0:
            return False
        if self._current_dd <= 0:
            return False
        drift_threshold = max(self.expected_dd_pct * 2.0, self.max_drift_pct)
        if drift_threshold <= 0:
            return False
        if self._current_dd >= drift_threshold - 1e-9:
            self._trigger(
                "hard_stop",
                f"DD={self._current_dd:.1f}% >= drift threshold {drift_threshold:.1f}% "
                f"(expected={self.expected_dd_pct:.1f}% ×2={self.expected_dd_pct * 2:.1f}%, "
                f"max_drift={self.max_drift_pct:.1f}%)",
                float(self._current_dd),
            )
            self.hard_stop()
            return True
        return False

    def status(self) -> dict:
        s = super().status()
        s["current_dd_pct"] = round(self._current_dd, 2)
        s["expected_dd_pct"] = self.expected_dd_pct
        s["max_drift_pct"] = self.max_drift_pct
        s["effective_threshold"] = round(max(self.expected_dd_pct * 2.0, self.max_drift_pct), 2)
        return s

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["current_dd"] = self._current_dd
        d["peak"] = self._peak
        d["balance"] = self._balance
        d["expected_dd_pct"] = self.expected_dd_pct
        d["max_drift_pct"] = self.max_drift_pct
        return d

    def load_dict(self, data: dict) -> None:
        super().load_dict(data)
        self._current_dd = data.get("current_dd", 0.0)
        self._peak = data.get("peak", 0.0)
        self._balance = data.get("balance", 0.0)


class BreakerSuite:
    """Orchestrates all circuit breakers with optional file persistence."""

    def __init__(
        self,
        dd_expected_pct: float = 0.0,
        dd_drift_max_pct: float = 0.0,
        breaker_overrides: Optional[dict] = None,
        persistence_path: Optional[str | Path] = None,
    ):
        overrides = breaker_overrides or {}
        wc = dict(overrides.get("winrate", {}))
        sc = dict(overrides.get("slippage", {}))
        dc = dict(overrides.get("drawdown_pace", {}))
        pc = dict(overrides.get("profit_factor", {}))
        cc = dict(overrides.get("correlation", {}))
        dd_conf = dict(overrides.get("drawdown_drift", {}))
        dd_conf.setdefault("expected_dd_pct", dd_expected_pct)
        dd_conf.setdefault("max_drift_pct", dd_drift_max_pct)

        self.winrate = WinRateBreaker(**wc)
        self.slippage = SlippageBreaker(**sc)
        self.dd_pace = DrawdownPaceBreaker(**dc)
        self.pf = ProfitFactorBreaker(**pc)
        self.correlation = CorrelationBreaker(**cc)
        self.dd_drift = DrawdownDriftBreaker(**dd_conf)
        self._any_paused = False
        self._any_hard_stopped = False
        self._persistence_path = Path(persistence_path) if persistence_path else None

        # Load persisted state if available
        if self._persistence_path:
            self._load_state()

    def record_trade(
        self,
        pnl: float,
        equity: float,
        peak: float,
        slippage_pips: float = 0.0,
    ) -> None:
        self.winrate.record_trade(pnl)
        self.pf.record_trade(pnl)
        self.dd_pace.record_trade(pnl, equity, peak)
        self.dd_drift.record_state(equity, peak)
        if slippage_pips > 0:
            self.slippage.record_slippage(slippage_pips)
        self._save_state()

    def record_dd_state(self, balance: float, peak: float) -> None:
        self.dd_drift.record_state(balance, peak)

    def update_correlation(self, corr_matrix: np.ndarray) -> None:
        self.correlation.update_matrix(corr_matrix)
        self._save_state()

    def check_all(self) -> list[dict]:
        """Run all breaker checks. Returns list of trigger events."""
        events: list[dict] = []
        for b in [
            self.winrate,
            self.slippage,
            self.pf,
            self.dd_pace,
            self.correlation,
            self.dd_drift,
        ]:
            if not b.triggered and b.check():
                events.extend(b.events[-1:])
        self._any_paused = any(b.paused for b in self.breakers)
        self._any_hard_stopped = any(b.hard_stopped for b in self.breakers)
        if events:
            self._save_state()
        return events

    @property
    def breakers(self) -> list[BaseBreaker]:
        return [self.winrate, self.slippage, self.dd_pace, self.pf, self.correlation, self.dd_drift]

    @property
    def can_trade(self) -> tuple[bool, Optional[str]]:
        """Returns (can_trade, reason_if_blocked)."""
        for b in self.breakers:
            if b.hard_stopped:
                return False, f"Hard stop: {b.name}"
            if b.paused:
                return False, f"Paused: {b.name}"
        return True, None

    def status(self) -> dict:
        return {
            "can_trade": self.can_trade[0],
            "blocked_by": self.can_trade[1],
            "any_paused": self._any_paused,
            "any_hard_stopped": self._any_hard_stopped,
            "breakers": {b.name: b.status() for b in self.breakers},
            "persistence_path": str(self._persistence_path) if self._persistence_path else None,
        }

    def save(self) -> None:
        """Explicitly persist current state to disk."""
        self._save_state()

    def load(self) -> None:
        """Explicitly load state from disk."""
        self._load_state()

    def reset(self) -> None:
        for b in self.breakers:
            b.reset()
        self._any_paused = False
        self._any_hard_stopped = False
        if self._persistence_path:
            self._save_state()
        logger.info("CIRCUIT_BREAKER_SUITE_RESET: all breakers reset")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        """Persist all breaker state to file via atomic write."""
        if not self._persistence_path:
            return
        payload = {
            "version": 1,
            "saved_at": datetime.now(UTC).isoformat(),
            "breakers": {b.name: b.to_dict() for b in self.breakers},
        }
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, dir=str(self._persistence_path.parent), encoding="utf-8"
            ) as tmp:
                json.dump(payload, tmp, indent=2, default=str)
                tmp_path = Path(tmp.name)
            tmp_path.replace(self._persistence_path)
        except Exception as e:
            logger.error("CIRCUIT_BREAKER_PERSIST_FAILED: %s", e)

    def _load_state(self) -> None:
        """Load breaker state from file. Corrupted state → start fresh."""
        if not self._persistence_path or not self._persistence_path.exists():
            return
        try:
            data = json.loads(self._persistence_path.read_text())
            if data.get("version") != 1:
                logger.warning("CIRCUIT_BREAKER_STATE_VERSION_MISMATCH: starting fresh")
                return
            breaker_data = data.get("breakers", {})
            for b in self.breakers:
                if b.name in breaker_data:
                    b.load_dict(breaker_data[b.name])
            self._any_paused = any(b.paused for b in self.breakers)
            self._any_hard_stopped = any(b.hard_stopped for b in self.breakers)
            logger.info(
                "CIRCUIT_BREAKER_STATE_LOADED: paused=%s hard_stopped=%s saved_at=%s",
                self._any_paused, self._any_hard_stopped, data.get("saved_at"),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error("CIRCUIT_BREAKER_STATE_CORRUPT: %s — starting fresh, preserving corrupt file", e)
            try:
                corrupt_path = self._persistence_path.with_suffix(".corrupt.json")
                self._persistence_path.rename(corrupt_path)
            except Exception:
                pass
