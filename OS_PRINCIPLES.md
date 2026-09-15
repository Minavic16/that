# NQTS Operational Principles
# Codified from incident post-mortem and production validation.
# Date: 2026-09-15

## Principle 1: Fail Closed, Never Fail Semantically

When a component cannot determine its state, it must report failure rather than
assume health. A dashboard that cannot read state.json must say RED, not guess GREEN.
A runner that cannot reach MT5 must say DEGRADED, not pretend connected.

Semantic failures are worse than crashes. A silently wrong signal is worse than
no signal at all.

## Principle 2: Environment Independence

No production code may assume a specific filesystem layout, hostname, IP address,
or directory structure. All paths must be derived from one of:
- Module location (Path(__file__).resolve())
- Environment variables
- Configuration files
- Working directory

The same code must run on the dev machine (/root/that), the VPS (/root/nestquant),
and any future environment without modification. The /root/that incident
(commits 9ad7d49 through 8b7ed7a) proved that hardcoded paths are ticking bombs.

## Principle 3: Evidence Before Root Cause

When diagnosing a production incident, collect evidence before theorizing.
The telemetry pipeline failure was diagnosed by:
1. Checking state.json contents (evidence: bars=601, signals=9)
2. Checking the dashboard API response (evidence: bars_processed=601)
3. Checking file paths in compiled code (evidence: /root/that/ everywhere)
4. Checking /root/that existence on VPS (evidence: does not exist)

Only after 4/4 evidence points converged did we conclude root cause.

Do not skip to "it must be a stale build" without checking whether the
build actually changed. The build was correct. The paths were wrong.

## Principle 4: Runtime Truth Over Activity

A system that has been running correctly for 16 hours with no new signals
is HEALTHY. A system that generates 100 signals in an hour but cannot
report its state is UNHEALTHY.

The purpose of the shadow runner is not to generate signals. It is to:
1. Continuously operate according to its constitution
2. Preserve state across restarts
3. Maintain data integrity
4. Survive expected operational events
5. Faithfully report what it is doing

Signal generation is a consequence of market structure, not a goal.

## Principle 5: Version Identity Must Be Explicit and Machine-Readable

Every deployment must answer: "What version of the system is running?"

Before: "What code happens to be running?" (answer required git log + file inspection)
After: VERSION file with NQTS_VERSION, NQTS_CODENAME, Git HEAD, deployment timestamp.

The VERSION file at the repo root is the single source of truth for system identity.
It must be updated when making meaningful system changes.

## Principle 6: Paths Are Contracts

Every hardcoded path is a contract between the code and the filesystem.
When the filesystem changes (new machine, new user, new layout), every
contract must be renegotiated.

Use relative paths, __file__-derived paths, or environment variables.
Never hardcode absolute paths in production code. The contract cost is
too high and the failure mode is silent.

## Principle 7: Test Reality, Not Configuration

Tests that verify hardcoded values are testing configuration, not behavior.
Tests that verify dynamic behavior (does state.json drive the dashboard?)
are testing reality.

Prefer integration tests over unit tests for production validation.
A unit test that checks "the constant is 3600" tells you nothing about
whether the system actually uses 3600.
