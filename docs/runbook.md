# Weekly Product Review Pulse - Runbook

## Purpose

This runbook covers the operational path for the weekly pulse agent after Phase 7 orchestration.

## Main Commands

Initialize local state:

```text
pulse init-db
```

Run one product for the current week in safe draft mode:

```text
pulse run --product indmoney --draft-only
```

Backfill a past week:

```text
pulse run --product indmoney --week 2026-W15 --draft-only
```

Run the final Gmail send path:

```text
pulse run --product indmoney --week 2026-W17
```

## Checkpoint Resume

The orchestrator resumes from stored checkpoints instead of replaying completed work.

- if ingestion already succeeded, the rerun skips ingestion
- if Docs publish already succeeded, the rerun skips Docs append
- if Gmail already created a draft or message, the rerun skips duplicate notification

This means the safe recovery action after a transient failure is to rerun the same `product + iso_week`.

## Failure Recovery

If the run fails before Docs publish:

1. inspect the logged exception
2. fix the root cause
3. rerun the same `pulse run --product <key> --week <iso_week>`

If the run fails after Docs publish:

1. rerun the same command
2. the orchestrator should skip duplicate Docs append
3. Gmail delivery resumes from the stored Doc link

If the run fails after Gmail draft creation:

1. rerun the same command
2. the orchestrator should skip duplicate draft creation
3. inspect the stored draft in Gmail before forcing another send attempt

## Operational Checks

After a successful run, verify:

- `runs.status` is `completed`
- `metrics_json` contains `ingestion`, `analysis`, `summarization`, `rendering`, `publish_docs`, `publish_gmail`, and `orchestration`
- the running Google Doc contains the section anchor for the target week
- the Gmail draft or sent message includes the final Google Doc deep link

## Common Issues

Docs MCP unreachable:

- verify the MCP helper server is running
- check `PULSE_DOCS_MCP_BASE_URL`

Gmail MCP unreachable:

- verify the MCP helper server is running
- check `PULSE_GMAIL_MCP_BASE_URL`

No reviews found or too few eligible reviews:

- confirm the product identifiers in `products.yaml`
- retry with a backfill week that has known review volume

Invalid recipients:

- validate the stakeholder email addresses in `products.yaml`
