# Z-Score Research Engine — Regime Research Design

## Two Independent Dimensions

Regime classification has two orthogonal dimensions:

1. **Trend** — direction and strength of price movement
2. **Volatility** — magnitude of price fluctuations

Each dimension is classified independently.
A trade's regime is the combination: e.g., `strong_trend + low_vol`.

---

## A. Causal Regime State (Available to Strategy)

These classifications use ONLY data available at timestamp t.
They can be used in real-time trading decisions.

### Trend Classification

Based on distance from EMA-200 (4h timeframe, forward-filled):

| Label | Condition | Description |
|-------|-----------|-------------|
| `near_ema200` | \|dist\| < 0.1% | Price is very close to EMA-200 |
| `weak_trend` | 0.1% <= \|dist\| < 0.3% | Moderate trend |
| `strong_trend` | \|dist\| >= 0.3% | Strong directional move |

### Volatility Classification

Based on ATR-14 percentage, using an **expanding window**:

| Label | Condition | Description |
|-------|-----------|-------------|
| `low_vol` | ATR percentile <= 25th | Unusually quiet market |
| `mid_vol` | 25th < percentile < 75th | Normal volatility |
| `high_vol` | 75th <= percentile < 95th | Elevated volatility |
| `extreme_vol` | percentile >= 95th | Crisis-level volatility |
| `unknown` | < 200 bars of history | Insufficient data |

**Expanding window implementation:**

```python
def classify_vol_regime_causal(atr_pct_arr, bar_idx, min_history=200):
    """At bar_idx, use ONLY atr_pct_arr[:bar_idx] for percentiles."""
    if bar_idx >= len(atr_pct_arr): return 'unknown'
    atr = atr_pct_arr[bar_idx]
    if np.isnan(atr): return 'unknown'
    history = atr_pct_arr[:bar_idx]           # <-- causal: no future
    valid = history[~np.isnan(history)]
    if len(valid) < min_history: return 'unknown'
    p25 = np.percentile(valid, 25)
    p75 = np.percentile(valid, 75)
    p95 = np.percentile(valid, 95)
    if atr <= p25: return 'low_vol'
    elif atr >= p95: return 'extreme_vol'
    elif atr >= p75: return 'high_vol'
    else: return 'mid_vol'
```

---

## B. Retrospective Research Labels (Analysis Only)

These labels use full-sample information for post-hoc analysis.
They are NEVER available to the strategy at decision time.

### Full-Sample Volatility (for comparison)

```python
def classify_vol_regime_fullsample(atr_pct_arr, bar_idx):
    """Uses ALL data (look-ahead bias). For comparison only."""
    atr = atr_pct_arr[bar_idx]
    valid = atr_pct_arr[~np.isnan(atr_pct_arr)]  # <-- includes future
    # ... same percentile logic
```

### Regime Transition Detection (research)

Detect when regime changes from one state to another.
This is retrospective — the transition is only known after it occurs.

```python
@dataclass
class RegimeTransition:
    pair: str
    timestamp: pd.Timestamp
    from_regime: RegimeState
    to_regime: RegimeState
    duration_bars: int              # how long the previous regime lasted
```

---

## Regime × Year Matrix (Analysis)

For each regime combination, report yearly performance:

```
           2018    2019    2020    2021    2022    2023    2024    2025
low_vol    PF=x    PF=x    PF=x    PF=x    PF=x    PF=x    PF=x    PF=x
mid_vol    PF=x    PF=x    PF=x    PF=x    PF=x    PF=x    PF=x    PF=x
high_vol   PF=x    PF=x    PF=x    PF=x    PF=x    PF=x    PF=x    PF=x
```

This reveals whether the edge is regime-dependent or robust.

---

## Causality Test for Regime

For any regime classifier at timestamp t:

1. Compute regime at t using original data
2. Modify data strictly after t (e.g., change tomorrow's prices)
3. Recompute regime at t
4. Assert regime at t is unchanged

This must be tested for:
- Trend classification (EMA-based — inherently causal if EMA is causal)
- Volatility classification (expanding window — must be verified)
- Any future regime features (e.g., rolling regime stability)
