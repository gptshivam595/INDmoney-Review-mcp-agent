# Phase 5 Evaluations - Google Docs MCP Append

## Objective

Prove that the agent can append a weekly report section to the running product Google Doc using MCP only, while remaining idempotent.

## Test Matrix

| Area | Evaluation | Pass condition |
| --- | --- | --- |
| Doc resolution | publish for product with no existing Doc | Doc is created or resolved successfully |
| First append | publish new run | section is appended |
| Duplicate prevention | publish same run again | second call is skipped after anchor check |
| Metadata capture | inspect persisted run state | `gdoc_id` and section metadata are stored |
| Real workspace smoke | publish to test workspace | rendered section appears in expected running Doc |

## Required Automated Checks

- integration test against mock Docs MCP server
- test that pre-append read happens before write
- test that append is skipped when anchor already exists

## Demo

Run:

```text
pulse publish-docs --run <run_id>
```

Expected result:

- running Doc is found or created
- report section is appended once
- rerun reports a no-op because the anchor already exists

## Metrics to Record

- Docs MCP call count
- Docs MCP latency
- whether Doc was created or reused
- append status

## Exit Gate

Phase 5 passes when the agent can publish the weekly report into the correct running Google Doc through MCP and avoid duplicates on rerun.
