"""
Shadow runner — orchestrates the S7 SHADOW pipeline.

Mode: SHADOW ONLY. No broker adapter is ever instantiated, no order is
ever sent. Intended orders are logged to JSONL for later reconciliation.

The runner is intentionally single-threaded and deterministic. It loads
historical bars via DataLoader, replays them bar-by-bar with strict
causality, and on each bar:

  1. Validates the bar (DataValidation helpers)
  2. Logs a §3.5 bar record
  3. Generates a shadow signal (Variant B) and, if BUY/SELL, logs §3.1
     and a shadow intended-order (§3.2 SHADOW)
  4. Advances shadow position lifecycle (SL/TP/MAX_HOLD) if tracking
  5. Updates health, checks kill switch, persists state

Restart/recovery: on startup, `ShadowState` is loaded; bars at or before
`last_bar[pair]` are skipped (no duplicate signals). Kill switch halts
the loop and emits an infrastructure event.

No MT5 imports. No network in historical replay.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from nestquant.data.loader import DataLoader
from nestquant.data.validation import (
    validate_data_quality,
    validate_duplicates,
    validate_gaps,
    validate_ohlc_integrity,
    validate_timestamps,
)
from nestquant.execution.shadow.health import HealthMonitor
from nestquant.execution.shadow.kill_switch import KillSwitch
from nestquant.execution.shadow.logger import ShadowLogger
from nestquant.execution.shadow.signal_generator import (
    BARS_PER_DAY_4H,
    MAX_HOLD_DAYS,
    ShadowCausalSignalGenerator,
)
from nestquant.execution.shadow.state import ShadowState


def _pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001


@dataclass
class ShadowPosition:
    """Minimal shadow position for lifecycle logging."""

    signal_id: str
    pair: str
    direction: str  # BUY/SELL
    entry_price: float
    sl: float
    tp: float
    entry_idx: int
    entry_timestamp: str
    max_hold_bars: int = MAX_HOLD_DAYS * BARS_PER_DAY_4H
    breakeven_ratio: float = 0.8  # informational only in this MVP

    def check_exit(
        self,
        bar_idx: int,
        open_: float,
        high: float,
        low: float,
        close: float,
    ) -> Optional[tuple[str, float]]:
        """Return (exit_reason, exit_price) if this bar should close."""
        held = bar_idx - self.entry_idx
        if held >= self.max_hold_bars:
            return ("MAX_HOLD", float(close))
        if self.direction == "BUY":
            if low <= self.sl:
                return ("SL", float(self.sl))
            if high >= self.tp:
                return ("TP", float(self.tp))
        else:
            if high >= self.sl:
                return ("SL", float(self.sl))
            if low <= self.tp:
                return ("TP", float(self.tp))
        return None


@dataclass
class ShadowRunSummary:
    run_id: str
    pairs: list[str]
    bars_processed: int
    signals_emitted: int
    shadow_positions_opened: int
    shadow_positions_closed: int
    start_wall_iso: str
    end_wall_iso: str
    elapsed_seconds: float
    fidelity: Optional[dict[str, Any]] = None
    health: Optional[dict[str, Any]] = None
    state_path: Optional[str] = None
    log_dir: Optional[str] = None


class ShadowRunner:
    """Historical-replay shadow runner (no live broker)."""

    def __init__(
        self,
        *,
        pairs: Optional[list[str]] = None,
        timeframe: str = "4h",
        data_dir: Optional[str] = None,
        log_dir: str | Path = "logs/shadow",
        state_path: Optional[str | Path] = None,
        kill_switch_path: Optional[str | Path] = None,
        spread_map: Optional[dict[str, float]] = None,
        limit_bars: Optional[int] = None,  # for smoke tests: cap per pair
        enable_lifecycle: bool = True,
    ) -> None:
        self.timeframe = timeframe
        self.data_dir = data_dir
        self.log_dir = Path(log_dir)
        self.state_path = Path(state_path) if state_path else self.log_dir / "state.json"
        self.limit_bars = limit_bars
        self.enable_lifecycle = enable_lifecycle

        self.logger = ShadowLogger(log_dir=self.log_dir)
        self.health = HealthMonitor()
        self.kill_switch = KillSwitch(primary_path=kill_switch_path or (self.log_dir / "KILL"))
        self.state = ShadowState(path=self.state_path)
        self.generator = ShadowCausalSignalGenerator(spread_pips_map=spread_map)
        self.loader = DataLoader(data_dir=data_dir)

        # Default to S7 20-pair universe if not supplied
        if pairs is None:
            # Prefer the S6C-validated universe (20) over the broader 28
            import json as _json

            s6c_path = Path("research_data/s6c/S6C_causal_swing_results.json")
            if s6c_path.exists():
                try:
                    raw = _json.loads(s6c_path.read_text())
                    pairs = list(raw.get("config", {}).get("pairs_loaded", []))
                except Exception:
                    pairs = None
            if not pairs:
                from nestquant.config.settings import get_config

                pairs = list(get_config().universe.all_pairs[:20])
        self.pairs = list(pairs)

        # Shadow positions keyed by pair (at most one open per pair in MVP)
        self._open: dict[str, ShadowPosition] = {}

    def _bars_for_pair(self, pair: str) -> Optional[pd.DataFrame]:
        df = self.loader.load_pair(pair, timeframe=self.timeframe)
        if df is None or len(df) == 0:
            return None
        df = df.sort_index()
        # DataLoader returns tz-aware UTC; runner normalizes to UTC ISO via logger
        if df.index.tz is None:
            df.index = df.index.tz_localize(timezone.utc)
        else:
            df.index = df.index.tz_convert(timezone.utc)
        if self.limit_bars and len(df) > self.limit_bars:
            df = df.iloc[-self.limit_bars :]
        return df

    def run(self) -> ShadowRunSummary:
        t_wall_start = time.perf_counter()
        start_iso = datetime.now(timezone.utc).isoformat()
        self.logger.log_infrastructure("STARTUP", f"shadow start run_id={self.state.run_id} pairs={self.pairs} tf={self.timeframe}")
        self.health.heartbeat()

        total_bars = 0
        total_signals = 0
        opened = 0
        closed = 0

        # Pre-load all pair DataFrames to handle stale detection honestly
        pair_dfs: dict[str, pd.DataFrame] = {}
        for pair in self.pairs:
            df = self._bars_for_pair(pair)
            if df is None:
                self.logger.log_infrastructure("ERROR", f"no data for {pair}", impact="MISSED_SIGNAL")
                self.health.record_gap(f"no data {pair}")
                continue
            pair_dfs[pair] = df

        # Per-pair replay (chronological within each pair; cross-pair
        # interleaving is not required for fidelity since signals are
        # per-pair independent).
        for pair, df in pair_dfs.items():
            # Validate full frame once (cheap) for gaps/duplicates
            # FX 4h has expected weekend gaps (~48h = 12× median); use generous multiplier
            for chk in (validate_timestamps(df), validate_duplicates(df), validate_gaps(df, max_gap_multiplier=20.0)):
                if not chk.passed:
                    self.health.record_gap(f"{pair} {chk.check_name}: {chk.details}")
                    self.logger.log_infrastructure("ERROR", f"{pair} {chk.details}", impact="NO_IMPACT")

            # Resume from state if present
            resume_ts = self.state.last_bar.get(pair)
            start_idx = 0
            if resume_ts:
                try:
                    # Find first index > resume_ts
                    resume_dt = pd.Timestamp(resume_ts)
                    if resume_dt.tzinfo is None:
                        resume_dt = resume_dt.tz_localize(timezone.utc)
                    else:
                        resume_dt = resume_dt.tz_convert(timezone.utc)
                    # df index is tz-aware UTC
                    mask = df.index > resume_dt
                    if not mask.any():
                        continue  # already fully processed
                    start_idx = int(mask.argmax())  # first True
                except Exception:
                    start_idx = 0

            # Warmup bars before first signal is evaluable
            warmup = self.generator.lookback * 2 + self.generator.atr_period + 2
            loop_start = max(start_idx, warmup)

            for i in range(loop_start, len(df) + 1):
                # Kill switch poll per bar
                if self.kill_switch.is_active():
                    self.health.set_kill_switch(True)
                    self.logger.log_infrastructure("ERROR", "kill switch active — halting", impact="MISSED_SIGNAL", resolution="manual clear required")
                    break

                prefix = df.iloc[:i]
                bar_ts = prefix.index[-1]
                bar_ts_iso = bar_ts.isoformat()

                # Data integrity per-bar (cheap OHLC check on the prefix tail)
                # Only validate the current bar's OHLC, not the whole history each time
                bar_row = prefix.iloc[-1]
                ohlc_ok = (
                    bar_row["high"] >= max(bar_row["open"], bar_row["close"])
                    and bar_row["low"] <= min(bar_row["open"], bar_row["close"])
                    and bar_row["high"] >= bar_row["low"]
                )
                if not ohlc_ok:
                    self.health.record_integrity_violation(f"{pair} {bar_ts_iso} ohlc invalid")
                    self.logger.log_infrastructure("ERROR", f"{pair} {bar_ts_iso} ohlc violation", impact="NO_IMPACT")
                    self.state.mark_bar(pair, bar_ts_iso)
                    continue

                # Log bar (§3.5) — compute ATR/swing context for observability if possible
                try:
                    from nestquant.indicators.atr import calculate_atr
                    from nestquant.indicators.swing import swing_high_series, swing_low_series

                    atr_s = calculate_atr(prefix, self.generator.atr_period)
                    sh_s = swing_high_series(prefix, self.generator.lookback)
                    sl_s = swing_low_series(prefix, self.generator.lookback)
                    atr_val = float(atr_s.iloc[-1]) if len(atr_s) else None
                    sh_val = float(sh_s.iloc[-1]) if len(sh_s) else None
                    sl_val = float(sl_s.iloc[-1]) if len(sl_s) else None
                except Exception:
                    atr_val = sh_val = sl_val = None

                spread = self.generator._spread_for(pair)
                # Log bar
                self.logger.log_bar(
                    pair=pair,
                    bar_timestamp=bar_ts_iso,
                    open_=float(bar_row["open"]),
                    high=float(bar_row["high"]),
                    low=float(bar_row["low"]),
                    close=float(bar_row["close"]),
                    volume=float(bar_row.get("volume", 0) or 0),
                    spread=float(spread),
                    atr_14=atr_val if atr_val is not None and atr_val == atr_val else None,  # NaN guard
                    swing_high=sh_val if sh_val is not None and sh_val == sh_val else None,
                    swing_low=sl_val if sl_val is not None and sl_val == sl_val else None,
                )
                total_bars += 1
                self.health.record_bar(bar_ts_iso, latency_ms=None)
                self.health.heartbeat()

                # Lifecycle: check open position exit BEFORE new signal (avoid same-bar flip)
                if self.enable_lifecycle and pair in self._open:
                    pos = self._open[pair]
                    outcome = pos.check_exit(
                        bar_idx=i - 1,
                        open_=float(bar_row["open"]),
                        high=float(bar_row["high"]),
                        low=float(bar_row["low"]),
                        close=float(bar_row["close"]),
                    )
                    if outcome:
                        reason, exit_price = outcome
                        gross = (
                            (exit_price - pos.entry_price) / _pip_size(pair)
                            if pos.direction == "BUY"
                            else (pos.entry_price - exit_price) / _pip_size(pair)
                        )
                        held = (i - 1) - pos.entry_idx
                        self.logger.log_lifecycle(
                            signal_id=pos.signal_id,
                            symbol=pair,
                            exit_reason=reason,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            gross_pnl_pips=float(gross),
                            hold_bars=int(held),
                            hold_hours=float(held * 4.0),
                        )
                        del self._open[pair]
                        closed += 1

                # Generate signal for this bar close
                t_gen = time.perf_counter()
                rec = self.generator.generate(prefix, pair)
                gen_ms = (time.perf_counter() - t_gen) * 1000.0

                # Record generation latency in health (even for NEUTRAL, useful for perf)
                self.health._latencies.append(gen_ms) if gen_ms == gen_ms else None  # NaN guard

                if rec is not None:
                    # Block real order submission: shadow only
                    self.logger.log_signal(rec)
                    pip = _pip_size(pair)
                    # Intended order (shadow, not sent)
                    self.logger.log_intended_order(
                        signal_id=rec.signal_id,
                        symbol=pair,
                        direction=rec.direction,
                        volume=0.01,  # shadow placeholder; real sizing lives in Risk layer
                        requested_price=rec.expected_entry,
                        sl=rec.expected_sl,
                        tp=rec.expected_tp,
                        spread_at_submission=rec.spread_at_signal,
                    )
                    total_signals += 1
                    self.health.record_signal(latency_ms=gen_ms)
                    self.state.inc("signals_emitted", 1)

                    # Open shadow position if none open (max 1 per pair in MVP)
                    if self.enable_lifecycle and pair not in self._open:
                        self._open[pair] = ShadowPosition(
                            signal_id=rec.signal_id,
                            pair=pair,
                            direction=rec.direction,
                            entry_price=rec.expected_entry,
                            sl=rec.expected_sl,
                            tp=rec.expected_tp,
                            entry_idx=i - 1,
                            entry_timestamp=rec.timestamp,
                        )
                        opened += 1

                self.state.mark_bar(pair, bar_ts_iso)
                self.state.inc("bars_processed", 1)

                # Periodic state flush (every 50 bars)
                if total_bars % 50 == 0:
                    self.state.save()

            # End of pair loop — flush state
            self.state.save()
            if self.kill_switch.is_active():
                break

        elapsed = time.perf_counter() - t_wall_start
        end_iso = datetime.now(timezone.utc).isoformat()
        self.state.save()
        self.logger.log_infrastructure(
            "SHUTDOWN",
            f"shadow run {self.state.run_id} done bars={total_bars} signals={total_signals} elapsed={elapsed:.1f}s",
        )

        health_snap = self.health.snapshot(historical=True).to_dict()
        # Attach to infrastructure log as well
        self.logger.log_infrastructure(
            "HEALTH",
            f"health snapshot status={health_snap['status']} bars={health_snap['bars_processed']} signals={health_snap['signals_emitted']} gaps={health_snap['gaps_detected']}",
        )

        return ShadowRunSummary(
            run_id=self.state.run_id,
            pairs=list(pair_dfs.keys()),
            bars_processed=total_bars,
            signals_emitted=total_signals,
            shadow_positions_opened=opened,
            shadow_positions_closed=closed,
            start_wall_iso=start_iso,
            end_wall_iso=end_iso,
            elapsed_seconds=elapsed,
            health=health_snap,
            state_path=str(self.state.path),
            log_dir=str(self.log_dir),
        )
