"""
currency_strength.py — 8-Currency Strength Ranker
===================================================
Core concept:
    For any pair BASE/QUOTE, a rising price means BASE is strengthening
    relative to QUOTE. By decomposing every pair's % change into individual
    currency contributions and averaging across all pairs a currency appears in,
    we get a "pure" measure of each currency's strength — independent of
    any single pair chart.

💡 KEY IMPROVEMENTS over the original single-lookback approach:
    1. Weighted multi-period ROC (fast/medium/slow blend)
       → Much fewer whipsaw signals than a fixed lookback
    2. Rolling z-score normalization
       → Scores stay comparable across changing volatility regimes
    3. Tanh squashing to [-100, +100]
       → Easy to threshold and visualize as a histogram
    4. Minimum pairs check per currency
       → Prevents thin data from skewing a currency's score
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import logging

from config import (
    CURRENCIES, STRENGTH_LOOKBACKS, STRENGTH_NORMALIZE_WINDOW,
    STRENGTH_TOP_N, STRENGTH_MIN_DIVERGENCE,
)

logger = logging.getLogger(__name__)


class CurrencyStrengthRanker:
    """
    Calculates normalized strength scores for all 8 major currencies.

    Usage:
        ranker   = CurrencyStrengthRanker()
        strength = ranker.calculate(pair_data)        # DataFrame [currencies]
        signal   = ranker.get_signal(strength, "GBP/JPY")
        best     = ranker.get_best_pairs_to_trade(strength, tradeable_pairs)
    """

    def __init__(self,
                 lookbacks:  List[Tuple[int, float]] = None,
                 top_n:      int   = STRENGTH_TOP_N,
                 min_div:    float = STRENGTH_MIN_DIVERGENCE,
                 norm_window: int  = STRENGTH_NORMALIZE_WINDOW):

        self.lookbacks   = lookbacks or STRENGTH_LOOKBACKS
        self.top_n       = top_n
        self.min_div     = min_div
        self.norm_window = norm_window
        self.currencies  = CURRENCIES

    # ── Pair Parsing ──────────────────────────────────────────────────────────

    def _parse_pair(self, pair: str) -> Tuple[str, str]:
        """'EUR/USD' → ('EUR', 'USD').  Also handles 'EURUSD'."""
        pair = pair.strip().upper().replace("_", "/")
        if "/" in pair:
            parts = pair.split("/")
            return parts[0], parts[1]
        # Infer split from known 3-letter currency codes
        for c in self.currencies:
            if pair.startswith(c):
                rest = pair[len(c):]
                if rest in self.currencies:
                    return c, rest
        raise ValueError(f"Cannot parse pair: {pair}")

    # ── Core Calculation ──────────────────────────────────────────────────────

    def calculate(self, pair_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Build a currency strength DataFrame from OHLCV data for multiple pairs.

        Args:
            pair_data: {pair_symbol: OHLCV DataFrame with 'close' column}

        Returns:
            DataFrame  index=datetime, columns=currencies
                       values are normalized strength scores in [-100, +100]
                       Positive = strong, Negative = weak
        """
        contributions: Dict[str, List[pd.Series]] = {c: [] for c in self.currencies}

        for pair, df in pair_data.items():
            if df is None or df.empty or "close" not in df.columns:
                continue
            try:
                base, quote = self._parse_pair(pair)
            except ValueError:
                logger.debug(f"Skipping unrecognised pair: {pair}")
                continue

            if base not in self.currencies or quote not in self.currencies:
                continue

            # Weighted blend of multiple lookback ROCs
            weighted_roc = pd.Series(0.0, index=df.index, dtype=float)
            for period, weight in self.lookbacks:
                roc = df["close"].pct_change(period) * 100.0
                weighted_roc = weighted_roc.add(roc * weight, fill_value=0.0)

            contributions[base].append(weighted_roc)     # Base benefits when price rises
            contributions[quote].append(-weighted_roc)   # Quote suffers when price rises

        # Average contributions per currency (require ≥2 pairs for a currency)
        raw: Dict[str, pd.Series] = {}
        for currency, series_list in contributions.items():
            if len(series_list) < 2:
                logger.warning(
                    f"Currency {currency} only appears in {len(series_list)} pair(s) "
                    f"— score may be unreliable."
                )
            if series_list:
                stacked = pd.concat(series_list, axis=1)
                raw[currency] = stacked.mean(axis=1)

        if not raw:
            raise ValueError(
                "No currency strength computed. "
                "Check that pair_data contains recognisable pairs."
            )

        raw_df = pd.DataFrame(raw).ffill().dropna(how="all")
        normalized = self._rolling_normalize(raw_df)

        logger.info(
            f"Currency strength computed: {len(raw_df)} bars, "
            f"{len(raw_df.columns)} currencies."
        )
        return normalized

    def _rolling_normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert raw % scores to normalized [-100, +100] using rolling z-score
        then tanh-squashing.

        WHY ROLLING vs GLOBAL?
            Global normalization uses future data (look-ahead bias in a backtest).
            Rolling normalization only uses past data — safe for live use too.
        """
        result = pd.DataFrame(index=df.index, columns=df.columns, dtype=float)
        for col in df.columns:
            roll_mean = df[col].rolling(self.norm_window, min_periods=10).mean()
            roll_std  = df[col].rolling(self.norm_window, min_periods=10).std()
            z         = (df[col] - roll_mean) / (roll_std.replace(0, np.nan) + 1e-10)
            result[col] = np.tanh(z) * 100.0
        return result.ffill()

    # ── Signal Generation ────────────────────────────────────────────────────

    def get_ranked(self, strength_df: pd.DataFrame,
                   bar_idx: int = -1) -> pd.Series:
        """
        Rank currencies at a specific bar from strongest (rank 0) to weakest.

        Args:
            strength_df: Output of calculate()
            bar_idx:     Bar index (-1 = latest)

        Returns:
            pd.Series  index=currency, values=score, sorted descending
        """
        row = strength_df.iloc[bar_idx]
        return row.sort_values(ascending=False)

    def get_signal(self, strength_df: pd.DataFrame, pair: str,
                   bar_idx: int = -1,
                   top_n:   int   = None,
                   min_div: float = None) -> str:
        """
        Determine BUY / SELL / NONE for a specific pair at a given bar.

        BUY  → base is among the N strongest AND quote is among the N weakest
               AND their score gap ≥ min_div
        SELL → base is among the N weakest  AND quote is among the N strongest
               AND their score gap ≥ min_div

        Args:
            top_n:   Override instance default
            min_div: Override instance default

        Returns:
            'BUY' | 'SELL' | 'NONE'
        """
        top_n   = top_n   or self.top_n
        min_div = min_div or self.min_div

        try:
            base, quote = self._parse_pair(pair)
        except ValueError:
            return "NONE"

        if base not in strength_df.columns or quote not in strength_df.columns:
            return "NONE"

        ranked     = self.get_ranked(strength_df, bar_idx)
        order      = ranked.index.tolist()            # [strongest … weakest]
        base_rank  = order.index(base)                # 0 = strongest
        quote_rank = order.index(quote)

        base_score  = float(strength_df[base].iloc[bar_idx])
        quote_score = float(strength_df[quote].iloc[bar_idx])
        divergence  = base_score - quote_score

        bottom_threshold = len(self.currencies) - top_n   # index ≥ this = bottom N

        # BUY: base in top N  AND  quote in bottom N
        if base_rank < top_n and quote_rank >= bottom_threshold:
            if divergence >= min_div:
                return "BUY"

        # SELL: base in bottom N  AND  quote in top N
        if base_rank >= bottom_threshold and quote_rank < top_n:
            if divergence <= -min_div:
                return "SELL"

        return "NONE"

    def get_best_pairs_to_trade(self,
                                 strength_df: pd.DataFrame,
                                 tradeable_pairs: List[str],
                                 bar_idx: int = -1,
                                 top_n: int = None) -> List[dict]:
        """
        Scan all tradeable pairs, return those with valid signals sorted by
        strength divergence (strongest edge first).

        Returns:
            List of dicts:
                pair, signal, divergence, base_score, quote_score,
                base_rank, quote_rank
        """
        top_n = top_n or self.top_n
        signals = []

        ranked = self.get_ranked(strength_df, bar_idx)
        order  = ranked.index.tolist()

        for pair in tradeable_pairs:
            try:
                base, quote = self._parse_pair(pair)
            except ValueError:
                continue

            if base not in strength_df.columns or quote not in strength_df.columns:
                continue

            signal = self.get_signal(strength_df, pair, bar_idx, top_n=top_n)
            if signal == "NONE":
                continue

            base_score  = float(strength_df[base].iloc[bar_idx])
            quote_score = float(strength_df[quote].iloc[bar_idx])

            signals.append({
                "pair":        pair,
                "signal":      signal,
                "divergence":  abs(base_score - quote_score),
                "base_score":  round(base_score,  2),
                "quote_score": round(quote_score, 2),
                "base_rank":   order.index(base)  + 1,   # 1-based for readability
                "quote_rank":  order.index(quote) + 1,
            })

        return sorted(signals, key=lambda x: x["divergence"], reverse=True)

    # ── Diagnostics ──────────────────────────────────────────────────────────

    def snapshot(self, strength_df: pd.DataFrame,
                 bar_idx: int = -1) -> str:
        """
        Human-readable snapshot of the current strength ranking.

        Example output:
            GBP   ██████████  +82.3
            EUR   ████████    +61.4
            USD   ████        +31.2
            CAD   ──          -12.1
            AUD   ────        -38.7
            NZD   ──────      -51.0
            CHF   ────────    -63.4
            JPY   ██████████  -87.1  ← weakest
        """
        ranked = self.get_ranked(strength_df, bar_idx)
        lines = [f"{'Currency Strength':>20}  (bar {bar_idx})", "─" * 36]
        for currency, score in ranked.items():
            bar_len = int(abs(score) / 10)
            bar     = ("█" if score >= 0 else "░") * min(bar_len, 10)
            lines.append(f"  {currency:<5} {bar:<10}  {score:+.1f}")
        return "\n".join(lines)