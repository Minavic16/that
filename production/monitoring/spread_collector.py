"""
Spread Collector — Passive Market Data Sampling
================================================

Samples bid/ask/spread from the MT5 bridge at regular intervals.
Stores snapshots in-memory and optionally writes to JSONL.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from nestquant.production.monitoring.models import MarketSnapshot

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5.0


class SpreadCollector:
    """Passive spread data collector for a single symbol."""

    def __init__(
        self,
        max_snapshots: int = 10000,
        pip_size: float = 0.0001,
    ) -> None:
        self.max_snapshots = max_snapshots
        self.pip_size = pip_size
        self._snapshots: list[MarketSnapshot] = []
        self._lock = threading.Lock()
        self._collection_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._jsonl_path: Optional[Path] = None

    def set_jsonl_output(self, path: Path) -> None:
        """Enable JSONL output to the given file path."""
        self._jsonl_path = path

    def collect_once(
        self,
        client_base_url: str,
        symbol: str,
    ) -> Optional[MarketSnapshot]:
        """
        Fetch a single bid/ask snapshot from the MT5 bridge.

        Returns MarketSnapshot on success, None on failure.
        """
        url = f"{client_base_url.rstrip('/')}/tick?symbol={symbol}"
        monotonic_start = time.monotonic()

        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            if not body.get("ok", False):
                logger.warning("Bridge returned ok=false: %s", body.get("error"))
                return None

            data = body.get("data", {})
            bid = float(data.get("bid", 0))
            ask = float(data.get("ask", 0))
            spread = ask - bid
            spread_pips = spread / self.pip_size

            now_str = datetime.now(UTC).isoformat()

            snapshot = MarketSnapshot(
                timestamp=now_str,
                symbol=symbol,
                bid=bid,
                ask=ask,
                spread=spread,
                spread_pips=spread_pips,
                last=float(data.get("last", 0)),
                volume=int(data.get("volume", 0)),
                server_time=data.get("server_time"),
            )

            with self._lock:
                self._snapshots.append(snapshot)
                if len(self._snapshots) > self.max_snapshots:
                    self._snapshots = self._snapshots[-self.max_snapshots:]

            if self._jsonl_path is not None:
                self._write_jsonl(snapshot)

            return snapshot

        except (HTTPError, URLError, OSError) as exc:
            elapsed = (time.monotonic() - monotonic_start) * 1000
            logger.warning(
                "Spread collection failed (%s) after %.1fms: %s",
                symbol, elapsed, exc,
            )
            return None
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse tick data for %s: %s", symbol, exc)
            return None

    def _write_jsonl(self, snapshot: MarketSnapshot) -> None:
        """Append a snapshot to the JSONL output file."""
        try:
            with self._jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot.to_dict(), default=str) + "\n")
        except OSError as exc:
            logger.warning("Failed to write JSONL: %s", exc)

    def run_collection(
        self,
        client_base_url: str,
        symbol: str,
        interval_seconds: float = 1.0,
        duration_seconds: float = 0.0,
    ) -> None:
        """
        Start background collection in a daemon thread.

        Args:
            client_base_url: Bridge base URL.
            symbol: Instrument symbol.
            interval_seconds: Time between snapshots.
            duration_seconds: 0 = run indefinitely until stop() called.
        """
        if self._collection_thread is not None and self._collection_thread.is_alive():
            logger.warning("Collection thread already running")
            return

        self._stop_event.clear()

        def _loop() -> None:
            monotonic_start = time.monotonic()
            while not self._stop_event.is_set():
                self.collect_once(client_base_url, symbol)
                # Use monotonic sleep in short chunks for responsive stop
                sleep_end = time.monotonic() + interval_seconds
                while not self._stop_event.is_set() and time.monotonic() < sleep_end:
                    remaining = sleep_end - time.monotonic()
                    time.sleep(min(0.1, max(0, remaining)))

                if duration_seconds > 0:
                    elapsed = time.monotonic() - monotonic_start
                    if elapsed >= duration_seconds:
                        break

        self._collection_thread = threading.Thread(target=_loop, daemon=True)
        self._collection_thread.start()
        logger.info(
            "Started spread collection for %s (interval=%.1fs, duration=%.1fs)",
            symbol, interval_seconds, duration_seconds,
        )

    def stop(self) -> None:
        """Signal the collection thread to stop."""
        self._stop_event.set()
        if self._collection_thread is not None:
            self._collection_thread.join(timeout=5.0)
            self._collection_thread = None
        logger.info("Spread collection stopped")

    def get_snapshots(self) -> list[MarketSnapshot]:
        """Return a copy of stored snapshots."""
        with self._lock:
            return list(self._snapshots)

    def get_spread_distribution(self) -> np.ndarray:
        """Return numpy array of recent spread_pips values."""
        with self._lock:
            if not self._snapshots:
                return np.array([], dtype=float)
            return np.array([s.spread_pips for s in self._snapshots], dtype=float)

    def get_percentiles(self) -> dict[str, float]:
        """Return dict of P50/P75/P90/P95/P99 for spread_pips."""
        from nestquant.production.monitoring.percentiles import compute_percentiles

        dist = self.get_spread_distribution()
        if len(dist) == 0:
            return {
                "P50": float("nan"),
                "P75": float("nan"),
                "P90": float("nan"),
                "P95": float("nan"),
                "P99": float("nan"),
                "count": 0,
            }

        result = compute_percentiles(dist)
        return {
            "P50": result.p50.value,
            "P75": result.p75.value,
            "P90": result.p90.value,
            "P95": result.p95.value,
            "P99": result.p99.value,
            "count": result.count,
        }

    def clear(self) -> None:
        """Clear stored snapshots."""
        with self._lock:
            self._snapshots.clear()
