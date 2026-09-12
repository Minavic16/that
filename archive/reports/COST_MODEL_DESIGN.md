# Z-Score Research Engine — Cost Model Design

## Philosophy

The cost model must be:
1. **Configurable** — all parameters adjustable without code changes
2. **Transparent** — every cost explicitly recorded per trade
3. **Testable** — cost sensitivity experiments are a first-class feature
4. **Causal** — cost estimates at t use only information available at t

---

## Cost Components

### 1. Spread

```python
spread_cost = spread_pips * pip_value * lot_size
```

- Configurable per pair
- Applied on entry (half spread) and exit (half spread)
- Can be set to historical median, measured, or stressed

### 2. Commission

```python
commission_cost = commission_per_lot * lot_size * 2  # entry + exit
```

- Configurable per lot per side
- Typically $3.50 per lot per side for retail FX

### 3. Slippage

```python
slippage_cost = slippage_pips * pip_value * lot_size
```

- Configurable per trade
- Applied in the direction adverse to the trade
- Can be constant, random, or modelled

### 4. Execution Delay (Optional)

- Signal at bar t, execution at bar t+N
- During delay, price may move against the trade
- Modelled as additional slippage or as a separate bar offset

### 5. News-Related Degradation (Optional, Phase 2+)

- Spread widening during high-impact news
- Slippage increase during low-liquidity windows
- Requires news data integration

---

## Cost Model Configuration

```python
@dataclass
class CostModelConfig:
    # Per-pair spread (pips)
    spread_pips: dict[str, float] = field(default_factory=lambda: {
        'EUR/USD': 1.0, 'GBP/USD': 1.6, 'USD/JPY': 1.0,
        'USD/CHF': 1.2, 'AUD/USD': 1.2, 'NZD/USD': 1.6,
        'EUR/GBP': 1.6, 'EUR/JPY': 1.9, 'GBP/JPY': 3.0,
        'AUD/JPY': 1.9, 'NZD/JPY': 1.9, 'EUR/AUD': 2.6,
        'GBP/AUD': 3.9, 'AUD/NZD': 2.0, 'USD/CAD': 1.5,
        'CAD/CHF': 1.8, 'EUR/CHF': 1.5, 'GBP/CHF': 2.6,
        'AUD/CHF': 2.0, 'NZD/CHF': 2.6,
    })
    commission_per_lot: float = 3.50    # USD per lot per side
    slippage_pips: float = 0.3          # constant slippage estimate
    execution_delay_bars: int = 0       # same-bar execution
```

---

## Cost Sensitivity Experiments

The architecture must support sweeping cost parameters:

```
For slippage in [0.0, 0.3, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
    Run backtest with slippage=slippage
    Record: PF, WR, expectancy, PnL, MDD
    Report break-even slippage (where expectancy = 0)

For spread in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
    Run backtest with spread=spread
    Record: PF, WR, expectancy, PnL, MDD
    Report break-even spread

For commission in [0.0, 1.0, 2.0, 3.5, 5.0, 7.0]:
    Run backtest with commission=commission
    Record: PF, WR, expectancy, PnL, MDD
    Report break-even commission
```

Break-even cost = the cost level at which strategy expectancy becomes zero.

---

## Cost Application in Simulation

```python
def apply_costs(entry_price, exit_price, direction, cost_model, pip, pv, lot):
    """Apply all costs and return net PnL components."""
    # Entry price already includes half-spread + slippage
    # Exit price includes half-spread + slippage in opposite direction

    gross_pnl = (exit_price - entry_price) * direction / pip * pv * lot
    spread_cost = cost_model.spread_pips * pv * lot
    commission_cost = cost_model.commission_per_lot * lot * 2
    slippage_cost = cost_model.slippage_pips * pv * lot

    total_cost = spread_cost + commission_cost + slippage_cost
    net_pnl = gross_pnl - total_cost

    return {
        'gross_pnl': gross_pnl,
        'spread_cost': spread_cost,
        'commission_cost': commission_cost,
        'slippage_cost': slippage_cost,
        'total_cost': total_cost,
        'net_pnl': net_pnl,
    }
```

---

## Reporting Requirement

Every trade must report:
- gross_pnl
- spread_cost
- commission_cost
- slippage_cost
- total_cost
- net_pnl

Aggregate reports must show:
- Total costs as percentage of gross PnL
- Cost-adjusted PF vs raw PF
- Break-even costs
