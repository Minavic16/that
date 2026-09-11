"""
Health monitor for shadow mode — S7 Protocol §3.6 + §8 bridge.

Tracks:
  - heartbeat / uptime
  - bars processed, signals emitted
  - data freshness (staleness detection)
  - generation latency stats (p50/p95)
  - gap / integrity violations observed

Provides health snapshot for the daily-report shape and for
`check_shadow_health.py` to declare HEALTHY / DEGRADED / FAILED.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class HealthSnapshot:
    status: str  # "HEALTHY" | "DEGRADED" | "FAILED"
    uptime_seconds: float
    bars_processed: int
    signals_emitted: int
    last_bar_timestamp: Optional[str]
    last_heartbeat_iso: str
    avg_latency_ms: Optional[float]
    p95_latency_ms: Optional[float]
    data_stale: bool
    gaps_detected: int
    integrity_violations: int
    kill_switch_active: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "uptime_seconds": self.uptime_seconds,
            "bars_processed": self.bars_processed,
            "signals_emitted": self.signals_emitted,
            "last_bar_timestamp": self.last_bar_timestamp,
            "last_heartbeat_iso": self.last_heartbeat_iso,
            "avg_latency_ms": self.avg_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "data_stale": self.data_stale,
            "gaps_detected": self.gaps_detected,
            "integrity_violations": self.integrity_violations,
            "kill_switch_active": self.kill_switch_active,
            "notes": list(self.notes),
        }


class HealthMonitor:
    """In-memory health tracker. Thread-unsafe by design (single runner)."""

    # Stale threshold: 2× expected bar interval for 4h = 8h
    STALE_SECONDS_4H = 8 * 3600

    def __init__(self) -> None:
        self._start = time.monotonic()
        self.bars_processed = 0
        self.signals_emitted = 0
        self.last_bar_timestamp: Optional[str] = None
        self._last_bar_epoch: Optional[float] = None
        self._latencies: list[float] = []
        self.gaps_detected = 0
        self.integrity_violations = 0
        self.kill_switch_active = False
        self._notes: list[str] = []
        self._heartbeat_count = 0

    def heartbeat(self) -> None:
        self._heartbeat_count += 1

    def record_bar(self, bar_timestamp_iso: str, latency_ms: Optional[float] = None) -> None:
        self.bars_processed += 1
        self.last_bar_timestamp = bar_timestamp_iso
        try:
            dt = datetime.fromisoformat(bar_timestamp_iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            self._last_bar_epoch = dt.timestamp()
        except Exception:
            self._last_bar_epoch = time.time()
        if latency_ms is not None:
            self._latencies.append(float(latency_ms))

    def record_signal(self, latency_ms: Optional[float] = None) -> None:
        self.signals_emitted += 1
        if latency_ms is not None:
            # Also count signal latency (deduplicated from bar latency is fine)
            pass

    def record_gap(self, note: str = "") -> None:
        self.gaps_detected += 1
        if note:
            self._notes.append(note)

    def record_integrity_violation(self, note: str = "") -> None:
        self.integrity_violations += 1
        if note:
            self._notes.append(note)

    def set_kill_switch(self, active: bool) -> None:
        self.kill_switch_active = active

    def add_note(self, note: str) -> None:
        self._notes.append(note)

    def _is_stale(self) -> bool:
        if self._last_bar_epoch is None:
            return False
        age = time.time() - self._last_bar_epoch
        # For historical replay, age will be large (bars are in the past),
        # so treat staleness as meaningful only for live mode. Shadow runner
        # overrides this by not marking historical replays stale when
        # `live_mode=False`. Default conservative: stale if no heartbeat late.
        # Keep simple: stale if not live and gap > threshold AND live_mode flag implied by recency?
        # Caller (runner) should interpret; here we just report time-since-last-bar.
        return age > self.STALE_SECONDS_4H

    def snapshot(self, *, historical: bool = False) -> HealthSnapshot:
        now = time.monotonic()
        uptime = now - self._start
        avg = sum(self._latencies) / len(self._latencies) if self._latencies else None
        p95: Optional[float] = None
        if self._latencies:
            s = sorted(self._latencies)
            p95 = s[int(len(s) * 0.95)] if len(s) > 1 else s[0]

        # Determine status
        status = "HEALTHY"
        notes = list(self._notes)
        if self.kill_switch_active:
            status = "FAILED"
            notes.append("kill switch active")
        elif self.integrity_violations > 0:
            status = "FAILED"
        elif self.gaps_detected > 0:
            status = "DEGRADED"
            notes.append(f"{self.gaps_detected} gap(s) detected")
        elif not historical and self._is_stale():
            status = "DEGRADED"
            notes.append("data stale")

        return HealthSnapshot(
            status=status,
            uptime_seconds=uptime,
            bars_processed=self.bars_processed,
            signals_emitted=self.signals_emitted,
            last_bar_timestamp=self.last_bar_timestamp,
            last_heartbeat_iso=datetime.now(timezone.utc).isoformat(),
            avg_latency_ms=avg,
            p95_latency_ms=p95,
            data_stale=self._is_stale(),
            gaps_detected=self.gaps_detected,
            integrity_violations=self.integrity_violations,
            kill_switch_active=self.kill_switch_active,
            notes=notes,
        )
