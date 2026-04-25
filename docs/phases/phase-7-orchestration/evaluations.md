# Phase 7 Evaluations - Orchestration and Hardening

## Objective

Prove that the full weekly pulse agent can run unattended, resume from failure, remain idempotent, and expose useful operational telemetry.

## Test Matrix

| Area | Evaluation | Pass condition |
| --- | --- | --- |
| End-to-end run | execute full run on fixture-backed environment | final status is `completed` |
| Resume | fail after Docs publish then rerun | Gmail resumes without duplicate Doc append |
| Weekly schedule | execute scheduled workflow in staging | one run per active product is triggered |
| Backfill | run a past ISO week | run completes with correct `run_id` and no duplicate delivery |
| Observability | inspect logs and metrics | run emits timings, statuses, and cost figures |

## Required Automated Checks

- end-to-end integration test through mocked MCP servers
- retry behavior test for transient network or MCP failures
- idempotent rerun test for same `product + iso_week`

## Demo

Run:

```text
pulse run --product indmoney
```

Expected result:

- all phases execute in order
- Google Doc append happens before Gmail
- run metadata shows resumable checkpoints

## Metrics to Record

- end-to-end run duration
- phase durations
- total tokens and cost
- retries by phase
- delivery success rate

## Exit Gate

Phase 7 passes when the full weekly agent can run in staging without manual intervention and recover safely from partial failure.
