# Phase 6 Evaluations - Gmail MCP Delivery

## Objective

Prove that the agent can draft or send one stakeholder notification per run through Gmail MCP and include the Google Doc section link.

## Test Matrix

| Area | Evaluation | Pass condition |
| --- | --- | --- |
| Link injection | render final email after Docs publish | email contains resolved Doc link |
| Draft flow | run in draft-only mode | Gmail draft is created, nothing is sent |
| Send flow | run with sending enabled | exactly one message is sent |
| Duplicate prevention | rerun same publish step | second publish is skipped |
| Real workspace smoke | deliver to test inbox | received message contains expected subject and Doc link |

## Required Automated Checks

- integration test against mock Gmail MCP server
- test for search-before-create behavior
- test that Gmail publish is blocked when Docs link is absent

## Demo

Run:

```text
pulse publish-gmail --run <run_id> --draft-only
```

Expected result:

- draft is created with the correct run metadata
- rerun skips duplicate creation
- switching to send mode sends once

## Metrics to Record

- Gmail MCP call count
- draft creation latency
- send latency
- draft or send status

## Exit Gate

Phase 6 passes when the agent can create or send one notification per run through Gmail MCP and never notify without a valid Google Doc destination.
