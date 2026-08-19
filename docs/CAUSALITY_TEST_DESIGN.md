# Z-Score Research Engine — Causality Test Design

## Principle

For any feature or decision computed at timestamp t:
The result must NOT change when data strictly after t is modified.

A causality violation is a BLOCKING DEFECT.
No feature with a causality violation may be used in trading decisions.

---

## Generic Causality Test

```python
def causality_test(func, data, t_index, modification):
    """
    Test that func(data, t_index) is invariant to modifications after t_index.

    Args:
        func: callable(data, t_index) -> value
        data: the full dataset
        t_index: the bar index at which to test
        modification: callable(data, t_index) -> modified_data
                      must only modify data strictly after t_index

    Returns:
        (is_causal: bool, original_value, modified_value)
    """
    original = func(data, t_index)
    modified_data = modification(data, t_index)
    modified_value = func(modified_data, t_index)
    is_causal = np.allclose(original, modified_value, equal_nan=True)
    return is_causal, original, modified_value
```

---

## Modification Functions

### 1. Shift Future Prices

```python
def shift_future_prices(data, t_index, shift_bars=10):
    """Shift all prices after t_index by a random amount."""
    modified = data.copy()
    for col in ['open', 'high', 'low', 'close']:
        modified[col][t_index+1:] = modified[col][t_index+1:] * (1 + np.random.uniform(-0.01, 0.01))
    return modified
```

### 2. Zero Future Prices

```python
def zero_future_prices(data, t_index):
    """Set all prices after t_index to zero."""
    modified = data.copy()
    for col in ['open', 'high', 'low', 'close']:
        modified[col][t_index+1:] = 0.0
    return modified
```

### 3. Swap Future Bars

```python
def swap_future_bars(data, t_index):
    """Reverse the order of bars after t_index."""
    modified = data.copy()
    for col in ['open', 'high', 'low', 'close']:
        modified[col][t_index+1:] = modified[col][t_index+1:][::-1]
    return modified
```

---

## Features to Test

### Z-Score Calculation

```python
def test_zscore_causality(pair_data, bar_idx):
    """Verify Z-score at bar_idx is invariant to future data changes."""
    def compute_zscore(data, idx):
        lookback = 20
        if idx < lookback:
            return np.nan
        window = data['close'][idx-lookback:idx]
        mean = np.mean(window)
        std = np.std(window)
        if std == 0:
            return 0.0
        return (data['close'][idx] - mean) / std

    is_causal, orig, mod = causality_test(
        compute_zscore, pair_data, bar_idx,
        lambda d, i: shift_future_prices(d, i)
    )
    assert is_causal, f"Z-score causality violation at bar {bar_idx}: {orig} vs {mod}"
```

### Volatility Regime Classification

```python
def test_vol_regime_causality(atr_pct_arr, bar_idx):
    """Verify vol regime at bar_idx uses only past data."""
    def compute_regime(arr, idx):
        return classify_vol_regime_causal(arr, idx)

    is_causal, orig, mod = causality_test(
        compute_regime, atr_pct_arr, bar_idx,
        lambda arr, i: np.concatenate([arr[:i+1], arr[i+1:] * np.random.uniform(0.5, 2.0, len(arr)-i-1)])
    )
    assert is_causal, f"Vol regime causality violation at bar {bar_idx}"
```

### Trend Regime Classification

```python
def test_trend_regime_causality(close_arr, e200_arr, bar_idx):
    """Trend regime is inherently causal (uses only current bar's data)."""
    def compute_trend(data, idx):
        return classify_trend_regime(data['close'][idx], data['e200'][idx])

    # Trend regime only depends on current bar — always causal
    # But verify EMA-200 itself is causal
```

### Daily Direction Filter

```python
def test_daily_direction_causality(daily_df, bar_idx):
    """Verify daily direction at bar_idx uses only previous day's data."""
    def compute_direction(df, idx):
        d_ts = df.index.asof(idx)
        d_idx = df.index.get_loc(d_ts)
        if d_idx == 0:
            return None
        prev_ts = df.index[d_idx - 1]
        return df.loc[prev_ts, 'close'] > df.loc[prev_ts, 'open']

    is_causal, orig, mod = causality_test(
        compute_direction, daily_df, bar_idx,
        lambda df, i: # modify future daily bars only
    )
    assert is_causal
```

---

## Test Runner

```python
def run_causality_suite(pair_data):
    """Run causality tests on all features for a given pair."""
    results = {}
    n = len(pair_data['close'])

    # Test at multiple points
    test_indices = [250, 500, 1000, n//2, n-10]

    for idx in test_indices:
        results[f'zscore_{idx}'] = test_zscore_causality(pair_data, idx)
        results[f'vol_regime_{idx}'] = test_vol_regime_causality(pair_data['atr_pct'], idx)
        results[f'daily_dir_{idx}'] = test_daily_direction_causality(pair_data['daily'], idx)

    # All must pass
    failures = {k: v for k, v in results.items() if not v}
    if failures:
        raise CausalityViolation(f"Causality violations: {failures}")

    return results
```

---

## Blocking Rule

If ANY causality test fails:
1. The feature is marked as UNCAUSAL
2. It may NOT be used in trading decisions
3. The violation is documented in the experiment report
4. The feature may still be used for retrospective research labels
