"""Z-Score Research Engine — Cost Model."""
from __future__ import annotations

from zscore.contracts import CostBreakdown, CostModel

# Default spread configuration (pips)
DEFAULT_SPREADS: dict[str, float] = {
    'EUR/USD': 1.0, 'GBP/USD': 1.6, 'USD/JPY': 1.0,
    'USD/CHF': 1.2, 'AUD/USD': 1.2, 'NZD/USD': 1.6,
    'EUR/GBP': 1.6, 'EUR/JPY': 1.9, 'GBP/JPY': 3.0,
    'AUD/JPY': 1.9, 'NZD/JPY': 1.9, 'EUR/AUD': 2.6,
    'GBP/AUD': 3.9, 'AUD/NZD': 2.0, 'USD/CAD': 1.5,
    'CAD/CHF': 1.8, 'EUR/CHF': 1.5, 'GBP/CHF': 2.6,
    'AUD/CHF': 2.0, 'NZD/CHF': 2.6,
}


def compute_costs(
    direction: int,
    entry_price: float,
    exit_price: float,
    pip: float,
    pv: float,
    lot_size: float,
    cost_model: CostModel,
) -> CostBreakdown:
    """Compute all execution costs for a trade.

    Args:
        direction: 1 for long, -1 for short
        entry_price: fill price (already includes spread + slippage)
        exit_price: exit fill price (already includes spread + slippage)
        pip: pip size for the pair
        pv: pip value per lot in USD
        lot_size: position size in lots
        cost_model: cost configuration

    Returns:
        CostBreakdown with individual and total costs
    """
    spread_cost = cost_model.spread_pips * pv * lot_size
    commission_cost = cost_model.commission_per_lot * lot_size * 2  # both sides
    slippage_cost = cost_model.slippage_pips * pv * lot_size

    total_cost = spread_cost + commission_cost + slippage_cost

    return CostBreakdown(
        spread_cost=spread_cost,
        commission_cost=commission_cost,
        slippage_cost=slippage_cost,
        total_cost=total_cost,
    )


def apply_spread_to_entry(
    mid_price: float,
    direction: int,
    spread_pips: float,
    pip: float,
    slippage_pips: float,
) -> float:
    """Adjust entry price for spread and slippage.

    For longs: entry = mid + (spread/2 + slippage) * pip
    For shorts: entry = mid - (spread/2 + slippage) * pip
    """
    adjustment = (spread_pips * 0.5 + slippage_pips) * pip
    if direction == 1:
        return mid_price + adjustment
    else:
        return mid_price - adjustment


def apply_spread_to_exit(
    mid_price: float,
    direction: int,
    spread_pips: float,
    pip: float,
    slippage_pips: float,
) -> float:
    """Adjust exit price for spread and slippage.

    For longs: exit = mid - (spread/2 + slippage) * pip
    For shorts: exit = mid + (spread/2 + slippage) * pip
    """
    adjustment = (spread_pips * 0.5 + slippage_pips) * pip
    if direction == 1:
        return mid_price - adjustment
    else:
        return mid_price + adjustment


def break_even_slippage(
    gross_pnl_per_unit: float,
    spread_pips: float,
    commission_per_lot: float,
    pip: float,
    pv: float,
    lot_size: float,
) -> float:
    """Compute the slippage (pips) at which expectancy becomes zero.

    gross_pnl_per_unit * pv * lot_size = spread_cost + commission + slippage_cost
    slippage_pips = (gross_pnl * lot - spread_cost - commission) / (pv * lot)
    """
    spread_cost = spread_pips * pv * lot_size
    commission = commission_per_lot * lot_size * 2
    remaining = gross_pnl_per_unit * pv * lot_size - spread_cost - commission
    if remaining <= 0:
        return 0.0
    return remaining / (pv * lot_size)
