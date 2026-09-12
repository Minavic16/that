"""
NestQuant S8.6.2 — Decision Engine (Layer 4)
==============================================

Combines monitoring classifications into trading decisions.

KEY PRINCIPLE:
    Hard safety limits bypass statistical classification.
    Statistical anomalies alone should NOT trigger hard halts.

DECISION HIERARCHY:
    1. Hard safety limits → HALT (immediate, no override)
    2. Infrastructure failure → HALT
    3. Multiple extreme statistical anomalies → INVESTIGATE / REDUCE
    4. Single statistical anomaly → LOG / MONITOR
    5. Normal → ALLOW TRADING
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from nestquant.production.monitoring.architecture import MetricState, MonitoringClassification


# ─────────────────────────────────────────────────────────────────────
# Decision Types
# ─────────────────────────────────────────────────────────────────────

class DecisionAction(Enum):
    """What the decision engine recommends."""
    ALLOW = "ALLOW"
    MONITOR = "MONITOR"
    INVESTIGATE = "INVESTIGATE"
    REDUCE_RISK = "REDUCE_RISK"
    BLOCK_ENTRIES = "BLOCK_ENTRIES"
    HALT = "HALT"


class DecisionSource(Enum):
    """What triggered the decision."""
    HARD_SAFETY = "HARD_SAFETY"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    STATISTICAL = "STATISTICAL"
    COMBINED = "COMBINED"
    NONE = "NONE"


@dataclass
class Decision:
    """A trading decision from the decision engine."""
    action: DecisionAction
    source: DecisionSource
    reason: str
    metrics_involved: list[str] = field(default_factory=list)
    is_provisional: bool = True
    details: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────
# Hard Safety Limits
# ─────────────────────────────────────────────────────────────────────

@dataclass
class HardSafetyLimits:
    """
    Prop-firm and infrastructure safety limits.
    These bypass ALL statistical classification.
    If triggered, trading halts immediately.
    """
    max_drawdown_pct: float = 10.0
    max_daily_loss_pct: float = 5.0
    max_position_size_lots: float = 0.20
    max_open_trades: int = 3
    max_total_exposure_lots: float = 1.0

    def check(
        self,
        current_dd_pct: float,
        daily_pnl_pct: float,
        open_trades: int,
        total_exposure_lots: float,
    ) -> Optional[Decision]:
        """Check hard safety limits. Returns Decision if breached."""
        violations = []

        if current_dd_pct >= self.max_drawdown_pct:
            violations.append(
                f"DD {current_dd_pct:.1f}% >= limit {self.max_drawdown_pct:.1f}%"
            )

        if daily_pnl_pct <= -self.max_daily_loss_pct:
            violations.append(
                f"Daily loss {daily_pnl_pct:.1f}% >= limit -{self.max_daily_loss_pct:.1f}%"
            )

        if open_trades >= self.max_open_trades:
            violations.append(
                f"Open trades {open_trades} >= limit {self.max_open_trades}"
            )

        if total_exposure_lots >= self.max_total_exposure_lots:
            violations.append(
                f"Exposure {total_exposure_lots:.2f} lots >= limit {self.max_total_exposure_lots}"
            )

        if violations:
            return Decision(
                action=DecisionAction.HALT,
                source=DecisionSource.HARD_SAFETY,
                reason="; ".join(violations),
                is_provisional=False,
                details={
                    "current_dd_pct": current_dd_pct,
                    "daily_pnl_pct": daily_pnl_pct,
                    "open_trades": open_trades,
                    "total_exposure_lots": total_exposure_lots,
                },
            )
        return None


# ─────────────────────────────────────────────────────────────────────
# Decision Engine
# ─────────────────────────────────────────────────────────────────────

@dataclass
class DecisionEngine:
    """
    Layer 4: Combines hard safety limits and statistical classifications
    into trading decisions.

    Decision hierarchy:
        1. Hard safety limits → HALT
        2. Infrastructure failure → HALT
        3. Multiple extreme anomalies → INVESTIGATE / REDUCE
        4. Single anomaly → MONITOR
        5. Normal → ALLOW
    """
    safety: HardSafetyLimits = field(default_factory=HardSafetyLimits)

    def decide(
        self,
        classification: MonitoringClassification,
        current_dd_pct: float = 0.0,
        daily_pnl_pct: float = 0.0,
        open_trades: int = 0,
        total_exposure_lots: float = 0.0,
        infrastructure_ok: bool = True,
    ) -> Decision:
        """
        Make a trading decision based on all available information.

        This is the SINGLE entry point for all trading decisions.
        """
        # 1. Hard safety limits (bypass everything)
        safety_decision = self.safety.check(
            current_dd_pct, daily_pnl_pct, open_trades, total_exposure_lots
        )
        if safety_decision is not None:
            return safety_decision

        # 2. Infrastructure failure
        if not infrastructure_ok:
            return Decision(
                action=DecisionAction.HALT,
                source=DecisionSource.INFRASTRUCTURE,
                reason="Infrastructure failure detected",
                is_provisional=False,
            )

        # 3. Statistical anomalies
        extremes = [
            m for m in classification.metrics
            if m.state == MetricState.EXTREME
        ]
        warnings = [
            m for m in classification.metrics
            if m.state == MetricState.WARNING
        ]

        # Multiple extreme anomalies → investigate/reduce
        if len(extremes) >= 2:
            return Decision(
                action=DecisionAction.REDUCE_RISK,
                source=DecisionSource.STATISTICAL,
                reason=f"{len(extremes)} extreme statistical anomalies",
                metrics_involved=[m.metric_name for m in extremes],
                is_provisional=True,
                details={
                    "extreme_metrics": [m.metric_name for m in extremes],
                    "warning_metrics": [m.metric_name for m in warnings],
                },
            )

        # Single extreme → investigate
        if len(extremes) == 1:
            return Decision(
                action=DecisionAction.INVESTIGATE,
                source=DecisionSource.STATISTICAL,
                reason=f"1 extreme statistical anomaly: {extremes[0].metric_name}",
                metrics_involved=[extremes[0].metric_name],
                is_provisional=True,
            )

        # Multiple warnings → monitor closely
        if len(warnings) >= 2:
            return Decision(
                action=DecisionAction.MONITOR,
                source=DecisionSource.STATISTICAL,
                reason=f"{len(warnings)} warning-level anomalies",
                metrics_involved=[m.metric_name for m in warnings],
                is_provisional=True,
            )

        # Single warning or normal
        if len(warnings) == 1:
            return Decision(
                action=DecisionAction.MONITOR,
                source=DecisionSource.STATISTICAL,
                reason=f"1 warning-level anomaly: {warnings[0].metric_name}",
                metrics_involved=[warnings[0].metric_name],
                is_provisional=True,
            )

        # All normal
        return Decision(
            action=DecisionAction.ALLOW,
            source=DecisionSource.NONE,
            reason="All metrics within normal range",
            is_provisional=False,
        )
