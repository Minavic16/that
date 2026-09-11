"""
Persistent shadow state for restart/recovery — S7 §5.4 / §8.

State is a small JSON file written atomically (temp + rename) after each
processed bar (or batch). On restart, the runner resumes after the last
recorded bar timestamp per pair, so no bar is double-counted or skipped
without detection.

Schema:
  {
    "run_id": "s7-shadow-...",
    "created_at": "ISO8601",
    "updated_at": "ISO8601",
    "last_bar": {"EUR/USD": "2026-07-17T20:00:00+00:00", ...},
    "counters": {"bars_processed": 1234, "signals_emitted": 42}
  }
"""

from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ShadowState:
    def __init__(self, path: str | Path = "logs/shadow/state.json") -> None:
        self.path = Path(path)
        self.run_id: str = f"s7-shadow-{uuid.uuid4().hex[:8]}"
        self.created_at: str = _utc_now_iso()
        self.updated_at: str = self.created_at
        self.last_bar: dict[str, str] = {}
        self.counters: dict[str, int] = {"bars_processed": 0, "signals_emitted": 0}
        # Attempt to load existing state if present
        self._load_if_exists()

    def _load_if_exists(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
            self.run_id = raw.get("run_id", self.run_id)
            self.created_at = raw.get("created_at", self.created_at)
            self.updated_at = raw.get("updated_at", self.updated_at)
            self.last_bar = dict(raw.get("last_bar", {}))
            self.counters = dict(raw.get("counters", self.counters))
        except Exception:
            # Corrupt state → start fresh but keep old file for forensics
            try:
                self.path.rename(self.path.with_suffix(".corrupt.json"))
            except Exception:
                pass

    def mark_bar(self, pair: str, bar_timestamp_iso: str) -> None:
        self.last_bar[pair] = bar_timestamp_iso

    def inc(self, key: str, n: int = 1) -> None:
        self.counters[key] = int(self.counters.get(key, 0)) + n

    def save(self) -> None:
        self.updated_at = _utc_now_iso()
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_bar": dict(self.last_bar),
            "counters": dict(self.counters),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, dir=str(self.path.parent), encoding="utf-8"
        ) as tmp:
            json.dump(payload, tmp, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_bar": dict(self.last_bar),
            "counters": dict(self.counters),
            "path": str(self.path),
        }
