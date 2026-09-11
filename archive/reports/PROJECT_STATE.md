# NestQuant — Project State

**Last updated:** 2026-08-07

## Current Objective

Establish a clean, reproducible Git/GitHub baseline for NestQuant and then systematically audit, test, and improve the trading engine.

## Repository

- Local path: `/root/nestquant`
- Git remote: `https://github.com/Minavic16/that.git`
- Remote branch: `origin/master`
- Local NestQuant `.git`: present
- Current local branch: `master`
- Current state: NestQuant files are currently untracked locally.

## Current Architecture

NestQuant currently contains components for:

- Backtesting
- Indicators
- Trading signals
- Execution
- Portfolio management
- Risk management
- Market regime detection
- Data loading
- Experiment tracking
- Utilities
- Logging

## Current Trading System

The project has previously included:

- Multi-timeframe trend following
- Mean reversion
- MR+TF engine
- Statistical/arbitrage research
- Momentum/breakout research
- cTrader execution
- MT5 execution

The exact current production configuration must be verified from the code before making changes.

## Infrastructure

- VPS-based development/deployment
- Python virtual environment
- Git/GitHub
- Live trading infrastructure
- Dashboard and engine processes may exist outside the repository

## Important Rule

Do not modify trading logic or execution behavior until the current codebase has been audited and a reproducible baseline has been established.

## Current Task

1. Establish Git baseline.
2. Verify repository contents and ignore rules.
3. Create reproducible project documentation.
4. Audit current architecture.
5. Run tests and validation.
6. Review live engine behavior.
7. Make changes deliberately.
8. Commit and document every meaningful checkpoint.

## Next Action

Create the initial clean Git checkpoint after verifying the files to be committed.
