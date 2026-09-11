"""
Kill switch for shadow mode — S7 execution reality (hard stop).

Shadow must stop generating signals immediately when the switch is active,
emit an infrastructure event, and exit with a non-zero status that the
health check interprets as FAILED. The switch is polled per bar.

File-based so an operator (or a monitor) can trigger it without process
coordination. Path defaults to <log_dir>/KILL and also honors the legacy
/tmp/nestquant_shadow_kill if present.

No broker interaction here — this is research safety, not trade liquidation
(the latter lives in the live executor, out of scope for shadow).
"""

from __future__ import annotations

from pathlib import Path


DEFAULT_KILL_PATHS = [
    Path("/tmp/nestquant_shadow_kill"),
]


class KillSwitch:
    """Pollable kill switch. Activation is sticky until explicitly cleared."""

    def __init__(self, primary_path: str | Path = "logs/shadow/KILL") -> None:
        self.primary = Path(primary_path)
        self._forced = False  # in-memory latch for tests

    def is_active(self) -> bool:
        if self._forced:
            return True
        if self.primary.exists():
            return True
        for p in DEFAULT_KILL_PATHS:
            if p.exists():
                return True
        return False

    def trigger(self, reason: str = "") -> None:
        """Programmatically engage the switch and create the sentinel file."""
        self._forced = True
        self.primary.parent.mkdir(parents=True, exist_ok=True)
        self.primary.write_text(f"kill: {reason}\n" if reason else "kill\n")

    def clear(self) -> None:
        """Clear both in-memory and file sentinels."""
        self._forced = False
        for p in [self.primary, *DEFAULT_KILL_PATHS]:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    def path(self) -> Path:
        return self.primary
