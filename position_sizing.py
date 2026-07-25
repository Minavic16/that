"""
position_sizing.py — Position sizing with leverage-aware margin checks.

Standard FX position sizing rules:
    - 1 standard lot = CONTRACT_SIZE (= 100,000 base-currency units)
    - pip value per lot for USD account = pip × CONTRACT_SIZE × (USD / quote_ccy)

This module computes:
  1. Risk-based lot size (preserves strategy's risk-per-trade semantics).
  2. Required margin at given leverage and rejects if exceeds safety threshold.
  3. Cross-rate pip-value conversion to account currency (USD).

Pair format: "BASE/QUOTE" (e.g. "EUR/CHF", "USD/CHF", "GBP/JPY").
Rates must be forward prices (bid/ask neutral for sizing).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


# Account currency
ACCOUNT_CCY = "USD"
CONTRACT_SIZE = 100_000          # 1 lot = 100,000 base units

# Most common pip sizes
PIP_SIZE = {
    "JPY": 0.01,                 # 0.01 yen = 1 pip for JPY pairs
}
DEFAULT_PIP = 0.0001             # 0.0001 = 1 pip for non-JPY pairs

# Conversion rates: how much 1 unit of base/quote currency is worth in USD.
# These are populated at runtime from latest market quotes via _rate_lookup.


def pip_size_for_pair(pair: str) -> float:
    """Pip size for a pair (0.01 for JPY quotes, 0.0001 otherwise)."""
    base, quote = pair.split("/")
    if quote == "JPY" or base == "JPY":
        return PIP_SIZE["JPY"]
    return DEFAULT_PIP


@dataclass
class QuoteSnapshot:
    """Latest quotes used for currency conversion.

    `usd_to_ccy[X]` = how many X per 1 USD (i.e. USD/X rate). For X="USD": 1.0.
    We compute pip-value-in-USD by mapping any quote currency to USD
    using these rates.
    """
    # Map currency -> USD-per-1-unit (i.e. CCYUSD or inverse of USDCCY).
    # Example: usd_value["EUR"]=1.08 (1 EUR = 1.08 USD), usd_value["JPY"]=0.0067
    usd_value: dict[str, float]


def _build_default_snapshot() -> QuoteSnapshot:
    """Approximate fallback rates. Real engine should call update_rates()."""
    return QuoteSnapshot(usd_value={
        "USD": 1.0,
        "EUR": 1.08,
        "GBP": 1.26,
        "JPY": 0.0067,
        "CHF": 0.88,
        "CAD": 0.74,
        "AUD": 0.66,
        "NZD": 0.60,
    })


DEFAULT_SNAPSHOT = _build_default_snapshot()


def pip_value_per_lot(pair: str, snap: QuoteSnapshot | None = None) -> float:
    """Pip value per 1 standard lot, in account currency (USD).

    For pair BASE/QUOTE:
        pip_value = pip × CONTRACT_SIZE × (USD per unit of QUOTE)

    Examples (CONTRACT_SIZE = 100,000):
        EUR/USD, pip=0.0001 → 0.0001 × 100000 × 1.0 = $10.00 per lot
        USD/CHF, pip=0.0001 → 0.0001 × 100000 × (USD per CHF) = $11.00 per lot
        GBP/JPY, pip=0.01   → 0.01 × 100000  × (USD per JPY) = $670.00 per lot
        EUR/CHF, pip=0.0001 → 0.0001 × 100000 × (USD per CHF) = $11.00
    """
    if snap is None:
        snap = DEFAULT_SNAPSHOT
    base, quote = pair.split("/")
    pip = pip_size_for_pair(pair)
    usd_per_quote = snap.usd_value.get(quote, 1.0)
    return pip * CONTRACT_SIZE * usd_per_quote


def lot_size_by_risk(
    pair: str,
    sl_price_distance: float,
    risk_dollars: float,
    snap: QuoteSnapshot | None = None,
) -> float:
    """Risk-based lot size.

    lot = risk_dollars / (sl_distance_price × CONTRACT_SIZE × USD_per_quote)
    Equivalent: lot = risk_dollars / (sl_pips × pip_value_per_lot).

    Returns 0.0 if inputs invalid.
    """
    if sl_price_distance <= 0 or risk_dollars <= 0:
        return 0.0
    pip = pip_size_for_pair(pair)
    if snap is None:
        snap = DEFAULT_SNAPSHOT
    base, quote = pair.split("/")
    usd_per_quote = snap.usd_value.get(quote, 1.0)
    notional_per_lot = CONTRACT_SIZE * usd_per_quote  # USD notional for 1 lot
    loss_per_lot = sl_price_distance * (CONTRACT_SIZE / 1.0) * usd_per_quote
    # Simpler form:
    loss_per_lot = sl_price_distance / pip * pip_value_per_lot(pair, snap)
    lot = risk_dollars / loss_per_lot
    return max(0.0, lot)


def round_lot_to_step(lot: float, step: float = 0.01, min_lot: float = 0.01) -> float:
    """Round lot size to broker step (default 0.01)."""
    if lot < min_lot:
        return min_lot
    return round(lot / step) * step


def required_margin(
    pair: str,
    lot: float,
    leverage: int,
    snap: QuoteSnapshot | None = None,
) -> float:
    """Margin required to open position, in account currency (USD).

    margin = notional / leverage
    notional = lot × CONTRACT_SIZE × (USD per base ccy)
    """
    if snap is None:
        snap = DEFAULT_SNAPSHOT
    base, _ = pair.split("/")
    usd_per_base = snap.usd_value.get(base, 1.0)
    notional_usd = lot * CONTRACT_SIZE * usd_per_base
    return notional_usd / leverage


@dataclass
class SizingResult:
    """Output of compute_position_size."""
    ok: bool
    pair: str
    side: str
    risk_dollars: float
    sl_distance_price: float
    lot_size: float
    volume_units: int               # lot_size × 100000 (cTrader volume)
    pip_value_per_lot_usd: float
    notional_usd: float
    required_margin_usd: float
    available_margin_usd: float
    margin_pct: float                # required / available
    reject_reason: Optional[str] = None


def compute_position_size(
    pair: str,
    side: str,
    entry_price: float,
    sl_price: float,
    account_balance_usd: float,
    risk_pct: float,
    leverage: int = 100,
    margin_safety: float = 0.5,
    snap: QuoteSnapshot | None = None,
    lot_step: float = 0.01,
    min_lot: float = 0.01,
    max_lot: float | None = None,
    existing_margin_used: float = 0.0,
) -> SizingResult:
    """Full position-sizing with leverage/margin guard.

    Args:
        pair:          "EUR/USD", "GBP/JPY", etc.
        side:          "BUY" or "SELL".
        entry_price:   Expected entry price (or current market mid).
        sl_price:      Stop loss price.
        account_balance_usd: Account balance in USD.
        risk_pct:      Risk fraction per trade (e.g. 0.0075 = 0.75%).
        leverage:      Account leverage (e.g. 100 = 1:100).
        margin_safety: Reject if required margin > safety × available.
        snap:          Latest currency conversion rates.
        lot_step:      Broker's lot step (Pepperstone = 0.01).
        min_lot:       Broker's minimum lot.
        max_lot:       Optional max lot override.
        existing_margin_used: Margin already used by open positions (USD).

    Returns:
        SizingResult with lot/volume/margin info or rejection reason.
    """
    if snap is None:
        snap = DEFAULT_SNAPSHOT

    sl_distance = abs(entry_price - sl_price)
    risk_dollars = account_balance_usd * risk_pct

    raw_lot = lot_size_by_risk(pair, sl_distance, risk_dollars, snap)
    if raw_lot <= 0:
        return SizingResult(
            ok=False, pair=pair, side=side, risk_dollars=risk_dollars,
            sl_distance_price=sl_distance, lot_size=0.0, volume_units=0,
            pip_value_per_lot_usd=pip_value_per_lot(pair, snap),
            notional_usd=0.0, required_margin_usd=0.0,
            available_margin_usd=0.0, margin_pct=0.0,
            reject_reason="Invalid risk inputs or SL distance"
        )

    lot = round_lot_to_step(raw_lot, lot_step, min_lot)
    if max_lot is not None:
        lot = min(lot, max_lot)

    notional = lot * CONTRACT_SIZE * snap.usd_value.get(pair.split("/")[0], 1.0)
    req_margin = notional / leverage
    available = account_balance_usd * leverage - existing_margin_used
    margin_pct = req_margin / available if available > 0 else float("inf")

    reject = None
    if margin_pct > margin_safety:
        reject = f"Margin {margin_pct*100:.1f}% > safety {margin_safety*100:.0f}%"
    elif lot < min_lot:
        reject = f"Lot {lot} < min {min_lot}"
        lot = min_lot
    elif req_margin > available:
        reject = f"Required margin ${req_margin:.2f} > available ${available:.2f}"

    volume_units = int(lot * CONTRACT_SIZE)

    return SizingResult(
        ok=(reject is None),
        pair=pair, side=side, risk_dollars=risk_dollars,
        sl_distance_price=sl_distance, lot_size=lot, volume_units=volume_units,
        pip_value_per_lot_usd=pip_value_per_lot(pair, snap),
        notional_usd=notional, required_margin_usd=req_margin,
        available_margin_usd=available, margin_pct=margin_pct,
        reject_reason=reject,
    )
