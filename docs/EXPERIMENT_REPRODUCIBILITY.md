# Z-Score Research Engine — Experiment Reproducibility

## Experiment Configuration

Every research run MUST record:

```python
@dataclass
class ExperimentConfig:
    # Identity
    experiment_id: str             # e.g., "ZS-2026-001"
    git_commit: str                # full commit hash
    timestamp: str                 # ISO 8601 UTC

    # Data
    dataset_version: str           # e.g., "dukascopy_minute_2016_2026"
    data_source: str               # e.g., "dukascopy"
    instruments: list[str]         # e.g., ["EUR/USD", "GBP/USD", ...]
    timeframe: str                 # e.g., "1min"
    date_range: tuple[str, str]    # ("2018-01-01", "2026-12-31")
    timezone: str                  # "UTC"

    # Execution costs
    spread_pips: dict[str, float]  # per-pair spread
    commission_per_lot: float      # USD per lot per side
    slippage_pips: float           # constant slippage
    execution_delay_bars: int      # 0 = same bar

    # Strategy parameters
    lookback_window: int           # Z-score lookback
    z_score_threshold: float       # entry threshold
    max_concurrent: int            # max open positions
    risk_per_trade: float          # fraction of balance
    leverage: float                # e.g., 100
    max_hold_bars: int             # maximum holding period

    # Session definitions
    sessions: dict[str, tuple[int, int]]  # e.g., {"london": (7, 16)}

    # Regime parameters
    vol_min_history: int           # minimum bars for vol classification
    trend_ema_distance_thresholds: tuple[float, float]  # (near, weak)

    # Random seeds (if applicable)
    random_seed: int | None

    # Software environment
    python_version: str
    numpy_version: str
    pandas_version: str
```

---

## Experiment Results

```python
@dataclass
class ExperimentResults:
    experiment_id: str
    config: ExperimentConfig

    # Performance
    trades: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    expectancy: float
    net_pnl: float
    max_drawdown_pct: float
    sharpe_ratio: float | None

    # Cost analysis
    total_spread_cost: float
    total_commission_cost: float
    total_slippage_cost: float
    total_cost: float
    cost_as_pct_of_pnl: float

    # Regime breakdown
    regime_performance: dict      # regime -> {trades, pf, wr}

    # Session breakdown
    session_performance: dict     # session -> {trades, pf, wr}

    # Causality status
    causality_violations: list[str]  # empty if all pass

    # File paths
    metrics_path: str             # JSON metrics file
    report_path: str              # human-readable report
```

---

## Storage Convention

```
/root/nestquant/
├── experiments/
│   ├── ZS-2026-001/
│   │   ├── config.json
│   │   ├── results.json
│   │   ├── metrics.json
│   │   └── report.md
│   ├── ZS-2026-002/
│   │   └── ...
│   └── ...
├── logs/
│   ├── mr_baseline_metrics.json
│   ├── mr_phase2_metrics.json
│   └── ...
```

---

## Git Integration

Before each experiment:
1. Record current commit hash
2. Ensure working directory is clean (or record dirty state)
3. Save config with commit hash

```python
import subprocess
def get_git_commit():
    return subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'],
        cwd='/root/nestquant'
    ).decode().strip()
```

---

## Minimal Implementation (Phase 1)

Do NOT build experiment infrastructure yet.
Establish the minimum:

1. ExperimentConfig dataclass (defined above)
2. A function to auto-populate from current state
3. A function to save config + results as JSON

```python
def create_experiment(config: ExperimentConfig) -> str:
    """Create experiment directory and save config."""
    exp_dir = f"/root/nestquant/experiments/{config.experiment_id}"
    os.makedirs(exp_dir, exist_ok=True)
    with open(f"{exp_dir}/config.json", 'w') as f:
        json.dump(asdict(config), f, indent=2, default=str)
    return exp_dir

def save_results(exp_dir: str, results: ExperimentResults):
    """Save experiment results."""
    with open(f"{exp_dir}/results.json", 'w') as f:
        json.dump(asdict(results), f, indent=2, default=str)
```

---

## Reproducibility Checklist

Before publishing any result:

- [ ] Experiment ID is unique
- [ ] Git commit is recorded
- [ ] All configuration parameters are in config.json
- [ ] Dataset version and date range are specified
- [ ] Spread, commission, slippage are explicit
- [ ] Random seed is set (if applicable)
- [ ] Causality tests pass (no violations)
- [ ] Metrics file is complete
- [ ] Report includes all required fields (AGENTS.md §21)
