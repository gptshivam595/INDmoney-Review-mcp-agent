# Phase 0 Evaluations - Foundations and Agent Skeleton

## Objective

Prove that the project can boot as one agent runtime with deterministic run identity, config loading, storage initialization, and a usable CLI.

## Test Matrix

| Area | Evaluation | Pass condition |
| --- | --- | --- |
| CLI surface | Run `pulse --help` | all planned commands appear without import errors |
| Config loading | Load `products.yaml` with one valid and one invalid fixture | valid config loads, invalid config fails with useful message |
| Database bootstrap | Run `pulse init-db` on empty workspace | all core tables are created |
| Deterministic identity | compute `run_id` and anchor twice for same inputs | identical outputs across runs |
| Logging | execute a stub run | log lines include `run_id` and phase |

## Required Automated Checks

- unit test for `run_id` generation
- unit test for anchor generation
- unit test for config schema validation
- integration test for DB creation

## Demo

Run:

```text
pulse init-db
pulse plan-run --product indmoney --week 2026-W17
```

Expected result:

- database exists
- a planned run row is written
- output includes the deterministic `run_id`

## Metrics to Record

- CLI startup time
- DB init duration
- number of created tables

## Exit Gate

Phase 0 passes when a developer can bootstrap the repo, initialize storage, and create a planned run without touching production services.
