"""Identity utilities: run IDs, config hashes, git capture.

Git helpers follow research.experiment patterns (subprocess, fail-closed).
Config hashing follows the deterministic JSON+SHA256 pattern used by
core.configuration.experiment but is implemented locally to keep the research
provenance package free of production imports.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from datetime import UTC, datetime
from typing import Any, Mapping, Optional


def new_run_id(prefix: str = "run") -> str:
    """Unique, serializable, strategy-independent run identifier."""
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def get_git_commit(cwd: Optional[str] = None, timeout: float = 5.0) -> Optional[str]:
    """Return HEAD commit hash or None if unavailable. Never fabricates."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        if result.returncode == 0:
            out = result.stdout.strip()
            return out or None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_git_dirty(cwd: Optional[str] = None, timeout: float = 5.0) -> Optional[bool]:
    """Return True if dirty, False if clean, None if git status unavailable."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        if result.returncode == 0:
            return len(result.stdout.strip()) > 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def config_hash(obj: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Deterministic SHA-256 of a JSON-safe config mapping.

    Same configuration -> same hash.
      - None -> None
      - empty mapping {} -> deterministic hash of the empty mapping (not None)
    """
    if obj is None:
        return None
    try:
        canonical = canonical_json(dict(obj))
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
