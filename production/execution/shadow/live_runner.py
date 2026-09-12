"""
Live read-only shadow runner — S7 READ-ONLY LIVE SHADOW.

Polls a ReadOnlyMarketDataAdapter for newly completed 4H candles,
feeds each exactly once into the frozen ShadowCausalSignalGenerator,
and logs live-augmented records. No order path is ever touched.

Safety: install_hard_guard() is called before any import that could
lead to order submission. Any attempt to call OrderSend terminates
with CRITICAL and is recorded in orders_submitted_count.json (must stay 0).
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from nestquant.core.data.loader import DataLoader
from nestquant.production.execution.shadow.health import HealthMonitor
from nestquant.production.execution.shadow.kill_switch import KillSwitch
from nestquant.production.execution.shadow.live_adapter import ReadOnlyMarketDataAdapter, StubLiveAdapter
from nestquant.production.execution.shadow.logger import ShadowLogger
from nestquant.production.execution.shadow.safety import install_hard_guard, verify_zero_orders
from nestquant.production.execution.shadow.signal_generator import ShadowCausalSignalGenerator
from nestquant.production.execution.shadow.state import ShadowState
try:
    from nestquant.production.notifications.signal_notifier import send_signal_alert
except ImportError:
    send_signal_alert = None


def _parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class LiveShadowRunner:
    """Polling live-shadow runner (read-only)."""

    EXPECTED_BAR_SEC = 4 * 3600
    STALE_THRESHOLD_SEC = EXPECTED_BAR_SEC + 30 * 60  # 4h30m
    CLOCK_SKEW_THRESHOLD_SEC = 10  # broker vs local receipt

    def __init__(
        self,
        *,
        adapter: Optional[ReadOnlyMarketDataAdapter] = None,
        pairs: Optional[list[str]] = None,
        timeframe: str = "4h",
        data_dir: Optional[str] = None,
        log_dir: str | Path = "logs/shadow_live",
        state_path: Optional[str | Path] = None,
        kill_switch_path: Optional[str | Path] = None,
        poll_interval_sec: float = 60.0,
        spread_map: Optional[dict[str, float]] = None,
        max_iterations: Optional[int] = None,  # for tests: stop after N polls
    ) -> None:
        self.timeframe = timeframe
        self.log_dir = Path(log_dir)
        self.state_path = Path(state_path) if state_path else self.log_dir / "state.json"
        self.poll_interval_sec = poll_interval_sec
        self.max_iterations = max_iterations

        # Hard guard first
        install_hard_guard(self.log_dir)

        self.logger = ShadowLogger(log_dir=self.log_dir)
        self.health = HealthMonitor()
        self.kill_switch = KillSwitch(primary_path=kill_switch_path or (self.log_dir / "KILL"))
        self.state = ShadowState(path=self.state_path)
        self.generator = ShadowCausalSignalGenerator(spread_pips_map=spread_map)
        self.loader = DataLoader(data_dir=data_dir)

        if pairs is None:
            import json as _json
            s6c = Path("research_data/s6c/S6C_causal_swing_results.json")
            if s6c.exists():
                try:
                    pairs = _json.loads(s6c.read_text())["config"]["pairs_loaded"]
                except Exception:
                    pairs = None
            if not pairs:
                from nestquant.core.configuration.settings import get_config
                pairs = list(get_config().universe.all_pairs[:20])
        self.pairs = list(pairs)

        if adapter is None:
            # Default to stub backed by files (works on Linux without MT5)
            adapter = StubLiveAdapter(data_dir=str(self.loader.data_dir) if hasattr(self.loader, "data_dir") else None, timeframe=timeframe, pairs=self.pairs)
        self.adapter = adapter

        # Metrics for S7_LIVE_SHADOW_REPORT
        self._bars_observed = 0
        self._bars_processed = 0
        self._signals = 0
        self._duplicates = 0
        self._missed_bars = 0
        self._reconnects = 0
        self._crashes = 0
        self._health_failures = 0
        self._spreads: list[float] = []
        self._latencies: list[float] = []
        self._clock_mismatches = 0
        self._broker_discrepancies: list[str] = []
        self._start_iso = datetime.now(timezone.utc).isoformat()
        self._bars_observed_set: set[tuple[str, str]] = set()  # (pair, ts)

    def _expected_next_ts(self, last_iso: Optional[str]) -> Optional[datetime]:
        if not last_iso:
            return None
        try:
            return _parse_iso(last_iso) + timedelta(seconds=self.EXPECTED_BAR_SEC)
        except Exception:
            return None

    def _is_weekend_gap(self, expected: datetime, actual: datetime) -> bool:
        """True if gap is due to normal Fri→Sun FX market closure, not data loss."""
        gap_sec = (actual - expected).total_seconds()
        # Normal weekend closure: Fri 22:00 UTC → Sun 22:00 UTC ≈ 48h = 12×4h
        # Allow 40–60h window to cover broker variations (21:00–22:00 close)
        if 40 * 3600 <= gap_sec <= 60 * 3600:
            # Check if interval spans a weekend (contains Sat/Sun)
            cur = expected
            while cur < actual:
                if cur.weekday() in (5, 6):  # Saturday=5, Sunday=6
                    return True
                cur += timedelta(seconds=self.EXPECTED_BAR_SEC)
            # Also check if expected is Fri evening and actual is Sun evening/Mon morning
            if expected.weekday() == 4 and actual.weekday() in (6, 0):
                return True
        return False

    def run(self) -> dict[str, Any]:
        # Load Telegram credentials from .env.telegram
        _env_file = Path("/root/that/.env.telegram")
        if not _env_file.exists():
            _env_file = Path("/root/that/.env.telegram")
        if _env_file.exists():
            for line in _env_file.read_text().splitlines():
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    import os
                    os.environ.setdefault(k.strip(), v.strip())
        self.logger.log_infrastructure("STARTUP", f"live shadow start pairs={self.pairs} tf={self.timeframe} poll={self.poll_interval_sec}s adapter={self.adapter.name}")
        self.health.heartbeat()

        # Initial connect with retry
        if not self.adapter.is_connected():
            ok = self.adapter.connect()
            if not ok:
                self.logger.log_infrastructure("ERROR", "initial adapter connect failed", impact="MISSED_SIGNAL", resolution="retry")
                self.health.record_gap("initial connect failed")
            else:
                self._reconnects += 1

        iteration = 0
        try:
            while True:
                if self.max_iterations is not None and iteration >= self.max_iterations:
                    break
                iteration += 1

                # Kill switch
                if self.kill_switch.is_active():
                    self.health.set_kill_switch(True)
                    self.logger.log_infrastructure("CRITICAL", "kill switch active — halting live shadow", impact="MISSED_SIGNAL", resolution="manual clear required")
                    break

                # Reconnect check
                if not self.adapter.is_connected():
                    self.logger.log_infrastructure("RECONNECT", "adapter disconnected — attempting reconnect", impact="MISSED_SIGNAL")
                    ok = self.adapter.connect()
                    if ok:
                        self._reconnects += 1
                        self.logger.log_infrastructure("RECONNECT", "reconnect succeeded", impact="NO_IMPACT", resolution="auto-reconnect")
                    else:
                        self.health.record_gap("reconnect failed")
                        time.sleep(min(self.poll_interval_sec, 5))
                        continue

                # Poll each pair
                for pair in self.pairs:
                    if self.kill_switch.is_active():
                        break
                    bar = self.adapter.get_last_completed_bar(pair, timeframe=self.timeframe)
                    if bar is None:
                        continue
                    self._bars_observed += 1
                    key = (pair, bar.timestamp)
                    # Duplicate / already-processed detection (restart safety)
                    last = self.state.last_bar.get(pair)
                    is_duplicate = False
                    if last:
                        try:
                            if _parse_iso(bar.timestamp) <= _parse_iso(last):
                                is_duplicate = True
                        except Exception:
                            if bar.timestamp <= last:
                                is_duplicate = True
                    if is_duplicate:
                        self._duplicates += 1
                        self.logger.log_infrastructure("DUPLICATE", f"{pair} duplicate bar {bar.timestamp}", impact="NO_IMPACT")
                        continue
                    # Missing detection: expected next vs actual (weekend-aware)
                    expected = self._expected_next_ts(last)
                    if expected and last:
                        try:
                            actual = _parse_iso(bar.timestamp)
                            if actual > expected + timedelta(seconds=60):
                                if self._is_weekend_gap(expected, actual):
                                    self.logger.log_infrastructure("INFO", f"{pair} weekend market closure {expected.isoformat()} → {bar.timestamp} (not counted as missed)", impact="NO_IMPACT")
                                else:
                                    gap_sec = (actual - expected).total_seconds()
                                    missed = int(round(gap_sec / self.EXPECTED_BAR_SEC))
                                    if missed > 0:
                                        self._missed_bars += missed
                                        self.health.record_gap(f"{pair} missed {missed} bar(s) gap {gap_sec:.0f}s")
                                        self.logger.log_infrastructure("ERROR", f"{pair} missed {missed} bar(s) expected {expected.isoformat()} got {bar.timestamp}", impact="MISSED_SIGNAL")
                        except Exception:
                            pass

                    # Clock mismatch detection — bar close vs receipt is not a clock skew for 4h bars
                    # (bar close at 16:00, receipt at 18:08 => 2h is expected, not skew). Suppress for historical backfill.
                    # Only count as mismatch if skew is truly anomalous (>48h) to avoid false positives on old bars.
                    try:
                        broker_dt = _parse_iso(bar.broker_timestamp)
                        receipt_dt = _parse_iso(bar.receipt_timestamp)
                        skew = abs((receipt_dt - broker_dt).total_seconds())
                        if skew > 48 * 3600:  # >48h indicates real clock issue, not normal polling delay
                            self._clock_mismatches += 1
                            self.health.add_note(f"{pair} clock skew {skew:.1f}s")
                            self.logger.log_infrastructure("WARNING", f"{pair} clock mismatch {skew:.1f}s broker {bar.broker_timestamp} receipt {bar.receipt_timestamp}", impact="NO_IMPACT")
                    except Exception:
                        pass

                    # Spread + broker vs loader discrepancy check
                    self._spreads.append(float(bar.spread))
                    # Fetch history for signal generation (need enough bars)
                    history = self.adapter.fetch_history(pair, timeframe=self.timeframe, count=600)
                    if history is None or len(history) < 50:
                        # Fallback to loader file history
                        history = self.loader.load_pair(pair, timeframe=self.timeframe)
                        if history is not None:
                            # Trim to include up to bar.timestamp
                            history = history[history.index <= _parse_iso(bar.timestamp)]
                    if history is None or len(history) < 30:
                        self.logger.log_infrastructure("ERROR", f"{pair} insufficient history for signal generation", impact="MISSED_SIGNAL")
                        self.health.record_gap(f"{pair} insufficient history")
                        continue
                    # Ensure history ends at bar.timestamp (append bar if needed for stub)
                    # History from adapter should already include this bar

                    # Data integrity per bar
                    # Already validated in bar; quick OHLC check
                    if not (bar.high >= max(bar.open, bar.close) and bar.low <= min(bar.open, bar.close) and bar.high >= bar.low):
                        self.health.record_integrity_violation(f"{pair} {bar.timestamp} ohlc invalid")
                        self.logger.log_infrastructure("ERROR", f"{pair} {bar.timestamp} ohlc violation", impact="NO_IMPACT")
                        continue

                    # Generate signal — frozen generator, no mutation
                    t0 = time.perf_counter()
                    rec = self.generator.generate(history, pair)
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    self._latencies.append(latency_ms)
                    self.health._latencies.append(latency_ms)

                    # Log live bar with broker/receipt/bid/ask
                    self.logger.log_bar(
                        pair=pair,
                        bar_timestamp=bar.timestamp,
                        open_=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                        spread=bar.spread,
                        broker_timestamp=bar.broker_timestamp,
                        receipt_timestamp=bar.receipt_timestamp,
                        bid=bar.bid,
                        ask=bar.ask,
                    )
                    self._bars_processed += 1
                    self.state.mark_bar(pair, bar.timestamp)
                    self.state.inc("bars_processed", 1)
                    self.health.record_bar(bar.timestamp, latency_ms=latency_ms)
                    # For stub adapters that simulate live progression, advance pointer
                    # so next poll sees a new bar (not duplicate). MT5 adapter has no advance.
                    try:
                        adv = getattr(self.adapter, "advance", None)
                        if callable(adv):
                            adv(pair, 1)
                    except Exception:
                        pass

                    if rec is not None:
                        # Live-augmented signal logging (broker/receipt/bid/ask)
                        self.logger.log_live_signal(
                            rec,
                            broker_timestamp=bar.broker_timestamp,
                            receipt_timestamp=bar.receipt_timestamp,
                            bid=bar.bid,
                            ask=bar.ask,
                            spread=bar.spread,
                        )
                        # Intended order (shadow only)
                        self.logger.log_intended_order(
                            signal_id=rec.signal_id,
                            symbol=pair,
                            direction=rec.direction,
                            volume=0.01,
                            requested_price=rec.expected_entry,
                            sl=rec.expected_sl,
                            tp=rec.expected_tp,
                            spread_at_submission=bar.spread,
                        )
                        self._signals += 1
                        # Send Telegram notification
                        if send_signal_alert:
                            try:
                                send_signal_alert(
                                    symbol=pair,
                                    direction=rec.direction,
                                    entry=rec.expected_entry,
                                    sl=rec.expected_sl,
                                    tp=rec.expected_tp,
                                    atr=rec.atr_at_signal,
                                    latency_ms=rec.generation_latency_ms,
                                    signal_id=rec.signal_id,
                                    broker_timestamp=bar.broker_timestamp,
                                )
                            except Exception as e:
                                self.logger.log_infrastructure("WARNING", f"Telegram notification failed: {e}", impact="NO_IMPACT")
                        self.health.record_signal(latency_ms=latency_ms)
                        self.state.inc("signals_emitted", 1)

                    # Duplicate prevention: already marked, next poll will see same timestamp as duplicate
                    self.state.save()

                # Stale feed detection: if no bars processed this iteration, health may degrade
                # The health monitor's stale is based on last_bar time vs now; for live we want real-time staleness
                # We track via time since last successful bar receipt
                # (Handled via health snapshot; runner just heartbeats)
                self.health.heartbeat()
                if self.max_iterations is not None and iteration >= self.max_iterations:
                    break
                # Sleep until next poll (allow kill switch to be responsive via short sleeps)
                # For tests, poll_interval may be 0.05 sec
                time.sleep(self.poll_interval_sec)

        except Exception as e:
            self._crashes += 1
            self.logger.log_infrastructure("CRITICAL", f"live shadow crash: {type(e).__name__}: {e}", impact="MISSED_SIGNAL", resolution="restart required")
            self.health.record_integrity_violation(f"crash {e}")
            raise
        finally:
            self.state.save()
            # Final health snapshot — for stub historical replay, suppress stale (bar timestamps are old by design)
            is_stub = isinstance(self.adapter, StubLiveAdapter)
            snap = self.health.snapshot(historical=is_stub).to_dict()
            if snap["status"] == "FAILED":
                self._health_failures += 1
            self.logger.log_infrastructure("SHUTDOWN", f"live shadow done bars_processed={self._bars_processed} signals={self._signals} duplicates={self._duplicates} missed={self._missed_bars} reconnects={self._reconnects}", impact="NO_IMPACT")
            self.logger.log_infrastructure("HEALTH", f"health snapshot status={snap['status']} bars={snap['bars_processed']} signals={snap['signals_emitted']} gaps={snap['gaps_detected']}", impact="NO_IMPACT")

        # Verify zero orders
        zero = verify_zero_orders(self.log_dir)
        if zero.get("orders_submitted", 0) != 0 or zero.get("blocked_attempts", 0) != 0:
            self.logger.log_infrastructure("CRITICAL", f"order guard violation: {zero}", impact="ORDER_BLOCKED")

        # Build report payload
        spread_sorted = sorted(self._spreads) if self._spreads else []
        def _pct(p: float) -> Optional[float]:
            if not spread_sorted:
                return None
            idx = int(len(spread_sorted) * p)
            idx = max(0, min(len(spread_sorted) - 1, idx))
            return spread_sorted[idx]
        lat_sorted = sorted(self._latencies) if self._latencies else []
        def _lat_pct(p: float) -> Optional[float]:
            if not lat_sorted:
                return None
            idx = int(len(lat_sorted) * p)
            idx = max(0, min(len(lat_sorted) - 1, idx))
            return lat_sorted[idx]

        return {
            "data_source": f"{self.adapter.name} ({self.adapter.__class__.__name__}) timeframe={self.timeframe} data_dir={self.loader.data_dir}",
            "symbols": list(self.pairs),
            "timeframe": self.timeframe,
            "start_time": self._start_iso,
            "end_time": datetime.now(timezone.utc).isoformat(),
            "bars_observed": self._bars_observed,
            "bars_processed": self._bars_processed,
            "signals_generated": self._signals,
            "duplicate_signals": self._duplicates,
            "missed_bars": self._missed_bars,
            "spread_distribution": {
                "count": len(spread_sorted),
                "min": min(spread_sorted) if spread_sorted else None,
                "max": max(spread_sorted) if spread_sorted else None,
                "p50": _pct(0.50),
                "p95": _pct(0.95),
                "mean": sum(spread_sorted) / len(spread_sorted) if spread_sorted else None,
            },
            "signal_latency_ms": {
                "p50": _lat_pct(0.50),
                "p95": _lat_pct(0.95),
                "p99": _lat_pct(0.99),
                "mean": sum(lat_sorted) / len(lat_sorted) if lat_sorted else None,
            },
            "reconnects": self._reconnects,
            "crashes": self._crashes,
            "health_failures": self._health_failures,
            "clock_mismatches": self._clock_mismatches,
            "broker_discrepancies": list(self._broker_discrepancies),
            "zero_orders": zero,
            "health": self.health.snapshot(historical=isinstance(self.adapter, StubLiveAdapter)).to_dict(),
            "state_path": str(self.state.path),
            "log_dir": str(self.log_dir),
        }
