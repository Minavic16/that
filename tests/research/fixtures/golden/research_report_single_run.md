# Research Report

- Report type: `research_report`  
- Schema version: `1.0`  
- Generated at: `2024-06-01T00:00:00+00:00`  
- Renderer: `markdown:1.0`

## Summary

- Evaluation ID: `eval-fixture00000001`
- Status: `VALID_WITH_WARNINGS`
- Face: `evaluation`
- Closed trades (finite PnL): 3
- Win rate: 66.7%
- Profit factor: 2.6
- Warnings: 1

## Experiment

- Experiment ID: exp-fixture
- Strategy / workload: fixture-strategy
- Run ID: `run-fixture00000001`
- Experiment context: unavailable

## Evaluation

**Evaluation metrics** (canonical, not recalculated):

| Metric | Value | Unit | Status |
|---|---:|---|---|
| `total_trades` | 3 | count | DEFINED |
| `winning_trades` | 2 | count | DEFINED |
| `losing_trades` | 1 | count | DEFINED |
| `breakeven_trades` | 0 | count | DEFINED |
| `win_rate` | 66.7% | ratio | DEFINED |
| `total_pnl` | 8 | currency | DEFINED |
| `gross_profit` | 13 | currency | DEFINED |
| `gross_loss` | -5 | currency | DEFINED |
| `profit_factor` | 2.6 | ratio | DEFINED |
| `average_win` | 6.5 | currency | DEFINED |
| `average_loss` | -5 | currency | DEFINED |
| `expectancy` | 2.66667 | currency | DEFINED |
| `max_drawdown` | 5 | currency | DEFINED |
| `max_drawdown_pct` | 0.05% | percent | DEFINED |
| `total_return` | 0.0008 | ratio | DEFINED |
| `sharpe_ratio` | 6.90768 | ratio | DEFINED |
| `average_trade_duration` | 7200 | timedelta_seconds | DEFINED |
| `average_winning_trade_duration` | 9000 | timedelta_seconds | DEFINED |
| `average_losing_trade_duration` | 3600 | timedelta_seconds | DEFINED |

- Evaluation config: rf=0.0, periods_per_year=252, min_obs=2

## Folds

- Not applicable (single-run evaluation without fold payload).

## Provenance

- Run ID: `run-fixture00000001`
- Experiment ID: exp-fixture
- Strategy identity: fixture-strategy
- Git available: `true`
- Git commit: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Git dirty: false
- Code version: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Data instruments: EUR/USD
- Data timeframe: 1h
- Data source: fixture://data
- Data checksum: `deadbeef`
- Data dataset_id: `ds-fixture`
- Data dataset_version: `1`
- Data n_bars: 100
- Execution config hash: `1111111111111111`
- Evaluation config hash: `2222222222222222`
- Evaluation ID: `eval-fixture00000001`
- Evaluation status (provenance): `VALID_WITH_WARNINGS`
- Evaluation status (face): `VALID_WITH_WARNINGS`
- Created at: `2024-06-01T00:00:00+00:00`
- Parent run ID: `unavailable`
- Notes:
  - fixture note

## Warnings & Limitations

- `equity_curve_missing_trade_normalized_drawdown` — Drawdown uses trade-normalized path (equity curve missing).

### Limitations applicable to this report

- Sharpe uses trade-PnL series annualized with √252 (not portfolio time-series Sharpe).
- Drawdown source is warning-distinguished (trade-normalized, not equity-path).
