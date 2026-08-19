# Z-Score Research Engine — Test Structure

## Directory Layout

```
tests/
├── conftest.py                 # Shared fixtures
├── unit/
│   ├── __init__.py
│   ├── test_data_validation.py
│   ├── test_features.py
│   ├── test_regime.py
│   ├── test_zscore.py
│   ├── test_signals.py
│   ├── test_costs.py
│   ├── test_portfolio.py
│   └── test_position_sizing.py
├── integration/
│   ├── __init__.py
│   ├── test_pipeline.py        # Full pipeline integration
│   └── test_data_flow.py       # Data flows between stages
├── regression/
│   ├── __init__.py
│   ├── test_causality.py       # Causality violations
│   └── test_lookahead.py       # Look-ahead bias detection
└── smoke/
    ├── __init__.py
    └── test_end_to_end.py      # Minimal e2e smoke test
```

---

## Test Categories

### Unit Tests (`tests/unit/`)

Test individual functions in isolation.
Each test file corresponds to one pipeline stage.

**Fixture requirements:**
- Small synthetic data (500-1000 bars)
- Known expected outputs
- No external dependencies

**Example:**
```python
def test_classify_vol_regime_causal():
    atr = np.random.uniform(0.5, 2.0, 500)
    # First 200 bars should return 'unknown'
    for i in range(200):
        assert classify_vol_regime_causal(atr, i) == 'unknown'
    # Bar 200+ should return a valid regime
    for i in range(200, 500):
        regime = classify_vol_regime_causal(atr, i)
        assert regime in ['low_vol', 'mid_vol', 'high_vol', 'extreme_vol']
```

### Integration Tests (`tests/integration/`)

Test that pipeline stages connect correctly.
Verify data flows between stages without corruption.

**Example:**
```python
def test_feature_to_regime_flow():
    data = generate_synthetic_data()
    validated = validate_data(data)
    normalized = normalize_data(validated)
    features = compute_features(normalized)
    regimes = classify_regimes(features)
    # Verify regimes align with features
    assert len(regimes) == features.n
```

### Regression Tests (`tests/regression/`)

Prevent previously fixed bugs from returning.
Each test documents the specific bug it guards against.

**Example:**
```python
def test_daily_direction_causality():
    """Regression: daily candle look-ahead (Phase 5 finding).
    The strategy used today's close at intraday timestamps.
    This test verifies the fix uses only previous day's data."""
    daily = create_daily_data()
    ts = pd.Timestamp('2024-01-15 10:00', tz='UTC')
    direction = compute_daily_direction(daily, ts)
    # Must NOT use today's close
    today_close = daily.loc[daily.index.asof(ts), 'close']
    assert direction != (today_close > daily.loc[daily.index.asof(ts), 'open'])
```

### Smoke Tests (`tests/smoke/`)

Minimal end-to-end pipeline execution.
Verifies structural integrity, not correctness.

**See:** `SMOKE_TEST_SPEC.md`

---

## Conftest Fixtures

```python
@pytest.fixture
def synthetic_ohlcv():
    """Generate 500-bar synthetic OHLCV data with known properties."""
    n = 500
    timestamps = pd.date_range('2024-01-02', periods=n, freq='1min', tz='UTC')
    np.random.seed(42)
    close = 1.1000 + np.cumsum(np.random.randn(n) * 0.0001)
    high = close + np.abs(np.random.randn(n) * 0.00005)
    low = close - np.abs(np.random.randn(n) * 0.00005)
    open_ = close + np.random.randn(n) * 0.00002
    return pd.DataFrame({
        'open': open_, 'high': high, 'low': low, 'close': close
    }, index=timestamps)

@pytest.fixture
def synthetic_daily(synthetic_ohlcv):
    """Generate daily OHLCV from synthetic minute data."""
    return synthetic_ohlcv.resample('1D').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna()

@pytest.fixture
def pair_metadata():
    """Instrument metadata for test pair."""
    return InstrumentMetadata(
        pair='TEST/USD', pip_size=0.0001,
        pip_value_per_lot=10.0, typical_spread_pips=1.0,
        contract_size=100000
    )
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Unit only
pytest tests/unit/ -v

# Integration only
pytest tests/integration/ -v

# Regression only
pytest tests/regression/ -v

# Smoke only
pytest tests/smoke/ -v

# Causality tests specifically
pytest tests/regression/test_causality.py -v

# With coverage
pytest tests/ --cov=nestquant --cov-report=term-missing
```

---

## Test Naming Convention

- `test_<function_name>_<scenario>` for unit tests
- `test_<stage>_to_<stage>_flow` for integration tests
- `test_regression_<bug_id>` for regression tests
- `test_smoke_<pipeline_step>` for smoke tests
